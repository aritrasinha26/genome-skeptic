"""Generic locus reconstruction for Agentic V4-dev.

V3/V5 ``_loci`` and ``assess_multiplicity`` are not replaced for those systems.
V4-dev uses this module so accepted candidate proteins keep genomic coordinates,
same-ORF hits collapse, and distinct loci stay distinct.

Acceptance uses already-registered thresholds:
- ``gene_paralogue_min_coverage`` (0.50) for a usable interval
- ``family_member_min_identity`` (0.35) for family-member homology
No accession, gene, or truth labels are consulted.
"""
from __future__ import annotations

from typing import Any

from genome_skeptic.agents.derived_state import recompute_derived_measurements
from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit
from genome_skeptic.validators.falsification import TargetMeasurements, _loci as _loci_v3
from genome_skeptic.validators.paralogy import _contained, _genomic_interval_iou


def locus_key(hit: GeneSearchHit) -> str:
    lo, hi = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
    strand = hit.strand or "+"
    return hit.orf_id or f"{hit.contig_id}:{lo}-{hi}:{strand}"


def recover_hit_coordinates(hit: GeneSearchHit) -> GeneSearchHit:
    """Retain or recover contig/start/end/strand/ORF identity. Never invents them."""
    lo, hi = min(int(hit.tstart), int(hit.tend)), max(int(hit.tstart), int(hit.tend))
    orf_id = hit.orf_id or f"{hit.contig_id}:{lo}-{hi}:{hit.strand or '+'}"
    if hit.orf_id == orf_id and lo == min(hit.tstart, hit.tend):
        return hit
    return hit.model_copy(update={"orf_id": orf_id, "tstart": lo, "tend": hi})


def is_accepted_candidate(hit: GeneSearchHit, settings: Settings) -> bool:
    """A hit that can represent a genomic locus after coordinate recovery."""
    t = settings.thresholds
    if hit.search_kind == "domain":
        return False
    if not hit.contig_id:
        return False
    if min(hit.tstart, hit.tend) == max(hit.tstart, hit.tend):
        return False
    if hit.query_coverage < t.gene_paralogue_min_coverage:
        return False
    if hit.tool in {"family_member_search", "internal_gene_search"} and hit.query_id != getattr(
        hit, "target_query_id", hit.query_id
    ):
        # Family-member searches use the member protein as query_id. Require the
        # pre-registered member-identity gate so short remote fragments stay out.
        if hit.identity < t.family_member_min_identity:
            return False
    if hit.identity < t.family_member_min_identity and hit.query_coverage < t.gene_paralogue_min_coverage:
        return False
    if hit.identity < t.family_member_min_identity and hit.tool != "internal_gene_search":
        # Member-homology hits below the family-member identity gate are not loci.
        if hit.query_id and hit.query_id != (hit.domain_name or ""):
            if hit.identity < t.family_member_min_identity:
                return False
    return True


def _is_member_style_hit(hit: GeneSearchHit, target_query_id: str | None) -> bool:
    if not target_query_id:
        return False
    return bool(hit.query_id) and hit.query_id != target_query_id


def accepted_hits(
    hits: list[GeneSearchHit],
    settings: Settings,
    *,
    target_query_id: str | None = None,
) -> list[GeneSearchHit]:
    kept: list[GeneSearchHit] = []
    for raw in hits:
        hit = recover_hit_coordinates(raw)
        if hit.search_kind == "domain":
            continue
        if not hit.contig_id:
            continue
        if min(hit.tstart, hit.tend) == max(hit.tstart, hit.tend):
            continue
        if hit.query_coverage < settings.thresholds.gene_paralogue_min_coverage:
            continue
        if _is_member_style_hit(hit, target_query_id) and hit.identity < settings.thresholds.family_member_min_identity:
            continue
        kept.append(hit)
    return kept


