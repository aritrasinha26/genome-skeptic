#!/usr/bin/env python3
"""Shared helpers for paper_role_swap locked-output reproduction.

Calculation logic copied from:
  paper_role_swap/scripts/scoring/score_role_swap_unblind.py
  (itself the historical role_swap_cross_task unblind scorer)

Paths resolve relative to paper_role_swap/ only. No API calls.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

BUNDLE = Path(__file__).resolve().parents[2]
DATA = BUNDLE / "data"
RESULTS = BUNDLE / "results"
PROTOCOL = BUNDLE / "protocol"
REPRODUCED = BUNDLE / "reproduced"

BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260920  # from score_role_swap_unblind.py


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in fields})


def pred_to_class(endpoint: str) -> str:
    e = str(endpoint or "").upper()
    if e in {"PRESENT", "POSITIVE"}:
        return "POSITIVE"
    if e in {"ABSENT", "NEGATIVE"}:
        return "NEGATIVE"
    return "UNRESOLVED"


def is_correct(truth: str, endpoint: str) -> bool:
    pc = pred_to_class(endpoint)
    if pc == "UNRESOLVED":
        return False
    return pc == truth


def mcc(tp: int, tn: int, fp: int, fn: int) -> float:
    num = tp * tn - fp * fn
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if den == 0:
        return 0.0
    return num / den


def score_arm(rows: list[dict]) -> dict:
    n = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    pos = [r for r in rows if r["truth"] == "POSITIVE"]
    neg = [r for r in rows if r["truth"] == "NEGATIVE"]
    tp = sum(1 for r in pos if pred_to_class(r["endpoint"]) == "POSITIVE")
    fn = sum(1 for r in pos if pred_to_class(r["endpoint"]) != "POSITIVE")
    tn = sum(1 for r in neg if pred_to_class(r["endpoint"]) == "NEGATIVE")
    fp = sum(1 for r in neg if pred_to_class(r["endpoint"]) != "NEGATIVE")
    unresolved = sum(1 for r in rows if pred_to_class(r["endpoint"]) == "UNRESOLVED")
    sens = tp / len(pos) if pos else float("nan")
    spec = tn / len(neg) if neg else float("nan")
    bal = (sens + spec) / 2 if pos and neg else float("nan")
    return {
        "n": n,
        "correct": correct,
        "accuracy": correct / n,
        "n_pos": len(pos),
        "n_neg": len(neg),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "sensitivity": sens,
        "specificity": spec,
        "balanced_accuracy": bal,
        "mcc": mcc(tp, tn, fp, fn),
        "unresolved": unresolved,
        "false_positive": fp,
        "false_negative": fn,
    }


def mcnemar_exact(b_ok: list[bool], d_ok: list[bool]) -> dict:
    b_only = sum(1 for a, b in zip(b_ok, d_ok) if a and not b)
    d_only = sum(1 for a, b in zip(b_ok, d_ok) if (not a) and b)
    n = b_only + d_only
    if n == 0:
        return {
            "b_correct_d_wrong": b_only,
            "b_wrong_d_correct": d_only,
            "mcnemar_p": None,
            "mcnemar_note": "McNemar not applicable (B+C = 0)",
        }
    p = float(binomtest(d_only, n=n, p=0.5, alternative="two-sided").pvalue)
    return {
        "b_correct_d_wrong": b_only,
        "b_wrong_d_correct": d_only,
        "mcnemar_p": p,
        "mcnemar_note": f"exact two-sided McNemar / binomial P={p:.6g} on B+C={n}",
    }


def paired_bootstrap_diff(a_ok: list[bool], b_ok: list[bool]) -> dict:
    """Paired bootstrap of mean(b) - mean(a). Seed/N from score_role_swap_unblind.py."""
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    a = np.asarray(a_ok, dtype=float)
    b = np.asarray(b_ok, dtype=float)
    n = len(a)
    obs = float(b.mean() - a.mean())
    diffs = []
    for _ in range(BOOTSTRAP_N):
        idx = rng.integers(0, n, size=n)
        diffs.append(float(b[idx].mean() - a[idx].mean()))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {
        "diff_b_minus_a": obs,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "n_bootstrap": BOOTSTRAP_N,
        "seed": BOOTSTRAP_SEED,
    }


def load_predictions(arm: str) -> dict[str, dict]:
    root = DATA / "locked_predictions" / arm
    out = {}
    for path in sorted(root.glob("RS*_prediction.json")):
        row = load_json(path)
        out[row["case_id"]] = row
    return out


def load_truth() -> dict[str, dict]:
    rows = list(csv.DictReader((DATA / "prospective_truth.csv").open(encoding="utf-8")))
    return {r["case_id"]: r for r in rows}


def load_behaviour() -> dict[str, dict]:
    rows = list(csv.DictReader((RESULTS / "preunblind_behaviour.csv").open(encoding="utf-8")))
    return {r["arm"]: r for r in rows}


def build_case_level(truth: dict[str, dict], preds: dict[str, dict[str, dict]]) -> list[dict]:
    case_level = []
    for cid in sorted(truth):
        t = truth[cid]["truth"]
        row = {
            "case_id": cid,
            "accession": truth[cid]["accession"],
            "truth": t,
        }
        for arm in ("A", "B", "C", "D", "F"):
            ep = preds[arm][cid].get("endpoint")
            row[f"{arm}_endpoint"] = ep
            row[f"{arm}_correct"] = is_correct(t, ep)
            row[f"{arm}_followup_count"] = preds[arm][cid].get("followup_count")
            row[f"{arm}_final_state_hash"] = preds[arm][cid].get("final_state_hash") or preds[arm][
                cid
            ].get("arm_b_final_state_hash")
        d = preds["D"][cid]
        row.update(
            {
                "D_target_family_support": d.get("target_family_support"),
                "D_credible_competitor_support": d.get("credible_competitor_support"),
                "D_evidence_sufficient": d.get("evidence_sufficient"),
                "D_target_locus_interpretation": d.get("target_locus_interpretation"),
                "D_decisive_evidence_ids": "|".join(d.get("decisive_evidence_ids") or []),
                "D_invalid_evidence_ids": "|".join(d.get("invalid_evidence_ids") or []),
                "B_vs_D_endpoint_same": preds["B"][cid].get("endpoint") == d.get("endpoint"),
                "identical_evidence_B_D": bool(d.get("identical_evidence_assert")),
            }
        )
        case_level.append(row)
    return case_level


def compute_statistics() -> dict:
    """Recompute final stats from locked predictions + truth + pre-unblind behaviour."""
    truth = load_truth()
    if len(truth) != 20:
        raise SystemExit(f"STOP: truth cases {len(truth)}")
    n_pos = sum(1 for r in truth.values() if r["truth"] == "POSITIVE")
    n_neg = sum(1 for r in truth.values() if r["truth"] == "NEGATIVE")
    if n_pos != 10 or n_neg != 10:
        raise SystemExit(f"STOP: truth composition {n_pos}/{n_neg}")

    preds = {arm: load_predictions(arm) for arm in ("A", "B", "C", "D", "F")}
    for arm, mp in preds.items():
        if len(mp) != 20:
            raise SystemExit(f"STOP: arm {arm} predictions {len(mp)}")

    case_level = build_case_level(truth, preds)
    arm_scores = {}
    for arm in ("A", "B", "C", "D", "F"):
        rows = [
            {"truth": r["truth"], "endpoint": r[f"{arm}_endpoint"], "correct": r[f"{arm}_correct"]}
            for r in case_level
        ]
        arm_scores[arm] = score_arm(rows)

    for other in ("B", "C", "F"):
        diffs = sum(1 for r in case_level if r["A_endpoint"] != r[f"{other}_endpoint"])
        if diffs != 0:
            raise SystemExit(f"STOP: unexpected A vs {other} endpoint diffs {diffs}")

    b_ok = [r["B_correct"] for r in case_level]
    d_ok = [r["D_correct"] for r in case_level]
    both_correct = sum(1 for a, b in zip(b_ok, d_ok) if a and b)
    both_wrong = sum(1 for a, b in zip(b_ok, d_ok) if (not a) and (not b))
    b_correct_d_wrong = sum(1 for a, b in zip(b_ok, d_ok) if a and not b)
    b_wrong_d_correct = sum(1 for a, b in zip(b_ok, d_ok) if (not a) and b)
    corrections = b_wrong_d_correct
    degradations = b_correct_d_wrong
    net = corrections - degradations
    mcn = mcnemar_exact(b_ok, d_ok)
    boot = paired_bootstrap_diff(b_ok, d_ok)

    discordant = []
    for r in case_level:
        if r["B_endpoint"] != r["D_endpoint"]:
            discordant.append(
                {
                    "case_id": r["case_id"],
                    "accession": r["accession"],
                    "truth": r["truth"],
                    "B_endpoint": r["B_endpoint"],
                    "D_endpoint": r["D_endpoint"],
                    "B_correct": r["B_correct"],
                    "D_correct": r["D_correct"],
                    "transition": f"{r['B_endpoint']}->{r['D_endpoint']}",
                    "effect": (
                        "CORRECTION"
                        if (not r["B_correct"] and r["D_correct"])
                        else (
                            "DEGRADATION"
                            if (r["B_correct"] and not r["D_correct"])
                            else "NEITHER_OR_BOTH_WRONG"
                        )
                    ),
                }
            )
    transitions = Counter(d["transition"] for d in discordant)

    follow = {}
    for arm in ("A", "B", "C", "F"):
        follow[arm] = sum(int(preds[arm][cid].get("followup_count") or 0) for cid in truth)

    beh = load_behaviour()
    sol_lat = float(beh["B"]["median_model_latency"])
    jev_lat = float(beh["F"]["median_model_latency"])
    sol_cost = float(beh["B"]["total_api_cost"])
    jev_cost = float(beh["F"]["total_api_cost"])

    identical = sum(1 for r in case_level if r["identical_evidence_B_D"])
    # Also verify via Arm B locked evidence hashes vs D input
    hash_rows = list(csv.DictReader((DATA / "arm_b_vs_d_evidence_hashes.csv").open(encoding="utf-8")))
    hash_ok = sum(1 for r in hash_rows if r["hashes_equal"] == "True")

    ctrl = []
    for arm, label in [
        ("A", "Det controller"),
        ("B", "Sol controller"),
        ("C", "Exhaustive"),
        ("F", "Jev controller"),
    ]:
        ctrl.append(
            {
                "arm": arm,
                "label": label,
                "followups": follow[arm],
                "reduction_vs_A": 0.0 if arm == "A" else (follow["A"] - follow[arm]) / follow["A"],
                "reduction_vs_C": 0.0 if arm == "C" else (follow["C"] - follow[arm]) / follow["C"],
                "median_model_latency": float(beh[arm]["median_model_latency"]),
                "median_total_runtime": float(beh[arm]["median_total_runtime"]),
                "cost": float(beh[arm]["total_api_cost"]),
            }
        )

    headline = []
    for arm, controller, judge in [
        ("A", "deterministic", "deterministic"),
        ("B", "sol", "deterministic"),
        ("C", "exhaustive", "deterministic"),
        ("D", "sol", "sol"),
        ("F", "jev", "deterministic"),
    ]:
        s = arm_scores[arm]
        b = beh[arm]
        headline.append(
            {
                "arm": arm,
                "controller": controller,
                "judge": judge,
                "correct": s["correct"],
                "sensitivity": s["sensitivity"],
                "specificity": s["specificity"],
                "balanced_accuracy": s["balanced_accuracy"],
                "mcc": s["mcc"],
                "false_positive": s["false_positive"],
                "false_negative": s["false_negative"],
                "unresolved": s["unresolved"],
                "followups": follow.get(arm, int(float(b["followups_total"]))),
                "median_model_latency": float(b["median_model_latency"] or 0),
                "median_total_runtime": float(b["median_total_runtime"] or 0),
                "cost": float(b["total_api_cost"] or 0),
            }
        )

    stats = {
        "unblinded_utc": utc_now(),
        "n_cases": 20,
        "n_positive": 10,
        "n_negative": 10,
        "arm_scores": arm_scores,
        "b_vs_d": {
            "endpoint_differences": len(discordant),
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "b_correct_d_wrong": b_correct_d_wrong,
            "b_wrong_d_correct": b_wrong_d_correct,
            "sol_corrections": corrections,
            "sol_degradations": degradations,
            "net_sol_judge_effect": net,
            "mcnemar": mcn,
            "paired_bootstrap_D_minus_B": boot,
            "transitions": dict(transitions),
        },
        "controller": {
            "A_vs_B_endpoint_diff": 0,
            "B_vs_C_endpoint_diff": 0,
            "B_vs_F_endpoint_diff": 0,
            "followups": follow,
            "B_reduction_vs_A": (follow["A"] - follow["B"]) / follow["A"],
            "B_reduction_vs_C": (follow["C"] - follow["B"]) / follow["C"],
            "F_reduction_vs_A": (follow["A"] - follow["F"]) / follow["A"],
            "F_reduction_vs_C": (follow["C"] - follow["F"]) / follow["C"],
            "sol_vs_jev_latency_ratio": sol_lat / jev_lat if jev_lat else float("inf"),
            "sol_vs_jev_cost_ratio": sol_cost / jev_cost if jev_cost else float("inf"),
        },
        "evidence_identity": {
            "identical_evidence_assert_count": identical,
            "arm_b_vs_d_hash_equal_count": hash_ok,
        },
        "scoring_rule": "UNRESOLVED vs resolved truth counts as incorrect (M60 frozen rule)",
        "source_logic": "paper_role_swap/scripts/scoring/score_role_swap_unblind.py",
    }
    return {
        "stats": stats,
        "case_level": case_level,
        "discordant": discordant,
        "controller_efficiency": ctrl,
        "headline": headline,
        "followups": follow,
        "arm_scores": arm_scores,
        "corrections": corrections,
        "degradations": degradations,
        "both_correct": both_correct,
        "both_wrong": both_wrong,
        "beh": beh,
    }
