"""Production analysis stack for the real-genome benchmark.

The toy de Bruijn assembler is never used here. Missing tools are reported
as unavailable dimensions.
"""
from __future__ import annotations

from pathlib import Path

from genome_skeptic.tools.base import available, run_command

PRODUCTION_TOOLS = (
    "fastp", "spades.py", "quast.py", "minimap2", "samtools",
    "checkm2", "bakta", "mmseqs", "diamond", "hmmsearch",
    "kraken2", "sourmash", "wgsim", "FastTree", "fastqc",
)


def production_inventory() -> dict[str, bool]:
    return {name: available(name) for name in PRODUCTION_TOOLS}


def production_available(name: str) -> bool:
    return bool(available(name))


def spades_argv(
    r1: Path,
    r2: Path | None,
    out_dir: Path,
    threads: int,
    memory_gb: int,
    *,
    only_assembler: bool = False,
    kmers: str | None = None,
    careful: bool = False,
    isolate: bool = True,
) -> list[str]:
    """Build the SPAdes command. Defaults match the full-production isolate stack."""
    cmd = ["spades.py", "-1", str(r1)]
    if r2 and Path(r2).exists():
        cmd += ["-2", str(r2)]
    cmd += ["-o", str(out_dir), "-t", str(threads), "-m", str(memory_gb)]
    if only_assembler:
        cmd.append("--only-assembler")
    if kmers:
        cmd += ["-k", str(kmers)]
    if careful:
        cmd.append("--careful")
    elif isolate:
        cmd.append("--isolate")
    return cmd


def assemble_with_spades(
    r1: Path,
    r2: Path | None,
    out_dir: Path,
    threads: int = 4,
    memory_gb: int = 4,
    *,
    only_assembler: bool = False,
    kmers: str | None = None,
    careful: bool = False,
    isolate: bool = True,
) -> tuple[Path | None, dict]:
    """Run SPAdes. Does not fall back to the eval-only assembler."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not available("spades.py"):
        return None, {
            "ok": False,
            "unavailable": "spades.py",
            "note": "SPAdes was missing; the toy assembler was not substituted.",
        }
    cmd = spades_argv(
        r1, r2, out_dir, threads, memory_gb,
        only_assembler=only_assembler, kmers=kmers, careful=careful, isolate=isolate,
    )
    result = run_command("spades", "assembly", cmd, out_dir)
    log = out_dir / "spades.log"
    extra = {"log": str(log) if log.exists() else None}
    contigs = out_dir / "contigs.fasta"
    if result.ok and contigs.exists():
        return contigs, {"ok": True, "assembler": "SPAdes", "command": cmd, "contigs": str(contigs), **extra}
    alt = out_dir / "scaffolds.fasta"
    if alt.exists():
        return alt, {"ok": True, "assembler": "SPAdes", "command": cmd, "contigs": str(alt), **extra}
    return None, {
        "ok": False,
        "error": result.error or "SPAdes did not write contigs",
        "command": cmd,
        **extra,
    }


def maybe_fastp(r1: Path, r2: Path | None, out_dir: Path) -> tuple[Path, Path | None, dict]:
    """Clean reads with fastp when installed. Never invent a QC summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not available("fastp"):
        return r1, r2, {"ok": False, "unavailable": "fastp", "note": "QC dimension unavailable; raw reads used."}
    clean1 = out_dir / "clean_R1.fastq"
    json_path = out_dir / "fastp.json"
    html_path = out_dir / "fastp.html"
    cmd = ["fastp", "-i", str(r1), "-o", str(clean1), "-j", str(json_path), "-h", str(html_path)]
    clean2 = None
    if r2 and r2.exists():
        clean2 = out_dir / "clean_R2.fastq"
        cmd[3:3] = ["-I", str(r2), "-O", str(clean2)]
    result = run_command("fastp", "qc", cmd, out_dir)
    if result.ok and clean1.exists():
        return clean1, clean2 if clean2 and clean2.exists() else r2, {"ok": True, "tool": "fastp", "command": cmd}
    return r1, r2, {"ok": False, "error": result.error or "fastp failed", "note": "Raw reads used after fastp failure."}
