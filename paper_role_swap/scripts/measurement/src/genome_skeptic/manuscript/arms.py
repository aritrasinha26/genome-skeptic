"""Manuscript analysis arms. Thin aliases over the shared V4.1 loop."""
from __future__ import annotations

from genome_skeptic.agents.assembly_loop_v4_1_dev import (
    POLICY_AGENTIC,
    POLICY_DETERMINISTIC,
    POLICY_EXHAUSTIVE,
    run_gs_agentic_v4_1,
    run_gs_deterministic_v4_1,
    run_gs_exhaustive_v4_1,
    run_skeptic_agentic_v4_1_dev,
)

ARM_RUNNERS = {
    POLICY_DETERMINISTIC: run_gs_deterministic_v4_1,
    POLICY_AGENTIC: run_gs_agentic_v4_1,
    POLICY_EXHAUSTIVE: run_gs_exhaustive_v4_1,
}

__all__ = [
    "ARM_RUNNERS",
    "POLICY_AGENTIC",
    "POLICY_DETERMINISTIC",
    "POLICY_EXHAUSTIVE",
    "run_gs_agentic_v4_1",
    "run_gs_deterministic_v4_1",
    "run_gs_exhaustive_v4_1",
    "run_skeptic_agentic_v4_1_dev",
]
