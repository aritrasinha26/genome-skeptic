#!/usr/bin/env python3
"""M60 Phase 4: one-shot final unblind and pre-registered scoring.

Does not modify predictions, truth, thresholds, V4.1, or D20.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MB = ROOT / "manuscript_benchmark"
OUT = MB / "RESULTS_M60"
TRUTH_ROOT = MB / "TRUTH_M60"

EXPECTED = {
    "system_manifest": "97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b",
    "scientific_core": "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0",
    "protocol_v11": "73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660",
    "cohort": "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655",
    "prediction_lock": "5317b33fa554f81855fa6c68854ad732c5f5127fc0ad41f224fede9159a90791",
    "final_truth": "a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9",
    "final_truth_lock": "787f7a96224c2c61b21a8747bc9e9e46025b126e4b9d0f5b9dd38b4b89f54eb4",
    "git": "8f66868850a98494778966bd729b88a6fc2952eb",
}

BOOTSTRAP_SEED = 20260920
BOOTSTRAP_N = 10000
SYSTEMS = ("conventional", "specialist", "gs_det", "gs_agent", "gs_exh")
SYSTEM_LABELS = {
    "conventional": "Conventional",
    "specialist": "Specialist comparator",
    "gs_det": "GS-Deterministic V4.1",
    "gs_agent": "GS-Agentic V4.1",
    "gs_exh": "GS-Exhaustive V4.1",
}
COLORS = {
    "conventional": "#0072B2",
    "specialist": "#E69F00",
    "gs_det": "#009E73",
    "gs_agent": "#D55E00",
    "gs_exh": "#56B4E9",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")
    return sha256_file(path)


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    if fields is None:
        fields = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / den
    margin = (z / den) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def iqr(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return (float("nan"), float("nan"), float("nan"))
    q1, q2, q3 = np.percentile(values, [25, 50, 75])
    return (float(q1), float(q2), float(q3))


def as_list(value) -> list:
    if value is None or value is False:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        if "action_id" in value:
            return [value]
        return [json.dumps(value, sort_keys=True)]
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return []
    return [text]


def needs_label(value) -> str:
    items = as_list(value)
    names = []
    for item in items:
        if isinstance(item, dict):
            names.append(str(item.get("need") or item.get("id") or item))
        else:
            names.append(str(item))
    return ";".join(names)


def gs_binary(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("completion_status") not in {None, "complete"}:
        if rec.get("completion_status") == "complete":
            pass
        elif rec.get("ok") is False or rec.get("completion_status") in {"failed", "error"}:
            return "UNRESOLVED"
    fr = rec.get("final_result") or rec.get("binary_call")
    if fr == "target_gene_detected" or fr == "POSITIVE":
        return "POSITIVE"
    if fr == "target_gene_not_detected" or fr == "NEGATIVE":
        return "NEGATIVE"
    if fr in {"POSITIVE", "NEGATIVE"}:
        return fr
    return "UNRESOLVED"


def conventional_binary(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("completion_status") in {"failed", "error"}:
        return "UNRESOLVED"
    return gs_binary(rec)


def specialist_binary(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("completion_status") in {"failed", "error"}:
        return "UNRESOLVED"
    call = rec.get("binary_call")
    if call in {"POSITIVE", "NEGATIVE"}:
        return call
    if call in {"UNCERTAIN", "UNRESOLVED", None, ""}:
        return "UNRESOLVED"
    return "UNRESOLVED"


def is_complete(rec: dict) -> bool:
    return rec.get("completion_status") == "complete"


def is_correct(truth: str, pred: str) -> bool | None:
    if truth == "TRUTH_UNCERTAIN":
        return None
    if truth in {"POSITIVE", "NEGATIVE"}:
        return pred == truth
    return None


def followups(rec: dict) -> int:
    integ = rec.get("integrity") or {}
    if integ.get("n_deterministic_followup_analyses") is not None:
        try:
            return int(integ["n_deterministic_followup_analyses"])
        except (TypeError, ValueError):
            pass
    acts = rec.get("actions_executed") or []
    if isinstance(acts, list):
        return len(acts)
    return 0


def action_status_counts(rec: dict) -> Counter:
    counts: Counter = Counter()
    for item in as_list(rec.get("action_results")):
        if isinstance(item, dict):
            status = str(item.get("status") or "UNKNOWN").upper()
        else:
            status = str(item).upper()
        if status in {"INFORMATIVE", "NO_NEW_INFORMATION", "UNAVAILABLE", "FAILED"}:
            counts[status] += 1
        elif "NO_NEW" in status:
            counts["NO_NEW_INFORMATION"] += 1
        else:
            counts[status] += 1
    return counts


def verify_locks() -> dict:
    from genome_skeptic.manuscript.scientific_core import scientific_core_hashes

    rows = {}

    def check(name: str, path: Path, expected: str, *, lf: bool = False) -> str:
        raw = sha256_file(path)
        got = raw
        if lf:
            got_lf = sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
            ok = raw == expected or got_lf == expected
            got = raw if raw == expected else got_lf
        else:
            ok = raw == expected
        rows[name] = {"path": str(path), "sha256": got, "expected": expected, "ok": ok}
        if not ok:
            raise SystemExit(f"HASH MISMATCH {name}: got={raw} expected={expected}")
        return got

    check("system_manifest", MB / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json", EXPECTED["system_manifest"])
    core = scientific_core_hashes()["scientific_core_hash"]
    rows["scientific_core"] = {"sha256": core, "expected": EXPECTED["scientific_core"], "ok": core == EXPECTED["scientific_core"]}
    if core != EXPECTED["scientific_core"]:
        raise SystemExit(f"HASH MISMATCH scientific_core: got={core}")
    check("protocol_v11", MB / "M60_PROTOCOL_V1_1.md", EXPECTED["protocol_v11"], lf=True)
    check("cohort", MB / "M60_COHORT_MANIFEST.json", EXPECTED["cohort"])
    check("prediction_lock", MB / "M60_PREDICTION_LOCK_MANIFEST.json", EXPECTED["prediction_lock"])
    check("final_truth", TRUTH_ROOT / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json", EXPECTED["final_truth"])
    check("final_truth_lock", TRUTH_ROOT / "M60_TRUTH_FINAL_LOCK_MANIFEST.json", EXPECTED["final_truth_lock"])

    pred_lock = load_json(MB / "M60_PREDICTION_LOCK_MANIFEST.json")
    for name, expected in (pred_lock.get("file_sha256") or {}).items():
        got = sha256_file(MB / name)
        if got != expected:
            raise SystemExit(f"LOCKED PREDICTION FILE HASH MISMATCH {name}")
    if pred_lock.get("n_cases") != 60:
        raise SystemExit("prediction lock n_cases != 60")

    return {
        "verified_utc": utc_now(),
        "FINAL_UNBLIND_INTEGRITY_VERIFIED": "YES",
        "files": rows,
        "prediction_inner_files_verified": True,
        "d20_touched": False,
        "predictions_regenerated": False,
    }


def index_preds(payload: dict) -> dict:
    out = {}
    for rec in payload["predictions"]:
        out[rec["case_id"]] = rec
    if len(out) != 60:
        raise SystemExit(f"{payload.get('kind')} n={len(out)}")
    return out


def paired_bootstrap_diff(a: list[int], b: list[int]) -> tuple[float, float]:
    n = len(a)
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    diffs = np.empty(BOOTSTRAP_N, dtype=float)
    for i in range(BOOTSTRAP_N):
        idx = rng.integers(0, n, size=n)
        diffs[i] = aa[idx].mean() - bb[idx].mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(lo), float(hi)


def fmt_ci(ci: tuple[float, float]) -> str:
    if any(math.isnan(x) for x in ci):
        return "NA"
    return f"{ci[0]:.3f}–{ci[1]:.3f}"


def fmt_pct(x: float) -> str:
    return f"{100.0 * x:.1f}"


def confusion(rows: list[dict], pred_key: str) -> dict:
    tp = tn = fp = fn = 0
    for r in rows:
        truth = r["truth"]
        pred = r[pred_key]
        if truth == "POSITIVE" and pred == "POSITIVE":
            tp += 1
        elif truth == "NEGATIVE" and pred == "NEGATIVE":
            tn += 1
        elif truth == "NEGATIVE" and pred != "NEGATIVE":
            fp += 1
        elif truth == "POSITIVE" and pred != "POSITIVE":
            fn += 1
    n_pos = tp + fn
    n_neg = tn + fp
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "sensitivity": (tp / n_pos) if n_pos else None,
        "specificity": (tn / n_neg) if n_neg else None,
        "ppv": (tp / (tp + fp)) if (tp + fp) else None,
        "npv": (tn / (tn + fn)) if (tn + fn) else None,
    }


def classify_error(row: dict, which: str) -> tuple[str, str]:
    """Post-hoc descriptive taxonomy. Does not change scores."""
    truth = row["truth"]
    pred = row[f"{which}_pred"]
    other = "gs_det" if which == "gs_agent" else "gs_agent"
    rec = row[f"{which}_rec"]
    architecture = str(rec.get("architecture") or "")
    homology = rec.get("homology_support")
    statement = str(rec.get("statement") or "").lower()
    claim = str(rec.get("claim_class") or "").lower()
    target = row["target"]
    fn = truth == "POSITIVE" and pred != "POSITIVE"
    fp = truth == "NEGATIVE" and pred != "NEGATIVE"
    statuses = action_status_counts(rec)
    same_endpoint = row["gs_agent_pred"] == row["gs_det_pred"]
    det_correct = row.get("gs_det_correct") is True
    agent_correct = row.get("gs_agent_correct") is True

    if pred == "UNRESOLVED" or "fail" in claim or "unresolved" in claim:
        return "VALIDATOR_DECISION_LIMIT", "unresolved or failed-closed claim counted incorrect under frozen rule"
    if which == "gs_agent" and det_correct and not agent_correct:
        return "ACTION_SELECTION_FAILURE", "Agent endpoint differed from a correct Deterministic call"
    if which == "gs_agent" and same_endpoint and not agent_correct and statuses.get("NO_NEW_INFORMATION") and not statuses.get("INFORMATIVE"):
        return "NON_DISCRIMINATING_ACTION", "follow-up returned no new information; wrong Deterministic call unchanged"
    if target.startswith("tetA") and fp:
        return "FAMILY_DISCRIMINATION_FAILURE", "POSITIVE tet(A)/tet(B) call on independently NEGATIVE truth"
    if target.startswith("tetA") and fn:
        if homology is not None and float(homology) < 0.40:
            return "INSUFFICIENT_SIGNAL", f"missed tetAB call with homology_support={homology}"
        if "compet" in statement or "mfs" in statement or "family" in statement:
            return "FAMILY_DISCRIMINATION_FAILURE", "failed to call tet(A)/tet(B) against independent POSITIVE truth"
        return "FAMILY_DISCRIMINATION_FAILURE", "false-negative tetA exact-endpoint call"
    if target.startswith("rpoB") and fn:
        arch_l = architecture.lower()
        if "domain" in arch_l or "fragment" in arch_l or "partial" in arch_l:
            return "REMOTE_HOMOLOGY_FAILURE", f"rpoB miss with architecture={architecture}"
        if homology is not None and float(homology) < 0.60:
            return "REMOTE_HOMOLOGY_FAILURE", f"rpoB miss with homology_support={homology} below identity-like support"
        if homology is None or float(homology) < 0.20:
            return "INSUFFICIENT_SIGNAL", "rpoB miss with little recorded homology support"
        return "VALIDATOR_DECISION_LIMIT", f"rpoB miss despite architecture={architecture} homology_support={homology}"
    if fp:
        return "FAMILY_DISCRIMINATION_FAILURE" if target.startswith("tetA") else "OTHER", "false positive on independent NEGATIVE truth"
    return "OTHER", f"wrong call truth={truth} pred={pred} architecture={architecture}"


def evidence_limitation(tcase: dict) -> str:
    bits = [
        tcase.get("human_review_evidence_basis"),
        tcase.get("adjudication_rationale"),
        tcase.get("primary_evidence_summary"),
        tcase.get("resolution_note"),
        ((tcase.get("evidence_route_1") or {}).get("reason")),
        ((tcase.get("evidence_route_2") or {}).get("reason")),
    ]
    text = " | ".join(str(b) for b in bits if b)
    return text[:800]


def why_changed(row: dict) -> str:
    det = row["gs_det_rec"]
    ag = row["gs_agent_rec"]
    d_pred = row["gs_det_pred"]
    a_pred = row["gs_agent_pred"]
    changed_m = bool(ag.get("measurements_changed_before_validation") or ag.get("m0_hash") != ag.get("m_final_hash"))
    acts = ",".join(str(x) for x in as_list(ag.get("actions_executed")))
    statuses = action_status_counts(ag)
    return (
        f"Det={d_pred} ({det.get('architecture')}, homology={det.get('homology_support')}) -> "
        f"Agent={a_pred} ({ag.get('architecture')}, homology={ag.get('homology_support')}); "
        f"actions={acts or 'none'} statuses={dict(statuses)}; "
        f"measurements_changed={changed_m}; planner={ag.get('planner_decision')}; critic={ag.get('critic_verdict')}"
    )


def system_summary_row(name: str, rows_eval: list[dict], all_rows: list[dict]) -> dict:
    pred_key = f"{name}_pred"
    corr_key = f"{name}_correct"
    k = sum(1 for r in rows_eval if r[corr_key] is True)
    n = len(rows_eval)
    acc = k / n if n else float("nan")
    ci = wilson_ci(k, n)
    completed = sum(1 for r in all_rows if r[f"{name}_complete"])
    return {
        "system": SYSTEM_LABELS[name],
        "system_id": name,
        "correct": k,
        "evaluable_n": n,
        "accuracy": acc,
        "wilson_ci_low": ci[0],
        "wilson_ci_high": ci[1],
        "wilson_ci": fmt_ci(ci),
        "completion": completed,
        "completion_denom": 60,
        "completion_rate": completed / 60,
        "correct_over_n": f"{k} / {n}",
    }


def style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)


def save_fig(fig, stem: str) -> None:
    fig.savefig(OUT / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def make_figures(eval_rows, summaries, tetA_rows, rpob_rows, routine_rows, challenge_rows, agent_all, exh_all, C, B, net) -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    order = list(SYSTEMS)
    n = len(eval_rows)

    # Figure 1
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    accs = [summaries[s]["accuracy"] for s in order]
    lows = [summaries[s]["accuracy"] - summaries[s]["wilson_ci_low"] for s in order]
    highs = [summaries[s]["wilson_ci_high"] - summaries[s]["accuracy"] for s in order]
    x = np.arange(len(order))
    ax.bar(x, accs, color=[COLORS[s] for s in order], width=0.72, yerr=[lows, highs], capsize=4, ecolor="#222")
    ax.set_ylim(0, 1.05)
    ax.set_xticks(x)
    ax.set_xticklabels([SYSTEM_LABELS[s].replace(" V4.1", "") for s in order], rotation=15, ha="right")
    ax.set_ylabel("Exact-endpoint accuracy")
    ax.set_title(f"M60 overall accuracy (N = {n} truth-evaluable cases)")
    for i, s in enumerate(order):
        ax.text(i, min(1.0, accs[i] + 0.04), summaries[s]["correct_over_n"], ha="center", va="bottom", fontsize=8)
    style_axes(ax)
    fig.text(0.5, 0.01, "Error bars are Wilson 95% confidence intervals. Unresolved predictions count as incorrect.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save_fig(fig, "FIGURE1_overall_accuracy")

    # Figure 2
    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    vals = [len(C), len(B)]
    bars = ax.bar(["Det errors corrected\nby Agent (C)", "Det correct calls\ndegraded by Agent (B)"], vals, color=["#009E73", "#D55E00"], width=0.55)
    ymax = max(vals + [1]) + 1.5
    ax.set_ylim(0, ymax)
    ax.set_ylabel(f"Cases (evaluable N = {n})")
    ax.set_title("Paired effect of GS-Agentic vs GS-Deterministic")
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.08, str(v), ha="center", va="bottom")
    ax.text(0.5, 0.92, f"NET CORRECTIONS = C − B = {net}", transform=ax.transAxes, ha="center", fontsize=11)
    style_axes(ax)
    fig.tight_layout()
    save_fig(fig, "FIGURE2_agent_vs_det")

    # Figure 3
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 5.0), sharey=True)
    for ax, subset, title, denom in (
        (axes[0], tetA_rows, "tetA_tetracycline_efflux", 26),
        (axes[1], rpob_rows, "rpoB_RNAP_beta", 15),
    ):
        ks = [sum(1 for r in subset if r[f"{s}_correct"] is True) for s in order]
        ns = len(subset)
        accs = [k / ns if ns else 0 for k in ks]
        cis = [wilson_ci(k, ns) for k in ks]
        lows = [accs[i] - cis[i][0] for i in range(5)]
        highs = [cis[i][1] - accs[i] for i in range(5)]
        x = np.arange(5)
        ax.bar(x, accs, color=[COLORS[s] for s in order], width=0.72, yerr=[lows, highs], capsize=3, ecolor="#222")
        ax.set_ylim(0, 1.08)
        ax.set_xticks(x)
        ax.set_xticklabels([SYSTEM_LABELS[s].replace(" V4.1", "").replace(" comparator", "") for s in order], rotation=20, ha="right", fontsize=8)
        ax.set_title(f"{title}\nN = {ns} (expected {denom})")
        for i, k in enumerate(ks):
            ax.text(i, min(1.02, accs[i] + 0.03), f"{k}/{ns}", ha="center", fontsize=7)
        style_axes(ax)
    axes[0].set_ylabel("Exact-endpoint accuracy")
    fig.suptitle("Per-target performance on truth-evaluable cases")
    fig.tight_layout()
    save_fig(fig, "FIGURE3_per_target")

    # Figure 4
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    width = 0.36
    r_acc = [sum(1 for r in routine_rows if r[f"{s}_correct"]) / len(routine_rows) for s in order]
    c_acc = [sum(1 for r in challenge_rows if r[f"{s}_correct"]) / len(challenge_rows) for s in order]
    x = np.arange(len(order))
    ax.bar(x - width / 2, r_acc, width, label=f"Routine (N={len(routine_rows)})", color="#0072B2")
    ax.bar(x + width / 2, c_acc, width, label=f"Challenge (N={len(challenge_rows)})", color="#D55E00")
    ax.set_ylim(0, 1.05)
    ax.set_xticks(x)
    ax.set_xticklabels([SYSTEM_LABELS[s].replace(" V4.1", "") for s in order], rotation=15, ha="right")
    ax.set_ylabel("Exact-endpoint accuracy")
    ax.set_title("Routine vs challenge accuracy (truth-evaluable cases)")
    ax.legend(frameon=False)
    style_axes(ax)
    fig.tight_layout()
    save_fig(fig, "FIGURE4_stratum")

    # Figure 5
    a_n = [followups(r) for r in agent_all]
    e_n = [followups(r) for r in exh_all]
    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    positions = [1, 2]
    bp = ax.boxplot([a_n, e_n], positions=positions, widths=0.45, patch_artist=True, medianprops={"color": "black"})
    for patch, color in zip(bp["boxes"], [COLORS["gs_agent"], COLORS["gs_exh"]]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.scatter(positions, [statistics.mean(a_n), statistics.mean(e_n)], marker="D", color="black", zorder=3, label="mean")
    ax.set_ylim(0, max(a_n + e_n) + 1)
    ax.set_xticks(positions)
    ax.set_xticklabels(["GS-Agentic", "GS-Exhaustive"])
    ax.set_ylabel("Follow-up analyses per case")
    red = 100.0 * (sum(e_n) - sum(a_n)) / sum(e_n) if sum(e_n) else float("nan")
    ax.set_title("Follow-up analysis efficiency (all 60 cases)")
    ax.text(0.5, 0.92, f"Follow-up action reduction = {red:.1f}%", transform=ax.transAxes, ha="center")
    ax.legend(frameon=False, loc="upper right")
    style_axes(ax)
    fig.tight_layout()
    save_fig(fig, "FIGURE5_followup_efficiency")

    # Figure 6
    a_t = [float(r.get("runtime_seconds") or 0) for r in agent_all]
    e_t = [float(r.get("runtime_seconds") or 0) for r in exh_all]
    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    bp = ax.boxplot([a_t, e_t], positions=[1, 2], widths=0.45, patch_artist=True, medianprops={"color": "black"})
    for patch, color in zip(bp["boxes"], [COLORS["gs_agent"], COLORS["gs_exh"]]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.set_ylim(0, max(a_t + e_t) * 1.08)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(["GS-Agentic", "GS-Exhaustive"])
    ax.set_ylabel("Wall-clock runtime per case (seconds)")
    ax.set_title("Runtime (all 60 cases)")
    ratio = statistics.median(a_t) / statistics.median(e_t) if statistics.median(e_t) else float("nan")
    fig.text(
        0.5,
        0.01,
        f"Agent median {statistics.median(a_t):.1f}s vs Exhaustive {statistics.median(e_t):.1f}s "
        f"(ratio {ratio:.1f}×). Agent wall-clock includes local LLM inference (qwen3:4b) and is not implied by tool-call count.",
        ha="center",
        fontsize=8,
    )
    style_axes(ax)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    save_fig(fig, "FIGURE6_runtime")


def pct(x) -> str:
    if x is None:
        return "NA"
    return f"{100.0 * x:.1f}%"


def main() -> int:
    integrity = verify_locks()
    print("FINAL_UNBLIND_INTEGRITY_VERIFIED = YES")

    truth_obj = load_json(TRUTH_ROOT / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json")
    truth_cases = {c["case_id"]: c for c in truth_obj["cases"]}
    if len(truth_cases) != 60:
        raise SystemExit("truth n != 60")

    conv = index_preds(load_json(MB / "M60_CONVENTIONAL_LOCKED.json"))
    spec = index_preds(load_json(MB / "M60_SPECIALIST_COMPARATORS_LOCKED.json"))
    det = index_preds(load_json(MB / "M60_GS_DETERMINISTIC_LOCKED.json"))
    agent = index_preds(load_json(MB / "M60_GS_AGENTIC_LOCKED.json"))
    exh = index_preds(load_json(MB / "M60_GS_EXHAUSTIVE_LOCKED.json"))

    rows = []
    for cid, tcase in sorted(truth_cases.items(), key=lambda kv: int(kv[1]["position"])):
        for store, name in ((conv, "conventional"), (spec, "specialist"), (det, "gs_det"), (agent, "gs_agent"), (exh, "gs_exh")):
            if cid not in store:
                raise SystemExit(f"missing prediction {name} {cid}")
        c_rec, s_rec, d_rec, a_rec, e_rec = conv[cid], spec[cid], det[cid], agent[cid], exh[cid]
        if not (c_rec["accession"] == s_rec["accession"] == d_rec["accession"] == a_rec["accession"] == e_rec["accession"] == tcase["accession"]):
            raise SystemExit(f"accession mismatch {cid}")
        if not (c_rec["target"] == s_rec["target"] == d_rec["target"] == a_rec["target"] == e_rec["target"] == tcase["target"]):
            raise SystemExit(f"target mismatch {cid}")
        truth = tcase["truth_value"]
        c_pred = conventional_binary(c_rec)
        s_pred = specialist_binary(s_rec)
        d_pred = gs_binary(d_rec)
        a_pred = gs_binary(a_rec)
        e_pred = gs_binary(e_rec)
        row = {
            "case_id": cid,
            "position": int(tcase["position"]),
            "accession": tcase["accession"],
            "target": tcase["target"],
            "stratum": tcase["stratum"],
            "truth": truth,
            "truth_status": tcase.get("truth_status"),
            "evaluable": truth in {"POSITIVE", "NEGATIVE"},
            "conventional_pred": c_pred,
            "conventional_correct": is_correct(truth, c_pred),
            "conventional_complete": is_complete(c_rec),
            "specialist_pred": s_pred,
            "specialist_correct": is_correct(truth, s_pred),
            "specialist_complete": is_complete(s_rec),
            "specialist_tool": "AMRFinderPlus" if tcase["target"].startswith("tetA") else "NCBI_RefSeq_PGAP",
            "gs_det_pred": d_pred,
            "gs_det_correct": is_correct(truth, d_pred),
            "gs_det_complete": is_complete(d_rec),
            "gs_agent_pred": a_pred,
            "gs_agent_correct": is_correct(truth, a_pred),
            "gs_agent_complete": is_complete(a_rec),
            "gs_exh_pred": e_pred,
            "gs_exh_correct": is_correct(truth, e_pred),
            "gs_exh_complete": is_complete(e_rec),
            "agent_completion": a_rec.get("completion_status"),
            "agent_actions": followups(a_rec),
            "exhaustive_actions": followups(e_rec),
            "agent_runtime": a_rec.get("runtime_seconds"),
            "exhaustive_runtime": e_rec.get("runtime_seconds"),
            "gs_det_runtime": d_rec.get("runtime_seconds"),
            "conventional_runtime": c_rec.get("runtime_seconds"),
            "specialist_runtime": s_rec.get("runtime_seconds"),
            "conventional_rec": c_rec,
            "specialist_rec": s_rec,
            "gs_det_rec": d_rec,
            "gs_agent_rec": a_rec,
            "gs_exh_rec": e_rec,
            "truth_case": tcase,
        }
        rows.append(row)

    if len(rows) != 60:
        raise SystemExit("joined n != 60")

    def n_truth(target_prefix, value):
        return sum(1 for r in rows if r["target"].startswith(target_prefix) and r["truth"] == value)

    dist = {
        "total": 60,
        "tetA_POSITIVE": n_truth("tetA", "POSITIVE"),
        "tetA_NEGATIVE": n_truth("tetA", "NEGATIVE"),
        "tetA_TRUTH_UNCERTAIN": n_truth("tetA", "TRUTH_UNCERTAIN"),
        "rpoB_POSITIVE": n_truth("rpoB", "POSITIVE"),
        "rpoB_NEGATIVE": n_truth("rpoB", "NEGATIVE"),
        "rpoB_TRUTH_UNCERTAIN": n_truth("rpoB", "TRUTH_UNCERTAIN"),
    }
    expected_dist = {
        "total": 60,
        "tetA_POSITIVE": 7,
        "tetA_NEGATIVE": 19,
        "tetA_TRUTH_UNCERTAIN": 4,
        "rpoB_POSITIVE": 15,
        "rpoB_NEGATIVE": 0,
        "rpoB_TRUTH_UNCERTAIN": 15,
    }
    if dist != expected_dist:
        raise SystemExit(f"TRUTH DISTRIBUTION MISMATCH {dist}")
    eval_rows = [r for r in rows if r["evaluable"]]
    if len(eval_rows) != 41:
        raise SystemExit(f"evaluable {len(eval_rows)} != 41")
    print("TRUTH DISTRIBUTION VERIFIED; EVALUABLE 41/60")

    summaries = {s: system_summary_row(s, eval_rows, rows) for s in SYSTEMS}
    agent_corr = [1 if r["gs_agent_correct"] else 0 for r in eval_rows]
    det_corr = [1 if r["gs_det_correct"] else 0 for r in eval_rows]
    exh_corr = [1 if r["gs_exh_correct"] else 0 for r in eval_rows]
    acc_agent = summaries["gs_agent"]["accuracy"]
    acc_det = summaries["gs_det"]["accuracy"]
    acc_exh = summaries["gs_exh"]["accuracy"]
    diff_ad = acc_agent - acc_det
    diff_ae = acc_agent - acc_exh
    ci_ad = paired_bootstrap_diff(agent_corr, det_corr)
    ci_ae = paired_bootstrap_diff(agent_corr, exh_corr)

    A = [r for r in eval_rows if r["gs_det_correct"] and r["gs_agent_correct"]]
    B = [r for r in eval_rows if r["gs_det_correct"] and not r["gs_agent_correct"]]
    C = [r for r in eval_rows if (not r["gs_det_correct"]) and r["gs_agent_correct"]]
    D = [r for r in eval_rows if (not r["gs_det_correct"]) and (not r["gs_agent_correct"])]
    net = len(C) - len(B)
    if len(B) + len(C) == 0:
        mcnemar_p = None
        mcnemar_note = "McNemar not applicable (B+C = 0)"
    else:
        mcnemar_p = float(binomtest(len(C), n=len(B) + len(C), p=0.5, alternative="two-sided").pvalue)
        mcnemar_note = f"exact two-sided McNemar / binomial P={mcnemar_p:.6g} on B+C={len(B)+len(C)}"

    E_wrong_A_ok = [r for r in eval_rows if (not r["gs_exh_correct"]) and r["gs_agent_correct"]]
    E_ok_A_wrong = [r for r in eval_rows if r["gs_exh_correct"] and not r["gs_agent_correct"]]

    tetA_rows = [r for r in eval_rows if r["target"].startswith("tetA")]
    rpob_rows = [r for r in eval_rows if r["target"].startswith("rpoB")]
    routine_rows = [r for r in eval_rows if r["stratum"] == "routine"]
    challenge_rows = [r for r in eval_rows if r["stratum"] == "challenge"]
    if len(tetA_rows) != 26 or len(rpob_rows) != 15:
        raise SystemExit(f"target evaluable tetA={len(tetA_rows)} rpoB={len(rpob_rows)}")

    def paired_counts(subset):
        b = [r for r in subset if r["gs_det_correct"] and not r["gs_agent_correct"]]
        c = [r for r in subset if (not r["gs_det_correct"]) and r["gs_agent_correct"]]
        return len(c), len(b), len(c) - len(b)

    tetA_c, tetA_b, tetA_net = paired_counts(tetA_rows)
    rpob_c, rpob_b, rpob_net = paired_counts(rpob_rows)
    rou_c, rou_b, rou_net = paired_counts(routine_rows)
    cha_c, cha_b, cha_net = paired_counts(challenge_rows)

    agent_all = [r["gs_agent_rec"] for r in rows]
    exh_all = [r["gs_exh_rec"] for r in rows]
    a_actions = [followups(r) for r in agent_all]
    e_actions = [followups(r) for r in exh_all]
    a_times = [float(r.get("runtime_seconds") or 0) for r in agent_all]
    e_times = [float(r.get("runtime_seconds") or 0) for r in exh_all]
    action_reduction = 100.0 * (sum(e_actions) - sum(a_actions)) / sum(e_actions) if sum(e_actions) else float("nan")
    runtime_ratio = statistics.median(a_times) / statistics.median(e_times) if statistics.median(e_times) else float("nan")
    a_q = iqr(a_actions)
    e_q = iqr(e_actions)
    at_q = iqr(a_times)
    et_q = iqr(e_times)

    # Mechanisms across 60
    planner_freq = Counter()
    critic_challenge = 0
    critic_second = 0
    status_tot = Counter()
    m_changed = 0
    endpoint_diff = 0
    endpoint_same = 0
    for r in rows:
        ag = r["gs_agent_rec"]
        for act in as_list(ag.get("planner_actions")):
            planner_freq[str(act)] += 1
        verdict = str(ag.get("critic_verdict") or "").lower()
        if verdict and verdict not in {"accept", "accepted", "none", "null"}:
            critic_challenge += 1
        if as_list(ag.get("critic_actions")):
            critic_second += 1
        status_tot.update(action_status_counts(ag))
        if ag.get("m0_hash") and ag.get("m_final_hash") and ag.get("m0_hash") != ag.get("m_final_hash"):
            m_changed += 1
        if r["gs_agent_pred"] != r["gs_det_pred"]:
            endpoint_diff += 1
        else:
            endpoint_same += 1

    beneficial = sum(1 for r in eval_rows if (not r["gs_det_correct"]) and r["gs_agent_correct"])
    harmful = sum(1 for r in eval_rows if r["gs_det_correct"] and not r["gs_agent_correct"])
    neutral = sum(1 for r in eval_rows if r["gs_agent_correct"] == r["gs_det_correct"])

    OUT.mkdir(parents=True, exist_ok=True)

    case_fields = [
        "case_id", "position", "accession", "target", "stratum", "truth", "truth_status", "evaluable",
        "conventional_pred", "conventional_correct",
        "specialist_pred", "specialist_correct", "specialist_tool",
        "gs_det_pred", "gs_det_correct",
        "gs_agent_pred", "gs_agent_correct",
        "gs_exh_pred", "gs_exh_correct",
        "agent_completion", "agent_actions", "exhaustive_actions",
        "agent_runtime", "exhaustive_runtime",
    ]
    write_csv(OUT / "M60_FINAL_CASE_LEVEL_RESULTS.csv", rows, case_fields)

    write_csv(OUT / "M60_FINAL_SYSTEM_SUMMARY.csv", [summaries[s] for s in SYSTEMS])

    avd_rows = [
        {"section": "summary", "metric": "A_both_correct", "value": len(A)},
        {"section": "summary", "metric": "B_det_correct_agent_wrong", "value": len(B)},
        {"section": "summary", "metric": "C_det_wrong_agent_correct", "value": len(C)},
        {"section": "summary", "metric": "D_both_wrong", "value": len(D)},
        {"section": "summary", "metric": "DET_ERRORS_CORRECTED_BY_AGENT", "value": len(C)},
        {"section": "summary", "metric": "DET_CORRECT_CALLS_DEGRADED_BY_AGENT", "value": len(B)},
        {"section": "summary", "metric": "NET_CORRECTIONS", "value": net},
        {"section": "summary", "metric": "accuracy_agent", "value": acc_agent},
        {"section": "summary", "metric": "accuracy_det", "value": acc_det},
        {"section": "summary", "metric": "accuracy_difference_agent_minus_det", "value": diff_ad},
        {"section": "summary", "metric": "paired_bootstrap_ci_low", "value": ci_ad[0]},
        {"section": "summary", "metric": "paired_bootstrap_ci_high", "value": ci_ad[1]},
        {"section": "summary", "metric": "mcnemar_exact_p", "value": mcnemar_p if mcnemar_p is not None else "NA"},
        {"section": "summary", "metric": "mcnemar_note", "value": mcnemar_note},
        {"section": "summary", "metric": "bootstrap_seed", "value": BOOTSTRAP_SEED},
        {"section": "summary", "metric": "bootstrap_resamples", "value": BOOTSTRAP_N},
    ]
    for label, subset in (("B", B), ("C", C)):
        for r in subset:
            avd_rows.append(
                {
                    "section": f"discordant_{label}",
                    "case_id": r["case_id"],
                    "position": r["position"],
                    "target": r["target"],
                    "stratum": r["stratum"],
                    "truth": r["truth"],
                    "det_prediction": r["gs_det_pred"],
                    "agent_prediction": r["gs_agent_pred"],
                    "agent_diagnostic_need": needs_label(r["gs_agent_rec"].get("diagnostic_needs_m0")),
                    "planner_action": ";".join(str(x) for x in as_list(r["gs_agent_rec"].get("planner_actions"))),
                    "critic_action": ";".join(str(x) for x in as_list(r["gs_agent_rec"].get("critic_actions"))),
                    "new_deterministic_evidence": bool(
                        r["gs_agent_rec"].get("measurements_changed_before_validation")
                        or r["gs_agent_rec"].get("m0_hash") != r["gs_agent_rec"].get("m_final_hash")
                    ),
                    "why_final_decision_changed": why_changed(r),
                    "metric": label,
                    "value": "",
                }
            )
    write_csv(OUT / "M60_AGENT_VS_DETERMINISTIC.csv", avd_rows)

    ave_rows = [
        {"section": "summary", "metric": "accuracy_agent", "value": acc_agent},
        {"section": "summary", "metric": "accuracy_exhaustive", "value": acc_exh},
        {"section": "summary", "metric": "accuracy_difference_agent_minus_exhaustive", "value": diff_ae},
        {"section": "summary", "metric": "paired_bootstrap_ci_low", "value": ci_ae[0]},
        {"section": "summary", "metric": "paired_bootstrap_ci_high", "value": ci_ae[1]},
        {"section": "summary", "metric": "exhaustive_wrong_agent_correct", "value": len(E_wrong_A_ok)},
        {"section": "summary", "metric": "exhaustive_correct_agent_wrong", "value": len(E_ok_A_wrong)},
        {"section": "summary", "metric": "equivalence_claimed", "value": False},
        {"section": "summary", "metric": "wording", "value": (
            f"Agentic performance differed from Exhaustive by {100*(acc_agent-acc_exh):.1f} percentage points."
        )},
    ]
    for label, subset in (("exh_wrong_agent_correct", E_wrong_A_ok), ("exh_correct_agent_wrong", E_ok_A_wrong)):
        for r in subset:
            ave_rows.append(
                {
                    "section": label,
                    "case_id": r["case_id"],
                    "target": r["target"],
                    "stratum": r["stratum"],
                    "truth": r["truth"],
                    "exhaustive_prediction": r["gs_exh_pred"],
                    "agent_prediction": r["gs_agent_pred"],
                    "metric": label,
                    "value": "",
                }
            )
    write_csv(OUT / "M60_AGENT_VS_EXHAUSTIVE.csv", ave_rows)

    target_rows = []
    for subset, label, n_exp in ((tetA_rows, "tetA", 26), (rpob_rows, "rpoB", 15)):
        for s in SYSTEMS:
            k = sum(1 for r in subset if r[f"{s}_correct"])
            n = len(subset)
            ci = wilson_ci(k, n)
            conf = confusion(subset, f"{s}_pred")
            rec = {
                "target": label,
                "system": SYSTEM_LABELS[s],
                "evaluable_n": n,
                "expected_n": n_exp,
                "correct": k,
                "accuracy": k / n,
                "wilson_ci": fmt_ci(ci),
                "wilson_ci_low": ci[0],
                "wilson_ci_high": ci[1],
                "tp": conf["tp"],
                "tn": conf["tn"],
                "fp": conf["fp"],
                "fn": conf["fn"],
                "sensitivity": conf["sensitivity"],
                "specificity": conf["specificity"] if label != "rpoB" else "NA_no_negative_truth",
                "ppv": conf["ppv"] if (conf["tp"] + conf["fp"]) else "undefined_zero_predicted_positives",
                "npv": conf["npv"] if label != "rpoB" else "NA_no_negative_truth",
                "sensitivity_denominator": f"{conf['tp']} / {conf['n_pos']}" if conf["n_pos"] else "NA",
                "specificity_denominator": (
                    "Specificity could not be estimated for rpoB because no independently resolved negative cases were present."
                    if label == "rpoB"
                    else f"{conf['tn']} / {conf['n_neg']}"
                ),
            }
            if label == "tetA" and s == "gs_agent":
                rec["agent_vs_det_corrections"] = tetA_c
                rec["agent_vs_det_degradations"] = tetA_b
                rec["agent_vs_det_net"] = tetA_net
            target_rows.append(rec)
    write_csv(OUT / "M60_TARGET_SPECIFIC_RESULTS.csv", target_rows)

    stratum_rows = []
    for subset, label in ((routine_rows, "routine"), (challenge_rows, "challenge")):
        cc, bb, nn = paired_counts(subset)
        for s in SYSTEMS:
            k = sum(1 for r in subset if r[f"{s}_correct"])
            n = len(subset)
            stratum_rows.append(
                {
                    "stratum": label,
                    "system": SYSTEM_LABELS[s],
                    "evaluable_n": n,
                    "correct": k,
                    "accuracy": k / n if n else None,
                    "wilson_ci": fmt_ci(wilson_ci(k, n)),
                    "agent_vs_det_corrections": cc if s == "gs_agent" else "",
                    "agent_vs_det_degradations": bb if s == "gs_agent" else "",
                    "agent_vs_det_net": nn if s == "gs_agent" else "",
                    "analysis_class": "secondary",
                }
            )
    write_csv(OUT / "M60_STRATUM_RESULTS.csv", stratum_rows)

    write_csv(
        OUT / "M60_EFFICIENCY_RESULTS.csv",
        [
            {
                "system": "GS-Agentic V4.1",
                "n_cases": 60,
                "completion": sum(1 for r in rows if r["gs_agent_complete"]),
                "total_followup_actions": sum(a_actions),
                "mean_actions_per_case": statistics.mean(a_actions),
                "median_actions_per_case": statistics.median(a_actions),
                "iqr_actions_q1": a_q[0],
                "iqr_actions_q3": a_q[2],
                "total_runtime_seconds": sum(a_times),
                "median_runtime_seconds": statistics.median(a_times),
                "iqr_runtime_q1": at_q[0],
                "iqr_runtime_q3": at_q[2],
                "followup_action_reduction_percent": action_reduction,
                "runtime_ratio_agent_over_exhaustive": runtime_ratio,
                "note": "Wall-clock includes local LLM inference; fewer tool calls do not imply faster runtime.",
            },
            {
                "system": "GS-Exhaustive V4.1",
                "n_cases": 60,
                "completion": sum(1 for r in rows if r["gs_exh_complete"]),
                "total_followup_actions": sum(e_actions),
                "mean_actions_per_case": statistics.mean(e_actions),
                "median_actions_per_case": statistics.median(e_actions),
                "iqr_actions_q1": e_q[0],
                "iqr_actions_q3": e_q[2],
                "total_runtime_seconds": sum(e_times),
                "median_runtime_seconds": statistics.median(e_times),
                "iqr_runtime_q1": et_q[0],
                "iqr_runtime_q3": et_q[2],
                "followup_action_reduction_percent": "",
                "runtime_ratio_agent_over_exhaustive": "",
                "note": "No LLM calls; deterministic follow-up of all eligible registered actions.",
            },
        ],
    )

    uncertain = [r for r in rows if r["truth"] == "TRUTH_UNCERTAIN"]
    if len(uncertain) != 19:
        raise SystemExit(f"uncertain {len(uncertain)} != 19")
    unc_rows = []
    for r in uncertain:
        preds = [r["conventional_pred"], r["specialist_pred"], r["gs_det_pred"], r["gs_agent_pred"], r["gs_exh_pred"]]
        unc_rows.append(
            {
                "case_id": r["case_id"],
                "position": r["position"],
                "accession": r["accession"],
                "target": r["target"],
                "stratum": r["stratum"],
                "truth": "TRUTH_UNCERTAIN",
                "conventional_prediction": r["conventional_pred"],
                "specialist_prediction": r["specialist_pred"],
                "specialist_tool": r["specialist_tool"],
                "gs_det_prediction": r["gs_det_pred"],
                "gs_agent_prediction": r["gs_agent_pred"],
                "gs_exh_prediction": r["gs_exh_pred"],
                "systems_unanimous": len(set(preds)) == 1,
                "n_distinct_predictions": len(set(preds)),
                "scored_correct_or_incorrect": "NOT_SCORED",
                "evidence_limitation": evidence_limitation(r["truth_case"]),
            }
        )
    write_csv(OUT / "M60_UNCERTAIN_CASES.csv", unc_rows)

    mech_rows = [
        {"metric": "planner_invoked", "value": sum(1 for r in rows if r["gs_agent_rec"].get("planner_invoked"))},
        {"metric": "critic_invoked", "value": sum(1 for r in rows if r["gs_agent_rec"].get("critic_invoked"))},
        {"metric": "critic_challenge_frequency", "value": critic_challenge},
        {"metric": "critic_second_action_frequency", "value": critic_second},
        {"metric": "INFORMATIVE_actions", "value": status_tot.get("INFORMATIVE", 0)},
        {"metric": "NO_NEW_INFORMATION_actions", "value": status_tot.get("NO_NEW_INFORMATION", 0)},
        {"metric": "UNAVAILABLE_actions", "value": status_tot.get("UNAVAILABLE", 0)},
        {"metric": "FAILED_actions", "value": status_tot.get("FAILED", 0)},
        {"metric": "m0_ne_m_final_count", "value": m_changed},
        {"metric": "agent_endpoint_ne_det_endpoint", "value": endpoint_diff},
        {"metric": "agent_endpoint_eq_det_endpoint", "value": endpoint_same},
        {"metric": "evaluable_BENEFICIAL_agent_corrected_det", "value": beneficial},
        {"metric": "evaluable_HARMFUL_agent_degraded_det", "value": harmful},
        {"metric": "evaluable_NEUTRAL_same_scored_endpoint", "value": neutral},
        {"metric": "n_agentic_cases", "value": 60},
    ]
    for act, n in planner_freq.most_common():
        mech_rows.append({"metric": "planner_action_frequency", "action": act, "value": n})
    write_csv(OUT / "M60_AGENT_MECHANISMS.csv", mech_rows)

    tax_rows = []
    for r in eval_rows:
        for which, label in (("gs_agent", "GS-Agentic V4.1"), ("gs_det", "GS-Deterministic V4.1")):
            if r[f"{which}_correct"] is True:
                continue
            code, note = classify_error(r, which)
            tax_rows.append(
                {
                    "case_id": r["case_id"],
                    "position": r["position"],
                    "target": r["target"],
                    "stratum": r["stratum"],
                    "truth": r["truth"],
                    "system": label,
                    "prediction": r[f"{which}_pred"],
                    "taxonomy": code,
                    "note": note,
                    "analysis_class": "post_hoc_descriptive_only",
                    "used_to_tune": False,
                }
            )
    write_csv(OUT / "M60_ERROR_TAXONOMY.csv", tax_rows)

    make_figures(
        eval_rows, summaries, tetA_rows, rpob_rows, routine_rows, challenge_rows,
        agent_all, exh_all, C, B, net,
    )

    def acc_line(s):
        sm = summaries[s]
        return f"{sm['correct_over_n']} ({sm['accuracy']:.3f}; Wilson 95% CI {sm['wilson_ci']}); completion {sm['completion']}/60"

    tetA_conf_agent = confusion(tetA_rows, "gs_agent_pred")
    rpob_k_agent = sum(1 for r in rpob_rows if r["gs_agent_correct"])
    routine_k_agent = sum(1 for r in routine_rows if r["gs_agent_correct"])
    challenge_k_agent = sum(1 for r in challenge_rows if r["gs_agent_correct"])

    md = f"""# M60 final results

