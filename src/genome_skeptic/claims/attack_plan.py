from __future__ import annotations

from genome_skeptic.models import ClaimType, FalsificationResult, FalsificationTest


DETECTED_ATTACKS: list[tuple[str, str, str, bool]] = [
    ("wrong_paralogue", "wrong paralogue", "The hit is a paralogue rather than the intended gene.", True),
    ("short_conserved_domain", "short conserved-domain match", "The hit is only a short conserved domain, not the full gene.", True),
    ("low_alignment_coverage", "low alignment coverage", "Alignment covers too little of the query to support full-gene detection.", True),
    ("abnormal_protein_length", "abnormal protein length", "Predicted protein length is inconsistent with the target.", True),
    ("missing_catalytic_residues", "missing expected catalytic residues", "Expected catalytic residues are missing or substituted.", False),
    ("contamination", "contamination", "The hit lies on a likely contaminant contig.", False),
    ("abnormal_contig_coverage", "abnormal contig coverage", "Local coverage is inconsistent with a single-copy chromosomal gene.", False),
    ("taxonomic_inconsistency", "taxonomic inconsistency", "Hit taxonomy disagrees with the isolate.", False),
    ("inconsistent_genomic_neighborhood", "inconsistent genomic neighborhood", "Flanking genes disagree with the expected neighborhood.", False),
    ("orthology_versus_paralogy", "orthology versus paralogy", "Reference comparison shows a paralogue rather than an orthologue.", False),
    ("reciprocal_best_hit", "reciprocal best hit", "The candidate is not a reciprocal-best-hit orthologue of the reference gene.", False),
    ("gene_length_conservation", "gene length conservation", "Candidate length is not conserved relative to the reference orthologue.", False),
    ("protein_identity_and_coverage", "protein identity and coverage", "Protein identity or coverage versus the reference orthologue is too weak.", False),
    ("gene_orientation", "gene orientation", "Candidate orientation disagrees with the reference locus.", False),
    ("upstream_downstream_orthologues", "upstream and downstream orthologues", "Expected flanking orthologues are missing or rearranged.", False),
    ("local_gene_order", "local gene order", "Local gene order is inconsistent with the trusted reference locus.", False),
    ("intergenic_spacing", "intergenic spacing", "Intergenic spacing around the candidate is inconsistent with the reference.", False),
    ("contig_edge_effects", "contig-edge effects", "The candidate locus is truncated or distorted by a contig edge.", False),
    ("taxonomic_consistency_of_locus", "taxonomic consistency of the locus", "Measured contig taxonomy is inconsistent with the declared isolate.", False),
    ("read_supported_break", "read-supported contig break", "Paired-end mapping supports a truncated locus at a contig break.", False),
    ("phylogenetic_placement", "phylogenetic placement", "Placement among labeled homologues disagrees with a single-copy orthologue.", False),
    ("family_profile_hmm", "family profile HMM", "The family profile-HMM does not support a full-length orthologue (domain-only hits are not auto-promoted).", True),
    ("fusion_orf", "fusion ORF", "The family region sits inside a longer protein; extra sequence may be another conserved family.", False),
    ("split_gene", "split gene", "Adjacent ORFs jointly cover the family profile, or contig breaks mimic a split.", False),
    ("assembly_fragmentation", "assembly fragmentation", "The candidate is split across contig boundaries rather than a biological split gene.", False),
    ("competitive_family", "competitive family discrimination", "A competing family explains the locus at least as well as the requested family.", True),
    ("locus_multiplicity", "locus multiplicity", "Near-identical copies may be distinct loci rather than one collapsed gene.", False),
]