def cluster_loci(hits: list[GeneSearchHit], settings: Settings) -> list[GeneSearchHit]:
    """Collapse same-ORF / overlapping representations; keep genomically distinct loci."""
    ranked = sorted(hits, key=lambda h: (h.identity * h.query_coverage, h.alignment_length), reverse=True)
    kept: list[GeneSearchHit] = []
    seen_orfs: set[str] = set()
    for hit in ranked:
        orf = locus_key(hit)
        if orf in seen_orfs:
            continue
        overlapped = False
        blob = {
            "contig": hit.contig_id,
            "genomic_start": min(hit.tstart, hit.tend),
            "genomic_end": max(hit.tstart, hit.tend),
        }
        for prev in kept:
            if locus_key(prev) == orf:
                overlapped = True
                break
            if prev.contig_id != hit.contig_id:
                continue
            prev_blob = {
                "contig": prev.contig_id,
                "genomic_start": min(prev.tstart, prev.tend),
                "genomic_end": max(prev.tstart, prev.tend),
            }
            if _contained(blob, prev_blob) or _contained(prev_blob, blob) or _genomic_interval_iou(blob, prev_blob) >= 0.50:
                overlapped = True
                break
            if min(prev.tend, hit.tend) - max(prev.tstart, hit.tstart) > 30:
                overlapped = True
                break
        if overlapped:
            continue
        seen_orfs.add(orf)
        kept.append(hit)
    return kept


def _loci(
    hits: list[GeneSearchHit],
    settings: Settings,
    *,
    target_query_id: str | None = None,
) -> list[GeneSearchHit]:
    """V4-dev canonical loci. Same name as the V3 helper for the invariant."""
    return cluster_loci(accepted_hits(hits, settings, target_query_id=target_query_id), settings)


