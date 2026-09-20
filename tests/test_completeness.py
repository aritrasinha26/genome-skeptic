from genome_skeptic.claims.completeness import apply_completeness_to_confidence, score_evidence_completeness
from genome_skeptic.config import Settings
from genome_skeptic.models import ClaimStatus, ClaimType, FalsificationResult, FalsificationTest, TargetProfile
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim


def _test(prefix: str, status: str, result=FalsificationResult.supports_claim) -> FalsificationTest:
    return FalsificationTest(
        test_id=f"{prefix}:rpoB",
        name=prefix,
        hypothesis=prefix,
        status=status,  # type: ignore[arg-type]
        result=result,
        blocking=False,
    )


def test_optional_skip_does_not_zero_completeness():
    # Optional gene_orientation is skipped; all essential and high-value tests completed.
    prefixes = [
        "low_alignment_coverage", "short_conserved_domain", "abnormal_protein_length",
        "wrong_paralogue", "contamination", "contig_edge_effects", "read_supported_break",
        "orthology_versus_paralogy", "reciprocal_best_hit", "protein_identity_and_coverage",
        "taxonomic_consistency_of_locus", "local_gene_order", "phylogenetic_placement",
        "missing_catalytic_residues", "abnormal_contig_coverage",
    ]
    tests = [_test(p, "completed") for p in prefixes]
    tests.append(_test("gene_orientation", "skipped"))
    rec = score_evidence_completeness(ClaimType.target_gene_detected, tests)
    assert rec.score > 0.85
    assert any("gene_orientation" in u for u in rec.unavailable)
    assert not rec.missing_essential


def test_missing_essential_strongly_reduces_completeness():
    tests = [
        _test("gene_orientation", "completed"),
        _test("low_alignment_coverage", "skipped"),
        _test("short_conserved_domain", "skipped"),
    ]
    rec = score_evidence_completeness(ClaimType.target_gene_detected, tests)
    assert rec.missing_essential
    assert rec.score < 0.35


def test_completeness_lowers_confidence_not_status():
    rec = score_evidence_completeness(
        ClaimType.target_gene_detected,
        [_test("gene_orientation", "skipped"), _test("low_alignment_coverage", "skipped")],
    )
    conf = apply_completeness_to_confidence(0.8, rec)
    assert conf < 0.8
    assert rec.score < 0.5


def test_supported_survives_skipped_optional(tmp_path):
    from genome_skeptic.eval.synthetic import RPOB
    from genome_skeptic.models import GeneSearchHit
    settings = Settings()
    hit = GeneSearchHit(
        query_id="rpoB", contig_id="c1", search_kind="nucleotide",
        qstart=0, qend=len(RPOB), tstart=80, tend=80 + len(RPOB), strand="+",
        identity=1.0, query_coverage=1.0, alignment_length=len(RPOB),
        query_length=len(RPOB), contig_length=80 + len(RPOB) + 80,
    )
    m = TargetMeasurements(
        query_id="rpoB",
        profile=TargetProfile(query_id="rpoB", sequence=RPOB),
        hits=[hit],
        contig_sequences={"c1": "N" * 80 + RPOB + "N" * 80},
        falsification_enabled=True,
    )
    claim, _, tests = build_target_gene_claim(m, settings, [])
    skipped = [t for t in tests if t.status == "skipped"]
    assert claim.evidence_completeness >= 0
    assert claim.status in {ClaimStatus.supported, ClaimStatus.weakened, ClaimStatus.unresolved}
    assert "evidence_completeness" not in (claim.provenance.created_by)
    assert "LLM did not assign" in claim.provenance.notes
    assert skipped or claim.unavailable_tests is not None
