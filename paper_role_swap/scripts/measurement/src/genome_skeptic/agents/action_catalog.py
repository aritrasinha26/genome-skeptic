"""Capability metadata for the registered agentic diagnostic actions (V2).

Agentic V1 handed the planner a bare list of action names. The planner could
therefore spend a full reasoning turn selecting an action that cannot change any
measurement relevant to the open question -- contig-edge inspection was chosen in
all six V1 gate cases even where fragmentation was not the live alternative.

Each action here declares which competing explanations it can discriminate,
which inputs it needs, and which ``TargetMeasurements`` fields it can update.
Availability is computed from the run's actual inputs, so the planner is told up
front that, for example, coverage inspection is inert without a depth file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genome_skeptic.claims.hypothesis_graph import HYPOTHESIS_IDS


@dataclass(frozen=True)
class AgenticActionSpec:
    action_id: str
    resolves: str
    discriminates: tuple[str, ...]
    requires: tuple[str, ...]
    updates_measurement_fields: tuple[str, ...]
    cost_class: str
    informative_when: str
    inert_when: str = ""
    repeats_baseline_work: str = ""

    def as_payload(
        self,
        capabilities: dict[str, bool],
        performed: frozenset[str] = frozenset(),
        measurements: Any = None,
        *,
        edge_bp: int = 300,
    ) -> dict[str, Any]:
        missing = self.missing_inputs(capabilities)
        inert_because = self.inert_because(performed, measurements, edge_bp=edge_bp)
        return {
            "action_id": self.action_id,
            "resolves": self.resolves,
            "discriminates_between": list(self.discriminates),
            "updates_measurement_fields": list(self.updates_measurement_fields),
            "requires_inputs": list(self.requires),
            "cost_class": self.cost_class,
            "informative_when": self.informative_when,
            "inert_when": self.inert_when,
            "available": not missing,
            "unavailable_because_missing": missing,
            "inert_now": bool(inert_because),
            "inert_now_because": inert_because,
            "can_change_a_measurement_now": (not missing) and not inert_because,
        }

    def missing_inputs(self, capabilities: dict[str, bool]) -> list[str]:
        return [req for req in self.requires if not capabilities.get(req, False)]

    def is_available(self, capabilities: dict[str, bool]) -> bool:
        return not self.missing_inputs(capabilities)

    def inert_because(
        self,
        performed: frozenset[str] = frozenset(),
        measurements: Any = None,
        *,
        edge_bp: int = 300,
    ) -> str:
        """Why this action cannot move the measured state, or '' if it still can.

        Decided without asking the model, and without running the action:
        no updatable field, a repeat of baseline work already in ``performed``,
        or a result already represented in the current ``TargetMeasurements``.
        """
        if not self.updates_measurement_fields:
            return self.inert_when or "this action updates no measurement field, so it cannot change the measured state"
        if self.repeats_baseline_work and self.repeats_baseline_work in performed:
            return self.inert_when or f"the initial measurements already performed {self.repeats_baseline_work}"
        return already_represented(self.action_id, measurements, edge_bp=edge_bp)

    def is_inert(
        self,
        performed: frozenset[str] = frozenset(),
        measurements: Any = None,
        *,
        edge_bp: int = 300,
    ) -> bool:
        return bool(self.inert_because(performed, measurements, edge_bp=edge_bp))

    def can_change_state_now(
        self,
        capabilities: dict[str, bool],
        performed: frozenset[str] = frozenset(),
        measurements: Any = None,
        *,
        edge_bp: int = 300,
    ) -> bool:
        return self.is_available(capabilities) and not self.is_inert(performed, measurements, edge_bp=edge_bp)


_SEARCH_ALREADY_ON_HITS = {
    "search_target_proteins_mmseqs": frozenset({"mmseqs"}),
    "search_target_proteins_diamond": frozenset({"diamond"}),
    "search_target_domains_hmmer": frozenset({"hmmer", "hmmsearch", "hmmbuild_hmmsearch", "hmmer_nominated_alignment"}),
}


def _recompute_edge_flags(contig_len: int, lo: int, hi: int, query_coverage: float, edge_bp: int) -> dict[str, Any]:
    edge_distance = min(max(lo, 0), max(contig_len - hi, 0))
    near = edge_distance <= edge_bp
    return {
        "near_contig_edge": bool(near),
        "possible_edge_truncation": bool(near and query_coverage < 0.95),
        "edge_distance_bp": int(edge_distance),
    }


def _hit_contig_length(measurements: Any, hit: Any) -> int:
    seqs = getattr(measurements, "contig_sequences", None) or {}
    seq = seqs.get(getattr(hit, "contig_id", None))
    if seq:
        return len(seq)
    return int(getattr(hit, "contig_length", 0) or 0)


def already_represented(action_id: str, measurements: Any = None, *, edge_bp: int = 300) -> str:
    """If the action's result is already in ``measurements``, say why; else ''."""
    if measurements is None:
        return ""
    hits = list(getattr(measurements, "hits", None) or [])
    if action_id == "inspect_contig_edges_for_target":
        if not hits:
            return "there is no placed hit whose contig edge could still be measured"
        for hit in hits:
            contig_len = _hit_contig_length(measurements, hit)
            if contig_len <= 0:
                return ""
            lo, hi = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
            expected = _recompute_edge_flags(contig_len, lo, hi, hit.query_coverage, edge_bp)
            stored = {
                "near_contig_edge": bool(hit.near_contig_edge),
                "possible_edge_truncation": bool(hit.possible_edge_truncation),
                "edge_distance_bp": int(hit.edge_distance_bp),
            }
            if stored != expected:
                return ""
        return "edge flags already present on the hits agree with the contig lengths"
    if action_id == "inspect_hit_contig_contamination":
        if not hits:
            return "there is no hit contig whose composition could still be measured"
        gc = getattr(measurements, "contig_gc", None) or {}
        missing = [hit.contig_id for hit in hits if hit.contig_id not in gc]
        if missing or getattr(measurements, "genome_gc", None) is None:
            return ""
        return "composition has already been measured for every hit contig"
    tools_done = _SEARCH_ALREADY_ON_HITS.get(action_id)
    if tools_done and any(getattr(hit, "tool", "") in tools_done for hit in hits):
        return f"{action_id} already contributed a hit in the current measurements"
    cov = getattr(measurements, "coverage_by_hit", None) or {}
    if action_id == "inspect_local_coverage_for_target" and hits and cov:
        if all(any(hit.contig_id in key for key in cov) for hit in hits):
            return "every hit interval already has a depth measurement"
    nb = getattr(measurements, "neighborhood_by_hit", None) or {}
    if action_id in {"inspect_synteny_neighborhood_for_target", "inspect_gene_order_against_reference"} and hits and nb:
        if all(any(hit.contig_id in key for key in nb) for hit in hits):
            return "gene-order around the current hits has already been measured"
    tax = getattr(measurements, "contig_taxonomy", None) or {}
    if action_id == "classify_contig_taxonomy" and hits and tax:
        if all(hit.contig_id in tax for hit in hits):
            return "taxonomy has already been assigned for every hit contig"
    if action_id == "inspect_read_supported_breaks" and getattr(measurements, "break_evidence", None):
        return "read-supported break evidence is already present"
    if action_id == "place_target_among_homologues" and getattr(measurements, "phylogeny", None):
        return "a phylogenetic placement is already present"
    return ""


