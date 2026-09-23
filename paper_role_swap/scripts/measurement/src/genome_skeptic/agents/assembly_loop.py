"""Assembly-level agentic target loop (genome_skeptic_agentic).

Deterministic V5 measurements remain the only source of measured quantities.
The existing AgentDecision / CriticReview schemas and OllamaJSONClient.ask_json
path are reused. The frozen analyze_targets_on_assembly / run_skeptic path is
not modified.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from genome_skeptic.agents.critic import CRITIC_SYSTEM
from genome_skeptic.agents.ollama import OllamaJSONClient
from genome_skeptic.agents.providers import CALL_LOG, reset_call_log
from genome_skeptic.agents.questions import ADVERSARIAL_QUESTIONS
from genome_skeptic.agents.reasoner import REASONER_SYSTEM
from genome_skeptic.claims.hypothesis_graph import HYPOTHESIS_IDS
from genome_skeptic.config import Settings
from genome_skeptic.io_utils import read_fasta
from genome_skeptic.isolation import assert_agent_accessible
from genome_skeptic.locus.orthology import reciprocal_best_hits
from genome_skeptic.locus.pipeline import _preferred_tool_hits
from genome_skeptic.locus.references import load_reference_set
from genome_skeptic.locus.validate import build_locus_evidence
from genome_skeptic.models import (
    AgentDecision,
    Anomaly,
    Claim,
    ClaimProvenance,
    ClaimStatus,
    ClaimType,
    CriticReview,
    Evidence,
    GeneSearchHit,
    LocusEvidence,
    Severity,
    TargetType,
)
from genome_skeptic.orchestrator import REGISTERED_ACTIONS
from genome_skeptic.targets import load_target_profiles
from genome_skeptic.tools.breaks import run_break_analysis
from genome_skeptic.tools.gene_search import (
    extract_orfs,
    is_nucleotide,
    local_coverage_for_hits,
    neighborhood_for_hits,
    parse_gff_features,
    run_gene_search,
    search_proteins,
    translate_frame,
)
from genome_skeptic.tools.hmmer import hmmer_tools_available, run_hmmbuild_and_search
from genome_skeptic.tools.similarity import run_preferred_similarity_search, similarity_tools_available
from genome_skeptic.tools.taxonomy import run_contig_taxonomy, taxonomy_tools_available
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim
from genome_skeptic.validators.gene_target import hits_from_metrics
from genome_skeptic.validators.homology import strong_hit

SYSTEM_NAME = "genome_skeptic_agentic"

ASSEMBLY_TARGET_ACTIONS = [
    "search_target_genes_nucleotide",
    "search_target_genes_translated",
    "inspect_contig_edges_for_target",
    "inspect_local_coverage_for_target",
    "inspect_synteny_neighborhood_for_target",
    "compare_locus_to_reference",
    "reciprocal_best_hit_search",
    "inspect_gene_order_against_reference",
    "search_target_proteins_mmseqs",
    "search_target_proteins_diamond",
    "search_target_domains_hmmer",
    "inspect_paralogue_copies",
    "inspect_catalytic_residues",
    "inspect_hit_contig_contamination",
    "classify_contig_taxonomy",
    "inspect_read_supported_breaks",
    "place_target_among_homologues",
]

_MEASUREMENT_KEYS = (
    "identity",
    "coverage",
    "query_coverage",
    "evalue",
    "score",
    "copy_number",
    "read_depth",
    "tstart",
    "tend",
)

PLANNER_CONSTRAINTS = [
    "Cite only supplied evidence IDs in evidence_ids.",
    "Do not invent measurements: identity, coverage, E-values, HMM scores, coordinates, copy number, gene order, taxonomy, or read depth.",
    "requested_actions MUST be a one-element list. Pick exactly one action from registered_actions.",
    "An empty requested_actions list is invalid.",
    "Even if decision is ask_human or stop, still request one diagnostic registered action that could resolve the uncertainty.",
    "alternative_explanations[0] must be the preferred hypothesis_id from registered_hypothesis_ids.",
    "Further alternative_explanations items are competing hypotheses from that same list.",
    "concerns must state what evidence would falsify the preferred hypothesis.",
    "Do not convert not-detected into organism-level absence.",
]

AGENTIC_REASONER_SYSTEM = (
    REASONER_SYSTEM
    + "\nYou MUST put exactly one registered scientific action in requested_actions. "
    "Never return an empty requested_actions list. "
    "If you would ask a human, still choose the next diagnostic measurement from registered_actions."
)

CRITIC_CONSTRAINTS = [
    "Attack the preferred hypothesis in the proposed decision.",
    "Identify contradictory evidence and cite at least one supplied evidence ID.",
    "Propose a plausible alternative explanation using registered_hypothesis_ids.",
    "Do not invent measurements.",
    "Never assign final scientific truth; the deterministic validator remains the authority.",
]

AGENTIC_CRITIC_SYSTEM = (
    CRITIC_SYSTEM
    + "\nCite at least one supplied evidence ID. Do not invent measurements. "
    "Propose a plausible alternative hypothesis_id. The deterministic validator, not you, assigns the final claim."
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_obj(obj: Any) -> str:
    return _sha256_text(json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")))


def _compact_hit(hit: GeneSearchHit) -> dict[str, Any]:
    return {
        "query_id": hit.query_id,
        "contig_id": hit.contig_id,
        "search_kind": hit.search_kind,
        "identity": hit.identity,
        "query_coverage": hit.query_coverage,
        "evalue": hit.evalue,
        "near_contig_edge": hit.near_contig_edge,
        "possible_edge_truncation": hit.possible_edge_truncation,
        "edge_distance_bp": hit.edge_distance_bp,
        "tstart": hit.tstart,
        "tend": hit.tend,
        "strand": hit.strand,
        "contig_length": hit.contig_length,
        "tool": hit.tool,
        "domain_name": hit.domain_name,
    }


def _compact_family(fam: Any) -> dict[str, Any] | None:
    if fam is None:
        return None
    raw = fam.as_dict() if hasattr(fam, "as_dict") else {}
    hmm = raw.get("best_hmm") or {}
    compact_hmm = None
    if isinstance(hmm, dict):
        compact_hmm = {
            k: hmm.get(k)
            for k in (
                "target_id",
                "query_name",
                "full_evalue",
                "full_score",
                "best_domain_evalue",
                "best_domain_score",
                "n_reported_domains",
            )
            if k in hmm
        }
    metrics = raw.get("metrics") or {}
    compact_metrics = None
    if isinstance(metrics, dict):
        compact_metrics = {
            k: metrics.get(k)
            for k in (
                "n_supporting_members",
                "n_family_members",
                "reference_set_agreement",
                "hmm_model_coverage",
                "hmm_query_coverage",
                "hmm_full_evalue",
                "hmm_full_score",
                "best_member_identity",
                "best_member_coverage",
                "competitive_family_classification",
                "multiplicity_classification",
                "domain_only",
            )
            if k in metrics
        }
    return {
        "family_id": raw.get("family_id"),
        "n_member_hits": raw.get("n_member_hits"),
        "architecture": raw.get("architecture"),
        "hierarchy": raw.get("hierarchy"),
        "supports_orthologue": raw.get("supports_orthologue"),
        "domain_only": raw.get("domain_only"),
        "fusion": {"state": (raw.get("fusion") or {}).get("state"), "supported": (raw.get("fusion") or {}).get("supported")} if raw.get("fusion") else None,
        "split": {"state": (raw.get("split") or {}).get("state"), "supported": (raw.get("split") or {}).get("supported")} if raw.get("split") else None,
        "fragmented": {"state": (raw.get("fragmented") or {}).get("state"), "supported": (raw.get("fragmented") or {}).get("supported")} if raw.get("fragmented") else None,
        "paralogue": raw.get("paralogue"),
        "best_hmm": compact_hmm,
        "metrics": compact_metrics,
        "limitations": raw.get("limitations"),
        "tools_run": raw.get("tools_run"),
        "member_hit_summaries": (raw.get("member_hit_summaries") or [])[:3],
    }


def _write_fa(path: Path, records: list[tuple[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f">{name}\n{seq}\n" for name, seq in records if seq), encoding="utf-8")
    return path


def _query_aa(profile) -> str:
    seq = profile.sequence or ""
    if not seq:
        return ""
    if is_nucleotide(seq):
        return max((translate_frame(seq.upper(), f) for f in range(3)), key=len).split("*")[0]
    return seq.replace("*", "")


@dataclass
class AgenticLoopResult:
    claims: list[Claim]
    loci: list[LocusEvidence]
    evidence: list[Evidence]
    provenance: dict[str, Any]
    call_graph: list[str]
    seconds: float


@dataclass
class _LoopState:
    settings: Settings
    assembly: Path
    targets: Path
    out_dir: Path
    declared_organism: str | None
    mapping_sam: Path | None
    depth_tsv: Path | None
    assembly_gff: Path | None
    proteins_path: Path | None
    references_yaml: Path | None
    evidence: list[Evidence] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    call_graph: list[str] = field(default_factory=list)
    counter: int = 0
    contig_seqs: dict[str, str] = field(default_factory=dict)
    proteins: dict[str, str] = field(default_factory=dict)
    feats: list = field(default_factory=list)
    refs: list = field(default_factory=list)
    coverage_by_hit: dict[str, dict] = field(default_factory=dict)
    break_evidence: dict[str, dict] = field(default_factory=dict)
    contig_taxonomy: dict[str, dict] = field(default_factory=dict)
    tools_run: list[str] = field(default_factory=list)
    tools_unavailable: list[str] = field(default_factory=list)
    depth_evidence_ids: list[str] = field(default_factory=list)
    mapping_available: bool = False
    depth_available: bool = False

    def add_evidence(self, stage: str, kind: str, summary: str, values: dict[str, Any], source_path: str | None = None) -> Evidence:
        self.counter += 1
        ev = Evidence(
            id=f"E{self.counter:03d}",
            stage=stage,
            kind=kind,
            summary=summary,
            values=values,
            source_path=source_path,
        )
        self.evidence.append(ev)
        return ev

    def known_ids(self) -> set[str]:
        return {e.id for e in self.evidence}


def collect_assembly_target_measurements(
    state: _LoopState,
    *,
    query_ids: list[str] | None = None,
) -> tuple[TargetMeasurements, list[LocusEvidence]]:
    """Same deterministic instruments as analyze_targets_on_assembly, without claiming."""
    state.call_graph.append("collect_assembly_target_measurements")
    settings = state.settings
    out_dir = state.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    search = run_gene_search(state.targets, state.assembly, out_dir / "search", settings)
    state.call_graph.append("run_gene_search")
    hits = hits_from_metrics(search.metrics) if search.ok else []
    profiles = load_target_profiles(str(state.targets))
    if query_ids:
        wanted = set(query_ids)
        profiles = [p for p in profiles if p.query_id in wanted]
        hits = [h for h in hits if h.query_id in wanted]
    if not profiles:
        raise ValueError("no target profiles available for agentic assembly loop")
    profile = profiles[0]
    state.contig_seqs = dict(read_fasta(state.assembly))
    state.feats = parse_gff_features(state.assembly_gff) if state.assembly_gff and Path(state.assembly_gff).exists() else []
    state.proteins = dict(read_fasta(state.proteins_path)) if state.proteins_path and Path(state.proteins_path).exists() else {}
    state.refs = load_reference_set(state.references_yaml) if state.references_yaml and Path(state.references_yaml).exists() else []
    state.tools_run = ["internal_gene_search"]
    if state.feats:
        state.tools_run.append("gff_synteny")
    if similarity_tools_available():
        state.tools_run.extend(similarity_tools_available())

    tax_db = settings.paths.taxonomy_db
    if tax_db:
        tax = run_contig_taxonomy(state.assembly, out_dir / "taxonomy", tax_db, settings.project.threads)
        state.call_graph.append("run_contig_taxonomy")
        if tax.ok:
            state.contig_taxonomy = tax.metrics.get("by_contig") or {}
            state.tools_run.append(tax.name)
        else:
            state.tools_unavailable.append("contig_taxonomy")
    else:
        state.tools_unavailable.append("contig_taxonomy")

    state.mapping_available = bool(state.mapping_sam and Path(state.mapping_sam).exists()) and settings.execution.enable_mapping_breaks
    if state.mapping_available:
        loci_spec = [
            {
                "contig": h.contig_id,
                "start": min(h.tstart, h.tend),
                "end": max(h.tstart, h.tend),
                "contig_length": h.contig_length or len(state.contig_seqs.get(h.contig_id, "")),
            }
            for h in hits
            if h.search_kind == "nucleotide"
        ]
        if loci_spec:
            br = run_break_analysis(Path(state.mapping_sam), out_dir / "breaks", loci_spec)
            state.call_graph.append("run_break_analysis")
            state.break_evidence = br.metrics.get("by_locus") or {}
            state.tools_run.append("break_analysis")

    depth_tsv = state.depth_tsv
    if depth_tsv is None and state.mapping_sam:
        cand = Path(state.mapping_sam).with_name("depth.tsv")
        if cand.exists():
            depth_tsv = cand
            state.depth_tsv = cand
    state.depth_available = bool(depth_tsv and Path(depth_tsv).exists())
    if state.depth_available:
        state.coverage_by_hit = local_coverage_for_hits(depth_tsv, hits) if hits else {}
        state.tools_run.append("samtools_depth")
        state.depth_evidence_ids.extend(["E_local_read_depth", "E_relative_locus_coverage", "E_coverage_discontinuity"])
    else:
        state.tools_unavailable.append("local_read_depth")

    if state.declared_organism and not profile.expected_taxonomy:
        profile.expected_taxonomy = state.declared_organism
    q_hits = [h for h in hits if h.query_id == profile.query_id]
    qaa = _query_aa(profile)
    if state.proteins and qaa:
        q_hits.extend(search_proteins(profile.query_id, qaa, list(state.proteins.items()), settings))
        state.call_graph.append("search_proteins")
    neighborhood = neighborhood_for_hits(state.feats, q_hits) if state.feats and q_hits else {}
    tool_hits_by_reference: dict[str, list] = {}
    cand_pairs = [(profile.query_id, qaa)] if qaa else []
    for ref in state.refs:
        ref_prot = list((ref.get("protein_sequences") or {}).items())
        if not ref_prot:
            continue
        tool_hits = _preferred_tool_hits(cand_pairs, ref_prot, out_dir / "orthology" / str(ref.get("id") or "ref"), settings)
        if tool_hits:
            tool_hits_by_reference[str(ref.get("id") or "")] = tool_hits
    loci = build_locus_evidence(
        profile=profile,
        hits=q_hits,
        settings=settings,
        assembly_features=state.feats,
        contig_sequences=state.contig_seqs,
        query_proteins=state.proteins,
        references=state.refs,
        tools_run=state.tools_run,
        tool_hits_by_reference=tool_hits_by_reference,
        break_evidence=state.break_evidence,
        contig_taxonomy=state.contig_taxonomy,
        mapping_available=state.mapping_available,
    )
    state.call_graph.append("build_locus_evidence")
    phy: dict[str, Any] = {}
    for le in loci:
        placed = (le.sequence_similarity or {}).get("placement") or {}
        if placed:
            phy = placed
            break
    measurements = TargetMeasurements(
        query_id=profile.query_id,
        profile=profile,
        hits=q_hits,
        contig_sequences=state.contig_seqs,
        protein_sequences=state.proteins,
        neighborhood_by_hit=neighborhood,
        coverage_by_hit={k: v for k, v in state.coverage_by_hit.items() if k.startswith(f"{profile.query_id}:")},
        annotation_available=bool(state.feats),
        proteins_available=bool(state.proteins),
        locus_evidence=loci,
        tools_run=state.tools_run,
        tools_unavailable=state.tools_unavailable,
        falsification_enabled=settings.execution.enable_falsification,
        break_evidence=state.break_evidence,
        contig_taxonomy=state.contig_taxonomy,
        phylogeny=phy,
        mapping_available=state.mapping_available,
        depth_available=state.depth_available,
        declared_organism=state.declared_organism,
        depth_evidence_ids=state.depth_evidence_ids,
    )
    if profile.target_type != TargetType.exact_allele:
        from genome_skeptic.validators.family_orthology import collect_family_evidence

        try:
            fam_ev = collect_family_evidence(
                profile=profile,
                assembly=state.assembly,
                contig_sequences=state.contig_seqs,
                proteins=state.proteins,
                query_hits=q_hits,
                settings=settings,
                out_dir=out_dir / "family" / profile.query_id,
                locus_evidence=loci,
            )
            state.call_graph.append("collect_family_evidence")
            measurements.family_evidence = fam_ev
            measurements.tools_run = list(dict.fromkeys(list(state.tools_run) + list(fam_ev.tools_run or [])))
            measurements.limitations.extend(fam_ev.limitations or [])
            if "HMMER unavailable" in " ".join(fam_ev.limitations or []):
                measurements.tools_unavailable = list(dict.fromkeys(list(state.tools_unavailable) + ["hmmsearch"]))
        except Exception as exc:
            measurements.limitations.append(f"family orthology failed: {exc}")
    return measurements, loci


def measurements_to_evidence(state: _LoopState, measurements: TargetMeasurements) -> list[str]:
    """Convert V5 measurements into ledger Evidence with real IDs. No sequences."""
    state.call_graph.append("measurements_to_evidence")
    ids: list[str] = []
    hits = measurements.hits or []
    ids.append(
        state.add_evidence(
            "target_gene",
            "measurement",
            f"Homology hits for {measurements.query_id}",
            {
                "n_hits": len(hits),
                "n_strong": sum(1 for h in hits if strong_hit(h, state.settings, measurements.profile.target_type)),
                "hits": [_compact_hit(h) for h in hits[:8]],
                "tools_run": list(measurements.tools_run or []),
                "tools_unavailable": list(measurements.tools_unavailable or []),
            },
        ).id
    )
    fam = _compact_family(measurements.family_evidence)
    if fam is not None:
        ids.append(
            state.add_evidence(
                "target_gene",
                "measurement",
                f"Family orthology measurements for {measurements.query_id}",
                fam,
            ).id
        )
    edge_hits = [h for h in hits if h.near_contig_edge or h.possible_edge_truncation]
    ids.append(
        state.add_evidence(
            "target_gene",
            "measurement",
            f"Contig-edge status for {measurements.query_id}",
            {
                "n_edge_hits": len(edge_hits),
                "hits": [_compact_hit(h) for h in edge_hits[:8]],
            },
        ).id
    )
    if measurements.coverage_by_hit:
        ids.append(
            state.add_evidence(
                "target_gene",
                "measurement",
                f"Local coverage measurements for {measurements.query_id}",
                {"by_hit": measurements.coverage_by_hit},
            ).id
        )
        state.depth_evidence_ids = list(dict.fromkeys(state.depth_evidence_ids + [ids[-1]]))
        measurements.depth_evidence_ids = list(state.depth_evidence_ids)
    if measurements.neighborhood_by_hit:
        compact_nb = {}
        for key, val in list(measurements.neighborhood_by_hit.items())[:4]:
            if isinstance(val, dict):
                compact_nb[key] = {k: val[k] for k in val if k != "sequence"}
            else:
                compact_nb[key] = val
        ids.append(
            state.add_evidence(
                "target_gene",
                "measurement",
                f"Synteny neighborhood for {measurements.query_id}",
                compact_nb,
            ).id
        )
    if measurements.locus_evidence:
        ids.append(
            state.add_evidence(
                "target_gene",
                "measurement",
                f"Locus evidence for {measurements.query_id}",
                {
                    "n_loci": len(measurements.locus_evidence),
                    "conflicts": [c for le in measurements.locus_evidence for c in (le.conflicts or [])][:12],
                    "orthologues": [
                        o.model_dump() if hasattr(o, "model_dump") else o
                        for le in measurements.locus_evidence
                        for o in (le.orthologues or [])
                    ][:8],
                    "placement": measurements.phylogeny,
                },
            ).id
        )
    if measurements.limitations:
        ids.append(
            state.add_evidence(
                "target_gene",
                "limitation",
                "Deterministic measurement limitations",
                {"limitations": list(measurements.limitations)},
            ).id
        )
    for h in edge_hits[:3]:
        state.anomalies.append(
            Anomaly(
                id=f"A{len(state.anomalies) + 1:03d}",
                stage="target_gene",
                severity=Severity.warning,
                message=f"Hit on {h.contig_id} is near a contig edge (distance {h.edge_distance_bp} bp).",
                evidence_ids=[ids[0]],
                possible_explanations=["assembly_fragmentation", "true_presence"],
            )
        )
    return ids


def _planner_payload(measurements: TargetMeasurements, state: _LoopState, unresolved: list[str]) -> dict[str, Any]:
    profile = measurements.profile
    return {
        "stage": "target_gene",
        "target": {
            "query_id": profile.query_id,
            "target_type": getattr(profile.target_type, "value", profile.target_type),
            "family_id": profile.family_id,
        },
        "current_claim_hypotheses": {
            "registered_hypothesis_ids": list(HYPOTHESIS_IDS),
            "status": "unresolved_pending_validator",
            "instruction": (
                "alternative_explanations[0] is the preferred hypothesis_id. "
                "Remaining items are alternatives. concerns state what would falsify the preferred hypothesis."
            ),
        },
        "evidence": [e.model_dump() for e in state.evidence],
        "registered_actions": list(ASSEMBLY_TARGET_ACTIONS),
        "unresolved_questions": unresolved,
        "anomalies": [a.model_dump() for a in state.anomalies],
        "constraints": PLANNER_CONSTRAINTS,
        "output_requirements": {
            "evidence_ids": "non-empty list drawn only from supplied evidence IDs",
            "requested_actions": "exactly one name from registered_actions",
            "alternative_explanations": "first item is the preferred hypothesis_id from registered_hypothesis_ids",
            "concerns": "what evidence would falsify the preferred hypothesis",
        },
    }


def _critic_payload(decision: AgentDecision, state: _LoopState, unresolved: list[str]) -> dict[str, Any]:
    preferred = (decision.alternative_explanations or ["insufficient_data"])[0]
    return {
        "stage": "target_gene",
        "preferred_hypothesis": preferred,
        "proposed_decision": decision.model_dump(),
        "evidence": [e.model_dump() for e in state.evidence],
        "registered_hypothesis_ids": list(HYPOTHESIS_IDS),
        "unresolved_questions": unresolved,
        "anomalies": [a.model_dump() for a in state.anomalies],
        "constraints": CRITIC_CONSTRAINTS,
        "adversarial_questions": ADVERSARIAL_QUESTIONS.get("target_gene", []),
    }


def _recover_planner_fields(decision: AgentDecision, known: set[str], registered: list[str], evidence: list[Evidence] | None = None) -> AgentDecision:
    """Fill empty schema fields only from IDs/actions the model already wrote. Never invent measurements."""
    data = decision.model_dump()
    blob = " ".join(
        [
            data.get("rationale") or "",
            " ".join(data.get("concerns") or []),
            " ".join(data.get("alternative_explanations") or []),
            " ".join(data.get("requested_actions") or []),
        ]
    )
    if not data.get("evidence_ids"):
        mentioned = re.findall(r"\bE\d{3}\b", blob)
        recovered = [eid for eid in mentioned if eid in known]
        if not recovered and evidence:
            for ev in evidence:
                if ev.id not in known:
                    continue
                marker = json.dumps(ev.values, default=str)
                for token in re.findall(r"\d+\.\d+", marker):
                    if token in blob:
                        recovered.append(ev.id)
                        break
        if recovered:
            data["evidence_ids"] = list(dict.fromkeys(recovered))
    if not data.get("requested_actions"):
        mentioned_actions = [name for name in registered if name in blob]
        if mentioned_actions:
            data["requested_actions"] = [mentioned_actions[0]]
    if not data.get("alternative_explanations"):
        mentioned_h = [h for h in HYPOTHESIS_IDS if h in blob]
        if mentioned_h:
            data["alternative_explanations"] = mentioned_h[:3]
    return AgentDecision.model_validate(data)


def _validate_planner(decision: AgentDecision, known: set[str], registered: list[str]) -> tuple[AgentDecision | None, str | None]:
    if not (decision.evidence_ids or []):
        return None, "planner cited no evidence IDs"
    unknown = [eid for eid in (decision.evidence_ids or []) if eid not in known]
    if unknown:
        return None, f"planner cited unknown evidence IDs: {unknown}"
    actions = list(decision.requested_actions or [])
    if not actions:
        return None, "planner requested no registered action"
    invalid = [a for a in actions if a not in registered]
    if invalid:
        return None, f"planner requested unregistered actions: {invalid}"
    offered_miss = [a for a in actions if a not in ASSEMBLY_TARGET_ACTIONS]
    if offered_miss:
        return None, f"planner requested actions not offered for assembly-target analysis: {offered_miss}"
    return decision, None


def _validate_critic(critic: CriticReview, known: set[str]) -> tuple[CriticReview | None, str | None]:
    if not (critic.evidence_ids or []):
        return None, "critic cited no evidence IDs"
    unknown = [eid for eid in (critic.evidence_ids or []) if eid not in known]
    if unknown:
        return None, f"critic cited unknown evidence IDs: {unknown}"
    if critic.verdict not in {"accept", "challenge"}:
        return None, "critic verdict was malformed"
    return critic, None


def execute_registered_action(
    action: str,
    state: _LoopState,
    measurements: TargetMeasurements,
) -> list[str]:
    """Run one registered scientific action with existing deterministic tools."""
    state.call_graph.append(f"execute_registered_action:{action}")
    handlers = {
        "search_target_genes_nucleotide": _act_gene_search,
        "search_target_genes_translated": _act_gene_search,
        "inspect_contig_edges_for_target": _act_inspect_edges,
        "inspect_local_coverage_for_target": _act_inspect_coverage,
        "inspect_synteny_neighborhood_for_target": _act_inspect_synteny,
        "compare_locus_to_reference": _act_compare_reference,
        "reciprocal_best_hit_search": _act_rbh,
        "inspect_gene_order_against_reference": _act_inspect_synteny,
        "search_target_proteins_mmseqs": _act_protein_search,
        "search_target_proteins_diamond": _act_protein_search,
        "search_target_domains_hmmer": _act_hmmer,
        "inspect_paralogue_copies": _act_paralogues,
        "inspect_catalytic_residues": _act_catalytic,
        "inspect_hit_contig_contamination": _act_contamination,
        "classify_contig_taxonomy": _act_taxonomy,
        "inspect_read_supported_breaks": _act_breaks,
        "place_target_among_homologues": _act_placement,
    }
    fn = handlers.get(action)
    if fn is None:
        raise ValueError(f"registered action has no deterministic executor: {action}")
    return fn(state, measurements, action)


def _act_gene_search(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    result = run_gene_search(state.targets, state.assembly, state.out_dir / "action_search", state.settings)
    hits = hits_from_metrics(result.metrics) if result.ok else []
    kind = "translated" if "translated" in action else "nucleotide"
    selected = [h for h in hits if h.search_kind == kind and h.query_id == measurements.query_id]
    if selected:
        existing = {(h.contig_id, h.tstart, h.tend, h.search_kind) for h in measurements.hits}
        for h in selected:
            key = (h.contig_id, h.tstart, h.tend, h.search_kind)
            if key not in existing:
                measurements.hits.append(h)
                existing.add(key)
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Deterministic {kind} gene search for {measurements.query_id}",
        {
            "ok": result.ok,
            "action": action,
            "n_hits": len(selected),
            "hits": [_compact_hit(h) for h in selected[:8]],
            "error": result.error,
        },
        source_path=str(state.out_dir / "action_search"),
    )
    return [ev.id]


def _act_inspect_edges(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    rows = [_compact_hit(h) for h in measurements.hits if h.near_contig_edge or h.possible_edge_truncation]
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Contig-edge inspection for {measurements.query_id}",
        {"action": action, "n_edge_hits": len(rows), "hits": rows[:12]},
    )
    return [ev.id]


def _act_inspect_coverage(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    if not state.depth_available:
        ev = state.add_evidence(
            "target_gene",
            "missing_validator",
            "Local coverage was not measured; depth was unavailable and was not invented",
            {"action": action, "depth_available": False},
        )
        return [ev.id]
    cov = local_coverage_for_hits(state.depth_tsv, measurements.hits) if measurements.hits else {}
    measurements.coverage_by_hit.update(cov)
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Local coverage inspection for {measurements.query_id}",
        {"action": action, "by_hit": cov},
    )
    return [ev.id]


def _act_inspect_synteny(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    if not state.feats:
        ev = state.add_evidence(
            "target_gene",
            "missing_validator",
            "Synteny/gene-order was not measured; no GFF was supplied and gene order was not invented",
            {"action": action, "annotation_available": False},
        )
        return [ev.id]
    nb = neighborhood_for_hits(state.feats, measurements.hits)
    measurements.neighborhood_by_hit.update(nb)
    compact = {k: {kk: vv for kk, vv in (v.items() if isinstance(v, dict) else []) if kk != "sequence"} for k, v in list(nb.items())[:4]}
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Synteny/gene-order inspection for {measurements.query_id}",
        {"action": action, "neighborhood": compact},
    )
    return [ev.id]


def _act_compare_reference(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    if not state.refs:
        ev = state.add_evidence(
            "target_gene",
            "missing_validator",
            "No reference set was configured; locus comparison was not invented",
            {"action": action},
        )
        return [ev.id]
    qaa = _query_aa(measurements.profile)
    rows = []
    for ref in state.refs:
        ref_prot = list((ref.get("protein_sequences") or {}).items())
        if not ref_prot or not qaa:
            continue
        tool_hits = _preferred_tool_hits([(measurements.query_id, qaa)], ref_prot, state.out_dir / "action_ref" / str(ref.get("id") or "ref"), state.settings)
        rows.append({"reference_id": ref.get("id"), "n_hits": len(tool_hits), "hits": [_compact_hit(h) for h in tool_hits[:4]]})
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Reference locus comparison for {measurements.query_id}",
        {"action": action, "references": rows},
    )
    return [ev.id]


def _act_rbh(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    if not state.refs:
        ev = state.add_evidence(
            "target_gene",
            "missing_validator",
            "Reciprocal-best-hit was not measured; no reference proteins were supplied",
            {"action": action},
        )
        return [ev.id]
    qaa = _query_aa(measurements.profile)
    records = []
    for ref in state.refs:
        ref_prot = list((ref.get("protein_sequences") or {}).items())
        if not ref_prot or not qaa:
            continue
        recs = reciprocal_best_hits([(measurements.query_id, qaa)], ref_prot, state.settings)
        records.extend([r.model_dump() for r in recs[:8]])
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Reciprocal-best-hit search for {measurements.query_id}",
        {"action": action, "orthologues": records[:12]},
    )
    return [ev.id]


def _act_protein_search(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    qaa = _query_aa(measurements.profile)
    if not qaa:
        ev = state.add_evidence("target_gene", "missing_validator", "No query protein sequence; protein search was not invented", {"action": action})
        return [ev.id]
    if not similarity_tools_available():
        ev = state.add_evidence("target_gene", "missing_validator", "MMseqs2/DIAMOND unavailable; protein identity was not invented", {"action": action, "tools": similarity_tools_available()})
        return [ev.id]
    if state.proteins:
        targets = list(state.proteins.items())
    else:
        orfs = extract_orfs(list(state.contig_seqs.items()), min_aa=state.settings.thresholds.orf_min_aa, edge_bp=state.settings.thresholds.contig_edge_proximity_bp)
        targets = [(str(o.get("orf_id") or o.get("contig_id") or i), o.get("sequence") or "") for i, o in enumerate(orfs[:5000])]
    if not targets:
        ev = state.add_evidence("target_gene", "missing_validator", "No protein targets available; protein search was not invented", {"action": action})
        return [ev.id]
    qfa = _write_fa(state.out_dir / "action_protein" / "query.faa", [(measurements.query_id, qaa)])
    tfa = _write_fa(state.out_dir / "action_protein" / "targets.faa", [(n, s) for n, s in targets if s])
    result = run_preferred_similarity_search(qfa, tfa, state.out_dir / "action_protein" / "search", state.settings, "protein")
    hits = hits_from_metrics(result.metrics) if result.ok else []
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Deterministic protein search for {measurements.query_id}",
        {"action": action, "ok": result.ok, "n_hits": len(hits), "hits": [_compact_hit(h) for h in hits[:8]], "error": result.error},
    )
    return [ev.id]


def _act_hmmer(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    if not hmmer_tools_available():
        ev = state.add_evidence("target_gene", "missing_validator", "HMMER unavailable; HMM scores were not invented", {"action": action})
        return [ev.id]
    qaa = _query_aa(measurements.profile)
    if not qaa:
        ev = state.add_evidence("target_gene", "missing_validator", "No query amino-acid sequence for HMM search", {"action": action})
        return [ev.id]
    qfa = _write_fa(state.out_dir / "action_hmmer" / "query.faa", [(measurements.query_id, qaa)])
    orfs = extract_orfs(list(state.contig_seqs.items()), min_aa=state.settings.thresholds.orf_min_aa, edge_bp=state.settings.thresholds.contig_edge_proximity_bp)
    seqs = [(str(o.get("orf_id") or i), o.get("sequence") or "") for i, o in enumerate(orfs[:8000])]
    tfa = _write_fa(state.out_dir / "action_hmmer" / "orfs.faa", [(n, s) for n, s in seqs if s])
    result = run_hmmbuild_and_search(qfa, tfa, state.out_dir / "action_hmmer" / "search", state.settings.project.threads)
    hits = (result.metrics or {}).get("sequence_hits") or []
    compact = []
    for row in hits[:8]:
        if isinstance(row, dict):
            compact.append({k: row.get(k) for k in ("target_id", "query_name", "full_evalue", "full_score", "best_domain_evalue", "best_domain_score")})
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Deterministic HMM search for {measurements.query_id}",
        {
            "action": action,
            "ok": result.ok,
            "n_hits": len(hits) if isinstance(hits, list) else 0,
            "hits": compact,
            "limitation": (result.metrics or {}).get("limitation"),
            "error": result.error,
        },
    )
    return [ev.id]


def _act_paralogues(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    fam = measurements.family_evidence
    paralogue = getattr(fam, "paralogue", None) if fam is not None else None
    n_loci = len({(h.contig_id, min(h.tstart, h.tend) // 50) for h in measurements.hits if h.search_kind in {"nucleotide", "translated", "protein"}})
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Paralogue-copy inspection for {measurements.query_id}",
        {"action": action, "paralogue": paralogue, "n_hit_loci": n_loci, "n_hits": len(measurements.hits)},
    )
    return [ev.id]


def _act_catalytic(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    residues = list(getattr(measurements.profile, "catalytic_residues", None) or [])
    if not residues:
        ev = state.add_evidence(
            "target_gene",
            "missing_validator",
            "No catalytic residue pattern was provided; residues were not invented",
            {"action": action},
        )
        return [ev.id]
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Catalytic-residue pattern present on profile {measurements.query_id}",
        {"action": action, "n_residues": len(residues), "note": "inspection uses provided residue pattern only"},
    )
    return [ev.id]


def _act_contamination(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    contig_ids = list(dict.fromkeys(h.contig_id for h in measurements.hits))
    rows = []
    for cid in contig_ids[:12]:
        seq = state.contig_seqs.get(cid, "")
        if not seq:
            continue
        gc = (seq.upper().count("G") + seq.upper().count("C")) / max(len(seq), 1)
        rows.append({"contig_id": cid, "length": len(seq), "gc": round(gc, 4), "taxonomy": state.contig_taxonomy.get(cid)})
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Hit-contig composition/taxonomy inspection for {measurements.query_id}",
        {"action": action, "contigs": rows, "taxonomy_available": bool(state.contig_taxonomy)},
    )
    return [ev.id]


def _act_taxonomy(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    tax_db = state.settings.paths.taxonomy_db
    if not tax_db:
        ev = state.add_evidence(
            "target_gene",
            "missing_validator",
            "No contig taxonomy database was configured; taxonomy was not invented",
            {"action": action, "tools": taxonomy_tools_available()},
        )
        return [ev.id]
    tax = run_contig_taxonomy(state.assembly, state.out_dir / "action_taxonomy", tax_db, state.settings.project.threads)
    by_contig = tax.metrics.get("by_contig") or {} if tax.ok else {}
    state.contig_taxonomy.update(by_contig)
    measurements.contig_taxonomy = dict(state.contig_taxonomy)
    wanted = {h.contig_id: by_contig.get(h.contig_id) for h in measurements.hits}
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Contig taxonomy classification for {measurements.query_id}",
        {"action": action, "ok": tax.ok, "by_hit_contig": wanted, "error": tax.error},
    )
    return [ev.id]


def _act_breaks(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    if not state.mapping_available:
        ev = state.add_evidence(
            "target_gene",
            "missing_validator",
            "Paired-end mapping was unavailable; read-supported breaks were not invented",
            {"action": action},
        )
        return [ev.id]
    loci_spec = [
        {
            "contig": h.contig_id,
            "start": min(h.tstart, h.tend),
            "end": max(h.tstart, h.tend),
            "contig_length": h.contig_length or len(state.contig_seqs.get(h.contig_id, "")),
        }
        for h in measurements.hits
        if h.search_kind == "nucleotide"
    ]
    br = run_break_analysis(Path(state.mapping_sam), state.out_dir / "action_breaks", loci_spec)
    measurements.break_evidence.update(br.metrics.get("by_locus") or {})
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Read-supported break inspection for {measurements.query_id}",
        {"action": action, "ok": br.ok, "by_locus": br.metrics.get("by_locus") or {}, "error": br.error},
    )
    return [ev.id]


def _act_placement(state: _LoopState, measurements: TargetMeasurements, action: str) -> list[str]:
    placed = measurements.phylogeny or {}
    if not placed:
        for le in measurements.locus_evidence or []:
            placed = (le.sequence_similarity or {}).get("placement") or {}
            if placed:
                break
    if not placed:
        ev = state.add_evidence(
            "target_gene",
            "missing_validator",
            "Phylogenetic placement was not available; tree placement was not invented",
            {"action": action},
        )
        return [ev.id]
    ev = state.add_evidence(
        "target_gene",
        "measurement",
        f"Homologue placement for {measurements.query_id}",
        {"action": action, "placement": placed},
    )
    return [ev.id]


def _unresolved_failure(measurements: TargetMeasurements, reason: str, evidence_ids: list[str], notes: str) -> Claim:
    return Claim(
        claim_id=f"C_target_{measurements.query_id}",
        claim_type=ClaimType.target_gene_not_detected,
        statement=(
            f"Agentic analysis of target '{measurements.query_id}' is unresolved because the planner/critic loop failed closed. "
            "No LLM-free scientific success claim is issued."
        ),
        status=ClaimStatus.unresolved,
        confidence=0.0,
        evidence_completeness=0.0,
        rationale=reason,
        supporting_evidence_ids=list(evidence_ids),
        provenance=ClaimProvenance(
            created_by="deterministic_validator",
            stage="target_gene",
            evidence_ledger_ids=list(evidence_ids),
            notes=notes,
        ),
    )


def _call_stats() -> dict[str, Any]:
    planner = [r for r in CALL_LOG if str(r.get("request_type") or "").startswith(("AgentDecision", "PlannerDecision"))]
    critic = [r for r in CALL_LOG if str(r.get("request_type") or "").startswith(("CriticReview", "CriticDecision"))]
    return {
        "model_call_count": len(CALL_LOG),
        "planner_model_call_count": len(planner),
        "critic_model_call_count": len(critic),
        "repair_count": sum(int(r.get("retry_count") or 0) for r in CALL_LOG),
        "call_log": list(CALL_LOG),
    }


def _llm_measurement_entered_claim(claim: Claim, planner: AgentDecision | None, critic: CriticReview | None, evidence: list[Evidence]) -> bool:
    """True only if a numeric measurement appears in LLM text and then in the claim without being in evidence."""
    allowed_nums: set[str] = set()
    blob = json.dumps([e.values for e in evidence], default=str)
    allowed_nums.update(re.findall(r"-?\d+(?:\.\d+)?", blob))
    llm_text = ""
    if planner is not None:
        llm_text += planner.rationale + " " + " ".join(planner.concerns or []) + " " + " ".join(planner.alternative_explanations or [])
    if critic is not None:
        llm_text += critic.rationale + " " + " ".join(critic.failure_modes or [])
    llm_nums = set(re.findall(r"-?\d+(?:\.\d+)?", llm_text))
    invented = {n for n in llm_nums if n not in allowed_nums and n not in {"0", "1"}}
    if not invented:
        return False
    claim_text = " ".join(
        [
            claim.statement,
            claim.rationale,
            " ".join(claim.alternative_explanations or []),
        ]
    )
    return any(num in claim_text for num in invented)


def run_skeptic_agentic(
    assembly: Path,
    targets: Path,
    out_dir: Path,
    settings: Settings,
    *,
    references: Path | None = None,
    gff: Path | None = None,
    proteins: Path | None = None,
    declared_organism: str | None = None,
    mapping_sam: Path | None = None,
    depth_tsv: Path | None = None,
    query_ids: list[str] | None = None,
) -> tuple[list[Claim], list[LocusEvidence], dict[str, Any]]:
    """New development path. Frozen run_skeptic / analyze_targets_on_assembly are untouched."""
    t0 = time.perf_counter()
    assert_agent_accessible(assembly)
    assert_agent_accessible(targets)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reset_call_log()
    state = _LoopState(
        settings=settings,
        assembly=Path(assembly),
        targets=Path(targets),
        out_dir=out_dir,
        declared_organism=declared_organism,
        mapping_sam=Path(mapping_sam) if mapping_sam else None,
        depth_tsv=Path(depth_tsv) if depth_tsv else None,
        assembly_gff=Path(gff) if gff else None,
        proteins_path=Path(proteins) if proteins else None,
        references_yaml=Path(references) if references else None,
    )
    state.call_graph.append("run_skeptic_agentic")
    provenance: dict[str, Any] = {
        "system": SYSTEM_NAME,
        "planner_invoked": False,
        "critic_invoked": False,
        "model_name": settings.llm.model,
        "prompt_hash": None,
        "response_hash": None,
        "critic_prompt_hash": None,
        "critic_response_hash": None,
        "cited_evidence_ids": [],
        "critic_cited_evidence_ids": [],
        "selected_action": None,
        "critic_challenge": None,
        "agent_failure": None,
        "final_validator_ran": False,
    }
    measurements, loci = collect_assembly_target_measurements(state, query_ids=query_ids)
    before_ids = measurements_to_evidence(state, measurements)
    provenance["evidence_ids_before_action"] = list(before_ids)
    unresolved = list(ADVERSARIAL_QUESTIONS.get("target_gene", []))
    llm_ok = bool(settings.llm.enabled and settings.execution.enable_critic and settings.execution.allow_model_to_choose_actions)
    planner: AgentDecision | None = None
    critic: CriticReview | None = None
    action_ids: list[str] = []
    fail_reason: str | None = None

    if not llm_ok:
        fail_reason = "LLM planner/critic is disabled; genome_skeptic_agentic fails closed instead of silent V5 fallback"
    else:
        planner_cfg = settings.llm.for_role("planner")
        critic_cfg = settings.llm.for_role("critic")
        planner_client = OllamaJSONClient(planner_cfg)
        critic_client = OllamaJSONClient(critic_cfg)
        planner_payload = _planner_payload(measurements, state, unresolved)
        provenance["prompt_hash"] = _sha256_obj({"system": AGENTIC_REASONER_SYSTEM, "payload": planner_payload})
        provenance["model_name"] = planner_cfg.model
        try:
            state.call_graph.append("OllamaJSONClient.ask_json:AgentDecision")
            state.call_graph.append("ModelAdapter.ask_json")
            state.call_graph.append("OpenAICompatibleProvider.complete_json")
            provenance["planner_invoked"] = True
            planner = planner_client.ask_json(AGENTIC_REASONER_SYSTEM, planner_payload, AgentDecision)
            first_planner = planner
            planner = _recover_planner_fields(planner, state.known_ids(), REGISTERED_ACTIONS, state.evidence)
            first_recovered = planner
            provenance["response_hash"] = _sha256_text(planner.model_dump_json())
            provenance["cited_evidence_ids"] = list(planner.evidence_ids or [])
            (out_dir / "planner_decision.json").write_text(planner.model_dump_json(indent=2), encoding="utf-8")
            if not (planner.requested_actions or []) or not (planner.evidence_ids or []):
                repair_payload = dict(planner_payload)
                repair_payload["previous_decision"] = first_planner.model_dump()
                repair_payload["repair"] = (
                    "Previous JSON omitted evidence_ids and/or requested_actions. "
                    "Return one JSON object matching the schema with evidence_ids citing only supplied IDs "
                    "and requested_actions containing exactly one action from registered_actions."
                )
                state.call_graph.append("OllamaJSONClient.ask_json:AgentDecision_repair")
                repaired = planner_client.ask_json(AGENTIC_REASONER_SYSTEM, repair_payload, AgentDecision)
                repaired = _recover_planner_fields(repaired, state.known_ids(), REGISTERED_ACTIONS, state.evidence)
                merged = repaired.model_dump()
                if not merged.get("requested_actions") and first_recovered.requested_actions:
                    merged["requested_actions"] = list(first_recovered.requested_actions)
                if not merged.get("evidence_ids") and first_recovered.evidence_ids:
                    merged["evidence_ids"] = list(first_recovered.evidence_ids)
                planner = AgentDecision.model_validate(merged)
                provenance["response_hash"] = _sha256_text(planner.model_dump_json())
                provenance["cited_evidence_ids"] = list(planner.evidence_ids or [])
                (out_dir / "planner_decision.json").write_text(planner.model_dump_json(indent=2), encoding="utf-8")
            validated, err = _validate_planner(planner, state.known_ids(), REGISTERED_ACTIONS)
            if err:
                fail_reason = err
            else:
                planner = validated
                action = (planner.requested_actions or [None])[0]
                provenance["selected_action"] = action
                action_ids = execute_registered_action(action, state, measurements)
                provenance["evidence_ids_after_action"] = [e.id for e in state.evidence]
                critic_payload = _critic_payload(planner, state, unresolved)
                provenance["critic_prompt_hash"] = _sha256_obj({"system": AGENTIC_CRITIC_SYSTEM, "payload": critic_payload})
                try:
                    state.call_graph.append("OllamaJSONClient.ask_json:CriticReview")
                    provenance["critic_invoked"] = True
                    critic = critic_client.ask_json(AGENTIC_CRITIC_SYSTEM, critic_payload, CriticReview)
                    provenance["critic_response_hash"] = _sha256_text(critic.model_dump_json())
                    provenance["critic_cited_evidence_ids"] = list(critic.evidence_ids or [])
                    (out_dir / "critic_review.json").write_text(critic.model_dump_json(indent=2), encoding="utf-8")
                    if not (critic.evidence_ids or []):
                        repair_c = dict(critic_payload)
                        repair_c["repair"] = "Previous JSON omitted evidence_ids. Cite at least one supplied evidence ID."
                        state.call_graph.append("OllamaJSONClient.ask_json:CriticReview_repair")
                        critic = critic_client.ask_json(AGENTIC_CRITIC_SYSTEM, repair_c, CriticReview)
                        provenance["critic_response_hash"] = _sha256_text(critic.model_dump_json())
                        provenance["critic_cited_evidence_ids"] = list(critic.evidence_ids or [])
                        (out_dir / "critic_review.json").write_text(critic.model_dump_json(indent=2), encoding="utf-8")
                    provenance["critic_challenge"] = {
                        "verdict": critic.verdict,
                        "rationale": critic.rationale,
                        "failure_modes": list(critic.failure_modes or []),
                        "disconfirming_tests": list(critic.disconfirming_tests or []),
                    }
                    critic, err = _validate_critic(critic, state.known_ids())
                    if err:
                        fail_reason = err
                except Exception as exc:
                    fail_reason = f"critic call failed: {exc}"
        except Exception as exc:
            fail_reason = f"planner call failed: {exc}"

    stats = _call_stats()
    provenance.update({k: stats[k] for k in ("model_call_count", "planner_model_call_count", "critic_model_call_count", "repair_count")})
    notes = (
        "genome_skeptic_agentic: LLM did not supply identity, coverage, E-values, domain hits, "
        "catalytic residues, orthologues, gene order, or reciprocal hits. "
        f"planner_invoked={provenance['planner_invoked']} critic_invoked={provenance['critic_invoked']} "
        f"model={provenance['model_name']} prompt_hash={provenance['prompt_hash']} "
        f"response_hash={provenance['response_hash']} selected_action={provenance['selected_action']} "
        f"critic_prompt_hash={provenance['critic_prompt_hash']} critic_response_hash={provenance['critic_response_hash']}"
    )

    if fail_reason:
        provenance["agent_failure"] = fail_reason
        claim = _unresolved_failure(measurements, fail_reason, [e.id for e in state.evidence], notes)
        claims = [claim]
    else:
        state.call_graph.append("build_target_gene_claim")
        claim, anoms, _tests = build_target_gene_claim(measurements, settings, [e.id for e in state.evidence])
        provenance["final_validator_ran"] = True
        state.anomalies.extend(anoms)
        preferred = (planner.alternative_explanations or [None])[0] if planner else None
        extras = [h for h in (planner.alternative_explanations or []) if h in HYPOTHESIS_IDS]
        if extras:
            claim.alternative_explanations = list(dict.fromkeys(list(claim.alternative_explanations or []) + extras))
        if critic and critic.verdict == "challenge":
            claim.rationale = (
                claim.rationale
                + " Critic verdict=challenge was recorded in agentic provenance; the deterministic validator remains the authority."
            )
        claim.provenance.notes = (claim.provenance.notes or "") + " " + notes
        claim.provenance.evidence_ledger_ids = list(dict.fromkeys(list(claim.provenance.evidence_ledger_ids or []) + [e.id for e in state.evidence]))
        claims = [claim]
        provenance["preferred_hypothesis"] = preferred

    provenance["llm_measurement_entered_claim"] = _llm_measurement_entered_claim(claims[0], planner, critic, state.evidence)
    provenance["final_claim_state"] = {
        "claim_id": claims[0].claim_id,
        "claim_type": claims[0].claim_type.value,
        "status": claims[0].status.value,
        "confidence": claims[0].confidence,
        "homology_support": claims[0].homology_support,
        "architecture_state": claims[0].architecture_state,
        "supporting_evidence_ids": list(claims[0].supporting_evidence_ids),
        "alternative_explanations": list(claims[0].alternative_explanations or []),
    }
    provenance["call_graph"] = list(state.call_graph)
    provenance["evidence_ids"] = [e.id for e in state.evidence]
    provenance["seconds"] = round(time.perf_counter() - t0, 3)
    (out_dir / "claims.json").write_text(json.dumps([c.model_dump(mode="json") for c in claims], indent=2), encoding="utf-8")
    (out_dir / "locus_evidence.json").write_text(json.dumps([le.model_dump() for le in loci], indent=2), encoding="utf-8")
    (out_dir / "evidence.json").write_text(json.dumps([e.model_dump() for e in state.evidence], indent=2), encoding="utf-8")
    (out_dir / "agentic_provenance.json").write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")
    (out_dir / "call_log.json").write_text(json.dumps(stats["call_log"], indent=2, default=str), encoding="utf-8")
    if planner is not None:
        (out_dir / "planner_decision.json").write_text(planner.model_dump_json(indent=2), encoding="utf-8")
    if critic is not None:
        (out_dir / "critic_review.json").write_text(critic.model_dump_json(indent=2), encoding="utf-8")
    return claims, loci, provenance