def extra_source_hits(m: TargetMeasurements) -> list[GeneSearchHit]:
    fam = m.family_evidence
    extra: list[GeneSearchHit] = []
    if fam is not None:
        extra.extend(list(getattr(fam, "member_hits", None) or []))
        recon = getattr(fam, "reconstruction", None) or {}
        if recon.get("contig") is not None and recon.get("genomic_start") is not None and recon.get("genomic_end") is not None:
            cov = float(recon.get("protein_coverage") or 0.0)
            ident = float(recon.get("sequence_identity") or 0.0)
            extra.append(
                GeneSearchHit(
                    query_id=str(getattr(fam, "family_id", None) or m.query_id),
                    contig_id=str(recon["contig"]),
                    search_kind="translated",
                    qstart=0,
                    qend=max(1, int(round(cov * max(1, int(recon.get("protein_length") or 1))))),
                    tstart=int(recon["genomic_start"]),
                    tend=int(recon["genomic_end"]),
                    strand=str(recon.get("strand") or "+"),
                    identity=ident,
                    query_coverage=cov if cov else 0.0,
                    alignment_length=abs(int(recon["genomic_end"]) - int(recon["genomic_start"])),
                    query_length=int(recon.get("protein_length") or max(1, abs(int(recon["genomic_end"]) - int(recon["genomic_start"])) // 3)),
                    contig_length=len((m.contig_sequences or {}).get(str(recon["contig"]), "") or ""),
                    tool="family_member_search",
                    orf_id=f"{recon['contig']}:{int(recon['genomic_start'])}-{int(recon['genomic_end'])}:{recon.get('strand') or '+'}",
                )
            )
    return extra


def loci_from_measurements(m: TargetMeasurements, settings: Settings) -> list[GeneSearchHit]:
    combined = list(m.hits or []) + extra_source_hits(m)
    return _loci(combined, settings, target_query_id=m.query_id)


def inject_accepted_loci_into_hits(m: TargetMeasurements, settings: Settings) -> list[GeneSearchHit]:
    """Copy accepted family-member / reconstruction loci into ``m.hits``.

    Existing query hits are kept as evidence. Accepted extras that do not
    overlap an already-accepted query hit are appended. The LLM does not
    write these values.
    """
    current = [recover_hit_coordinates(h) for h in (m.hits or [])]
    extras = accepted_hits(extra_source_hits(m), settings, target_query_id=m.query_id)
    already = accepted_hits(current, settings, target_query_id=m.query_id)
    placed = cluster_loci(already, settings)
    out = list(current)
    seen = {locus_key(h) for h in out}
    for extra in cluster_loci(extras, settings):
        blob = {
            "contig": extra.contig_id,
            "genomic_start": min(extra.tstart, extra.tend),
            "genomic_end": max(extra.tstart, extra.tend),
        }
        duplicate = False
        for prev in placed:
            if locus_key(prev) == locus_key(extra):
                duplicate = True
                break
            if prev.contig_id != extra.contig_id:
                continue
            prev_blob = {
                "contig": prev.contig_id,
                "genomic_start": min(prev.tstart, prev.tend),
                "genomic_end": max(prev.tstart, prev.tend),
            }
            if _contained(blob, prev_blob) or _contained(prev_blob, blob) or _genomic_interval_iou(blob, prev_blob) >= 0.50:
                duplicate = True
                break
        if duplicate or locus_key(extra) in seen:
            continue
        extra = extra.model_copy(update={"query_id": m.query_id or extra.query_id})
        out.append(extra)
        placed.append(extra)
        seen.add(locus_key(extra))
    return out


def assert_locus_count_invariant(m: TargetMeasurements, settings: Settings) -> None:
    fam = m.family_evidence
    if fam is None or not hasattr(fam, "reconstruction"):
        return
    recon = getattr(fam, "reconstruction", None) or {}
    multi = recon.get("multiplicity") or {}
    n_cand = multi.get("number_of_candidate_loci")
    if n_cand is None:
        return
    n = len(_loci(list(m.hits or []), settings, target_query_id=m.query_id))
    if int(n_cand) != n:
        raise RuntimeError(
            f"locus-count invariant failed: number_of_candidate_loci={n_cand} but _loci(hits)={n}"
        )


def refine_weak_family_classification(m: TargetMeasurements) -> bool:
    """Reclassify a non-decisive target_family_supported call as ambiguous_family.

    Uses only stored competitive-family measurements and the frozen 0.70
    identity-product gate. Does not consult truth labels.
    """
    from genome_skeptic.agents.diagnostic_needs_v4_dev import family_identity_is_decisive

    fam = m.family_evidence
    if fam is None:
        return False
    recon = dict(getattr(fam, "reconstruction", None) or {})
    competitive = dict(recon.get("competitive_family") or {})
    if not competitive:
        return False
    if competitive.get("classification") != "target_family_supported":
        return False
    if family_identity_is_decisive(competitive):
        return False
    competitive["classification"] = "ambiguous_family"
    conflicts = list(competitive.get("conflicting_evidence") or [])
    conflicts.append(
        "target family support is not sequence-decisive; competing-family comparison did not settle identity"
    )
    competitive["conflicting_evidence"] = conflicts
    recon["competitive_family"] = competitive
    fam.reconstruction = recon
    return True


def repair_loci_v4(m: TargetMeasurements, settings: Settings) -> None:
    """Deterministic locus repair used after m0 and after every hits-changing action."""
    m.hits = inject_accepted_loci_into_hits(m, settings)
    recompute_derived_measurements(m, settings)
    # Canonical count is V4 ``_loci(hits)`` after accepted member loci were merged.
    fam = m.family_evidence
    if fam is not None and hasattr(fam, "reconstruction"):
        recon = dict(getattr(fam, "reconstruction", None) or {})
        multi = dict(recon.get("multiplicity") or {})
        n = len(_loci(list(m.hits or []), settings, target_query_id=m.query_id))
        multi["number_of_candidate_loci"] = n
        if n == 0:
            multi["classification"] = multi.get("classification") or "single_locus"
        elif n == 1:
            multi["classification"] = "single_locus"
        elif (multi.get("classification") or "single_locus") == "single_locus":
            n_contigs = len({h.contig_id for h in _loci(list(m.hits or []), settings, target_query_id=m.query_id)})
            multi["classification"] = "true_gene_duplication" if n_contigs >= 2 else "unresolved_multiple_hits"
        loci = _loci(list(m.hits or []), settings, target_query_id=m.query_id)
        multi["coordinates"] = [
            {
                "contig": h.contig_id,
                "start": min(h.tstart, h.tend),
                "end": max(h.tstart, h.tend),
                "strand": h.strand or "+",
            }
            for h in loci
        ]
        multi["contigs"] = sorted({h.contig_id for h in loci})
        recon["multiplicity"] = multi
        fam.reconstruction = recon
        metrics = dict(getattr(fam, "metrics", None) or {})
        metrics["n_loci"] = n
        metrics["multiplicity_classification"] = multi.get("classification")
        fam.metrics = metrics
    assert_locus_count_invariant(m, settings)


def v3_loci(hits: list[GeneSearchHit], settings: Settings) -> list[GeneSearchHit]:
    return _loci_v3(hits, settings)
