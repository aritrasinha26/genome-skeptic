"""Locus multiplicity: near-identical proteins can still be distinct genes.

Do not collapse two loci because their translations are almost the same.
"""
from __future__ import annotations

from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit
from genome_skeptic.validators.paralogy import _contained, _genomic_interval_iou, assess_paralogy


def _cluster_hits(hits: list[GeneSearchHit], min_id: float, min_cov: float) -> list[dict]:
    cands = []
    for h in hits:
        if h.search_kind not in {"translated", "protein", "nucleotide"}:
            continue
        if h.identity < min_id or h.query_coverage < min_cov:
            continue
        lo, hi = min(h.tstart, h.tend), max(h.tstart, h.tend)
        cands.append({
            "contig": h.contig_id,
            "strand": h.strand or "+",
            "genomic_start": lo,
            "genomic_end": hi,
            "identity": h.identity,
            "coverage": h.query_coverage,
            "query_identity": h.identity,
            "query_coverage": h.query_coverage,
            "hmm_from": 1,
            "hmm_to": max(1, int(h.query_length or 1)),
            "hmm_coverage": h.query_coverage,
            "contig_length": h.contig_length,
            "contig_edge": bool(h.near_contig_edge),
            "gc": None,
            "orf_ids": [f"{h.contig_id}:{lo}-{hi}:{h.strand or '+'}"],
        })
    cands.sort(key=lambda x: -(x["identity"] * x["coverage"]))
    kept: list[dict] = []
    for loc in cands:
        if any(_contained(loc, k) or _genomic_interval_iou(loc, k) >= 0.50 for k in kept):
            continue
        kept.append(loc)
    return kept


def _flank(seq: str, start: int, end: int, bp: int = 120) -> tuple[str, str]:
    up = seq[max(0, start - bp): max(0, start)].upper()
    down = seq[min(len(seq), end): min(len(seq), end + bp)].upper()
    return up, down


def assess_multiplicity(
    *,
    family_id: str,
    member_hits: list[GeneSearchHit],
    query_hits: list[GeneSearchHit],
    hmm_loci: list[dict],
    contig_sequences: dict[str, str],
    settings: Settings,
    paralogue_record: dict | None = None,
) -> dict:
    t = settings.thresholds
    hit_loci = _cluster_hits(list(member_hits) + list(query_hits), t.multiplicity_min_identity, t.multiplicity_min_coverage)
    # Merge HMM-gated loci that are genomically distinct even if identity was not recorded.
    for loc in hmm_loci or []:
        blob = {
            "contig": loc.get("contig"),
            "strand": loc.get("strand") or "+",
            "genomic_start": loc.get("genomic_start"),
            "genomic_end": loc.get("genomic_end"),
            "identity": loc.get("identity") or loc.get("query_identity") or 0.0,
            "coverage": loc.get("coverage") or loc.get("query_coverage") or loc.get("hmm_coverage") or 0.0,
            "query_identity": loc.get("query_identity") or loc.get("identity"),
            "hmm_from": loc.get("hmm_from") or 1,
            "hmm_to": loc.get("hmm_to") or 1,
            "hmm_coverage": loc.get("hmm_coverage") or 0.0,
            "contig_length": loc.get("contig_length"),
            "contig_edge": loc.get("contig_edge"),
            "gc": loc.get("gc"),
            "contig_gc": loc.get("contig_gc"),
            "orf_ids": loc.get("orf_ids") or [],
        }
        if blob["genomic_start"] is None or blob["contig"] is None:
            continue
        if (blob["hmm_coverage"] or 0) < t.hmm_min_gate_model_coverage and (blob["coverage"] or 0) < t.multiplicity_min_coverage:
            continue
        if any(_contained(blob, k) or _genomic_interval_iou(blob, k) >= 0.50 for k in hit_loci):
            continue
        hit_loci.append(blob)

    for loc in hit_loci:
        seq = contig_sequences.get(loc["contig"]) or ""
        loc["contig_length"] = loc.get("contig_length") or len(seq)
        up, down = _flank(seq, int(loc["genomic_start"]), int(loc["genomic_end"]))
        loc["upstream_context"] = up[:80]
        loc["downstream_context"] = down[:80]
        loc["family_gate_passed"] = bool(
            (loc.get("hmm_coverage") or 0) >= t.hmm_min_gate_model_coverage
            or ((loc.get("identity") or 0) >= t.multiplicity_min_identity and (loc.get("coverage") or 0) >= t.multiplicity_min_coverage)
        )

    n = len(hit_loci)
    classification = "single_locus"
    pairwise_id = None
    if n >= 2:
        a, b = hit_loci[0], hit_loci[1]
        pairwise_id = min(a.get("identity") or 0, b.get("identity") or 0)
        same_contig = a["contig"] == b["contig"]
        independent_flanks = (a.get("upstream_context") or "") != (b.get("upstream_context") or "") or (a.get("downstream_context") or "") != (b.get("downstream_context") or "")
        para = paralogue_record or assess_paralogy(loci=hit_loci, member_hits=member_hits, query_hits=query_hits, settings=settings)
        kind = (para or {}).get("kind")
        if kind == "assembly_fragments_of_one_gene":
            classification = "assembly_fragments_of_one_gene"
        elif kind == "plasmid_copy":
            classification = "plasmid_copy"
        elif kind == "contaminant_copy":
            classification = "contaminant_copy"
        elif kind == "recent_gene_duplication" or (pairwise_id is not None and pairwise_id >= 0.95 and independent_flanks):
            classification = "recent_duplication"
        elif kind == "true_duplicated_paralogue":
            classification = "paralogous_copy"
        elif independent_flanks or not same_contig:
            classification = "true_gene_duplication"
        else:
            classification = "unresolved_multiple_hits"

    return {
        "family": family_id,
        "number_of_candidate_loci": n,
        "coordinates": [{"contig": x["contig"], "start": x["genomic_start"], "end": x["genomic_end"], "strand": x.get("strand")} for x in hit_loci],
        "contigs": sorted({x["contig"] for x in hit_loci}),
        "strand": [x.get("strand") for x in hit_loci],
        "sequence_identity_between_copies": pairwise_id,
        "family_evidence_per_locus": [
            {"contig": x["contig"], "identity": x.get("identity"), "coverage": x.get("coverage"), "hmm_coverage": x.get("hmm_coverage"), "family_gate_passed": x.get("family_gate_passed")}
            for x in hit_loci
        ],
        "read_depth_per_locus": [x.get("local_depth") for x in hit_loci],
        "upstream_context": [x.get("upstream_context") for x in hit_loci],
        "downstream_context": [x.get("downstream_context") for x in hit_loci],
        "assembly_fragment_relationship": classification == "assembly_fragments_of_one_gene",
        "plasmid_chromosome_context": classification if classification in {"plasmid_copy"} else None,
        "contamination_evidence": classification == "contaminant_copy",
        "classification": classification,
        "loci": hit_loci,
        "provenance": {"created_by": "deterministic_locus_multiplicity", "llm_invented_scores": False, "collapsed_near_identical_copies": False},
        "evidence_ids": ["E_locus_reconstruction", "E_paralogy", "E_multiplicity"],
    }
