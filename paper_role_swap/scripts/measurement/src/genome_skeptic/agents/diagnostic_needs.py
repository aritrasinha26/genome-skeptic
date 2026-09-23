"""Deterministic diagnostic-need layer for Agentic V3.

Needs are inferred from ``TargetMeasurements``, validator-derived family state,
and input capabilities. They do not use truth labels, accessions, or case ids.
"""
from __future__ import annotations

from typing import Any

from genome_skeptic.config import Settings
from genome_skeptic.validators.falsification import TargetMeasurements, _loci


REMOTE_HOMOLOG_NOT_EXCLUDED = "REMOTE_HOMOLOG_NOT_EXCLUDED"
FAMILY_IDENTITY_UNRESOLVED = "FAMILY_IDENTITY_UNRESOLVED"
ORTHOLOG_VS_PARALOG_UNRESOLVED = "ORTHOLOG_VS_PARALOG_UNRESOLVED"
COPY_NUMBER_UNRESOLVED = "COPY_NUMBER_UNRESOLVED"
FRAGMENTATION_UNRESOLVED = "FRAGMENTATION_UNRESOLVED"
CONTAMINATION_UNRESOLVED = "CONTAMINATION_UNRESOLVED"
ASSEMBLY_SUPPORT_UNRESOLVED = "ASSEMBLY_SUPPORT_UNRESOLVED"

DIAGNOSTIC_NEEDS: tuple[str, ...] = (
    REMOTE_HOMOLOG_NOT_EXCLUDED,
    FAMILY_IDENTITY_UNRESOLVED,
    ORTHOLOG_VS_PARALOG_UNRESOLVED,
    COPY_NUMBER_UNRESOLVED,
    FRAGMENTATION_UNRESOLVED,
    CONTAMINATION_UNRESOLVED,
    ASSEMBLY_SUPPORT_UNRESOLVED,
)

# Higher = more decision-relevant. Not a biological answer; it ranks question type.
NEED_PRIORITY: dict[str, int] = {
    REMOTE_HOMOLOG_NOT_EXCLUDED: 5,
    FAMILY_IDENTITY_UNRESOLVED: 5,
    COPY_NUMBER_UNRESOLVED: 5,
    ORTHOLOG_VS_PARALOG_UNRESOLVED: 4,
    FRAGMENTATION_UNRESOLVED: 3,
    ASSEMBLY_SUPPORT_UNRESOLVED: 2,
    CONTAMINATION_UNRESOLVED: 1,
}

# Agentic ORF-level searches only. Family-profile hmmsearch on m0 is not
# exclusion of remote homologs or additional copies over assembly ORFs.
_AGENTIC_ORF_TOOLS = frozenset(
    {
        "mmseqs",
        "diamond",
        "hmmer_nominated_alignment",
    }
)


def _tools(m: TargetMeasurements) -> set[str]:
    names = {str(t) for t in (m.tools_run or [])}
    names.update(str(getattr(h, "tool", "") or "") for h in (m.hits or []))
    return {t for t in names if t}


def _architecture(m: TargetMeasurements) -> str | None:
    fam = m.family_evidence
    if fam is None:
        return None
    recon = getattr(fam, "reconstruction", None) or {}
    return recon.get("architecture") or getattr(fam, "architecture", None)


def _competitive(m: TargetMeasurements) -> dict[str, Any]:
    fam = m.family_evidence
    if fam is None:
        return {}
    recon = getattr(fam, "reconstruction", None) or {}
    blob = recon.get("competitive_family") or {}
    return blob if isinstance(blob, dict) else {}


def _multiplicity(m: TargetMeasurements) -> dict[str, Any]:
    fam = m.family_evidence
    if fam is None:
        return {}
    recon = getattr(fam, "reconstruction", None) or {}
    blob = recon.get("multiplicity") or {}
    return blob if isinstance(blob, dict) else {}


def _orf_search_done(m: TargetMeasurements) -> bool:
    return bool(_tools(m) & _AGENTIC_ORF_TOOLS)


