"""Development-only confidence calibration. Never fit on held-out cases."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from genome_skeptic.eval.scoring import CaseTruth, HiddenTruth, scientifically_correct, score_case, group_scores, merge_totals, overall_score
from genome_skeptic.models import Claim, TargetType


BIN_EDGES = [i / 10 for i in range(11)]


def _bin_index(p: float) -> int:
    if p >= 1.0:
        return len(BIN_EDGES) - 2
    idx = int(p * 10)
    return min(max(idx, 0), len(BIN_EDGES) - 2)


def _target_type_of(claim: Claim, expected) -> str:
    tt = getattr(expected, "target_type", None) if expected is not None else None
    if tt:
        return str(tt)
    notes = (claim.provenance.notes or "") if claim.provenance else ""
    for name in ("exact_allele", "gene_orthologue", "protein_family"):
        if name in notes:
            return name
    return "unknown"


def collect_pairs(report: dict, hidden: HiddenTruth, system: str = "genome_skeptic") -> list[dict]:
    rows = []
    for case in report.get("cases") or []:
        truth: CaseTruth | None = hidden.cases.get(case["case_id"]) if hidden.cases else None
        if truth is None:
            continue
        sys_blob = (case.get("systems") or {}).get(system) or {}
        targets = sys_blob.get("targets") or {}
        for target, expected in truth.targets.items():
            tblob = targets.get(target) or {}
            claims = []
            # Reconstruct a minimal Claim for correctness if needed
            from genome_skeptic.models import ClaimStatus, ClaimType, ClaimProvenance
            if tblob:
                claim = Claim(
                    claim_id=f"C_target_{target}",
                    claim_type=ClaimType(tblob["claim_type"]) if tblob.get("claim_type") else ClaimType.target_gene_not_detected,
                    statement=tblob.get("statement") or "",
                    status=ClaimStatus(tblob["status"]) if tblob.get("status") else ClaimStatus.unresolved,
                    confidence=float(tblob.get("confidence") or 0.0),
                    evidence_completeness=float(tblob.get("evidence_completeness") or 0.0),
                    homology_support=tblob.get("homology_support"),
                    provenance=ClaimProvenance(stage="target_gene", notes=f"target_type={expected.target_type}"),
                )
            else:
                continue
            correct = scientifically_correct(claim, expected)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "target": target,
                    "target_type": expected.target_type or "unknown",
                    "confidence": claim.confidence,
                    "correct": int(bool(correct)),
                    "claim_type": claim.claim_type.value,
                    "status": claim.status.value,
                }
            )
    return rows


def reliability_table(pairs: list[dict]) -> list[dict]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    for row in pairs:
        buckets[_bin_index(float(row["confidence"]))].append(row)
    out = []
    for i in range(len(BIN_EDGES) - 1):
        lo, hi = BIN_EDGES[i], BIN_EDGES[i + 1]
        blob = buckets.get(i) or []
        n = len(blob)
        mean_p = sum(float(r["confidence"]) for r in blob) / n if n else None
        emp = sum(int(r["correct"]) for r in blob) / n if n else None
        # Laplace smoothing used only for the frozen map, recorded separately
        mapped = ((sum(int(r["correct"]) for r in blob) + 1) / (n + 2)) if True else None
        out.append(
            {
                "bin_low": lo,
                "bin_high": hi,
                "n": n,
                "mean_predicted": None if mean_p is None else round(mean_p, 4),
                "empirical_accuracy": None if emp is None else round(emp, 4),
                "smoothed_map": round(mapped, 4),
            }
        )
    return out


def brier_score(pairs: list[dict]) -> float | None:
    if not pairs:
        return None
    s = sum((float(r["confidence"]) - float(r["correct"])) ** 2 for r in pairs)
    return round(s / len(pairs), 4)


def expected_calibration_error(table: list[dict], n_total: int) -> float | None:
    if not n_total:
        return None
    acc = 0.0
    for row in table:
        n = row["n"]
        if not n or row["empirical_accuracy"] is None or row["mean_predicted"] is None:
            continue
        acc += (n / n_total) * abs(row["empirical_accuracy"] - row["mean_predicted"])
    return round(acc, 4)


def over_under_rates(pairs: list[dict]) -> dict:
    if not pairs:
        return {"overconfidence_rate": None, "underconfidence_rate": None}
    over = sum(1 for r in pairs if float(r["confidence"]) >= 0.70 and not r["correct"])
    under = sum(1 for r in pairs if float(r["confidence"]) <= 0.40 and r["correct"])
    return {
        "overconfidence_rate": round(over / len(pairs), 4),
        "underconfidence_rate": round(under / len(pairs), 4),
        "n_overconfident_high_p": over,
        "n_underconfident_low_p": under,
        "n": len(pairs),
    }


def fit_calibration(pairs: list[dict]) -> dict:
    """Fit and freeze using development pairs only."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in pairs:
        by_type[str(row.get("target_type") or "unknown")].append(row)
    models = {}
    for tt, blob in by_type.items():
        table = reliability_table(blob)
        models[tt] = {
            "target_type": tt,
            "n": len(blob),
            "bin_edges": BIN_EDGES,
            "reliability": table,
            "map": [row["smoothed_map"] for row in table],
            "brier": brier_score(blob),
            "ece": expected_calibration_error(table, len(blob)),
            **over_under_rates(blob),
            "fit_split": "development",
            "held_out_used_to_fit": False,
        }
    overall_table = reliability_table(pairs)
    return {
        "kind": "confidence_calibration_v3",
        "fit_split": "development",
        "held_out_used_to_fit": False,
        "llm_generated_confidence": False,
        "n": len(pairs),
        "overall": {
            "reliability": overall_table,
            "brier": brier_score(pairs),
            "ece": expected_calibration_error(overall_table, len(pairs)),
            **over_under_rates(pairs),
        },
        "by_target_type": models,
        "note": "Frozen after development. Apply once to held-out without refitting.",
    }


