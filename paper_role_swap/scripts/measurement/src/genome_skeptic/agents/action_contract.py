"""Structured action contract for Genome Skeptic Agentic V2.

In Agentic V1 a registered action wrote its result into the evidence ledger but
usually not into ``TargetMeasurements``. The final deterministic validator
therefore received the same ``m0`` that deterministic V5 would have received,
which biased V1 towards reproducing V5 regardless of what the planner reasoned.

This module defines the contract that makes a diagnostic action causally able to
change the measured state. Every executor returns an :class:`ActionResult`
carrying deterministic measurement patches; only :func:`apply_action_result`
writes them into ``TargetMeasurements``, and it recomputes the real delta rather
than trusting the executor's self-report.

The LLM never authors a patch value. Patches are constructed inside
deterministic executors and are rejected unless they declare a registered
deterministic origin.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit, LocusEvidence, OrthologueRecord
from genome_skeptic.validators.falsification import TargetMeasurements


class ActionStatus(str, Enum):
    """Outcome class of a registered diagnostic action.

    ``informative`` is only assigned once a patch has actually changed
    ``TargetMeasurements``; an executor cannot award it to itself.
    """

    informative = "INFORMATIVE"
    no_new_information = "NO_NEW_INFORMATION"
    unavailable = "UNAVAILABLE"
    failed = "FAILED"


FINALIZE_WITH_CURRENT_EVIDENCE = "FINALIZE_WITH_CURRENT_EVIDENCE"
ABSTAIN_UNRESOLVED = "ABSTAIN_UNRESOLVED"

CONTROL_DECISIONS: tuple[str, ...] = (FINALIZE_WITH_CURRENT_EVIDENCE, ABSTAIN_UNRESOLVED)

CONTROL_DECISION_SEMANTICS: dict[str, str] = {
    FINALIZE_WITH_CURRENT_EVIDENCE: (
        "No further measurement is needed: the current measurements already discriminate the "
        "competing explanations. The deterministic validator runs on the current measurements."
    ),
    ABSTAIN_UNRESOLVED: (
        "No registered action can resolve the remaining alternatives on the available inputs. "
        "The deterministic validator still runs, and the abstention is recorded as a limitation. "
        "This is a legitimate outcome, not an execution failure."
    ),
}

# AgentDecision.decision is a frozen V1 field: continue | rerun | stop | ask_human.
# qwen3:4b copies those verbs into requested_actions. They are not diagnostic
# actions and they are not V2 control decisions; they mean "I cannot proceed
# with a registered measurement." Mapping them here keeps that intent from
# becoming an execution crash. Truly invented action names are not aliased.
V1_DECISION_VERBS: frozenset[str] = frozenset({"continue", "rerun", "stop", "ask_human"})
V1_DECISION_TO_CONTROL: dict[str, str] = {
    "ask_human": ABSTAIN_UNRESOLVED,
    "stop": ABSTAIN_UNRESOLVED,
    "rerun": ABSTAIN_UNRESOLVED,
    "continue": ABSTAIN_UNRESOLVED,
}

# Each measurement field has exactly one legal merge operation. The operation is
# derived from the field name, never chosen by the caller, so an executor cannot
# smuggle a replace where only a merge is sound.
FIELD_OPS: dict[str, str] = {
    "hits": "append_hits",
    "hit_edge_flags": "revise_hit_flags",
    "coverage_by_hit": "merge_dict",
    "neighborhood_by_hit": "merge_dict",
    "contig_taxonomy": "merge_dict",
    "break_evidence": "merge_dict",
    "contig_gc": "merge_dict",
    "genome_gc": "set_scalar",
    "measured_taxonomy": "set_scalar",
    "phylogeny": "replace_dict",
    "locus_evidence": "replace_locus_evidence",
    "orthologues": "merge_orthologues",
    "family_evidence": "replace_family_evidence",
    "tools_run": "extend_unique",
    "tools_unavailable": "extend_unique",
    "limitations": "extend_unique",
    "depth_available": "set_flag",
    "annotation_available": "set_flag",
    "proteins_available": "set_flag",
    "mapping_available": "set_flag",
}

# Virtual patch fields write into a different attribute than their own name.
_VIRTUAL_TARGETS: dict[str, str] = {
    "hit_edge_flags": "hits",
    "orthologues": "locus_evidence",
}

DETERMINISTIC_ORIGINS: frozenset[str] = frozenset(
    {
        "internal_gene_search",
        "contig_edge_recomputation",
        "samtools_depth",
        "gff_synteny",
        "reference_locus_comparison",
        "reciprocal_best_hits",
        "orf_protein_similarity_search",
        "hmm_orf_search",
        "locus_multiplicity_clustering",
        "catalytic_residue_inspection",
        "contig_composition_inspection",
        "contig_taxonomy_classifier",
        "read_supported_break_analysis",
        "phylogenetic_placement_readout",
        "locus_evidence_rebuild",
        "deterministic_competitive_family",
        "deterministic_ortholog_references",
    }
)


class PatchRejected(ValueError):
    """Raised when a patch is not admissible as a deterministic measurement."""


@dataclass(frozen=True)
class MeasurementPatch:
    """One deterministic measurement update destined for ``TargetMeasurements``.

    ``origin`` names the deterministic instrument that produced ``value``. It is
    checked against :data:`DETERMINISTIC_ORIGINS` so that no value reachable from
    planner or critic text can be applied.
    """

    field: str
    value: Any
    origin: str
    note: str = ""

    @property
    def op(self) -> str:
        try:
            return FIELD_OPS[self.field]
        except KeyError as exc:
            raise PatchRejected(f"{self.field} is not a patchable measurement field") from exc


@dataclass
class FieldUpdate:
    """What a single patch actually changed, measured after the fact."""

    field: str
    op: str
    origin: str
    n_new: int
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "op": self.op, "origin": self.origin, "n_new": self.n_new, "detail": self.detail}


@dataclass
class ActionResult:
    """Structured return value of every registered diagnostic action.

    ``status`` is the executor's self-report. :func:`apply_action_result`
    downgrades ``INFORMATIVE`` to ``NO_NEW_INFORMATION`` whenever the applied
    patches turn out to change nothing, so the ledger cannot claim progress that
    did not happen.
    """

    action_id: str
    status: ActionStatus
    summary: str
    observations: dict[str, Any] = field(default_factory=dict)
    patches: list[MeasurementPatch] = field(default_factory=list)
    limitation: str | None = None
    applied: list[FieldUpdate] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    status_reason: str = ""

    @property
    def n_new_measurements(self) -> int:
        return sum(u.n_new for u in self.applied)

    @property
    def learned_something_new(self) -> bool:
        return self.status == ActionStatus.informative

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "summary": self.summary,
            "learned_something_new": self.learned_something_new,
            "n_new_measurements": self.n_new_measurements,
            "updated_measurement_fields": sorted({u.field for u in self.applied if u.n_new}),
            "applied_updates": [u.as_dict() for u in self.applied],
            "limitation": self.limitation,
            "evidence_ids": list(self.evidence_ids),
            "observations": self.observations,
        }


def unavailable(action_id: str, reason: str, observations: dict[str, Any] | None = None) -> ActionResult:
    return ActionResult(
        action_id=action_id,
        status=ActionStatus.unavailable,
        summary=reason,
        observations=observations or {},
        limitation=reason,
        status_reason=reason,
    )


def failed(action_id: str, reason: str, observations: dict[str, Any] | None = None) -> ActionResult:
    return ActionResult(
        action_id=action_id,
        status=ActionStatus.failed,
        summary=f"{action_id} failed: {reason}",
        observations=observations or {},
        limitation=reason,
        status_reason=reason,
    )


def hit_key(hit: GeneSearchHit) -> tuple:
    return (
        hit.query_id,
        hit.contig_id,
        hit.search_kind,
        int(hit.tstart),
        int(hit.tend),
        hit.strand,
        hit.tool,
        hit.domain_name,
    )


def _orthologue_key(rec: OrthologueRecord) -> tuple:
    return (rec.query_id, rec.subject_id, rec.tool)


def _locus_fingerprint(loci: list[LocusEvidence]) -> dict[str, Any]:
    return {
        "n_loci": len(loci),
        "conflicts": sorted({c for le in loci for c in (le.conflicts or [])}),
        "orthologues": sorted({f"{o.query_id}|{o.subject_id}|{round(o.identity, 4)}" for le in loci for o in (le.orthologues or [])}),
        "gene_order": sorted({f"{le.target}|{len(le.gene_order or [])}" for le in loci}),
    }


def _apply_append_hits(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    value = patch.value or []
    if not all(isinstance(h, GeneSearchHit) for h in value):
        raise PatchRejected("hits patch must contain GeneSearchHit objects produced by a deterministic search")
    existing = {hit_key(h) for h in m.hits}
    added: list[GeneSearchHit] = []
    for hit in value:
        key = hit_key(hit)
        if key in existing:
            continue
        existing.add(key)
        m.hits.append(hit)
        added.append(hit)
    return FieldUpdate(
        field="hits",
        op=patch.op,
        origin=patch.origin,
        n_new=len(added),
        detail={
            "n_offered": len(value),
            "n_duplicate": len(value) - len(added),
            "added": [
                {
                    "contig_id": h.contig_id,
                    "search_kind": h.search_kind,
                    "identity": round(h.identity, 4),
                    "query_coverage": round(h.query_coverage, 4),
                    "tstart": h.tstart,
                    "tend": h.tend,
                    "tool": h.tool,
                }
                for h in added[:8]
            ],
        },
    )


def _apply_revise_hit_flags(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    """Correct contig-edge flags on hits already in the measurement state."""
    revisions = patch.value or {}
    by_key = {hit_key(h): h for h in m.hits}
    changed: list[dict[str, Any]] = []
    for key, flags in revisions.items():
        hit = by_key.get(key)
        if hit is None:
            continue
        before = {
            "near_contig_edge": hit.near_contig_edge,
            "possible_edge_truncation": hit.possible_edge_truncation,
            "edge_distance_bp": hit.edge_distance_bp,
        }
        after = {k: flags[k] for k in before if k in flags}
        if all(before[k] == after[k] for k in after):
            continue
        for k, v in after.items():
            setattr(hit, k, v)
        changed.append({"contig_id": hit.contig_id, "tstart": hit.tstart, "before": before, "after": after})
    return FieldUpdate(
        field="hit_edge_flags",
        op=patch.op,
        origin=patch.origin,
        n_new=len(changed),
        detail={"n_inspected": len(revisions), "revised": changed[:8]},
    )


def _apply_merge_dict(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    current: dict = getattr(m, patch.field)
    incoming = patch.value or {}
    if not isinstance(incoming, dict):
        raise PatchRejected(f"{patch.field} patch must be a dict of measured values")
    new_keys = [k for k in incoming if k not in current]
    changed_keys = [k for k in incoming if k in current and current[k] != incoming[k]]
    current.update(incoming)
    return FieldUpdate(
        field=patch.field,
        op=patch.op,
        origin=patch.origin,
        n_new=len(new_keys) + len(changed_keys),
        detail={"new_keys": new_keys[:12], "changed_keys": changed_keys[:12], "n_total": len(current)},
    )


def _apply_replace_dict(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    current: dict = getattr(m, patch.field) or {}
    incoming = patch.value or {}
    if not isinstance(incoming, dict):
        raise PatchRejected(f"{patch.field} patch must be a dict of measured values")
    changed = bool(incoming) and incoming != current
    if changed:
        setattr(m, patch.field, incoming)
    return FieldUpdate(
        field=patch.field,
        op=patch.op,
        origin=patch.origin,
        n_new=1 if changed else 0,
        detail={"keys": sorted(incoming)[:12]},
    )


def _apply_replace_locus_evidence(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    incoming = patch.value or []
    if not all(isinstance(le, LocusEvidence) for le in incoming):
        raise PatchRejected("locus_evidence patch must contain LocusEvidence objects")
    before = _locus_fingerprint(m.locus_evidence or [])
    after = _locus_fingerprint(incoming)
    changed = before != after
    if changed:
        m.locus_evidence = list(incoming)
        placement = {}
        for le in incoming:
            placement = (le.sequence_similarity or {}).get("placement") or {}
            if placement:
                break
        if placement and placement != (m.phylogeny or {}):
            m.phylogeny = placement
    return FieldUpdate(
        field="locus_evidence",
        op=patch.op,
        origin=patch.origin,
        n_new=1 if changed else 0,
        detail={"before": before, "after": after},
    )


def _apply_merge_orthologues(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    incoming = patch.value or []
    if not all(isinstance(rec, OrthologueRecord) for rec in incoming):
        raise PatchRejected("orthologues patch must contain OrthologueRecord objects")
    targets = [le for le in (m.locus_evidence or []) if le.target == m.query_id] or list(m.locus_evidence or [])
    if not targets:
        return FieldUpdate(
            field="orthologues",
            op=patch.op,
            origin=patch.origin,
            n_new=0,
            detail={"reason": "no locus evidence exists to attach orthologues to"},
        )
    added = 0
    for le in targets:
        existing = {_orthologue_key(o) for o in (le.orthologues or [])}
        for rec in incoming:
            if _orthologue_key(rec) in existing:
                continue
            existing.add(_orthologue_key(rec))
            le.orthologues.append(rec)
            added += 1
    return FieldUpdate(
        field="orthologues",
        op=patch.op,
        origin=patch.origin,
        n_new=added,
        detail={"n_offered": len(incoming), "n_loci_updated": len(targets)},
    )


def _apply_replace_family_evidence(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    incoming = patch.value
    before = m.family_evidence
    before_blob = _stable_hash(before.as_dict()) if hasattr(before, "as_dict") else None
    after_blob = _stable_hash(incoming.as_dict()) if hasattr(incoming, "as_dict") else None
    if after_blob is None:
        raise PatchRejected("family_evidence patch must expose as_dict() from the deterministic family validator")
    changed = before_blob != after_blob
    if changed:
        m.family_evidence = incoming
    return FieldUpdate(
        field="family_evidence",
        op=patch.op,
        origin=patch.origin,
        n_new=1 if changed else 0,
        detail={"before_hash": before_blob, "after_hash": after_blob},
    )


def _apply_extend_unique(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    current: list = getattr(m, patch.field) or []
    incoming = [str(v) for v in (patch.value or [])]
    added = [v for v in dict.fromkeys(incoming) if v not in current]
    setattr(m, patch.field, list(current) + added)
    return FieldUpdate(field=patch.field, op=patch.op, origin=patch.origin, n_new=len(added), detail={"added": added[:12]})


def _apply_set_flag(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    incoming = bool(patch.value)
    changed = bool(getattr(m, patch.field)) != incoming
    if changed:
        setattr(m, patch.field, incoming)
    return FieldUpdate(field=patch.field, op=patch.op, origin=patch.origin, n_new=1 if changed else 0, detail={"value": incoming})


def _apply_set_scalar(m: TargetMeasurements, patch: MeasurementPatch) -> FieldUpdate:
    incoming = patch.value
    changed = incoming is not None and getattr(m, patch.field) != incoming
    if changed:
        setattr(m, patch.field, incoming)
    return FieldUpdate(field=patch.field, op=patch.op, origin=patch.origin, n_new=1 if changed else 0, detail={"value": incoming})


_APPLIERS = {
    "append_hits": _apply_append_hits,
    "revise_hit_flags": _apply_revise_hit_flags,
    "merge_dict": _apply_merge_dict,
    "replace_dict": _apply_replace_dict,
    "set_scalar": _apply_set_scalar,
    "replace_locus_evidence": _apply_replace_locus_evidence,
    "merge_orthologues": _apply_merge_orthologues,
    "replace_family_evidence": _apply_replace_family_evidence,
    "extend_unique": _apply_extend_unique,
    "set_flag": _apply_set_flag,
}


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def measurement_fingerprint(m: TargetMeasurements) -> dict[str, Any]:
    """Canonical summary of the measured state the validator will read.

    Comparing fingerprints across the loop is what proves a diagnostic action
    actually changed what the final validator sees.
    """
    fam = m.family_evidence
    summary = {
        "query_id": m.query_id,
        "hits": sorted(f"{h.contig_id}|{h.search_kind}|{h.tstart}|{h.tend}|{round(h.identity, 4)}|{round(h.query_coverage, 4)}|{h.tool}" for h in m.hits),
        "hit_edge_flags": sorted(f"{h.contig_id}|{h.tstart}|{int(h.near_contig_edge)}|{int(h.possible_edge_truncation)}|{h.edge_distance_bp}" for h in m.hits),
        "coverage_by_hit": {k: sorted(v) if isinstance(v, dict) else v for k, v in sorted((m.coverage_by_hit or {}).items())},
        "neighborhood_keys": sorted(m.neighborhood_by_hit or {}),
        "contig_taxonomy_keys": sorted(m.contig_taxonomy or {}),
        "break_evidence_keys": sorted(m.break_evidence or {}),
        "contig_gc": {k: round(float(v), 5) for k, v in sorted((m.contig_gc or {}).items())},
        "genome_gc": None if m.genome_gc is None else round(float(m.genome_gc), 5),
        "measured_taxonomy": m.measured_taxonomy,
        "phylogeny": sorted(m.phylogeny or {}),
        "locus_evidence": _locus_fingerprint(m.locus_evidence or []),
        "family_evidence": (fam.as_dict() if hasattr(fam, "as_dict") else None),
        "tools_run": sorted(m.tools_run or []),
        "tools_unavailable": sorted(m.tools_unavailable or []),
        "availability": {
            "depth": m.depth_available,
            "annotation": m.annotation_available,
            "proteins": m.proteins_available,
            "mapping": m.mapping_available,
        },
    }
    return {"hash": _stable_hash(summary), "n_hits": len(m.hits), "n_loci": len(m.locus_evidence or []), "n_coverage": len(m.coverage_by_hit or {})}


_HIT_DEPENDENT_FIELDS = frozenset({"hits", "hit_edge_flags"})


def apply_action_result(m: TargetMeasurements, result: ActionResult, *, settings: Settings | None = None) -> ActionResult:
    """Apply an action's deterministic patches to ``TargetMeasurements`` in place.

    Returns the same ``ActionResult`` with ``applied`` populated and ``status``
    reconciled against what the patches genuinely changed.

    If the applied patches change ``hits``, every deterministic field that is a
    function of the hit set is regenerated before this function returns. The LLM
    never authors those derived values.
    """
    if result.status in {ActionStatus.unavailable, ActionStatus.failed}:
        if result.patches:
            raise PatchRejected(f"{result.action_id} reported {result.status.value} but still offered measurement patches")
        return result
    for patch in result.patches:
        op = patch.op  # raises PatchRejected for any field outside the whitelist
        if patch.origin not in DETERMINISTIC_ORIGINS:
            raise PatchRejected(
                f"{result.action_id} offered a patch to '{patch.field}' from unregistered origin '{patch.origin}'; "
                "measurement values may only come from deterministic instruments"
            )
        target_field = _VIRTUAL_TARGETS.get(patch.field, patch.field)
        if not hasattr(m, target_field):
            raise PatchRejected(f"TargetMeasurements has no field '{target_field}'")
        result.applied.append(_APPLIERS[op](m, patch))
    hits_changed = any(u.field in _HIT_DEPENDENT_FIELDS and u.n_new for u in result.applied)
    if hits_changed:
        from genome_skeptic.agents.derived_state import assert_hits_derived_consistent, recompute_derived_measurements

        cfg = settings or Settings()
        result.applied.extend(recompute_derived_measurements(m, cfg))
        assert_hits_derived_consistent(m, cfg)
    if result.n_new_measurements == 0:
        result.status = ActionStatus.no_new_information
        if not result.status_reason:
            result.status_reason = (
                "the action executed but every value it produced was already present in TargetMeasurements"
            )
    else:
        result.status = ActionStatus.informative
        if not result.status_reason:
            changed = sorted({u.field for u in result.applied if u.n_new})
            result.status_reason = f"updated measurement fields: {', '.join(changed)}"
    return result
