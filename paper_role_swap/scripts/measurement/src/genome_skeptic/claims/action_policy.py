"""Value-of-information policy over registered diagnostic actions.

The orchestrator may propose tests. This layer rejects tests that cannot
discriminate the leading hypotheses and prefers the cheapest remaining
informative test. The LLM does not invent measurements.
"""
from __future__ import annotations

from genome_skeptic.models import DiagnosticAction, FalsificationTest, HypothesisGraph


CATALOG: list[DiagnosticAction] = [
    DiagnosticAction(action_id="nucleotide_homology", required_inputs=["assembly", "targets"], cost_class="cheap", evidence_produced=["E_nt_hit"], supports_hypotheses=["true_presence"], rejects_hypotheses=["true_absence"], informative_when="presence vs absence is open"),
    DiagnosticAction(action_id="translated_homology", required_inputs=["assembly", "targets"], cost_class="cheap", evidence_produced=["E_aa_hit"], supports_hypotheses=["true_presence", "divergent_orthologue"], rejects_hypotheses=["true_absence"], informative_when="nucleotide search is weak"),
    DiagnosticAction(action_id="family_profile_hmm", required_inputs=["assembly", "family_hmm"], cost_class="cheap", evidence_produced=["E_family_hmm"], supports_hypotheses=["true_presence", "divergent_orthologue", "fusion", "biological_split"], rejects_hypotheses=["true_absence"], informative_when="pairwise identity is weak or architecture is open"),
    DiagnosticAction(action_id="fusion_orf", required_inputs=["locus_reconstruction", "partner_family"], cost_class="cheap", evidence_produced=["E_fusion"], supports_hypotheses=["fusion", "annotation_failure"], rejects_hypotheses=["true_absence"], informative_when="locus is longer than the family or partner evidence exists"),
    DiagnosticAction(action_id="split_gene", required_inputs=["locus_reconstruction"], cost_class="cheap", evidence_produced=["E_split"], supports_hypotheses=["biological_split", "annotation_failure"], rejects_hypotheses=["assembly_fragmentation"], informative_when="multiple same-contig segments cover the family"),
    DiagnosticAction(action_id="assembly_fragmentation", required_inputs=["assembly", "mapping"], cost_class="cheap", evidence_produced=["E_fragment"], supports_hypotheses=["assembly_fragmentation", "insufficient_data"], rejects_hypotheses=["biological_split"], informative_when="coverage is incomplete or a contig edge is involved"),
    DiagnosticAction(action_id="contig_edge_effects", required_inputs=["assembly"], cost_class="cheap", evidence_produced=["E_edge"], supports_hypotheses=["assembly_fragmentation"], rejects_hypotheses=[], informative_when="candidate is near a contig boundary"),
    DiagnosticAction(action_id="contig_edge_truncation", required_inputs=["assembly"], cost_class="cheap", evidence_produced=["E_edge"], supports_hypotheses=["assembly_fragmentation"], rejects_hypotheses=["true_absence"], informative_when="non-detection with edge-proximal hits"),
    DiagnosticAction(action_id="read_supported_break", required_inputs=["mapping_sam"], cost_class="moderate", evidence_produced=["E_break"], supports_hypotheses=["assembly_fragmentation", "insufficient_data"], rejects_hypotheses=["true_absence"], informative_when="fragmentation vs missing gene is open and mapping exists"),
    DiagnosticAction(action_id="wrong_paralogue", required_inputs=["hits"], cost_class="cheap", evidence_produced=["E_loci"], supports_hypotheses=["paralogue"], rejects_hypotheses=["true_presence"], informative_when="multiple loci exist"),
    DiagnosticAction(action_id="orthology_versus_paralogy", required_inputs=["references"], cost_class="moderate", evidence_produced=["E_orthology"], supports_hypotheses=["paralogue", "true_presence"], rejects_hypotheses=[], informative_when="paralogy vs orthology is open"),
    DiagnosticAction(action_id="reciprocal_best_hit", required_inputs=["references"], cost_class="moderate", evidence_produced=["E_rbh"], supports_hypotheses=["true_presence"], rejects_hypotheses=["paralogue"], informative_when="family identity is ambiguous"),
    DiagnosticAction(action_id="phylogenetic_placement", required_inputs=["homolog_alignment", "fasttree"], cost_class="expensive", evidence_produced=["E_phylo"], supports_hypotheses=["paralogue", "divergent_orthologue", "true_presence"], rejects_hypotheses=[], informative_when="cheaper evidence leaves paralogy or family identity ambiguous"),
    DiagnosticAction(action_id="local_read_coverage", required_inputs=["depth_tsv"], cost_class="cheap", evidence_produced=["E_depth"], supports_hypotheses=["insufficient_data", "assembly_fragmentation"], rejects_hypotheses=[], informative_when="depth file exists and coverage is untested"),
    DiagnosticAction(action_id="contamination", required_inputs=["taxonomy_db"], cost_class="moderate", evidence_produced=["E_tax"], supports_hypotheses=["contamination"], rejects_hypotheses=["true_presence"], informative_when="taxonomy disagrees or contamination metrics exist"),
    DiagnosticAction(action_id="taxonomic_inconsistency", required_inputs=["taxonomy"], cost_class="moderate", evidence_produced=["E_tax"], supports_hypotheses=["contamination"], rejects_hypotheses=[], informative_when="declared organism and contig taxonomy may disagree"),
    DiagnosticAction(action_id="divergent_homologues", required_inputs=["family_hmm"], cost_class="cheap", evidence_produced=["E_divergent"], supports_hypotheses=["divergent_orthologue"], rejects_hypotheses=["true_absence"], informative_when="nucleotide search is negative"),
    DiagnosticAction(action_id="abnormal_protein_length", required_inputs=["locus_reconstruction"], cost_class="cheap", evidence_produced=["E_length"], supports_hypotheses=["fusion", "annotation_failure"], rejects_hypotheses=[], informative_when="length is off relative to the family"),
    DiagnosticAction(action_id="local_gene_order", required_inputs=["gff", "references"], cost_class="moderate", evidence_produced=["E_synteny"], supports_hypotheses=["true_presence", "annotation_failure"], rejects_hypotheses=[], informative_when="architecture is canonical and synteny is still untested"),
    DiagnosticAction(action_id="competitive_family", required_inputs=["family_hmm", "competing_families"], expected_output="CompetitiveFamilyEvidence", cost_class="cheap", approximate_cost="one hmmsearch per competing family", evidence_produced=["E_competitive_family"], supports_hypotheses=["wrong_family", "true_presence"], rejects_hypotheses=["true_presence"], informative_when="the requested family passed a positive gate"),
    DiagnosticAction(action_id="locus_multiplicity", required_inputs=["hits", "assembly"], expected_output="LocusMultiplicityEvidence", cost_class="cheap", approximate_cost="coordinate clustering of existing hits", evidence_produced=["E_multiplicity"], supports_hypotheses=["gene_duplication", "paralogue"], rejects_hypotheses=["assembly_fragmentation"], informative_when="more than one family-supported interval exists"),
    DiagnosticAction(action_id="short_conserved_domain", required_inputs=["hits"], cost_class="cheap", evidence_produced=["E_domain"], supports_hypotheses=["true_absence"], rejects_hypotheses=["true_presence"], informative_when="coverage is partial"),
    DiagnosticAction(action_id="low_alignment_coverage", required_inputs=["hits"], cost_class="cheap", evidence_produced=["E_coverage"], supports_hypotheses=["assembly_fragmentation", "domain_only"], rejects_hypotheses=[], informative_when="coverage is untested"),
]


