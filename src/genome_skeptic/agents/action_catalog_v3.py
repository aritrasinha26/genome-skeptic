"""V3 action metadata: diagnostic needs, ranking, and an active (non-inert) catalog.

Frozen V2 ``action_catalog.py`` is not modified. Inert actions remain registered
for audit but are excluded from planner/critic selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genome_skeptic.agents.action_catalog import BY_ID, CATALOG, AgenticActionSpec
from genome_skeptic.agents.diagnostic_needs import (
    ASSEMBLY_SUPPORT_UNRESOLVED,
    CONTAMINATION_UNRESOLVED,
    COPY_NUMBER_UNRESOLVED,
    DIAGNOSTIC_NEEDS,
    FAMILY_IDENTITY_UNRESOLVED,
    FRAGMENTATION_UNRESOLVED,
    NEED_PRIORITY,
    ORTHOLOG_VS_PARALOG_UNRESOLVED,
    REMOTE_HOMOLOG_NOT_EXCLUDED,
)
from genome_skeptic.validators.falsification import TargetMeasurements

# Fields the deterministic validator actually reads when forming the claim.
VALIDATOR_CONSUMED_FIELDS: frozenset[str] = frozenset(
    {
        "hits",
        "hit_edge_flags",
        "family_evidence",
        "locus_evidence",
        "orthologues",
        "coverage_by_hit",
        "contig_gc",
        "genome_gc",
        "contig_taxonomy",
        "break_evidence",
        "phylogeny",
    }
)

# Actions that cannot alter a scientific field or produce genuinely new evidence.
INERT_ACTION_IDS: frozenset[str] = frozenset(
    {
        "inspect_paralogue_copies",  # restates _loci(hits); validator already clusters
        "inspect_catalytic_residues",  # reports the profile pattern without testing the candidate
    }
)

_COST_RANK = {"cheap": 1, "moderate": 2, "expensive": 3}

# Dedicated live instruments per DiagnosticNeed. Ranking must not drop the first
# executable entry for a current need; homology search scoring must not hide
# competitive_family when curated competing families exist.
NEED_PRIMARY_ACTIONS: dict[str, tuple[str, ...]] = {
    REMOTE_HOMOLOG_NOT_EXCLUDED: (
        "search_target_domains_hmmer",
        "search_target_proteins_mmseqs",
        "search_target_proteins_diamond",
        "search_target_genes_translated",
        "search_target_genes_nucleotide",
    ),
    COPY_NUMBER_UNRESOLVED: (
        "search_target_domains_hmmer",
        "search_target_proteins_mmseqs",
        "search_target_proteins_diamond",
    ),
    FAMILY_IDENTITY_UNRESOLVED: (
        "competitive_family",
        "search_target_domains_hmmer",
        "place_target_among_homologues",
        "compare_locus_to_reference",
    ),
    ORTHOLOG_VS_PARALOG_UNRESOLVED: (
        "reciprocal_best_hit_search",
        "compare_locus_to_reference",
        "inspect_gene_order_against_reference",
        "inspect_synteny_neighborhood_for_target",
        "place_target_among_homologues",
    ),
    FRAGMENTATION_UNRESOLVED: (
        "inspect_contig_edges_for_target",
        "inspect_read_supported_breaks",
    ),
    CONTAMINATION_UNRESOLVED: (
        "inspect_hit_contig_contamination",
        "classify_contig_taxonomy",
    ),
    ASSEMBLY_SUPPORT_UNRESOLVED: (
        "inspect_read_supported_breaks",
        "inspect_local_coverage_for_target",
    ),
}

_TESTS: dict[str, tuple[str, ...]] = {
    "search_target_genes_nucleotide": (REMOTE_HOMOLOG_NOT_EXCLUDED,),
    "search_target_genes_translated": (REMOTE_HOMOLOG_NOT_EXCLUDED,),
    "inspect_contig_edges_for_target": (FRAGMENTATION_UNRESOLVED,),
    "inspect_local_coverage_for_target": (ASSEMBLY_SUPPORT_UNRESOLVED, CONTAMINATION_UNRESOLVED),
    "inspect_synteny_neighborhood_for_target": (ORTHOLOG_VS_PARALOG_UNRESOLVED, FAMILY_IDENTITY_UNRESOLVED),
    "compare_locus_to_reference": (FAMILY_IDENTITY_UNRESOLVED, ORTHOLOG_VS_PARALOG_UNRESOLVED),
    "reciprocal_best_hit_search": (ORTHOLOG_VS_PARALOG_UNRESOLVED,),
    "inspect_gene_order_against_reference": (ORTHOLOG_VS_PARALOG_UNRESOLVED, FAMILY_IDENTITY_UNRESOLVED),
    "search_target_proteins_mmseqs": (REMOTE_HOMOLOG_NOT_EXCLUDED, COPY_NUMBER_UNRESOLVED),
    "search_target_proteins_diamond": (REMOTE_HOMOLOG_NOT_EXCLUDED, COPY_NUMBER_UNRESOLVED),
    "search_target_domains_hmmer": (
        REMOTE_HOMOLOG_NOT_EXCLUDED,
        FAMILY_IDENTITY_UNRESOLVED,
        COPY_NUMBER_UNRESOLVED,
    ),
    "competitive_family": (FAMILY_IDENTITY_UNRESOLVED,),
    "inspect_hit_contig_contamination": (CONTAMINATION_UNRESOLVED,),
    "classify_contig_taxonomy": (CONTAMINATION_UNRESOLVED,),
    "inspect_read_supported_breaks": (FRAGMENTATION_UNRESOLVED, ASSEMBLY_SUPPORT_UNRESOLVED),
    "place_target_among_homologues": (FAMILY_IDENTITY_UNRESOLVED, ORTHOLOG_VS_PARALOG_UNRESOLVED),
}


@dataclass(frozen=True)
class V3ActionMeta:
    action_id: str
    tests: tuple[str, ...]
    requires: tuple[str, ...]
    updates: tuple[str, ...]
    novel_if: str
    relative_cost: int
    spec: AgenticActionSpec

    def validator_consumed(self) -> bool:
        return any(field in VALIDATOR_CONSUMED_FIELDS for field in self.updates)

    def as_planner_row(self, matched_needs: list[str], score: int) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "tests": list(self.tests),
            "matched_needs": matched_needs,
            "updates": list(self.updates),
            "relative_cost": self.relative_cost,
            "priority_score": score,
        }


def _meta_for(spec: AgenticActionSpec) -> V3ActionMeta:
    return V3ActionMeta(
        action_id=spec.action_id,
        tests=_TESTS.get(spec.action_id, ()),
        requires=spec.requires,
        updates=spec.updates_measurement_fields,
        novel_if=spec.informative_when,
        relative_cost=_COST_RANK.get(spec.cost_class, 2),
        spec=spec,
    )


V3_META: dict[str, V3ActionMeta] = {
    spec.action_id: _meta_for(spec) for spec in CATALOG if spec.action_id not in INERT_ACTION_IDS
}

ACTIVE_ACTION_IDS: tuple[str, ...] = tuple(V3_META)


def is_active(action_id: str) -> bool:
    return action_id in V3_META


def _eligible(
    meta: V3ActionMeta,
    capabilities: dict[str, bool],
    performed: frozenset[str],
    measurements: TargetMeasurements | None,
    *,
    edge_bp: int,
    banned: set[str],
    needs: list[str],
) -> list[str] | None:
    if meta.action_id in banned:
        return None
    if not meta.updates or not meta.validator_consumed():
        return None
    if not meta.spec.can_change_state_now(capabilities, performed, measurements, edge_bp=edge_bp):
        return None
    matched = [n for n in meta.tests if n in needs]
    return matched or None


def _collect_eligible(
    needs: list[str],
    capabilities: dict[str, bool],
    performed: frozenset[str],
    measurements: TargetMeasurements | None,
    *,
    edge_bp: int,
    banned: set[str],
) -> list[tuple[V3ActionMeta, list[str]]]:
    eligible: list[tuple[V3ActionMeta, list[str]]] = []
    for meta in V3_META.values():
        matched = _eligible(
            meta, capabilities, performed, measurements, edge_bp=edge_bp, banned=banned, needs=needs
        )
        if matched:
            eligible.append((meta, matched))
    return eligible


def _priority_score(
    meta: V3ActionMeta,
    matched: list[str],
    *,
    unique_needs: set[str],
    novel: bool,
) -> int:
    need_term = sum(NEED_PRIORITY.get(n, 0) for n in matched) * 20
    unique_term = 50 * sum(1 for n in matched if n in unique_needs)
    validator_term = 30 if meta.validator_consumed() else 0
    novelty_term = 15 if novel else 0
    return need_term + unique_term + validator_term + novelty_term + 10 - meta.relative_cost


def executable_actions_before_ranking(
    needs: list[str],
    capabilities: dict[str, bool],
    performed: frozenset[str],
    measurements: TargetMeasurements | None,
    *,
    edge_bp: int = 300,
    already_run: list[str] | None = None,
) -> list[dict[str, Any]]:
    """All live, need-matching actions before score truncation."""
    banned = set(already_run or [])
    rows: list[dict[str, Any]] = []
    for meta, matched in _collect_eligible(
        needs, capabilities, performed, measurements, edge_bp=edge_bp, banned=banned
    ):
        rows.append(
            {
                "action_id": meta.action_id,
                "tests": list(meta.tests),
                "matched_needs": matched,
                "updates": list(meta.updates),
                "relative_cost": meta.relative_cost,
            }
        )
    rows.sort(key=lambda row: (row["action_id"]))
    return rows


def live_actions_for_need(
    need: str,
    capabilities: dict[str, bool],
    performed: frozenset[str],
    measurements: TargetMeasurements | None,
    *,
    edge_bp: int = 300,
) -> list[str]:
    """Registered active actions that are live for one DiagnosticNeed."""
    if need not in DIAGNOSTIC_NEEDS:
        return []
    rows = executable_actions_before_ranking(
        [need], capabilities, performed, measurements, edge_bp=edge_bp
    )
    return [row["action_id"] for row in rows]


def rank_candidate_actions(
    needs: list[str],
    capabilities: dict[str, bool],
    performed: frozenset[str],
    measurements: TargetMeasurements | None,
    *,
    edge_bp: int = 300,
    already_run: list[str] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Expose the dedicated live instrument for each current need, then fill by score.

    Homology-search score must not hide ``competitive_family`` when that action is
    live for ``FAMILY_IDENTITY_UNRESOLVED``. Extra slots are filled up to ``limit``.
    """
    banned = set(already_run or [])
    eligible = _collect_eligible(
        needs, capabilities, performed, measurements, edge_bp=edge_bp, banned=banned
    )
    by_id = {meta.action_id: (meta, matched) for meta, matched in eligible}
    cover_counts: dict[str, int] = {}
    for _meta, matched in eligible:
        for need in matched:
            cover_counts[need] = cover_counts.get(need, 0) + 1
    unique_needs = {need for need, n in cover_counts.items() if n == 1}
    scored: dict[str, tuple[int, V3ActionMeta, list[str]]] = {}
    for meta, matched in eligible:
        novel = not meta.spec.is_inert(performed, measurements, edge_bp=edge_bp)
        score = _priority_score(meta, matched, unique_needs=unique_needs, novel=novel)
        scored[meta.action_id] = (score, meta, matched)

    must_ids: list[str] = []
    for need in needs:
        for action_id in NEED_PRIMARY_ACTIONS.get(need, ()):
            if action_id in by_id and action_id not in must_ids:
                must_ids.append(action_id)
                break

    rest = [
        action_id
        for action_id, _row in sorted(
            scored.items(), key=lambda item: (-item[1][0], item[1][1].relative_cost, item[1][1].action_id)
        )
        if action_id not in must_ids
    ]
    ordered = list(must_ids)
    fill_slots = max(0, limit - len(ordered))
    ordered.extend(rest[:fill_slots])
    return [
        scored[action_id][1].as_planner_row(scored[action_id][2], scored[action_id][0])
        for action_id in ordered
        if action_id in scored
    ]


def remaining_relevant_actions(
    needs: list[str],
    capabilities: dict[str, bool],
    performed: frozenset[str],
    measurements: TargetMeasurements | None,
    *,
    edge_bp: int = 300,
    already_run: list[str] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    return rank_candidate_actions(
        needs,
        capabilities,
        performed,
        measurements,
        edge_bp=edge_bp,
        already_run=already_run,
        limit=limit,
    )
