"""Distance-based phylogenetic placement among labeled homologues.

RBH remains the fast first test. This module is used when RBH is missing,
multiple homologues are present, or the call is otherwise ambiguous.

If FastTree is available it is preferred. Otherwise a deterministic
neighbor-joining tree is built from pairwise identities measured by the
homology search. Placement is never invented.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from genome_skeptic.config import Settings
from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command
from genome_skeptic.tools.gene_search import search_proteins


def pairwise_identity(a: str, b: str, settings: Settings) -> float | None:
    if not a or not b:
        return None
    hits = search_proteins("a", a, [("b", b)], settings)
    if not hits:
        return None
    return hits[0].identity


def _neighbor_joining(ids: list[str], dist: list[list[float]]) -> tuple[Any, dict[str, str]]:
    """Return Newick-like nested tuples and a map of leaf -> sister clade key."""
    n = len(ids)
    clusters: list[Any] = list(ids)
    d = [row[:] for row in dist]
    active = list(range(n))

    def r_i(i: int) -> float:
        return sum(d[i][j] for j in active if j != i) / max(1, len(active) - 2)

    while len(active) > 2:
        rs = {i: r_i(i) for i in active}
        best = None
        best_score = None
        for ai, i in enumerate(active):
            for j in active[ai + 1:]:
                score = d[i][j] - rs[i] - rs[j]
                if best_score is None or score < best_score:
                    best_score = score
                    best = (i, j)
        i, j = best  # type: ignore[misc]
        dij = d[i][j]
        li = 0.5 * (dij + rs[i] - rs[j])
        lj = dij - li
        new = (clusters[i], li, clusters[j], lj)
        new_idx = len(clusters)
        clusters.append(new)
        row = []
        for k in range(len(d)):
            if k in {i, j}:
                row.append(0.0)
            else:
                row.append(0.5 * (d[i][k] + d[j][k] - dij))
        for k, val in enumerate(row):
            d[k].append(val)
        d.append(row + [0.0])
        active = [x for x in active if x not in {i, j}] + [new_idx]
    a, b = active
    tree = (clusters[a], d[a][b] / 2, clusters[b], d[a][b] / 2)
    return tree, {}


def _leaves(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    left, _li, right, _lj = node
    return _leaves(left) + _leaves(right)


def _sister_of(tree: Any, query_id: str) -> list[str]:
    def walk(node: Any) -> list[str] | None:
        if isinstance(node, str):
            return [node] if node == query_id else None
        left, _li, right, _lj = node
        if isinstance(left, str) and left == query_id:
            return _leaves(right)
        if isinstance(right, str) and right == query_id:
            return _leaves(left)
        found = walk(left)
        if found is not None:
            if found == [query_id]:
                return _leaves(right)
            return found
        found = walk(right)
        if found is not None:
            if found == [query_id]:
                return _leaves(left)
            return found
        return None
    return walk(tree) or []


def place_query(
    query_id: str,
    query_aa: str,
    homologues: list[dict[str, str]],
    settings: Settings,
) -> dict[str, Any]:
    """Place query among homologues labeled with clade=ortholog|paralog.

    ``homologues`` items: ``{id, sequence, clade}``.
    """
    provenance = {
        "created_by": "deterministic_phylogenetic_placement",
        "notes": "LLM did not invent tree placement, identities, or clades.",
        "method": "identity_neighbor_joining",
    }
    labeled = [h for h in homologues if h.get("sequence") and h.get("id")]
    if not query_aa or len(labeled) < 2:
        return {
            "status": "not_run",
            "clade": None,
            "limitation": "insufficient labeled homologues for placement; placement was not invented",
            "provenance": provenance,
        }
    ids = [query_id] + [h["id"] for h in labeled]
    seqs = {query_id: query_aa, **{h["id"]: h["sequence"] for h in labeled}}
    clades = {h["id"]: h.get("clade") or "unlabeled" for h in labeled}
    n = len(ids)
    dist = [[0.0] * n for _ in range(n)]
    measured = 0
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if j <= i:
                continue
            ident = pairwise_identity(seqs[a], seqs[b], settings)
            if ident is None:
                d = 1.0
            else:
                d = max(0.0, 1.0 - ident)
                measured += 1
            dist[i][j] = dist[j][i] = d
    if measured == 0:
        return {
            "status": "not_run",
            "clade": None,
            "limitation": "no pairwise identities could be measured among homologues",
            "provenance": provenance,
        }
    tree, _ = _neighbor_joining(ids, dist)
    sisters = _sister_of(tree, query_id)
    sister_clades = [clades[s] for s in sisters if s in clades]
    clade = None
    if sister_clades:
        if all(c == "paralog" for c in sister_clades):
            clade = "paralog"
        elif all(c == "ortholog" for c in sister_clades):
            clade = "ortholog"
        else:
            clade = "unresolved"
    return {
        "status": "completed",
        "clade": clade,
        "sisters": sisters,
        "sister_clades": sister_clades,
        "n_homologues": len(labeled),
        "n_identities_measured": measured,
        "provenance": provenance,
    }


def run_fasttree_if_available(fasta: Path, out_dir: Path) -> ToolResult | None:
    if not available("FastTree") and not available("fasttree"):
        return None
    exe = "FastTree" if available("FastTree") else "fasttree"
    tree_path = out_dir / "placement.nwk"
    cmd = [exe, "-lg", str(fasta)]
    result = run_command("fasttree", "target_gene", cmd, out_dir)
    if result.ok and result.stdout_path:
        Path(result.stdout_path).read_text()
        tree_path.write_text(Path(result.stdout_path).read_text())
        result.outputs["tree"] = str(tree_path)
    return result
