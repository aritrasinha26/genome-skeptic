#!/usr/bin/env python3
"""Verify manuscript numerical claims from LOCKED bundle artifacts only (no API)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

B = Path(__file__).resolve().parents[2]


def main() -> int:
    stats = json.loads((B / "results/statistics.json").read_text(encoding="utf-8"))
    eff = list(csv.DictReader((B / "results/controller_efficiency.csv").open(encoding="utf-8")))
    ev = list(csv.DictReader((B / "data/arm_b_vs_d_evidence_hashes.csv").open(encoding="utf-8")))
    locks = json.loads((B / "provenance/final_manifest.json").read_text(encoding="utf-8"))["locks"]
    by_arm = {r["arm"]: r for r in eff}

    checks = [
        ("Arm B correct 18/20", stats["arm_scores"]["B"]["correct"] == 18),
        ("Arm D correct 11/20", stats["arm_scores"]["D"]["correct"] == 11),
        ("corrections 0", stats["b_vs_d"]["sol_corrections"] == 0),
        ("degradations 7", stats["b_vs_d"]["sol_degradations"] == 7),
        ("ABSENT->UNRESOLVED 9", stats["b_vs_d"]["transitions"].get("ABSENT->UNRESOLVED") == 9),
        ("McNemar P 0.015625", abs(stats["b_vs_d"]["mcnemar"]["mcnemar_p"] - 0.015625) < 1e-12),
        ("paired diff -0.35", abs(stats["b_vs_d"]["paired_bootstrap_D_minus_B"]["diff_b_minus_a"] + 0.35) < 1e-9),
        ("followups A=57", int(float(by_arm["A"]["followups"])) == 57),
        ("followups B=39", int(float(by_arm["B"]["followups"])) == 39),
        ("followups C=74", int(float(by_arm["C"]["followups"])) == 74),
        ("Sol latency ~10.28", abs(float(by_arm["B"]["median_model_latency"]) - 10.2845) < 1e-6),
        ("Jev latency ~2.22", abs(float(by_arm["F"]["median_model_latency"]) - 2.2165) < 1e-6),
        ("B/D evidence 20/20", sum(1 for r in ev if r["hashes_equal"] == "True") == 20),
        ("prediction_lock pin", locks["prediction_lock"].startswith("1e8c3cb7")),
        ("truth_lock pin", locks["truth_lock"].startswith("a1f3a9c2")),
    ]
    ok = True
    for name, passed in checks:
        print(("PASS" if passed else "FAIL"), name)
        ok = ok and passed
    print("ALL_PASS" if ok else "SOME_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
