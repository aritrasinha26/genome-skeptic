"""V4-dev action ranking: DECISION_RELEVANCE.

An action that directly resolves the current endpoint-defining uncertainty
outranks an action that only accumulates supporting evidence.

V3 ranking is not modified. No accession, gene, or truth labels are used.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genome_skeptic.agents.action_catalog import CATALOG, AgenticActionSpec
from genome_skeptic.agents.action_catalog_v3 import (
    INERT_ACTION_IDS,
    VALIDATOR_CONSUMED_FIELDS,
    _COST_RANK,
    is_active,
)
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

NOVELTY_DISCRIMINATING = "discriminating"
NOVELTY_SUPPORTING = "supporting_evidence"

# Needs this action directly settles (endpoint-defining), not merely supports.
_ENDPOINT_RELEVANCE: dict[str, tuple[str, ...]] = {
    "search_target_genes_nucleotide": (REMOTE_HOMOLOG_NOT_EXCLUDED,),
    "search_target_genes_translated": (REMOTE_HOMOLOG_NOT_EXCLUDED,),
    "inspect_contig_edges_for_target": (FRAGMENTATION_UNRESOLVED,),
    "inspect_local_coverage_for_target": (ASSEMBLY_SUPPORT_UNRESOLVED,),
    "inspect_synteny_neighborhood_for_target": (ORTHOLOG_VS_PARALOG_UNRESOLVED,),
    "compare_locus_to_reference": (ORTHOLOG_VS_PARALOG_UNRESOLVED, FAMILY_IDENTITY_UNRESOLVED),
    "reciprocal_best_hit_search": (ORTHOLOG_VS_PARALOG_UNRESOLVED,),
    "inspect_gene_order_against_reference": (ORTHOLOG_VS_PARALOG_UNRESOLVED,),
    "search_target_proteins_mmseqs": (REMOTE_HOMOLOG_NOT_EXCLUDED, COPY_NUMBER_UNRESOLVED),
    "search_target_proteins_diamond": (REMOTE_HOMOLOG_NOT_EXCLUDED, COPY_NUMBER_UNRESOLVED),
    "search_target_domains_hmmer": (REMOTE_HOMOLOG_NOT_EXCLUDED, COPY_NUMBER_UNRESOLVED),
    "competitive_family": (FAMILY_IDENTITY_UNRESOLVED,),
    "inspect_hit_contig_contamination": (CONTAMINATION_UNRESOLVED,),
    "classify_contig_taxonomy": (CONTAMINATION_UNRESOLVED,),
    "inspect_read_supported_breaks": (FRAGMENTATION_UNRESOLVED, ASSEMBLY_SUPPORT_UNRESOLVED),
    "place_target_among_homologues": (ORTHOLOG_VS_PARALOG_UNRESOLVED, FAMILY_IDENTITY_UNRESOLVED),
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

# Endpoint-defining questions outrank generic additional homology search.
DECISION_NEED_RANK: dict[str, int] = {
    FAMILY_IDENTITY_UNRESOLVED: 100,
    COPY_NUMBER_UNRESOLVED: 90,
    ORTHOLOG_VS_PARALOG_UNRESOLVED: 80,
    FRAGMENTATION_UNRESOLVED: 50,
    ASSEMBLY_SUPPORT_UNRESOLVED: 40,
    CONTAMINATION_UNRESOLVED: 30,
    REMOTE_HOMOLOG_NOT_EXCLUDED: 20,
}


def _need_rank(need: str) -> int:
    return DECISION_NEED_RANK.get(need, NEED_PRIORITY.get(need, 0))


# Dedicated live instrument per current need, used only to guarantee coverage.
NEED_PRIMARY_ACTIONS: dict[str, tuple[str, ...]] = {
    FAMILY_IDENTITY_UNRESOLVED: ("competitive_family", "place_target_among_homologues", "compare_locus_to_reference"),
    COPY_NUMBER_UNRESOLVED: (
        "search_target_proteins_mmseqs",
        "search_target_proteins_diamond",
        "search_target_domains_hmmer",
    ),
    ORTHOLOG_VS_PARALOG_UNRESOLVED: (
        "reciprocal_best_hit_search",
        "compare_locus_to_reference",
        "inspect_gene_order_against_reference",
        "inspect_synteny_neighborhood_for_target",
        "place_target_among_homologues",
    ),
    REMOTE_HOMOLOG_NOT_EXCLUDED: (
        "search_target_domains_hmmer",
        "search_target_proteins_mmseqs",
        "search_target_proteins_diamond",
        "search_target_genes_translated",
        "search_target_genes_nucleotide",
    ),
    FRAGMENTATION_UNRESOLVED: ("inspect_contig_edges_for_target", "inspect_read_supported_breaks"),
    CONTAMINATION_UNRESOLVED: ("inspect_hit_contig_contamination", "classify_contig_taxonomy"),
    ASSEMBLY_SUPPORT_UNRESOLVED: ("inspect_read_supported_breaks", "inspect_local_coverage_for_target"),
}


@dataclass(frozen=True)
class V4ActionMeta:
    action_id: str
    tests: tuple[str, ...]
    requires: tuple[str, ...]
    updates: tuple[str, ...]
    novel_if: str
    relative_cost: int
    endpoint_relevance: tuple[str, ...]
    expected_novelty: str
    spec: AgenticActionSpec

    def validator_consumed(self) -> bool:
        return any(field in VALIDATOR_CONSUMED_FIELDS for field in self.updates)

    def novelty_for(self, need: str) -> str:
        if need in self.endpoint_relevance:
            return NOVELTY_DISCRIMINATING
        return NOVELTY_SUPPORTING

    def as_planner_row(self, matched_needs: list[str], score: int) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "tests": list(self.tests),
            "matched_needs": matched_needs,
            "updates": list(self.updates),
            "relative_cost": self.relative_cost,
            "endpoint_relevance": list(self.endpoint_relevance),
            "expected_novelty": self.expected_novelty,
            "decision_relevance": {
                need: self.novelty_for(need) for need in matched_needs
            },
            "priority_score": score,
        }


def _meta_for(spec: AgenticActionSpec) -> V4ActionMeta:
    endpoint = _ENDPOINT_RELEVANCE.get(spec.action_id, ())
    return V4ActionMeta(
        action_id=spec.action_id,
        tests=_TESTS.get(spec.action_id, ()),
        requires=spec.requires,
        updates=spec.updates_measurement_fields,
        novel_if=spec.informative_when,
        relative_cost=_COST_RANK.get(spec.cost_class, 2),
        endpoint_relevance=endpoint,
        expected_novelty=NOVELTY_DISCRIMINATING if endpoint else NOVELTY_SUPPORTING,
        spec=spec,
    )


V4_META: dict[str, V4ActionMeta] = {
    spec.action_id: _meta_for(spec) for spec in CATALOG if spec.action_id not in INERT_ACTION_IDS
}

ACTIVE_ACTION_IDS: tuple[str, ...] = tuple(V4_META)


def _eligible(
    meta: V4ActionMeta,
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
) -> list[tuple[V4ActionMeta, list[str]]]:
    eligible: list[tuple[V4ActionMeta, list[str]]] = []
    for meta in V4_META.values():
        matched = _eligible(
            meta, capabilities, performed, measurements, edge_bp=edge_bp, banned=banned, needs=needs
        )
        if matched:
            eligible.append((meta, matched))
    return eligible


def _priority_score(
    meta: V4ActionMeta,
    matched: list[str],
    *,
    unique_needs: set[str],
    novel: bool,
    needs: list[str],
) -> int:
    need_term = sum(NEED_PRIORITY.get(n, 0) for n in matched) * 20
    unique_term = 50 * sum(1 for n in matched if n in unique_needs)
    validator_term = 30 if meta.validator_consumed() else 0
    novelty_term = 15 if novel else 0
    # DECISION_RELEVANCE: directly resolving the current endpoint outranks
    # additional supporting evidence for that same endpoint.
    discriminating = [n for n in matched if n in meta.endpoint_relevance]
    supporting_only = [n for n in matched if n not in meta.endpoint_relevance]
    relevance_term = 0
    if needs:
        top_need = max(needs, key=lambda n: (_need_rank(n), NEED_PRIORITY.get(n, 0)))
        if top_need in discriminating:
            relevance_term += 220
        elif top_need in supporting_only:
            relevance_term -= 40
    relevance_term += 80 * len(discriminating)
    relevance_term -= 25 * len(supporting_only)
    return need_term + unique_term + validator_term + novelty_term + relevance_term + 10 - meta.relative_cost


def executable_actions_before_ranking(
    needs: list[str],
    capabilities: dict[str, bool],
    performed: frozenset[str],
    measurements: TargetMeasurements | None,
    *,
    edge_bp: int = 300,
    already_run: list[str] | None = None,
) -> list[dict[str, Any]]:
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
                "endpoint_relevance": list(meta.endpoint_relevance),
                "expected_novelty": meta.expected_novelty,
            }
        )
    rows.sort(key=lambda row: row["action_id"])
    return rows


def live_actions_for_need(
    need: str,
    capabilities: dict[str, bool],
    performed: frozenset[str],
    measurements: TargetMeasurements | None,
    *,
    edge_bp: int = 300,
) -> list[str]:
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
    scored: dict[str, tuple[int, V4ActionMeta, list[str]]] = {}
    for meta, matched in eligible:
        novel = not meta.spec.is_inert(performed, measurements, edge_bp=edge_bp)
        score = _priority_score(meta, matched, unique_needs=unique_needs, novel=novel, needs=needs)
        scored[meta.action_id] = (score, meta, matched)

    must_ids: list[str] = []
    for need in sorted(needs, key=lambda n: (-_need_rank(n), n)):
        for action_id in NEED_PRIMARY_ACTIONS.get(need, ()):
            if action_id in by_id and action_id not in must_ids:
                must_ids.append(action_id)
                break

    rest = [
        action_id
        for action_id, _row in sorted(
            scored.items(),
            key=lambda item: (-item[1][0], item[1][1].relative_cost, item[1][1].action_id),
        )
        if action_id not in must_ids
    ]
    # Discriminating actions for the current highest-priority need stay first.
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


__all__ = [
    "INERT_ACTION_IDS",
    "NOVELTY_DISCRIMINATING",
    "NOVELTY_SUPPORTING",
    "V4_META",
    "VALIDATOR_CONSUMED_FIELDS",
    "executable_actions_before_ranking",
    "is_active",
    "live_actions_for_need",
    "rank_candidate_actions",
    "remaining_relevant_actions",
]