CATALOG: tuple[AgenticActionSpec, ...] = (
    AgenticActionSpec(
        action_id="search_target_genes_nucleotide",
        resolves="whether any nucleotide-level homolog of the target exists in this assembly",
        discriminates=("true_presence", "true_absence"),
        requires=("assembly", "targets"),
        updates_measurement_fields=("hits",),
        cost_class="cheap",
        informative_when="the initial search was not run, or new contigs/targets have since been introduced",
        inert_when="the initial measurements already ran the same nucleotide search over the same assembly",
        repeats_baseline_work="nucleotide_gene_search",
    ),
    AgenticActionSpec(
        action_id="search_target_genes_translated",
        resolves="whether a protein-level homolog exists where nucleotide identity has decayed",
        discriminates=("true_presence", "true_absence", "divergent_orthologue"),
        requires=("assembly", "targets"),
        updates_measurement_fields=("hits",),
        cost_class="cheap",
        informative_when="nucleotide search is weak or negative and divergence is a live alternative",
        inert_when="the initial measurements already ran the same translated search over the same assembly",
        repeats_baseline_work="translated_gene_search",
    ),
    AgenticActionSpec(
        action_id="inspect_contig_edges_for_target",
        resolves="whether a candidate locus is truncated by a contig boundary",
        discriminates=("assembly_fragmentation", "true_absence", "biological_split"),
        requires=("assembly", "hits"),
        updates_measurement_fields=("hit_edge_flags",),
        cost_class="cheap",
        informative_when="hits exist whose stored edge flags have not been checked against real contig lengths",
        inert_when="edge flags already present on the hits agree with the contig lengths, in which case this repeats known values",
    ),
    AgenticActionSpec(
        action_id="inspect_local_coverage_for_target",
        resolves="whether the candidate locus is supported by read depth comparable to the genome mean",
        discriminates=("insufficient_data", "assembly_fragmentation", "contamination"),
        requires=("depth_tsv", "hits"),
        updates_measurement_fields=("coverage_by_hit",),
        cost_class="cheap",
        informative_when="a real depth table exists and some hit interval has no depth measurement yet",
        inert_when="no depth file was supplied, in which case depth cannot be measured and must not be assumed",
    ),
    AgenticActionSpec(
        action_id="inspect_synteny_neighborhood_for_target",
        resolves="which annotated genes flank the candidate locus",
        discriminates=("true_presence", "paralogue", "annotation_failure"),
        requires=("gff", "hits"),
        updates_measurement_fields=("neighborhood_by_hit",),
        cost_class="cheap",
        informative_when="an annotation file exists and some hit has no neighborhood measurement yet",
        inert_when="no GFF was supplied, in which case gene order cannot be measured",
    ),
    AgenticActionSpec(
        action_id="compare_locus_to_reference",
        resolves="how the candidate locus compares to curated reference loci",
        discriminates=("divergent_orthologue", "true_presence", "wrong_family"),
        requires=("references", "query_protein"),
        updates_measurement_fields=("locus_evidence", "phylogeny"),
        cost_class="moderate",
        informative_when="a reference set exists and the hit set has changed since locus evidence was last built",
        inert_when="no reference set was configured",
    ),
    AgenticActionSpec(
        action_id="reciprocal_best_hit_search",
        resolves="whether the candidate is the orthologue of the target or a paralogue of it",
        discriminates=("paralogue", "true_presence", "gene_duplication", "wrong_family"),
        requires=("references", "query_protein"),
        updates_measurement_fields=("orthologues", "locus_evidence"),
        cost_class="moderate",
        informative_when="orthologue-versus-paralogue is the open question and reference proteins are available",
        inert_when="no reference proteins were supplied, so reciprocity cannot be tested",
    ),
    AgenticActionSpec(
        action_id="inspect_gene_order_against_reference",
        resolves="whether local gene order matches the reference arrangement",
        discriminates=("true_presence", "paralogue", "annotation_failure", "contamination"),
        requires=("gff", "hits"),
        updates_measurement_fields=("neighborhood_by_hit",),
        cost_class="moderate",
        informative_when="annotation exists and synteny has not yet been measured for the current hits",
        inert_when="no GFF was supplied",
    ),
    AgenticActionSpec(
        action_id="search_target_proteins_mmseqs",
        resolves="whether a diverged protein-coding homolog exists in six-frame ORFs that nucleotide search missed",
        discriminates=("true_presence", "true_absence", "divergent_orthologue", "frameshift_or_pseudogene"),
        requires=("query_protein", "similarity_tools"),
        updates_measurement_fields=("hits", "tools_run"),
        cost_class="moderate",
        informative_when="nucleotide identity is low or partial and no protein search has been run over assembly ORFs",
        inert_when="MMseqs2/DIAMOND are not installed, so protein identity cannot be measured",
    ),
    AgenticActionSpec(
        action_id="search_target_proteins_diamond",
        resolves="whether a diverged protein-coding homolog exists in six-frame ORFs that nucleotide search missed",
        discriminates=("true_presence", "true_absence", "divergent_orthologue", "frameshift_or_pseudogene"),
        requires=("query_protein", "similarity_tools"),
        updates_measurement_fields=("hits", "tools_run"),
        cost_class="moderate",
        informative_when="nucleotide identity is low or partial and no protein search has been run over assembly ORFs",
        inert_when="MMseqs2/DIAMOND are not installed, so protein identity cannot be measured",
    ),
    AgenticActionSpec(
        action_id="search_target_domains_hmmer",
        resolves="whether a profile model of the query detects ORFs that pairwise search missed, and how well they align",
        discriminates=("divergent_orthologue", "wrong_family", "true_presence", "true_absence"),
        requires=("hmmer", "query_protein"),
        updates_measurement_fields=("hits", "tools_run"),
        cost_class="moderate",
        informative_when="pairwise identity is weak and family membership or deep divergence is the open question",
        inert_when="HMMER is not installed, so profile scores cannot be measured",
    ),
    AgenticActionSpec(
        action_id="competitive_family",
        resolves="whether a competing family explains the candidate at least as well as the requested family",
        discriminates=("wrong_family", "true_presence"),
        requires=("hits", "query_protein", "competing_families"),
        updates_measurement_fields=("family_evidence",),
        cost_class="cheap",
        informative_when="declared competing families have not yet been scored against the candidate protein",
        inert_when="competitive-family scores are already present in family_evidence and would only be repeated",
    ),
    AgenticActionSpec(
        action_id="inspect_paralogue_copies",
        resolves="how many distinct genomic loci carry a candidate copy",
        discriminates=("paralogue", "gene_duplication", "true_presence"),
        requires=("hits",),
        updates_measurement_fields=(),
        cost_class="cheap",
        informative_when="never on its own: it only re-reads hits",
        inert_when="the final validator already clusters hits into loci itself, so clustering them again adds no measurement",
    ),
    AgenticActionSpec(
        action_id="inspect_catalytic_residues",
        resolves="whether the candidate retains the catalytic residues declared on the target profile",
        discriminates=("frameshift_or_pseudogene", "annotation_failure", "wrong_family", "true_presence"),
        requires=("catalytic_residues", "hits"),
        updates_measurement_fields=(),
        cost_class="cheap",
        informative_when="never on its own: residue-level alignment is not yet implemented as a measurement",
        inert_when="it currently only reports the residue pattern declared on the profile, without testing the candidate",
    ),
    AgenticActionSpec(
        action_id="inspect_hit_contig_contamination",
        resolves="whether the hit contig's composition is consistent with the declared organism",
        discriminates=("contamination", "true_presence"),
        requires=("assembly", "hits"),
        updates_measurement_fields=("contig_gc", "genome_gc"),
        cost_class="cheap",
        informative_when="contig and genome GC have not been measured yet, so the contamination test cannot run at all",
        inert_when="composition has already been measured for every hit contig",
    ),
    AgenticActionSpec(
        action_id="classify_contig_taxonomy",
        resolves="the taxonomic assignment of the contig carrying the candidate",
        discriminates=("contamination", "true_presence"),
        requires=("taxonomy_db", "hits"),
        updates_measurement_fields=("contig_taxonomy",),
        cost_class="expensive",
        informative_when="a taxonomy database is configured and the hit contig is unclassified",
        inert_when="no taxonomy database was configured, so taxonomy cannot be measured",
    ),
    AgenticActionSpec(
        action_id="inspect_read_supported_breaks",
        resolves="whether reads support an assembly break at the candidate locus",
        discriminates=("assembly_fragmentation", "biological_split", "insufficient_data", "true_absence"),
        requires=("mapping_sam", "hits"),
        updates_measurement_fields=("break_evidence",),
        cost_class="moderate",
        informative_when="fragmentation versus a genuine split or absence is open and paired-end mapping exists",
        inert_when="no mapping was supplied, so read support cannot be measured",
    ),
    AgenticActionSpec(
        action_id="place_target_among_homologues",
        resolves="where the candidate falls relative to known homologues",
        discriminates=("paralogue", "divergent_orthologue", "wrong_family"),
        requires=("phylogenetic_placement",),
        updates_measurement_fields=("phylogeny",),
        cost_class="expensive",
        informative_when="cheaper family and reciprocity evidence has left paralogy or family identity ambiguous",
        inert_when="no placement was produced by the deterministic locus validators",
    ),
)