One-shot unblind of GENOME_SKEPTIC_V4_1_MANUSCRIPT on the frozen M60 cohort.
Numbers below are the manuscript result. No post-unblind development, threshold
change, case replacement, or prediction regeneration was performed.

## 1. Cohort and independent truth

The locked cohort contains 60 genome-target cases (30 tetA, 30 rpoB; 30 routine,
30 challenge). Independent truth was assigned and human-reviewed before this
unblind.

Frozen final truth distribution:

- Total: 60
- tetA: 7 POSITIVE, 19 NEGATIVE, 4 TRUTH_UNCERTAIN
- rpoB: 15 POSITIVE, 0 NEGATIVE, 15 TRUTH_UNCERTAIN

Truth-evaluable primary denominator: **41 / 60**.
TRUTH_UNCERTAIN cases (n = 19) remain in case-level output and completion
statistics and are excluded from primary accuracy, McNemar, and bootstrap
tables.

Unresolved or failed-closed predictions count as incorrect when truth is
POSITIVE or NEGATIVE.

## 2. Overall performance

Truth-evaluable N = 41.

- Conventional: {acc_line('conventional')}
- Specialist comparator (AMRFinderPlus on tetA; NCBI RefSeq/PGAP on rpoB): {acc_line('specialist')}
- GS-Deterministic V4.1: {acc_line('gs_det')}
- GS-Agentic V4.1: {acc_line('gs_agent')}
- GS-Exhaustive V4.1: {acc_line('gs_exh')}

