#!/usr/bin/env python3
"""Regenerate manuscript Figure 2 (60-case precursor) source panel from locked precursor CSVs.

Manuscript Figure 2 = precursor experiment (policy vs endpoint / efficiency).
Sources (paper_role_swap only):
  - results/precursor/M60_AGENT_VS_DETERMINISTIC.csv
  - results/precursor/M60_EFFICIENCY_RESULTS.csv

Renders a two-panel figure; source data written beside the PNG.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import REPRODUCED, RESULTS, write_csv  # noqa: E402


def main() -> int:
    agent = list(
        csv.DictReader((RESULTS / "precursor/M60_AGENT_VS_DETERMINISTIC.csv").open(encoding="utf-8"))
    )
    eff = list(csv.DictReader((RESULTS / "precursor/M60_EFFICIENCY_RESULTS.csv").open(encoding="utf-8")))

    # Preserve locked CSVs as figure source data
    write_csv(
        REPRODUCED / "figure2_source_agent_vs_det.csv",
        agent,
        list(agent[0].keys()) if agent else [],
    )
    write_csv(
        REPRODUCED / "figure2_source_efficiency.csv",
        eff,
        list(eff[0].keys()) if eff else [],
    )

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    # Panel A: try to plot endpoint-agreement style columns if present
    ax = axes[0]
    if agent:
        # Flexible column detection from locked CSV
        keys = list(agent[0].keys())
        label_key = keys[0]
        labels = [r[label_key] for r in agent]
        # Prefer a numeric agreement / same-endpoint column if present
        num_cols = [
            k
            for k in keys[1:]
            if all(_is_float(r.get(k)) for r in agent)
        ]
        if num_cols:
            vals = [float(r[num_cols[0]]) for r in agent]
            ax.bar(range(len(labels)), vals, color="#4C72B0")
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
            ax.set_title(num_cols[0])
        else:
            ax.text(0.5, 0.5, "See figure2_source_agent_vs_det.csv", ha="center", va="center")
            ax.set_axis_off()
    ax.set_title(ax.get_title() or "Precursor: agent vs deterministic")

    ax = axes[1]
    if eff:
        keys = list(eff[0].keys())
        label_key = keys[0]
        labels = [r[label_key] for r in eff]
        num_cols = [k for k in keys[1:] if all(_is_float(r.get(k)) for r in eff)]
        # Prefer follow-up-like column
        prefer = [k for k in num_cols if "follow" in k.lower() or "n_" in k.lower() or "count" in k.lower()]
        col = prefer[0] if prefer else (num_cols[0] if num_cols else None)
        if col:
            vals = [float(r[col]) for r in eff]
            ax.bar(range(len(labels)), vals, color="#55A868")
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
            ax.set_title(col)
        else:
            ax.text(0.5, 0.5, "See figure2_source_efficiency.csv", ha="center", va="center")
            ax.set_axis_off()
    ax.set_title(ax.get_title() or "Precursor: efficiency")

    fig.suptitle("Figure 2. Precursor 60-case experiment (locked source data)")
    fig.tight_layout()
    out = REPRODUCED / "figure2.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print("WROTE", out)
    return 0


def _is_float(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
