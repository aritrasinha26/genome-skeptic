"""Deterministic multi-locus paralogy. Not every duplicate is a paralogue."""
from __future__ import annotations

from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit, LocusSegment


def _parse_orf_id(orf_id: str) -> dict | None:
    try:
        contig_span, strand = orf_id.rsplit(":", 1)
        contig, span = contig_span.rsplit(":", 1)
        start_s, end_s = span.split("-", 1)
        return {"contig_id": contig, "start": int(start_s), "end": int(end_s), "strand": strand, "orf_id": orf_id}
    except ValueError:
        return None


def _union_hmm_coverage(segs: list[LocusSegment], model_length: int) -> float:
    if model_length <= 0 or not segs:
        return 0.0
    covered = [False] * (model_length + 1)
    for s in segs:
        a = max(1, int(s.hmm_from or 0))
        b = min(model_length, int(s.hmm_to or 0))
        for i in range(a, b + 1):
            covered[i] = True
    return sum(covered[1:]) / model_length


def _hmm_iou(a: LocusSegment, b: LocusSegment) -> float:
    af, at = int(a.hmm_from or 0), int(a.hmm_to or 0)
    bf, bt = int(b.hmm_from or 0), int(b.hmm_to or 0)
    lo, hi = max(af, bf), min(at, bt)
    inter = max(0, hi - lo + 1)
    union = max(at, bt) - min(af, bf) + 1
    return inter / union if union > 0 else 0.0


def _span_hmm(segs: list[LocusSegment]) -> tuple[int, int]:
    return min(int(s.hmm_from or 0) for s in segs), max(int(s.hmm_to or 0) for s in segs)


def _genomic_iou_to_locus(seg: LocusSegment, loc: list[LocusSegment]) -> float:
    if not loc or loc[0].contig != seg.contig or loc[0].strand != seg.strand:
        return 0.0
    ls = min(s.genomic_start for s in loc)
    le = max(s.genomic_end for s in loc)
    lo, hi = max(ls, seg.genomic_start), min(le, seg.genomic_end)
    inter = max(0, hi - lo)
    union = max(le, seg.genomic_end) - min(ls, seg.genomic_start)
    return inter / union if union > 0 else 0.0


def cluster_loci(segments: list[LocusSegment], model_length: int, settings: Settings) -> list[list[LocusSegment]]:
    """Merge continuing HMM tiles and same-ORF / genomically overlapping HSPs of one gene.

    Distinct tandem or inter-contig copies stay separate even when HMM spans overlap.
    """
    if not segments:
        return []
    max_merge = max(500, settings.thresholds.split_max_intergenic_bp * 2)
    remaining = sorted(segments, key=lambda s: (s.contig, s.strand, s.genomic_start, s.hmm_from or 0))
    loci: list[list[LocusSegment]] = []
    for seg in remaining:
        placed = False
        for loc in loci:
            last = loc[-1]
            if last.contig != seg.contig or last.strand != seg.strand:
                continue
            same_orf = bool(seg.orf_id) and any(s.orf_id == seg.orf_id for s in loc if s.orf_id)
            if same_orf or _genomic_iou_to_locus(seg, loc) >= 0.50:
                loc.append(seg)
                placed = True
                break
            gap = seg.genomic_start - last.genomic_end if seg.strand == "+" else last.genomic_start - seg.genomic_end
            iou = _hmm_iou(last, seg)
            continuing = (seg.hmm_from or 0) >= (last.hmm_from or 0) - 20
            if gap is not None and -30 <= gap <= max_merge and iou < 0.35 and continuing:
                loc.append(seg)
                placed = True
                break
        if not placed:
            loci.append([seg])
    loci.sort(key=lambda loc: -_union_hmm_coverage(loc, model_length or 1))
    return loci


def _genomic_interval_iou(a: dict, b: dict) -> float:
    if a.get("contig") != b.get("contig"):
        return 0.0
    lo = max(int(a["genomic_start"]), int(b["genomic_start"]))
    hi = min(int(a["genomic_end"]), int(b["genomic_end"]))
    inter = max(0, hi - lo)
    union = max(int(a["genomic_end"]), int(b["genomic_end"])) - min(int(a["genomic_start"]), int(b["genomic_start"]))
    return inter / union if union > 0 else 0.0


def _contained(inner: dict, outer: dict) -> bool:
    if inner.get("contig") != outer.get("contig"):
        return False
    return int(inner["genomic_start"]) >= int(outer["genomic_start"]) and int(inner["genomic_end"]) <= int(outer["genomic_end"])


def _distinct_loci(loci: list[dict]) -> list[dict]:
    """Drop nested or heavily overlapping copies on the same contig; those are not two genes."""
    kept: list[dict] = []
    for loc in sorted(loci, key=lambda x: -(x.get("hmm_coverage") or 0)):
        if any(_contained(loc, k) or _genomic_interval_iou(loc, k) >= 0.50 for k in kept):
            continue
        kept.append(loc)
    return kept


