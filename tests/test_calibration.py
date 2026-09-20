from genome_skeptic.eval.scoring import CaseTruth, TargetTruth, overall_score, score_case
from genome_skeptic.models import Claim, ClaimProvenance, ClaimStatus, ClaimType


def _claim(status: ClaimStatus, confidence: float, statement: str, completeness: float = 0.7) -> Claim:
    return Claim(
        claim_id="C_target_rpoB",
        claim_type=ClaimType.target_gene_detected if "detected" in statement else ClaimType.target_gene_not_detected,
        statement=statement,
        status=status,
        confidence=confidence,
        evidence_completeness=completeness,
        provenance=ClaimProvenance(stage="target_gene"),
        rationale="Adversarial attack plan executed. Status is a claim-state, not certainty.",
    )


def test_clean_locus_penalizes_unresolved():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=True, clean=True)})
    cautious = _claim(ClaimStatus.unresolved, 0.3, "Target gene 'rpoB' is detected in the current assembly.")
    totals, _ = score_case("clean", [cautious], [], truth)
    assert totals["underconfidence_on_clean"].n == 1
    assert totals["underconfidence_on_clean"].correct == 0


def test_ambiguous_locus_penalizes_high_confidence_support():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=True, paralogue=True, uncertainty_required=True)})
    cocky = _claim(ClaimStatus.supported, 0.84, "Target gene 'rpoB' is detected in the current assembly.")
    totals, _ = score_case("para", [cocky], [], truth)
    assert totals["overconfidence_on_ambiguous"].correct == 0


def test_scientific_overall_does_not_reward_universal_caution():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=True, clean=True)})
    ok = _claim(ClaimStatus.supported, 0.7, "Target gene 'rpoB' is detected in the current assembly.", completeness=0.85)
    cautious = _claim(ClaimStatus.unresolved, 0.2, "Target gene 'rpoB' is detected in the current assembly.", completeness=0.2)
    tot_ok, _ = score_case("c1", [ok], [], truth)
    tot_bad, _ = score_case("c1", [cautious], [], truth)
    assert overall_score(tot_ok) > overall_score(tot_bad)


def test_organism_level_absence_is_unsupported():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=False, overclaim_forbidden=True)})
    claim = Claim(
        claim_id="C_target_rpoB",
        claim_type=ClaimType.target_gene_not_detected,
        statement="Target gene 'rpoB' is absent from the organism.",
        status=ClaimStatus.supported,
        confidence=0.99,
        evidence_completeness=0.15,
        provenance=ClaimProvenance(stage="target_gene"),
        rationale="No hit.",
    )
    totals, _ = score_case("abs", [claim], [], truth)
    assert totals["unsupported_organism_level_claims"].correct == 0
