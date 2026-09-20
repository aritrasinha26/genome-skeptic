from genome_skeptic.config import Settings
from genome_skeptic.eval.catalog import PUBLIC_RPOB_SEED
from genome_skeptic.eval.real_genomes import locate_target
from genome_skeptic.eval.scoring import CaseTruth, TargetTruth, group_scores, score_case
from genome_skeptic.models import Claim, ClaimProvenance, ClaimStatus, ClaimType, GeneSearchHit, TargetProfile, TargetType
from genome_skeptic.validators.homology import homology_support_score, strong_hit
from genome_skeptic.claims.state_machine import confidence_for
from genome_skeptic.claims.completeness import apply_completeness_to_confidence, score_evidence_completeness
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim


def _write_fa(path, records):
    path.write_text("".join(f">{name}\n{seq}\n" for name, seq in records.items()))
    return path


def test_locate_target_52_of_122_is_not_full_gene_presence(tmp_path):
    """Regression: 52/122 bp identity-only call must not become present."""
    seed = PUBLIC_RPOB_SEED
    assert len(seed) == 122
    fragment = seed[:52]
    genome = tmp_path / "g.fa"
    _write_fa(genome, {"c1": "A" * 80 + fragment + "C" * 80})
    loc = locate_target(genome, seed, min_identity=0.50, min_coverage=0.0)
    # Historical false truth: identity >= 0.5 with no coverage floor.
    assert loc["alignment_length"] == 52 or (loc["coverage"] or 0) < 0.5 or loc["n_hits"] >= 1
    repaired = locate_target(genome, seed)
    assert repaired["present"] is False
    assert (repaired["coverage"] or 0) < repaired["min_coverage"]


def test_locate_target_requires_identity_and_coverage(tmp_path):
    genome = tmp_path / "g.fa"
    query = "ATG" + ("CGTAGC") * 20 + "TAA"
    _write_fa(genome, {"c1": "N" * 40 + query + "N" * 40})
    loc = locate_target(genome, query)
    assert loc["present"] is True
    assert loc["identity"] >= loc["min_identity"]
    assert loc["coverage"] >= loc["min_coverage"]


def test_target_types_are_not_interchangeable():
    settings = Settings()
    nt_hit = GeneSearchHit(
        query_id="rpoB", contig_id="c1", search_kind="nucleotide",
        qstart=0, qend=100, tstart=10, tend=110, strand="+",
        identity=0.90, query_coverage=0.90, alignment_length=100,
        query_length=100, contig_length=400,
    )
    aa_hit = GeneSearchHit(
        query_id="rpoB", contig_id="c1", search_kind="translated",
        qstart=0, qend=80, tstart=10, tend=250, strand="+",
        identity=0.70, query_coverage=0.85, alignment_length=240,
        query_length=80, contig_length=400,
    )
    domain_hit = GeneSearchHit(
        query_id="rpoB", contig_id="c1", search_kind="domain",
        qstart=0, qend=40, tstart=10, tend=130, strand="+",
        identity=0.95, query_coverage=0.30, alignment_length=120,
        query_length=80, contig_length=400, domain_name="RNAP_beta",
    )
    assert strong_hit(nt_hit, settings, TargetType.exact_allele) is False
    nt_allele = nt_hit.model_copy(update={"identity": 0.995, "query_coverage": 0.99})
    assert strong_hit(nt_allele, settings, TargetType.exact_allele) is True
    assert strong_hit(nt_allele, settings, TargetType.gene_orthologue) is False
    assert strong_hit(aa_hit, settings, TargetType.gene_orthologue) is True
    assert strong_hit(aa_hit, settings, TargetType.exact_allele) is False
    assert strong_hit(domain_hit, settings, TargetType.gene_orthologue) is False
    assert strong_hit(domain_hit, settings, TargetType.protein_family) is False
    family = homology_support_score([domain_hit], settings, TargetType.protein_family)
    assert family["domain_only"] is True
    assert family["score"] <= 0.35


def test_clean_true_positive_not_detected_weakened_is_error():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=True, clean=True, target_type="gene_orthologue")})
    dummy = Claim(
        claim_id="C_target_rpoB",
        claim_type=ClaimType.target_gene_not_detected,
        statement="Target gene 'rpoB' was not detected in the current assembly.",
        status=ClaimStatus.weakened,
        confidence=0.46,
        evidence_completeness=0.63,
        provenance=ClaimProvenance(stage="target_gene"),
        rationale="Dummy cautious baseline.",
    )
    totals, _ = score_case("tp", [dummy], [], truth)
    assert totals["false_absence"].correct == 0
    assert totals["underclaiming"].correct == 0
    assert totals["status_appropriateness"].correct == 0


