"""V5 decision-layer repair tests.

These tests capture the biological semantics of the two repaired rules.
They do not use M60 accessions, truth labels, or locked cohort fixtures.
"""
from genome_skeptic.agents.diagnostic_needs_v4_1_dev import family_identity_is_decisive
from genome_skeptic.config import Settings
from genome_skeptic.families import load_family
from genome_skeptic.models import (
    ClaimType,
    GeneSearchHit,
    LocusReconstruction,
    LocusSegment,
    TargetProfile,
    TargetType,
)
from genome_skeptic.validators.falsification import TargetMeasurements, classify_polarity
from genome_skeptic.validators.family_orthology import FamilyEvidence, family_detects_orthologue
from genome_skeptic.validators.locus_reconstruction import (
    architecture_profile_coverage,
    classify_architecture,
)
from genome_skeptic.validators.locus_v4_dev import refine_weak_family_classification


def _hit(**kwargs) -> GeneSearchHit:
    data = {
        "query_id": "member",
        "contig_id": "c1",
        "search_kind": "translated",
        "qstart": 0,
        "qend": 400,
        "tstart": 100,
        "tend": 1300,
        "strand": "+",
        "identity": 0.99,
        "query_coverage": 0.98,
        "alignment_length": 1200,
        "query_length": 400,
        "contig_length": 5000,
    }
    data.update(kwargs)
    return GeneSearchHit.model_validate(data)


def _profile() -> TargetProfile:
    return TargetProfile(query_id="target", sequence="ATG" + "CGT" * 40 + "TAA", target_type=TargetType.gene_orthologue)


def _measurements(competitive: dict, reconstruction_extra: dict | None = None) -> TargetMeasurements:
    recon = {
        "architecture": "divergent_full_length",
        "sequence_identity": competitive.get("target_family_sequence_identity"),
        "query_identity": None,
        "hmm_coverage": 0.90,
        "competitive_family": competitive,
    }
    if reconstruction_extra:
        recon.update(reconstruction_extra)
    fam = FamilyEvidence(
        family_id="tetA_tetracycline_efflux",
        architecture=recon["architecture"],
        supports_orthologue=True,
        domain_only=False,
        reconstruction=recon,
        member_hits=[_hit()],
    )
    return TargetMeasurements(query_id="tetA", profile=_profile(), hits=[_hit()], family_evidence=fam)


def _rpoB_rec(*, hmm_coverage: float, orf_id: str = "c1:100-4000:+") -> LocusReconstruction:
    return LocusReconstruction(
        contig="c1",
        strand="+",
        genomic_start=100,
        genomic_end=4000,
        hmm_coverage=hmm_coverage,
        sequence_identity=0.84,
        protein_coverage=0.98,
        query_identity=0.84,
        contig_edge=False,
        candidate_segments=[
            LocusSegment(
                contig="c1",
                strand="+",
                genomic_start=100,
                genomic_end=4000,
                hmm_from=1,
                hmm_to=int(1200 * hmm_coverage),
                orf_id=orf_id,
            )
        ],
    )


def test_teta_strong_target_weak_competitor_remains_target():
    competitive = {
        "classification": "target_family_supported",
        "target_family_sequence_identity": 0.99,
        "target_family_sequence_coverage": 0.94,
        "conflicting_evidence": [
            "best competing family did not pass the family gate and is not treated as an alternative identity"
        ],
    }
    assert family_identity_is_decisive(competitive) is True
    m = _measurements(competitive)
    assert refine_weak_family_classification(m) is False
    assert m.family_evidence.reconstruction["competitive_family"]["classification"] == "target_family_supported"
    ev = m.family_evidence
    assert family_detects_orthologue(_profile(), list(ev.member_hits), Settings(), ev) is True
    assert classify_polarity(list(ev.member_hits), Settings(), TargetType.gene_orthologue, ev) == ClaimType.target_gene_detected