NOT_DETECTED_ATTACKS: list[tuple[str, str, str, bool]] = [
    ("nucleotide_homology", "nucleotide homology", "A nucleotide homolog is present and would disprove non-detection.", True),
    ("translated_homology", "translated homology", "A translated homolog is present and would disprove non-detection.", True),
    ("predicted_protein_homology", "predicted protein homology", "A predicted protein homolog is present and would disprove non-detection.", False),
    ("partial_domain_hits", "partial-domain hits", "A partial domain hit is present and would disprove clean non-detection.", True),
    ("contig_edge_truncation", "contig-edge truncation", "The gene is truncated at a contig edge rather than missing.", True),
    ("assembly_fragmentation", "assembly fragmentation", "The gene is split across contigs rather than missing.", True),
    ("local_read_coverage", "local read coverage", "Coverage suggests an unassembled, collapsed, or hidden locus.", False),
    ("expected_neighboring_genes", "expected neighboring genes", "Expected neighbors are present in a configuration that could hide or replace the target.", False),
    ("divergent_homologues", "divergent homologues", "A diverged homolog is visible only to protein or domain search.", True),
    ("family_profile_hmm", "family profile HMM", "A family profile-HMM or multi-reference hit is present and would disprove clean non-detection.", True),
    ("competitive_family", "competitive family discrimination", "A competing family match would mean non-detection of the requested family rather than absence of all similar transporters.", False),
    ("locus_multiplicity", "locus multiplicity", "Multiple distinct loci would disprove a single-copy non-detection interpretation.", False),
    ("fusion_orf", "fusion ORF", "A fusion protein covering the family profile is present rather than the gene being absent.", True),
    ("split_gene", "split gene", "Adjacent ORFs jointly cover the family profile rather than the gene being absent.", True),
    ("reference_neighbor_presence", "reference neighbor presence", "Expected neighboring genes from the reference are present, which can localize a missing target.", False),
    ("missing_in_fragmented_region", "missing in fragmented region", "The missing target lies in a region likely affected by assembly fragmentation.", False),
    ("read_supported_break", "read-supported contig break", "Paired-end mapping supports truncation of a missing target at a contig break.", False),
]


ASSEMBLY_ATTACKS: list[tuple[str, str, str, bool]] = [
    ("read_back_mapping", "read-back mapping", "Reads do not support the assembled sequence.", True),
    ("completeness_estimate", "completeness estimate", "Completeness is too low for a usable isolate assembly.", False),
    ("contamination_estimate", "contamination estimate", "Contamination is high enough to undermine isolate interpretation.", False),
    ("assembly_size_and_fragmentation", "assembly size and fragmentation", "Genome size or contig count is implausible for a bacterial isolate.", True),
]


ANNOTATION_ATTACKS: list[tuple[str, str, str, bool]] = [
    ("gene_density_check", "gene-density check", "Predicted coding density is implausible for a bacterial isolate.", True),
    ("truncated_gene_risk", "truncated-gene risk", "Fragmentation may have produced truncated calls that look numerically normal.", False),
]


def generate_attack_plan(claim_type: ClaimType, query_id: str | None = None) -> list[FalsificationTest]:
    if claim_type == ClaimType.target_gene_detected:
        specs = DETECTED_ATTACKS
    elif claim_type == ClaimType.target_gene_not_detected:
        specs = NOT_DETECTED_ATTACKS
    elif claim_type == ClaimType.assembly_supported_for_annotation:
        specs = ASSEMBLY_ATTACKS
    elif claim_type == ClaimType.annotation_internally_plausible:
        specs = ANNOTATION_ATTACKS
    else:
        specs = []
    tests = []
    suffix = f":{query_id}" if query_id else ""
    for test_id, name, hypothesis, blocking in specs:
        tests.append(
            FalsificationTest(
                test_id=f"{test_id}{suffix}",
                name=name,
                hypothesis=hypothesis,
                blocking=blocking,
                status="skipped",
                result=FalsificationResult.not_run,
            )
        )
    return tests


def attack_plan_id(claim_type: ClaimType, query_id: str | None = None) -> str:
    suffix = f"_{query_id}" if query_id else ""
    return f"AP_{claim_type.value}{suffix}"
