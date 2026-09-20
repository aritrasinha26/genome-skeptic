"""Copy agent-visible inputs into a sandbox that cannot see hidden truth."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from genome_skeptic.isolation import assert_agent_accessible


def make_sandbox(
    visible_case: Path,
    work_root: Path,
    hidden_root: Path | None = None,
    *,
    skip_reads: bool = False,
    reuse_existing: bool = True,
) -> Path:
    assert_agent_accessible(visible_case)
    sandbox = work_root / "sandbox" / visible_case.name
    if reuse_existing and (sandbox / "case.yaml").exists():
        return sandbox
    if sandbox.exists():
        shutil.rmtree(sandbox)
    ignore = shutil.ignore_patterns("*.fastq", "*.fastq.gz", "*.fq", "*.fq.gz") if skip_reads else None
    shutil.copytree(visible_case, sandbox, ignore=ignore)
    # Do not write the hidden-root path into the sandbox; that would leak it.
    return sandbox


def sandbox_env(hidden_root: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("GENOME_SKEPTIC_TRUTH", "GENOME_SKEPTIC_SOURCE_GENOME", "GENOME_SKEPTIC_TRUTH_MANIFEST"):
        env.pop(key, None)
    if hidden_root is not None:
        env["GENOME_SKEPTIC_HIDDEN_ROOTS"] = str(Path(hidden_root).resolve())
    return env