def _has_rbh(m: TargetMeasurements) -> bool:
    for le in m.locus_evidence or []:
        if any(getattr(o, "reciprocal_best_hit", None) is not None for o in (le.orthologues or [])):
            return True
    return False


def derive_diagnostic_needs(
    m: TargetMeasurements,
    capabilities: dict[str, bool],
    *,
    settings: Settings | None = None,
    edge_bp: int = 300,
) -> list[str]:
    """Return unresolved DiagnosticNeed ids. Order is NEED_PRIORITY, then name."""
    cfg = settings or Settings()
    hits = list(m.hits or [])
    n_loci = len(_loci(hits, cfg))
    arch = _architecture(m)
    multi = _multiplicity(m)
    fam = m.family_evidence
    needs: list[str] = []

    protein_ready = bool(capabilities.get("query_protein")) and (
        bool(capabilities.get("similarity_tools")) or bool(capabilities.get("hmmer"))
    )
    if protein_ready and not _orf_search_done(m):
        needs.append(REMOTE_HOMOLOG_NOT_EXCLUDED)

    competing_ready = bool(capabilities.get("competing_families")) and bool(capabilities.get("hits"))
    competitive = _competitive(m)
    family_cls = competitive.get("classification")
    if competing_ready and family_cls not in {
        "target_family_supported",
        "competing_family_preferred",
        "ambiguous_family",
        "domain_only",
    }:
        needs.append(FAMILY_IDENTITY_UNRESOLVED)

    if (
        hits
        and bool(capabilities.get("references"))
        and bool(capabilities.get("query_protein"))
        and not _has_rbh(m)
    ):
        needs.append(ORTHOLOG_VS_PARALOG_UNRESOLVED)

    n_cand = multi.get("number_of_candidate_loci")
    copy_open = False
    if hits and n_loci == 0:
        copy_open = True
    if n_cand == 0 and hits:
        copy_open = True
    if arch == "true_no_candidate":
        copy_open = True
    if (multi.get("classification") or "") == "unresolved_multiple_hits":
        copy_open = True
    # Clustering the current hit set into one locus does not exclude unplaced copies.
    if protein_ready and not _orf_search_done(m) and n_loci <= 1:
        copy_open = True
    if copy_open:
        needs.append(COPY_NUMBER_UNRESOLVED)

    fragmented = False
    if any(bool(h.possible_edge_truncation) or (bool(h.near_contig_edge) and h.query_coverage < 0.95) for h in hits):
        fragmented = True
    if arch == "assembly_fragmented":
        fragmented = True
    if fam is not None and bool((getattr(fam, "fragmented", None) or {}).get("supported")):
        fragmented = True
    if fragmented and hits:
        needs.append(FRAGMENTATION_UNRESOLVED)

    gc_missing = bool(hits) and (
        not m.contig_gc
        or any(h.contig_id not in (m.contig_gc or {}) for h in hits)
        or m.genome_gc is None
    )
    tax_missing = bool(hits) and not any((m.contig_taxonomy or {}).values())
    if gc_missing or (tax_missing and bool(capabilities.get("taxonomy_db"))):
        needs.append(CONTAMINATION_UNRESOLVED)

    if bool(capabilities.get("mapping_sam")) and hits and not m.break_evidence:
        needs.append(ASSEMBLY_SUPPORT_UNRESOLVED)
    elif bool(capabilities.get("depth_tsv")) and hits and not m.coverage_by_hit:
        needs.append(ASSEMBLY_SUPPORT_UNRESOLVED)

    unique: list[str] = []
    for need in DIAGNOSTIC_NEEDS:
        if need in needs:
            unique.append(need)
    return unique


def need_payload(needs: list[str]) -> list[dict[str, Any]]:
    return [{"need": n, "priority": NEED_PRIORITY[n]} for n in needs]


def orf_search_already_done(m: TargetMeasurements) -> bool:
    return _orf_search_done(m)
