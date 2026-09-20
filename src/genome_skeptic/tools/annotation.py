from __future__ import annotations

import os
from pathlib import Path

from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def run_annotation(contigs: Path, out_dir: Path, threads: int, bakta_db: str | None = None) -> ToolResult:
    if available("bakta") and bakta_db:
        cmd = ["bakta", "--db", bakta_db, "--threads", str(threads), "--output", str(out_dir), str(contigs)]
        result = run_command("bakta", "annotation", cmd, out_dir)
        if result.ok:
            gffs = list(out_dir.glob("*.gff3")) + list(out_dir.glob("*.gff"))
            faas = list(out_dir.glob("*.faa"))
            ffns = list(out_dir.glob("*.ffn"))
            if gffs:
                result.outputs["gff"] = str(gffs[0])
            if faas:
                result.outputs["proteins"] = str(faas[0])
            if ffns:
                result.outputs["genes"] = str(ffns[0])
        return result
    if not available("prodigal"):
        return ToolResult(name="annotation", stage="annotation", ok=False, error="Bakta+database or Prodigal required")
    out_dir.mkdir(parents=True, exist_ok=True)
    gff = out_dir / "genes.gff"
    proteins = out_dir / "proteins.faa"
    genes = out_dir / "genes.fna"
    cmd = ["prodigal", "-i", str(contigs), "-o", str(gff), "-a", str(proteins), "-d", str(genes), "-f", "gff"]
    result = run_command("prodigal", "annotation", cmd, out_dir)
    if result.ok:
        result.outputs = {"gff": str(gff), "proteins": str(proteins), "genes": str(genes)}
    return result