Primary comparison is GS-Agentic V4.1 versus GS-Deterministic V4.1.

Absolute accuracy difference (Agent − Deterministic): **{100*diff_ad:+.1f} percentage points**.
Paired bootstrap 95% CI (10,000 resamples, seed {BOOTSTRAP_SEED}): **{fmt_ci(ci_ad)}**.

## 3. Agent vs deterministic paired comparison

Among 41 evaluable cases:

- A (both correct): {len(A)}
- B (Det correct, Agent wrong): {len(B)}
- C (Det wrong, Agent correct): {len(C)}
- D (both wrong): {len(D)}

DET ERRORS CORRECTED BY AGENT = {len(C)}
DET CORRECT CALLS DEGRADED BY AGENT = {len(B)}
NET CORRECTIONS = {net}

{mcnemar_note}.

Discordant cases are listed in `M60_AGENT_VS_DETERMINISTIC.csv`.

{"GS-Agentic achieved higher exact endpoint accuracy than the identical deterministic core by " + f"{100*diff_ad:.1f}" + " percentage points in this prospective blinded benchmark." if diff_ad > 0 else "GS-Agentic did not outperform GS-Deterministic on exact endpoint accuracy in this prospective blinded benchmark (difference " + f"{100*diff_ad:+.1f}" + " percentage points)."}
{" The adaptive layer corrected " + str(len(C)) + " deterministic errors while introducing " + str(len(B)) + " errors." if (len(C) or len(B)) else ""}

