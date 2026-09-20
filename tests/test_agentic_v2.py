"""Agentic V2 action contract: actions must be able to change what the validator sees."""
from pathlib import Path

import pytest

from genome_skeptic.agents.action_catalog import (
    ACTION_IDS,
    BY_ID,
    actions_discriminating,
    catalog_payload,
    executable_action_payload,
    state_changing_action_ids,
)
from genome_skeptic.agents.action_contract import (
    ABSTAIN_UNRESOLVED,
    FINALIZE_WITH_CURRENT_EVIDENCE,
    ActionResult,
    ActionStatus,
    MeasurementPatch,
    PatchRejected,
    apply_action_result,
    hit_key,
    measurement_fingerprint,
    unavailable,
)
from genome_skeptic.agents.assembly_loop_v2 import (
    _HANDLERS,
    _act_contamination,
    _act_inspect_edges,
    _alias_v1_requested_actions,
    _planner_defects,
    _recover_planner_fields,
    _sanitize_evidence_ids,
    _V2Run,
    _validate_planner,
    planner_decision_to_agent,
    select_critic_action,
)
from genome_skeptic.config import Settings
from genome_skeptic.models import AgentDecision, CriticDecision, CriticReview, GeneSearchHit, PlannerDecision, TargetProfile
from genome_skeptic.validators.falsification import TargetMeasurements

GENE = "ATG" + ("CGTAGC") * 20 + "TAA"


def _profile(**kwargs) -> TargetProfile:
    data = {"query_id": "rpoB", "sequence": GENE}
    data.update(kwargs)
    return TargetProfile.model_validate(data)


def _hit(**kwargs) -> GeneSearchHit:
    data = {
        "query_id": "rpoB",
        "contig_id": "c1",
        "search_kind": "nucleotide",
        "qstart": 0,
        "qend": len(GENE),
        "tstart": 500,
        "tend": 500 + len(GENE),
        "strand": "+",
        "identity": 0.95,
        "query_coverage": 0.98,
        "alignment_length": len(GENE),
        "query_length": len(GENE),
        "contig_length": 2000,
    }
    data.update(kwargs)
    return GeneSearchHit.model_validate(data)


def _measurements(hits=None, **kwargs) -> TargetMeasurements:
    profile = _profile()
    return TargetMeasurements(query_id=profile.query_id, profile=profile, hits=list(hits or []), **kwargs)


def _matching_edge_hit(**kwargs) -> GeneSearchHit:
    """A hit whose stored edge flags already agree with contig_length."""
    hit = _hit(**kwargs)
    lo, hi = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
    contig_len = hit.contig_length
    edge_distance = min(max(lo, 0), max(contig_len - hi, 0))
    near = edge_distance <= 300
    return _hit(
        **kwargs,
        near_contig_edge=near,
        possible_edge_truncation=bool(near and hit.query_coverage < 0.95),
        edge_distance_bp=edge_distance,
    )


def _fit_schema(schema, data: dict):
    payload = dict(data)
    if "disconfirming_tests" in payload and "requested_action" not in payload:
        tests = payload.get("disconfirming_tests") or []
        payload["requested_action"] = tests[0] if tests else None
    if "failure_modes" in payload and "failure_mode" not in payload:
        modes = payload.get("failure_modes") or []
        payload["failure_mode"] = modes[0] if modes else None
    if "requested_actions" in payload and "requested_action" not in payload:
        acts = payload.get("requested_actions") or []
        payload["requested_action"] = acts[0] if acts else None
    alts = payload.get("alternative_explanations") or []
    if alts:
        payload.setdefault("leading_hypothesis", alts[0])
        if len(alts) > 1:
            payload.setdefault("alternative_hypothesis", alts[1])
    dec = payload.get("decision")
    action = payload.get("requested_action")
    if dec in {"continue", "rerun"}:
        payload["decision"] = "investigate"
    elif dec in {"ask_human", "stop"}:
        payload["decision"] = "abstain"
    if action == FINALIZE_WITH_CURRENT_EVIDENCE:
        payload["decision"] = "finalize"
    elif action == ABSTAIN_UNRESOLVED and payload.get("decision") not in {"investigate", "finalize", "abstain"}:
        payload["decision"] = "abstain"
    if payload.get("decision") not in {"investigate", "finalize", "abstain", "accept", "challenge", None}:
        payload["decision"] = "investigate"
    fields = getattr(schema, "model_fields", payload)
    return schema.model_validate({k: v for k, v in payload.items() if k in fields})


def _informative(action_id: str, patches) -> ActionResult:
    return ActionResult(action_id=action_id, status=ActionStatus.informative, summary="t", patches=list(patches))


# --- patches are the only route into TargetMeasurements ---------------------


def test_new_hits_reach_measurements_and_change_the_fingerprint():
    m = _measurements([_hit()])
    before = measurement_fingerprint(m)
    result = apply_action_result(
        m,
        _informative(
            "search_target_proteins_mmseqs",
            [MeasurementPatch(field="hits", value=[_hit(tstart=9000, tend=9300, search_kind="translated")], origin="orf_protein_similarity_search")],
        ),
    )
    assert result.status is ActionStatus.informative
    assert result.n_new_measurements == 1
    assert len(m.hits) == 2
    assert measurement_fingerprint(m)["hash"] != before["hash"]


def test_repeating_a_known_measurement_is_no_new_information():
    hit = _hit()
    m = _measurements([hit])
    before = measurement_fingerprint(m)
    result = apply_action_result(
        m,
        _informative("search_target_genes_nucleotide", [MeasurementPatch(field="hits", value=[_hit()], origin="internal_gene_search")]),
    )
    assert result.status is ActionStatus.no_new_information
    assert result.n_new_measurements == 0
    assert "already present" in result.status_reason
    assert measurement_fingerprint(m)["hash"] == before["hash"]


