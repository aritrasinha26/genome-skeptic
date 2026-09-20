from __future__ import annotations

from pathlib import Path

from genome_skeptic.io_utils import fasta_stats
from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def run_quast(contigs: Path, out_dir: Path, threads: int) -> ToolResult:
    exe = "quast.py" if available("quast.py") else "quast" if available("quast") else None
    if not exe:
        stats = fasta_stats(contigs)
        return ToolResult(name="internal_fasta_stats", stage="assembly_qc", ok=True, outputs={"contigs": str(contigs)}, metrics=stats)
    cmd = [exe, str(contigs), "-o", str(out_dir), "-t", str(threads), "--silent"]
    result = run_command("quast", "assembly_qc", cmd, out_dir)
    if result.ok:
        result.metrics.update(fasta_stats(contigs))
        result.outputs["quast_report"] = str(out_dir / "report.tsv")
    return result
