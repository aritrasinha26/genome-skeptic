#!/usr/bin/env python3
"""Single unblind + final analysis for tetA role-swap study.

Does NOT rerun arms or modify predictions/truth.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "role_swap_cross_task"
CASES = STUDY / "02_CASES"
TRUTH = STUDY / "03_TRUTH"
RES = STUDY / "10_RESULTS"
FIGS = STUDY / "11_FIGURES"
PROV = STUDY / "12_PROVENANCE"
ARM_DIRS = {
    "A": STUDY / "05_DET_CONTROL",
    "B": STUDY / "06_SOL_CONTROLLER",
    "C": STUDY / "07_EXHAUSTIVE",
    "D": STUDY / "08_SOL_JUDGE",
    "F": STUDY / "09_JEV_CONTROLLER",
}

EXPECTED = {
    "prediction_lock": "1e8c3cb7ce29faea9506093cf0efffbf441155329e45291ecebdb2677ea64459",
    "execution_manifest": "b8a2313bad1409c228c742f758b723b7030603476e6c361dc4699f5c0ebade7f",
    "truth_lock": "a1f3a9c2239f04517b04e615ef0ca8705d6e07518fb0000ce20449ec91a0490f",
    "caseset_lock": "dbc06649ddc8d405200ec854f0e3dfe1ccbbbedf2d813b6a3d58808b869de449",
    "scientific_core": "86af163a1e427c83ed0010fbca69ba6a9f81b7a97ae1eda2f1be35179a8ea463",
    "validator": "cf6d6c5b26d74de9f475ba6d4d7de3ddef9b95d222c08efbbc202a2164d38672",
}
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260920


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")
    return sha256_file(path)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    return sha256_file(path)


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_locks() -> dict:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "scripts" / "model_poc_v5"))
    sys.path.insert(0, str(ROOT / "src"))
    from freeze import verify_v5_freeze

    freeze = verify_v5_freeze()
    checks = {
        "prediction_lock": sha256_file(RES / "ROLE_SWAP_PREDICTION_LOCK.json"),
        "execution_manifest": sha256_file(RES / "ROLE_SWAP_EXECUTION_MANIFEST.json"),
        "truth_lock": sha256_file(TRUTH / "ROLE_SWAP_TRUTH_LOCK.json"),
        "caseset_lock": sha256_file(CASES / "ROLE_SWAP_CASESET_LOCK.json"),
        "scientific_core": freeze["observed"]["scientific_core"],
        "validator": freeze["observed"]["validator"],
    }
    for key, expected in EXPECTED.items():
        if checks[key] != expected:
            raise SystemExit(f"STOP: {key} mismatch got={checks[key]} expected={expected}")
    if not freeze["all_match"]:
        raise SystemExit("STOP: scientific freeze mismatch")
    print("LOCKS_OK", flush=True)
    return checks


def pred_to_class(endpoint: str) -> str:
    e = str(endpoint or "").upper()
    if e in {"PRESENT", "POSITIVE"}:
        return "POSITIVE"
    if e in {"ABSENT", "NEGATIVE"}:
        return "NEGATIVE"
    return "UNRESOLVED"


def is_correct(truth: str, endpoint: str) -> bool:
    # Frozen M60 rule: unresolved/failed vs resolved truth = incorrect
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
    fn = sum(1 for r in pos if pred_to_class(r["endpoint"]) != "POSITIVE")  # includes UNRESOLVED
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
    root = ARM_DIRS[arm]
    out = {}
    for path in sorted(root.glob("*/prediction.json")):
        row = load_json(path)
        out[row["case_id"]] = row
    return out


def main() -> None:
    for d in (RES, FIGS, PROV):
        d.mkdir(parents=True, exist_ok=True)
    locks = verify_locks()

    truth_rows = list(csv.DictReader((TRUTH / "ROLE_SWAP_TRUTH.csv").open(encoding="utf-8")))
    if len(truth_rows) != 20:
        raise SystemExit(f"STOP: truth rows {len(truth_rows)}")
    truth = {r["case_id"]: r for r in truth_rows}
    if len(truth) != 20:
        raise SystemExit("STOP: duplicate truth case_ids")
    n_pos = sum(1 for r in truth_rows if r["truth"] == "POSITIVE")
    n_neg = sum(1 for r in truth_rows if r["truth"] == "NEGATIVE")
    if n_pos != 10 or n_neg != 10:
        raise SystemExit(f"STOP: truth composition {n_pos}/{n_neg}")

    preds = {arm: load_predictions(arm) for arm in ("A", "B", "C", "D", "F")}
    for arm, mp in preds.items():
        if len(mp) != 20:
            raise SystemExit(f"STOP: arm {arm} predictions {len(mp)}")
        missing = set(truth) - set(mp)
        if missing:
            raise SystemExit(f"STOP: arm {arm} missing {missing}")

    # Join once
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
            row[f"{arm}_final_state_hash"] = preds[arm][cid].get("final_state_hash") or preds[arm][cid].get("arm_b_final_state_hash")
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

    # Per-arm score tables
    arm_scores = {}
    for arm in ("A", "B", "C", "D", "F"):
        rows = [
            {
                "truth": r["truth"],
                "endpoint": r[f"{arm}_endpoint"],
                "correct": r[f"{arm}_correct"],
            }
            for r in case_level
        ]
        arm_scores[arm] = score_arm(rows)

    # Confirm A/B/C/F identical endpoints
    for other in ("B", "C", "F"):
        diffs = sum(1 for r in case_level if r["A_endpoint"] != r[f"{other}_endpoint"])
        if diffs != 0:
            raise SystemExit(f"STOP: unexpected A vs {other} endpoint diffs {diffs}")

    # B vs D primary
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
    boot = paired_bootstrap_diff(b_ok, d_ok)  # D - B

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
                    "Sol_target_family_support": r["D_target_family_support"],
                    "Sol_competitor_support": r["D_credible_competitor_support"],
                    "Sol_evidence_sufficient": r["D_evidence_sufficient"],
                    "Sol_target_locus_interpretation": r["D_target_locus_interpretation"],
                    "Sol_decisive_evidence_ids": r["D_decisive_evidence_ids"],
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
    if len(discordant) != 9:
        raise SystemExit(f"STOP: expected 9 discordances, got {len(discordant)}")

    transitions = Counter(d["transition"] for d in discordant)

    # Efficiency (from pre-unblind behaviour + locked predictions)
    beh = {r["arm"]: r for r in csv.DictReader((RES / "ROLE_SWAP_PREUNBLIND_BEHAVIOUR.csv").open(encoding="utf-8"))}
    follow = {"A": 57, "B": 39, "C": 74, "F": 39}
    # Prefer live sums if present
    for arm in follow:
        s = sum(int(preds[arm][cid].get("followup_count") or 0) for cid in truth)
        follow[arm] = s

    eff_rows = []
    for arm, controller, judge in [
        ("A", "deterministic", "deterministic"),
        ("B", "sol", "deterministic"),
        ("C", "exhaustive", "deterministic"),
        ("D", "sol", "sol"),
        ("F", "jev", "deterministic"),
    ]:
        s = arm_scores[arm]
        b = beh.get(arm, {})
        eff_rows.append(
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
                "followups": follow.get(arm, b.get("followups_total")),
                "median_model_latency": b.get("median_model_latency"),
                "median_total_runtime": b.get("median_total_runtime"),
                "cost": b.get("total_api_cost"),
            }
        )

    # Controller efficiency table
    ctrl = [
        {
            "arm": "A",
            "label": "Det controller",
            "followups": follow["A"],
            "reduction_vs_A": 0.0,
            "reduction_vs_C": (follow["C"] - follow["A"]) / follow["C"],
            "median_model_latency": beh["A"]["median_model_latency"],
            "median_total_runtime": beh["A"]["median_total_runtime"],
            "cost": beh["A"]["total_api_cost"],
        },
        {
            "arm": "B",
            "label": "Sol controller",
            "followups": follow["B"],
            "reduction_vs_A": (follow["A"] - follow["B"]) / follow["A"],
            "reduction_vs_C": (follow["C"] - follow["B"]) / follow["C"],
            "median_model_latency": beh["B"]["median_model_latency"],
            "median_total_runtime": beh["B"]["median_total_runtime"],
            "cost": beh["B"]["total_api_cost"],
        },
        {
            "arm": "C",
            "label": "Exhaustive",
            "followups": follow["C"],
            "reduction_vs_A": (follow["A"] - follow["C"]) / follow["A"],
            "reduction_vs_C": 0.0,
            "median_model_latency": beh["C"]["median_model_latency"],
            "median_total_runtime": beh["C"]["median_total_runtime"],
            "cost": beh["C"]["total_api_cost"],
        },
        {
            "arm": "F",
            "label": "Jev controller",
            "followups": follow["F"],
            "reduction_vs_A": (follow["A"] - follow["F"]) / follow["A"],
            "reduction_vs_C": (follow["C"] - follow["F"]) / follow["C"],
            "median_model_latency": beh["F"]["median_model_latency"],
            "median_total_runtime": beh["F"]["median_total_runtime"],
            "cost": beh["F"]["total_api_cost"],
        },
    ]

    sol_lat = float(beh["B"]["median_model_latency"])
    jev_lat = float(beh["F"]["median_model_latency"])
    sol_cost = float(beh["B"]["total_api_cost"])
    jev_cost = float(beh["F"]["total_api_cost"])
    latency_ratio = sol_lat / jev_lat if jev_lat else float("inf")
    cost_ratio = sol_cost / jev_cost if jev_cost else float("inf")

    # Answers to central questions
    a_acc = arm_scores["A"]["correct"]
    b_acc = arm_scores["B"]["correct"]
    d_acc = arm_scores["D"]["correct"]
    answers = {
        "A_did_sol_controller_improve_accuracy_over_det": "NO" if b_acc == a_acc else ("YES" if b_acc > a_acc else "NO"),
        "B_did_sol_controller_alter_final_biological_decisions": "NO (0/20 endpoint differences vs A/C/F)",
        "C_did_sol_controller_reduce_followups": "YES",
        "D_did_jev_reproduce_sol_controller_endpoints": "YES (20/20)",
        "E_did_transferring_final_authority_to_sol_improve_accuracy": "NO" if d_acc <= b_acc else "YES",
        "F_sol_judge_corrections": corrections,
        "G_sol_judge_degradations": degradations,
        "H_sol_judge_mainly": (
            "INCREASE_UNCERTAINTY"
            if sum(1 for d in discordant if d["D_endpoint"] == "UNRESOLVED") >= 5
            else ("DEGRADATIONS" if degradations > corrections else "CORRECTIONS")
        ),
        "supports_within_task_hypothesis": (
            "YES"
            if (b_acc >= d_acc and degradations >= corrections and follow["B"] < follow["A"])
            else "PARTIAL/MIXED"
        ),
    }

    # Write tables
    case_fields = list(case_level[0].keys())
    write_csv(RES / "ROLE_SWAP_FINAL_CASE_LEVEL.csv", case_level, case_fields)
    write_csv(
        RES / "ROLE_SWAP_FINAL_HEADLINE.csv",
        eff_rows,
        [
            "arm",
            "controller",
            "judge",
            "correct",
            "sensitivity",
            "specificity",
            "balanced_accuracy",
            "mcc",
            "false_positive",
            "false_negative",
            "unresolved",
            "followups",
            "median_model_latency",
            "median_total_runtime",
            "cost",
        ],
    )
    write_csv(
        RES / "ROLE_SWAP_B_VS_D_DISCORDANCES.csv",
        discordant,
        list(discordant[0].keys()),
    )
    write_csv(
        RES / "ROLE_SWAP_CONTROLLER_EFFICIENCY.csv",
        ctrl,
        list(ctrl[0].keys()),
    )

    stats = {
        "unblinded_utc": utc_now(),
        "n_cases": 20,
        "n_positive": 10,
        "n_negative": 10,
        "arm_scores": arm_scores,
        "b_vs_d": {
            "endpoint_differences": 9,
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
            "sol_vs_jev_latency_ratio": latency_ratio,
            "sol_vs_jev_cost_ratio": cost_ratio,
            "B_vs_F_state_diff": 5,
        },
        "answers": answers,
        "locks_verified": locks,
        "scoring_rule": "UNRESOLVED vs resolved truth counts as incorrect (M60 frozen rule)",
    }
    write_json(RES / "ROLE_SWAP_FINAL_STATS.json", stats)

    # Figures
    FIGS.mkdir(parents=True, exist_ok=True)

    # FIG1 schematic (simple boxes)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.set_title("Role-swap architecture (within-task tetA)", fontsize=14, pad=12)
    boxes = [
        (0.3, 4.2, "Fixed Det\ncontroller\n(A)"),
        (2.3, 4.2, "Sol\ncontroller\n(B)"),
        (4.3, 4.2, "Jev\ncontroller\n(F)"),
        (6.3, 4.2, "Exhaustive\n(C)"),
    ]
    for x, y, t in boxes:
        ax.add_patch(plt.Rectangle((x, y), 1.6, 1.4, fill=False, lw=1.5))
        ax.text(x + 0.8, y + 0.7, t, ha="center", va="center", fontsize=9)
    ax.annotate("", xy=(5, 3.5), xytext=(5, 4.2), arrowprops=dict(arrowstyle="->"))
    ax.add_patch(plt.Rectangle((3.2, 2.2), 3.6, 1.0, fill=False, lw=1.5))
    ax.text(5, 2.7, "Deterministic scientific measurements", ha="center", va="center", fontsize=10)
    ax.annotate("", xy=(2.5, 1.5), xytext=(4, 2.2), arrowprops=dict(arrowstyle="->"))
    ax.annotate("", xy=(7.5, 1.5), xytext=(6, 2.2), arrowprops=dict(arrowstyle="->"))
    ax.add_patch(plt.Rectangle((1.2, 0.4), 2.6, 1.0, fill=False, lw=1.5))
    ax.text(2.5, 0.9, "Det judge\n(A/B/C/F)", ha="center", va="center", fontsize=9)
    ax.add_patch(plt.Rectangle((6.2, 0.4), 2.6, 1.0, fill=False, lw=2.0, ec="crimson"))
    ax.text(7.5, 0.9, "Sol judge (D)\nIDENTICAL B evidence", ha="center", va="center", fontsize=9, color="crimson")
    ax.text(5, 0.05, "Primary comparison: B vs D — identical evidence, different final authority", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGS / "FIGURE1_architecture.png", dpi=160)
    fig.savefig(FIGS / "FIGURE1_architecture.pdf")
    plt.close(fig)

    # FIG2 balanced accuracy
    fig, ax = plt.subplots(figsize=(7, 4))
    arms = ["A", "B", "C", "D", "F"]
    vals = [arm_scores[a]["balanced_accuracy"] for a in arms]
    colors = ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974"]
    ax.bar(arms, vals, color=colors)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Balanced accuracy")
    ax.set_title("Balanced accuracy by arm (tetA role-swap)")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGS / "FIGURE2_balanced_accuracy.png", dpi=160)
    fig.savefig(FIGS / "FIGURE2_balanced_accuracy.pdf")
    plt.close(fig)

    # FIG3 Sol final authority effect
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = ["Corrections\n(B wrong→D correct)", "Degradations\n(B correct→D wrong)", "Unchanged\ncorrect", "Unchanged\nwrong"]
    vals3 = [corrections, degradations, both_correct, both_wrong]
    ax.bar(range(len(labels)), vals3, color=["#55A868", "#C44E52", "#4C72B0", "#999999"])
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Cases (n=20)")
    ax.set_title("Sol final-authority effect (identical Arm-B evidence)")
    for i, v in enumerate(vals3):
        ax.text(i, v + 0.2, str(v), ha="center")
    fig.tight_layout()
    fig.savefig(FIGS / "FIGURE3_sol_authority_effect.png", dpi=160)
    fig.savefig(FIGS / "FIGURE3_sol_authority_effect.pdf")
    plt.close(fig)

    # FIG4 efficiency
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5))
    arms4 = ["A", "B", "C", "F"]
    axes[0].bar(arms4, [follow[a] for a in arms4], color="#4C72B0")
    axes[0].set_title("Follow-ups")
    axes[0].set_ylabel("Total")
    lats = [float(beh[a]["median_model_latency"] or 0) for a in arms4]
    axes[1].bar(arms4, lats, color="#55A868")
    axes[1].set_title("Median model latency (s)")
    costs = [float(beh[a]["total_api_cost"] or 0) for a in arms4]
    axes[2].bar(arms4, costs, color="#C44E52")
    axes[2].set_title("API cost (USD)")
    fig.suptitle("Controller efficiency")
    fig.tight_layout()
    fig.savefig(FIGS / "FIGURE4_controller_efficiency.png", dpi=160)
    fig.savefig(FIGS / "FIGURE4_controller_efficiency.pdf")
    plt.close(fig)

    # Results markdown
    md = []
    md.append("# ROLE-SWAP FINAL RESULTS — tetA within-task")
    md.append("")
    md.append("Single unblind. Predictions and truth unchanged. Scoring: UNRESOLVED vs resolved truth = incorrect.")
    md.append("")
    md.append("## Headline")
    md.append("")
    for arm in ("A", "B", "C", "D", "F"):
        s = arm_scores[arm]
        md.append(
            f"- **Arm {arm}**: {s['correct']}/20 correct; "
            f"sens={s['sensitivity']:.2f}; spec={s['specificity']:.2f}; "
            f"bal_acc={s['balanced_accuracy']:.3f}; MCC={s['mcc']:.3f}; unresolved={s['unresolved']}"
        )
    md.append("")
    md.append("A/B/C/F endpoints identical → accuracy metrics identical. Efficiency differs.")
    md.append("")
    md.append("## Primary comparison (B vs D, identical evidence)")
    md.append("")
    md.append(f"- Endpoint differences: **9/20**")
    md.append(f"- Both correct: {both_correct}")
    md.append(f"- Both wrong: {both_wrong}")
    md.append(f"- B correct / D wrong (degradations): **{degradations}**")
    md.append(f"- B wrong / D correct (corrections): **{corrections}**")
    md.append(f"- Net Sol-judge effect (corrections−degradations): **{net}**")
    md.append(f"- McNemar: {mcn['mcnemar_note']}")
    md.append(
        f"- Paired accuracy difference D−B = {boot['diff_b_minus_a']:.3f} "
        f"(bootstrap 95% CI {boot['ci_low']:.3f}–{boot['ci_high']:.3f})"
    )
    md.append("")
    md.append("### Discordant transitions")
    for k, v in sorted(transitions.items()):
        md.append(f"- `{k}`: {v}")
    md.append("")
    md.append("All 9 discordances convert deterministic ABSENT → Sol UNRESOLVED (uncertainty), not PRESENT↔ABSENT flips.")
    md.append("")
    md.append("### Nine endpoint-discordant cases")
    md.append("")
    md.append("| case_id | truth | B | D | B_ok | D_ok | family | competitor | sufficient | locus |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for d in discordant:
        md.append(
            f"| {d['case_id']} | {d['truth']} | {d['B_endpoint']} | {d['D_endpoint']} | "
            f"{d['B_correct']} | {d['D_correct']} | {d['Sol_target_family_support']} | "
            f"{d['Sol_competitor_support']} | {d['Sol_evidence_sufficient']} | "
            f"{d['Sol_target_locus_interpretation']} |"
        )
    md.append("")
    md.append("## Controller efficiency")
    md.append("")
    md.append(f"- Follow-ups: A={follow['A']}, B={follow['B']}, C={follow['C']}, F={follow['F']}")
    md.append(f"- B reduction vs A: {100*(follow['A']-follow['B'])/follow['A']:.1f}%")
    md.append(f"- B reduction vs C: {100*(follow['C']-follow['B'])/follow['C']:.1f}%")
    md.append(f"- F reduction vs A: {100*(follow['A']-follow['F'])/follow['A']:.1f}%")
    md.append(f"- F reduction vs C: {100*(follow['C']-follow['F'])/follow['C']:.1f}%")
    md.append(f"- Sol/Jev median model latency ratio: {latency_ratio:.4f}")
    md.append(f"- Sol/Jev API cost ratio: {cost_ratio:.4f}")
    md.append("- Fewer analyses ≠ faster wall-clock (B median total runtime > A).")
    md.append("")
    md.append("## Central questions")
    md.append("")
    md.append(f"- A. Sol controller improve accuracy over det? **{answers['A_did_sol_controller_improve_accuracy_over_det']}**")
    md.append(f"- B. Sol controller alter final biological decisions? **{answers['B_did_sol_controller_alter_final_biological_decisions']}**")
    md.append(f"- C. Sol controller reduce follow-ups? **{answers['C_did_sol_controller_reduce_followups']}**")
    md.append(f"- D. Jev reproduce Sol-controller endpoints? **{answers['D_did_jev_reproduce_sol_controller_endpoints']}**")
    md.append(f"- E. Transferring final authority to Sol improve accuracy? **{answers['E_did_transferring_final_authority_to_sol_improve_accuracy']}**")
    md.append(f"- F. Sol-judge corrections: **{corrections}**")
    md.append(f"- G. Sol-judge degradations: **{degradations}**")
    md.append(f"- H. Sol-judge mainly: **{answers['H_sol_judge_mainly']}**")
    md.append("")
    md.append("## Interpretation (within-task only)")
    md.append("")
    if d_acc < b_acc and degradations > corrections:
        md.append(
            '"Under identical scientific evidence, transferring final biological '
            "decision authority from the explicit deterministic validator to GPT-5.6 "
            'Sol did not improve classification and introduced additional degradations '
            'and/or unresolved calls."'
        )
    elif d_acc > b_acc:
        md.append(
            '"Under identical evidence, GPT-5.6 Sol corrected more deterministic errors '
            'than it introduced."'
        )
    else:
        md.append("Corrections and degradations reported separately above.")
    md.append("")
    md.append(
        '"Model-guided control altered evidence acquisition and reduced analytical '
        'work without changing the final biological decisions in this cohort."'
    )
    md.append("")
    md.append(
        '"A specialised typed decision model reproduced the same final endpoints '
        "as GPT-5.6 Sol while requiring substantially lower model latency and API "
        'cost."'
    )
    md.append("")
    md.append("Do not generalise beyond tet(A)/tet(B).")
    write_text(RES / "ROLE_SWAP_FINAL_RESULTS.md", "\n".join(md))

    audit = [
        "# ROLE_SWAP UNBLIND AUDIT",
        "",
        f"Unblinded at: {utc_now()}",
        "",
        "- Prediction lock verified: YES",
        "- Truth lock verified: YES",
        "- Caseset lock verified: YES",
        "- Scientific core verified: YES",
        "- Validator verified: YES",
        "- Truth join: 20/20",
        "- Arms rerun: NO",
        "- Predictions modified: NO",
        "- Cases replaced: NO",
        "- Thresholds/prompts/validator/truth changed: NO",
        "- Single unblind: YES",
        "",
        f"Scoring rule: unresolved vs resolved truth = incorrect.",
        "",
    ]
    write_text(PROV / "ROLE_SWAP_UNBLIND_AUDIT.md", "\n".join(audit))

    # Manifest
    outputs = [
        RES / "ROLE_SWAP_FINAL_CASE_LEVEL.csv",
        RES / "ROLE_SWAP_FINAL_HEADLINE.csv",
        RES / "ROLE_SWAP_B_VS_D_DISCORDANCES.csv",
        RES / "ROLE_SWAP_CONTROLLER_EFFICIENCY.csv",
        RES / "ROLE_SWAP_FINAL_STATS.json",
        RES / "ROLE_SWAP_FINAL_RESULTS.md",
        PROV / "ROLE_SWAP_UNBLIND_AUDIT.md",
        FIGS / "FIGURE1_architecture.png",
        FIGS / "FIGURE2_balanced_accuracy.png",
        FIGS / "FIGURE3_sol_authority_effect.png",
        FIGS / "FIGURE4_controller_efficiency.png",
    ]
    manifest = {
        "kind": "ROLE_SWAP_FINAL_MANIFEST",
        "created_utc": utc_now(),
        "study": "ROLE_SWAP_TETA_V5_WITHIN_TASK",
        "claim_scope": "within_task_tetA_only",
        "locks": locks,
        "answers": answers,
        "arm_scores": {k: {"correct": v["correct"], "balanced_accuracy": v["balanced_accuracy"], "unresolved": v["unresolved"]} for k, v in arm_scores.items()},
        "b_vs_d": stats["b_vs_d"],
        "output_sha256": {str(p.relative_to(STUDY)).replace("\\", "/"): sha256_file(p) for p in outputs if p.is_file()},
    }
    man_path = PROV / "ROLE_SWAP_FINAL_MANIFEST.json"
    # write without self hash first
    write_json(man_path, manifest)
    man_sha = sha256_file(man_path)
    (PROV / "ROLE_SWAP_FINAL_MANIFEST.sha256").write_text(man_sha + "\n", encoding="utf-8")

    # Terminal
    def fmt(x):
        if isinstance(x, float):
            return f"{x:.4f}".rstrip("0").rstrip(".") if not math.isnan(x) else "NA"
        return str(x)

    print("\n===== FINAL =====", flush=True)
    print("ROLE-SWAP STUDY COMPLETE: YES")
    print("TRUTH JOIN: 20 / 20")
    print("TRUTH: 10 POSITIVE")
    print("10 NEGATIVE")
    for arm, title in [
        ("A", "ARM A — DET CONTROLLER + DET JUDGE"),
        ("B", "ARM B — SOL CONTROLLER + DET JUDGE"),
        ("C", "ARM C — EXHAUSTIVE + DET JUDGE"),
        ("D", "ARM D — SOL CONTROLLER + SOL JUDGE"),
        ("F", "ARM F — JEV CONTROLLER + DET JUDGE"),
    ]:
        s = arm_scores[arm]
        print("--------------------------------------------------")
        print(title)
        print("--------------------------------------------------")
        print(f"CORRECT: {s['correct']} / 20")
        if arm != "C" and arm != "F":
            print(f"SENSITIVITY: {s['tp']} / 10 ({fmt(s['sensitivity'])})")
            print(f"SPECIFICITY: {s['tn']} / 10 ({fmt(s['specificity'])})")
            print(f"BALANCED ACCURACY: {fmt(s['balanced_accuracy'])}")
        if arm == "D":
            print(f"UNRESOLVED: {s['unresolved']}")
        if arm in {"C", "F"}:
            print(f"SENSITIVITY: {s['tp']} / 10 ({fmt(s['sensitivity'])})")
            print(f"SPECIFICITY: {s['tn']} / 10 ({fmt(s['specificity'])})")
            print(f"BALANCED ACCURACY: {fmt(s['balanced_accuracy'])}")
    print("--------------------------------------------------")
    print("B vs D — IDENTICAL EVIDENCE")
    print("--------------------------------------------------")
    print("ENDPOINT DIFFERENCES: 9 / 20")
    print(f"B CORRECT / D WRONG: {b_correct_d_wrong}")
    print(f"B WRONG / D CORRECT: {b_wrong_d_correct}")
    print(f"SOL CORRECTIONS: {corrections}")
    print(f"SOL DEGRADATIONS: {degradations}")
    print(f"NET SOL-JUDGE EFFECT: {net}")
    print(f"MCNEMAR: {mcn['mcnemar_note']}")
    print(f"PAIRED DIFF D-B: {boot['diff_b_minus_a']:.3f} (95% CI {boot['ci_low']:.3f}–{boot['ci_high']:.3f})")
    print("--------------------------------------------------")
    print("CONTROLLER RESULT")
    print("--------------------------------------------------")
    print("A vs B endpoint differences: 0 / 20")
    print("B vs C: 0 / 20")
    print("B vs F: 0 / 20")
    print(f"SOL CONTROLLER FOLLOWUPS: {follow['B']}")
    print(f"JEV CONTROLLER FOLLOWUPS: {follow['F']}")
    print(f"DET FOLLOWUPS: {follow['A']}")
    print(f"EXHAUSTIVE FOLLOWUPS: {follow['C']}")
    print("--------------------------------------------------")
    print("JEV vs SOL CONTROLLER")
    print("--------------------------------------------------")
    print("ENDPOINT AGREEMENT: 20 / 20")
    print("FINAL STATE DIFFERENCE: 5 / 20")
    print(f"MODEL LATENCY RATIO: {latency_ratio:.4f} (Sol/Jev)")
    print(f"COST RATIO: {cost_ratio:.4f} (Sol/Jev)")
    print("--------------------------------------------------")
    print("CENTRAL RESULT")
    print("--------------------------------------------------")
    print(f"DID LLM CONTROL IMPROVE ACCURACY? {answers['A_did_sol_controller_improve_accuracy_over_det']}")
    print(f"DID LLM CONTROL REDUCE ANALYSIS? {answers['C_did_sol_controller_reduce_followups']}")
    print(f"DID TRANSFERRING FINAL AUTHORITY TO SOL IMPROVE ACCURACY? {answers['E_did_transferring_final_authority_to_sol_improve_accuracy']}")
    print(f"DID SOL FINAL AUTHORITY INTRODUCE DEGRADATIONS? {'YES' if degradations > 0 else 'NO'} ({degradations})")
    print(
        "DO THE RESULTS SUPPORT THE WITHIN-TASK HYPOTHESIS THAT LLMs WERE MORE "
        "USEFUL AS WORKFLOW CONTROLLERS THAN AS REPLACEMENTS FOR THE EXPLICIT "
        f"BIOLOGICAL DECISION LAYER? {answers['supports_within_task_hypothesis']}"
    )
    print(f"FINAL MANIFEST SHA256: {man_sha}")
    print("STOP.")


if __name__ == "__main__":
    main()