def test_executor_cannot_award_itself_informative():
    m = _measurements([_hit()])
    result = apply_action_result(m, _informative("inspect_paralogue_copies", []))
    assert result.status is ActionStatus.no_new_information


def test_patch_from_an_unregistered_origin_is_rejected():
    m = _measurements([_hit()])
    with pytest.raises(PatchRejected, match="unregistered origin"):
        apply_action_result(
            m,
            _informative("search_target_genes_nucleotide", [MeasurementPatch(field="hits", value=[_hit(tstart=1)], origin="qwen_planner")]),
        )


def test_patch_to_an_unknown_field_is_rejected():
    m = _measurements([_hit()])
    with pytest.raises(PatchRejected, match="not a patchable measurement field"):
        apply_action_result(m, _informative("x", [MeasurementPatch(field="confidence", value=0.99, origin="internal_gene_search")]))


def test_hits_patch_must_carry_deterministic_hit_objects():
    m = _measurements([_hit()])
    with pytest.raises(PatchRejected, match="GeneSearchHit"):
        apply_action_result(
            m,
            _informative("search_target_genes_nucleotide", [MeasurementPatch(field="hits", value=[{"identity": 0.99}], origin="internal_gene_search")]),
        )


def test_unavailable_action_may_not_smuggle_a_patch():
    m = _measurements([_hit()])
    bad = unavailable("inspect_local_coverage_for_target", "no depth")
    bad.patches.append(MeasurementPatch(field="coverage_by_hit", value={"k": {"relative_depth": 1.0}}, origin="samtools_depth"))
    with pytest.raises(PatchRejected, match="still offered measurement patches"):
        apply_action_result(m, bad)


def test_unavailable_action_leaves_measurements_untouched():
    m = _measurements([_hit()])
    before = measurement_fingerprint(m)
    result = apply_action_result(m, unavailable("inspect_local_coverage_for_target", "no depth table was supplied"))
    assert result.status is ActionStatus.unavailable
    assert measurement_fingerprint(m)["hash"] == before["hash"]


def test_merge_dict_counts_only_genuinely_new_keys():
    m = _measurements([_hit()], coverage_by_hit={"a": {"relative_depth": 1.0}})
    result = apply_action_result(
        m,
        _informative(
            "inspect_local_coverage_for_target",
            [MeasurementPatch(field="coverage_by_hit", value={"a": {"relative_depth": 1.0}, "b": {"relative_depth": 0.2}}, origin="samtools_depth")],
        ),
    )
    assert result.applied[0].n_new == 1
    assert result.applied[0].detail["new_keys"] == ["b"]


# --- the audited failure mode: edge inspection that repeats known flags -----


def _run_with_contig(seq_len: int = 2000) -> _V2Run:
    class _State:
        settings = Settings()
        contig_seqs = {"c1": "A" * seq_len}
        call_graph: list = []

    return _V2Run(state=_State())


def test_contig_edge_inspection_repeating_known_flags_is_no_new_information():
    run = _run_with_contig()
    edge_bp = run.state.settings.thresholds.contig_edge_proximity_bp
    hit = _hit(tstart=500, tend=800, near_contig_edge=False, possible_edge_truncation=False, edge_distance_bp=500)
    assert hit.edge_distance_bp > edge_bp
    m = _measurements([hit])
    result = apply_action_result(m, _act_inspect_edges(run, m, "inspect_contig_edges_for_target"))
    assert result.status is ActionStatus.no_new_information


def test_contig_edge_inspection_that_corrects_a_stale_flag_is_informative():
    run = _run_with_contig()
    m = _measurements([_hit(tstart=5, tend=300, query_coverage=0.4, near_contig_edge=False, edge_distance_bp=999)])
    result = apply_action_result(m, _act_inspect_edges(run, m, "inspect_contig_edges_for_target"))
    assert result.status is ActionStatus.informative
    assert m.hits[0].near_contig_edge is True
    assert m.hits[0].edge_distance_bp == 5


def test_composition_measurement_unlocks_the_contamination_test_then_goes_quiet():
    run = _run_with_contig()
    run.state.contig_seqs = {"c1": "GC" * 1000, "c2": "AT" * 1000}
    m = _measurements([_hit()])
    assert not m.contig_gc and m.genome_gc is None
    first = apply_action_result(m, _act_contamination(run, m, "inspect_hit_contig_contamination"))
    assert first.status is ActionStatus.informative
    assert m.contig_gc["c1"] == 1.0
    assert m.genome_gc == pytest.approx(0.5)
    second = apply_action_result(m, _act_contamination(run, m, "inspect_hit_contig_contamination"))
    assert second.status is ActionStatus.no_new_information


# --- action metadata --------------------------------------------------------


def test_every_registered_action_has_a_deterministic_executor():
    assert set(ACTION_IDS) == set(_HANDLERS)


def test_catalog_marks_actions_inert_when_their_inputs_are_missing():
    caps = {"assembly": True, "targets": True, "hits": True}
    payload = {row["action_id"]: row for row in catalog_payload(caps)}
    assert payload["inspect_local_coverage_for_target"]["available"] is False
    assert "depth_tsv" in payload["inspect_local_coverage_for_target"]["unavailable_because_missing"]
    assert payload["search_target_genes_nucleotide"]["available"] is True
    assert "paralogue" in payload["reciprocal_best_hit_search"]["discriminates_between"]


def test_every_action_declares_what_it_discriminates():
    for spec in BY_ID.values():
        assert spec.discriminates, spec.action_id
        assert spec.resolves and spec.informative_when


# --- inertness is decided by the catalog, not left to the model -------------

_BASELINE = frozenset({"nucleotide_gene_search", "translated_gene_search"})


def test_an_action_that_updates_no_field_can_never_change_the_state():
    """inspect_paralogue_copies only re-reads hits, so it is inert by construction."""
    spec = BY_ID["inspect_paralogue_copies"]
    assert spec.updates_measurement_fields == ()
    assert spec.is_inert(frozenset()) is True
    assert spec.can_change_state_now({"hits": True}, frozenset()) is False


