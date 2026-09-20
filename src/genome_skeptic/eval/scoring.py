from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from genome_skeptic.claims.actions import classify_actions
from genome_skeptic.models import Claim, ClaimStatus, ClaimType, LocusEvidence
from genome_skeptic.validators.homology import FORBIDDEN_ABSENCE_PHRASES


METRIC_NAMES = (
    "correct_detection",
    "false_detection",
    "correct_non_detection",
    "false_absence",
    "contamination_recognition",
    "paralogue_recognition",
    "fragmentation_recognition",
    "appropriate_uncertainty",
    "unsupported_overclaiming",
    "useful_follow_up_analyses",
    "unnecessary_analyses",
    "correct_next_action",
    "overconfidence_on_ambiguous",
    "underconfidence_on_clean",
    "calibration_error",
    "appropriate_abstention",
    "appropriate_escalation",
    "unsupported_organism_level_claims",
    "completeness_confidence_consistency",
    "redundant_analyses",
    "irrelevant_analyses",
    "harmful_next_actions",
    "status_appropriateness",
    "claim_scope_correctness",
    "underclaiming",
)

SCORE_GROUPS = {
    "detection_correctness": (
        "correct_detection", "false_detection", "correct_non_detection", "false_absence",
    ),
    "claim_scope_correctness": ("claim_scope_correctness", "unsupported_organism_level_claims"),
    "status_appropriateness": ("status_appropriateness", "appropriate_uncertainty"),
    "confidence_calibration": ("calibration_error", "overconfidence_on_ambiguous"),
    "evidence_completeness_consistency": ("completeness_confidence_consistency",),
    "overclaiming": ("unsupported_overclaiming",),
    "underclaiming": ("underclaiming", "underconfidence_on_clean"),
    "appropriate_abstention": ("appropriate_abstention",),
    "next_action_usefulness": (
        "useful_follow_up_analyses", "correct_next_action", "harmful_next_actions",
        "unnecessary_analyses",
    ),
}

# Composite convenience score only. Reports must show SCORE_GROUPS separately.
SCIENTIFIC_METRICS = (
    "correct_detection",
    "false_detection",
    "correct_non_detection",
    "false_absence",
    "unsupported_overclaiming",
    "overconfidence_on_ambiguous",
    "underconfidence_on_clean",
    "unsupported_organism_level_claims",
    "completeness_confidence_consistency",
    "status_appropriateness",
    "underclaiming",
    "claim_scope_correctness",
)


class TargetTruth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    present: bool | None = None
    paralogue: bool = False
    contaminant: bool = False
    fragmented: bool = False
    uncertainty_required: bool = False
    overclaim_forbidden: bool = True
    clean: bool | None = None
    target_type: str | None = None
    truth_state: str = "resolved"
    provenance: dict[str, Any] = Field(default_factory=dict)


class CaseTruth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    targets: dict[str, TargetTruth]
    expected_actions: list[str] = Field(default_factory=list)
    expected_next_action: str | None = None
    acceptable_action_classes: list[str] = Field(default_factory=list)
    harmful_action_classes: list[str] = Field(default_factory=list)
    corruption: str | None = None
    true_organism: str | None = None
    label: str | None = None
    genome_id: str | None = None
    split: str | None = None


class HiddenTruth(BaseModel):
    cases: dict[str, CaseTruth]


class MetricCount(BaseModel):
    n: int = 0
    correct: int = 0

    @property
    def rate(self) -> float | None:
        if self.n == 0:
            return None
        return self.correct / self.n