## 4. Agent vs exhaustive comparison

- GS-Agentic accuracy: {summaries['gs_agent']['correct_over_n']} ({summaries['gs_agent']['accuracy']:.3f})
- GS-Exhaustive accuracy: {summaries['gs_exh']['correct_over_n']} ({summaries['gs_exh']['accuracy']:.3f})
- Absolute difference (Agent − Exhaustive): {100*diff_ae:+.1f} percentage points
- Paired bootstrap 95% CI: {fmt_ci(ci_ae)}
- Exhaustive wrong → Agent correct: {len(E_wrong_A_ok)}
- Exhaustive correct → Agent wrong: {len(E_ok_A_wrong)}

No equivalence margin was preregistered. Statistical equivalence is not claimed.
Agentic performance differed from Exhaustive by {100*(acc_agent-acc_exh):.1f} percentage points, while Agent used {action_reduction:.1f}% fewer follow-up analyses.

## 5. Established comparator performance

Specialist tools were not pooled into one biological method. AMRFinderPlus 4.2.7
(database 2026-08-07.1) is the tetA specialist. NCBI RefSeq/PGAP annotation is
the rpoB specialist. The overall specialist row above is a composite of those
two frozen converters.

tetA evaluable n = {len(tetA_rows)}:

"""
    for s in SYSTEMS:
        sm_k = sum(1 for r in tetA_rows if r[f"{s}_correct"])
        ci = wilson_ci(sm_k, len(tetA_rows))
        md += f"- {SYSTEM_LABELS[s]}: {sm_k} / {len(tetA_rows)} ({sm_k/len(tetA_rows):.3f}; Wilson 95% CI {fmt_ci(ci)})\n"
    md += f"\nrpoB evaluable n = {len(rpob_rows)}:\n\n"
    for s in SYSTEMS:
        sm_k = sum(1 for r in rpob_rows if r[f"{s}_correct"])
        ci = wilson_ci(sm_k, len(rpob_rows))
        md += f"- {SYSTEM_LABELS[s]}: {sm_k} / {len(rpob_rows)} ({sm_k/len(rpob_rows):.3f}; Wilson 95% CI {fmt_ci(ci)})\n"

    md += f"""

