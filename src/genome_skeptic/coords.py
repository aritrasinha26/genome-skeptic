"""Internal genomic coordinate convention.

All in-memory interval coordinates in Genome Skeptic are **0-based, half-open**
``[start, end)`` on the forward strand of the named contig.

GFF3/GTF files use **1-based, fully closed** ``[start, end]``. Conversion
happens only at parse/write boundaries. Homology hits, depth windows, synteny
intervals, and locus evidence use the internal convention.

SAM/BAM POS fields are 1-based. Map them with :func:`sam_pos_to_internal`
before comparing to hit coordinates.
"""
from __future__ import annotations

COORDINATE_CONVENTION = "0-based-half-open"
GFF_COORDINATE_CONVENTION = "1-based-closed"
SAM_COORDINATE_CONVENTION = "1-based-closed-start"


def gff_to_internal(gff_start: int, gff_end: int) -> tuple[int, int]:
    """Convert GFF3 1-based inclusive coordinates to 0-based half-open."""
    if gff_start < 1 or gff_end < gff_start:
        raise ValueError(f"Invalid GFF interval {gff_start}-{gff_end}")
    return gff_start - 1, gff_end


def internal_to_gff(start: int, end: int) -> tuple[int, int]:
    """Convert 0-based half-open coordinates to GFF3 1-based inclusive."""
    if start < 0 or end < start:
        raise ValueError(f"Invalid internal interval [{start}, {end})")
    return start + 1, end


def sam_pos_to_internal(sam_pos: int) -> int:
    """Convert a SAM/BAM 1-based alignment start to 0-based."""
    if sam_pos < 1:
        raise ValueError(f"Invalid SAM POS {sam_pos}")
    return sam_pos - 1


def intervals_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """True if two 0-based half-open intervals overlap."""
    return a_start < b_end and b_start < a_end
