from __future__ import annotations

from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit, TargetType


FORBIDDEN_ABSENCE_PHRASES = (
    "absent from organism",
    "absent from the organism",
    "gene is absent",
    "not present in the organism",
    "true absence",
)


def claim_id_for_query(query_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in query_id)
    return f"C_target_{safe}"


def query_span_coverage(hits: list[GeneSearchHit], query_length: int) -> float:
    if query_length <= 0 or not hits:
        return 0.0
    covered = [False] * query_length
    for hit in hits:
        for i in range(max(0, hit.qstart), min(query_length, hit.qend)):
            covered[i] = True
    return sum(covered) / query_length


def _truncated(hit: GeneSearchHit) -> bool:
    return bool(hit.possible_edge_truncation and hit.query_coverage < 0.95)


def strong_hit(hit: GeneSearchHit, settings: Settings, target_type: TargetType | None = None) -> bool:
    t = settings.thresholds
    if hit.search_kind == "domain":
        return False
    if _truncated(hit):
        return False
    if target_type == TargetType.exact_allele:
        if hit.search_kind != "nucleotide":
            return False
        return hit.identity >= t.allele_min_identity and hit.query_coverage >= t.allele_min_query_coverage
    if target_type == TargetType.gene_orthologue:
        if hit.search_kind == "nucleotide":
            return False
        return hit.identity >= t.gene_aa_min_identity and hit.query_coverage >= t.gene_aa_min_query_coverage
    if target_type == TargetType.protein_family:
        if hit.search_kind not in {"translated", "protein"}:
            return False
        return hit.identity >= t.gene_aa_min_identity and hit.query_coverage >= t.gene_aa_min_query_coverage
    if hit.search_kind == "nucleotide":
        return hit.identity >= t.gene_nt_min_identity and hit.query_coverage >= t.gene_nt_min_query_coverage
    return hit.identity >= t.gene_aa_min_identity and hit.query_coverage >= t.gene_aa_min_query_coverage


def partial_hit(hit: GeneSearchHit, settings: Settings, target_type: TargetType | None = None) -> bool:
    t = settings.thresholds
    if strong_hit(hit, settings, target_type):
        return False
    if hit.search_kind == "nucleotide":
        return hit.alignment_length >= t.gene_partial_min_nt_bp
    return hit.alignment_length >= t.gene_partial_min_aa * 3


def homology_support_score(hits: list[GeneSearchHit], settings: Settings, target_type: TargetType | None = None) -> dict:
    """Deterministic homology quality in [0, 1]. Completeness is computed separately."""
    nt = [h for h in hits if h.search_kind == "nucleotide"]
    aa = [h for h in hits if h.search_kind == "translated"]
    prot = [h for h in hits if h.search_kind == "protein"]
    domain = [h for h in hits if h.search_kind == "domain"]
    non_domain = nt + aa + prot

    def _best(rows: list[GeneSearchHit]) -> GeneSearchHit | None:
        return max(rows, key=lambda h: h.identity * h.query_coverage) if rows else None

    best_nt = _best(nt)
    best_aa = _best(aa)
    best_prot = _best(prot)
    best_any = _best(non_domain)

    def _span(h: GeneSearchHit | None) -> float:
        if h is None:
            return 0.0
        span = max(0.0, min(1.0, h.identity * h.query_coverage))
        if _truncated(h):
            span *= 0.7
        if h.near_contig_edge and h.query_coverage < 0.95:
            span *= 0.85
        return span

    score = 0.0
    modes = 0
    if best_nt:
        span = _span(best_nt)
        score = max(score, 0.55 * span)
        if strong_hit(best_nt, settings, target_type):
            score = max(score, 0.55 + 0.40 * span)
            modes += 1
    if best_aa:
        span = _span(best_aa)
        score = max(score, 0.65 * span)
        if strong_hit(best_aa, settings, target_type):
            score = max(score, 0.60 + 0.35 * span)
            modes += 1
    if best_prot:
        span = _span(best_prot)
        score = max(score, 0.70 * span)
        if strong_hit(best_prot, settings, target_type):
            score = max(score, 0.62 + 0.33 * span)
            modes += 1
    if modes >= 2:
        score = min(1.0, score + 0.08)
    if not non_domain and domain:
        score = min(score, 0.28)
    elif domain and not any(strong_hit(h, settings, target_type) for h in non_domain):
        score = min(max(score, 0.20 * _span(_best(domain))), 0.35)
    if best_any and best_any.query_coverage < 0.50:
        score = min(score, 0.45)
    if best_any and best_any.subject_coverage is not None and best_any.subject_coverage < 0.40 and best_any.search_kind in {"protein", "translated"}:
        score = min(score, 0.50)
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 4),
        "best_nucleotide": best_nt.model_dump() if best_nt else None,
        "best_translated": best_aa.model_dump() if best_aa else None,
        "best_protein": best_prot.model_dump() if best_prot else None,
        "n_strong": sum(1 for h in non_domain if strong_hit(h, settings, target_type)),
        "n_partial": sum(1 for h in hits if partial_hit(h, settings, target_type)),
        "n_modes_strong": modes,
        "full_length": bool(best_any and best_any.query_coverage >= 0.80 and not _truncated(best_any)),
        "domain_only": bool(domain and not non_domain),
    }