def test_repeating_the_baseline_search_is_inert_once_the_baseline_has_run():
    spec = BY_ID["search_target_genes_nucleotide"]
    caps = {"assembly": True, "targets": True}
    assert spec.can_change_state_now(caps, frozenset()) is True
    assert spec.can_change_state_now(caps, _BASELINE) is False
    assert "already ran the same nucleotide search" in spec.inert_because(_BASELINE)


def test_an_inert_action_is_still_reported_as_input_available():
    """Inert and unavailable are different failures and must stay distinguishable."""
    caps = {"assembly": True, "targets": True, "hits": True}
    payload = {row["action_id"]: row for row in catalog_payload(caps, _BASELINE)}
    row = payload["search_target_genes_nucleotide"]
    assert row["available"] is True
    assert row["unavailable_because_missing"] == []
    assert row["inert_now"] is True
    assert row["can_change_a_measurement_now"] is False


def test_state_changing_list_excludes_both_unavailable_and_inert_actions():
    caps = {"assembly": True, "targets": True, "hits": True}
    ids = state_changing_action_ids(caps, _BASELINE)
    assert "search_target_genes_nucleotide" not in ids  # inert: baseline already ran it
    assert "inspect_paralogue_copies" not in ids  # inert: updates no field
    assert "inspect_local_coverage_for_target" not in ids  # unavailable: no depth file
    assert "inspect_hit_contig_contamination" in ids


def test_edge_flags_already_in_state_are_not_shown_to_the_planner():
    """The LLM must not see inspect_contig_edges when m0 already encodes the flags."""
    caps = {"assembly": True, "targets": True, "hits": True}
    matching = _matching_edge_hit()
    m = _measurements([matching], contig_sequences={"c1": "A" * matching.contig_length})
    ids = state_changing_action_ids(caps, _BASELINE, m)
    shown = {row["action_id"] for row in executable_action_payload(caps, _BASELINE, m)}
    assert "inspect_contig_edges_for_target" not in ids
    assert "inspect_contig_edges_for_target" not in shown
    reason = BY_ID["inspect_contig_edges_for_target"].inert_because(_BASELINE, m)
    assert "edge flags already present" in reason


def test_stale_edge_flags_keep_edge_inspection_visible():
    caps = {"assembly": True, "targets": True, "hits": True}
    stale = _hit(tstart=5, tend=300, query_coverage=0.4, near_contig_edge=False, edge_distance_bp=999)
    m = _measurements([stale], contig_sequences={"c1": "A" * stale.contig_length})
    ids = state_changing_action_ids(caps, _BASELINE, m)
    assert "inspect_contig_edges_for_target" in ids


def test_composition_already_measured_is_not_shown_to_the_planner():
    caps = {"assembly": True, "targets": True, "hits": True}
    hit = _hit()
    m = _measurements([hit], contig_gc={"c1": 0.5}, genome_gc=0.5)
    ids = state_changing_action_ids(caps, _BASELINE, m)
    assert "inspect_hit_contig_contamination" not in ids
    assert BY_ID["inspect_hit_contig_contamination"].can_change_state_now(caps, _BASELINE) is True


def test_compact_critic_schema_asks_for_one_action_not_lists():
    schema = CriticDecision.model_json_schema()
    props = schema.get("properties") or {}
    assert "verdict" in props
    assert "requested_action" in props
    assert "failure_mode" in props
    assert "disconfirming_tests" not in props
    assert "failure_modes" not in props


def test_compact_planner_schema_asks_for_one_action_not_lists():
    schema = PlannerDecision.model_json_schema()
    props = schema.get("properties") or {}
    assert "decision" in props
    assert "requested_action" in props
    assert "leading_hypothesis" in props
    assert "alternative_hypothesis" in props
    assert "requested_actions" not in props
    assert "concerns" not in props
    assert "alternative_explanations" not in props


def test_compact_planner_decision_maps_onto_agent_decision():
    mapped = planner_decision_to_agent(
        PlannerDecision(
            decision="investigate",
            leading_hypothesis="divergent_orthologue",
            alternative_hypothesis="true_absence",
            evidence_ids=["E001", "E003"],
            requested_action="search_target_proteins_mmseqs",
            confidence=0.63,
            rationale="Low coverage leaves a divergent full-length protein-level orthologue unresolved.",
        )
    )
    assert mapped.decision == "continue"
    assert mapped.requested_actions == ["search_target_proteins_mmseqs"]
    assert mapped.alternative_explanations == ["divergent_orthologue", "true_absence"]
    assert mapped.evidence_ids == ["E001", "E003"]
    assert mapped.confidence == 0.63


def test_discriminating_actions_exclude_inert_ones():
    caps = {"assembly": True, "targets": True, "hits": True}
    before = {spec.action_id for spec in actions_discriminating({"true_presence"}, caps, frozenset())}
    after = {spec.action_id for spec in actions_discriminating({"true_presence"}, caps, _BASELINE)}
    assert "search_target_genes_nucleotide" in before
    assert "search_target_genes_nucleotide" not in after


# --- planner control decisions ---------------------------------------------


def _decision(**kwargs) -> AgentDecision:
    data = {"decision": "continue", "rationale": "r", "evidence_ids": ["E001"], "requested_actions": []}
    data.update(kwargs)
    return AgentDecision.model_validate(data)


def test_empty_plan_becomes_an_abstention_not_an_execution_failure():
    choice, err = _validate_planner(_decision(requested_actions=[]), {"E001"})
    assert err is None
    assert choice == ABSTAIN_UNRESOLVED


def test_control_decisions_are_accepted_choices():
    choice, err = _validate_planner(_decision(requested_actions=[FINALIZE_WITH_CURRENT_EVIDENCE]), {"E001"})
    assert (choice, err) == (FINALIZE_WITH_CURRENT_EVIDENCE, None)


