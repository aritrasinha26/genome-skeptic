"""Compact planner/critic views. The full evidence ledger stays on disk.

Qwen receives scientifically relevant summaries and evidence IDs, not raw hit
dictionaries, reconstruction blobs, or the full action catalog.
"""
from __future__ import annotations

from typing import Any

from genome_skeptic.agents.action_catalog import executable_action_payload, state_changing_action_ids
from genome_skeptic.agents.action_contract import ABSTAIN_UNRESOLVED, CONTROL_DECISION_SEMANTICS, CONTROL_DECISIONS, FINALIZE_WITH_CURRENT_EVIDENCE
from genome_skeptic.claims.hypothesis_graph import HYPOTHESIS_IDS
from genome_skeptic.models import AgentDecision, Evidence, GeneSearchHit
from genome_skeptic.validators.falsification import TargetMeasurements, _loci
from genome_skeptic.validators.homology import strong_hit


_COMPACT_CONSTRAINTS = [
    "Return one concise decision. Cite evidence IDs from valid_evidence_ids.",
    "At most one alternative_hypothesis. At most one requested_action.",
    "Rationale <= 160 characters. Do not restate evidence values.",
    f"requested_action is one available_actions id, '{FINALIZE_WITH_CURRENT_EVIDENCE}', '{ABSTAIN_UNRESOLVED}', or null.",
    f"Choose '{ABSTAIN_UNRESOLVED}' only when available_actions is empty.",
]

_CRITIC_CONSTRAINTS = [
    "Attack the preferred hypothesis. Cite at least one evidence ID from valid_evidence_ids.",
    "If challenge: requested_action = one available_actions id; failure_mode = one hypothesis_id; rationale = one sentence.",
    "If accept: requested_action and failure_mode are null.",
]


def _best_hit(hits: list[GeneSearchHit]) -> GeneSearchHit | None:
    genomic = [h for h in hits if h.search_kind in {"translated", "protein", "nucleotide"}]
    pool = genomic or list(hits)
    if not pool:
        return None
    return max(pool, key=lambda h: (h.query_coverage * h.identity, h.alignment_length))


def _current_result(m: TargetMeasurements, n_loci: int) -> dict[str, Any]:
    fam = m.family_evidence
    recon = getattr(fam, "reconstruction", None) or {}
    multi = recon.get("multiplicity") or {}
    best = _best_hit(m.hits)
    settings = None
    detected = False
    try:
        from genome_skeptic.config import Settings
        from genome_skeptic.validators.family_orthology import family_detects_orthologue

        settings = Settings()
        if fam is not None:
            detected = bool(family_detects_orthologue(m.profile, m.hits, settings, fam))
        elif best is not None:
            detected = bool(strong_hit(best, settings, m.profile.target_type))
    except Exception:
        detected = bool(best and best.query_coverage >= 0.80 and best.identity >= 0.60)
    return {
        "polarity": "detected" if detected else "not_detected",
        "n_hits": len(m.hits),
        "n_loci": n_loci,
        "best_hit": None
        if best is None
        else {
            "contig": best.contig_id,
            "kind": best.search_kind,
            "identity": round(best.identity, 4),
            "coverage": round(best.query_coverage, 4),
            "tool": best.tool,
            "evidence_hint": "see evidence_ids",
        },
        "family_architecture": getattr(fam, "architecture", None) if fam is not None else None,
        "supports_orthologue": getattr(fam, "supports_orthologue", None) if fam is not None else None,
        "multiplicity": multi.get("classification"),
        "number_of_candidate_loci": multi.get("number_of_candidate_loci", n_loci),
    }


def _observation_line(ev: Evidence) -> dict[str, Any]:
    values = ev.values or {}
    note: dict[str, Any] = {}
    for key in (
        "n_hits",
        "n_strong",
        "n_loci",
        "n_hits_before",
        "n_hits_after",
        "identity",
        "query_coverage",
        "architecture",
        "supports_orthologue",
        "status",
        "action",
        "from_state",
        "to_state",
        "classification",
        "limitation",
    ):
        if key in values and values[key] not in (None, "", [], {}):
            note[key] = values[key]
    hits = values.get("hits")
    if isinstance(hits, list) and hits:
        first = hits[0] if isinstance(hits[0], dict) else {}
        if first:
            note["best_identity"] = first.get("identity")
            note["best_coverage"] = first.get("query_coverage")
            note["best_contig"] = first.get("contig_id") or first.get("contig")
            note["best_kind"] = first.get("search_kind") or first.get("kind")
    metrics = values.get("metrics")
    if isinstance(metrics, dict):
        if metrics.get("best_member_identity") is not None:
            note["best_member_identity"] = metrics.get("best_member_identity")
        if metrics.get("best_member_coverage") is not None:
            note["best_member_coverage"] = metrics.get("best_member_coverage")
        if metrics.get("multiplicity_classification"):
            note["multiplicity"] = metrics.get("multiplicity_classification")
    limitations = values.get("limitations")
    if limitations:
        note["limitations"] = list(limitations)[:3]
    return {"id": ev.id, "summary": ev.summary, **note}


