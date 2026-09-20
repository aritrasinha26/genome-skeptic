"""Deterministic evidence-completeness for claims.

The LLM does not assign these values. Completeness is computed from which
expected validators actually completed, using a documented importance class.

Status and confidence stay separate. Missing optional tests do not force
``unresolved``. Missing essential tests lower completeness (and may lower
confidence) without automatically converting a supported claim.
"""
from __future__ import annotations

from dataclasses import dataclass

from genome_skeptic.models import ClaimType, FalsificationTest

IMPORTANCE_WEIGHTS = {
    "essential": 4.0,
    "high_value": 2.0,
    "supporting": 1.0,
    "optional": 0.25,
}

# Documented importance for each falsification-test prefix.
TEST_IMPORTANCE: dict[str, str] = {
    # detection polarity / homology quality
    "wrong_paralogue": "high_value",
    "short_conserved_domain": "essential",
    "low_alignment_coverage": "essential",
    "abnormal_protein_length": "high_value",
    "missing_catalytic_residues": "supporting",
    "contamination": "high_value",
    "abnormal_contig_coverage": "supporting",
    "taxonomic_inconsistency": "high_value",
    "inconsistent_genomic_neighborhood": "supporting",
    "orthology_versus_paralogy": "high_value",
    "reciprocal_best_hit": "high_value",
    "gene_length_conservation": "supporting",
    "protein_identity_and_coverage": "high_value",
    "gene_orientation": "optional",
    "upstream_downstream_orthologues": "supporting",
    "local_gene_order": "supporting",
    "intergenic_spacing": "optional",
    "contig_edge_effects": "high_value",
    "taxonomic_consistency_of_locus": "high_value",
    "read_supported_break": "high_value",
    "phylogenetic_placement": "supporting",
    "family_profile_hmm": "high_value",
    "fusion_orf": "high_value",
    "split_gene": "high_value",
    # non-detection
    "nucleotide_homology": "essential",
    "translated_homology": "essential",
    "predicted_protein_homology": "high_value",
    "partial_domain_hits": "high_value",
    "contig_edge_truncation": "high_value",
    "assembly_fragmentation": "high_value",
    "local_read_coverage": "high_value",
    "expected_neighboring_genes": "supporting",
    "divergent_homologues": "high_value",
    "reference_neighbor_presence": "supporting",
    "missing_in_fragmented_region": "supporting",
    # assembly / annotation
    "read_back_mapping": "essential",
    "completeness_estimate": "high_value",
    "contamination_estimate": "high_value",
    "assembly_size_and_fragmentation": "essential",
    "gene_density_check": "essential",
    "truncated_gene_risk": "supporting",
}

# Extra expected validators that are not always named as attack-plan tests.
EXPECTED_BY_CLAIM: dict[ClaimType, list[str]] = {
    ClaimType.target_gene_detected: [
        "low_alignment_coverage", "short_conserved_domain", "abnormal_protein_length",
        "wrong_paralogue", "contamination", "contig_edge_effects", "read_supported_break",
        "orthology_versus_paralogy", "reciprocal_best_hit", "protein_identity_and_coverage",
        "taxonomic_consistency_of_locus", "local_gene_order", "phylogenetic_placement",
        "missing_catalytic_residues", "abnormal_contig_coverage", "gene_orientation",
    ],
    ClaimType.target_gene_not_detected: [
        "nucleotide_homology", "translated_homology", "predicted_protein_homology",
        "partial_domain_hits", "contig_edge_truncation", "assembly_fragmentation",
        "local_read_coverage", "divergent_homologues", "read_supported_break",
        "reference_neighbor_presence", "expected_neighboring_genes",
    ],
    ClaimType.assembly_supported_for_annotation: [
        "read_back_mapping", "completeness_estimate", "contamination_estimate",
        "assembly_size_and_fragmentation",
    ],
    ClaimType.annotation_internally_plausible: [
        "gene_density_check", "truncated_gene_risk",
    ],
}


def importance_for(test_id: str) -> str:
    prefix = test_id.split(":")[0]
    return TEST_IMPORTANCE.get(prefix, "supporting")


