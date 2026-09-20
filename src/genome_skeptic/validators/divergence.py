"""Query-relative divergence vs the trusted family-member identity distribution.

Not a species rule. Detection polarity is not changed by this label.
"""
from __future__ import annotations

from statistics import median

from genome_skeptic.config import Settings
from genome_skeptic.models import TargetFamily
from genome_skeptic.tools.gene_search import search_proteins


def _identity(a: str, b: str, settings: Settings) -> float | None:
    if not a or not b:
        return None
    hits = search_proteins("query", a, [("member", b)], settings)
    if not hits:
        return None
    return hits[0].identity


def family_identity_distribution(family: TargetFamily, query_aa: str, settings: Settings) -> dict:
    ids: list[float] = []
    by_member: dict[str, float] = {}
    for member in family.members:
        pid = _identity(query_aa, member.sequence, settings)
        if pid is None:
            continue
        ids.append(pid)
        by_member[member.protein_id] = pid
    close = [x for x in ids if x >= 0.90]
    other = [x for x in ids if x < 0.90]
    split = None
    if other:
        med_close = median(close) if close else 1.0
        med_other = median(other)
        split = (med_close + med_other) / 2
    return {
        "n_members_scored": len(ids),
        "identities_vs_query": by_member,
        "median_close": median(close) if close else None,
        "median_other": median(other) if other else None,
        "split": None if split is None else round(split, 4),
        "min_other": min(other) if other else None,
        "max_other": max(other) if other else None,
    }


def is_divergent_full_length(candidate_query_identity: float | None, distribution: dict) -> bool:
    if candidate_query_identity is None:
        return False
    split = distribution.get("split")
    if split is None:
        return False
    return candidate_query_identity < split
