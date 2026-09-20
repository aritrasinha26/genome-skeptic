"""Competing hypotheses for a target-gene question. Measurements are never invented.

Relative support is ranking, not a calibrated probability.
"""
from __future__ import annotations

from genome_skeptic.models import HypothesisGraph, HypothesisNode


HYPOTHESIS_IDS = (
    "true_presence",
    "true_absence",
    "divergent_orthologue",
    "paralogue",
    "gene_duplication",
    "annotation_failure",
    "biological_split",
    "fusion",
    "assembly_fragmentation",
    "frameshift_or_pseudogene",
    "contamination",
    "wrong_family",
    "insufficient_data",
)

DISTINGUISHERS = {
    "true_presence": ["family_profile_hmm", "translated_homology", "protein_identity_and_coverage", "competitive_family"],
    "true_absence": ["nucleotide_homology", "translated_homology", "family_profile_hmm", "divergent_homologues"],
    "divergent_orthologue": ["family_profile_hmm", "protein_identity_and_coverage", "divergent_homologues"],
    "paralogue": ["wrong_paralogue", "orthology_versus_paralogy", "reciprocal_best_hit", "locus_multiplicity"],
    "gene_duplication": ["locus_multiplicity", "wrong_paralogue", "inspect_paralogue_copies"],
    "annotation_failure": ["abnormal_protein_length", "fusion_orf", "split_gene"],
    "biological_split": ["split_gene", "family_profile_hmm", "contig_edge_effects"],
    "fusion": ["fusion_orf", "abnormal_protein_length", "family_profile_hmm"],
    "assembly_fragmentation": ["assembly_fragmentation", "contig_edge_truncation", "read_supported_break", "contig_edge_effects"],
    "frameshift_or_pseudogene": ["abnormal_protein_length", "family_profile_hmm"],
    "contamination": ["contamination", "taxonomic_inconsistency", "taxonomic_consistency_of_locus"],
    "wrong_family": ["competitive_family", "family_profile_hmm"],
    "insufficient_data": ["local_read_coverage", "read_supported_break"],
}


def build_hypothesis_graph(
    *,
    target_id: str,
    polarity_detected: bool,
    architecture: str | None,
    family_supports: bool,
    domain_only: bool,
    n_loci: int,
    contig_edge: bool,
    contamination_flag: bool,
    evidence_ids: list[str],
    tests: list | None = None,
    competitive_class: str | None = None,
    multiplicity_class: str | None = None,
    unavailable: list[str] | None = None,
) -> HypothesisGraph:
    scores = {h: 0.05 for h in HYPOTHESIS_IDS}
    support_ids = list(evidence_ids or [])
    contradict: dict[str, list[str]] = {h: [] for h in HYPOTHESIS_IDS}
    missing = list(unavailable or [])

    if family_supports and polarity_detected:
        scores["true_presence"] += 0.45
        scores["true_absence"] = 0.02
        contradict["true_absence"].extend(support_ids[:3])
    elif polarity_detected:
        scores["true_presence"] += 0.25
        scores["true_absence"] += 0.05
    else:
        scores["true_absence"] += 0.35
        scores["true_presence"] += 0.05
        contradict["true_presence"].extend(support_ids[:2])

    if architecture == "fusion":
        scores["fusion"] += 0.40
        scores["true_presence"] += 0.10
        scores["true_absence"] = min(scores["true_absence"], 0.05)
    elif architecture == "biological_split":
        scores["biological_split"] += 0.40
        scores["annotation_failure"] += 0.15
        scores["true_presence"] += 0.10
    elif architecture == "assembly_fragmented":
        scores["assembly_fragmentation"] += 0.40
        scores["insufficient_data"] += 0.15
        scores["true_absence"] = min(scores["true_absence"], 0.15)
    elif architecture == "divergent_full_length":
        scores["divergent_orthologue"] += 0.40
        scores["true_presence"] += 0.15
    elif architecture == "close_paralogue":
        scores["paralogue"] += 0.35
        scores["gene_duplication"] += 0.20
    elif architecture == "domain_only":
        scores["true_absence"] += 0.15
        scores["insufficient_data"] += 0.10
        scores["wrong_family"] += 0.10
        scores["true_presence"] = min(scores["true_presence"], 0.15)
    elif architecture == "frameshift_or_pseudogene":
        scores["frameshift_or_pseudogene"] += 0.40
        scores["annotation_failure"] += 0.15
        scores["true_presence"] += 0.10
    elif architecture == "unresolved_candidate":
        scores["insufficient_data"] += 0.25
        scores["annotation_failure"] += 0.10
    elif architecture == "true_no_candidate":
        scores["true_absence"] += 0.25

    if competitive_class == "competing_family_preferred":
        scores["wrong_family"] += 0.45
        scores["true_presence"] = min(scores["true_presence"], 0.08)
        contradict["true_presence"].append("E_competitive_family")
    elif competitive_class == "ambiguous_family":
        scores["wrong_family"] += 0.25
        scores["insufficient_data"] += 0.15
        scores["true_presence"] = min(scores["true_presence"], 0.20)
    if multiplicity_class in {"true_gene_duplication", "recent_duplication"}:
        scores["gene_duplication"] += 0.30
        scores["paralogue"] += 0.10
    if domain_only:
        scores["true_presence"] = min(scores["true_presence"], 0.12)
    if n_loci >= 2:
        scores["paralogue"] += 0.10
        scores["gene_duplication"] += 0.10
    if contig_edge:
        scores["assembly_fragmentation"] += 0.20
        scores["insufficient_data"] += 0.10
    if contamination_flag:
        scores["contamination"] += 0.35

    total = sum(scores.values()) or 1.0
    nodes = []
    for hid, raw in scores.items():
        rel = raw / total
        if rel >= 0.28:
            state = "supported"
            reason = "this explanation currently outranks alternatives on deterministic evidence"
        elif rel >= 0.12:
            state = "plausible"
            reason = "evidence is compatible but does not uniquely select this explanation"
        else:
            state = "unsupported"
            reason = "little or no current evidence favors this explanation"
        unresolved = []
        if tests:
            for test in tests:
                prefix = test.test_id.split(":")[0]
                if prefix in DISTINGUISHERS.get(hid, []) and test.status != "completed":
                    unresolved.append(test.test_id)
        nodes.append(
            HypothesisNode(
                hypothesis_id=hid,
                supporting_evidence_ids=support_ids if state != "unsupported" else [],
                contradicting_evidence_ids=contradict.get(hid) or [],
                unavailable_evidence=missing,
                remaining_discriminating_tests=unresolved,
                required_unresolved_tests=unresolved,
                posterior_support=None,
                relative_support=round(rel, 4),
                support_state=state,
                reason_for_support_state=reason,
                distinguishing_tests=list(DISTINGUISHERS.get(hid) or []),
            )
        )
    nodes.sort(key=lambda n: n.relative_support, reverse=True)
    leading = nodes[0].hypothesis_id if nodes else None
    runner = nodes[1].hypothesis_id if len(nodes) > 1 else None
    stop = None
    if nodes and nodes[0].relative_support >= 0.40 and (not nodes[1:] or nodes[0].relative_support - nodes[1].relative_support >= 0.12):
        stop = "one explanation is sufficiently supported relative to alternatives"
    return HypothesisGraph(
        target_id=target_id,
        hypotheses=nodes,
        leading=leading,
        runner_up=runner,
        stop_reason=stop,
        provenance={
            "created_by": "deterministic_hypothesis_graph",
            "llm_invented_posteriors": False,
            "calibrated_probabilities": False,
            "relative_support_is_not_a_probability": True,
        },
    )