def test_unregistered_action_still_fails_closed():
    choice, err = _validate_planner(_decision(requested_actions=["rewrite_the_claim"]), {"E001"})
    assert choice is None and "unregistered" in err


def test_unknown_evidence_id_still_fails_closed():
    choice, err = _validate_planner(_decision(evidence_ids=["E999"]), {"E001"})
    assert choice is None and "unknown evidence" in err


# --- critic-triggered second action ----------------------------------------


_CAPS = {
    "assembly": True,
    "targets": True,
    "hits": True,
    "query_protein": True,
    "similarity_tools": True,
    "references": True,
}


def _critic(**kwargs) -> CriticReview:
    data = {"verdict": "challenge", "rationale": "r", "evidence_ids": ["E001"]}
    data.update(kwargs)
    return CriticReview.model_validate(data)


def test_accepting_critic_triggers_no_second_action():
    action, reason = select_critic_action(_critic(verdict="accept"), _CAPS, [])
    assert action is None and "accepted" in reason


def test_critic_naming_an_available_action_triggers_it():
    action, _ = select_critic_action(_critic(disconfirming_tests=["reciprocal_best_hit_search"]), _CAPS, [])
    assert action == "reciprocal_best_hit_search"


def test_critic_naming_a_hypothesis_selects_a_discriminating_action():
    action, reason = select_critic_action(_critic(failure_modes=["this may be a paralogue"]), _CAPS, [])
    assert action in {spec.action_id for spec in actions_discriminating({"paralogue"}, _CAPS)}
    assert "paralogue" in reason


def test_vague_challenge_earns_no_second_measurement():
    action, reason = select_critic_action(_critic(rationale="I am not convinced"), _CAPS, [])
    assert action is None and "concrete unresolved alternative" in reason


def test_an_action_already_run_is_not_repeated():
    action, _ = select_critic_action(
        _critic(disconfirming_tests=["reciprocal_best_hit_search"]),
        _CAPS,
        ["reciprocal_best_hit_search"],
    )
    assert action != "reciprocal_best_hit_search"


def test_critic_cannot_request_an_unavailable_action():
    action, _ = select_critic_action(
        _critic(disconfirming_tests=["inspect_local_coverage_for_target"], failure_modes=["insufficient_data"]),
        {"assembly": True, "targets": True, "hits": True},
        [],
    )
    assert action != "inspect_local_coverage_for_target"


def test_critic_cannot_answer_a_challenge_with_a_baseline_repeat():
    """The defect seen on dev_01/rpoB: the critic named the baseline search itself.

    Its inputs exist, so the availability check passed, and it was executed for a
    guaranteed NO_NEW_INFORMATION. Naming it must now be refused.
    """
    action, _ = select_critic_action(
        _critic(disconfirming_tests=["search_target_genes_nucleotide"], failure_modes=["true_presence"]),
        _CAPS,
        [],
        _BASELINE,
    )
    assert action != "search_target_genes_nucleotide"


def test_critic_cannot_answer_a_challenge_with_already_represented_edge_flags():
    matching = _matching_edge_hit()
    m = _measurements([matching], contig_sequences={"c1": "A" * matching.contig_length})
    action, _ = select_critic_action(
        _critic(disconfirming_tests=["inspect_contig_edges_for_target"], failure_modes=["divergent_orthologue"]),
        _CAPS,
        [],
        _BASELINE,
        m,
    )
    assert action != "inspect_contig_edges_for_target"
    assert action is not None


# --- measurement transitions reach the validator ---------------------------


def test_added_hits_change_the_claim_the_validator_produces():
    from genome_skeptic.validators.falsification import build_target_gene_claim

    settings = Settings()
    weak = _hit(identity=0.40, query_coverage=0.08, alignment_length=20)
    m = _measurements([weak], tools_run=["internal_gene_search"])
    baseline, _a, _t = build_target_gene_claim(m, settings, ["E001"])

    strong = _hit(contig_id="c1", tstart=9000, tend=9000 + len(GENE), search_kind="translated", identity=0.96, query_coverage=0.97, tool="mmseqs")
    apply_action_result(m, _informative("search_target_proteins_mmseqs", [MeasurementPatch(field="hits", value=[strong], origin="orf_protein_similarity_search")]))
    updated, _a2, _t2 = build_target_gene_claim(m, settings, ["E001"])

    assert hit_key(strong) in {hit_key(h) for h in m.hits}
    assert (updated.claim_type, updated.homology_support) != (baseline.claim_type, baseline.homology_support)


# --- end-to-end loop with a stubbed planner/critic --------------------------


def _write_case(tmp_path: Path) -> tuple[Path, Path]:
    from genome_skeptic.eval.synthetic import DNAA, RPOB, RPOC, _fa, _operon

    seq, _genes = _operon([("dnaA", DNAA), ("rpoB", RPOB), ("rpoC", RPOC)])
    assembly = tmp_path / "assembly.fa"
    assembly.write_text(_fa({"c1": seq}))
    targets = tmp_path / "targets.fa"
    targets.write_text(f">rpoB\n{RPOB}\n")
    return assembly, targets


def _stub_llm(monkeypatch, *, planner_actions, critic_review):
    """Replace the Ollama client so the loop runs without a model server."""
    calls: list[str] = []

    class _Stub:
        def __init__(self, cfg):
            self.cfg = cfg

        def ask_json(self, system, payload, schema):
            calls.append(schema.__name__)
            if schema.__name__ in {"AgentDecision", "PlannerDecision"}:
                return _fit_schema(
                    schema,
                    {
                        "decision": "continue",
                        "rationale": "deterministic stub decision",
                        "evidence_ids": [payload["evidence"][0]["id"]],
                        "alternative_explanations": ["true_presence", "paralogue"],
                        "requested_actions": list(planner_actions),
                    },
                )
            return _fit_schema(schema, {**critic_review, "evidence_ids": [payload["evidence"][0]["id"]]})

    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v2.OllamaJSONClient", _Stub)
    return calls


