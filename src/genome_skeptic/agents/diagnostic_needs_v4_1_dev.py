"""Diagnostic needs for Agentic V4.1-dev.

V4-dev need generation is not modified. V4.1 also treats family/paralogy
identity as unresolved when an independent orthology reference set exists
and has not yet produced a sequence-decisive classification.
"""
from __future__ import annotations

from typing import Any

from genome_skeptic.agents.diagnostic_needs import (
    ASSEMBLY_SUPPORT_UNRESOLVED,
    CONTAMINATION_UNRESOLVED,
    COPY_NUMBER_UNRESOLVED,
    DIAGNOSTIC_NEEDS,
    FAMILY_IDENTITY_UNRESOLVED,
    FRAGMENTATION_UNRESOLVED,
    NEED_PRIORITY,
    ORTHOLOG_VS_PARALOG_UNRESOLVED,
    REMOTE_HOMOLOG_NOT_EXCLUDED,
    _architecture,
    _competitive,
    _has_rbh,
    _multiplicity,
    _orf_search_done,
    need_payload,
    orf_search_already_done,
)
from genome_skeptic.config import Settings
from genome_skeptic.validators.falsification import TargetMeasurements
from genome_skeptic.validators.locus_stages_v4_1_dev import loci_from_measurements
from genome_skeptic.validators.ortholog_references import (
    COMPETING_FAMILY_PREFERRED,
    TARGET_FAMILY_SUPPORTED,
)

# Same numeric gate the frozen discriminator uses for a decisive sequence call.
_DECISIVE_IDENTITY_PRODUCT = 0.70


def family_identity_is_decisive(competitive: dict[str, Any]) -> bool:
    """True only when stored competitive-family scores already settle identity."""
    cls = competitive.get("classification")
    if cls == "competing_family_preferred":
        return True
    if cls != "target_family_supported":
        return False
    coverage = float(competitive.get("target_family_sequence_coverage") or 0.0)
    if coverage < _DECISIVE_IDENTITY_PRODUCT:
        return False
    conflicts = [str(item).lower() for item in (competitive.get("conflicting_evidence") or [])]
    if any("did not pass the family gate" in item for item in conflicts):
        return False
    return True


def derive_diagnostic_needs_v4_1_dev(
    m: TargetMeasurements,
    capabilities: dict[str, bool],
    *,
    settings: Settings | None = None,
    edge_bp: int = 300,
) -> list[str]:
    """V4-dev needs. Order is NEED_PRIORITY, then the frozen DiagnosticNeed sequence."""
    cfg = settings or Settings()
    hits = list(m.hits or [])
    n_loci = len(loci_from_measurements(m, cfg))
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
    ortholog_ready = bool(capabilities.get("ortholog_reference_set")) and bool(capabilities.get("hits"))
    competitive = _competitive(m)
    if (competing_ready or ortholog_ready) and not family_identity_is_decisive(competitive):
        needs.append(FAMILY_IDENTITY_UNRESOLVED)

    ortho = ((getattr(m.family_evidence, "reconstruction", None) or {}) if m.family_evidence else {}) or {}
    ortho_cls = ((ortho.get("ortholog_reference_discrimination") or {}).get("classification"))
    ortho_decisive = ortho_cls in {TARGET_FAMILY_SUPPORTED, COMPETING_FAMILY_PREFERRED}
    if (
        hits
        and bool(capabilities.get("references"))
        and bool(capabilities.get("query_protein"))
        and not _has_rbh(m)
    ):
        needs.append(ORTHOLOG_VS_PARALOG_UNRESOLVED)
    elif ortholog_ready and bool(capabilities.get("query_protein")) and not ortho_decisive:
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


derive_diagnostic_needs_v4_dev = derive_diagnostic_needs_v4_1_dev


__all__ = [
    "ASSEMBLY_SUPPORT_UNRESOLVED",
    "CONTAMINATION_UNRESOLVED",
    "COPY_NUMBER_UNRESOLVED",
    "DIAGNOSTIC_NEEDS",
    "FAMILY_IDENTITY_UNRESOLVED",
    "FRAGMENTATION_UNRESOLVED",
    "NEED_PRIORITY",
    "ORTHOLOG_VS_PARALOG_UNRESOLVED",
    "REMOTE_HOMOLOG_NOT_EXCLUDED",
    "derive_diagnostic_needs_v4_1_dev",
    "derive_diagnostic_needs_v4_dev",
    "family_identity_is_decisive",
    "need_payload",
    "orf_search_already_done",
]
