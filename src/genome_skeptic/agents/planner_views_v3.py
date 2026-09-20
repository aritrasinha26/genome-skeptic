"""Compact planner/critic views for Agentic V3.

The planner sees the dedicated live instrument for each current DiagnosticNeed,
then remaining slots filled by score (default fill to 3), plus control
decisions. Evidence IDs are supplied for claim grounding; they are not a
prerequisite for executing a registered diagnostic action.
"""
from __future__ import annotations

from typing import Any

from genome_skeptic.agents.action_catalog_v3 import rank_candidate_actions, remaining_relevant_actions
from genome_skeptic.agents.action_contract import (
    ABSTAIN_UNRESOLVED,
    CONTROL_DECISION_SEMANTICS,
    CONTROL_DECISIONS,
    FINALIZE_WITH_CURRENT_EVIDENCE,
)
from genome_skeptic.agents.diagnostic_needs import derive_diagnostic_needs, need_payload
from genome_skeptic.agents.planner_views import _current_result, _observation_line, estimated_tokens
from genome_skeptic.claims.hypothesis_graph import HYPOTHESIS_IDS
from genome_skeptic.models import AgentDecision, Evidence
from genome_skeptic.validators.falsification import TargetMeasurements, _loci


PLANNER_CONSTRAINTS = [
    "Return one concise decision. At most one requested_action from available_actions or control.",
    "evidence_ids, if present, must be copied verbatim from valid_evidence_ids. They ground the scientific claim, not action execution.",
    "Do not invent measurements. The deterministic validator assigns the final claim.",
    "Rationale <= 160 characters. Do not restate evidence values.",
    f"requested_action is one available_actions id, '{FINALIZE_WITH_CURRENT_EVIDENCE}', '{ABSTAIN_UNRESOLVED}', or null.",
    f"Choose '{ABSTAIN_UNRESOLVED}' only when available_actions is empty.",
]

CRITIC_CONSTRAINTS = [
    "Attack the preferred hypothesis using the current deterministic scientific state.",
    "Cite at least one evidence ID copied verbatim from valid_evidence_ids.",
    "If challenge: requested_action = one remaining_actions id; failure_mode = one hypothesis_id.",
    "If accept: requested_action and failure_mode are null.",
    "At most one additional action. Do not invent measurements.",
]


def _edge_bp(settings) -> int:
    return int(getattr(getattr(settings, "thresholds", None), "contig_edge_proximity_bp", 300) or 300)


def build_planner_view_v3(
    m: TargetMeasurements,
    *,
    evidence: list[Evidence],
    capabilities: dict[str, bool],
    performed: frozenset[str],
    settings=None,
    actions_already_tried: list[str] | None = None,
    planner_grounding_status: str | None = None,
) -> dict[str, Any]:
    from genome_skeptic.config import Settings

    cfg = settings or Settings()
    n_loci = len(_loci(m.hits, cfg))
    edge_bp = _edge_bp(cfg)
    needs = derive_diagnostic_needs(m, capabilities, settings=cfg, edge_bp=edge_bp)
    available = rank_candidate_actions(
        needs,
        capabilities,
        performed,
        m,
        edge_bp=edge_bp,
        already_run=actions_already_tried,
        limit=3,
    )
    can_change = [row["action_id"] for row in available]
    return {
        "target": m.query_id,
        "current_result": _current_result(m, n_loci),
        "diagnostic_needs": need_payload(needs),
        "key_observations": [_observation_line(ev) for ev in evidence],
        "evidence": [{"id": ev.id, "summary": ev.summary} for ev in evidence],
        "actions_already_tried": list(actions_already_tried or []),
        "available_actions": available,
        "actions_that_can_change_a_measurement_now": can_change,
        "registered_actions": can_change,
        "control_decisions": [{"decision_id": cid, "meaning": CONTROL_DECISION_SEMANTICS[cid]} for cid in CONTROL_DECISIONS],
        "valid_evidence_ids": [e.id for e in evidence],
        "registered_hypothesis_ids": list(HYPOTHESIS_IDS),
        "planner_grounding_status": planner_grounding_status,
        "abstention_precondition": (
            "available_actions is empty, so ABSTAIN_UNRESOLVED is the correct choice."
            if not can_change
            else (
                f"available_actions lists {len(can_change)} ranked action(s); "
                "ABSTAIN_UNRESOLVED is NOT yet justified."
            )
        ),
        "constraints": PLANNER_CONSTRAINTS,
    }


def build_critic_view_v3(
    decision: AgentDecision,
    *,
    m: TargetMeasurements,
    evidence: list[Evidence],
    capabilities: dict[str, bool],
    performed: frozenset[str],
    actions_already_tried: list[str],
    new_evidence: list[Evidence] | None = None,
    transition: dict[str, Any] | None = None,
    settings=None,
    planner_grounding_status: str | None = None,
    planner_control_failure: str | None = None,
) -> dict[str, Any]:
    from genome_skeptic.config import Settings

    cfg = settings or Settings()
    n_loci = len(_loci(m.hits, cfg))
    edge_bp = _edge_bp(cfg)
    needs = derive_diagnostic_needs(m, capabilities, settings=cfg, edge_bp=edge_bp)
    remaining = remaining_relevant_actions(
        needs,
        capabilities,
        performed,
        m,
        edge_bp=edge_bp,
        already_run=actions_already_tried,
        limit=3,
    )
    preferred = (decision.alternative_explanations or ["insufficient_data"])[0]
    ledger_tail = new_evidence if new_evidence is not None else evidence[-4:]
    return {
        "target": m.query_id,
        "current_state": _current_result(m, n_loci),
        "diagnostic_needs": need_payload(needs),
        "planner": {
            "hypothesis": preferred,
            "alternative": (decision.alternative_explanations or [None, None])[1]
            if len(decision.alternative_explanations or []) > 1
            else None,
            "action": (decision.requested_actions or [None])[0],
            "evidence_ids": list(decision.evidence_ids or []),
            "grounding_status": planner_grounding_status,
            "control_failure": planner_control_failure,
            "confidence": decision.confidence,
            "rationale": (decision.rationale or "")[:280],
        },
        "action_already_executed": (actions_already_tried or [None])[-1] if actions_already_tried else None,
        "new_evidence": [_observation_line(ev) for ev in ledger_tail],
        "evidence": [{"id": ev.id, "summary": ev.summary} for ev in evidence],
        "measurement_update": None
        if not transition
        else {
            "from": transition.get("from"),
            "to": transition.get("to"),
            "action_id": transition.get("action_id"),
            "status": transition.get("status"),
            "updated_measurement_fields": transition.get("updated_measurement_fields"),
            "n_new_measurements": transition.get("n_new_measurements"),
        },
        "remaining_diagnostic_needs": need_payload(needs),
        "remaining_actions": remaining,
        "available_actions": remaining,
        "actions_already_tried": list(actions_already_tried),
        "valid_evidence_ids": [e.id for e in evidence],
        "registered_hypothesis_ids": list(HYPOTHESIS_IDS),
        "question": "Does the current interpretation have a credible unresolved alternative that a remaining action can test?",
        "constraints": CRITIC_CONSTRAINTS,
    }


__all__ = [
    "PLANNER_CONSTRAINTS",
    "CRITIC_CONSTRAINTS",
    "build_planner_view_v3",
    "build_critic_view_v3",
    "estimated_tokens",
]