def _run(tmp_path, monkeypatch, *, planner_actions, critic_review=None):
    from genome_skeptic.agents.assembly_loop_v2 import run_skeptic_agentic_v2

    assembly, targets = _write_case(tmp_path)
    _stub_llm(monkeypatch, planner_actions=planner_actions, critic_review=critic_review or {"verdict": "accept", "rationale": "ok"})
    return run_skeptic_agentic_v2(assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"])


def test_loop_labels_an_inert_action_and_still_reaches_the_validator(tmp_path, monkeypatch):
    claims, _loci, prov = _run(tmp_path, monkeypatch, planner_actions=["inspect_paralogue_copies"])
    assert prov["final_validator_ran"] is True
    assert prov["agent_failure"] is None
    assert prov["actions_executed"][0]["status"] == ActionStatus.no_new_information.value
    assert prov["measurements_changed_before_validation"] is False
    assert prov["measurement_state"]["m0"]["hash"] == prov["measurement_state"]["m_final"]["hash"]
    assert claims[0].confidence > 0.0


def test_an_informative_action_changes_what_the_validator_sees(tmp_path, monkeypatch):
    claims, _loci, prov = _run(tmp_path, monkeypatch, planner_actions=["inspect_hit_contig_contamination"])
    assert prov["actions_executed"][0]["status"] == ActionStatus.informative.value
    assert prov["measurements_changed_before_validation"] is True
    assert prov["measurement_state"]["m0"]["hash"] != prov["measurement_state"]["m_final"]["hash"]
    assert "contig_gc" in prov["measurement_trajectory"][0]["updated_measurement_fields"]
    assert prov["final_validator_ran"] is True
    assert prov["llm_measurement_entered_claim"] is False
    assert claims


def test_measurement_update_is_recorded_as_its_own_evidence(tmp_path, monkeypatch):
    _claims, _loci, prov = _run(tmp_path, monkeypatch, planner_actions=["inspect_hit_contig_contamination"])
    update = prov["measurement_trajectory"][0]
    assert update["from"] == "m0" and update["to"] == "m1"
    assert len(update["evidence_ids"]) == 2  # the action reading and the state transition


def test_empty_plan_abstains_instead_of_crashing_the_run(tmp_path, monkeypatch):
    """The tuf failure mode: V1 turned an empty plan into an execution failure."""
    claims, _loci, prov = _run(tmp_path, monkeypatch, planner_actions=[])
    assert prov["agent_failure"] is None
    assert prov["planner_returned_empty_plan"] is True
    assert prov["control_decision"] == ABSTAIN_UNRESOLVED
    assert prov["final_validator_ran"] is True
    assert prov["abstention_justified"] in {True, False}
    assert claims[0].provenance.created_by == "deterministic_validator"
    assert "abstained" in claims[0].rationale


def test_finalize_control_decision_runs_no_action(tmp_path, monkeypatch):
    _claims, _loci, prov = _run(tmp_path, monkeypatch, planner_actions=[FINALIZE_WITH_CURRENT_EVIDENCE])
    assert prov["control_decision"] == FINALIZE_WITH_CURRENT_EVIDENCE
    assert prov["measurement_trajectory"] == []
    assert prov["final_validator_ran"] is True


def test_critic_challenge_triggers_exactly_one_second_action(tmp_path, monkeypatch):
    _claims, _loci, prov = _run(
        tmp_path,
        monkeypatch,
        planner_actions=["inspect_contig_edges_for_target"],
        critic_review={
            "verdict": "challenge",
            "rationale": "the hit may sit on a contaminant contig rather than the chromosome",
            "failure_modes": ["contamination"],
        },
    )
    assert prov["critic_second_action"] is not None
    assert len(prov["measurement_trajectory"]) == 2
    assert prov["measurement_trajectory"][1]["requested_by"] == "critic"
    assert prov["measurement_trajectory"][1]["from"] == "m1"


def test_a_challenge_whose_only_discriminating_action_is_inert_earns_no_measurement(tmp_path, monkeypatch):
    """Paralogy is discriminated here only by inspect_paralogue_copies.

    That action updates no measurement field, so it can never move the state.
    Spending the critic's single follow-up on it would guarantee
    NO_NEW_INFORMATION, so no second measurement is triggered at all.
    """
    _claims, _loci, prov = _run(
        tmp_path,
        monkeypatch,
        planner_actions=["inspect_contig_edges_for_target"],
        critic_review={
            "verdict": "challenge",
            "rationale": "the candidate may be a paralogue rather than the orthologue",
            "failure_modes": ["paralogue"],
        },
    )
    assert prov["critic_second_action"] is None
    assert "paralogue" in prov["critic_second_action_reason"]
    assert len(prov["measurement_trajectory"]) == 1
    assert prov["final_validator_ran"] is True


def test_critic_can_still_measure_after_the_planner_abstains(tmp_path, monkeypatch):
    _claims, _loci, prov = _run(
        tmp_path,
        monkeypatch,
        planner_actions=[ABSTAIN_UNRESOLVED],
        critic_review={
            "verdict": "challenge",
            "rationale": "contamination has not been excluded",
            "failure_modes": ["contamination"],
        },
    )
    assert prov["control_decision"] == ABSTAIN_UNRESOLVED
    assert prov["critic_second_action"] is not None
    assert len(prov["measurement_trajectory"]) == 1
    assert prov["measurement_trajectory"][0]["requested_by"] == "critic"
    assert prov["final_validator_ran"] is True


def test_at_most_one_action_follows_the_critic(tmp_path, monkeypatch):
    """Frozen V2 contract: critic follow-up is at most one action.

    Historical fixture used planner=inspect_hit_contig_contamination plus
    critic=assembly_fragmentation. On this synthetic assembly the edge flags
    are already represented and mapping/depth are absent, so every
    assembly_fragmentation discriminator is inert or unavailable and the
    critic correctly records zero follow-ups. The cap is exercised with a
    challenge that still has one state-changing discriminator.
    """
    _claims, _loci, prov = _run(
        tmp_path,
        monkeypatch,
        planner_actions=["inspect_contig_edges_for_target"],
        critic_review={
            "verdict": "challenge",
            "rationale": "the hit may sit on a contaminant contig rather than the chromosome",
            "failure_modes": ["contamination"],
        },
    )
    critic_steps = [step for step in prov["measurement_trajectory"] if step["requested_by"] == "critic"]
    assert len(prov["measurement_trajectory"]) <= 2
    assert len(critic_steps) == 1
    assert prov["critic_second_action"] is not None


# --- citation discipline: wrong IDs are repairable, not fatal ---------------


def test_sanitize_splits_real_ids_from_non_ids():
    kept, dropped = _sanitize_evidence_ids(["E001", "hits", "E002", "hits"], {"E001", "E002"})
    assert kept == ["E001", "E002"]
    assert dropped == ["hits"]


def test_recovery_drops_a_field_name_cited_as_an_evidence_id():
    decision = AgentDecision.model_validate(
        {"decision": "ask_human", "rationale": "r", "evidence_ids": ["hits"], "requested_actions": [ABSTAIN_UNRESOLVED]}
    )
    recovered, dropped = _recover_planner_fields(decision, {"E001", "E002"}, [])
    assert dropped == ["hits"]
    assert recovered.evidence_ids == []
    assert recovered.requested_actions == [ABSTAIN_UNRESOLVED]


def test_defects_name_the_bad_token_and_the_valid_ids():
    decision = AgentDecision.model_validate(
        {"decision": "continue", "rationale": "r", "evidence_ids": [], "requested_actions": [ABSTAIN_UNRESOLVED]}
    )
    defects = _planner_defects(decision, {"E001", "E002"}, ["hits"])
    assert any("hits" in d and "E001" in d for d in defects)


def test_a_well_formed_decision_produces_no_defects():
    decision = AgentDecision.model_validate(
        {"decision": "continue", "rationale": "r", "evidence_ids": ["E001"], "requested_actions": [ABSTAIN_UNRESOLVED]}
    )
    assert _planner_defects(decision, {"E001"}, []) == []


_VALID = "__VALID__"


def _sequenced_llm(monkeypatch, planner_responses, critic_responses):
    """Stub that can answer differently on the repair call."""
    counts = {"planner": 0, "critic": 0}

    def _pick(queue, key):
        spec = queue[min(counts[key], len(queue) - 1)]
        counts[key] += 1
        return dict(spec)

    def _resolve(spec, payload):
        if spec.get("evidence_ids") == [_VALID]:
            spec["evidence_ids"] = [payload["valid_evidence_ids"][0]]
        return spec

    class _Stub:
        def __init__(self, cfg):
            self.cfg = cfg

        def ask_json(self, system, payload, schema):
            if schema.__name__ in {"AgentDecision", "PlannerDecision"}:
                base = {"decision": "continue", "rationale": "stub", "alternative_explanations": ["true_presence"]}
                return _fit_schema(schema, {**base, **_resolve(_pick(planner_responses, "planner"), payload)})
            base = {"verdict": "accept", "rationale": "stub"}
            return _fit_schema(schema, {**base, **_resolve(_pick(critic_responses, "critic"), payload)})

    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v2.OllamaJSONClient", _Stub)
    return counts


def _run_sequenced(tmp_path, monkeypatch, planner_responses, critic_responses):
    from genome_skeptic.agents.assembly_loop_v2 import run_skeptic_agentic_v2

    assembly, targets = _write_case(tmp_path)
    counts = _sequenced_llm(monkeypatch, planner_responses, critic_responses)
    claims, loci, prov = run_skeptic_agentic_v2(assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"])
    return claims, prov, counts


def test_planner_payload_exposes_a_flat_list_of_valid_evidence_ids(tmp_path, monkeypatch):
    seen = {}

    class _Stub:
        def __init__(self, cfg):
            self.cfg = cfg

        def ask_json(self, system, payload, schema):
            seen.setdefault(schema.__name__, payload)
            if schema.__name__ in {"AgentDecision", "PlannerDecision"}:
                return _fit_schema(
                    schema,
                    {
                        "decision": "continue",
                        "rationale": "stub",
                        "evidence_ids": [payload["valid_evidence_ids"][0]],
                        "requested_actions": [FINALIZE_WITH_CURRENT_EVIDENCE],
                    },
                )
            return _fit_schema(schema, {"verdict": "accept", "rationale": "stub", "evidence_ids": [payload["valid_evidence_ids"][0]]})

    from genome_skeptic.agents.assembly_loop_v2 import run_skeptic_agentic_v2

    assembly, targets = _write_case(tmp_path)
    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v2.OllamaJSONClient", _Stub)
    run_skeptic_agentic_v2(assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"])
    for payload in seen.values():
        assert payload["valid_evidence_ids"]
        assert all(eid.startswith("E") for eid in payload["valid_evidence_ids"])


def test_planner_is_told_which_actions_can_still_change_a_measurement(tmp_path, monkeypatch):
    """Abstention must be checkable against one list, not inferred from 17 entries."""
    seen = {}

    class _Stub:
        def __init__(self, cfg):
            self.cfg = cfg

        def ask_json(self, system, payload, schema):
            seen.setdefault(schema.__name__, payload)
            if schema.__name__ in {"AgentDecision", "PlannerDecision"}:
                return _fit_schema(
                    schema,
                    {
                        "decision": "continue",
                        "rationale": "stub",
                        "evidence_ids": [payload["valid_evidence_ids"][0]],
                        "requested_actions": [FINALIZE_WITH_CURRENT_EVIDENCE],
                    },
                )
            return _fit_schema(schema, {"verdict": "accept", "rationale": "stub", "evidence_ids": [payload["valid_evidence_ids"][0]]})

    from genome_skeptic.agents.assembly_loop_v2 import run_skeptic_agentic_v2

    assembly, targets = _write_case(tmp_path)
    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v2.OllamaJSONClient", _Stub)
    _claims, _loci, prov = run_skeptic_agentic_v2(
        assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"]
    )
    payload = seen["PlannerDecision"]
    can_change = payload["actions_that_can_change_a_measurement_now"]
    assert "inspect_hit_contig_contamination" in can_change
    assert "search_target_genes_nucleotide" not in can_change
    assert "inspect_paralogue_copies" not in can_change
    assert "inspect_read_supported_breaks" not in can_change
    assert "inspect_local_coverage_for_target" not in can_change
    assert "NOT yet justified" in payload["abstention_precondition"]
    rows = {row["action_id"]: row for row in payload["available_actions"]}
    assert "search_target_genes_nucleotide" not in rows
    assert "inspect_read_supported_breaks" not in rows
    assert "inspect_local_coverage_for_target" not in rows
    assert "inspect_hit_contig_contamination" in rows
    assert payload["registered_actions"] == can_change
    assert all("values" not in row for row in payload["evidence"])
    assert prov["state_changing_actions"] == can_change
    assert any(row["action_id"] == "search_target_genes_nucleotide" for row in prov["inert_actions"])


def test_a_field_name_cited_as_an_evidence_id_is_repaired_not_fatal(tmp_path, monkeypatch):
    """The dev_01 smoke failure: evidence_ids was ['hits'] alongside a valid abstention."""
    claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[
            {"evidence_ids": ["hits"], "requested_actions": [ABSTAIN_UNRESOLVED]},
            {"evidence_ids": [_VALID], "requested_actions": [ABSTAIN_UNRESOLVED]},
        ],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert counts["planner"] == 2, "the repair pass must fire on an invalid citation, not only an empty one"
    assert prov["planner_dropped_evidence_ids"] == ["hits"]
    assert prov["agent_failure"] is None
    assert prov["control_decision"] == ABSTAIN_UNRESOLVED
    assert prov["final_validator_ran"] is True
    assert claims[0].confidence > 0.0


def test_a_valid_first_answer_does_not_burn_a_repair(tmp_path, monkeypatch):
    _claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [_VALID], "requested_actions": ["inspect_hit_contig_contamination"]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert counts["planner"] == 1
    assert prov["planner_defects"] == []
    assert prov["final_validator_ran"] is True


def test_repair_budget_is_one_and_then_it_still_fails_closed(tmp_path, monkeypatch):
    claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": ["hits"], "requested_actions": [ABSTAIN_UNRESOLVED]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert counts["planner"] == 2
    assert prov["planner_defects_after_repair"]
    assert prov["agent_failure"] is not None
    assert prov["final_validator_ran"] is False
    assert claims[0].confidence == 0.0


def test_critic_citation_is_repaired_the_same_way(tmp_path, monkeypatch):
    _claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [_VALID], "requested_actions": [FINALIZE_WITH_CURRENT_EVIDENCE]}],
        critic_responses=[{"evidence_ids": ["hits"]}, {"evidence_ids": [_VALID]}],
    )
    assert counts["critic"] == 2
    assert prov["critic_dropped_evidence_ids"] == ["hits"]
    assert prov["agent_failure"] is None
    assert prov["final_validator_ran"] is True


