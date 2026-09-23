#!/usr/bin/env python3
"""Regenerate manuscript Table 1 (frozen role-swap conditions) from locked defs + scores.

Manuscript Table 1 = frozen arm conditions.
Sources:
  - protocol/ARM_DEFINITIONS.md (arm roles)
  - regenerated headline scores from locked predictions (via _lib.compute_statistics)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import REPRODUCED, compute_statistics, write_csv  # noqa: E402


def main() -> int:
    pack = compute_statistics()
    scores = pack["arm_scores"]
    follow = pack["followups"]
    rows = [
        {
            "arm": "A",
            "label": "Fixed deterministic controller",
            "controller": "deterministic",
            "final_judge": "deterministic validator",
            "evidence_source": "own measurement trail",
            "correct_out_of_20": scores["A"]["correct"],
            "followups": follow["A"],
        },
        {
            "arm": "B",
            "label": "GPT-5.6 Sol controller",
            "controller": "gpt-5.6-sol (planner/critic)",
            "final_judge": "deterministic validator",
            "evidence_source": "own measurement trail",
            "correct_out_of_20": scores["B"]["correct"],
            "followups": follow["B"],
        },
        {
            "arm": "C",
            "label": "Exhaustive controller",
            "controller": "exhaustive eligible actions",
            "final_judge": "deterministic validator",
            "evidence_source": "own measurement trail",
            "correct_out_of_20": scores["C"]["correct"],
            "followups": follow["C"],
        },
        {
            "arm": "D",
            "label": "Sol final judge (role swap)",
            "controller": "none (no re-measurement)",
            "final_judge": "gpt-5.6-sol",
            "evidence_source": "exact Arm B final evidence state",
            "correct_out_of_20": scores["D"]["correct"],
            "followups": 0,
        },
        {
            "arm": "F",
            "label": "Jev controller",
            "controller": "jev-latest (Choice/Noul)",
            "final_judge": "deterministic validator",
            "evidence_source": "own measurement trail",
            "correct_out_of_20": scores["F"]["correct"],
            "followups": follow["F"],
        },
    ]
    # Arm E noted in protocol as numerically ≡ Arm D under this design
    rows.append(
        {
            "arm": "E",
            "label": "Sol full authority (≡ Arm D in this design)",
            "controller": "represented by Arm D",
            "final_judge": "gpt-5.6-sol",
            "evidence_source": "exact Arm B final evidence state",
            "correct_out_of_20": scores["D"]["correct"],
            "followups": 0,
        }
    )
    out = REPRODUCED / "table1.csv"
    write_csv(out, rows, list(rows[0].keys()))
    print("WROTE", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
