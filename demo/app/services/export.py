"""Export locked or live results as CSV, TSV, or JSON with provenance metadata."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable

from demo.app.services.trace_model import NOT_AVAILABLE, target_short

PRECOMPUTED_MODE = "PRECOMPUTED — locked record from the frozen GENOME_SKEPTIC_V4_1_MANUSCRIPT M60 run (not recomputed)"
LIVE_MODE = "LIVE — computed in this session by the Genome Skeptic code deployed with this app"

CASE_COLUMNS = [
    "analysis_mode",
    "sample_id",
    "accession",
    "organism",
    "target",
    "stratum",
    "independent_truth",
    "truth_status",
    "system",
    "endpoint",
    "correct_vs_truth",
    "claim_type",
    "claim_status",
    "evidence_score_uncalibrated",
    "evidence_completeness",
    "architecture",
    "homology_support",
    "supporting_evidence_ids",
    "falsification_tests_completed",
    "falsification_tests_total",
    "planner_action",
    "critic_verdict",
    "follow_up_actions",
    "model",
    "system_version",
    "git_commit",
    "scientific_core_hash",
    "tool_versions",
    "database_versions",
    "reference_database",
]


def _na(v: Any) -> Any:
    return NOT_AVAILABLE if v is None or v == "" or v == [] else v


def case_export_rows(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per system for a locked case."""
    case = trace["case"]
    frozen = trace.get("frozen_system") or {}
    common = {
        "analysis_mode": PRECOMPUTED_MODE,
        "sample_id": case["case_id"],
        "accession": case["accession"],
        "organism": case["organism"],
        "target": case["target"],
        "stratum": case["stratum"],
        "independent_truth": case["truth"],
        "truth_status": case["truth_status"],
        "system_version": _na(frozen.get("system_version")),
        "git_commit": _na(frozen.get("git_commit")),
        "scientific_core_hash": _na(frozen.get("scientific_core_hash")),
        "tool_versions": json.dumps(frozen.get("tool_versions") or {}, sort_keys=True),
        "database_versions": json.dumps(frozen.get("database_versions") or {}, sort_keys=True),
        "reference_database": (
            f"Curated Genome Skeptic family '{case['target']}' (src/genome_skeptic/data/target_families); "
            f"family_definitions_hash={(frozen.get('database_versions') or {}).get('family_definitions_hash', NOT_AVAILABLE)}"
        ),
    }
    rows = []
    for key, system in (("conventional", "CONVENTIONAL"), ("specialist", case.get("specialist_tool") or "SPECIALIST")):
        rows.append(
            {
                **common,
                "system": system,
                "endpoint": _na(case.get(f"{key}_pred")),
                "correct_vs_truth": _na(case.get(f"{key}_correct")) if case.get("evaluable") else "Not evaluated",
                "model": "none",
            }
        )
    for key, arm in (("gs_det", "GS_DETERMINISTIC_V4_1"), ("gs_agent", "GS_AGENTIC_V4_1"), ("gs_exh", "GS_EXHAUSTIVE_V4_1")):
        rec = trace["arms"][arm]
        claim = rec.get("claim") or {}
        prov = rec.get("provenance") or {}
        tests = claim.get("falsification_tests") or []
        rows.append(
            {
                **common,
                "system": arm,
                "endpoint": _na(case.get(f"{key}_pred")),
                "correct_vs_truth": _na(case.get(f"{key}_correct")) if case.get("evaluable") else "Not evaluated",
                "claim_type": _na(claim.get("claim_type")),
                "claim_status": _na(claim.get("status")),
                "evidence_score_uncalibrated": _na(claim.get("confidence")),
                "evidence_completeness": _na(claim.get("evidence_completeness")),
                "architecture": _na(claim.get("architecture_state")),
                "homology_support": _na(claim.get("homology_support")),
                "supporting_evidence_ids": ";".join(claim.get("supporting_evidence_ids") or []) or NOT_AVAILABLE,
                "falsification_tests_completed": sum(1 for t in tests if t.get("status") == "completed"),
                "falsification_tests_total": len(tests),
                "planner_action": _na(prov.get("selected_action")) if arm == "GS_AGENTIC_V4_1" else "none (no LLM)",
                "critic_verdict": _na((prov.get("critic_challenge") or {}).get("verdict"))
                if arm == "GS_AGENTIC_V4_1"
                else "none (no LLM)",
                "follow_up_actions": len(prov.get("actions_executed") or []),
                "model": _na(rec.get("locked", {}).get("model")) if arm == "GS_AGENTIC_V4_1" else "none",
            }
        )
    return [{c: r.get(c, NOT_AVAILABLE) for c in CASE_COLUMNS} for r in rows]