def test_critic_ids_named_only_in_prose_are_recovered(tmp_path, monkeypatch):
    """The dev_01 rerun failure: the critic argued from E002/E003 but left evidence_ids empty."""
    _claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [_VALID], "requested_actions": [FINALIZE_WITH_CURRENT_EVIDENCE]}],
        critic_responses=[
            {
                "verdict": "challenge",
                "rationale": "E003 shows n_edge_hits=0 and E002 confirms a canonical full-length homolog.",
                "evidence_ids": [],
            }
        ],
    )
    assert counts["critic"] == 1, "recovery should settle this without spending the repair call"
    assert prov["critic_cited_evidence_ids"] == ["E003", "E002"]
    assert prov["agent_failure"] is None
    assert prov["final_validator_ran"] is True


def test_critic_recovery_never_invents_an_id_it_did_not_write(tmp_path, monkeypatch):
    """A citation-less critic is unusable for a second action, but cannot veto the claim."""
    _claims, prov, _counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [_VALID], "requested_actions": [FINALIZE_WITH_CURRENT_EVIDENCE]}],
        critic_responses=[{"rationale": "no citation at all", "evidence_ids": []}],
    )
    assert prov["critic_unusable"] == "critic cited no evidence IDs"
    assert prov["critic_second_action"] is None
    assert prov["agent_failure"] is None
    assert prov["final_validator_ran"] is True