def _applicable(test: FalsificationTest) -> bool:
    lim = (test.limitation or "").lower()
    if "not defined" in lim or "not configured" in lim:
        return False
    if "catalytic residues were not provided" in lim or "no expected catalytic" in lim:
        return False
    if lim.startswith("voi policy"):
        return False
    return True


@dataclass
class CompletenessRecord:
    score: float
    completed: list[str]
    unresolved: list[str]
    unavailable: list[str]
    missing_essential: list[str]
    missing_high_value: list[str]
    notes: str
    provenance: dict


def score_evidence_completeness(
    claim_type: ClaimType,
    tests: list[FalsificationTest],
    *,
    tools_unavailable: list[str] | None = None,
) -> CompletenessRecord:
    by_prefix = {t.test_id.split(":")[0]: t for t in tests}
    expected = EXPECTED_BY_CLAIM.get(claim_type, list(by_prefix))
    completed: list[str] = []
    unresolved: list[str] = []
    unavailable: list[str] = []
    weighted_done = 0.0
    weighted_total = 0.0
    missing_essential: list[str] = []
    missing_high_value: list[str] = []
    for prefix in expected:
        test = by_prefix.get(prefix)
        imp = importance_for(prefix)
        w = IMPORTANCE_WEIGHTS[imp]
        if test is None:
            unavailable.append(prefix)
            weighted_total += w
            if imp == "essential":
                missing_essential.append(prefix)
            elif imp == "high_value":
                missing_high_value.append(prefix)
            continue
        if not _applicable(test):
            continue
        weighted_total += w
        if test.status == "completed":
            completed.append(test.test_id)
            weighted_done += w
        elif test.status == "unresolved":
            unresolved.append(test.test_id)
            weighted_done += 0.25 * w
        else:
            unavailable.append(test.test_id)
            if imp == "essential":
                missing_essential.append(prefix)
            elif imp == "high_value":
                missing_high_value.append(prefix)
    score = (weighted_done / weighted_total) if weighted_total else 0.0
    if missing_essential:
        score *= 0.45
    elif missing_high_value:
        score *= max(0.55, 1.0 - 0.08 * len(missing_high_value))
    score = max(0.0, min(1.0, score))
    notes = "LLM did not assign evidence_completeness."
    if tools_unavailable:
        notes += " Unavailable instruments: " + ", ".join(tools_unavailable) + "."
    return CompletenessRecord(
        score=round(score, 4),
        completed=completed,
        unresolved=unresolved,
        unavailable=unavailable,
        missing_essential=missing_essential,
        missing_high_value=missing_high_value,
        notes=notes,
        provenance={
            "created_by": "deterministic_evidence_completeness",
            "weights": IMPORTANCE_WEIGHTS,
            "missing_essential": missing_essential,
            "missing_high_value": missing_high_value,
        },
    )


def apply_completeness_to_confidence(confidence: float, rec: CompletenessRecord) -> float:
    """Lower confidence when high-value evidence is missing. Do not change status.

    Completeness is a separate score. Missing optional instruments must not
    collapse two claims with different homology into the same confidence.
    """
    conf = confidence
    if rec.missing_essential:
        conf *= 0.88
    elif rec.missing_high_value:
        conf *= max(0.90, 1.0 - 0.025 * len(rec.missing_high_value))
    if rec.score < 0.30:
        conf = min(conf, 0.55)
    return max(0.05, min(0.85, round(conf, 4)))


def attach_completeness(claim, *, tools_unavailable: list[str] | None = None, apply_to_confidence: bool = True):
    rec = score_evidence_completeness(claim.claim_type, claim.falsification_tests, tools_unavailable=tools_unavailable)
    claim.evidence_completeness = rec.score
    claim.completed_tests = rec.completed
    claim.unresolved_tests = rec.unresolved
    claim.unavailable_tests = rec.unavailable
    claim.provenance.notes = (claim.provenance.notes or "") + " " + rec.notes
    if apply_to_confidence:
        claim.confidence = apply_completeness_to_confidence(claim.confidence, rec)
    return rec
