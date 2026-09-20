from __future__ import annotations

from genome_skeptic.config import Settings
from genome_skeptic.models import OrthologueRecord
from genome_skeptic.tools.gene_search import search_proteins


def _best_by_query(hits) -> dict[str, object]:
    best: dict[str, object] = {}
    for hit in hits:
        key = hit.query_id
        prev = best.get(key)
        score = hit.identity * hit.query_coverage
        if prev is None or score > prev.identity * prev.query_coverage:  # type: ignore[union-attr]
            best[key] = hit
    return best


def reciprocal_best_hits(
    query_proteins: list[tuple[str, str]],
    ref_proteins: list[tuple[str, str]],
    settings: Settings,
    tool_hits: list | None = None,
) -> list[OrthologueRecord]:
    """Deterministic RBH. Never invents identity, coverage, or reciprocal calls."""
    forward = []
    reverse = []
    if tool_hits:
        forward = list(tool_hits)
    if query_proteins and ref_proteins:
        for qid, qseq in query_proteins:
            if qseq:
                forward.extend(search_proteins(qid, qseq, ref_proteins, settings))
        for rid, rseq in ref_proteins:
            if rseq:
                reverse.extend(search_proteins(rid, rseq, query_proteins, settings))
    fwd_best = _best_by_query(forward)
    rev_best = _best_by_query(reverse)
    records: list[OrthologueRecord] = []
    for qid, hit in fwd_best.items():
        rev = rev_best.get(hit.contig_id)
        rbh = bool(rev and rev.contig_id == qid)
        tlen = len(dict(ref_proteins).get(hit.contig_id, "")) or None
        scov = None
        if tlen:
            scov = abs(hit.tend - hit.tstart) / tlen
        records.append(OrthologueRecord(
            query_id=qid,
            subject_id=hit.contig_id,
            identity=hit.identity,
            query_coverage=hit.query_coverage,
            subject_coverage=scov,
            evalue=hit.evalue,
            reciprocal_best_hit=rbh if reverse else None,
            tool=hit.tool,
            orientation=hit.strand,
        ))
    return records


def classify_orthology(records: list[OrthologueRecord], settings: Settings) -> tuple[str, list[str]]:
    t = settings.thresholds
    strong = [
        r for r in records
        if r.identity >= t.orthologue_min_identity and r.query_coverage >= t.orthologue_min_coverage
    ]
    conflicts: list[str] = []
    if not strong:
        return "unassigned", ["no_strong_reference_hit"]
    subjects = [r.subject_id for r in strong]
    if len(set(subjects)) == 1 and len(strong) >= 2:
        conflicts.append("paralogous_copies")
        return "paralog", conflicts
    best = max(strong, key=lambda r: r.identity * r.query_coverage)
    if best.reciprocal_best_hit is False:
        conflicts.append("not_reciprocal_best_hit")
        return "paralog_or_xenolog", conflicts
    if best.reciprocal_best_hit is True:
        return "ortholog", conflicts
    return "putative_homolog", conflicts
