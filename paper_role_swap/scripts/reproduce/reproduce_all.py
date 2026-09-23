#!/usr/bin/env python3
"""Run all paper_role_swap locked-output reproduction steps and verify vs locked results.

No API calls. Paths relative to paper_role_swap/ only.
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import BUNDLE, REPRODUCED, RESULTS, compute_statistics, load_json  # noqa: E402

SCRIPTS = [
    "reproduce_statistics.py",
    "reproduce_table1.py",
    "reproduce_figure2.py",
    "reproduce_figure3.py",
    "reproduce_figure4.py",
]


def _near(a, b, tol=1e-9) -> bool:
    if a is None or b is None:
        return a == b
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def compare_claims() -> list[dict]:
    locked = load_json(RESULTS / "statistics.json")
    regen = load_json(REPRODUCED / "statistics.json")
    locked_eff = {
        r["arm"]: r
        for r in csv.DictReader((RESULTS / "controller_efficiency.csv").open(encoding="utf-8"))
    }
    regen_eff = {
        r["arm"]: r
        for r in csv.DictReader((REPRODUCED / "controller_efficiency.csv").open(encoding="utf-8"))
    }
    locked_head = {
        r["arm"]: r
        for r in csv.DictReader((RESULTS / "controller_summary.csv").open(encoding="utf-8"))
    }
    hash_rows = list(
        csv.DictReader((BUNDLE / "data/arm_b_vs_d_evidence_hashes.csv").open(encoding="utf-8"))
    )
    hash_ok = sum(1 for r in hash_rows if r["hashes_equal"] == "True")

    rows: list[dict] = []

    def add(name, regenerated, locked_val, ok=None, tol=1e-9):
        if ok is None:
            ok = _near(regenerated, locked_val, tol=tol)
        rows.append(
            {
                "claim": name,
                "regenerated": regenerated,
                "locked": locked_val,
                "status": "MATCH" if ok else "MISMATCH",
            }
        )

    for arm in ("A", "B", "C", "F"):
        add(
            f"Arm {arm} correct/20",
            regen["arm_scores"][arm]["correct"],
            locked["arm_scores"][arm]["correct"],
        )
    add("Arm D correct/20", regen["arm_scores"]["D"]["correct"], locked["arm_scores"]["D"]["correct"])

    add(
        "sensitivity B",
        regen["arm_scores"]["B"]["sensitivity"],
        locked["arm_scores"]["B"]["sensitivity"],
    )
    add(
        "specificity B",
        regen["arm_scores"]["B"]["specificity"],
        locked["arm_scores"]["B"]["specificity"],
    )
    add(
        "sensitivity D",
        regen["arm_scores"]["D"]["sensitivity"],
        locked["arm_scores"]["D"]["sensitivity"],
    )
    add(
        "specificity D",
        regen["arm_scores"]["D"]["specificity"],
        locked["arm_scores"]["D"]["specificity"],
    )
    add(
        "unresolved D",
        regen["arm_scores"]["D"]["unresolved"],
        locked["arm_scores"]["D"]["unresolved"],
    )

    lb = locked["b_vs_d"]
    rb = regen["b_vs_d"]
    add("B correct / D wrong", rb["b_correct_d_wrong"], lb["b_correct_d_wrong"])
    add("B wrong / D correct", rb["b_wrong_d_correct"], lb["b_wrong_d_correct"])
    add("sol_corrections", rb["sol_corrections"], lb["sol_corrections"])
    add("sol_degradations", rb["sol_degradations"], lb["sol_degradations"])
    add("ABSENT->UNRESOLVED", rb["transitions"].get("ABSENT->UNRESOLVED"), lb["transitions"].get("ABSENT->UNRESOLVED"))
    add("McNemar P", rb["mcnemar"]["mcnemar_p"], lb["mcnemar"]["mcnemar_p"], tol=1e-12)
    add(
        "paired_diff D-B",
        rb["paired_bootstrap_D_minus_B"]["diff_b_minus_a"],
        lb["paired_bootstrap_D_minus_B"]["diff_b_minus_a"],
        tol=1e-12,
    )
    add(
        "paired_CI_low",
        rb["paired_bootstrap_D_minus_B"]["ci_low"],
        lb["paired_bootstrap_D_minus_B"]["ci_low"],
        tol=1e-9,
    )
    add(
        "paired_CI_high",
        rb["paired_bootstrap_D_minus_B"]["ci_high"],
        lb["paired_bootstrap_D_minus_B"]["ci_high"],
        tol=1e-9,
    )

    for arm, label in [("A", "fixed"), ("B", "Sol"), ("C", "exhaustive"), ("F", "Jev")]:
        add(
            f"followups {label} ({arm})",
            int(regen_eff[arm]["followups"]),
            int(float(locked_eff[arm]["followups"])),
        )

    add(
        "Sol median latency",
        float(regen_eff["B"]["median_model_latency"]),
        float(locked_eff["B"]["median_model_latency"]),
    )
    add(
        "Jev median latency",
        float(regen_eff["F"]["median_model_latency"]),
        float(locked_eff["F"]["median_model_latency"]),
    )
    add(
        "Sol API cost",
        float(regen_eff["B"]["cost"]),
        float(locked_eff["B"]["cost"]),
    )
    add(
        "Jev API cost",
        float(regen_eff["F"]["cost"]),
        float(locked_eff["F"]["cost"]),
    )

    add("B/D evidence identity 20/20", hash_ok, 20)
    add(
        "identical_evidence_assert from preds",
        regen["evidence_identity"]["identical_evidence_assert_count"],
        20,
    )

    # Table 1 source: correct counts match locked headline
    table1 = list(csv.DictReader((REPRODUCED / "table1.csv").open(encoding="utf-8")))
    for row in table1:
        if row["arm"] == "E":
            continue
        add(
            f"Table1 Arm {row['arm']} correct",
            int(row["correct_out_of_20"]),
            int(float(locked_head[row["arm"]]["correct"])),
        )

    # Figure source data checks (not pixels)
    fig3 = {r["arm"]: r for r in csv.DictReader((REPRODUCED / "figure3_source.csv").open(encoding="utf-8"))}
    for arm in ("A", "B", "C", "F"):
        add(
            f"Fig3 source followups {arm}",
            int(fig3[arm]["followups"]),
            int(float(locked_eff[arm]["followups"])),
        )
    fig4 = {
        r["category"]: int(r["n"])
        for r in csv.DictReader((REPRODUCED / "figure4_source.csv").open(encoding="utf-8"))
    }
    add("Fig4 source corrections", fig4["corrections_B_wrong_D_correct"], lb["sol_corrections"])
    add("Fig4 source degradations", fig4["degradations_B_correct_D_wrong"], lb["sol_degradations"])

    # Precursor figure2 source files exist and non-empty
    f2a = REPRODUCED / "figure2_source_agent_vs_det.csv"
    f2b = REPRODUCED / "figure2_source_efficiency.csv"
    add("Fig2 precursor agent_vs_det source present", f2a.exists() and f2a.stat().st_size > 0, True)
    add("Fig2 precursor efficiency source present", f2b.exists() and f2b.stat().st_size > 0, True)

    return rows


def write_report(comparisons: list[dict]) -> str:
    mismatches = [c for c in comparisons if c["status"] != "MATCH"]
    status = "ALL_REPORTED_RESULTS_REPRODUCED" if not mismatches else "REPRODUCTION_MISMATCHES"
    lines = [
        "# Reproduction report",
        "",
        f"Status: **{status}**",
        "",
        "Primary path uses only files under `paper_role_swap/`. No Sol/Jev API calls.",
        "",
        "## Dependency paths (current generation)",
        "",
        "| Output | Locked inputs inside paper_role_swap |",
        "| --- | --- |",
        "| Statistics / McNemar / bootstrap CI | `data/prospective_truth.csv`, `data/locked_predictions/{A,B,C,D,F}/*`, `results/preunblind_behaviour.csv` |",
        "| Follow-up counts | sum of `followup_count` in locked predictions |",
        "| Latency / API cost | `results/preunblind_behaviour.csv` (locked pre-unblind) |",
        "| B↔D evidence identity | `data/arm_b_vs_d_evidence_hashes.csv` + D `identical_evidence_assert` |",
        "| Table 1 | `protocol/ARM_DEFINITIONS.md` roles + regenerated arm scores |",
        "| Figure 2 (precursor) | `results/precursor/M60_AGENT_VS_DETERMINISTIC.csv`, `M60_EFFICIENCY_RESULTS.csv` |",
        "| Figure 3 (efficiency) | regenerated follow-ups + preunblind latency/cost |",
        "| Figure 4 (role swap) | regenerated B vs D correction/degradation counts |",
        "",
        "## Numerical comparison vs locked results",
        "",
        "| claim | regenerated | locked | status |",
        "| --- | --- | --- | --- |",
    ]
    for c in comparisons:
        lines.append(
            f"| {c['claim']} | {c['regenerated']} | {c['locked']} | {c['status']} |"
        )
    lines.append("")
    lines.append(f"MATCH count: {sum(1 for c in comparisons if c['status']=='MATCH')} / {len(comparisons)}")
    if mismatches:
        lines.append("")
        lines.append("## Mismatches")
        for c in mismatches:
            lines.append(f"- {c['claim']}: regenerated={c['regenerated']} locked={c['locked']}")
    else:
        lines.append("")
        lines.append("All reported numerical claims MATCH locked manuscript source data.")
    lines.append("")
    (REPRODUCED / "REPRODUCTION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return status


def main() -> int:
    REPRODUCED.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    for name in SCRIPTS:
        print("RUN", name, flush=True)
        r = subprocess.run([sys.executable, str(here / name)], cwd=str(BUNDLE))
        if r.returncode != 0:
            print("FAIL", name, flush=True)
            return r.returncode

    comparisons = compare_claims()
    status = write_report(comparisons)
    print(status, flush=True)
    return 0 if status == "ALL_REPORTED_RESULTS_REPRODUCED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
