"""Planner/critic views for Agentic V4-dev.

Same control-flow contract as V3. Ranking uses DECISION_RELEVANCE.
"""
from __future__ import annotations

from typing import Any

from genome_skeptic.agents.action_catalog_v4_dev import rank_candidate_actions, remaining_relevant_actions
from genome_skeptic.agents.action_contract import (
    ABSTAIN_UNRESOLVED,
    CONTROL_DECISION_SEMANTICS,
    CONTROL_DECISIONS,
    FINALIZE_WITH_CURRENT_EVIDENCE,
)
from genome_skeptic.agents.diagnostic_needs_v4_dev import derive_diagnostic_needs_v4_dev, need_payload
from genome_skeptic.agents.planner_views import _current_result, _observation_line, estimated_tokens
from genome_skeptic.agents.planner_views_v3 import CRITIC_CONSTRAINTS, PLANNER_CONSTRAINTS
from genome_skeptic.claims.hypothesis_graph import HYPOTHESIS_IDS
from genome_skeptic.models import AgentDecision, Evidence
from genome_skeptic.validators.falsification import TargetMeasurements
from genome_skeptic.validators.locus_v4_dev import loci_from_measurements


def _edge_bp(settings) -> int:
    return int(getattr(getattr(settings, "thresholds", None), "contig_edge_proximity_bp", 300) or 300)


def build_planner_view_v4_dev(
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
    n_loci = len(loci_from_measurements(m, cfg))
    edge_bp = _edge_bp(cfg)
    needs = derive_diagnostic_needs_v4_dev(m, capabilities, settings=cfg, edge_bp=edge_bp)
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


def build_critic_view_v4_dev(
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
    n_loci = len(loci_from_measurements(m, cfg))
    edge_bp = _edge_bp(cfg)
    needs = derive_diagnostic_needs_v4_dev(m, capabilities, settings=cfg, edge_bp=edge_bp)
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
    "build_planner_view_v4_dev",
    "build_critic_view_v4_dev",
    "estimated_tokens",
]