BY_ID: dict[str, AgenticActionSpec] = {spec.action_id: spec for spec in CATALOG}

ACTION_IDS: tuple[str, ...] = tuple(spec.action_id for spec in CATALOG)

_UNKNOWN_HYPOTHESES = {h for spec in CATALOG for h in spec.discriminates} - set(HYPOTHESIS_IDS)
if _UNKNOWN_HYPOTHESES:  # pragma: no cover - guards catalog edits
    raise ValueError(f"action catalog references unregistered hypotheses: {sorted(_UNKNOWN_HYPOTHESES)}")


def catalog_payload(
    capabilities: dict[str, bool],
    performed: frozenset[str] = frozenset(),
    measurements: Any = None,
    *,
    edge_bp: int = 300,
) -> list[dict[str, Any]]:
    """Full action metadata for provenance/audit. Do not send this blob to the LLM."""
    return [spec.as_payload(capabilities, performed, measurements, edge_bp=edge_bp) for spec in CATALOG]


def executable_action_payload(
    capabilities: dict[str, bool],
    performed: frozenset[str] = frozenset(),
    measurements: Any = None,
    *,
    edge_bp: int = 300,
) -> list[dict[str, Any]]:
    """Compact specs for actions that can actually run and change a measurement now.

    Unavailable, inert, and already-represented actions are omitted rather than
    annotated. The model should never spend tokens on a redundant experiment.
    """
    return [
        {
            "action_id": spec.action_id,
            "tests": spec.resolves,
            "discriminates_between": list(spec.discriminates),
            "cost_class": spec.cost_class,
        }
        for spec in _cheapest_first(CATALOG)
        if spec.can_change_state_now(capabilities, performed, measurements, edge_bp=edge_bp)
    ]


