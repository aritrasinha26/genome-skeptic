"""Read-supported contig-break analysis.

Proximity to a contig end is not evidence of truncation. When paired-end
mapping records are available, this module measures clips, mate-unmapped
reads, discordant pairs, and edge coverage. It never invents read support.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from genome_skeptic.coords import sam_pos_to_internal
from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def _parse_cigar_clip(cigar: str) -> tuple[int, int]:
    left = right = 0
    num = ""
    ops: list[tuple[int, str]] = []
    for ch in cigar or "*":
        if ch.isdigit():
            num += ch
            continue
        if num:
            ops.append((int(num), ch))
            num = ""
    if ops and ops[0][1] in {"S", "H"}:
        left = ops[0][0]
    if ops and ops[-1][1] in {"S", "H"}:
        right = ops[-1][0]
    return left, right


def parse_alignment_records(path: Path) -> list[dict[str, Any]]:
    """Parse SAM or a headerless SAM-like TSV (QNAME FLAG RNAME POS … CIGAR RNEXT)."""
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text().splitlines():
        if not line or line.startswith("@"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        try:
            flag = int(parts[1])
            pos = int(parts[3])
        except ValueError:
            continue
        records.append({
            "flag": flag,
            "rname": parts[2],
            "pos": pos,
            "cigar": parts[5] if len(parts) > 5 else "*",
            "rnext": parts[6] if len(parts) > 6 else "*",
        })
    return records


def analyze_locus_breaks(
    records: list[dict[str, Any]],
    *,
    contig_id: str,
    start: int,
    end: int,
    contig_length: int,
    edge_window: int = 80,
) -> dict[str, Any]:
    """Measure whether a locus is truncated by an unsupported contig break.

    Coordinates are 0-based half-open. Missing records yield ``not_run``.
    """
    provenance = {
        "created_by": "deterministic_break_analyzer",
        "notes": "LLM did not invent read support, clips, or mate status.",
    }
    if not records:
        return {
            "status": "not_run",
            "read_supported_break": None,
            "limitation": "no paired-end mapping records were available; read support was not invented",
            "provenance": provenance,
        }
    near_left = start <= edge_window
    near_right = (contig_length - end) <= edge_window
    if not near_left and not near_right:
        return {
            "status": "completed",
            "read_supported_break": False,
            "near_left": False,
            "near_right": False,
            "n_reads": 0,
            "provenance": provenance,
        }
    n = n_clip = n_mate_unmapped = n_discordant = 0
    for rec in records:
        if rec["rname"] != contig_id:
            continue
        aln_start = sam_pos_to_internal(rec["pos"])
        if aln_start < start - edge_window or aln_start >= end + edge_window:
            continue
        n += 1
        left_clip, right_clip = _parse_cigar_clip(str(rec.get("cigar") or "*"))
        if near_left and left_clip >= 5:
            n_clip += 1
        if near_right and right_clip >= 5:
            n_clip += 1
        flag = int(rec.get("flag") or 0)
        if flag & 8:
            n_mate_unmapped += 1
        rnext = rec.get("rnext") or "*"
        if rnext not in {"=", "*", contig_id} and rnext != contig_id:
            n_discordant += 1
    if n == 0:
        return {
            "status": "inconclusive",
            "read_supported_break": None,
            "near_left": near_left,
            "near_right": near_right,
            "n_reads": 0,
            "limitation": "mapping records exist but none covered the locus edge",
            "provenance": provenance,
        }
    clip_rate = n_clip / n
    mate_unmapped_rate = n_mate_unmapped / n
    discordant_rate = n_discordant / n
    supported = clip_rate >= 0.15 or mate_unmapped_rate >= 0.20 or discordant_rate >= 0.15
    return {
        "status": "completed",
        "read_supported_break": supported,
        "near_left": near_left,
        "near_right": near_right,
        "n_reads": n,
        "n_clipped": n_clip,
        "n_mate_unmapped": n_mate_unmapped,
        "n_discordant": n_discordant,
        "clip_rate": clip_rate,
        "mate_unmapped_rate": mate_unmapped_rate,
        "discordant_rate": discordant_rate,
        "provenance": provenance,
    }


def run_break_analysis(bam_or_sam: Path, out_dir: Path, loci: list[dict[str, Any]]) -> ToolResult:
    """Prefer samtools view; otherwise parse SAM directly. Never invent BAM metrics."""
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    command: list[str] = []
    if bam_or_sam.suffix == ".sam" or bam_or_sam.name.endswith(".sam"):
        records = parse_alignment_records(bam_or_sam)
        command = ["parse_sam", str(bam_or_sam)]
    elif available("samtools") and bam_or_sam.exists():
        sam_path = out_dir / "locus_reads.sam"
        cmd = ["samtools", "view", "-F", "256", str(bam_or_sam)]
        result = run_command("samtools_view", "mapping", cmd, out_dir)
        command = cmd
        if result.ok and result.stdout_path:
            Path(out_dir / "breaks_from_bam.sam").write_text(Path(result.stdout_path).read_text())
            records = parse_alignment_records(Path(result.stdout_path))
        elif sam_path.exists():
            records = parse_alignment_records(sam_path)
    elif bam_or_sam.exists():
        records = parse_alignment_records(bam_or_sam)
        command = ["parse_alignments", str(bam_or_sam)]
    by_locus = {}
    for locus in loci:
        key = f"{locus['contig']}:{locus['start']}-{locus['end']}"
        by_locus[key] = analyze_locus_breaks(
            records,
            contig_id=locus["contig"],
            start=int(locus["start"]),
            end=int(locus["end"]),
            contig_length=int(locus["contig_length"]),
        )
    return ToolResult(
        name="break_analysis",
        stage="mapping",
        ok=True,
        command=command,
        metrics={"by_locus": by_locus, "n_records": len(records)},
        outputs={"alignments": str(bam_or_sam) if bam_or_sam.exists() else None},
    )