def _uncertainties(m: TargetMeasurements, n_loci: int) -> list[str]:
    items: list[str] = []
    best = _best_hit(m.hits)
    fam = m.family_evidence
    if best is not None and best.query_coverage < 0.70:
        items.append("current hit has low coverage; divergent orthologue possible")
    if fam is None or not getattr(fam, "best_hmm", None):
        items.append("no family HMM result available yet")
    recon = getattr(fam, "reconstruction", None) or {}
    multi = recon.get("multiplicity") or {}
    if n_loci <= 1 and (multi.get("classification") or "single_locus") == "single_locus":
        items.append("additional unplaced copies have not been excluded")
    if not m.mapping_available:
        items.append("no mapping; read-supported breaks cannot be tested")
    if not items:
        items.append("whether the current measurements already discriminate the alternatives")
    return items[:4]


def build_planner_view(
    m: TargetMeasurements,
    *,
    evidence: list[Evidence],
    capabilities: dict[str, bool],
    performed: frozenset[str],
    actions_already_tried: list[str] | None = None,
    settings=None,
) -> dict[str, Any]:
    """User payload for the planner. Hundreds of tokens, not thousands."""
    cfg = settings
    if cfg is None:
        from genome_skeptic.config import Settings

        cfg = Settings()
    n_loci = len(_loci(m.hits, cfg))
    edge_bp = int(getattr(getattr(cfg, "thresholds", None), "contig_edge_proximity_bp", 300) or 300)
    available = executable_action_payload(capabilities, performed, m, edge_bp=edge_bp)
    can_change = state_changing_action_ids(capabilities, performed, m, edge_bp=edge_bp)
    return {
        "target": m.query_id,
        "current_result": _current_result(m, n_loci),
        "key_observations": [_observation_line(ev) for ev in evidence],
        "evidence": [{"id": ev.id, "summary": ev.summary} for ev in evidence],
        "main_uncertainties": _uncertainties(m, n_loci),
        "actions_already_tried": list(actions_already_tried or []),
        "available_actions": available,
        "actions_that_can_change_a_measurement_now": can_change,
        "registered_actions": can_change,
        "control_decisions": [{"decision_id": cid, "meaning": CONTROL_DECISION_SEMANTICS[cid]} for cid in CONTROL_DECISIONS],
        "valid_evidence_ids": [e.id for e in evidence],
        "registered_hypothesis_ids": list(HYPOTHESIS_IDS),
        "abstention_precondition": (
            "available_actions is empty, so ABSTAIN_UNRESOLVED is the correct choice."
            if not can_change
            else (
                f"available_actions lists {len(can_change)} executable action(s); "
                "ABSTAIN_UNRESOLVED is NOT yet justified."
            )
        ),
        "constraints": _COMPACT_CONSTRAINTS,
    }


def build_critic_view(
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
) -> dict[str, Any]:
    """User payload for the critic. Smaller than the planner view; no full replay."""
    cfg = settings
    if cfg is None:
        from genome_skeptic.config import Settings

        cfg = Settings()
    n_loci = len(_loci(m.hits, cfg))
    edge_bp = int(getattr(getattr(cfg, "thresholds", None), "contig_edge_proximity_bp", 300) or 300)
    available = [
        row
        for row in executable_action_payload(capabilities, performed, m, edge_bp=edge_bp)
        if row["action_id"] not in set(actions_already_tried)
    ]
    preferred = (decision.alternative_explanations or ["insufficient_data"])[0]
    ledger_tail = new_evidence if new_evidence is not None else evidence[-4:]
    return {
        "target": m.query_id,
        "current_state": _current_result(m, n_loci),
        "planner": {
            "hypothesis": preferred,
            "alternative": (decision.alternative_explanations or [None, None])[1] if len(decision.alternative_explanations or []) > 1 else None,
            "action": (decision.requested_actions or [None])[0],
            "evidence_ids": list(decision.evidence_ids or []),
            "confidence": decision.confidence,
            "rationale": (decision.rationale or "")[:280],
        },
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
        "question": "Does the current interpretation have a credible unresolved alternative?",
        "available_actions": available,
        "actions_already_tried": list(actions_already_tried),
        "valid_evidence_ids": [e.id for e in evidence],
        "registered_hypothesis_ids": list(HYPOTHESIS_IDS),
        "constraints": _CRITIC_CONSTRAINTS,
    }


def estimated_tokens(payload: dict[str, Any]) -> int:
    import json

    text = json.dumps(payload, separators=(",", ":"), default=str)
    return max(1, (len(text) + 3) // 4)