## 6. Target-specific performance

### tetA (evaluable n = 26; 7 POSITIVE, 19 NEGATIVE)

GS-Agentic: {sum(1 for r in tetA_rows if r['gs_agent_correct'])} / 26.
Sensitivity {tetA_conf_agent['tp']} / {tetA_conf_agent['n_pos']}; specificity {tetA_conf_agent['tn']} / {tetA_conf_agent['n_neg']}; PPV {tetA_conf_agent['tp']} / {tetA_conf_agent['tp']+tetA_conf_agent['fp'] if tetA_conf_agent['tp']+tetA_conf_agent['fp'] else 0}; NPV {tetA_conf_agent['tn']} / {tetA_conf_agent['tn']+tetA_conf_agent['fn'] if tetA_conf_agent['tn']+tetA_conf_agent['fn'] else 0}.

Agent vs Det on tetA: corrections {tetA_c}, degradations {tetA_b}, net {tetA_net}.

Full per-system sensitivity/specificity/PPV/NPV with denominators are in
`M60_TARGET_SPECIFIC_RESULTS.csv`.

### rpoB (evaluable n = 15; all POSITIVE)

GS-Agentic: {rpob_k_agent} / 15 (sensitivity / recall {rpob_k_agent} / 15).

Specificity could not be estimated for rpoB because no independently resolved
negative cases were present.

