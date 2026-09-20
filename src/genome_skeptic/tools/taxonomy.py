"""Contig-level taxonomic classification.

Taxonomy is measured by an open-source classifier when a database is configured.
It is never inferred from reference-genome metadata or from the LLM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def taxonomy_tools_available() -> list[str]:
    found = []
    if available("kraken2"):
        found.append("kraken2")
    if available("sourmash"):
        found.append("sourmash")
    if available("centrifuge"):
        found.append("centrifuge")
    return found


def parse_kraken2_output(path: Path) -> dict[str, dict[str, Any]]:
    """Parse kraken2 tabular output (C/U, seqid, taxname, …)."""
    by_contig: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return by_contig
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        classified = parts[0] == "C"
        contig = parts[1]
        tax = parts[2]
        by_contig[contig] = {
            "classified": classified,
            "taxonomy": tax if classified else None,
            "tool": "kraken2",
            "raw": line[:500],
        }
    return by_contig


def parse_sourmash_csv(path: Path) -> dict[str, dict[str, Any]]:
    by_contig: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return by_contig
    lines = path.read_text().splitlines()
    if not lines:
        return by_contig
    header = [h.strip() for h in lines[0].split(",")]
    name_i = next((i for i, h in enumerate(header) if h in {"name", "query_name", "contig"}), 0)
    tax_i = next((i for i, h in enumerate(header) if "lineage" in h or h in {"taxonomy", "match_name"}), None)
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= name_i:
            continue
        contig = parts[name_i].strip().split()[0]
        tax = parts[tax_i].strip() if tax_i is not None and tax_i < len(parts) else None
        by_contig[contig] = {"classified": bool(tax), "taxonomy": tax or None, "tool": "sourmash"}
    return by_contig


def run_contig_taxonomy(contigs: Path, out_dir: Path, db: str | None, threads: int = 1) -> ToolResult:
    """Run kraken2 or sourmash when a database is present. Never invent taxonomy."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not db:
        return ToolResult(
            name="contig_taxonomy",
            stage="target_gene",
            ok=False,
            error="no taxonomy database was configured; contig taxonomy was not invented from reference metadata",
        )
    db_path = Path(db)
    if available("kraken2") and db_path.exists():
        report = out_dir / "kraken2.tsv"
        cmd = ["kraken2", "--db", str(db_path), "--threads", str(threads), "--output", str(report), str(contigs)]
        result = run_command("kraken2", "target_gene", cmd, out_dir)
        if result.ok:
            parsed = parse_kraken2_output(report)
            result.outputs["kraken2"] = str(report)
            result.metrics["by_contig"] = parsed
            result.metrics["n_classified"] = sum(1 for v in parsed.values() if v.get("classified"))
        return result
    if available("sourmash") and db_path.exists():
        csv_path = out_dir / "sourmash.csv"
        cmd = ["sourmash", "gather", str(contigs), str(db_path), "-o", str(csv_path)]
        result = run_command("sourmash", "target_gene", cmd, out_dir)
        if result.ok:
            parsed = parse_sourmash_csv(csv_path)
            result.outputs["sourmash"] = str(csv_path)
            result.metrics["by_contig"] = parsed
        return result
    return ToolResult(
        name="contig_taxonomy",
        stage="target_gene",
        ok=False,
        error="kraken2/sourmash not found or database missing; contig taxonomy was not invented",
    )
