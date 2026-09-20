"""Three-stage locus logic for GENOME_SKEPTIC_V4_1_DEV.

1. CANDIDATE ACCEPTANCE — biological eligibility from existing family /
   homology / HMM gates. Does not use multiplicity_min_identity.
2.    LOCUS RECONSTRUCTION — contig/start/end/strand/ORF from accepted hits.
   No second high-identity orthology threshold (the copy-clustering identity
   gate is not applied here).
3. MULTIPLICITY — collapse same ORF / overlapping intervals; keep distinct
   genomic loci. number_of_candidate_loci is deterministic.

V3/V5 ``assess_multiplicity._cluster_hits`` is not modified.
The LLM never writes copy number.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genome_skeptic.agents.derived_state import recompute_derived_measurements
from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit
from genome_skeptic.validators.falsification import TargetMeasurements
from genome_skeptic.validators.locus_v4_dev import extra_source_hits, recover_hit_coordinates
from genome_skeptic.validators.paralogy import _contained, _genomic_interval_iou


@dataclass(frozen=True)
class ReconstructedLocus:
    contig: str
    start: int
    end: int
    strand: str
    orf_id: str
    identity: float
    coverage: float
    source_hit: GeneSearchHit

    def as_coord(self) -> dict[str, Any]:
        return {"contig": self.contig, "start": self.start, "end": self.end, "strand": self.strand}


def locus_key(hit: GeneSearchHit) -> str:
    lo, hi = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
    return hit.orf_id or f"{hit.contig_id}:{lo}-{hi}:{hit.strand or '+'}"


def _member_style(hit: GeneSearchHit, target_query_id: str | None) -> bool:
    return bool(target_query_id) and bool(hit.query_id) and hit.query_id != target_query_id


def accept_candidates(
    hits: list[GeneSearchHit],
    settings: Settings,
    *,
    target_query_id: str | None = None,
) -> list[GeneSearchHit]:
    """Stage 1: biologically eligible hits.

    Uses the pre-registered family-member identity gate (0.35) and the
    paralogue/locus coverage gate (0.50). Does not apply the copy-clustering identity gate.
    """
    t = settings.thresholds
    accepted: list[GeneSearchHit] = []
    for raw in hits:
        hit = recover_hit_coordinates(raw)
        if hit.search_kind == "domain":
            continue
        if not hit.contig_id:
            continue
        if min(hit.tstart, hit.tend) == max(hit.tstart, hit.tend):
            continue
        hmm_ok = bool(hit.domain_name) and hit.query_coverage >= t.hmm_min_gate_model_coverage
        coverage_ok = hit.query_coverage >= t.gene_paralogue_min_coverage
        if not coverage_ok and not hmm_ok:
            continue
        if _member_style(hit, target_query_id) and hit.identity < t.family_member_min_identity:
            continue
        accepted.append(hit)
    return accepted


def reconstruct_loci(accepted: list[GeneSearchHit], settings: Settings) -> list[ReconstructedLocus]:
    """Stage 2: genomic intervals from accepted hits. No identity cutoff."""
    out: list[ReconstructedLocus] = []
    for hit in accepted:
        hit = recover_hit_coordinates(hit)
        lo, hi = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
        out.append(
            ReconstructedLocus(
                contig=hit.contig_id,
                start=lo,
                end=hi,
                strand=hit.strand or "+",
                orf_id=locus_key(hit),
                identity=hit.identity,
                coverage=hit.query_coverage,
                source_hit=hit,
            )
        )
    return out


def collapse_multiplicity(loci: list[ReconstructedLocus]) -> list[ReconstructedLocus]:
    """Stage 3: same ORF / overlapping interval → one locus; distinct stay distinct."""
    ranked = sorted(loci, key=lambda loc: (loc.identity * loc.coverage, loc.end - loc.start), reverse=True)
    kept: list[ReconstructedLocus] = []
    seen: set[str] = set()
    for loc in ranked:
        if loc.orf_id in seen:
            continue
        blob = {"contig": loc.contig, "genomic_start": loc.start, "genomic_end": loc.end}
        overlapped = False
        for prev in kept:
            if prev.orf_id == loc.orf_id:
                overlapped = True
                break
            if prev.contig != loc.contig:
                continue
            prev_blob = {"contig": prev.contig, "genomic_start": prev.start, "genomic_end": prev.end}
            if _contained(blob, prev_blob) or _contained(prev_blob, blob) or _genomic_interval_iou(blob, prev_blob) >= 0.50:
                overlapped = True
                break
            if min(prev.end, loc.end) - max(prev.start, loc.start) > 30:
                overlapped = True
                break
        if overlapped:
            continue
        seen.add(loc.orf_id)
        kept.append(loc)
    return kept


def _loci(
    hits: list[GeneSearchHit],
    settings: Settings,
    *,
    target_query_id: str | None = None,
) -> list[GeneSearchHit]:
    """Canonical counted loci: reconstruct(accept(hits)) after multiplicity collapse."""
    accepted = accept_candidates(hits, settings, target_query_id=target_query_id)
    return [loc.source_hit for loc in collapse_multiplicity(reconstruct_loci(accepted, settings))]


def all_source_hits(m: TargetMeasurements) -> list[GeneSearchHit]:
    return list(m.hits or []) + extra_source_hits(m)


def accepted_from_measurements(m: TargetMeasurements, settings: Settings) -> list[GeneSearchHit]:
    return accept_candidates(all_source_hits(m), settings, target_query_id=m.query_id)


def loci_from_measurements(m: TargetMeasurements, settings: Settings) -> list[GeneSearchHit]:
    return _loci(all_source_hits(m), settings, target_query_id=m.query_id)


def assert_locus_count_invariant(m: TargetMeasurements, settings: Settings) -> None:
    fam = m.family_evidence
    if fam is None or not hasattr(fam, "reconstruction"):
        return
    recon = getattr(fam, "reconstruction", None) or {}
    multi = recon.get("multiplicity") or {}
    n_cand = multi.get("number_of_candidate_loci")
    if n_cand is None:
        return
    accepted = accept_candidates(list(m.hits or []), settings, target_query_id=m.query_id)
    n = len(_loci(accepted, settings, target_query_id=m.query_id))
    if int(n_cand) != n:
        raise RuntimeError(
            f"locus-count invariant failed: number_of_candidate_loci={n_cand} "
            f"but _loci(accepted_hits)={n}"
        )


def repair_loci_v4_1(m: TargetMeasurements, settings: Settings) -> dict[str, Any]:
    """Run the three stages and write deterministic multiplicity. LLM writes nothing."""
    sources = all_source_hits(m)
    accepted = accept_candidates(sources, settings, target_query_id=m.query_id)
    reconstructed = reconstruct_loci(accepted, settings)
    distinct = collapse_multiplicity(reconstructed)
    current = [recover_hit_coordinates(h) for h in (m.hits or [])]
    out = list(current)
    seen = {locus_key(h) for h in out}
    for loc in distinct:
        hit = loc.source_hit.model_copy(update={"query_id": m.query_id or loc.source_hit.query_id, "orf_id": loc.orf_id})
        if locus_key(hit) in seen:
            continue
        out.append(hit)
        seen.add(locus_key(hit))
    m.hits = out
    recompute_derived_measurements(m, settings)
    n = len(distinct)
    fam = m.family_evidence
    summary = {
        "n_source_hits": len(sources),
        "n_accepted": len(accepted),
        "n_reconstructed": len(reconstructed),
        "n_loci": n,
        "coordinates": [loc.as_coord() for loc in distinct],
    }
    if fam is not None and hasattr(fam, "reconstruction"):
        recon = dict(getattr(fam, "reconstruction", None) or {})
        multi = dict(recon.get("multiplicity") or {})
        multi["number_of_candidate_loci"] = n
        multi["coordinates"] = [loc.as_coord() for loc in distinct]
        multi["contigs"] = sorted({loc.contig for loc in distinct})
        if n == 0:
            multi["classification"] = "no_candidate_loci"
        elif n == 1:
            multi["classification"] = "single_locus"
        else:
            n_contigs = len({loc.contig for loc in distinct})
            multi["classification"] = "true_gene_duplication" if n_contigs >= 2 else "unresolved_multiple_hits"
        recon["multiplicity"] = multi
        recon["accepted_candidate_count"] = len(accepted)
        fam.reconstruction = recon
        metrics = dict(getattr(fam, "metrics", None) or {})
        metrics["n_loci"] = n
        metrics["multiplicity_classification"] = multi.get("classification")
        fam.metrics = metrics
    assert_locus_count_invariant(m, settings)
    return summary