Agent vs Det on rpoB: corrections {rpob_c}, degradations {rpob_b}, net {rpob_net}.

## 7. Routine vs challenge performance

Secondary analysis on truth-evaluable cases.

- Routine evaluable N = {len(routine_rows)}; GS-Agentic {routine_k_agent} / {len(routine_rows)}; corrections {rou_c}, degradations {rou_b}, net {rou_net}
- Challenge evaluable N = {len(challenge_rows)}; GS-Agentic {challenge_k_agent} / {len(challenge_rows)}; corrections {cha_c}, degradations {cha_b}, net {cha_net}

Per-system stratum accuracies are in `M60_STRATUM_RESULTS.csv`.

## 8. Computational efficiency

All 60 cases (completion statistics), not the accuracy denominator.

GS-Agentic:

- follow-up actions: total {sum(a_actions)}, mean {statistics.mean(a_actions):.3f}, median {statistics.median(a_actions):.1f}, IQR {a_q[0]:.1f}–{a_q[2]:.1f}
- runtime seconds: total {sum(a_times):.1f}, median {statistics.median(a_times):.1f}, IQR {at_q[0]:.1f}–{at_q[2]:.1f}
- completion: {sum(1 for r in rows if r['gs_agent_complete'])} / 60

GS-Exhaustive:

