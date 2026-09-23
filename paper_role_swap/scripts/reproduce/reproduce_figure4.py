#!/usr/bin/env python3
"""Regenerate manuscript Figure 4 (identical-evidence role swap) from locked predictions.

Manuscript Figure 4 = Sol final-authority effect under identical Arm-B evidence.
Logic copied from score_role_swap_unblind.py FIGURE3 block.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import REPRODUCED, compute_statistics, write_csv  # noqa: E402


def main() -> int:
    pack = compute_statistics()
    corrections = pack["corrections"]
    degradations = pack["degradations"]
    both_correct = pack["both_correct"]
    both_wrong = pack["both_wrong"]

    source_rows = [
        {"category": "corrections_B_wrong_D_correct", "n": corrections},
        {"category": "degradations_B_correct_D_wrong", "n": degradations},
        {"category": "unchanged_correct", "n": both_correct},
        {"category": "unchanged_wrong", "n": both_wrong},
    ]
    write_csv(REPRODUCED / "figure4_source.csv", source_rows, ["category", "n"])

    fig, ax = plt.subplots(figsize=(7, 4))
    labels = [
        "Corrections\n(B wrong→D correct)",
        "Degradations\n(B correct→D wrong)",
        "Unchanged\ncorrect",
        "Unchanged\nwrong",
    ]
    vals = [corrections, degradations, both_correct, both_wrong]
    ax.bar(range(len(labels)), vals, color=["#55A868", "#C44E52", "#4C72B0", "#999999"])
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Cases (n=20)")
    ax.set_title("Figure 4. Sol final-authority effect (identical Arm-B evidence)")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.2, str(v), ha="center")
    fig.tight_layout()
    out = REPRODUCED / "figure4.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print("WROTE", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