def test_ask_human_is_aliased_to_abstain_not_a_crash(tmp_path, monkeypatch):
    """Latest smoke: qwen3:4b copied the V1 decision verb into requested_actions."""
    claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"decision": "ask_human", "evidence_ids": [_VALID], "requested_actions": ["ask_human"]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert counts["planner"] == 1, "aliasing must not spend the repair pass"
    assert prov["v1_requested_action_aliased"] == "ask_human"
    assert prov["control_decision"] == ABSTAIN_UNRESOLVED
    assert prov["agent_failure"] is None
    assert prov["final_validator_ran"] is True
    assert claims[0].confidence > 0.0


def test_v1_stop_is_aliased_the_same_way():
    aliased, verb = _alias_v1_requested_actions(["stop"], "stop")
    assert aliased == [ABSTAIN_UNRESOLVED]
    assert verb == "stop"
    choice, err = _validate_planner(
        AgentDecision.model_validate(
            {"decision": "ask_human", "rationale": "r", "evidence_ids": ["E001"], "requested_actions": ["ask_human"]}
        ),
        {"E001"},
    )
    assert err is None
    assert choice == ABSTAIN_UNRESOLVED


def test_a_registered_action_next_to_ask_human_is_kept():
    aliased, verb = _alias_v1_requested_actions(["ask_human", "inspect_hit_contig_contamination"], "ask_human")
    assert aliased == ["inspect_hit_contig_contamination"]
    assert verb is None


