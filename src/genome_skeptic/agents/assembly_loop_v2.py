"""Assembly-level agentic target loop, version 2 (genome_skeptic_agentic_v2).

Agentic V1 (``assembly_loop.py``) is frozen and is not modified here. V1's
deterministic measurement collection is reused unchanged; only the orchestration
and the action layer are new.

The defect V2 addresses is causal, not rhetorical. In V1 a registered action
wrote into the evidence ledger but almost never into ``TargetMeasurements``, so
``build_target_gene_claim`` received the same ``m0`` that deterministic V5 would
have received. V1 was therefore structurally biased towards reproducing V5 no
matter what the planner reasoned.

V2 enforces this path::

    m0 (deterministic)
      -> evidence E001..E00k
      -> planner
      -> registered action (or an explicit control decision)
      -> deterministic tool
      -> validated measurement patch
      -> m0 becomes m1, with an evidence record describing the update
      -> critic
      -> at most one further action if the critic names a concrete alternative
      -> m1 becomes m2
      -> build_target_gene_claim(m2)

Patch values are produced only by deterministic instruments. The planner and
critic choose *which* measurement to make; they never supply a measured value
and they never set the claim.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from genome_skeptic.agents.action_catalog import (
    ACTION_IDS,
    BY_ID,
    actions_discriminating,
    available_action_ids,
    catalog_payload,
    state_changing_action_ids,
)
from genome_skeptic.agents.action_contract import (
    ABSTAIN_UNRESOLVED,
    CONTROL_DECISION_SEMANTICS,
    CONTROL_DECISIONS,
    FINALIZE_WITH_CURRENT_EVIDENCE,
    V1_DECISION_TO_CONTROL,
    V1_DECISION_VERBS,
    ActionResult,
    ActionStatus,
    MeasurementPatch,
    apply_action_result,
    failed,
    hit_key,
    measurement_fingerprint,
    unavailable,
)
from genome_skeptic.agents.assembly_loop import (
    _compact_hit,
    _call_stats,
    _llm_measurement_entered_claim,
    _LoopState,
    _query_aa,
    _sha256_obj,
    _sha256_text,
    _write_fa,
    collect_assembly_target_measurements,
    measurements_to_evidence,
)
from genome_skeptic.agents.genome_workspace import get_workspace, orf_fasta_path
from genome_skeptic.agents.ollama import OllamaJSONClient
from genome_skeptic.agents.planner_views import build_critic_view, build_planner_view, estimated_tokens
from genome_skeptic.agents.providers import reset_call_log
from genome_skeptic.agents.questions import ADVERSARIAL_QUESTIONS
from genome_skeptic.claims.hypothesis_graph import HYPOTHESIS_IDS
from genome_skeptic.config import Settings
from genome_skeptic.isolation import assert_agent_accessible
from genome_skeptic.locus.orthology import reciprocal_best_hits
from genome_skeptic.locus.pipeline import _preferred_tool_hits
from genome_skeptic.locus.validate import build_locus_evidence
from genome_skeptic.models import (
    AgentDecision,
    Claim,
    ClaimProvenance,
    ClaimStatus,
    ClaimType,
    CriticDecision,
    CriticReview,
    Evidence,
    GeneSearchHit,
    LocusEvidence,
    PlannerDecision,
)
from genome_skeptic.tools.breaks import run_break_analysis
from genome_skeptic.tools.gene_search import (
    local_coverage_for_hits,
    neighborhood_for_hits,
    run_gene_search,
    search_proteins,
)
from genome_skeptic.tools.hmmer import hmmer_tools_available, run_hmmbuild_and_search
from genome_skeptic.tools.similarity import run_preferred_similarity_search, similarity_tools_available
from genome_skeptic.tools.taxonomy import run_contig_taxonomy, taxonomy_tools_available
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim
from genome_skeptic.validators.gene_target import hits_from_metrics

SYSTEM_NAME = "genome_skeptic_agentic_v2"

REGISTERED_CHOICES: tuple[str, ...] = tuple(ACTION_IDS) + CONTROL_DECISIONS

PLANNER_CONSTRAINTS = [
    "evidence_ids must contain only strings copied verbatim from valid_evidence_ids, for example 'E001'. Input names, measurement field names such as 'hits', and action names are not evidence IDs.",
    "Do not invent measurements: identity, coverage, E-values, HMM scores, coordinates, copy number, gene order, taxonomy, or read depth. You choose which measurement to make; the deterministic tool produces the value.",
    "requested_actions MUST be a one-element list drawn from available_actions or control.",
    "available_actions already lists every action whose inputs exist and whose result is not "
    "already in the measurements. Choose from that list. Use 'discriminates_between' to pick the one that bears on the "
    "currently open explanations.",
    "Do not choose an action outside that list. It either lacks its inputs and will return UNAVAILABLE, or it repeats a "
    "measurement already taken and will return NO_NEW_INFORMATION.",
    f"Choose '{ABSTAIN_UNRESOLVED}' only when available_actions is empty. Then it is a "
    "legitimate scientific outcome, not a failure. While that list is non-empty, abstaining discards a measurement "
    "that is still available.",
    "ask_human, stop, continue, and rerun are V1 decision verbs, not requested_actions and not control_decisions. "
    f"If you would have chosen ask_human or stop, put '{ABSTAIN_UNRESOLVED}' in requested_actions instead.",
    f"If the current measurements already discriminate the alternatives, choose '{FINALIZE_WITH_CURRENT_EVIDENCE}'.",
    "alternative_explanations[0] must be the preferred hypothesis_id from registered_hypothesis_ids.",
    "Further alternative_explanations items are competing hypotheses from that same list.",
    "concerns must state what evidence would falsify the preferred hypothesis.",
    "Do not convert not-detected into organism-level absence.",
]

AGENTIC_REASONER_SYSTEM = (
    "You choose the next measurement for a bacterial genome target-gene question. "
    "Do not invent measurements. The deterministic validator assigns the final claim. "
    "Return one concise decision. At most one alternative hypothesis. At most one requested action. "
    "Rationale <= 160 characters. Do not restate evidence values. "
    "decision is investigate, finalize, or abstain. "
    "requested_action is one available_actions id, "
    f"'{FINALIZE_WITH_CURRENT_EVIDENCE}', '{ABSTAIN_UNRESOLVED}', or null. "
    f"Use '{ABSTAIN_UNRESOLVED}' only when available_actions is empty."
)

CRITIC_CONSTRAINTS = [
    "Attack the preferred hypothesis in the proposed decision.",
    "Cite at least one evidence ID copied verbatim from valid_evidence_ids, for example 'E001'.",
    "Do not invent measurements. The deterministic validator assigns the final claim.",
    "If you challenge, set requested_action to one action_id from available_actions and failure_mode to one hypothesis_id.",
    "Rationale is one sentence. Do not write lists of tests or failure modes.",
]

AGENTIC_CRITIC_SYSTEM = (
    "You are an adversarial scientific reviewer of a bacterial genome analysis. "
    "Do not invent measurements. The deterministic validator assigns the final claim. "
    "Return one JSON object with verdict (accept or challenge), evidence_ids (from valid_evidence_ids), "
    "requested_action (one available_actions id if challenge, else null), "
    "failure_mode (one registered_hypothesis_ids id if challenge, else null), "
    "and rationale (one sentence)."
)


# --------------------------------------------------------------------------
# run context
# --------------------------------------------------------------------------


@dataclass
class _V2Run:
    """Per-run context: the frozen V1 loop state plus V2-only caches."""

    state: _LoopState
    capabilities: dict[str, bool] = field(default_factory=dict)
    baseline_work: frozenset[str] = frozenset()
    _orfs: list[dict] | None = None

    def orfs(self) -> list[dict]:
        if self._orfs is None:
            t = self.state.settings.thresholds
            ws = get_workspace(
                self.state.contig_seqs,
                min_aa=t.orf_min_aa,
                edge_bp=t.contig_edge_proximity_bp,
            )
            self._orfs = ws.orfs
        return self._orfs

    def orf_fasta(self, dest: Path) -> Path:
        t = self.state.settings.thresholds
        ws = get_workspace(
            self.state.contig_seqs,
            min_aa=t.orf_min_aa,
            edge_bp=t.contig_edge_proximity_bp,
        )
        return orf_fasta_path(ws, dest)


# collect_assembly_target_measurements runs a single run_gene_search whose metrics
# carry both nucleotide and translated hits, so m0 already contains the result of
# both search actions over this assembly. Re-running either can only reproduce m0.
BASELINE_WORK: frozenset[str] = frozenset({"nucleotide_gene_search", "translated_gene_search"})


def capabilities_for(run_state: _LoopState, m: TargetMeasurements) -> dict[str, bool]:
    """Which inputs this run actually has, so inert actions can be declared up front."""
    placement_available = bool(m.phylogeny) or any(
        (le.sequence_similarity or {}).get("placement") for le in (m.locus_evidence or [])
    )
    competing = False
    try:
        from genome_skeptic.families import families_sharing_class
        from genome_skeptic.validators.family_orthology import resolve_family_for_profile

        family = resolve_family_for_profile(
            m.profile,
            Path(run_state.settings.paths.family_dir) if run_state.settings.paths.family_dir else None,
        )
        if family is not None:
            ids = list(family.competing_families or []) + families_sharing_class(family)
            competing = any(cid != family.family_id for cid in ids)
    except Exception:
        competing = bool(getattr(m.profile, "family_id", None))
    return {
        "assembly": True,
        "targets": True,
        "hits": bool(m.hits),
        "query_protein": bool(_query_aa(m.profile)),
        "protein_fasta": bool(run_state.proteins),
        "depth_tsv": bool(run_state.depth_available),
        "gff": bool(run_state.feats),
        "references": bool(run_state.refs),
        "mapping_sam": bool(run_state.mapping_available),
        "taxonomy_db": bool(run_state.settings.paths.taxonomy_db),
        "hmmer": bool(hmmer_tools_available()),
        "similarity_tools": bool(similarity_tools_available()),
        "catalytic_residues": bool(getattr(m.profile, "catalytic_residues", None)),
        "phylogenetic_placement": placement_available,
        "competing_families": competing,
    }


# --------------------------------------------------------------------------
# deterministic executors -- each returns an ActionResult and mutates nothing
# --------------------------------------------------------------------------


def _edge_flags(contig_len: int, lo: int, hi: int, query_coverage: float, edge_bp: int) -> dict[str, Any]:
    edge_distance = min(max(lo, 0), max(contig_len - hi, 0))
    near = edge_distance <= edge_bp
    return {
        "near_contig_edge": near,
        "possible_edge_truncation": bool(near and query_coverage < 0.95),
        "edge_distance_bp": edge_distance,
    }


def _remap_orf_hit(
    hit: GeneSearchHit,
    orf: dict,
    contig_len: int,
    edge_bp: int,
    tool: str,
) -> GeneSearchHit | None:
    """Place an ORF-space alignment back on the contig.

    ``hit.tstart``/``hit.tend`` are amino-acid offsets into the ORF translation,
    so the genomic offset is three nucleotides per residue from the ORF's 5' end.
    Identity and coverage are carried over unchanged from the alignment; nothing
    here is estimated.
    """
    if orf["strand"] == "+":
        gstart = orf["start"] + 3 * hit.tstart
        gend = orf["start"] + 3 * hit.tend
    else:
        gstart = orf["end"] - 3 * hit.tend
        gend = orf["end"] - 3 * hit.tstart
    lo = max(0, min(gstart, gend))
    hi = min(contig_len, max(gstart, gend))
    if hi <= lo:
        return None
    return GeneSearchHit(
        query_id=hit.query_id,
        contig_id=orf["contig_id"],
        search_kind="translated",
        qstart=hit.qstart,
        qend=hit.qend,
        tstart=lo,
        tend=hi,
        strand=orf["strand"],
        identity=hit.identity,
        query_coverage=hit.query_coverage,
        alignment_length=hit.alignment_length * 3,
        query_length=hit.query_length,
        contig_length=contig_len,
        evalue=hit.evalue,
        tool=tool,
        orf_id=orf.get("orf_id"),
        **_edge_flags(contig_len, lo, hi, hit.query_coverage, edge_bp),
    )


def _act_gene_search(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    state = run.state
    kind = "translated" if "translated" in action else "nucleotide"
    result = run_gene_search(state.targets, state.assembly, state.out_dir / "action_search", state.settings)
    if not result.ok:
        return failed(action, result.error or "gene search did not complete", {"kind": kind})
    hits = hits_from_metrics(result.metrics)
    selected = [h for h in hits if h.search_kind == kind and h.query_id == m.query_id]
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Deterministic {kind} gene search for {m.query_id}",
        observations={"kind": kind, "n_hits": len(selected), "hits": [_compact_hit(h) for h in selected[:8]]},
        patches=[MeasurementPatch(field="hits", value=selected, origin="internal_gene_search", note=f"{kind} search over the assembly")],
    )


def _act_inspect_edges(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    edge_bp = run.state.settings.thresholds.contig_edge_proximity_bp
    revisions: dict[tuple, dict[str, Any]] = {}
    stored: list[dict[str, Any]] = []
    for h in m.hits:
        seq = run.state.contig_seqs.get(h.contig_id)
        if not seq:
            continue
        lo, hi = min(h.tstart, h.tend), max(h.tstart, h.tend)
        revisions[hit_key(h)] = _edge_flags(len(seq), lo, hi, h.query_coverage, edge_bp)
        stored.append(
            {
                "contig_id": h.contig_id,
                "contig_length": len(seq),
                "near_contig_edge": h.near_contig_edge,
                "edge_distance_bp": h.edge_distance_bp,
            }
        )
    if not revisions:
        return unavailable(
            action,
            "no hit lies on a contig of this assembly, so contig edges cannot be measured",
            {"n_hits": len(m.hits)},
        )
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Contig-edge recomputation for {m.query_id}",
        observations={"n_inspected": len(revisions), "edge_proximity_bp": edge_bp, "stored_flags": stored[:12]},
        patches=[
            MeasurementPatch(
                field="hit_edge_flags",
                value=revisions,
                origin="contig_edge_recomputation",
                note="edge distance recomputed from measured contig lengths",
            )
        ],
    )


def _act_inspect_coverage(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    if not run.state.depth_available:
        return unavailable(
            action,
            "no read-depth table was supplied; local coverage cannot be measured and was not assumed",
            {"depth_available": False},
        )
    if not m.hits:
        return unavailable(action, "there is no candidate interval to measure depth over", {"n_hits": 0})
    cov = local_coverage_for_hits(run.state.depth_tsv, m.hits)
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Local read-depth measurement for {m.query_id}",
        observations={"n_intervals": len(cov)},
        patches=[MeasurementPatch(field="coverage_by_hit", value=cov, origin="samtools_depth", note="depth over current hit intervals")],
    )


def _act_inspect_synteny(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    if not run.state.feats:
        return unavailable(
            action,
            "no annotation (GFF) was supplied; gene order cannot be measured and was not invented",
            {"annotation_available": False},
        )
    if not m.hits:
        return unavailable(action, "there is no candidate locus whose neighborhood could be read", {"n_hits": 0})
    nb = neighborhood_for_hits(run.state.feats, m.hits)
    compact = {
        k: {kk: vv for kk, vv in (v.items() if isinstance(v, dict) else []) if kk != "sequence"}
        for k, v in list(nb.items())[:4]
    }
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Synteny/gene-order measurement for {m.query_id}",
        observations={"n_intervals": len(nb), "neighborhood": compact},
        patches=[
            MeasurementPatch(
                field="neighborhood_by_hit",
                value=nb,
                origin="gff_synteny",
                note="annotated features overlapping and flanking the current hits",
            )
        ],
    )


def _rebuild_locus_evidence(
    run: _V2Run,
    m: TargetMeasurements,
    tool_hits_by_reference: dict[str, list],
) -> list[LocusEvidence]:
    state = run.state
    return build_locus_evidence(
        profile=m.profile,
        hits=m.hits,
        settings=state.settings,
        assembly_features=state.feats,
        contig_sequences=state.contig_seqs,
        query_proteins=state.proteins,
        references=state.refs,
        tools_run=m.tools_run,
        tool_hits_by_reference=tool_hits_by_reference,
        break_evidence=m.break_evidence,
        contig_taxonomy=m.contig_taxonomy,
        mapping_available=m.mapping_available,
    )


def _act_compare_reference(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    state = run.state
    if not state.refs:
        return unavailable(action, "no reference set was configured; locus comparison cannot be measured", {})
    qaa = _query_aa(m.profile)
    if not qaa:
        return unavailable(action, "the target profile yields no protein sequence to compare against references", {})
    rows: list[dict[str, Any]] = []
    tool_hits_by_reference: dict[str, list] = {}
    for ref in state.refs:
        ref_prot = list((ref.get("protein_sequences") or {}).items())
        if not ref_prot:
            continue
        ref_id = str(ref.get("id") or "ref")
        tool_hits = _preferred_tool_hits([(m.query_id, qaa)], ref_prot, state.out_dir / "action_ref" / ref_id, state.settings)
        if tool_hits:
            tool_hits_by_reference[ref_id] = tool_hits
        rows.append({"reference_id": ref_id, "n_hits": len(tool_hits), "hits": [_compact_hit(h) for h in tool_hits[:4]]})
    rebuilt = _rebuild_locus_evidence(run, m, tool_hits_by_reference)
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Reference locus comparison for {m.query_id}",
        observations={"references": rows},
        patches=[
            MeasurementPatch(
                field="locus_evidence",
                value=rebuilt,
                origin="locus_evidence_rebuild",
                note="locus evidence rebuilt against reference proteins using the current hit set",
            )
        ],
    )


def _act_rbh(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    state = run.state
    if not state.refs:
        return unavailable(action, "no reference proteins were supplied; reciprocity cannot be measured", {})
    qaa = _query_aa(m.profile)
    if not qaa:
        return unavailable(action, "the target profile yields no protein sequence for a reciprocal search", {})
    records = []
    for ref in state.refs:
        ref_prot = list((ref.get("protein_sequences") or {}).items())
        if not ref_prot:
            continue
        records.extend(reciprocal_best_hits([(m.query_id, qaa)], ref_prot, state.settings)[:8])
    if not records:
        return ActionResult(
            action_id=action,
            status=ActionStatus.no_new_information,
            summary=f"Reciprocal-best-hit search for {m.query_id} returned no reciprocal pair",
            observations={"n_records": 0},
            status_reason="the reciprocal search completed but produced no orthologue record to record",
        )
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Reciprocal-best-hit search for {m.query_id}",
        observations={
            "n_records": len(records),
            "orthologues": [r.model_dump() for r in records[:8]],
            "n_reciprocal": sum(1 for r in records if r.reciprocal_best_hit),
        },
        patches=[
            MeasurementPatch(
                field="orthologues",
                value=records,
                origin="reciprocal_best_hits",
                note="reciprocal best hits against the configured reference proteins",
            )
        ],
    )


def _orf_protein_hits(run: _V2Run, m: TargetMeasurements, action: str, tool_label: str) -> tuple[list[GeneSearchHit], dict[str, Any]]:
    """Search the query protein against six-frame ORFs and return contig-placed hits."""
    state = run.state
    qaa = _query_aa(m.profile)
    orfs = run.orfs()
    by_id = {o["orf_id"]: o for o in orfs}
    edge_bp = state.settings.thresholds.contig_edge_proximity_bp
    records = [(o["orf_id"], o["sequence"]) for o in orfs if o.get("sequence")]
    if not records:
        return [], {"n_orfs": 0}
    raw: list[GeneSearchHit] = []
    tool_used = "internal_gene_search"
    if similarity_tools_available():
        qfa = _write_fa(state.out_dir / action / "query.faa", [(m.query_id, qaa)])
        tfa = run.orf_fasta(state.out_dir / "_genome" / "orfs.faa")
        result = run_preferred_similarity_search(qfa, tfa, state.out_dir / action / "search", state.settings, "protein")
        if result.ok:
            raw = hits_from_metrics(result.metrics)
            tool_used = tool_label
    if not raw:
        raw = search_proteins(m.query_id, qaa, records, state.settings)
    placed: list[GeneSearchHit] = []
    for hit in raw:
        orf = by_id.get(hit.contig_id)
        if orf is None:
            continue
        contig_len = len(state.contig_seqs.get(orf["contig_id"], "")) or orf.get("contig_length") or 0
        if not contig_len:
            continue
        remapped = _remap_orf_hit(hit, orf, contig_len, edge_bp, tool_used)
        if remapped is not None:
            placed.append(remapped)
    placed.sort(key=lambda h: (h.query_coverage * h.identity, h.alignment_length), reverse=True)
    return placed[: state.settings.thresholds.gene_max_hits_per_query], {
        "n_orfs": len(records),
        "tool": tool_used,
        "n_alignments": len(raw),
    }


def _act_protein_search(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    if not _query_aa(m.profile):
        return unavailable(action, "the target profile yields no protein sequence to search with", {})
    tool_label = "diamond" if "diamond" in action else "mmseqs"
    try:
        placed, obs = _orf_protein_hits(run, m, action, tool_label)
    except Exception as exc:  # deterministic tool failure must not crash the loop
        return failed(action, str(exc))
    if not obs.get("n_orfs"):
        return unavailable(action, "no ORF of sufficient length was extracted from the assembly", obs)
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Protein similarity search over assembly ORFs for {m.query_id}",
        observations={**obs, "n_placed_hits": len(placed), "hits": [_compact_hit(h) for h in placed[:8]]},
        patches=[
            MeasurementPatch(field="hits", value=placed, origin="orf_protein_similarity_search", note="ORF alignments placed back on contig coordinates"),
            MeasurementPatch(field="tools_run", value=[obs.get("tool") or "internal_gene_search"], origin="orf_protein_similarity_search"),
        ],
    )


def _act_hmmer(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    state = run.state
    if not hmmer_tools_available():
        return unavailable(action, "HMMER is not installed; profile scores cannot be measured and were not invented", {})
    qaa = _query_aa(m.profile)
    if not qaa:
        return unavailable(action, "the target profile yields no amino-acid sequence to build a model from", {})
    orfs = run.orfs()
    records = [(o["orf_id"], o["sequence"]) for o in orfs if o.get("sequence")]
    if not records:
        return unavailable(action, "no ORF of sufficient length was extracted from the assembly", {})
    qfa = _write_fa(state.out_dir / "action_hmmer" / "query.faa", [(m.query_id, qaa)])
    tfa = run.orf_fasta(state.out_dir / "_genome" / "orfs.faa")
    result = run_hmmbuild_and_search(qfa, tfa, state.out_dir / "action_hmmer" / "search", state.settings.project.threads)
    if not result.ok:
        return failed(action, result.error or "hmmbuild/hmmsearch did not complete")
    sequence_hits = (result.metrics or {}).get("sequence_hits") or []
    compact = [
        {k: row.get(k) for k in ("target_id", "full_evalue", "full_score", "best_domain_evalue", "best_domain_score")}
        for row in sequence_hits[:8]
        if isinstance(row, dict)
    ]
    # The profile nominates candidate ORFs; identity and coverage are then measured
    # by pairwise alignment rather than read off the HMM score.
    by_id = {o["orf_id"]: o for o in orfs}
    nominated = [by_id[str(row.get("target_id"))] for row in sequence_hits if isinstance(row, dict) and str(row.get("target_id")) in by_id]
    edge_bp = state.settings.thresholds.contig_edge_proximity_bp
    placed: list[GeneSearchHit] = []
    if nominated:
        aligned = search_proteins(m.query_id, qaa, [(o["orf_id"], o["sequence"]) for o in nominated[:50]], state.settings)
        for hit in aligned:
            orf = by_id.get(hit.contig_id)
            if orf is None:
                continue
            contig_len = len(state.contig_seqs.get(orf["contig_id"], "")) or orf.get("contig_length") or 0
            if not contig_len:
                continue
            remapped = _remap_orf_hit(hit, orf, contig_len, edge_bp, "hmmer_nominated_alignment")
            if remapped is not None:
                placed.append(remapped)
    observations = {
        "n_sequence_hits": len(sequence_hits),
        "hmm_hits": compact,
        "n_nominated_orfs": len(nominated),
        "n_placed_hits": len(placed),
        "limitation": (result.metrics or {}).get("limitation"),
    }
    if not placed:
        return ActionResult(
            action_id=action,
            status=ActionStatus.no_new_information,
            summary=f"Profile search for {m.query_id} nominated no alignable ORF",
            observations=observations,
            status_reason="the HMM search completed but nominated no ORF that could be aligned and placed on a contig",
        )
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Profile-nominated ORF alignments for {m.query_id}",
        observations=observations,
        patches=[
            MeasurementPatch(field="hits", value=placed, origin="hmm_orf_search", note="HMM-nominated ORFs aligned to the query and placed on contig coordinates"),
            MeasurementPatch(field="tools_run", value=["hmmbuild_hmmsearch"], origin="hmm_orf_search"),
        ],
    )


def _act_competitive_family(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    """Score declared competing families with the existing V5 discriminator.

    Does not invent a new family method. It calls ``discriminate_family`` and
    writes the result into ``TargetMeasurements.family_evidence``.
    """
    from genome_skeptic.families import families_sharing_class
    from genome_skeptic.validators.competitive_family import discriminate_family
    from genome_skeptic.validators.family_orthology import FamilyEvidence, classify_family_orthology, resolve_family_for_profile

    family = resolve_family_for_profile(
        m.profile,
        Path(run.state.settings.paths.family_dir) if run.state.settings.paths.family_dir else None,
    )
    if family is None:
        return unavailable(action, "no curated family was configured, so competing families cannot be scored", {})
    competitors = [cid for cid in list(family.competing_families or []) + families_sharing_class(family) if cid != family.family_id]
    if not competitors:
        return unavailable(action, "the requested family declares no competing families", {})
    contig_seqs = dict(m.contig_sequences or run.state.contig_seqs or {})
    if not contig_seqs:
        return unavailable(action, "no contig sequences are loaded, so the candidate protein cannot be translated", {})
    fam = m.family_evidence
    if fam is None:
        fam = FamilyEvidence(
            family_id=family.family_id,
            provenance={"created_by": "deterministic_family_orthology", "llm_invented_scores": False},
        )
    recon = dict(getattr(fam, "reconstruction", None) or {})
    if recon.get("contig") is None or recon.get("genomic_start") is None or recon.get("genomic_end") is None:
        hits = [h for h in m.hits if h.search_kind != "domain"]
        if not hits:
            return unavailable(action, "no placed hit exists from which to reconstruct a candidate locus", {})
        best = max(hits, key=lambda h: h.identity * h.query_coverage)
        recon.update(
            {
                "contig": best.contig_id,
                "genomic_start": min(best.tstart, best.tend),
                "genomic_end": max(best.tstart, best.tend),
                "strand": best.strand or "+",
            }
        )
    out_dir = run.state.out_dir / "action_competitive_family" / (m.query_id or family.family_id)
    scored = discriminate_family(
        family=family,
        reconstruction=recon,
        contig_sequences=contig_seqs,
        settings=run.state.settings,
        out_dir=out_dir,
    )
    updated = copy.deepcopy(fam)
    recon = dict(updated.reconstruction or {})
    recon["competitive_family"] = scored.as_dict()
    updated.reconstruction = recon
    classify_family_orthology(
        updated,
        family,
        run.state.settings,
        query_hits=m.hits,
        locus_evidence=m.locus_evidence,
    )
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Competitive family discrimination for {m.query_id}: {scored.classification}",
        observations={
            "classification": scored.classification,
            "target_family": scored.target_family,
            "best_competing_family": scored.best_competing_family,
            "score_margin": scored.score_margin,
            "reciprocal_family_assignment": scored.reciprocal_family_assignment,
            "supports_orthologue": updated.supports_orthologue,
            "competitors_scored": [row.get("family_id") for row in (scored.competitors_scored or [])],
        },
        patches=[
            MeasurementPatch(
                field="family_evidence",
                value=updated,
                origin="deterministic_competitive_family",
                note="competing-family HMM/sequence scores produced by the existing discriminate_family instrument",
            )
        ],
    )


def _act_paralogues(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    settings = run.state.settings
    from genome_skeptic.validators.falsification import _loci

    loci = _loci(m.hits, settings)
    fam = m.family_evidence
    return ActionResult(
        action_id=action,
        status=ActionStatus.no_new_information,
        summary=f"Copy-number readout for {m.query_id}",
        observations={
            "n_hit_loci": len(loci),
            "n_hits": len(m.hits),
            "paralogue": getattr(fam, "paralogue", None) if fam is not None else None,
        },
        status_reason=(
            "copy number is re-derived from hits that the final validator already clusters itself, "
            "so this readout adds no measurement to TargetMeasurements"
        ),
    )


def _act_catalytic(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    residues = list(getattr(m.profile, "catalytic_residues", None) or [])
    if not residues:
        return unavailable(action, "the target profile declares no catalytic residues, so none can be checked", {})
    return ActionResult(
        action_id=action,
        status=ActionStatus.no_new_information,
        summary=f"Catalytic-residue pattern declared on profile {m.query_id}",
        observations={"n_residues": len(residues)},
        status_reason=(
            "this action currently reports the residue pattern declared on the profile without aligning the "
            "candidate against it, so it produces no new measurement"
        ),
    )


def _act_contamination(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    contig_seqs = run.state.contig_seqs
    if not contig_seqs:
        return unavailable(action, "no contig sequences are loaded, so composition cannot be measured", {})
    contig_ids = list(dict.fromkeys(h.contig_id for h in m.hits))
    gc_by_contig: dict[str, float] = {}
    rows = []
    for cid in contig_ids[:24]:
        seq = contig_seqs.get(cid)
        if not seq:
            continue
        upper = seq.upper()
        gc = (upper.count("G") + upper.count("C")) / max(len(upper), 1)
        gc_by_contig[cid] = round(gc, 6)
        rows.append({"contig_id": cid, "length": len(seq), "gc": round(gc, 4), "taxonomy": m.contig_taxonomy.get(cid)})
    if not gc_by_contig:
        return unavailable(action, "no hit lies on a contig of this assembly, so composition cannot be measured", {"n_hits": len(m.hits)})
    total = sum(len(s) for s in contig_seqs.values())
    gc_total = sum(s.upper().count("G") + s.upper().count("C") for s in contig_seqs.values())
    genome_gc = round(gc_total / total, 6) if total else None
    patches = [MeasurementPatch(field="contig_gc", value=gc_by_contig, origin="contig_composition_inspection", note="GC fraction of each hit contig")]
    if genome_gc is not None:
        patches.append(MeasurementPatch(field="genome_gc", value=genome_gc, origin="contig_composition_inspection", note="assembly-wide GC fraction"))
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Hit-contig composition measurement for {m.query_id}",
        observations={"contigs": rows, "genome_gc": genome_gc, "taxonomy_available": bool(m.contig_taxonomy)},
        patches=patches,
    )


def _act_taxonomy(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    state = run.state
    tax_db = state.settings.paths.taxonomy_db
    if not tax_db:
        return unavailable(
            action,
            "no contig-taxonomy database was configured; taxonomy cannot be measured and was not invented",
            {"tools": taxonomy_tools_available()},
        )
    tax = run_contig_taxonomy(state.assembly, state.out_dir / "action_taxonomy", tax_db, state.settings.project.threads)
    if not tax.ok:
        return failed(action, tax.error or "contig taxonomy classifier did not complete")
    by_contig = tax.metrics.get("by_contig") or {}
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Contig taxonomy classification for {m.query_id}",
        observations={"by_hit_contig": {h.contig_id: by_contig.get(h.contig_id) for h in m.hits}},
        patches=[MeasurementPatch(field="contig_taxonomy", value=by_contig, origin="contig_taxonomy_classifier", note="per-contig taxonomic assignment")],
    )


def _act_breaks(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    state = run.state
    if not state.mapping_available:
        return unavailable(action, "no paired-end mapping was supplied; read-supported breaks cannot be measured", {})
    loci_spec = [
        {
            "contig": h.contig_id,
            "start": min(h.tstart, h.tend),
            "end": max(h.tstart, h.tend),
            "contig_length": h.contig_length or len(state.contig_seqs.get(h.contig_id, "")),
        }
        for h in m.hits
        if h.search_kind in {"nucleotide", "translated"}
    ]
    if not loci_spec:
        return unavailable(action, "there is no genomic interval to test for a read-supported break", {"n_hits": len(m.hits)})
    br = run_break_analysis(Path(state.mapping_sam), state.out_dir / "action_breaks", loci_spec)
    if not br.ok:
        return failed(action, br.error or "break analysis did not complete")
    by_locus = br.metrics.get("by_locus") or {}
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Read-supported break measurement for {m.query_id}",
        observations={"n_loci": len(loci_spec), "by_locus": by_locus},
        patches=[MeasurementPatch(field="break_evidence", value=by_locus, origin="read_supported_break_analysis", note="paired-end support across the candidate intervals")],
    )


def _act_placement(run: _V2Run, m: TargetMeasurements, action: str) -> ActionResult:
    placed = {}
    for le in m.locus_evidence or []:
        placed = (le.sequence_similarity or {}).get("placement") or {}
        if placed:
            break
    if not placed:
        return unavailable(action, "the deterministic locus validators produced no placement; a tree was not invented", {})
    return ActionResult(
        action_id=action,
        status=ActionStatus.informative,
        summary=f"Homologue placement readout for {m.query_id}",
        observations={"placement": placed},
        patches=[MeasurementPatch(field="phylogeny", value=placed, origin="phylogenetic_placement_readout", note="placement produced by the deterministic locus validators")],
    )


_HANDLERS = {
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
    "competitive_family": _act_competitive_family,
    "inspect_paralogue_copies": _act_paralogues,
    "inspect_catalytic_residues": _act_catalytic,
    "inspect_hit_contig_contamination": _act_contamination,
    "classify_contig_taxonomy": _act_taxonomy,
    "inspect_read_supported_breaks": _act_breaks,
    "place_target_among_homologues": _act_placement,
}

_MISSING_HANDLERS = set(ACTION_IDS) - set(_HANDLERS)
if _MISSING_HANDLERS:  # pragma: no cover - guards registry edits
    raise RuntimeError(f"registered actions without a deterministic executor: {sorted(_MISSING_HANDLERS)}")


def execute_registered_action(action: str, run: _V2Run, m: TargetMeasurements) -> ActionResult:
    """Run one registered action. Tool failures become FAILED, never exceptions."""
    run.state.call_graph.append(f"execute_registered_action:{action}")
    fn = _HANDLERS.get(action)
    if fn is None:
        return failed(action, "registered action has no deterministic executor")
    try:
        return fn(run, m, action)
    except Exception as exc:
        return failed(action, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------
# measurement transitions
# --------------------------------------------------------------------------


@dataclass
class _Transition:
    from_state: str
    to_state: str
    action_id: str
    requested_by: str
    result: ActionResult
    before: dict[str, Any]
    after: dict[str, Any]

    @property
    def changed(self) -> bool:
        return self.before["hash"] != self.after["hash"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_state,
            "to": self.to_state,
            "action_id": self.action_id,
            "requested_by": self.requested_by,
            "status": self.result.status.value,
            "status_reason": self.result.status_reason,
            "measurement_state_changed": self.changed,
            "n_new_measurements": self.result.n_new_measurements,
            "updated_measurement_fields": sorted({u.field for u in self.result.applied if u.n_new}),
            "measurement_hash_before": self.before["hash"],
            "measurement_hash_after": self.after["hash"],
            "evidence_ids": list(self.result.evidence_ids),
        }


def _next_states(transitions: list[_Transition]) -> tuple[str, str]:
    """Label the measurement states m0 -> m1 -> m2 in execution order."""
    i = len(transitions)
    return f"m{i}", f"m{i + 1}"


_EVIDENCE_KIND = {
    ActionStatus.informative: "measurement",
    ActionStatus.no_new_information: "no_new_information",
    ActionStatus.unavailable: "missing_validator",
    ActionStatus.failed: "action_failure",
}


def run_action_and_update(
    run: _V2Run,
    m: TargetMeasurements,
    action: str,
    *,
    requested_by: str,
    from_state: str,
    to_state: str,
) -> _Transition:
    """Execute one action, apply its validated patch, and record both in the ledger.

    The action never writes to ``m`` itself; ``apply_action_result`` is the only
    writer, and it decides the final status by diffing the measurement state.
    """
    state = run.state
    before = measurement_fingerprint(m)
    result = execute_registered_action(action, run, m)
    result = apply_action_result(m, result, settings=state.settings)
    after = measurement_fingerprint(m)

    action_ev = state.add_evidence(
        "target_gene",
        _EVIDENCE_KIND[result.status],
        result.summary,
        {
            "action": action,
            "requested_by": requested_by,
            "status": result.status.value,
            "status_reason": result.status_reason,
            "limitation": result.limitation,
            **result.observations,
        },
    )
    result.evidence_ids.append(action_ev.id)

    update_ev = state.add_evidence(
        "target_gene",
        "measurement_update",
        (
            f"Measurement state {from_state} -> {to_state} after {action}: "
            + (
                "updated " + ", ".join(sorted({u.field for u in result.applied if u.n_new}))
                if result.status == ActionStatus.informative
                else "no measured value changed"
            )
        ),
        {
            "action": action,
            "requested_by": requested_by,
            "status": result.status.value,
            "from_state": from_state,
            "to_state": to_state,
            "measurement_state_changed": before["hash"] != after["hash"],
            "measurement_hash_before": before["hash"],
            "measurement_hash_after": after["hash"],
            "applied_updates": [u.as_dict() for u in result.applied],
            "n_hits_before": before["n_hits"],
            "n_hits_after": after["n_hits"],
            "source_evidence_id": action_ev.id,
        },
    )
    result.evidence_ids.append(update_ev.id)
    return _Transition(
        from_state=from_state,
        to_state=to_state,
        action_id=action,
        requested_by=requested_by,
        result=result,
        before=before,
        after=after,
    )


# --------------------------------------------------------------------------
# planner / critic payloads and validation
# --------------------------------------------------------------------------


def _planner_payload(m: TargetMeasurements, run: _V2Run, unresolved: list[str]) -> dict[str, Any]:
    return build_planner_view(
        m,
        evidence=run.state.evidence,
        capabilities=run.capabilities,
        performed=run.baseline_work,
        settings=run.state.settings,
    )


def _critic_payload(
    decision: AgentDecision,
    run: _V2Run,
    m: TargetMeasurements,
    unresolved: list[str],
    transition: _Transition | None,
    already_run: list[str],
) -> dict[str, Any]:
    new_ids = set(transition.result.evidence_ids) if transition is not None else set()
    new_evidence = [e for e in run.state.evidence if e.id in new_ids] if new_ids else run.state.evidence[-4:]
    return build_critic_view(
        decision,
        m=m,
        evidence=run.state.evidence,
        capabilities=run.capabilities,
        performed=run.baseline_work,
        actions_already_tried=already_run,
        new_evidence=new_evidence,
        transition=None if transition is None else transition.as_dict(),
        settings=run.state.settings,
    )


def _alias_v1_requested_actions(actions: list[str] | None, decision: str | None) -> tuple[list[str], str | None]:
    """Rewrite frozen V1 decision verbs into a V2 control decision.

    Returns (actions, alias_applied). ``alias_applied`` is the V1 verb that was
    rewritten, or None when nothing changed. Legal registered choices are left
    untouched, including when they sit next to a V1 verb. An empty plan with
    decision ``continue``/``rerun`` is left empty so the empty-plan abstention
    stays distinguishable from an explicit ``ask_human``.
    """
    raw = list(actions or [])
    legal = [a for a in raw if a in REGISTERED_CHOICES]
    if legal:
        return [legal[0]], None
    for token in raw:
        if token in V1_DECISION_TO_CONTROL:
            return [V1_DECISION_TO_CONTROL[token]], token
    if not raw and (decision or "") in {"ask_human", "stop"}:
        return [ABSTAIN_UNRESOLVED], decision
    return raw, None


def _sanitize_evidence_ids(ids: list[str] | None, known: set[str]) -> tuple[list[str], list[str]]:
    """Split cited IDs into those that exist in the ledger and those that do not.

    Dropping a non-ID can only ever remove unsupported support, so it is safe;
    the dropped tokens are reported so the repair prompt can name them.
    """
    kept: list[str] = []
    dropped: list[str] = []
    for eid in ids or []:
        (kept if eid in known else dropped).append(eid)
    return list(dict.fromkeys(kept)), list(dict.fromkeys(dropped))


def _recover_planner_fields(
    decision: AgentDecision, known: set[str], evidence: list[Evidence]
) -> tuple[AgentDecision, list[str]]:
    """Drop citations that are not evidence IDs, then fill fields the model left empty.

    Recovery only reuses IDs and action names the model itself wrote; it never
    invents support. Sanitising first matters because a wrong-but-non-empty
    ``evidence_ids`` (for example ``["hits"]``) would otherwise look well-formed
    and skip both recovery and the repair pass.
    """
    import re

    data = decision.model_dump()
    kept, dropped = _sanitize_evidence_ids(data.get("evidence_ids"), known)
    data["evidence_ids"] = kept
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
        if not recovered:
            for ev in evidence:
                if ev.id not in known:
                    continue
                marker = json.dumps(ev.values, default=str)
                if any(token in blob for token in re.findall(r"\d+\.\d+", marker)):
                    recovered.append(ev.id)
        if recovered:
            data["evidence_ids"] = list(dict.fromkeys(recovered))
    if not data.get("requested_actions"):
        mentioned_actions = [name for name in REGISTERED_CHOICES if name in blob]
        if mentioned_actions:
            data["requested_actions"] = [mentioned_actions[0]]
    aliased, _v1_verb = _alias_v1_requested_actions(data.get("requested_actions"), data.get("decision"))
    data["requested_actions"] = aliased
    if not data.get("alternative_explanations"):
        mentioned_h = [h for h in HYPOTHESIS_IDS if h in blob]
        if mentioned_h:
            data["alternative_explanations"] = mentioned_h[:3]
    return AgentDecision.model_validate(data), dropped


def _not_an_evidence_id(dropped: list[str], known: set[str]) -> str:
    return (
        f"evidence_ids contained {dropped}, which are not evidence IDs. "
        f"Valid evidence IDs are exactly: {sorted(known)}. "
        "Input names, measurement field names and action names are not evidence IDs."
    )


def _planner_defects(decision: AgentDecision, known: set[str], dropped: list[str]) -> list[str]:
    """Everything the repair pass should be asked to fix, in prompt-ready form."""
    defects: list[str] = []
    if dropped:
        defects.append(_not_an_evidence_id(dropped, known))
    if not (decision.evidence_ids or []):
        defects.append("evidence_ids was empty; cite at least one supplied evidence ID.")
    actions = list(decision.requested_actions or [])
    if not actions:
        defects.append(
            "requested_actions was empty; return exactly one action_id from registered_actions "
            f"or one decision_id from control_decisions (use '{ABSTAIN_UNRESOLVED}' if no available "
            "action can change a relevant measurement)."
        )
    elif len(actions) > 1:
        defects.append(f"requested_actions must contain exactly one entry, not {actions}.")
    else:
        unregistered = [a for a in actions if a not in REGISTERED_CHOICES]
        if unregistered:
            defects.append(
                f"requested_actions contained {unregistered}, which is not registered. "
                "Choose one action_id from registered_actions or one decision_id from control_decisions."
            )
    return defects


def _recover_critic_fields(critic: CriticReview, known: set[str]) -> tuple[CriticReview, list[str]]:
    """The planner-side treatment, applied to the critic.

    Drop citations that are not evidence IDs, then recover IDs the critic named
    in its prose but omitted from ``evidence_ids``. Only IDs the critic itself
    wrote are recovered, so this cannot manufacture support.
    """
    import re

    data = critic.model_dump()
    kept, dropped = _sanitize_evidence_ids(data.get("evidence_ids"), known)
    data["evidence_ids"] = kept
    if not kept:
        blob = " ".join(
            [
                data.get("rationale") or "",
                " ".join(data.get("failure_modes") or []),
                " ".join(data.get("disconfirming_tests") or []),
            ]
        )
        recovered = [eid for eid in re.findall(r"\bE\d{3}\b", blob) if eid in known]
        if recovered:
            data["evidence_ids"] = list(dict.fromkeys(recovered))
    return CriticReview.model_validate(data), dropped


def _critic_defects(critic: CriticReview, known: set[str], dropped: list[str]) -> list[str]:
    defects: list[str] = []
    if dropped:
        defects.append(_not_an_evidence_id(dropped, known))
    if not (critic.evidence_ids or []):
        defects.append("evidence_ids was empty; cite at least one supplied evidence ID.")
    return defects


def _validate_planner(decision: AgentDecision, known: set[str]) -> tuple[str | None, str | None]:
    """Return (chosen action or control decision, failure reason)."""
    if not (decision.evidence_ids or []):
        return None, "planner cited no evidence IDs"
    unknown = [eid for eid in (decision.evidence_ids or []) if eid not in known]
    if unknown:
        return None, f"planner cited unknown evidence IDs: {unknown}"
    actions, _v1_verb = _alias_v1_requested_actions(decision.requested_actions, decision.decision)
    if not actions:
        # An empty plan is a malformed answer to a real question: no registered
        # action was judged worth running. V2 records that as an abstention
        # rather than turning it into an execution failure.
        return ABSTAIN_UNRESOLVED, None
    if len(actions) > 1:
        return None, f"planner requested more than one action: {actions}"
    choice = actions[0]
    if choice not in REGISTERED_CHOICES:
        return None, f"planner requested an unregistered action: {choice}"
    return choice, None


def _validate_critic(critic: CriticReview, known: set[str]) -> tuple[CriticReview | None, str | None]:
    if not (critic.evidence_ids or []):
        return None, "critic cited no evidence IDs"
    unknown = [eid for eid in (critic.evidence_ids or []) if eid not in known]
    if unknown:
        return None, f"critic cited unknown evidence IDs: {unknown}"
    if critic.verdict not in {"accept", "challenge"}:
        return None, "critic verdict was malformed"
    return critic, None


def planner_decision_to_agent(decision: PlannerDecision) -> AgentDecision:
    """Map the compact planner JSON onto the frozen AgentDecision object."""
    action = (decision.requested_action or "").strip() or None
    leading = (decision.leading_hypothesis or "").strip() or None
    alternative = (decision.alternative_hypothesis or "").strip() or None
    if action in CONTROL_DECISIONS or action in V1_DECISION_VERBS:
        requested = [action]
        v1 = "ask_human" if action in {ABSTAIN_UNRESOLVED, "ask_human", "stop"} else "continue"
    elif decision.decision == "finalize":
        requested = [FINALIZE_WITH_CURRENT_EVIDENCE]
        v1 = "continue"
    elif decision.decision == "abstain":
        requested = [ABSTAIN_UNRESOLVED]
        v1 = "ask_human"
    else:
        requested = [action] if action else []
        v1 = "continue"
    explanations = [h for h in (leading, alternative) if h]
    return AgentDecision(
        decision=v1,
        rationale=decision.rationale,
        evidence_ids=list(decision.evidence_ids or []),
        alternative_explanations=explanations,
        requested_actions=requested,
        confidence=decision.confidence,
    )


def critic_decision_to_review(decision: CriticDecision) -> CriticReview:
    action = (decision.requested_action or "").strip() or None
    mode = (decision.failure_mode or "").strip() or None
    return CriticReview(
        verdict=decision.verdict,
        rationale=decision.rationale,
        evidence_ids=list(decision.evidence_ids or []),
        failure_modes=[mode] if mode else [],
        disconfirming_tests=[action] if action else [],
    )


def select_critic_action(
    critic: CriticReview,
    capabilities: dict[str, bool],
    already_run: list[str],
    performed: frozenset[str] = frozenset(),
    measurements: Any = None,
    *,
    edge_bp: int = 300,
) -> tuple[str | None, str]:
    """Pick at most one follow-up action the critic's challenge justifies.

    The critic must name either a registered action or a registered hypothesis;
    a bare 'challenge' with no concrete alternative earns no second measurement.
    An action the critic names is still refused when it cannot move the measured
    state, so a challenge cannot be answered by a guaranteed NO_NEW_INFORMATION.
    """
    if critic.verdict != "challenge":
        return None, "critic accepted the decision, so no further measurement was triggered"
    named = [a for a in (critic.disconfirming_tests or []) if a in BY_ID and a not in already_run]
    for action_id in named:
        spec = BY_ID[action_id]
        if not spec.is_available(capabilities):
            continue
        inert = spec.inert_because(performed, measurements, edge_bp=edge_bp)
        if inert:
            continue
        return action_id, f"critic named an available discriminating action: {action_id}"
    blob = " ".join([critic.rationale or "", *(critic.failure_modes or []), *(critic.disconfirming_tests or [])])
    hypotheses = {h for h in HYPOTHESIS_IDS if h in blob}
    if not hypotheses:
        return None, "critic challenged without naming a concrete unresolved alternative or an available action"
    candidates = [
        spec
        for spec in actions_discriminating(hypotheses, capabilities, performed, measurements, edge_bp=edge_bp)
        if spec.action_id not in already_run
    ]
    if not candidates:
        return None, f"no unused action can still change a measurement discriminating {sorted(hypotheses)}"
    chosen = candidates[0]
    return chosen.action_id, f"cheapest available action discriminating {sorted(hypotheses)}: {chosen.action_id}"


def _llm_runtime_breakdown(call_log: list[dict[str, Any]]) -> dict[str, Any]:
    """Token/time split for planner vs critic. Does not change scientific behaviour."""
    planner = [r for r in call_log if str(r.get("request_type") or "").startswith(("AgentDecision", "PlannerDecision"))]
    critic = [r for r in call_log if str(r.get("request_type") or "").startswith(("CriticReview", "CriticDecision"))]

    def _sum(rows: list[dict[str, Any]], key: str) -> float:
        return round(sum(float(r.get(key) or 0) for r in rows), 3)

    return {
        "planner_call_estimated_tokens": sum(int(r.get("estimated_tokens") or 0) for r in planner),
        "critic_call_estimated_tokens": sum(int(r.get("estimated_tokens") or 0) for r in critic),
        "planner_seconds": _sum(planner, "elapsed_seconds"),
        "critic_seconds": _sum(critic, "elapsed_seconds"),
        "llm_seconds": _sum(list(call_log), "elapsed_seconds"),
    }


def _unresolved_failure(m: TargetMeasurements, reason: str, evidence_ids: list[str], notes: str) -> Claim:
    return Claim(
        claim_id=f"C_target_{m.query_id}",
        claim_type=ClaimType.target_gene_not_detected,
        statement=(
            f"Agentic analysis of target '{m.query_id}' is unresolved because the planner/critic loop failed closed. "
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


# --------------------------------------------------------------------------
# orchestrator
# --------------------------------------------------------------------------


def run_skeptic_agentic_v2(
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
    initial_measurements: TargetMeasurements | None = None,
) -> tuple[list[Claim], list[LocusEvidence], dict[str, Any]]:
    """Agentic V2. Frozen V1 and frozen deterministic V5 are untouched."""
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
    state.call_graph.append("run_skeptic_agentic_v2")
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
        "control_decision": None,
        "critic_challenge": None,
        "critic_second_action": None,
        "critic_second_action_reason": None,
        "agent_failure": None,
        "final_validator_ran": False,
        "planner_returned_empty_plan": False,
        "planner_chose_unavailable_action": False,
        "abstention_justified": None,
        "actions_executed": [],
        "measurement_trajectory": [],
        "measurements_changed_before_validation": False,
        "initial_measurements_injected": initial_measurements is not None,
        "validator_consumed_measurement_hash": None,
        "validator_consumed_m0": None,
    }

    if initial_measurements is not None:
        measurements = copy.deepcopy(initial_measurements)
        loci = list(measurements.locus_evidence or [])
        state.contig_seqs = dict(measurements.contig_sequences or {})
        state.call_graph.append("initial_measurements_injected")
    else:
        measurements, loci = collect_assembly_target_measurements(state, query_ids=query_ids)
    before_ids = measurements_to_evidence(state, measurements)
    provenance["evidence_ids_before_action"] = list(before_ids)

    run = _V2Run(state=state, baseline_work=BASELINE_WORK)
    run.capabilities = capabilities_for(state, measurements)
    provenance["available_inputs"] = dict(run.capabilities)
    provenance["available_actions"] = available_action_ids(run.capabilities)
    provenance["baseline_work_already_done"] = sorted(run.baseline_work)
    edge_bp = int(settings.thresholds.contig_edge_proximity_bp)
    provenance["state_changing_actions"] = state_changing_action_ids(
        run.capabilities, run.baseline_work, measurements, edge_bp=edge_bp
    )
    provenance["inert_actions"] = [
        {"action_id": spec["action_id"], "because": spec["inert_now_because"]}
        for spec in catalog_payload(run.capabilities, run.baseline_work, measurements, edge_bp=edge_bp)
        if spec["available"] and spec["inert_now"]
    ]

    m0 = measurement_fingerprint(measurements)
    provenance["measurement_state"] = {"m0": m0}

    unresolved = list(ADVERSARIAL_QUESTIONS.get("target_gene", []))
    llm_ok = bool(settings.llm.enabled and settings.execution.enable_critic and settings.execution.allow_model_to_choose_actions)
    planner: AgentDecision | None = None
    critic: CriticReview | None = None
    fail_reason: str | None = None
    transitions: list[_Transition] = []
    actions_run: list[str] = []
    control_decision: str | None = None

    if not llm_ok:
        fail_reason = "LLM planner/critic is disabled; genome_skeptic_agentic_v2 fails closed instead of silent V5 fallback"
    else:
        planner_cfg = settings.llm.for_role("planner")
        critic_cfg = settings.llm.for_role("critic")
        planner_client = OllamaJSONClient(planner_cfg)
        critic_client = OllamaJSONClient(critic_cfg)
        planner_payload = _planner_payload(measurements, run, unresolved)
        provenance["prompt_hash"] = _sha256_obj({"system": AGENTIC_REASONER_SYSTEM, "payload": planner_payload})
        provenance["planner_estimated_tokens"] = estimated_tokens(planner_payload)
        provenance["model_name"] = planner_cfg.model
        try:
            state.call_graph.append("OllamaJSONClient.ask_json:AgentDecision")
            provenance["planner_invoked"] = True
            compact_planner = planner_client.ask_json(AGENTIC_REASONER_SYSTEM, planner_payload, PlannerDecision)
            planner = planner_decision_to_agent(compact_planner)
            first_planner = planner
            _, v1_verb = _alias_v1_requested_actions(first_planner.requested_actions, first_planner.decision)
            if v1_verb:
                provenance["v1_requested_action_aliased"] = v1_verb
            planner, dropped = _recover_planner_fields(planner, state.known_ids(), state.evidence)
            first_recovered = planner
            provenance["planner_dropped_evidence_ids"] = list(dropped)
            defects = _planner_defects(planner, state.known_ids(), dropped)
            provenance["planner_defects"] = list(defects)
            if defects:
                repair_payload = dict(planner_payload)
                repair_payload["previous_decision"] = compact_planner.model_dump()
                repair_payload["defects_to_fix"] = defects
                repair_payload["repair"] = (
                    "The previous JSON was rejected for the reasons listed in defects_to_fix. Return one JSON "
                    "object matching the schema. evidence_ids must contain only strings copied verbatim from "
                    "valid_evidence_ids. requested_action must be exactly one action_id from available_actions "
                    "or one control decision "
                    f"(use '{ABSTAIN_UNRESOLVED}' if no available action can change a relevant measurement)."
                )
                state.call_graph.append("OllamaJSONClient.ask_json:AgentDecision_repair")
                repaired, repaired_dropped = _recover_planner_fields(
                    planner_decision_to_agent(
                        planner_client.ask_json(AGENTIC_REASONER_SYSTEM, repair_payload, PlannerDecision)
                    ),
                    state.known_ids(),
                    state.evidence,
                )
                provenance["planner_repair_dropped_evidence_ids"] = list(repaired_dropped)
                merged = repaired.model_dump()
                if not merged.get("requested_actions") and first_recovered.requested_actions:
                    merged["requested_actions"] = list(first_recovered.requested_actions)
                if not merged.get("evidence_ids") and first_recovered.evidence_ids:
                    merged["evidence_ids"] = list(first_recovered.evidence_ids)
                planner = AgentDecision.model_validate(merged)
                provenance["planner_defects_after_repair"] = _planner_defects(
                    planner, state.known_ids(), provenance["planner_repair_dropped_evidence_ids"]
                )
            provenance["planner_returned_empty_plan"] = not (planner.requested_actions or [])
            provenance["response_hash"] = _sha256_text(planner.model_dump_json())
            provenance["cited_evidence_ids"] = list(planner.evidence_ids or [])
            (out_dir / "planner_decision.json").write_text(planner.model_dump_json(indent=2), encoding="utf-8")

            choice, err = _validate_planner(planner, state.known_ids())
            if err:
                fail_reason = err
            elif choice in CONTROL_DECISIONS:
                control_decision = choice
                provenance["control_decision"] = choice
                remaining = [
                    spec.action_id
                    for spec in actions_discriminating(
                        set(HYPOTHESIS_IDS), run.capabilities, run.baseline_work, measurements, edge_bp=edge_bp
                    )
                ]
                provenance["abstention_justified"] = not remaining if choice == ABSTAIN_UNRESOLVED else None
                provenance["actions_still_available_at_abstention"] = remaining
                state.add_evidence(
                    "target_gene",
                    "control_decision",
                    f"Planner control decision: {choice}",
                    {
                        "decision_id": choice,
                        "meaning": CONTROL_DECISION_SEMANTICS[choice],
                        "inferred_from_empty_plan": provenance["planner_returned_empty_plan"],
                        "actions_still_available": remaining,
                        "rationale": planner.rationale,
                    },
                )
            else:
                provenance["selected_action"] = choice
                spec = BY_ID[choice]
                provenance["planner_chose_unavailable_action"] = not spec.is_available(run.capabilities)
                provenance["planner_chose_inert_action"] = spec.inert_because(
                    run.baseline_work, measurements, edge_bp=edge_bp
                ) or None
                from_state, to_state = _next_states(transitions)
                transitions.append(
                    run_action_and_update(
                        run, measurements, choice, requested_by="planner", from_state=from_state, to_state=to_state
                    )
                )
                actions_run.append(choice)

            if fail_reason is None:
                critic_payload = _critic_payload(
                    planner, run, measurements, unresolved, transitions[0] if transitions else None, actions_run
                )
                provenance["critic_prompt_hash"] = _sha256_obj({"system": AGENTIC_CRITIC_SYSTEM, "payload": critic_payload})
                provenance["critic_estimated_tokens"] = estimated_tokens(critic_payload)
                try:
                    state.call_graph.append("OllamaJSONClient.ask_json:CriticReview")
                    provenance["critic_invoked"] = True
                    critic = critic_decision_to_review(
                        critic_client.ask_json(AGENTIC_CRITIC_SYSTEM, critic_payload, CriticDecision)
                    )
                    critic, critic_dropped = _recover_critic_fields(critic, state.known_ids())
                    provenance["critic_dropped_evidence_ids"] = list(critic_dropped)
                    critic_defects = _critic_defects(critic, state.known_ids(), critic_dropped)
                    provenance["critic_defects"] = list(critic_defects)
                    if critic_defects:
                        repair_c = dict(critic_payload)
                        repair_c["defects_to_fix"] = critic_defects
                        repair_c["repair"] = (
                            "The previous JSON was rejected for the reasons listed in defects_to_fix. "
                            "Cite at least one evidence ID copied verbatim from valid_evidence_ids."
                        )
                        state.call_graph.append("OllamaJSONClient.ask_json:CriticReview_repair")
                        critic, critic_dropped = _recover_critic_fields(
                            critic_decision_to_review(
                                critic_client.ask_json(AGENTIC_CRITIC_SYSTEM, repair_c, CriticDecision)
                            ),
                            state.known_ids(),
                        )
                        provenance["critic_defects_after_repair"] = _critic_defects(
                            critic, state.known_ids(), critic_dropped
                        )
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
                        # The critic cannot change the claim. A citation-format
                        # failure therefore skips the optional second action
                        # (the challenge is unusable) but does not veto the
                        # deterministic validator.
                        provenance["critic_unusable"] = err
                        critic = None
                    else:
                        # At most one follow-up, even when the planner finalized or
                        # abstained: a concrete challenge still deserves a measurement.
                        second, reason = select_critic_action(
                            critic,
                            run.capabilities,
                            actions_run,
                            run.baseline_work,
                            measurements,
                            edge_bp=edge_bp,
                        )
                        provenance["critic_second_action"] = second
                        provenance["critic_second_action_reason"] = reason
                        if second:
                            from_state, to_state = _next_states(transitions)
                            transitions.append(
                                run_action_and_update(
                                    run, measurements, second, requested_by="critic", from_state=from_state, to_state=to_state
                                )
                            )
                            actions_run.append(second)
                except Exception as exc:
                    fail_reason = f"critic call failed: {exc}"
        except Exception as exc:
            fail_reason = f"planner call failed: {exc}"

    m_final = measurement_fingerprint(measurements)
    provenance["measurement_state"]["m_final"] = m_final
    provenance["measurements_changed_before_validation"] = m0["hash"] != m_final["hash"]
    provenance["measurement_trajectory"] = [t.as_dict() for t in transitions]
    provenance["actions_executed"] = [t.result.as_dict() for t in transitions]
    provenance["informative_action_count"] = sum(1 for t in transitions if t.result.status == ActionStatus.informative)
    provenance["action_status_counts"] = {
        status.value: sum(1 for t in transitions if t.result.status == status) for status in ActionStatus
    }

    stats = _call_stats()
    provenance.update({k: stats[k] for k in ("model_call_count", "planner_model_call_count", "critic_model_call_count", "repair_count")})
    provenance.update(_llm_runtime_breakdown(stats.get("call_log") or []))
    notes = (
        "genome_skeptic_agentic_v2: LLM did not supply identity, coverage, E-values, domain hits, "
        "catalytic residues, orthologues, gene order, or reciprocal hits. "
        f"planner_invoked={provenance['planner_invoked']} critic_invoked={provenance['critic_invoked']} "
        f"model={provenance['model_name']} prompt_hash={provenance['prompt_hash']} "
        f"response_hash={provenance['response_hash']} selected_action={provenance['selected_action']} "
        f"control_decision={provenance['control_decision']} "
        f"critic_second_action={provenance['critic_second_action']} "
        f"measurements_changed_before_validation={provenance['measurements_changed_before_validation']} "
        f"measurement_hash_m0={m0['hash']} measurement_hash_final={m_final['hash']} "
        f"critic_prompt_hash={provenance['critic_prompt_hash']} critic_response_hash={provenance['critic_response_hash']}"
    )

    if fail_reason:
        provenance["agent_failure"] = fail_reason
        claims = [_unresolved_failure(measurements, fail_reason, [e.id for e in state.evidence], notes)]
    else:
        state.call_graph.append("build_target_gene_claim")
        consumed = measurement_fingerprint(measurements)
        provenance["validator_consumed_measurement_hash"] = consumed["hash"]
        provenance["validator_consumed_m0"] = consumed["hash"] == m0["hash"]
        claim, anoms, _tests = build_target_gene_claim(measurements, settings, [e.id for e in state.evidence])
        provenance["final_validator_ran"] = True
        state.anomalies.extend(anoms)
        extras = [h for h in (planner.alternative_explanations or []) if h in HYPOTHESIS_IDS] if planner else []
        if extras:
            claim.alternative_explanations = list(dict.fromkeys(list(claim.alternative_explanations or []) + extras))
        if critic and critic.verdict == "challenge":
            claim.rationale += (
                " Critic verdict=challenge was recorded in agentic provenance; the deterministic validator remains the authority."
            )
        if control_decision == ABSTAIN_UNRESOLVED:
            claim.rationale += (
                " The planner abstained: no registered action could change a measurement bearing on the open alternatives. "
                "The abstention is recorded in provenance and did not alter the deterministic claim."
            )
        claim.provenance.notes = (claim.provenance.notes or "") + " " + notes
        claim.provenance.evidence_ledger_ids = list(
            dict.fromkeys(list(claim.provenance.evidence_ledger_ids or []) + [e.id for e in state.evidence])
        )
        claims = [claim]
        provenance["preferred_hypothesis"] = (planner.alternative_explanations or [None])[0] if planner else None

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

    final_loci = measurements.locus_evidence or loci
    (out_dir / "claims.json").write_text(json.dumps([c.model_dump(mode="json") for c in claims], indent=2), encoding="utf-8")
    (out_dir / "locus_evidence.json").write_text(json.dumps([le.model_dump() for le in final_loci], indent=2), encoding="utf-8")
    (out_dir / "evidence.json").write_text(json.dumps([e.model_dump() for e in state.evidence], indent=2), encoding="utf-8")
    (out_dir / "agentic_provenance.json").write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")
    (out_dir / "call_log.json").write_text(json.dumps(stats["call_log"], indent=2, default=str), encoding="utf-8")
    if planner is not None:
        (out_dir / "planner_decision.json").write_text(planner.model_dump_json(indent=2), encoding="utf-8")
    if critic is not None:
        (out_dir / "critic_review.json").write_text(critic.model_dump_json(indent=2), encoding="utf-8")
    return claims, final_loci, provenance