def _locus_blob(segs: list[LocusSegment], model_length: int, contig_sequences: dict[str, str], depth_by_contig: dict | None) -> dict:
    contig = segs[0].contig
    seq = contig_sequences.get(contig) or ""
    start = min(s.genomic_start for s in segs)
    end = max(s.genomic_end for s in segs)
    for s in segs:
        loc = _parse_orf_id(s.orf_id or "")
        if loc:
            start = min(start, int(loc["start"]))
            end = max(end, int(loc["end"]))
    window = seq[max(0, start):min(len(seq), end)].upper()
    gc = (window.count("G") + window.count("C")) / len(window) if window else None
    contig_gc = (seq.count("G") + seq.count("C")) / len(seq) if seq else None
    hmm_from, hmm_to = _span_hmm(segs)
    return {
        "contig": contig,
        "strand": segs[0].strand,
        "genomic_start": start,
        "genomic_end": end,
        "hmm_from": hmm_from,
        "hmm_to": hmm_to,
        "hmm_coverage": round(_union_hmm_coverage(segs, model_length or 1), 4),
        "orf_ids": sorted({s.orf_id for s in segs if s.orf_id}),
        "contig_length": len(seq),
        "contig_edge": any(s.near_contig_edge for s in segs),
        "gc": None if gc is None else round(gc, 4),
        "contig_gc": None if contig_gc is None else round(contig_gc, 4),
        "local_depth": None if not depth_by_contig else depth_by_contig.get(contig),
        "identity": None,
        "coverage": None,
    }


def _hit_on_locus(hit: GeneSearchHit, locus: dict) -> bool:
    if hit.contig_id != locus["contig"]:
        return False
    hs, he = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
    return hs < locus["genomic_end"] and he > locus["genomic_start"]


def _orthologue_flags(locus: dict, locus_evidence: list | None) -> dict:
    rbh = None
    synteny = None
    phylo = None
    for le in locus_evidence or []:
        cand = le.candidate_locus if hasattr(le, "candidate_locus") else (le.get("candidate_locus") if isinstance(le, dict) else None)
        contig = None
        if isinstance(cand, dict):
            contig = cand.get("contig") or cand.get("contig_id")
        if contig and contig != locus["contig"]:
            continue
        orths = le.orthologues if hasattr(le, "orthologues") else (le.get("orthologues") or [])
        for o in orths:
            val = o.reciprocal_best_hit if hasattr(o, "reciprocal_best_hit") else o.get("reciprocal_best_hit")
            if val is True:
                rbh = True
            elif val is False and rbh is not True:
                rbh = False
        conflicts = le.conflicts if hasattr(le, "conflicts") else (le.get("conflicts") or [])
        if "gene_order_mismatch" in conflicts or "missing_flanking_orthologues" in conflicts:
            synteny = False
        sim = le.sequence_similarity if hasattr(le, "sequence_similarity") else (le.get("sequence_similarity") or {})
        if isinstance(sim, dict) and sim.get("orthology_class") == "ortholog":
            synteny = True if synteny is not False else synteny
        placed = (sim.get("placement") if isinstance(sim, dict) else None) or {}
        if placed:
            phylo = placed
    return {"rbh": rbh, "synteny": synteny, "phylo": phylo}


def _equivalent_orthologues(a: dict, b: dict) -> bool:
    """True only when evidence actively supports both copies as orthologues."""
    fa, fb = a.get("orthologue_flags") or {}, b.get("orthologue_flags") or {}
    if fa.get("rbh") is True and fb.get("rbh") is True:
        return True
    if fa.get("synteny") is True and fb.get("synteny") is True:
        return True
    return False