def test_teta_strong_target_strong_competitor_is_not_unilaterally_settled():
    preferred = {
        "classification": "competing_family_preferred",
        "target_family_sequence_identity": 0.88,
        "target_family_sequence_coverage": 0.90,
    }
    assert family_identity_is_decisive(preferred) is True
    ev = FamilyEvidence(
        family_id="tetA_tetracycline_efflux",
        architecture="divergent_full_length",
        supports_orthologue=False,
        reconstruction={"architecture": "divergent_full_length", "competitive_family": preferred},
        member_hits=[_hit(identity=0.88)],
    )
    assert family_detects_orthologue(_profile(), list(ev.member_hits), Settings(), ev) is False

    ambiguous = {
        "classification": "ambiguous_family",
        "target_family_sequence_identity": 0.90,
        "target_family_sequence_coverage": 0.92,
        "conflicting_evidence": ["requested and competing families are not separated by the pre-registered margin"],
    }
    assert family_identity_is_decisive(ambiguous) is False
    ev.reconstruction["competitive_family"] = ambiguous
    ev.supports_orthologue = False
    assert family_detects_orthologue(_profile(), list(ev.member_hits), Settings(), ev) is False


def test_teta_weak_target_weak_competitor_is_not_decisive():
    competitive = {
        "classification": "target_family_supported",
        "target_family_sequence_identity": 0.25,
        "target_family_sequence_coverage": 0.10,
        "conflicting_evidence": [
            "best competing family did not pass the family gate and is not treated as an alternative identity"
        ],
    }
    assert family_identity_is_decisive(competitive) is False
    m = _measurements(competitive)
    assert refine_weak_family_classification(m) is True
    assert m.family_evidence.reconstruction["competitive_family"]["classification"] == "ambiguous_family"
    ev = m.family_evidence
    ev.supports_orthologue = False
    assert family_detects_orthologue(_profile(), list(ev.member_hits), Settings(), ev) is False


def test_teta_clear_negative_competitor_preferred():
    competitive = {
        "classification": "competing_family_preferred",
        "target_family_sequence_identity": 0.12,
        "target_family_sequence_coverage": 0.08,
    }
    assert family_identity_is_decisive(competitive) is True
    ev = FamilyEvidence(
        family_id="tetA_tetracycline_efflux",
        architecture="true_no_candidate",
        supports_orthologue=False,
        reconstruction={"architecture": "true_no_candidate", "competitive_family": competitive},
        member_hits=[],
    )
    assert family_detects_orthologue(_profile(), [], Settings(), ev) is False
    assert classify_polarity([], Settings(), TargetType.gene_orthologue, ev) == ClaimType.target_gene_not_detected


def test_rpob_consistent_full_length_orthologue():
    settings = Settings()
    family = load_family("rpoB_RNAP_beta")
    rec = _rpoB_rec(hmm_coverage=0.88)
    best_hmm = {"target_id": "c1:100-4000:+", "model_coverage": 0.88, "full_evalue": 1e-80, "full_score": 1600.0}
    assert architecture_profile_coverage(rec, best_hmm) == 0.88
    rec = classify_architecture(
        reconstruction=rec,
        family=family,
        member_hits=[_hit(query_id="NP_418414.1", identity=0.84, query_coverage=0.98, tstart=100, tend=4000)],
        partner_hits=[],
        partner_hmm={},
        settings=settings,
        best_hmm=best_hmm,
    )
    assert rec.architecture in {"canonical_full_length", "divergent_full_length", "close_paralogue"}
    assert rec.architecture != "domain_only"
    ev = FamilyEvidence(
        family_id="rpoB_RNAP_beta",
        architecture=rec.architecture,
        supports_orthologue=True,
        domain_only=False,
        reconstruction=rec.model_dump(),
        best_hmm=best_hmm,
        member_hits=[_hit(query_id="NP_418414.1", identity=0.84, query_coverage=0.98, tstart=100, tend=4000)],
        hierarchy=["exact_strong_homolog", "profile_hmm_family_match"],
    )
    assert family_detects_orthologue(_profile(), list(ev.member_hits), settings, ev) is True


