from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.eval.harness import evaluate_benchmark
from genome_skeptic.eval.scoring import CaseTruth, TargetTruth, score_case
from genome_skeptic.eval.synthetic import write_benchmark_tree
from genome_skeptic.locus import pipeline as locus_pipeline
from genome_skeptic.models import Claim, ClaimStatus, ClaimType, ClaimProvenance, LocusEvidence


def _claim(query: str, claim_type: ClaimType, status: ClaimStatus, confidence: float = 0.7, tests: list | None = None) -> Claim:
    return Claim(
        claim_id=f"C_target_{query}",
        claim_type=claim_type,
        statement=f"Target gene '{query}' is detected in the current assembly." if claim_type == ClaimType.target_gene_detected else f"Target gene '{query}' was not detected in the current assembly.",
        status=status,
        confidence=confidence,
        falsification_tests=tests or [],
        provenance=ClaimProvenance(stage="target_gene"),
        rationale="Adversarial attack plan executed. Status is a claim-state, not certainty. The statement is limited to the current assembly; it is not a claim that the gene is missing from the organism.",
    )


def test_scorer_does_not_require_the_agent_path():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=True, paralogue=True, uncertainty_required=True)})
    from genome_skeptic.models import FalsificationResult, FalsificationTest

    tests = [
        FalsificationTest(
            test_id="orthology_versus_paralogy:rpoB",
            name="orthology versus paralogy",
            hypothesis="paralog",
            status="completed",
            result=FalsificationResult.weakens_claim,
        )
    ]
    claim = _claim("rpoB", ClaimType.target_gene_detected, ClaimStatus.weakened, tests=tests)
    loci = [LocusEvidence(target="rpoB", conflicts=["paralogous_copies"], sequence_similarity={"orthology_class": "paralog"})]
    totals, rows = score_case("paralogue_copy", [claim], loci, truth)
    assert totals["correct_detection"].correct == 1
    assert totals["paralogue_recognition"].correct == 1
    assert totals["appropriate_uncertainty"].correct == 1
    assert totals["unsupported_overclaiming"].correct == 1
    assert rows[0].hits["paralogue_recognition"] is True


def test_scorer_flags_false_detection_and_overclaiming():
    truth = CaseTruth(targets={"rpoB": TargetTruth(present=False, overclaim_forbidden=True)})
    claim = _claim("rpoB", ClaimType.target_gene_detected, ClaimStatus.supported, confidence=0.84)
    totals, _rows = score_case("clean_absence", [claim], [], truth)
    assert totals["false_detection"].correct == 0
    assert totals["correct_non_detection"].correct == 0
    assert totals["unsupported_overclaiming"].correct == 0


def test_pipeline_source_never_loads_hidden_truth():
    source = Path(locus_pipeline.__file__).read_text()
    assert "truth.yaml" not in source
    assert "hidden" not in source
    assert "ground_truth" not in source
    assert "ground-truth" not in source


def test_evaluate_harness_loads_truth_only_after_predictions(tmp_path: Path):
    root = tmp_path / "benchmarks"
    write_benchmark_tree(root)
    report = evaluate_benchmark(root / "cases", root / "hidden" / "truth.yaml", tmp_path / "eval_out", Settings())
    payload = report.as_json()
    assert set(payload["totals"]) >= {
        "correct_detection",
        "false_detection",
        "correct_non_detection",
        "false_absence",
        "contamination_recognition",
        "paralogue_recognition",
        "fragmentation_recognition",
        "appropriate_uncertainty",
        "unsupported_overclaiming",
    }
    assert payload["overall"] is not None
    case_ids = {row["case_id"] for row in payload["targets"]}
    assert "syntenic_ortholog" in case_ids
    assert "clean_absence" in case_ids
    assert "realistic_rpo_operon" in case_ids
    syntenic = next(row for row in payload["targets"] if row["case_id"] == "syntenic_ortholog")
    assert syntenic["claim_type"] == ClaimType.target_gene_detected.value
    absence = next(row for row in payload["targets"] if row["case_id"] == "clean_absence")
    assert absence["claim_type"] == ClaimType.target_gene_not_detected.value
    para = next(row for row in payload["targets"] if row["case_id"] == "paralogue_copy")
    assert para["hits"].get("paralogue_recognition") is True
    scrambled = next(row for row in payload["targets"] if row["case_id"] == "scrambled_synteny")
    assert scrambled["claim_status"] in {"weakened", "rejected"}