- follow-up actions: total {sum(e_actions)}, mean {statistics.mean(e_actions):.3f}, median {statistics.median(e_actions):.1f}, IQR {e_q[0]:.1f}–{e_q[2]:.1f}
- runtime seconds: total {sum(e_times):.1f}, median {statistics.median(e_times):.1f}, IQR {et_q[0]:.1f}–{et_q[2]:.1f}
- completion: {sum(1 for r in rows if r['gs_exh_complete'])} / 60

FOLLOW-UP ACTION REDUCTION = {action_reduction:.1f}%
Agent / Exhaustive median runtime ratio = {runtime_ratio:.2f}

Action efficiency and wall-clock efficiency are reported separately. Agent
wall-clock includes local LLM inference (qwen3:4b). Fewer follow-up tool calls
did not produce a shorter wall-clock runtime.

## 9. Agent behavior

Across all 60 Agentic cases:

- planner action frequencies: {", ".join(f"{k}={v}" for k,v in planner_freq.most_common())}
- critic challenge frequency: {critic_challenge}
- critic second-action frequency: {critic_second}
- INFORMATIVE actions: {status_tot.get('INFORMATIVE', 0)}
- NO_NEW_INFORMATION actions: {status_tot.get('NO_NEW_INFORMATION', 0)}
- UNAVAILABLE actions: {status_tot.get('UNAVAILABLE', 0)}
- FAILED actions: {status_tot.get('FAILED', 0)}
- m0 ≠ m_final: {m_changed}
- Agent endpoint ≠ GS-Det endpoint: {endpoint_diff}
- Agent endpoint == GS-Det endpoint: {endpoint_same}

