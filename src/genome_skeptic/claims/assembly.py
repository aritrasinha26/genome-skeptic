from __future__ import annotations

from genome_skeptic.claims.attack_plan import attack_plan_id, generate_attack_plan
from genome_skeptic.claims.completeness import attach_completeness
from genome_skeptic.claims.state_machine import confidence_for, resolve_claim_status
from genome_skeptic.config import Settings
from genome_skeptic.models import (
    Claim,
    ClaimProvenance,
    ClaimStatus,
    ClaimType,
    FalsificationResult,
    FalsificationTest,
    Severity,
)


def _complete(test: FalsificationTest, result: FalsificationResult, metrics: dict, limitation: str | None = None) -> None:
    test.status = "completed"
    test.result = result
    test.metrics = metrics
    test.limitation = limitation


def _skip(test: FalsificationTest, limitation: str) -> None:
    test.status = "skipped"
    test.result = FalsificationResult.not_run
    test.limitation = limitation
    test.blocking = False


def build_assembly_claim(
    *,
    settings: Settings,
    mapping_rate: float | None,
    completeness: float | None,
    contamination: float | None,
    assembly_metrics: dict,
    anomalies,
    supporting_ids: list[str],
    contradicting_ids: list[str],
    tools: list[str],
) -> Claim:
    tests = generate_attack_plan(ClaimType.assembly_supported_for_annotation)
    by_id = {t.test_id: t for t in tests}
    hard = any(a.severity == Severity.hard for a in anomalies)

    mapping_test = by_id["read_back_mapping"]
    if mapping_rate is None:
        _skip(mapping_test, "read-back mapping was not measured")
    elif mapping_rate < settings.thresholds.min_mapping_rate_soft:
        _complete(mapping_test, FalsificationResult.weakens_claim, {"mapping_rate": mapping_rate})
    else:
        _complete(mapping_test, FalsificationResult.supports_claim, {"mapping_rate": mapping_rate})

    comp_test = by_id["completeness_estimate"]
    if completeness is None:
        _skip(comp_test, "CheckM2 completeness was not measured")
    elif completeness < settings.thresholds.min_completeness_soft:
        _complete(comp_test, FalsificationResult.weakens_claim, {"completeness": completeness})
    else:
        _complete(comp_test, FalsificationResult.supports_claim, {"completeness": completeness})

    cont_test = by_id["contamination_estimate"]
    if contamination is None:
        _skip(cont_test, "CheckM2 contamination was not measured")
    elif contamination > settings.thresholds.max_contamination_hard:
        _complete(cont_test, FalsificationResult.rejects_claim, {"contamination": contamination})
    elif contamination > settings.thresholds.max_contamination_soft:
        _complete(cont_test, FalsificationResult.weakens_claim, {"contamination": contamination})
    else:
        _complete(cont_test, FalsificationResult.supports_claim, {"contamination": contamination})

    size_test = by_id["assembly_size_and_fragmentation"]
    total = assembly_metrics.get("total_bp")
    contigs = assembly_metrics.get("contigs")
    metrics = {"total_bp": total, "contigs": contigs, "n50_bp": assembly_metrics.get("n50_bp")}
    if total is not None and total < settings.thresholds.bacterial_genome_min_bp:
        _complete(size_test, FalsificationResult.rejects_claim, metrics)
    elif (contigs is not None and contigs > settings.thresholds.max_contigs_soft) or (
        total is not None and total > settings.thresholds.bacterial_genome_max_bp
    ):
        _complete(size_test, FalsificationResult.weakens_claim, metrics)
    else:
        _complete(size_test, FalsificationResult.supports_claim, metrics)

    status = resolve_claim_status(tests)
    if hard and status == ClaimStatus.supported:
        status = ClaimStatus.unresolved
    confidence = confidence_for(status, tests, base=0.6, max_supported=settings.thresholds.max_claim_confidence)
    claim = Claim(
        claim_id="C001",
        claim_type=ClaimType.assembly_supported_for_annotation,
        statement="The assembly is sufficiently supported to proceed to gene annotation.",
        supporting_evidence_ids=supporting_ids,
        contradicting_evidence_ids=contradicting_ids,
        alternative_explanations=["fragmentation may hide loci", "contamination may distort genome content", "coverage anomalies may represent plasmids or repeats"],
        falsification_tests=tests,
        status=status,
        confidence=confidence,
        provenance=ClaimProvenance(
            created_by="deterministic_validator",
            stage="assembly_qc",
            tool_names=tools,
            attack_plan_id=attack_plan_id(ClaimType.assembly_supported_for_annotation),
        ),
        rationale="This claim is based on orthogonal validators rather than SPAdes exit status. Supported is not certainty.",
    )
    attach_completeness(claim, apply_to_confidence=settings.execution.apply_completeness_to_confidence)
    return claim


def build_annotation_claim(
    *,
    settings: Settings,
    annotation_anomalies,
    supporting_ids: list[str],
    contradicting_ids: list[str],
    tools: list[str],
    fragmented: bool,
) -> Claim:
    tests = generate_attack_plan(ClaimType.annotation_internally_plausible)
    by_id = {t.test_id: t for t in tests}
    density = by_id["gene_density_check"]
    if any(a.id == "annotation_gene_density" for a in annotation_anomalies):
        _complete(density, FalsificationResult.weakens_claim, {})
    else:
        _complete(density, FalsificationResult.supports_claim, {})
    trunc = by_id["truncated_gene_risk"]
    if fragmented:
        _complete(trunc, FalsificationResult.weakens_claim, {"fragmented": True})
    else:
        _complete(trunc, FalsificationResult.supports_claim, {"fragmented": False})
    status = resolve_claim_status(tests)
    confidence = confidence_for(status, tests, base=0.7, max_supported=settings.thresholds.max_claim_confidence)
    claim = Claim(
        claim_id="C002",
        claim_type=ClaimType.annotation_internally_plausible,
        statement="The annotation is internally plausible for the assembled bacterial genome.",
        supporting_evidence_ids=supporting_ids,
        contradicting_evidence_ids=contradicting_ids,
        alternative_explanations=["gene caller may miss atypical genes", "fragmented contigs may truncate genes", "functional names require database support"],
        falsification_tests=tests,
        status=status,
        confidence=confidence,
        provenance=ClaimProvenance(
            created_by="deterministic_validator",
            stage="annotation",
            tool_names=tools,
            attack_plan_id=attack_plan_id(ClaimType.annotation_internally_plausible),
        ),
        rationale="Internal plausibility is not proof that every predicted function is correct. Supported is not certainty.",
    )
    attach_completeness(claim, apply_to_confidence=settings.execution.apply_completeness_to_confidence)
    return claim