def apply_calibrated_confidence(raw: float, model: dict, target_type: str | None) -> float:
    by = model.get("by_target_type") or {}
    spec = by.get(target_type or "") or by.get("gene_orthologue") or by.get("unknown")
    if not spec:
        # overall map
        table = (model.get("overall") or {}).get("reliability") or []
        mapping = [row.get("smoothed_map") for row in table]
    else:
        mapping = spec.get("map") or []
    if not mapping:
        return round(max(0.0, min(1.0, raw)), 4)
    idx = _bin_index(raw)
    idx = min(idx, len(mapping) - 1)
    return round(float(mapping[idx]), 4)


def apply_model_to_report(report: dict, model: dict, hidden: HiddenTruth, system: str = "genome_skeptic") -> dict:
    """Return a copy of the report with calibrated confidence and rescoring. Original report is unchanged."""
    calibrated = deepcopy(report)
    for case in calibrated.get("cases") or []:
        truth = hidden.cases.get(case["case_id"]) if hidden.cases else None
        sys_blob = (case.get("systems") or {}).get(system)
        if not sys_blob or truth is None:
            continue
        targets = sys_blob.get("targets") or {}
        for target, expected in truth.targets.items():
            tblob = targets.get(target)
            if not tblob or tblob.get("confidence") is None:
                continue
            raw = float(tblob["confidence"])
            tblob["raw_confidence"] = raw
            tblob["calibrated_confidence"] = apply_calibrated_confidence(raw, model, expected.target_type)
            tblob["confidence"] = tblob["calibrated_confidence"]
        if sys_blob.get("confidence") is not None:
            # top-level case confidence follows first target if present
            first = next(iter(targets.values()), None)
            if first and first.get("calibrated_confidence") is not None:
                sys_blob["raw_confidence"] = sys_blob.get("confidence")
                sys_blob["confidence"] = first["calibrated_confidence"]
                sys_blob["calibrated_confidence"] = first["calibrated_confidence"]
    calibrated["calibration_applied"] = True
    calibrated["calibration_fit_split"] = "development"
    return calibrated