COST_RANK = {"cheap": 0, "moderate": 1, "expensive": 2}
_BY_ID = {a.action_id: a for a in CATALOG}
for _a in CATALOG:
    if not _a.expected_output:
        _a.expected_output = f"deterministic {_a.action_id} evidence"
    if not _a.approximate_cost:
        _a.approximate_cost = _a.cost_class
    if not _a.required_inputs:
        _a.required_inputs = ["assembly"]


def catalog_as_dicts() -> list[dict]:
    return [a.model_dump() for a in CATALOG]


def _open_hypotheses(graph: HypothesisGraph) -> set[str]:
    open_ids = set()
    for node in graph.hypotheses:
        if node.support_state in {"supported", "plausible"}:
            open_ids.add(node.hypothesis_id)
    if graph.leading:
        open_ids.add(graph.leading)
    if graph.runner_up:
        open_ids.add(graph.runner_up)
    return open_ids


def action_is_informative(action_id: str, graph: HypothesisGraph) -> tuple[bool, str]:
    spec = _BY_ID.get(action_id.split(":")[0])
    if spec is None:
        return False, "action is not in the diagnostic catalog"
    open_ids = _open_hypotheses(graph)
    touches = set(spec.supports_hypotheses) | set(spec.rejects_hypotheses)
    if not (touches & open_ids):
        return False, f"cannot discriminate leading hypotheses {sorted(open_ids)}"
    if spec.action_id == "phylogenetic_placement":
        cheap_ok = graph.leading in {"true_presence", "true_absence", "fusion", "biological_split"} and graph.runner_up not in {"paralogue", "divergent_orthologue"}
        if cheap_ok:
            return False, "cheaper family/architecture evidence already ranks the leading hypothesis; phylogeny is reserved for paralogy/family ambiguity"
    return True, spec.informative_when


def filter_tests(tests: list[FalsificationTest], graph: HypothesisGraph) -> tuple[list[FalsificationTest], list[dict]]:
    """Keep cheapest informative tests. Record why each test was selected or rejected."""
    decisions = []
    keep: list[FalsificationTest] = []
    ranked = sorted(tests, key=lambda t: COST_RANK.get((_BY_ID.get(t.test_id.split(":")[0]) or DiagnosticAction(action_id=t.test_id)).cost_class, 1))
    essential = {
        "nucleotide_homology", "translated_homology", "short_conserved_domain",
        "low_alignment_coverage", "family_profile_hmm", "protein_identity_and_coverage",
        "assembly_fragmentation", "contig_edge_truncation",
    }
    for test in ranked:
        prefix = test.test_id.split(":")[0]
        if prefix in essential:
            keep.append(test)
            decisions.append({"test_id": test.test_id, "selected": True, "reason": "essential homology/architecture discriminator", "cost_class": (_BY_ID.get(prefix).cost_class if prefix in _BY_ID else "cheap")})
            continue
        ok, reason = action_is_informative(prefix, graph)
        if ok:
            keep.append(test)
            decisions.append({"test_id": test.test_id, "selected": True, "reason": reason, "cost_class": _BY_ID[prefix].cost_class})
        else:
            test.status = "skipped"
            test.limitation = f"VOI policy: {reason}"
            test.blocking = False
            decisions.append({"test_id": test.test_id, "selected": False, "reason": reason, "cost_class": (_BY_ID[prefix].cost_class if prefix in _BY_ID else "moderate")})
    if graph.stop_reason:
        for test in keep:
            prefix = test.test_id.split(":")[0]
            if prefix not in essential and (_BY_ID.get(prefix).cost_class if prefix in _BY_ID else "moderate") == "expensive":
                test.status = "skipped"
                test.limitation = f"VOI policy: {graph.stop_reason}"
                test.blocking = False
    return keep, decisions
