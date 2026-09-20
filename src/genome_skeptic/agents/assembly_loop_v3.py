"""Assembly-level agentic target loop, version 3 (genome_skeptic_agentic_v3).

Frozen V2 (``assembly_loop_v2.py``) is not modified. V3 reuses V2 deterministic
executors and the measurement-patch contract. The changes are control flow:

1. Planner evidence_ids ground the scientific claim, not action execution.
2. The critic still runs after recoverable planner control/grounding failures.
3. A deterministic DiagnosticNeed layer ranks the 2–3 actions shown to the LLM.
4. Inert catalog entries are excluded from selection.

The LLM never authors a measurement. ``build_target_gene_claim`` remains the
authority. D20 is not read or used here.
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from genome_skeptic.agents.action_catalog import BY_ID, catalog_payload, state_changing_action_ids
from genome_skeptic.agents.action_catalog_v3 import (
    INERT_ACTION_IDS,
    executable_actions_before_ranking,
    is_active,
    rank_candidate_actions,
)
from genome_skeptic.agents.action_contract import (
    ABSTAIN_UNRESOLVED,
    CONTROL_DECISION_SEMANTICS,
    CONTROL_DECISIONS,
    FINALIZE_WITH_CURRENT_EVIDENCE,
)
from genome_skeptic.agents.assembly_loop import (
    _call_stats,
    _llm_measurement_entered_claim,
    _LoopState,
    _sha256_obj,
    _sha256_text,
    collect_assembly_target_measurements,
    measurements_to_evidence,
)
from genome_skeptic.agents.assembly_loop_v2 import (
    BASELINE_WORK,
    REGISTERED_CHOICES,
    _V2Run,
    _alias_v1_requested_actions,
    _critic_defects,
    _llm_runtime_breakdown,
    _next_states,
    _recover_critic_fields,
    _recover_planner_fields,
    _unresolved_failure,
    _validate_critic,
    capabilities_for,
    critic_decision_to_review,
    planner_decision_to_agent,
    run_action_and_update,
)
from genome_skeptic.agents.diagnostic_needs import derive_diagnostic_needs, need_payload
from genome_skeptic.agents.ollama import OllamaJSONClient
from genome_skeptic.agents.planner_views import estimated_tokens
from genome_skeptic.agents.planner_views_v3 import build_critic_view_v3, build_planner_view_v3
from genome_skeptic.agents.providers import reset_call_log
from genome_skeptic.claims.hypothesis_graph import HYPOTHESIS_IDS
from genome_skeptic.config import Settings
from genome_skeptic.isolation import assert_agent_accessible
from genome_skeptic.models import (
    AgentDecision,
    Claim,
    CriticDecision,
    CriticReview,
    LocusEvidence,
    PlannerDecision,
)
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim

SYSTEM_NAME = "genome_skeptic_agentic_v3"

GROUNDING_GROUNDED = "GROUNDED"
GROUNDING_MISSING = "MISSING"

AGENTIC_REASONER_SYSTEM = (
    "You choose the next measurement for a bacterial genome target-gene question. "
    "Do not invent measurements. The deterministic validator assigns the final claim. "
    "Return one concise decision. At most one alternative hypothesis. At most one requested action. "
    "Rationale <= 160 characters. Do not restate evidence values. "
    "decision is investigate, finalize, or abstain. "
    "requested_action is one available_actions id, "
    f"'{FINALIZE_WITH_CURRENT_EVIDENCE}', '{ABSTAIN_UNRESOLVED}', or null. "
    f"Use '{ABSTAIN_UNRESOLVED}' only when available_actions is empty. "
    "evidence_ids ground the claim; an investigation action may still be chosen if they are empty."
)

AGENTIC_CRITIC_SYSTEM = (
    "You are an adversarial scientific reviewer of a bacterial genome analysis. "
    "Do not invent measurements. The deterministic validator assigns the final claim. "
    "You receive the actual deterministic scientific state after any action that ran. "
    "Return one JSON object with verdict (accept or challenge), evidence_ids (from valid_evidence_ids), "
    "requested_action (one remaining_actions / available_actions id if challenge, else null), "
    "failure_mode (one registered_hypothesis_ids id if challenge, else null), "
    "and rationale (one sentence). At most one additional action."
)


def _planner_defects_v3(decision: AgentDecision, offered: set[str], dropped: list[str], known: set[str]) -> list[str]:
    """Repair-worthy defects. Empty evidence_ids is grounding status, not a crash."""
    defects: list[str] = []
    if dropped:
        defects.append(
            f"evidence_ids contained {dropped}, which are not evidence IDs. "
            f"Valid evidence IDs are exactly: {sorted(known)}. "
            "Input names, measurement field names and action names are not evidence IDs."
        )
    actions = list(decision.requested_actions or [])
    if not actions:
        defects.append(
            "requested_actions was empty; return exactly one action_id from available_actions "
            f"or one decision_id from control_decisions (use '{ABSTAIN_UNRESOLVED}' if no available "
            "action can change a relevant measurement)."
        )
    elif len(actions) > 1:
        defects.append(f"requested_actions must contain exactly one entry, not {actions}.")
    else:
        choice = actions[0]
        if choice not in REGISTERED_CHOICES:
            defects.append(
                f"requested_actions contained {[choice]}, which is not registered. "
                "Choose one action_id from available_actions or one decision_id from control_decisions."
            )
        elif choice not in CONTROL_DECISIONS and choice not in offered and offered:
            defects.append(
                f"requested_action {choice} is not in the ranked available_actions {sorted(offered)}. "
                "Choose one of those ids or a control decision."
            )
    return defects


def _validate_planner_v3(
    decision: AgentDecision,
    known: set[str],
    offered: set[str],
) -> tuple[str | None, str, str | None, str | None]:
    """Return (choice, grounding_status, recoverable_control_failure, unrecoverable_failure)."""
    grounding = GROUNDING_GROUNDED if (decision.evidence_ids or []) else GROUNDING_MISSING
    unknown = [eid for eid in (decision.evidence_ids or []) if eid not in known]
    if unknown:
        return None, grounding, None, f"planner cited unknown evidence IDs: {unknown}"
    actions, _v1 = _alias_v1_requested_actions(decision.requested_actions, decision.decision)
    if not actions:
        return ABSTAIN_UNRESOLVED, grounding, None, None
    if len(actions) > 1:
        return None, grounding, f"planner requested more than one action: {actions}", None
    choice = actions[0]
    if choice not in REGISTERED_CHOICES:
        return None, grounding, None, f"planner requested an unregistered action: {choice}"
    if choice in CONTROL_DECISIONS:
        return choice, grounding, None, None
    if not is_active(choice):
        return None, grounding, f"planner requested an inert action excluded from the V3 catalog: {choice}", None
    if offered and choice not in offered:
        return None, grounding, f"planner requested an action not in the ranked candidate set: {choice}", None
    spec = BY_ID.get(choice)
    if spec is None:
        return None, grounding, None, f"planner requested an unregistered action: {choice}"
    return choice, grounding, None, None


def select_critic_action_v3(
    critic: CriticReview,
    remaining_ids: list[str],
    already_run: list[str],
) -> tuple[str | None, str]:
    """At most one critic-requested action, and only if it remains relevant."""
    if critic.verdict != "challenge":
        return None, "critic accepted the decision, so no further measurement was triggered"
    named = [a for a in (critic.disconfirming_tests or []) if a]
    remaining = [a for a in remaining_ids if a not in already_run]
    for action_id in named:
        if action_id in remaining:
            return action_id, f"critic named a remaining relevant action: {action_id}"
    if named:
        return None, f"critic named {named} but none remain in the ranked relevant set {remaining}"
    return None, "critic challenged without naming a remaining relevant action"


def _planner_payload(m: TargetMeasurements, run: _V2Run, already: list[str] | None = None) -> dict[str, Any]:
    return build_planner_view_v3(
        m,
        evidence=run.state.evidence,
        capabilities=run.capabilities,
        performed=run.baseline_work,
        settings=run.state.settings,
        actions_already_tried=already,
    )


def _critic_payload(
    decision: AgentDecision,
    run: _V2Run,
    m: TargetMeasurements,
    transition,
    already_run: list[str],
    planner_grounding_status: str | None,
    planner_control_failure: str | None,
) -> dict[str, Any]:
    new_ids = set(transition.result.evidence_ids) if transition is not None else set()
    new_evidence = [e for e in run.state.evidence if e.id in new_ids] if new_ids else run.state.evidence[-4:]
    return build_critic_view_v3(
        decision,
        m=m,
        evidence=run.state.evidence,
        capabilities=run.capabilities,
        performed=run.baseline_work,
        actions_already_tried=already_run,
        new_evidence=new_evidence,
        transition=None if transition is None else transition.as_dict(),
        settings=run.state.settings,
        planner_grounding_status=planner_grounding_status,
        planner_control_failure=planner_control_failure,
    )


def run_skeptic_agentic_v3(
    assembly: Path,
    targets: Path,
    out_dir: Path,
    settings: Settings,
    *,
    references: Path | None = None,
    gff: Path | None = None,
    proteins: Path | None = None,
    declared_organism: str | None = None,
    mapping_sam: Path | None = None,
    depth_tsv: Path | None = None,
    query_ids: list[str] | None = None,
    initial_measurements: TargetMeasurements | None = None,
) -> tuple[list[Claim], list[LocusEvidence], dict[str, Any]]:
    """Agentic V3. Frozen V1, frozen V2, and frozen deterministic V5 are untouched."""
    t0 = time.perf_counter()
    assert_agent_accessible(assembly)
    assert_agent_accessible(targets)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reset_call_log()
    state = _LoopState(
        settings=settings,
        assembly=Path(assembly),
        targets=Path(targets),
        out_dir=out_dir,
        declared_organism=declared_organism,
        mapping_sam=Path(mapping_sam) if mapping_sam else None,
        depth_tsv=Path(depth_tsv) if depth_tsv else None,
        assembly_gff=Path(gff) if gff else None,
        proteins_path=Path(proteins) if proteins else None,
        references_yaml=Path(references) if references else None,
    )
    state.call_graph.append("run_skeptic_agentic_v3")
    provenance: dict[str, Any] = {
        "system": SYSTEM_NAME,
        "planner_invoked": False,
        "critic_invoked": False,
        "model_name": settings.llm.model,
        "prompt_hash": None,
        "response_hash": None,
        "critic_prompt_hash": None,
        "critic_response_hash": None,
        "cited_evidence_ids": [],
        "critic_cited_evidence_ids": [],
        "selected_action": None,
        "control_decision": None,
        "critic_challenge": None,
        "critic_second_action": None,
        "critic_second_action_reason": None,
        "agent_failure": None,
        "final_validator_ran": False,
        "planner_returned_empty_plan": False,
        "planner_chose_unavailable_action": False,
        "planner_grounding_status": None,
        "planner_control_failure": None,
        "abstention_justified": None,
        "actions_executed": [],
        "measurement_trajectory": [],
        "measurements_changed_before_validation": False,
        "initial_measurements_injected": initial_measurements is not None,
        "validator_consumed_measurement_hash": None,
        "validator_consumed_m0": None,
        "silent_deterministic_fallback": False,
        "inert_actions_excluded": sorted(INERT_ACTION_IDS),
    }

    if initial_measurements is not None:
        measurements = copy.deepcopy(initial_measurements)
        loci = list(measurements.locus_evidence or [])
        state.contig_seqs = dict(measurements.contig_sequences or {})
        state.call_graph.append("initial_measurements_injected")
    else:
        measurements, loci = collect_assembly_target_measurements(state, query_ids=query_ids)
    before_ids = measurements_to_evidence(state, measurements)
    provenance["evidence_ids_before_action"] = list(before_ids)

    run = _V2Run(state=state, baseline_work=BASELINE_WORK)
    run.capabilities = capabilities_for(state, measurements)
    provenance["available_inputs"] = dict(run.capabilities)
    edge_bp = int(settings.thresholds.contig_edge_proximity_bp)
    needs0 = derive_diagnostic_needs(measurements, run.capabilities, settings=settings, edge_bp=edge_bp)
    provenance["diagnostic_needs_m0"] = need_payload(needs0)
    executable0 = executable_actions_before_ranking(
        needs0, run.capabilities, run.baseline_work, measurements, edge_bp=edge_bp
    )
    provenance["executable_actions_before_ranking"] = executable0
    ranked0 = rank_candidate_actions(
        needs0, run.capabilities, run.baseline_work, measurements, edge_bp=edge_bp, limit=3
    )
    provenance["ranked_candidate_actions"] = ranked0
    provenance["available_actions"] = [row["action_id"] for row in ranked0]
    provenance["actions_exposed_to_planner"] = [row["action_id"] for row in ranked0]
    provenance["baseline_work_already_done"] = sorted(run.baseline_work)
    provenance["state_changing_actions"] = [
        aid
        for aid in state_changing_action_ids(run.capabilities, run.baseline_work, measurements, edge_bp=edge_bp)
        if is_active(aid)
    ]
    provenance["inert_actions"] = [
        {"action_id": spec["action_id"], "because": spec["inert_now_because"]}
        for spec in catalog_payload(run.capabilities, run.baseline_work, measurements, edge_bp=edge_bp)
        if spec["action_id"] in INERT_ACTION_IDS or (spec["available"] and spec["inert_now"])
    ]

    from genome_skeptic.agents.action_contract import measurement_fingerprint

    m0 = measurement_fingerprint(measurements)
    provenance["measurement_state"] = {"m0": m0}

    llm_ok = bool(
        settings.llm.enabled and settings.execution.enable_critic and settings.execution.allow_model_to_choose_actions
    )
    planner: AgentDecision | None = None
    critic: CriticReview | None = None
    fail_reason: str | None = None
    transitions: list = []
    actions_run: list[str] = []
    control_decision: str | None = None
    grounding_status: str | None = None
    planner_control_failure: str | None = None
    offered: set[str] = {row["action_id"] for row in ranked0}
    critic_failed = False

    if not llm_ok:
        fail_reason = (
            "LLM planner/critic is disabled; genome_skeptic_agentic_v3 fails closed instead of silent V5 fallback"
        )
    else:
        planner_cfg = settings.llm.for_role("planner")
        critic_cfg = settings.llm.for_role("critic")
        planner_client = OllamaJSONClient(planner_cfg)
        critic_client = OllamaJSONClient(critic_cfg)
        planner_payload = _planner_payload(measurements, run)
        provenance["prompt_hash"] = _sha256_obj({"system": AGENTIC_REASONER_SYSTEM, "payload": planner_payload})
        provenance["planner_estimated_tokens"] = estimated_tokens(planner_payload)
        provenance["model_name"] = planner_cfg.model
        try:
            state.call_graph.append("OllamaJSONClient.ask_json:AgentDecision")
            provenance["planner_invoked"] = True
            compact_planner = planner_client.ask_json(AGENTIC_REASONER_SYSTEM, planner_payload, PlannerDecision)
            planner = planner_decision_to_agent(compact_planner)
            _, v1_verb = _alias_v1_requested_actions(planner.requested_actions, planner.decision)
            if v1_verb:
                provenance["v1_requested_action_aliased"] = v1_verb
            planner, dropped = _recover_planner_fields(planner, state.known_ids(), state.evidence)
            first_recovered = planner
            provenance["planner_dropped_evidence_ids"] = list(dropped)
            defects = _planner_defects_v3(planner, offered, dropped, state.known_ids())
            provenance["planner_defects"] = list(defects)
            if defects:
                repair_payload = dict(planner_payload)
                repair_payload["previous_decision"] = compact_planner.model_dump()
                repair_payload["defects_to_fix"] = defects
                repair_payload["repair"] = (
                    "The previous JSON was rejected for the reasons listed in defects_to_fix. Return one JSON "
                    "object matching the schema. requested_action must be exactly one action_id from "
                    "available_actions or one control decision "
                    f"(use '{ABSTAIN_UNRESOLVED}' if no available action can change a relevant measurement). "
                    "evidence_ids, if supplied, must be copied verbatim from valid_evidence_ids; they may be empty."
                )
                state.call_graph.append("OllamaJSONClient.ask_json:AgentDecision_repair")
                repaired, repaired_dropped = _recover_planner_fields(
                    planner_decision_to_agent(
                        planner_client.ask_json(AGENTIC_REASONER_SYSTEM, repair_payload, PlannerDecision)
                    ),
                    state.known_ids(),
                    state.evidence,
                )
                provenance["planner_repair_dropped_evidence_ids"] = list(repaired_dropped)
                merged = repaired.model_dump()
                if not merged.get("requested_actions") and first_recovered.requested_actions:
                    merged["requested_actions"] = list(first_recovered.requested_actions)
                if not merged.get("evidence_ids") and first_recovered.evidence_ids:
                    merged["evidence_ids"] = list(first_recovered.evidence_ids)
                planner = AgentDecision.model_validate(merged)
                provenance["planner_defects_after_repair"] = _planner_defects_v3(
                    planner, offered, provenance["planner_repair_dropped_evidence_ids"], state.known_ids()
                )
            provenance["planner_returned_empty_plan"] = not (planner.requested_actions or [])
            provenance["response_hash"] = _sha256_text(planner.model_dump_json())
            provenance["cited_evidence_ids"] = list(planner.evidence_ids or [])
            (out_dir / "planner_decision.json").write_text(planner.model_dump_json(indent=2), encoding="utf-8")

            choice, grounding_status, planner_control_failure, unrecoverable = _validate_planner_v3(
                planner, state.known_ids(), offered
            )
            provenance["planner_grounding_status"] = grounding_status
            provenance["planner_control_failure"] = planner_control_failure
            if unrecoverable:
                fail_reason = unrecoverable
            elif planner_control_failure and choice is None:
                state.add_evidence(
                    "target_gene",
                    "planner_control_failure",
                    f"Planner control failure recorded: {planner_control_failure}",
                    {
                        "grounding_status": grounding_status,
                        "failure": planner_control_failure,
                        "requested_actions": list(planner.requested_actions or []),
                    },
                )
            elif choice in CONTROL_DECISIONS:
                control_decision = choice
                provenance["control_decision"] = choice
                remaining = [row["action_id"] for row in ranked0]
                provenance["abstention_justified"] = not remaining if choice == ABSTAIN_UNRESOLVED else None
                provenance["actions_still_available_at_abstention"] = remaining
                state.add_evidence(
                    "target_gene",
                    "control_decision",
                    f"Planner control decision: {choice}",
                    {
                        "decision_id": choice,
                        "meaning": CONTROL_DECISION_SEMANTICS[choice],
                        "inferred_from_empty_plan": provenance["planner_returned_empty_plan"],
                        "actions_still_available": remaining,
                        "grounding_status": grounding_status,
                        "rationale": planner.rationale,
                    },
                )
            else:
                provenance["selected_action"] = choice
                spec = BY_ID[choice]
                provenance["planner_chose_unavailable_action"] = not spec.is_available(run.capabilities)
                provenance["planner_chose_inert_action"] = spec.inert_because(
                    run.baseline_work, measurements, edge_bp=edge_bp
                ) or None
                from_state, to_state = _next_states(transitions)
                transitions.append(
                    run_action_and_update(
                        run, measurements, choice, requested_by="planner", from_state=from_state, to_state=to_state
                    )
                )
                actions_run.append(choice)
                run.capabilities = capabilities_for(state, measurements)

            # Critic must run after abstention, missing evidence IDs, or recoverable control failure.
            if fail_reason is None and planner is not None:
                critic_payload = _critic_payload(
                    planner,
                    run,
                    measurements,
                    transitions[0] if transitions else None,
                    actions_run,
                    grounding_status,
                    planner_control_failure,
                )
                provenance["diagnostic_needs_after_action1"] = critic_payload.get("diagnostic_needs")
                provenance["remaining_actions_for_critic"] = [
                    row["action_id"] for row in (critic_payload.get("remaining_actions") or [])
                ]
                provenance["critic_prompt_hash"] = _sha256_obj({"system": AGENTIC_CRITIC_SYSTEM, "payload": critic_payload})
                provenance["critic_estimated_tokens"] = estimated_tokens(critic_payload)
                try:
                    state.call_graph.append("OllamaJSONClient.ask_json:CriticReview")
                    provenance["critic_invoked"] = True
                    critic = critic_decision_to_review(
                        critic_client.ask_json(AGENTIC_CRITIC_SYSTEM, critic_payload, CriticDecision)
                    )
                    critic, critic_dropped = _recover_critic_fields(critic, state.known_ids())
                    provenance["critic_dropped_evidence_ids"] = list(critic_dropped)
                    critic_defects = _critic_defects(critic, state.known_ids(), critic_dropped)
                    provenance["critic_defects"] = list(critic_defects)
                    if critic_defects:
                        repair_c = dict(critic_payload)
                        repair_c["defects_to_fix"] = critic_defects
                        repair_c["repair"] = (
                            "The previous JSON was rejected for the reasons listed in defects_to_fix. "
                            "Cite at least one evidence ID copied verbatim from valid_evidence_ids."
                        )
                        state.call_graph.append("OllamaJSONClient.ask_json:CriticReview_repair")
                        critic, critic_dropped = _recover_critic_fields(
                            critic_decision_to_review(
                                critic_client.ask_json(AGENTIC_CRITIC_SYSTEM, repair_c, CriticDecision)
                            ),
                            state.known_ids(),
                        )
                        provenance["critic_defects_after_repair"] = _critic_defects(
                            critic, state.known_ids(), critic_dropped
                        )
                    provenance["critic_response_hash"] = _sha256_text(critic.model_dump_json())
                    provenance["critic_cited_evidence_ids"] = list(critic.evidence_ids or [])
                    (out_dir / "critic_review.json").write_text(critic.model_dump_json(indent=2), encoding="utf-8")
                    provenance["critic_challenge"] = {
                        "verdict": critic.verdict,
                        "rationale": critic.rationale,
                        "failure_modes": list(critic.failure_modes or []),
                        "disconfirming_tests": list(critic.disconfirming_tests or []),
                    }
                    critic, err = _validate_critic(critic, state.known_ids())
                    if err:
                        critic_failed = True
                        provenance["critic_unusable"] = err
                        critic = None
                        if grounding_status == GROUNDING_MISSING or planner_control_failure:
                            fail_reason = (
                                f"critic failed after planner control/grounding failure "
                                f"(grounding={grounding_status}, planner={planner_control_failure}, critic={err})"
                            )
                    else:
                        remaining_ids = list(provenance.get("remaining_actions_for_critic") or [])
                        second, reason = select_critic_action_v3(critic, remaining_ids, actions_run)
                        provenance["critic_second_action"] = second
                        provenance["critic_second_action_reason"] = reason
                        if second:
                            from_state, to_state = _next_states(transitions)
                            transitions.append(
                                run_action_and_update(
                                    run,
                                    measurements,
                                    second,
                                    requested_by="critic",
                                    from_state=from_state,
                                    to_state=to_state,
                                )
                            )
                            actions_run.append(second)
                except Exception as exc:
                    critic_failed = True
                    if grounding_status == GROUNDING_MISSING or planner_control_failure:
                        fail_reason = f"critic call failed after planner control/grounding failure: {exc}"
                    else:
                        fail_reason = f"critic call failed: {exc}"
        except Exception as exc:
            fail_reason = f"planner call failed: {exc}"

    m_final = measurement_fingerprint(measurements)
    provenance["measurement_state"]["m_final"] = m_final
    provenance["measurements_changed_before_validation"] = m0["hash"] != m_final["hash"]
    provenance["measurement_trajectory"] = [t.as_dict() for t in transitions]
    provenance["actions_executed"] = [t.result.as_dict() for t in transitions]
    provenance["informative_action_count"] = sum(1 for t in transitions if t.result.status.value == "INFORMATIVE")
    provenance["action_status_counts"] = {}
    for t in transitions:
        key = t.result.status.value
        provenance["action_status_counts"][key] = provenance["action_status_counts"].get(key, 0) + 1
    provenance["diagnostic_needs_m_final"] = need_payload(
        derive_diagnostic_needs(measurements, run.capabilities, settings=settings, edge_bp=edge_bp)
    )

    stats = _call_stats()
    provenance.update(
        {k: stats[k] for k in ("model_call_count", "planner_model_call_count", "critic_model_call_count", "repair_count")}
    )
    provenance.update(_llm_runtime_breakdown(stats.get("call_log") or []))
    notes = (
        "genome_skeptic_agentic_v3: LLM did not supply identity, coverage, E-values, domain hits, "
        "catalytic residues, orthologues, gene order, or reciprocal hits. "
        f"planner_invoked={provenance['planner_invoked']} critic_invoked={provenance['critic_invoked']} "
        f"model={provenance['model_name']} prompt_hash={provenance['prompt_hash']} "
        f"response_hash={provenance['response_hash']} selected_action={provenance['selected_action']} "
        f"control_decision={provenance['control_decision']} "
        f"planner_grounding_status={provenance['planner_grounding_status']} "
        f"critic_second_action={provenance['critic_second_action']} "
        f"measurements_changed_before_validation={provenance['measurements_changed_before_validation']} "
        f"measurement_hash_m0={m0['hash']} measurement_hash_final={m_final['hash']} "
        f"critic_prompt_hash={provenance['critic_prompt_hash']} critic_response_hash={provenance['critic_response_hash']}"
    )

    if fail_reason:
        provenance["agent_failure"] = fail_reason
        claims = [_unresolved_failure(measurements, fail_reason, [e.id for e in state.evidence], notes)]
    else:
        state.call_graph.append("build_target_gene_claim")
        consumed = measurement_fingerprint(measurements)
        provenance["validator_consumed_measurement_hash"] = consumed["hash"]
        provenance["validator_consumed_m0"] = consumed["hash"] == m0["hash"]
        claim, anoms, _tests = build_target_gene_claim(measurements, settings, [e.id for e in state.evidence])
        provenance["final_validator_ran"] = True
        state.anomalies.extend(anoms)
        extras = [h for h in (planner.alternative_explanations or []) if h in HYPOTHESIS_IDS] if planner else []
        if extras:
            claim.alternative_explanations = list(dict.fromkeys(list(claim.alternative_explanations or []) + extras))
        if critic and critic.verdict == "challenge":
            claim.rationale += (
                " Critic verdict=challenge was recorded in agentic provenance; the deterministic validator remains the authority."
            )
        if control_decision == ABSTAIN_UNRESOLVED:
            claim.rationale += (
                " The planner abstained: no registered action could change a measurement bearing on the open alternatives. "
                "The abstention is recorded in provenance and did not alter the deterministic claim."
            )
        if grounding_status == GROUNDING_MISSING:
            claim.rationale += (
                " Planner claim-grounding status was MISSING; the investigation action was still permitted. "
                "The deterministic validator assigned the claim."
            )
        claim.provenance.notes = (claim.provenance.notes or "") + " " + notes
        claim.provenance.evidence_ledger_ids = list(
            dict.fromkeys(list(claim.provenance.evidence_ledger_ids or []) + [e.id for e in state.evidence])
        )
        claims = [claim]
        provenance["preferred_hypothesis"] = (planner.alternative_explanations or [None])[0] if planner else None

    provenance["llm_measurement_entered_claim"] = _llm_measurement_entered_claim(
        claims[0], planner, critic, state.evidence
    )
    provenance["final_claim_state"] = {
        "claim_id": claims[0].claim_id,
        "claim_type": claims[0].claim_type.value,
        "status": claims[0].status.value,
        "confidence": claims[0].confidence,
        "homology_support": claims[0].homology_support,
        "architecture_state": claims[0].architecture_state,
        "supporting_evidence_ids": list(claims[0].supporting_evidence_ids),
        "alternative_explanations": list(claims[0].alternative_explanations or []),
    }
    provenance["call_graph"] = list(state.call_graph)
    provenance["evidence_ids"] = [e.id for e in state.evidence]
    provenance["seconds"] = round(time.perf_counter() - t0, 3)

    final_loci = measurements.locus_evidence or loci
    (out_dir / "claims.json").write_text(json.dumps([c.model_dump(mode="json") for c in claims], indent=2), encoding="utf-8")
    (out_dir / "locus_evidence.json").write_text(
        json.dumps([le.model_dump() for le in final_loci], indent=2), encoding="utf-8"
    )
    (out_dir / "evidence.json").write_text(json.dumps([e.model_dump() for e in state.evidence], indent=2), encoding="utf-8")
    (out_dir / "agentic_provenance.json").write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")
    (out_dir / "call_log.json").write_text(json.dumps(stats["call_log"], indent=2, default=str), encoding="utf-8")
    if planner is not None:
        (out_dir / "planner_decision.json").write_text(planner.model_dump_json(indent=2), encoding="utf-8")
    if critic is not None:
        (out_dir / "critic_review.json").write_text(critic.model_dump_json(indent=2), encoding="utf-8")
    return claims, final_loci, provenance
