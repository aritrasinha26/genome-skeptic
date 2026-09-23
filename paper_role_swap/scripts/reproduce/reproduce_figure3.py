#!/usr/bin/env python3
"""Regenerate manuscript Figure 3 (controller efficiency) from locked predictions + behaviour.

Manuscript Figure 3 = workflow controllers change analytical efficiency, not endpoints.
Logic copied from score_role_swap_unblind.py FIGURE4 block.
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
    follow = pack["followups"]
    beh = pack["beh"]
    arms4 = ["A", "B", "C", "F"]

    source_rows = []
    for a in arms4:
        source_rows.append(
            {
                "arm": a,
                "followups": follow[a],
                "median_model_latency": float(beh[a]["median_model_latency"] or 0),
                "total_api_cost": float(beh[a]["total_api_cost"] or 0),
            }
        )
    write_csv(REPRODUCED / "figure3_source.csv", source_rows, list(source_rows[0].keys()))

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5))
    axes[0].bar(arms4, [follow[a] for a in arms4], color="#4C72B0")
    axes[0].set_title("Follow-ups")
    axes[0].set_ylabel("Total")
    lats = [float(beh[a]["median_model_latency"] or 0) for a in arms4]
    axes[1].bar(arms4, lats, color="#55A868")
    axes[1].set_title("Median model latency (s)")
    costs = [float(beh[a]["total_api_cost"] or 0) for a in arms4]
    axes[2].bar(arms4, costs, color="#C44E52")
    axes[2].set_title("API cost (USD)")
    fig.suptitle("Figure 3. Controller efficiency (locked outputs)")
    fig.tight_layout()
    out = REPRODUCED / "figure3.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print("WROTE", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