def test_rpob_conflicting_locus_reconstruction_uses_stronger_same_orf_profile():
    settings = Settings()
    family = load_family("rpoB_RNAP_beta")
    rec = _rpoB_rec(hmm_coverage=0.40)
    best_hmm = {"target_id": "c1:100-4000:+", "model_coverage": 0.88, "full_evalue": 0.0, "full_score": 1610.5}
    assert rec.hmm_coverage == 0.40
    assert architecture_profile_coverage(rec, best_hmm) == 0.88
    rec = classify_architecture(
        reconstruction=rec,
        family=family,
        member_hits=[_hit(query_id="NP_418414.1", identity=0.67, query_coverage=0.98, tstart=100, tend=4000)],
        partner_hits=[],
        partner_hmm={},
        settings=settings,
        best_hmm=best_hmm,
    )
    assert rec.architecture != "domain_only"
    assert rec.architecture in {"canonical_full_length", "divergent_full_length", "close_paralogue", "unresolved_candidate"}
    # The chain-union measurement itself is not rewritten.
    assert rec.hmm_coverage == 0.40


def test_rpob_strong_profile_homology_valid_architecture():
    settings = Settings()
    family = load_family("rpoB_RNAP_beta")
    rec = _rpoB_rec(hmm_coverage=0.40)
    best_hmm = {
        "target_id": "c1:100-4000:+",
        "model_coverage": 0.88,
        "full_evalue": 0.0,
        "full_score": 1610.5,
    }
    rec = classify_architecture(
        reconstruction=rec,
        family=family,
        member_hits=[_hit(query_id="WP_010871995.1", identity=0.64, query_coverage=0.98, tstart=100, tend=4000)],
        partner_hits=[],
        partner_hmm={},
        settings=settings,
        best_hmm=best_hmm,
    )
    ev = FamilyEvidence(
        family_id="rpoB_RNAP_beta",
        architecture=rec.architecture,
        supports_orthologue=rec.architecture != "domain_only",
        domain_only=rec.architecture == "domain_only",
        reconstruction=rec.model_dump(),
        best_hmm=best_hmm,
        member_hits=[_hit(query_id="WP_010871995.1", identity=0.64, query_coverage=0.98, tstart=100, tend=4000)],
        hierarchy=["multi_reference_protein_homolog", "profile_hmm_family_match"],
    )
    assert ev.domain_only is False
    assert family_detects_orthologue(_profile(), list(ev.member_hits), settings, ev) is True


def test_rpob_clear_non_target_competitor_or_domain_only_without_conflict():
    settings = Settings()
    family = load_family("rpoB_RNAP_beta")
    rec = _rpoB_rec(hmm_coverage=0.22)
    best_hmm = {"target_id": "c1:100-4000:+", "model_coverage": 0.22, "full_evalue": 1e-20, "full_score": 80.0}
    rec = classify_architecture(
        reconstruction=rec,
        family=family,
        member_hits=[],
        partner_hits=[],
        partner_hmm={},
        settings=settings,
        best_hmm=best_hmm,
    )
    assert rec.architecture in {"domain_only", "true_no_candidate"}
    ev = FamilyEvidence(
        family_id="rpoB_RNAP_beta",
        architecture=rec.architecture,
        supports_orthologue=False,
        domain_only=rec.architecture == "domain_only",
        reconstruction=rec.model_dump(),
        best_hmm=best_hmm,
        member_hits=[],
    )
    assert family_detects_orthologue(_profile(), [], settings, ev) is False

    other_orf = {"target_id": "c2:10-80:+", "model_coverage": 0.88, "full_evalue": 0.0, "full_score": 400.0}
    rec2 = _rpoB_rec(hmm_coverage=0.22)
    assert architecture_profile_coverage(rec2, other_orf) == 0.22
    rec2 = classify_architecture(
        reconstruction=rec2,
        family=family,
        member_hits=[],
        partner_hits=[],
        partner_hmm={},
        settings=settings,
        best_hmm=other_orf,
    )
    assert rec2.architecture in {"domain_only", "true_no_candidate"}
