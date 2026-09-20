from __future__ import annotations

from genome_skeptic.models import GeneOrderItem
from genome_skeptic.tools.gene_search import parse_gff_features


def genes_from_features(features: list[dict], seqid: str | None = None) -> list[GeneOrderItem]:
    genes: list[GeneOrderItem] = []
    for feat in features:
        if feat.get("type") not in {"cds", "gene"}:
            continue
        if seqid is not None and feat.get("seqid") != seqid:
            continue
        genes.append(GeneOrderItem(
            gene_id=str(feat.get("gene_id") or feat.get("product") or ""),
            product=str(feat.get("product") or feat.get("gene_id") or ""),
            start=int(feat["start"]),
            end=int(feat["end"]),
            strand=str(feat.get("strand") or "+"),
            contig=str(feat.get("seqid") or "") or None,
        ))
    genes.sort(key=lambda g: (g.start, g.end))
    # Prefer CDS over gene when both exist at the same locus.
    kept: list[GeneOrderItem] = []
    for gene in genes:
        if kept and abs(kept[-1].start - gene.start) < 3 and abs(kept[-1].end - gene.end) < 3:
            continue
        kept.append(gene)
    return kept


def genes_from_gff(path: str, seqid: str | None = None) -> list[GeneOrderItem]:
    return genes_from_features(parse_gff_features(path), seqid)


def annotate_target(genes: list[GeneOrderItem], start: int, end: int) -> list[GeneOrderItem]:
    out = []
    for gene in genes:
        item = gene.model_copy()
        item.is_target = not (gene.end <= start or gene.start >= end)
        out.append(item)
    return out


def flanks(genes: list[GeneOrderItem], n: int = 2) -> tuple[list[GeneOrderItem], GeneOrderItem | None, list[GeneOrderItem]]:
    idx = next((i for i, g in enumerate(genes) if g.is_target), None)
    if idx is None:
        return [], None, []
    return genes[max(0, idx - n):idx], genes[idx], genes[idx + 1:idx + 1 + n]


def intergenic_distances(genes: list[GeneOrderItem]) -> dict[str, int | None]:
    up, target, down = flanks(genes, n=1)
    upstream_bp = (target.start - up[-1].end) if target and up else None
    downstream_bp = (down[0].start - target.end) if target and down else None
    return {"upstream_bp": upstream_bp, "downstream_bp": downstream_bp}


def names(items: list[GeneOrderItem]) -> list[str]:
    return [g.product or g.gene_id for g in items]


def compare_neighborhood(
    query_genes: list[GeneOrderItem],
    ref_genes: list[GeneOrderItem],
    flank: int = 2,
    spacing_fold: float = 3.0,
) -> list[str]:
    conflicts: list[str] = []
    q_up, q_t, q_down = flanks(query_genes, flank)
    r_up, r_t, r_down = flanks(ref_genes, flank)
    if q_t and r_t and q_t.strand != r_t.strand:
        conflicts.append("orientation_mismatch")
    if names(q_up) != names(r_up) or names(q_down) != names(r_down):
        if names(q_up)[::-1] == names(r_down) and names(q_down)[::-1] == names(r_up):
            conflicts.append("gene_order_inverted")
        else:
            conflicts.append("gene_order_mismatch")
    if (not names(q_up) and names(r_up)) or (not names(q_down) and names(r_down)):
        conflicts.append("missing_flanking_orthologues")
    q_dist = intergenic_distances(query_genes)
    r_dist = intergenic_distances(ref_genes)
    for side in ("upstream_bp", "downstream_bp"):
        qd, rd = q_dist.get(side), r_dist.get(side)
        if qd is None or rd is None or rd == 0:
            continue
        if qd < 0 or rd < 0:
            conflicts.append("overlapping_neighbors")
            continue
        ratio = max(qd, rd) / max(1, min(qd, rd))
        if ratio > spacing_fold:
            conflicts.append("spacing_outlier")
    return list(dict.fromkeys(conflicts))