On 41 evaluable cases, decision changes vs Deterministic: BENEFICIAL {beneficial}, HARMFUL {harmful}, NEUTRAL {neutral}.

## 10. Error analysis

Post-hoc descriptive taxonomy only; not used for tuning.

GS-Agentic errors on evaluable cases: {sum(1 for r in eval_rows if r['gs_agent_correct'] is False)}
GS-Deterministic errors on evaluable cases: {sum(1 for r in eval_rows if r['gs_det_correct'] is False)}

See `M60_ERROR_TAXONOMY.csv`.

## 11. Limitations

- Primary accuracy uses 41 of 60 cases because 19 remained TRUTH_UNCERTAIN after independent adjudication and human review.
- rpoB has no independently resolved NEGATIVE truth, so rpoB specificity cannot be estimated.
- Specialist performance is a composite of two different tools (AMRFinderPlus for tetA; RefSeq/PGAP for rpoB).
- Wilson intervals and the paired bootstrap describe this locked 41-case denominator; they were not used to change the frozen protocol.
- Agent runtime includes local LLM latency and is not a proxy for follow-up-action count.
- Error taxonomy is post-hoc and must not be read as a licence to retune V4.1.

Final truth SHA256: `{EXPECTED['final_truth']}`
Prediction lock SHA256: `{EXPECTED['prediction_lock']}`
"""
    (OUT / "M60_FINAL_RESULTS.md").write_text(md, encoding="utf-8")

    integ_md = f"""# M60 final integrity statement

- System frozen before cohort selection: GENOME_SKEPTIC_V4_1_MANUSCRIPT
- Git commit: `{EXPECTED['git']}`
- Scientific-core hash: `{EXPECTED['scientific_core']}`
- System manifest SHA256: `{EXPECTED['system_manifest']}`
- Protocol v1.1 SHA256: `{EXPECTED['protocol_v11']}`
- Cohort frozen before prediction: M60 cohort SHA256 `{EXPECTED['cohort']}`
- Predictions locked before truth: prediction lock SHA256 `{EXPECTED['prediction_lock']}`
- Truth assigned without prediction access (Phase 3 lock unaltered)
- Human review occurred before unblinding (Phase 3B)
- Final truth SHA256: `{EXPECTED['final_truth']}`
- Final truth lock manifest SHA256: `{EXPECTED['final_truth_lock']}`
- No prediction regenerated
- No case replaced
- No post-selection tuning
- Uncertain cases excluded from primary accuracy according to frozen rules (19 TRUTH_UNCERTAIN; 41 evaluable)
- D20 untouched
- V4.1 not patched
- V4.2 not created from these results
- FINAL_UNBLIND_INTEGRITY_VERIFIED = YES
- Verified UTC: {integrity['verified_utc']}
"""
    (OUT / "M60_FINAL_INTEGRITY_STATEMENT.md").write_text(integ_md, encoding="utf-8")

    stop = {
        "FINAL_UNBLIND_COMPLETE": "YES",
        "TOTAL_CASES": 60,
        "TRUTH_EVALUABLE": f"{len(eval_rows)} / 60",
        "TRUTH_UNCERTAIN": 19,
        "CONVENTIONAL": summaries["conventional"]["correct_over_n"],
        "SPECIALIST": summaries["specialist"]["correct_over_n"],
        "GS_DETERMINISTIC": summaries["gs_det"]["correct_over_n"],
        "GS_AGENTIC": summaries["gs_agent"]["correct_over_n"],
        "GS_EXHAUSTIVE": summaries["gs_exh"]["correct_over_n"],
        "AGENT_vs_DET_ACCURACY_DIFFERENCE": diff_ad,
        "PAIRED_BOOTSTRAP_CI": fmt_ci(ci_ad),
        "DET_ERRORS_CORRECTED_BY_AGENT": len(C),
        "DET_CORRECT_CALLS_DEGRADED_BY_AGENT": len(B),
        "NET_CORRECTIONS": net,
        "EXACT_MCNEMAR_P": mcnemar_p if mcnemar_p is not None else "NA",
        "AGENT_FOLLOW_UP_ACTIONS": sum(a_actions),
        "EXHAUSTIVE_FOLLOW_UP_ACTIONS": sum(e_actions),
        "FOLLOW_UP_ACTION_REDUCTION_PERCENT": action_reduction,
        "AGENT_MEDIAN_RUNTIME": statistics.median(a_times),
        "EXHAUSTIVE_MEDIAN_RUNTIME": statistics.median(e_times),
        "TETA_AGENT": f"{sum(1 for r in tetA_rows if r['gs_agent_correct'])} / 26",
        "RPOB_AGENT": f"{rpob_k_agent} / 15",
        "ROUTINE_AGENT": f"{routine_k_agent} / {len(routine_rows)}",
        "CHALLENGE_AGENT": f"{challenge_k_agent} / {len(challenge_rows)}",
        "PREDICTIONS_REGENERATED": "NO",
        "POST_SELECTION_TUNING": "NO",
        "D20_TOUCHED": "NO",
        "MANUSCRIPT_RESULT_LOCKED": "YES",
    }
    write_json(OUT / "M60_PHASE4_STOP.json", stop)
    print(json.dumps(stop, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