def test_unregistered_action_from_the_planner_still_fails_closed(tmp_path, monkeypatch):
    claims, _loci, prov = _run(tmp_path, monkeypatch, planner_actions=["set_the_claim_to_supported"])
    assert prov["agent_failure"] is not None
    assert prov["final_validator_ran"] is False
    assert claims[0].confidence == 0.0


# --- derived-state consistency after hits change ----------------------------


def test_second_hit_recomputes_all_multiplicity_representations():
    """tuf-class bug: hits become 2 loci while reconstruction.multiplicity stays single_locus."""
    from genome_skeptic.agents.derived_state import assert_hits_derived_consistent
    from genome_skeptic.validators.family_orthology import FamilyEvidence
    from genome_skeptic.validators.falsification import _loci

    settings = Settings()
    first = _hit(
        contig_id="locus_1",
        tstart=100,
        tend=400,
        search_kind="translated",
        identity=1.0,
        query_coverage=1.0,
        contig_length=2000,
    )
    fam = FamilyEvidence(
        family_id="tuf_EF_Tu",
        architecture="canonical_full_length",
        supports_orthologue=True,
        reconstruction={
            "architecture": "canonical_full_length",
            "multiplicity": {"classification": "single_locus", "number_of_candidate_loci": 1},
        },
        paralogue={"state": "single_locus", "supported": False},
        limitations=["only one placed EF-Tu locus is present in the current hit set"],
        metrics={"multiplicity_classification": "single_locus"},
    )
    m = _measurements(
        [first],
        family_evidence=fam,
        contig_sequences={"locus_1": "A" * 2000, "locus_2": "C" * 2000},
    )
    second = _hit(
        contig_id="locus_2",
        tstart=100,
        tend=400,
        search_kind="translated",
        identity=0.9276,
        query_coverage=1.0,
        contig_length=2000,
        tool="hmmer_nominated_alignment",
    )
    result = apply_action_result(
        m,
        _informative(
            "search_target_domains_hmmer",
            [MeasurementPatch(field="hits", value=[second], origin="hmm_orf_search")],
        ),
        settings=settings,
    )
    assert result.status is ActionStatus.informative
    n = len(_loci(m.hits, settings))
    assert n == 2
    multi = m.family_evidence.reconstruction["multiplicity"]
    assert multi["number_of_candidate_loci"] == 2
    assert multi["classification"] != "single_locus"
    assert m.family_evidence.paralogue["state"] == "multiple_loci"
    assert m.family_evidence.paralogue["n_loci"] == 2
    assert m.family_evidence.metrics["n_loci"] == 2
    assert m.family_evidence.metrics["multiplicity_classification"] != "single_locus"
    assert_hits_derived_consistent(m, settings)
    assert not any("only one placed" in item.lower() for item in (m.family_evidence.limitations or []))
    assert any(u.field == "family_evidence" for u in result.applied if u.n_new)


def test_planner_and_critic_views_record_compact_runtime_metrics(tmp_path, monkeypatch):
    """Runtime regression: payloads stay small; unavailable actions never reach the model."""
    seen = {}

    class _Stub:
        def __init__(self, cfg):
            self.cfg = cfg

        def ask_json(self, system, payload, schema):
            seen.setdefault(schema.__name__, payload)
            if schema.__name__ in {"AgentDecision", "PlannerDecision"}:
                return _fit_schema(
                    schema,
                    {
                        "decision": "continue",
                        "rationale": "stub",
                        "evidence_ids": [payload["valid_evidence_ids"][0]],
                        "requested_actions": [FINALIZE_WITH_CURRENT_EVIDENCE],
                    },
                )
            return _fit_schema(schema, {"verdict": "accept", "rationale": "stub", "evidence_ids": [payload["valid_evidence_ids"][0]]})

    from genome_skeptic.agents.assembly_loop_v2 import run_skeptic_agentic_v2
    from genome_skeptic.agents.planner_views import estimated_tokens

    assembly, targets = _write_case(tmp_path)
    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v2.OllamaJSONClient", _Stub)
    _claims, _loci_out, prov = run_skeptic_agentic_v2(
        assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"]
    )
    planner_payload = seen["PlannerDecision"]
    critic_payload = seen["CriticDecision"]
    planner_ids = {row["action_id"] for row in planner_payload["available_actions"]}
    critic_ids = {row["action_id"] for row in critic_payload["available_actions"]}
    for banned in (
        "inspect_read_supported_breaks",
        "inspect_local_coverage_for_target",
        "search_target_genes_nucleotide",
        "inspect_paralogue_copies",
    ):
        assert banned not in planner_ids
        assert banned not in critic_ids
    planner_tokens = estimated_tokens(planner_payload)
    critic_tokens = estimated_tokens(critic_payload)
    assert planner_tokens <= 1200, planner_tokens
    assert critic_tokens <= 1300, critic_tokens
    assert prov["planner_estimated_tokens"] == planner_tokens
    assert prov["critic_estimated_tokens"] == critic_tokens
    assert "planner_seconds" in prov
    assert "critic_seconds" in prov
    assert "llm_seconds" in prov


def test_genome_workspace_reuses_orfs_for_the_same_assembly():
    from genome_skeptic.agents.genome_workspace import clear_workspaces, get_workspace

    clear_workspaces()
    seqs = {"c1": "ATG" + ("AAATTTGGGCCC" * 40) + "TAA"}
    first = get_workspace(seqs, min_aa=20, edge_bp=10)
    second = get_workspace(seqs, min_aa=20, edge_bp=10)
    assert first is second
    assert first.orfs