def test_clean_true_negative_prefers_supported_non_detection():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=False, clean=True, target_type="exact_allele")})
    supported = Claim(
        claim_id="C_target_rpoB",
        claim_type=ClaimType.target_gene_not_detected,
        statement="Target gene 'rpoB' was not detected in the current assembly.",
        status=ClaimStatus.supported,
        confidence=0.55,
        evidence_completeness=0.40,
        provenance=ClaimProvenance(stage="target_gene"),
        rationale="Assembly-scoped non-detection.",
    )
    dummy = Claim(
        claim_id="C_target_rpoB",
        claim_type=ClaimType.target_gene_not_detected,
        statement="Target gene 'rpoB' was not detected in the current assembly.",
        status=ClaimStatus.weakened,
        confidence=0.46,
        evidence_completeness=0.63,
        provenance=ClaimProvenance(stage="target_gene"),
        rationale="Dummy cautious baseline.",
    )
    tot_ok, _ = score_case("tn", [supported], [], truth)
    tot_dummy, _ = score_case("tn", [dummy], [], truth)
    assert tot_ok["status_appropriateness"].correct == 1
    assert tot_dummy["status_appropriateness"].correct == 0


def test_ambiguous_negative_organism_absence_is_strongly_penalized():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=False, uncertainty_required=True, clean=False)})
    naive = Claim(
        claim_id="C_target_rpoB",
        claim_type=ClaimType.target_gene_not_detected,
        statement="Target gene 'rpoB' is absent from the organism.",
        status=ClaimStatus.supported,
        confidence=0.99,
        evidence_completeness=0.15,
        provenance=ClaimProvenance(stage="target_gene"),
        rationale="Naive confident baseline.",
    )
    totals, _ = score_case("ambneg", [naive], [], truth)
    assert totals["unsupported_organism_level_claims"].correct == 0
    assert totals["unsupported_overclaiming"].correct == 0
    assert totals["claim_scope_correctness"].correct == 0


def test_confidence_differs_when_homology_differs_and_completeness_is_shared():
    rec = score_evidence_completeness(ClaimType.target_gene_detected, [])
    weak = confidence_for(ClaimStatus.weakened, [], base=0.7, max_supported=0.85, homology_support=0.20)
    strong = confidence_for(ClaimStatus.weakened, [], base=0.7, max_supported=0.85, homology_support=0.90)
    weak = apply_completeness_to_confidence(weak, rec)
    strong = apply_completeness_to_confidence(strong, rec)
    assert rec.score == rec.score
    assert strong - weak >= 0.15


def test_group_scores_are_not_a_single_overall():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=True, clean=True)})
    claim = Claim(
        claim_id="C_target_rpoB",
        claim_type=ClaimType.target_gene_detected,
        statement="Target gene 'rpoB' is detected in the current assembly.",
        status=ClaimStatus.supported,
        confidence=0.70,
        evidence_completeness=0.40,
        provenance=ClaimProvenance(stage="target_gene"),
        rationale="ok",
    )
    totals, _ = score_case("g", [claim], [], truth)
    groups = group_scores(totals)
    assert "detection_correctness" in groups
    assert "confidence_calibration" in groups
    assert "underclaiming" in groups
    assert groups["detection_correctness"]["rate"] is not None


def test_full_length_orthologue_survives_missing_optional_validators():
    settings = Settings()
    seq = "ATG" + ("CGTAGC") * 40 + "TAA"
    hit = GeneSearchHit(
        query_id="rpoB", contig_id="c1", search_kind="translated",
        qstart=0, qend=len(seq) // 3, tstart=80, tend=80 + len(seq), strand="+",
        identity=0.92, query_coverage=0.98, alignment_length=len(seq),
        query_length=len(seq) // 3, contig_length=80 + len(seq) + 80,
    )
    m = TargetMeasurements(
        query_id="rpoB",
        profile=TargetProfile(query_id="rpoB", sequence=seq, target_type=TargetType.gene_orthologue),
        hits=[hit],
        contig_sequences={"c1": "N" * 80 + seq + "N" * 80},
        falsification_enabled=True,
    )
    claim, _, _tests = build_target_gene_claim(m, settings, [])
    assert claim.claim_type == ClaimType.target_gene_detected
    assert claim.homology_support is not None
    assert claim.homology_support > 0.5
    assert claim.confidence != claim.evidence_completeness
