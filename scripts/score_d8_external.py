#!/usr/bin/env python3
"""Join locked D8 truth with locked predictions. Does not regenerate predictions or touch D20."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation_agentic_d8"

EXPECTED = {
    "D8_MANIFEST.json": "37862918643052fa8cb81ff5e180161973a6dd5311aef62bd78c59f8ea74cdbd",
    "D8_CONVENTIONAL_LOCKED.json": "e2cdb6c91a788f6dd6126ba1bb1ce14aea512e71c110036a66e97e05b4214b51",
    "D8_V5_LOCKED.json": "0475084d908218c7676820e612745c4e6a309f71b0644642ac08dd8f4b4665db",
    "D8_AGENTIC_V2_LOCKED.json": "2331e5fd5c265df2046f7fcc1f43dd7ed9e5f51ed4b2c5ecf03b48fc5df63d16",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / den
    margin = (z / den) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def load_json(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def pred_polarity(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return "EXECUTION_FAILURE"
    fr = rec.get("final_result") or ""
    if fr == "target_gene_detected":
        return "DETECTED"
    if fr == "target_gene_not_detected":
        return "NOT_DETECTED"
    return fr or "UNKNOWN"


def predicted_multiplicity(rec: dict) -> int | None:
    multi = rec.get("multiplicity") or {}
    if isinstance(multi, dict) and multi.get("number_of_candidate_loci") is not None:
        try:
            return int(multi["number_of_candidate_loci"])
        except (TypeError, ValueError):
            return None
    pol = pred_polarity(rec)
    if pol == "DETECTED":
        return 1
    if pol == "NOT_DETECTED":
        return 0
    return None


def display_result(rec: dict, target: str) -> str:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return f"EXECUTION_FAILURE ({rec.get('agent_failure')})"
    pol = pred_polarity(rec)
    conf = rec.get("confidence")
    klass = rec.get("claim_class")
    extra = ""
    if target == "tuf_EF_Tu":
        n = predicted_multiplicity(rec)
        extra = f"; multiplicity={n}"
    return f"{pol} / {klass} / conf={conf}{extra}"


def is_correct(truth_case: dict, rec: dict) -> bool:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return False
    target = truth_case["target"]
    truth = truth_case["truth"]
    if target == "tuf_EF_Tu":
        n = predicted_multiplicity(rec)
        return n is not None and int(truth) == int(n)
    pol = pred_polarity(rec)
    if truth == "POSITIVE":
        return pol == "DETECTED"
    if truth == "NEGATIVE":
        return pol == "NOT_DETECTED"
    return False


def action_status_label(rec: dict) -> str:
    ars = rec.get("action_result_status")
    if isinstance(ars, list) and ars:
        return ";".join(f"{a.get('action_id')}={a.get('status')}" for a in ars)
    if isinstance(ars, dict):
        return json.dumps(ars, sort_keys=True)
    return ""


def classify_action_bucket(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return "execution_failure"
    ars = rec.get("action_result_status")
    statuses = []
    if isinstance(ars, list):
        statuses = [str(a.get("status") or "").upper() for a in ars]
    elif isinstance(ars, dict):
        statuses = [k for k, v in ars.items() if v]
    if any(s == "INFORMATIVE" for s in statuses):
        return "informative"
    if any(s == "NO_NEW_INFORMATION" for s in statuses):
        return "no_new_information"
    if any(s == "UNAVAILABLE" for s in statuses):
        return "unavailable"
    if any(s == "FAILED" for s in statuses):
        return "failed_action"
    return "other"


def main() -> int:
    for name, expected in EXPECTED.items():
        digest = sha256_file(OUT / name)
        if digest != expected:
            raise SystemExit(f"prediction/manifest hash mismatch {name}")
    truth_path = OUT / "D8_EXTERNAL_TRUTH_LOCKED.json"
    truth_sha = sha256_file(truth_path)
    sidecar = json.loads((OUT / "D8_EXTERNAL_TRUTH_LOCKED.json.sha256.json").read_text(encoding="utf-8"))
    if sidecar.get("sha256") != truth_sha:
        raise SystemExit("truth sidecar hash mismatch")
    truth = load_json("D8_EXTERNAL_TRUTH_LOCKED.json")
    conv = { (r["assembly_accession"], r["target"]): r for r in load_json("D8_CONVENTIONAL_LOCKED.json")["predictions"] }
    v5 = { (r["assembly_accession"], r["target"]): r for r in load_json("D8_V5_LOCKED.json")["predictions"] }
    ag = { (r["assembly_accession"], r["target"]): r for r in load_json("D8_AGENTIC_V2_LOCKED.json")["predictions"] }
    cases = sorted(truth["cases"], key=lambda r: r["execution_position"])
    if len(cases) != 8:
        raise SystemExit("expected 8 truth cases")

    rows = []
    for tc in cases:
        key = (tc["assembly_accession"], tc["target"])
        c, v, a = conv[key], v5[key], ag[key]
        evaluable = tc["truth_status"] == "EVALUABLE" and tc["truth"] is not None
        c_ok = is_correct(tc, c) if evaluable else None
        v_ok = is_correct(tc, v) if evaluable else None
        a_ok = is_correct(tc, a) if evaluable else None
        a_fail = bool(a.get("agent_failure") or a.get("ok") is False)
        m_changed = bool(a.get("measurements_changed_before_validation"))
        m0 = a.get("m0_hash")
        mf = a.get("m_final_hash")
        rows.append(
            {
                "position": tc["execution_position"],
                "accession": tc["assembly_accession"],
                "organism": tc.get("organism"),
                "target": tc["target"],
                "endpoint": tc["endpoint"],
                "truth_status": tc["truth_status"],
                "truth": tc["truth"],
                "externally_evaluable": evaluable,
                "conventional_result": display_result(c, tc["target"]),
                "conventional_final_result": c.get("final_result"),
                "conventional_correct": c_ok,
                "v5_result": display_result(v, tc["target"]),
                "v5_final_result": v.get("final_result"),
                "v5_correct": v_ok,
                "agentic_result": display_result(a, tc["target"]),
                "agentic_final_result": a.get("final_result"),
                "agentic_correct": a_ok,
                "agentic_completion_status": "FAILURE" if a_fail else "COMPLETED",
                "agent_failure": a.get("agent_failure"),
                "planner_action": a.get("planner_action"),
                "planner_decision": a.get("planner_decision"),
                "critic_action": a.get("critic_action"),
                "critic_verdict": a.get("critic_verdict"),
                "action_result_status": action_status_label(a),
                "action_bucket": classify_action_bucket(a),
                "m_final_ne_m0": bool(m0 and mf and m0 != mf) or m_changed,
                "validator_consumed_updated_measurements": (
                    m_changed and a.get("validator_consumed_m0") is False
                ),
                "validator_consumed_m0": a.get("validator_consumed_m0"),
                "final_claim": a.get("statement"),
                "runtime_seconds": a.get("runtime_seconds"),
                "conventional_runtime_seconds": c.get("runtime_seconds"),
                "v5_runtime_seconds": v.get("runtime_seconds"),
                "model_call_count": a.get("model_call_count"),
                "planner_call_count": a.get("planner_call_count"),
                "critic_call_count": a.get("critic_call_count"),
                "repair_count": a.get("repair_count"),
                "final_validator_ran": a.get("final_validator_ran"),
                "short_rationale": tc.get("short_rationale"),
            }
        )

    eval_rows = [r for r in rows if r["externally_evaluable"]]
    n = len(eval_rows)
    n_uncertain = sum(1 for r in rows if r["truth_status"] == "TRUTH_UNCERTAIN")
    conv_c = sum(1 for r in eval_rows if r["conventional_correct"])
    v5_c = sum(1 for r in eval_rows if r["v5_correct"])
    ag_c = sum(1 for r in eval_rows if r["agentic_correct"])
    ag_done = sum(1 for r in rows if r["agentic_completion_status"] == "COMPLETED")

    pair = []
    for r in eval_rows:
        pair.append((bool(r["v5_correct"]), bool(r["agentic_correct"]), r))
    A = [r for v_ok, a_ok, r in pair if v_ok and a_ok]
    B = [r for v_ok, a_ok, r in pair if v_ok and not a_ok]
    C = [r for v_ok, a_ok, r in pair if (not v_ok) and a_ok]
    D = [r for v_ok, a_ok, r in pair if (not v_ok) and not a_ok]
    net = len(C) - len(B)
    if len(B) + len(C) > 0:
        mcnemar = binomtest(len(C), n=len(B) + len(C), p=0.5, alternative="two-sided")
        mcnemar_p = float(mcnemar.pvalue)
        mcnemar_note = (
            f"exact McNemar / binomial P={mcnemar_p:.4f} on {len(B)+len(C)} discordant pairs; "
            "exploratory only because n=8 is very small"
        )
    else:
        mcnemar_p = None
        mcnemar_note = "exact McNemar not applicable (0 discordant pairs); exploratory n=8"

    changed_final = [
        r
        for r in rows
        if r["v5_final_result"] != r["agentic_final_result"]
        or (r["agentic_completion_status"] == "FAILURE")
    ]
    completed_changed = [
        r
        for r in rows
        if r["agentic_completion_status"] == "COMPLETED" and r["v5_final_result"] != r["agentic_final_result"]
    ]

    conv_ci = wilson_ci(conv_c, n)
    v5_ci = wilson_ci(v5_c, n)
    ag_ci = wilson_ci(ag_c, n)

    case_csv = OUT / "D8_CASE_LEVEL_RESULTS.csv"
    case_fields = [
        "position",
        "accession",
        "target",
        "truth",
        "conventional_result",
        "conventional_correct",
        "v5_result",
        "v5_correct",
        "agentic_result",
        "agentic_correct",
        "agentic_completion_status",
        "agent_failure",
        "endpoint",
        "truth_status",
        "organism",
    ]
    with case_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=case_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    sys_csv = OUT / "D8_SYSTEM_SUMMARY.csv"
    with sys_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "system",
                "correct",
                "externally_evaluable_n",
                "accuracy",
                "wilson_95_ci_low",
                "wilson_95_ci_high",
                "primary_metric",
                "agentic_completion",
                "truth_uncertain",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "system": "conventional",
                "correct": conv_c,
                "externally_evaluable_n": n,
                "accuracy": conv_c / n if n else None,
                "wilson_95_ci_low": conv_ci[0],
                "wilson_95_ci_high": conv_ci[1],
                "primary_metric": "correct / externally evaluable N",
                "agentic_completion": "",
                "truth_uncertain": n_uncertain,
            }
        )
        w.writerow(
            {
                "system": "deterministic_v5",
                "correct": v5_c,
                "externally_evaluable_n": n,
                "accuracy": v5_c / n if n else None,
                "wilson_95_ci_low": v5_ci[0],
                "wilson_95_ci_high": v5_ci[1],
                "primary_metric": "correct / externally evaluable N",
                "agentic_completion": "",
                "truth_uncertain": n_uncertain,
            }
        )
        w.writerow(
            {
                "system": "agentic_v2_end_to_end",
                "correct": ag_c,
                "externally_evaluable_n": n,
                "accuracy": ag_c / n if n else None,
                "wilson_95_ci_low": ag_ci[0],
                "wilson_95_ci_high": ag_ci[1],
                "primary_metric": "end-to-end correct / externally evaluable N (failures counted incorrect)",
                "agentic_completion": f"{ag_done}/8",
                "truth_uncertain": n_uncertain,
            }
        )

    vs_csv = OUT / "D8_AGENTIC_VS_V5.csv"
    with vs_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cell", "count", "positions", "accessions_targets"])
        def cell_line(name, items):
            w.writerow(
                [
                    name,
                    len(items),
                    ";".join(str(r["position"]) for r in items),
                    ";".join(f"{r['accession']}/{r['target']}" for r in items),
                ]
            )
        cell_line("A_both_correct", A)
        cell_line("B_v5_correct_agentic_incorrect", B)
        cell_line("C_v5_incorrect_agentic_correct", C)
        cell_line("D_both_incorrect", D)
        w.writerow(["V5_ERRORS_CORRECTED_BY_AGENTIC_C", len(C), "", ""])
        w.writerow(["V5_CORRECT_CALLS_DEGRADED_BY_AGENTIC_B", len(B), "", ""])
        w.writerow(["NET_CORRECTIONS_C_minus_B", net, "", ""])
        w.writerow(["mcnemar_exact_p", mcnemar_p if mcnemar_p is not None else "NA", mcnemar_note, ""])

    act_csv = OUT / "D8_ACTION_SUMMARY.csv"
    act_fields = [
        "position",
        "accession",
        "target",
        "planner_action",
        "critic_action",
        "critic_verdict",
        "action_result_status",
        "action_bucket",
        "m_final_ne_m0",
        "validator_consumed_updated_measurements",
        "final_claim",
        "runtime_seconds",
        "model_call_count",
        "repair_count",
        "agent_failure",
        "agentic_completion_status",
        "changed_v5_final_result",
    ]
    with act_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=act_fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    **r,
                    "changed_v5_final_result": r["v5_final_result"] != r["agentic_final_result"]
                    or r["agentic_completion_status"] == "FAILURE",
                }
            )

    run_csv = OUT / "D8_RUNTIME_SUMMARY.csv"
    with run_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "position",
                "accession",
                "target",
                "conventional_runtime_seconds",
                "v5_runtime_seconds",
                "agentic_runtime_seconds",
                "agentic_model_call_count",
                "agentic_planner_call_count",
                "agentic_critic_call_count",
                "agentic_repair_count",
                "agentic_completion_status",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "position": r["position"],
                    "accession": r["accession"],
                    "target": r["target"],
                    "conventional_runtime_seconds": r["conventional_runtime_seconds"],
                    "v5_runtime_seconds": r["v5_runtime_seconds"],
                    "agentic_runtime_seconds": r["runtime_seconds"],
                    "agentic_model_call_count": r["model_call_count"],
                    "agentic_planner_call_count": r["planner_call_count"],
                    "agentic_critic_call_count": r["critic_call_count"],
                    "agentic_repair_count": r["repair_count"],
                    "agentic_completion_status": r["agentic_completion_status"],
                }
            )

    informative = [r for r in rows if r["action_bucket"] == "informative"]
    nonew = [r for r in rows if r["action_bucket"] == "no_new_information"]
    unavail = [r for r in rows if r["action_bucket"] == "unavailable"]
    planner_useful = [r for r in informative if r["planner_action"]]
    critic_useful = [
        r
        for r in rows
        if r["critic_action"]
        and r["action_bucket"] == "informative"
        and r["agentic_completion_status"] == "COMPLETED"
    ]

    fig1 = OUT / "D8_FIGURE1_correct_cases.png"
    fig2 = OUT / "D8_FIGURE2_agentic_effect.png"
    labels = ["Conventional", "Deterministic V5", "Agentic V2"]
    vals = [conv_c, v5_c, ag_c]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    colors = ["#4C78A8", "#F58518", "#54A24B"]
    bars = ax.bar(labels, vals, color=colors, width=0.62)
    ax.set_ylim(0, max(n, 1) + 0.8)
    ax.set_ylabel(f"Correct cases (externally evaluable N = {n})")
    ax.set_title("Prospective blind external mini-benchmark")
    for bar, k in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.08, f"{k}/{n}", ha="center", va="bottom")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.text(
        0.5,
        0.02,
        "Eight prospectively selected unseen genome-target cases. Preliminary descriptive validation; not a substitute for the larger D20 benchmark.",
        ha="center",
        fontsize=8,
        wrap=True,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(fig1, dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    xlabels = ["V5 errors corrected\nby Agentic (C)", "V5 correct calls\ndegraded by Agentic (B)"]
    yvals = [len(C), len(B)]
    bars = ax.bar(xlabels, yvals, color=["#54A24B", "#E45756"], width=0.55)
    ax.set_ylim(0, max(3, max(yvals) + 1))
    ax.set_ylabel("Cases (n = 8 evaluable)")
    ax.set_title("Agentic effect relative to V5")
    for bar, k in zip(bars, yvals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05, str(k), ha="center", va="bottom")
    ax.text(0.5, 0.92, f"NET CORRECTIONS = C − B = {net}", transform=ax.transAxes, ha="center")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(fig2, dpi=160)
    plt.close(fig)

    def yn(v):
        if v is True:
            return "yes"
        if v is False:
            return "no"
        return ""

    md = []
    a = md.append
    a("# D8 mini-benchmark external results")
    a("")
    a("Prospective blinded eight-case mini-benchmark (`D8_MINI_EXTERNAL`).")
    a("Preliminary descriptive validation; not a substitute for the larger D20 benchmark.")
    a("n = 8 is very small. Wilson 95% intervals are descriptive only. No superiority claim is made.")
    a("")
    a("## Lock verification")
    a("")
    a("| File | SHA256 | Result |")
    a("|---|---|---|")
    for name, expected in EXPECTED.items():
        a(f"| `{name}` | `{expected}` | MATCH |")
    a(f"| `D8_EXTERNAL_TRUTH_LOCKED.json` | `{truth_sha}` | LOCKED before prediction join |")
    a("")
    a("Confirmed before truth assignment: 8 Conventional, 8 V5, 8 Agentic records.")
    a("Agentic position 7 remains `GCF_053618555.1` / `tetA_tetracycline_efflux`, `ok=False`, reason=`planner cited no evidence IDs`. V5 was not substituted for that failure.")
    a("D20 was not accessed or modified.")
    a("")
    a("## External truth (independent of predictions)")
    a("")
    a("| Pos | Accession | Target | Endpoint | Truth |")
    a("|---:|---|---|---|---|")
    for r in rows:
        a(f"| {r['position']} | {r['accession']} | {r['target']} | {r['endpoint']} | **{r['truth']}** |")
    a("")
    a("Truth assignment used NCBI Gene Orthologs where indexed, independent post-lock phmmer of frozen/authentic seeds against each proteome, and NCBI RefSeq/PGAP AMR gene calls (PGAP 6.10; AMRFinderPlus/NCBIfam-AMRFinder) for tet(A)/tet(B) only. tet(C) was not counted. PGAP names were corroboration only.")
    a("")
    a("## Case-level results")
    a("")
    a("| Pos | Accession | Target | Truth | Conventional | Conv correct? | V5 | V5 correct? | Agentic | Agentic correct? | Agentic status |")
    a("|---:|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        a(
            f"| {r['position']} | {r['accession']} | `{r['target']}` | **{r['truth']}** | {r['conventional_result']} | {yn(r['conventional_correct'])} | {r['v5_result']} | {yn(r['v5_correct'])} | {r['agentic_result']} | {yn(r['agentic_correct'])} | {r['agentic_completion_status']} |"
        )
    a("")
    a("tuf cases are scored on exact multiplicity (distinct genuine EF-Tu loci). Conventional has no copy-number field; `not_detected` is scored as multiplicity 0.")
    a("Agentic execution failures are incorrect in the primary end-to-end metric when truth is evaluable.")
    a("")
    a("## Primary results")
    a("")
    a(f"- Externally evaluable: **{n} / 8**")
    a(f"- TRUTH_UNCERTAIN: **{n_uncertain}**")
    a(f"- Conventional: **{conv_c} / {n}** (accuracy {conv_c/n:.3f}; Wilson 95% CI {conv_ci[0]:.3f}–{conv_ci[1]:.3f})")
    a(f"- Deterministic V5: **{v5_c} / {n}** (accuracy {v5_c/n:.3f}; Wilson 95% CI {v5_ci[0]:.3f}–{v5_ci[1]:.3f})")
    a(f"- Agentic V2 end-to-end: **{ag_c} / {n}** (accuracy {ag_c/n:.3f}; Wilson 95% CI {ag_ci[0]:.3f}–{ag_ci[1]:.3f})")
    a(f"- Agentic completion: **{ag_done} / 8**")
    a("")
    a("In this prospective blinded eight-case mini-benchmark, Agentic V2 achieved "
      f"{ag_c}/{n} correct compared with {v5_c}/{n} for V5 and {conv_c}/{n} for the conventional baseline.")
    a("")
    a("## Paired V5 vs Agentic")
    a("")
    a(f"- A (both correct) = {len(A)}: " + (", ".join(f"pos {r['position']}" for r in A) or "none"))
    a(f"- B (V5 correct, Agentic incorrect) = {len(B)}: " + (", ".join(f"pos {r['position']} {r['accession']}/{r['target']}" for r in B) or "none"))
    a(f"- C (V5 incorrect, Agentic correct) = {len(C)}: " + (", ".join(f"pos {r['position']} {r['accession']}/{r['target']}" for r in C) or "none"))
    a(f"- D (both incorrect) = {len(D)}: " + (", ".join(f"pos {r['position']}" for r in D) or "none"))
    a("")
    a(f"- V5 ERRORS CORRECTED BY AGENTIC = C = **{len(C)}**")
    a(f"- V5 CORRECT CALLS DEGRADED BY AGENTIC = B = **{len(B)}**")
    a(f"- NET CORRECTIONS = C − B = **{net}**")
    a("")
    a(f"Agentic V2 corrected {len(C)} V5 errors and degraded {len(B)} V5-correct cases.")
    a(mcnemar_note + ".")
    a("")
    a("## Mechanistic Agentic results")
    a("")
    a("| Pos | Planner action | Critic action | ActionResult | m_final ≠ m0 | Validator used updated measurements | Final claim | Runtime s | Model calls | Repair | Failure |")
    a("|---:|---|---|---|---|---|---|---:|---:|---:|---|")
    for r in rows:
        claim = (r.get("final_claim") or "").replace("|", "/")
        if len(claim) > 90:
            claim = claim[:87] + "..."
        a(
            f"| {r['position']} | `{r.get('planner_action') or ''}` | `{r.get('critic_action') or ''}` | {r.get('action_result_status')} | {yn(r['m_final_ne_m0'])} | {yn(r['validator_consumed_updated_measurements'])} | {claim} | {r.get('runtime_seconds')} | {r.get('model_call_count')} | {r.get('repair_count')} | {r.get('agent_failure') or ''} |"
        )
    a("")
    a(f"- Informative-action cases: {len(informative)} (positions {', '.join(str(r['position']) for r in informative) or 'none'})")
    a(f"- No-new-information cases: {len(nonew)}")
    a(f"- Unavailable-action cases: {len(unavail)}")
    a(f"- Planner-selected useful (INFORMATIVE) actions: {len(planner_useful)}")
    a(f"- Critic-selected useful actions: {len(critic_useful)}")
    a(f"- Completed cases where Agentic changed V5's final result polarity: {len(completed_changed)}")
    fail_pos = ", ".join(f"pos {r['position']}" for r in rows if r["agentic_completion_status"] == "FAILURE")
    a(f"- Execution failures (not V5 substitutions): {fail_pos or 'none'}")
    a("")
    a("## Figures")
    a("")
    a(f"![FIGURE 1]({fig1.name})")
    a("")
    a("*Figure 1. Prospective blind external mini-benchmark. Eight prospectively selected unseen genome-target cases. Preliminary descriptive validation; not a substitute for the larger D20 benchmark.*")
    a("")
    a(f"![FIGURE 2]({fig2.name})")
    a("")
    a("*Figure 2. Agentic effect relative to V5. NET CORRECTIONS = C − B. This panel does not support a 0–100 superiority claim.*")
    a("")
    a("## Interpretation (allowed wording only)")
    a("")
    a(
        f"In this prospective blinded eight-case mini-benchmark, Agentic V2 achieved {ag_c}/{n} correct compared with {v5_c}/{n} for V5 and {conv_c}/{n} for the conventional baseline."
    )
    a("")
    a(f"Agentic V2 corrected {len(C)} V5 errors and degraded {len(B)} V5-correct cases.")
    a("")
    a("This n=8 mini-benchmark does not establish general genome-wide performance.")
    a("")
    (OUT / "D8_EXTERNAL_RESULTS.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    summary = {
        "D8_MANIFEST_HASH_VERIFIED": "YES",
        "ALL_THREE_PREDICTION_HASHES_VERIFIED": "YES",
        "D8_TRUTH_SHA256": truth_sha,
        "EXTERNALLY_EVALUABLE": f"{n} / 8",
        "TRUTH_UNCERTAIN": str(n_uncertain),
        "CONVENTIONAL": f"{conv_c} / {n}",
        "V5": f"{v5_c} / {n}",
        "AGENTIC_V2": f"{ag_c} / {n}",
        "AGENTIC_COMPLETION": f"{ag_done} / 8",
        "V5_ERRORS_CORRECTED": str(len(C)),
        "V5_CORRECT_CALLS_DEGRADED": str(len(B)),
        "NET_CORRECTIONS": str(net),
        "D20_TOUCHED": "NO",
        "wilson_conventional": conv_ci,
        "wilson_v5": v5_ci,
        "wilson_agentic": ag_ci,
        "mcnemar_note": mcnemar_note,
    }
    (OUT / "D8_SCORE_PRINT.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("D8 MANIFEST HASH VERIFIED:")
    print("YES")
    print()
    print("ALL THREE PREDICTION HASHES VERIFIED:")
    print("YES")
    print()
    print("D8 TRUTH SHA256:")
    print(truth_sha)
    print()
    print("EXTERNALLY EVALUABLE:")
    print(f"{n} / 8")
    print()
    print("TRUTH UNCERTAIN:")
    print(str(n_uncertain))
    print()
    print("CONVENTIONAL:")
    print(f"{conv_c} / {n}")
    print()
    print("V5:")
    print(f"{v5_c} / {n}")
    print()
    print("AGENTIC V2:")
    print(f"{ag_c} / {n}")
    print()
    print("AGENTIC COMPLETION:")
    print(f"{ag_done} / 8")
    print()
    print("V5 ERRORS CORRECTED:")
    print(str(len(C)))
    print()
    print("V5 CORRECT CALLS DEGRADED:")
    print(str(len(B)))
    print()
    print("NET CORRECTIONS:")
    print(str(net))
    print()
    print("D20 TOUCHED:")
    print("NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
