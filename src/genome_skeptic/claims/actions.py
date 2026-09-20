"""Map proposed follow-ups onto scientific action classes.

The evaluator scores classes from the hidden case definition. Extra useful
diagnostics are not automatically penalized. Repeated no-op analyses are.
"""
from __future__ import annotations

from genome_skeptic.models import Claim, FalsificationResult

ACTION_CLASS_BY_NAME: dict[str, str] = {
    "inspect_read_supported_breaks": "inspect_paired_end_support",
    "repeat_assembly_after_diagnosing_fragmentation": "try_alternative_assembler",
    "inspect_contig_edges_for_target": "inspect_contig_ends",
    "investigate_coverage_anomalies": "inspect_coverage",
    "inspect_local_coverage_for_target": "inspect_coverage",
    "investigate_contamination": "investigate_contamination",
    "classify_contig_taxonomy": "classify_taxonomy",
    "inspect_paralogue_copies": "inspect_paralogues",
    "place_target_among_homologues": "phylogenetic_placement",
    "compare_locus_to_reference": "compare_synteny",
    "inspect_gene_order_against_reference": "compare_synteny",
    "search_target_genes_translated": "deeper_homology_search",
    "search_target_proteins_mmseqs": "deeper_homology_search",
    "search_target_proteins_diamond": "deeper_homology_search",
    "search_target_domains_hmmer": "deeper_homology_search",
    "repeat_cleaning_with_reviewed_parameters": "repeat_qc",
    "request_long_read_sequencing": "request_long_reads",
    "targeted_pcr_confirmation": "orthogonal_confirmation",
    "remap_reads": "remap_reads",
    "continue_pipeline": "continue",
}

HARMFUL_CLASSES = frozenset({
    "declare_organism_absence",
    "overwrite_hidden_truth",
    "skip_hard_gate",
    "invent_taxonomy",
})


def class_for_action(name: str) -> str:
    return ACTION_CLASS_BY_NAME.get(name, "unclassified")


def classify_actions(
    proposed: list[str],
    *,
    acceptable_classes: list[str],
    harmful_classes: list[str] | None = None,
) -> dict[str, list[str]]:
    useful: list[str] = []
    redundant: list[str] = []
    irrelevant: list[str] = []
    harmful: list[str] = []
    seen: set[str] = set()
    accept = set(acceptable_classes or [])
    harm = set(harmful_classes or []) | HARMFUL_CLASSES
    for raw in proposed:
        cls = class_for_action(raw)
        if cls in harm or raw in harm:
            harmful.append(raw)
            continue
        if cls in accept or raw in accept:
            if cls in seen or raw in seen:
                redundant.append(raw)
            else:
                useful.append(raw)
                seen.add(cls)
                seen.add(raw)
            continue
        if cls == "continue" and not accept:
            useful.append(raw)
            continue
        if cls == "unclassified":
            irrelevant.append(raw)
            continue
        # Extra diagnostic that is not listed: useful if it is a known scientific class
        # other than continue; otherwise irrelevant.
        if cls in ACTION_CLASS_BY_NAME.values() and cls != "continue":
            if cls in seen:
                redundant.append(raw)
            else:
                useful.append(raw)
                seen.add(cls)
        else:
            irrelevant.append(raw)
    return {
        "useful": useful,
        "reasonable_redundant": redundant,
        "irrelevant": irrelevant,
        "potentially_harmful": harmful,
    }


def recommended_followups(claims: list[Claim]) -> list[str]:
    actions: list[str] = []
    for claim in claims:
        ids = {t.test_id.split(":")[0]: t for t in claim.falsification_tests}

        def challenged(name: str) -> bool:
            t = ids.get(name)
            return bool(t and t.result in {FalsificationResult.weakens_claim, FalsificationResult.rejects_claim})

        if challenged("assembly_fragmentation") or challenged("contig_edge_truncation") or challenged("read_supported_break"):
            actions.extend(["inspect_read_supported_breaks", "repeat_assembly_after_diagnosing_fragmentation", "inspect_contig_edges_for_target"])
        if challenged("contamination") or challenged("taxonomic_inconsistency") or challenged("taxonomic_consistency_of_locus"):
            actions.extend(["investigate_contamination", "classify_contig_taxonomy"])
        if challenged("wrong_paralogue") or challenged("orthology_versus_paralogy") or challenged("phylogenetic_placement"):
            actions.extend(["inspect_paralogue_copies", "place_target_among_homologues"])
        if challenged("inconsistent_genomic_neighborhood") or challenged("local_gene_order"):
            actions.append("compare_locus_to_reference")
        if challenged("divergent_homologues"):
            actions.extend(["search_target_genes_translated", "search_target_proteins_mmseqs"])
        if challenged("abnormal_contig_coverage") or challenged("local_read_coverage"):
            actions.append("inspect_local_coverage_for_target")
    return list(dict.fromkeys(actions))
