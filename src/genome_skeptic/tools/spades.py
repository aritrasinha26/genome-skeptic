from __future__ import annotations

from pathlib import Path

from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def run_spades(r1: Path, r2: Path | None, out_dir: Path, threads: int) -> ToolResult:
    exe = "spades.py" if available("spades.py") else "spades" if available("spades") else None
    if not exe:
        return ToolResult(name="spades", stage="assembly", ok=False, error="SPAdes not found")
    if r2:
        cmd = [exe, "-1", str(r1), "-2", str(r2), "--careful", "-t", str(threads), "-o", str(out_dir)]
    else:
        cmd = [exe, "-s", str(r1), "--careful", "-t", str(threads), "-o", str(out_dir)]
    result = run_command("spades", "assembly", cmd, out_dir)
    contigs = out_dir / "contigs.fasta"
    scaffolds = out_dir / "scaffolds.fasta"
    if result.ok and contigs.exists():
        result.outputs["contigs"] = str(contigs)
        if scaffolds.exists():
            result.outputs["scaffolds"] = str(scaffolds)
    elif result.ok:
        result.ok = False
        result.error = "SPAdes returned success but contigs.fasta is missing"
    return result
