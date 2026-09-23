#!/usr/bin/env python3
"""Regenerate manuscript statistics from locked paper_role_swap artifacts only.

Source logic: scripts/scoring/score_role_swap_unblind.py (exact scoring functions).
Inputs (all under paper_role_swap/):
  - data/prospective_truth.csv
  - data/locked_predictions/{A,B,C,D,F}/RS*_prediction.json
  - results/preunblind_behaviour.csv  (latency/cost; locked pre-unblind)
  - data/arm_b_vs_d_evidence_hashes.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import REPRODUCED, compute_statistics, write_csv, write_json  # noqa: E402


def main() -> int:
    pack = compute_statistics()
    write_json(REPRODUCED / "statistics.json", pack["stats"])
    write_csv(
        REPRODUCED / "case_level_results.csv",
        pack["case_level"],
        list(pack["case_level"][0].keys()),
    )
    write_csv(
        REPRODUCED / "controller_efficiency.csv",
        pack["controller_efficiency"],
        list(pack["controller_efficiency"][0].keys()),
    )
    write_csv(
        REPRODUCED / "controller_summary.csv",
        pack["headline"],
        list(pack["headline"][0].keys()),
    )
    write_csv(
        REPRODUCED / "role_swap_summary.csv",
        pack["discordant"],
        list(pack["discordant"][0].keys()) if pack["discordant"] else ["case_id"],
    )
    print("WROTE", REPRODUCED / "statistics.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