class TargetScore(BaseModel):
    case_id: str
    target: str
    claim_type: str | None = None
    claim_status: str | None = None
    confidence: float | None = None
    evidence_completeness: float | None = None
    hits: dict[str, bool] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    totals: dict[str, MetricCount] = Field(default_factory=dict)
    targets: list[TargetScore] = Field(default_factory=list)
    overall: float | None = None

    def as_json(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["totals"] = {
            name: {**row, "rate": self.totals[name].rate}
            for name, row in payload["totals"].items()
        }
        return payload


def _tests_by_prefix(claim: Claim, prefixes: tuple[str, ...]) -> list:
    return [t for t in claim.falsification_tests if t.test_id.split(":")[0] in prefixes]


def _challenged(claim: Claim, prefixes: tuple[str, ...]) -> bool:
    return any(
        t.result.value in {"weakens_claim", "rejects_claim"}
        for t in _tests_by_prefix(claim, prefixes)
    )


def _conflict_hit(loci: list[LocusEvidence], names: set[str]) -> bool:
    return any(name in le.conflicts for le in loci for name in names)


def _organism_level(claim: Claim) -> bool:
    blob = f"{claim.statement} {claim.rationale}".lower()
    return any(p in blob for p in FORBIDDEN_ABSENCE_PHRASES) or "present in the isolate" in blob


def _is_clean(expected: TargetTruth) -> bool:
    if expected.truth_state == "unresolved" or expected.present is None:
        return False
    if expected.clean is not None:
        return expected.clean
    return bool(expected.present) and not (expected.paralogue or expected.contaminant or expected.fragmented or expected.uncertainty_required)


def _is_ambiguous(expected: TargetTruth) -> bool:
    return expected.paralogue or expected.contaminant or expected.fragmented or expected.uncertainty_required


def scientifically_correct(claim: Claim, expected: TargetTruth) -> bool:
    """Polarity and scope vs hidden biology. Status/confidence are scored separately."""
    if expected.truth_state == "unresolved" or expected.present is None:
        return not _organism_level(claim)
    detected = claim.claim_type == ClaimType.target_gene_detected
    not_detected = claim.claim_type == ClaimType.target_gene_not_detected
    if _organism_level(claim):
        return False
    if expected.present and not expected.fragmented:
        return detected
    if expected.present and expected.fragmented:
        return not_detected or claim.status in {ClaimStatus.weakened, ClaimStatus.unresolved}
    if not expected.present:
        return not_detected
    return False


def _overclaimed(claim: Claim, truth: TargetTruth) -> bool:
    blob = f"{claim.statement} {claim.rationale}".lower()
    if any(p in blob for p in FORBIDDEN_ABSENCE_PHRASES):
        return True
    if claim.confidence >= 0.95:
        return True
    if truth.overclaim_forbidden and claim.status == ClaimStatus.supported:
        if truth.paralogue or truth.contaminant or truth.fragmented or truth.uncertainty_required:
            return True
        if truth.present is False and claim.claim_type == ClaimType.target_gene_detected:
            return True
    return False


def _scientifically_correct(claim: Claim, expected: TargetTruth) -> bool:
    return scientifically_correct(claim, expected)


def score_case(
    case_id: str,
    claims: list[Claim],
    loci: list[LocusEvidence],
    truth: CaseTruth,
) -> tuple[dict[str, MetricCount], list[TargetScore]]:
    totals = {name: MetricCount() for name in METRIC_NAMES}
    rows: list[TargetScore] = []
    by_target = {c.claim_id.replace("C_target_", ""): c for c in claims}
    by_query = {}
    for claim in claims:
        by_query[claim.claim_id] = claim
        if claim.claim_id.startswith("C_target_"):
            by_query[claim.claim_id[len("C_target_"):]] = claim
    for target, expected in truth.targets.items():
        claim = by_query.get(target) or by_target.get(target)
        target_loci = [le for le in loci if le.target == target]
        row = TargetScore(case_id=case_id, target=target)
        if claim is None:
            row.notes.append("no claim produced")
            rows.append(row)
            continue
        row.claim_type = claim.claim_type.value
        row.claim_status = claim.status.value
        row.confidence = claim.confidence
        row.evidence_completeness = claim.evidence_completeness
        detected = claim.claim_type == ClaimType.target_gene_detected
        not_detected = claim.claim_type == ClaimType.target_gene_not_detected
        unresolved_truth = expected.truth_state == "unresolved" or expected.present is None
        present = bool(expected.present) and not unresolved_truth

        if unresolved_truth:
            totals["unsupported_overclaiming"].n += 1
            totals["unsupported_overclaiming"].correct += 0 if _overclaimed(claim, expected) else 1
            totals["unsupported_organism_level_claims"].n += 1
            totals["unsupported_organism_level_claims"].correct += 0 if _organism_level(claim) else 1
            totals["claim_scope_correctness"].n += 1
            totals["claim_scope_correctness"].correct += 0 if _organism_level(claim) else 1
            row.notes.append("ground truth unresolved; binary detection not scored")
            rows.append(row)
            continue

        detection_applicable = present and not expected.fragmented
        totals["correct_detection"].n += 1 if detection_applicable else 0
        if detection_applicable and detected:
            totals["correct_detection"].correct += 1
            row.hits["correct_detection"] = True

        totals["false_detection"].n += 1 if not present else 0
        if not present:
            false_pos = detected and claim.status in {ClaimStatus.supported, ClaimStatus.weakened}
            totals["false_detection"].correct += 0 if false_pos else 1
            row.hits["false_detection"] = not false_pos

        totals["correct_non_detection"].n += 1 if not present else 0
        if not present and not_detected:
            totals["correct_non_detection"].correct += 1
            row.hits["correct_non_detection"] = True

        totals["false_absence"].n += 1 if present else 0
        if present:
            clean_pos = _is_clean(expected) and not expected.fragmented
            if clean_pos:
                false_neg = not_detected
            else:
                false_neg = not_detected and (claim.status == ClaimStatus.supported or _organism_level(claim))
            totals["false_absence"].correct += 0 if false_neg else 1
            row.hits["false_absence"] = not false_neg

        if expected.contaminant:
            totals["contamination_recognition"].n += 1
            recognized = (
                _challenged(claim, ("contamination", "taxonomic_inconsistency", "taxonomic_consistency_of_locus"))
                or _conflict_hit(target_loci, {"taxonomic_inconsistency"})
            )
            totals["contamination_recognition"].correct += int(recognized)
            row.hits["contamination_recognition"] = recognized

        if expected.paralogue:
            totals["paralogue_recognition"].n += 1
            recognized = (
                _challenged(claim, ("wrong_paralogue", "orthology_versus_paralogy", "reciprocal_best_hit", "phylogenetic_placement"))
                or _conflict_hit(target_loci, {"paralogous_copies", "not_reciprocal_best_hit", "phylogenetic_paralog"})
                or any((le.sequence_similarity or {}).get("orthology_class") in {"paralog", "paralog_or_xenolog"} for le in target_loci)
            )
            totals["paralogue_recognition"].correct += int(recognized)
            row.hits["paralogue_recognition"] = recognized

        if expected.fragmented:
            totals["fragmentation_recognition"].n += 1
            recognized = (
                _challenged(claim, ("assembly_fragmentation", "contig_edge_truncation", "contig_edge_effects", "missing_in_fragmented_region", "read_supported_break"))
                or _conflict_hit(target_loci, {"contig_edge"})
            )
            totals["fragmentation_recognition"].correct += int(recognized)
            row.hits["fragmentation_recognition"] = recognized

        ambiguous = _is_ambiguous(expected)
        clean = _is_clean(expected)
        overclaimed = _overclaimed(claim, expected)
        organism = _organism_level(claim)
        overconfident = ambiguous and (
            organism
            or claim.confidence >= 0.80
            or (claim.status == ClaimStatus.supported and expected.uncertainty_required)
        )
        underconfident = clean and present and (
            not_detected
            or (detected and claim.status in {ClaimStatus.unresolved, ClaimStatus.rejected})
            or (detected and claim.status == ClaimStatus.weakened and (claim.confidence or 0) <= 0.35)
        )

        if expected.uncertainty_required or ambiguous:
            totals["appropriate_uncertainty"].n += 1
            recognized = (not overconfident) and claim.status in {ClaimStatus.unresolved, ClaimStatus.weakened, ClaimStatus.rejected}
            totals["appropriate_uncertainty"].correct += int(recognized)
            row.hits["appropriate_uncertainty"] = recognized

        totals["unsupported_overclaiming"].n += 1
        totals["unsupported_overclaiming"].correct += 0 if overclaimed else 1
        row.hits["unsupported_overclaiming"] = not overclaimed

        if ambiguous:
            totals["overconfidence_on_ambiguous"].n += 1
            totals["overconfidence_on_ambiguous"].correct += 0 if overconfident else 1
            row.hits["overconfidence_on_ambiguous"] = not overconfident
            totals["appropriate_abstention"].n += 1
            abstained = (not overconfident) and not organism
            totals["appropriate_abstention"].correct += int(abstained)
            row.hits["appropriate_abstention"] = abstained

        if clean:
            totals["underconfidence_on_clean"].n += 1
            totals["underconfidence_on_clean"].correct += 0 if underconfident else 1
            row.hits["underconfidence_on_clean"] = not underconfident

        totals["calibration_error"].n += 1
        correctness = 1.0 if _scientifically_correct(claim, expected) else 0.0
        error = abs((claim.confidence or 0) - correctness)
        totals["calibration_error"].correct += int(error <= 0.45)
        row.hits["calibration_error"] = error <= 0.45

        totals["unsupported_organism_level_claims"].n += 1
        totals["unsupported_organism_level_claims"].correct += 0 if organism else 1
        row.hits["unsupported_organism_level_claims"] = not organism

        totals["claim_scope_correctness"].n += 1
        totals["claim_scope_correctness"].correct += 0 if organism else 1
        row.hits["claim_scope_correctness"] = not organism

        totals["underclaiming"].n += 1
        underclaim = clean and present and not_detected
        totals["underclaiming"].correct += 0 if underclaim else 1
        row.hits["underclaiming"] = not underclaim

        status_ok = True
        if clean and present and not expected.fragmented:
            status_ok = detected and claim.status in {ClaimStatus.supported, ClaimStatus.weakened}
            if not_detected:
                status_ok = False
        elif clean and not present:
            status_ok = not_detected and claim.status == ClaimStatus.supported and not organism
        elif present and (expected.fragmented or expected.uncertainty_required or expected.paralogue or expected.contaminant):
            status_ok = claim.status in {ClaimStatus.weakened, ClaimStatus.unresolved} or (
                detected and not organism and (claim.confidence or 0) < 0.80
            )
        elif not present and ambiguous:
            status_ok = not_detected and not organism
        totals["status_appropriateness"].n += 1
        totals["status_appropriateness"].correct += int(status_ok)
        row.hits["status_appropriateness"] = status_ok

        totals["completeness_confidence_consistency"].n += 1
        complete = claim.evidence_completeness
        consistent = True
        if complete < 0.45 and (claim.confidence or 0) >= 0.75:
            consistent = False
        if complete >= 0.8 and clean and detected and (claim.confidence or 0) < 0.35:
            consistent = False
        totals["completeness_confidence_consistency"].correct += int(consistent)
        row.hits["completeness_confidence_consistency"] = consistent
        rows.append(row)
    return totals, rows


def score_actions(totals: dict[str, MetricCount], proposed: list[str], truth: CaseTruth) -> dict[str, MetricCount]:
    classes = list(truth.acceptable_action_classes or [])
    if not classes and truth.expected_actions:
        from genome_skeptic.claims.actions import class_for_action
        classes = [class_for_action(a) for a in truth.expected_actions]
    grouped = classify_actions(proposed, acceptable_classes=classes, harmful_classes=truth.harmful_action_classes)
    useful = grouped["useful"]
    redundant = grouped["reasonable_redundant"]
    irrelevant = grouped["irrelevant"]
    harmful = grouped["potentially_harmful"]

    if classes or proposed:
        totals["useful_follow_up_analyses"].n += max(1, len(classes) or 1)
        totals["useful_follow_up_analyses"].correct += min(len(useful), totals["useful_follow_up_analyses"].n)
    totals["redundant_analyses"].n += 1
    totals["redundant_analyses"].correct += 0 if redundant else 1
    totals["irrelevant_analyses"].n += 1
    totals["irrelevant_analyses"].correct += 0 if irrelevant else 1
    totals["harmful_next_actions"].n += 1
    totals["harmful_next_actions"].correct += 0 if harmful else 1
    extras = irrelevant + harmful
    totals["unnecessary_analyses"].n += 1
    totals["unnecessary_analyses"].correct += 0 if extras else 1
    totals["appropriate_escalation"].n += 1
    escalate_ok = (not harmful) and (bool(useful) or not classes)
    totals["appropriate_escalation"].correct += int(escalate_ok)
    totals["correct_next_action"].n += 1
    totals["correct_next_action"].correct += int(escalate_ok)
    return totals


def merge_totals(parts: list[dict[str, MetricCount]]) -> dict[str, MetricCount]:
    out = {name: MetricCount() for name in METRIC_NAMES}
    for part in parts:
        for name, row in part.items():
            if name not in out:
                out[name] = MetricCount()
            out[name].n += row.n
            out[name].correct += row.correct
    return out


def overall_score(totals: dict[str, MetricCount]) -> float | None:
    applicable = [totals[name] for name in SCIENTIFIC_METRICS if name in totals and totals[name].n]
    if not applicable:
        applicable = [row for row in totals.values() if row.n]
    if not applicable:
        return None
    return sum(row.correct for row in applicable) / sum(row.n for row in applicable)


def group_scores(totals: dict[str, MetricCount]) -> dict[str, dict]:
    out = {}
    for group, names in SCORE_GROUPS.items():
        rows = [totals[name] for name in names if name in totals and totals[name].n]
        if not rows:
            out[group] = {"n": 0, "correct": 0, "rate": None}
            continue
        n = sum(r.n for r in rows)
        correct = sum(r.correct for r in rows)
        out[group] = {"n": n, "correct": correct, "rate": correct / n if n else None}
    return out