def index_export_rows(index: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in index:
        out.append({"analysis_mode": PRECOMPUTED_MODE, **c, "target_short": target_short(c["target"])})
    return out


def to_delimited(rows: list[dict[str, Any]], delimiter: str = ",") -> bytes:
    if not rows:
        return b""
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, delimiter=delimiter, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: _cell(r.get(k)) for k in fields})
    return buf.getvalue().encode("utf-8")


def _cell(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True)
    return v


def to_csv(rows: list[dict[str, Any]]) -> bytes:
    return to_delimited(rows, ",")


def to_tsv(rows: list[dict[str, Any]]) -> bytes:
    return to_delimited(rows, "\t")


def case_json_report(trace: dict[str, Any]) -> bytes:
    """Full locked trace for one case, with an explicit mode banner."""
    payload = {
        "analysis_mode": PRECOMPUTED_MODE,
        "notice": (
            "Computational prediction from a frozen research benchmark. Not experimental validation. "
            "Evidence scores are uncalibrated heuristics, not probabilities."
        ),
        **trace,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode("utf-8")


def live_export_rows(result: dict[str, Any], input_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """One row for a live run, using the same columns as precomputed exports where they apply."""
    rec = result.get("record") or {}
    claim = rec.get("claim") or {}
    prov = rec.get("provenance") or {}
    core = result.get("core_check") or {}
    tests = claim.get("falsification_tests") or []
    arm = result.get("arm")
    row = {
        "analysis_mode": LIVE_MODE,
        "sample_id": input_summary.get("label") or "uploaded assembly",
        "accession": input_summary.get("accession") or NOT_AVAILABLE,
        "organism": "not declared",
        "target": result.get("target"),
        "stratum": "not part of a benchmark",
        "independent_truth": "Not evaluated",
        "truth_status": "Not evaluated",
        "system": arm,
        "endpoint": NOT_AVAILABLE,
        "correct_vs_truth": "Not evaluated",
        "claim_type": _na(claim.get("claim_type")),
        "claim_status": _na(claim.get("status")),
        "evidence_score_uncalibrated": _na(claim.get("confidence")),
        "evidence_completeness": _na(claim.get("evidence_completeness")),
        "architecture": _na(claim.get("architecture_state")),
        "homology_support": _na(claim.get("homology_support")),
        "supporting_evidence_ids": ";".join(claim.get("supporting_evidence_ids") or []) or NOT_AVAILABLE,
        "falsification_tests_completed": sum(1 for t in tests if t.get("status") == "completed"),
        "falsification_tests_total": len(tests),
        "planner_action": _na(prov.get("selected_action")) if arm == "GS_AGENTIC_V4_1" else "none (no LLM)",
        "critic_verdict": _na((prov.get("critic_challenge") or {}).get("verdict"))
        if arm == "GS_AGENTIC_V4_1"
        else "none (no LLM)",
        "follow_up_actions": len(prov.get("actions_executed") or []),
        "model": _na(result.get("model")) if arm == "GS_AGENTIC_V4_1" else "none",
        "system_version": "deployed code (see scientific-core comparison)",
        "git_commit": NOT_AVAILABLE,
        "scientific_core_hash": _na(core.get("byte_level_scientific_core_hash")),
        "tool_versions": json.dumps(result.get("tool_versions") or {}, sort_keys=True),
        "database_versions": NOT_AVAILABLE,
        "reference_database": f"Curated Genome Skeptic family '{result.get('target')}' as deployed",
    }
    row["input_sha256_sanitized"] = input_summary.get("sha256_sanitized") or NOT_AVAILABLE
    row["content_identical_to_frozen_m60_core"] = core.get("content_identical_to_frozen")
    return [row]


def live_json_report(result: dict[str, Any]) -> bytes:
    payload = {
        "analysis_mode": LIVE_MODE,
        "notice": (
            "Computed live from an uploaded sequence. Not part of any benchmark and not experimentally validated. "
            "Evidence scores are uncalibrated heuristics, not probabilities."
        ),
        **result,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode("utf-8")
