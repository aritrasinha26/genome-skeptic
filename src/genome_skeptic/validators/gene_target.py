from __future__ import annotations

from genome_skeptic.config import Settings
from genome_skeptic.models import Anomaly, Claim, GeneSearchHit, LocusEvidence, TargetProfile
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim
from genome_skeptic.validators.homology import (
    FORBIDDEN_ABSENCE_PHRASES,
    claim_id_for_query,
    partial_hit,
    query_span_coverage,
    strong_hit,
)

# Backwards-compatible aliases used by existing tests.
_strong_hit = strong_hit
_partial_hit = partial_hit
_query_span_coverage = query_span_coverage


def hits_from_metrics(metrics: dict) -> list[GeneSearchHit]:
    return [GeneSearchHit.model_validate(h) for h in metrics.get("hits", [])]


def evaluate_target_gene(
    query_id: str,
    hits: list[GeneSearchHit],
    settings: Settings,
    evidence_ids: dict[str, str],
    limitations: list[str],
    coverage_by_hit: dict[str, dict] | None = None,
    neighborhood_by_hit: dict[str, dict] | None = None,
    query_length: int | None = None,
    profile: TargetProfile | None = None,
    contig_sequences: dict[str, str] | None = None,
    protein_sequences: dict[str, str] | None = None,
    contig_gc: dict[str, float] | None = None,
    genome_gc: float | None = None,
    checkm_contamination: float | None = None,
    measured_taxonomy: str | None = None,
    tools_run: list[str] | None = None,
    tools_unavailable: list[str] | None = None,
    proteins_available: bool = False,
    depth_available: bool | None = None,
    annotation_available: bool | None = None,
    locus_evidence: list[LocusEvidence] | None = None,
) -> tuple[Claim, list[Anomaly]]:
    profile = profile or TargetProfile(query_id=query_id, sequence="", expected_length_aa=query_length)
    coverage_by_hit = coverage_by_hit or {}
    neighborhood_by_hit = neighborhood_by_hit or {}
    measurements = TargetMeasurements(
        query_id=query_id,
        profile=profile,
        hits=hits,
        coverage_by_hit=coverage_by_hit,
        neighborhood_by_hit=neighborhood_by_hit,
        contig_sequences=contig_sequences or {},
        protein_sequences=protein_sequences or {},
        contig_gc=contig_gc or {},
        genome_gc=genome_gc,
        checkm_contamination=checkm_contamination,
        measured_taxonomy=measured_taxonomy,
        tools_run=tools_run or ["internal_gene_search"],
        tools_unavailable=tools_unavailable or [],
        limitations=list(limitations),
        proteins_available=proteins_available,
        depth_available=bool(coverage_by_hit) if depth_available is None else depth_available,
        annotation_available=bool(neighborhood_by_hit) if annotation_available is None else annotation_available,
        locus_evidence=locus_evidence or [],
    )
    claim, anomalies, _tests = build_target_gene_claim(measurements, settings, list(evidence_ids.values()))
    return claim, anomalies