def available_action_ids(capabilities: dict[str, bool]) -> list[str]:
    """Actions whose declared inputs exist in this run, inert or not."""
    return [spec.action_id for spec in CATALOG if spec.is_available(capabilities)]


def state_changing_action_ids(
    capabilities: dict[str, bool],
    performed: frozenset[str] = frozenset(),
    measurements: Any = None,
    *,
    edge_bp: int = 300,
) -> list[str]:
    """Actions that could still move the measured state, cheapest first."""
    return [
        spec.action_id
        for spec in _cheapest_first(CATALOG)
        if spec.can_change_state_now(capabilities, performed, measurements, edge_bp=edge_bp)
    ]


def _cheapest_first(specs: tuple[AgenticActionSpec, ...] | list[AgenticActionSpec]) -> list[AgenticActionSpec]:
    rank = {"cheap": 0, "moderate": 1, "expensive": 2}
    return sorted(specs, key=lambda s: rank.get(s.cost_class, 1))


def actions_discriminating(
    hypothesis_ids: set[str],
    capabilities: dict[str, bool],
    performed: frozenset[str] = frozenset(),
    measurements: Any = None,
    *,
    edge_bp: int = 300,
) -> list[AgenticActionSpec]:
    """Actions that can still change a measurement bearing on the given explanations.

    Inert and already-represented actions are excluded rather than merely annotated:
    selecting one costs a reasoning turn and yields NO_NEW_INFORMATION by construction.
    Ordered cheapest first so the critic's follow-up stays proportionate.
    """
    matched = [
        spec
        for spec in CATALOG
        if spec.can_change_state_now(capabilities, performed, measurements, edge_bp=edge_bp)
        and (set(spec.discriminates) & hypothesis_ids)
    ]
    return _cheapest_first(matched)