def assess_paralogy(
    *,
    loci: list[dict],
    member_hits: list[GeneSearchHit],
    query_hits: list[GeneSearchHit],
    settings: Settings,
    locus_evidence: list | None = None,
) -> dict | None:
    """Return a paralogue record when two gated copies are not equivalent orthologues."""
    t = settings.thresholds
    gated = []
    for loc in loci:
        loc = dict(loc)
        mh = [h for h in member_hits if _hit_on_locus(h, loc) and h.search_kind in {"translated", "protein", "nucleotide"}]
        qh = [h for h in query_hits if _hit_on_locus(h, loc)]
        if mh:
            loc["identity"] = max(h.identity for h in mh)
            loc["coverage"] = max(h.query_coverage for h in mh)
        if qh:
            loc["query_identity"] = max(h.identity for h in qh)
            loc["query_coverage"] = max(h.query_coverage for h in qh)
        loc["family_gate_passed"] = bool(
            (loc.get("hmm_coverage") or 0) >= t.hmm_min_gate_model_coverage
            or (
                loc.get("identity") is not None
                and loc["identity"] >= t.family_member_min_identity
                and (loc.get("coverage") or 0) >= 0.20
            )
        )
        flags = _orthologue_flags(loc, locus_evidence)
        incoming = loc.get("orthologue_flags") or {}
        for key, val in incoming.items():
            if val is not None:
                flags[key] = val
        loc["orthologue_flags"] = flags
        gated.append(loc)
    strong = [loc for loc in _distinct_loci(gated) if loc.get("family_gate_passed")]
    if len(strong) < 2:
        return None
    primary, secondary = strong[0], strong[1]
    p_span = (primary["hmm_from"], primary["hmm_to"])
    s_span = (secondary["hmm_from"], secondary["hmm_to"])
    lo, hi = max(p_span[0], s_span[0]), min(p_span[1], s_span[1])
    inter = max(0, hi - lo + 1)
    union = max(p_span[1], s_span[1]) - min(p_span[0], s_span[0]) + 1
    hmm_iou = inter / union if union else 0.0
    complementary = hmm_iou < 0.35 and (primary["hmm_coverage"] + secondary["hmm_coverage"]) >= t.hmm_model_coverage_orthologue
    different_contigs = primary["contig"] != secondary["contig"]
    if complementary and different_contigs:
        return {
            "kind": "assembly_fragments_of_one_gene",
            "classify_as": "assembly_fragmented",
            "primary_locus": primary,
            "secondary_locus": secondary,
            "hmm_iou": round(hmm_iou, 4),
            "evidence_ids": ["E_family_hmm", "E_locus_reconstruction"],
            "provenance": {"created_by": "deterministic_paralogy", "species_specific_rules": False},
        }
    if _equivalent_orthologues(primary, secondary):
        return {
            "kind": "equivalent_orthologue_copies",
            "classify_as": None,
            "primary_locus": primary,
            "secondary_locus": secondary,
            "hmm_iou": round(hmm_iou, 4),
            "note": "Both copies have reciprocal/synteny support; not labeled close_paralogue automatically.",
            "evidence_ids": ["E_family_hmm", "E_locus_reconstruction"],
            "provenance": {"created_by": "deterministic_paralogy", "species_specific_rules": False},
        }
    p_id = primary.get("query_identity") if primary.get("query_identity") is not None else primary.get("identity") or 0
    s_id = secondary.get("query_identity") if secondary.get("query_identity") is not None else secondary.get("identity") or 0
    p_len = primary.get("contig_length") or 0
    s_len = secondary.get("contig_length") or 0
    plasmid_like = bool(s_len and p_len and s_len < 100_000 and (p_len >= 5 * s_len or p_len >= 500_000))
    gc_p = primary.get("contig_gc") if primary.get("contig_gc") is not None else primary.get("gc")
    gc_s = secondary.get("contig_gc") if secondary.get("contig_gc") is not None else secondary.get("gc")
    gc_out = gc_p is not None and gc_s is not None and abs(gc_p - gc_s) >= t.gene_gc_outlier
    d_p, d_s = primary.get("local_depth"), secondary.get("local_depth")
    depth_out = False
    if d_p and d_s and d_p > 0:
        ratio = d_s / d_p
        if ratio < t.gene_relative_depth_low or ratio > t.gene_relative_depth_high:
            depth_out = True
    near_identical = min(p_id, s_id) >= 0.95 and abs(p_id - s_id) <= 0.03
    if plasmid_like:
        kind = "plasmid_copy"
    elif gc_out or depth_out:
        kind = "contaminant_copy"
    elif near_identical:
        kind = "recent_gene_duplication"
    else:
        kind = "true_duplicated_paralogue"
    if not (secondary.get("hmm_coverage") or 0) >= t.hmm_min_gate_model_coverage and not (
        (secondary.get("identity") or 0) >= t.family_member_min_identity and (secondary.get("coverage") or 0) >= t.gene_paralogue_min_coverage
    ):
        return None
    return {
        "kind": kind,
        "classify_as": "close_paralogue",
        "primary_locus": primary,
        "secondary_locus": secondary,
        "identity": secondary.get("identity") or secondary.get("query_identity"),
        "coverage": secondary.get("coverage") or secondary.get("query_coverage"),
        "hmm_support": secondary.get("hmm_coverage"),
        "rbh_status": (secondary.get("orthologue_flags") or {}).get("rbh"),
        "synteny_status": (secondary.get("orthologue_flags") or {}).get("synteny"),
        "phylogenetic_evidence": (secondary.get("orthologue_flags") or {}).get("phylo"),
        "hmm_iou": round(hmm_iou, 4),
        "evidence_ids": ["E_family_hmm", "E_locus_reconstruction", "E_paralogy"],
        "provenance": {"created_by": "deterministic_paralogy", "species_specific_rules": False, "llm_invented_scores": False},
    }
