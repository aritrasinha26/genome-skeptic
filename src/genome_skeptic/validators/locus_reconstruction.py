"""Annotation-independent locus reconstruction from assembly DNA.

Predicted ORFs are inputs, not the definition of the locus. Architecture is
assigned only after a deterministic family-evidence gate. No species rules.
"""
from __future__ import annotations

from pathlib import Path
import tempfile

from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit, LocusReconstruction, LocusSegment, TargetFamily
from genome_skeptic.tools.gene_search import extract_orfs, reverse_complement, translate_frame


ARCHITECTURE_STATES = (
    "canonical_full_length",
    "divergent_full_length",
    "fusion",
    "biological_split",
    "assembly_fragmented",
    "frameshift_or_pseudogene",
    "close_paralogue",
    "domain_only",
    "unresolved_candidate",
    "true_no_candidate",
)


def _parse_orf_id(orf_id: str) -> dict | None:
    try:
        contig_span, strand = orf_id.rsplit(":", 1)
        contig, span = contig_span.rsplit(":", 1)
        start_s, end_s = span.split("-", 1)
        return {"contig_id": contig, "start": int(start_s), "end": int(end_s), "strand": strand, "orf_id": orf_id}
    except ValueError:
        return None


def window_orfs(
    contig_sequences: dict[str, str],
    centers: list[tuple[str, int, int]],
    settings: Settings,
) -> list[dict]:
    """Six-frame ORFs in genomic windows around candidate intervals. Coordinates are contig-absolute."""
    t = settings.thresholds
    pad = int(t.locus_window_bp)
    min_aa = int(t.locus_orf_min_aa)
    edge = int(t.contig_edge_proximity_bp)
    by_contig: dict[str, list[tuple[int, int]]] = {}
    for cid, lo, hi in centers:
        by_contig.setdefault(cid, []).append((lo, hi))
    orfs: list[dict] = []
    for cid, spans in by_contig.items():
        seq = contig_sequences.get(cid) or ""
        if not seq:
            continue
        n = len(seq)
        merged_lo = max(0, min(s[0] for s in spans) - pad)
        merged_hi = min(n, max(s[1] for s in spans) + pad)
        sub = seq[merged_lo:merged_hi]
        raw = extract_orfs([(cid, sub)], min_aa=min_aa, edge_bp=edge)
        for o in raw:
            start = int(o["start"]) + merged_lo
            end = int(o["end"]) + merged_lo
            o["start"] = start
            o["end"] = end
            o["contig_id"] = cid
            o["contig_length"] = n
            o["near_contig_edge"] = start <= edge or (n - end) <= edge
            o["orf_id"] = f"{cid}:{start}-{end}:{o['strand']}"
            o["window_offset"] = merged_lo
            orfs.append(o)
    return orfs


def _segments_from_hmm(hmm_by_target: dict, orf_by_id: dict, settings: Settings) -> list[LocusSegment]:
    t = settings.thresholds
    segs: list[LocusSegment] = []
    for tid, hmm in (hmm_by_target or {}).items():
        if not hmm:
            continue
        ev = hmm.get("full_evalue")
        if ev is None or ev > 1e-3:
            continue
        loc = _parse_orf_id(tid) or {}
        orf = orf_by_id.get(tid) or loc
        domains = hmm.get("domains") or []
        if not domains:
            domains = [{"hmm_from": 1, "hmm_to": int((hmm.get("model_length") or 1) * (hmm.get("model_coverage") or 0)), "ali_from": 1, "ali_to": hmm.get("query_length") or 1}]
        strand = (orf or {}).get("strand") or loc.get("strand") or "+"
        contig = (orf or {}).get("contig_id") or loc.get("contig_id") or tid
        ostart = int((orf or {}).get("start") or loc.get("start") or 0)
        oend = int((orf or {}).get("end") or loc.get("end") or 0)
        n = int((orf or {}).get("contig_length") or 0)
        for d in domains:
            hmm_from = int(d.get("hmm_from") or 0)
            hmm_to = int(d.get("hmm_to") or 0)
            ali_from = int(d.get("ali_from") or 1)
            ali_to = int(d.get("ali_to") or ali_from)
            if strand == "+":
                gstart = ostart + max(0, ali_from - 1) * 3
                gend = ostart + max(ali_from, ali_to) * 3
            else:
                gend = oend - max(0, ali_from - 1) * 3
                gstart = oend - max(ali_from, ali_to) * 3
                gstart, gend = min(gstart, gend), max(gstart, gend)
            segs.append(
                LocusSegment(
                    contig=str(contig),
                    strand=str(strand),
                    genomic_start=int(gstart),
                    genomic_end=int(gend),
                    frame=(gstart % 3) if strand == "+" else None,
                    orf_id=tid,
                    hmm_from=hmm_from,
                    hmm_to=hmm_to,
                    evalue=float(d.get("domain_i_evalue") if d.get("domain_i_evalue") is not None else ev),
                    score=d.get("domain_score") or hmm.get("full_score"),
                    near_contig_edge=bool((orf or {}).get("near_contig_edge")) or (n and (min(gstart, gend) <= t.contig_edge_proximity_bp or n - max(gstart, gend) <= t.contig_edge_proximity_bp)),
                )
            )
    segs.sort(key=lambda s: (s.contig, s.strand, s.hmm_from or 0, s.genomic_start))
    return segs


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


def _best_chain(segs: list[LocusSegment], model_length: int, settings: Settings) -> list[LocusSegment]:
    """Order segments by HMM coordinates; keep one compatible chain per contig+strand, pick the best coverage."""
    if not segs:
        return []
    groups: dict[tuple[str, str], list[LocusSegment]] = {}
    for s in segs:
        groups.setdefault((s.contig, s.strand), []).append(s)
    best: list[LocusSegment] = []
    best_cov = -1.0
    max_gap = max(5000, settings.thresholds.split_max_intergenic_bp * 20)
    for key, blob in groups.items():
        ordered = sorted(blob, key=lambda s: (s.hmm_from or 0, s.genomic_start))
        chain: list[LocusSegment] = []
        last_hmm = -1
        last_end = None
        for s in ordered:
            if (s.hmm_from or 0) < last_hmm - 20:
                continue
            if last_end is not None:
                gap = s.genomic_start - last_end if s.strand == "+" else last_end - s.genomic_end
                if gap > max_gap:
                    continue
            chain.append(s)
            last_hmm = s.hmm_to or last_hmm
            last_end = s.genomic_end if s.strand == "+" else s.genomic_start
        cov = _union_hmm_coverage(chain, model_length)
        if cov > best_cov:
            best_cov = cov
            best = chain
    return best


def _stops_between(seq: str, strand: str, start: int, end: int) -> list[dict]:
    if end <= start or not seq:
        return []
    window = seq[max(0, start):min(len(seq), end)]
    if strand == "-":
        window = reverse_complement(window)
    stops = []
    for i in range(0, len(window) - 2, 3):
        codon = window[i:i + 3].upper()
        if codon in {"TAA", "TAG", "TGA"}:
            stops.append({"offset": i, "codon": codon})
    return stops


def classify_architecture(
    *,
    reconstruction: LocusReconstruction,
    family: TargetFamily,
    member_hits: list[GeneSearchHit],
    partner_hits: list[GeneSearchHit],
    partner_hmm: dict,
    settings: Settings,
    query_hits: list[GeneSearchHit] | None = None,
    query_aa: str | None = None,
    locus_evidence: list | None = None,
) -> LocusReconstruction:
    t = settings.thresholds
    segs = list(reconstruction.candidate_segments)
    model_len = 0
    if family.members:
        model_len = max((m.length_aa or len(m.sequence) or 0) for m in family.members)
    hmm_cov = float(reconstruction.hmm_coverage or 0.0)
    gate = hmm_cov >= t.hmm_min_gate_model_coverage or any(
        h.identity >= t.family_member_min_identity and h.query_coverage >= 0.20
        for h in member_hits
        if h.search_kind in {"translated", "protein", "nucleotide"}
    )
    reconstruction.family_gate_passed = bool(gate)
    if not gate:
        reconstruction.architecture = "true_no_candidate"
        return reconstruction

    n_orfs = len({s.orf_id for s in segs if s.orf_id})
    n_contigs = len({s.contig for s in segs})
    edge = bool(reconstruction.contig_edge)
    identity = reconstruction.query_identity if reconstruction.query_identity is not None else (reconstruction.sequence_identity or 0.0)

    partner_in_locus = False
    if reconstruction.contig and reconstruction.genomic_start is not None and reconstruction.genomic_end is not None:
        lo, hi = reconstruction.genomic_start, reconstruction.genomic_end
        for ph in partner_hits:
            if ph.contig_id != reconstruction.contig:
                continue
            ps, pe = min(ph.tstart, ph.tend), max(ph.tstart, ph.tend)
            if ps < hi and pe > lo and ph.query_coverage >= 0.40:
                partner_in_locus = True
                break
        if not partner_in_locus:
            for tid, hmm in (partner_hmm or {}).items():
                loc = _parse_orf_id(tid) or {}
                if loc.get("contig_id") != reconstruction.contig:
                    continue
                if (hmm.get("full_evalue") is not None and hmm["full_evalue"] <= t.fusion_partner_evalue_max
                        and loc.get("start", 0) < hi and loc.get("end", 0) > lo):
                    partner_in_locus = True
                    break

    expected = family.expected_length_aa or 0
    locus_aa = 0
    if reconstruction.genomic_start is not None and reconstruction.genomic_end is not None:
        locus_aa = max(0, reconstruction.genomic_end - reconstruction.genomic_start) // 3
    long_locus = bool(expected and locus_aa >= t.fusion_length_ratio_min * expected)

    para = reconstruction.paralogue_record or {}
    if para.get("classify_as") == "assembly_fragmented":
        reconstruction.architecture = "assembly_fragmented"
        return reconstruction

    if 0 < hmm_cov <= t.hmm_domain_only_max_model_coverage and not reconstruction.frameshifts and n_contigs <= 1 and not edge:
        reconstruction.architecture = "domain_only"
        return reconstruction

    if hmm_cov == 0.0 and (reconstruction.sequence_identity or 0) >= t.family_member_min_identity and (reconstruction.protein_coverage or 0) >= 0.70:
        # HMM evidence is unavailable or empty; full-length member homology is not a domain-only hit.
        if para.get("classify_as") == "close_paralogue":
            reconstruction.architecture = "close_paralogue"
            return reconstruction
        reconstruction.architecture = "divergent_full_length" if bool((reconstruction.divergence or {}).get("divergent")) else "canonical_full_length"
        return reconstruction

    if reconstruction.frameshifts and hmm_cov >= t.hmm_unresolved_model_coverage:
        reconstruction.architecture = "frameshift_or_pseudogene"
        return reconstruction

    if partner_in_locus and long_locus and n_orfs <= 2 and n_contigs == 1 and hmm_cov >= t.hmm_unresolved_model_coverage:
        reconstruction.architecture = "fusion"
        return reconstruction

    if n_orfs >= 2 and n_contigs == 1 and hmm_cov >= t.hmm_model_coverage_orthologue:
        gaps_ok = bool(reconstruction.inter_segment_gaps) and all(
            0 <= g <= max(t.split_max_intergenic_bp, 400) for g in reconstruction.inter_segment_gaps
        )
        ordered = list(reconstruction.domain_order) == sorted(reconstruction.domain_order) if reconstruction.domain_order else True
        if gaps_ok and ordered:
            reconstruction.architecture = "biological_split"
            return reconstruction

    if (n_contigs > 1 or edge) and hmm_cov < t.hmm_model_coverage_orthologue:
        reconstruction.architecture = "assembly_fragmented"
        return reconstruction
    if edge and hmm_cov < t.hmm_model_coverage_orthologue:
        reconstruction.architecture = "assembly_fragmented"
        return reconstruction

    if para.get("classify_as") == "close_paralogue":
        reconstruction.architecture = "close_paralogue"
        return reconstruction

    full = hmm_cov >= t.hmm_model_coverage_orthologue
    divergent = bool((reconstruction.divergence or {}).get("divergent"))
    if full:
        reconstruction.architecture = "divergent_full_length" if divergent else "canonical_full_length"
        return reconstruction

    if hmm_cov >= t.hmm_unresolved_model_coverage:
        reconstruction.architecture = "unresolved_candidate"
        return reconstruction
    if hmm_cov >= t.hmm_min_gate_model_coverage:
        reconstruction.architecture = "unresolved_candidate"
        return reconstruction
    reconstruction.architecture = "domain_only"
    return reconstruction


def reconstruct_locus(
    *,
    family: TargetFamily,
    contig_sequences: dict[str, str],
    member_hits: list[GeneSearchHit],
    hmm_by_target: dict,
    orfs: list[dict],
    partner_hits: list[GeneSearchHit],
    partner_hmm: dict,
    settings: Settings,
    proteins: dict[str, str] | None = None,
    depth_by_contig: dict | None = None,
    annotation_orfs: list[str] | None = None,
    query_hits: list[GeneSearchHit] | None = None,
    query_aa: str | None = None,
    locus_evidence: list | None = None,
    out_dir: Path | None = None,
) -> LocusReconstruction:
    """Build a genomic locus from DNA-window HMM segments. LLM does not invent scores."""
    rec = LocusReconstruction(
        provenance={
            "created_by": "deterministic_locus_reconstruction",
            "operates_on": "assembly_sequence",
            "llm_invented_scores": False,
            "species_specific_rules": False,
        }
    )
    orf_by_id = {o["orf_id"]: o for o in orfs}
    segs = _segments_from_hmm(hmm_by_target, orf_by_id, settings)
    model_length = 0
    if hmm_by_target:
        model_length = max((int(h.get("model_length") or h.get("qlen") or 0) for h in hmm_by_target.values() if h), default=0)
    if not model_length:
        model_length = family.expected_length_aa or 0
    chain = _best_chain(segs, model_length or 1, settings)
    rec.candidate_segments = chain
    rec.hmm_coverage = round(_union_hmm_coverage(chain, model_length or 1), 4) if chain else 0.0
    if chain:
        rec.contig = chain[0].contig
        rec.strand = chain[0].strand
        rec.genomic_start = min(s.genomic_start for s in chain)
        rec.genomic_end = max(s.genomic_end for s in chain)
        for s in chain:
            loc = _parse_orf_id(s.orf_id or "")
            if loc:
                rec.genomic_start = min(rec.genomic_start, int(loc["start"]))
                rec.genomic_end = max(rec.genomic_end, int(loc["end"]))
        rec.frame = chain[0].frame
        rec.profile_hmm_from = min((s.hmm_from or 0) for s in chain)
        rec.profile_hmm_to = max((s.hmm_to or 0) for s in chain)
        rec.domain_order = [i + 1 for i, _ in enumerate(chain)]
        rec.contig_edge = any(s.near_contig_edge for s in chain)
        gaps = []
        stops = []
        frames = []
        seq = contig_sequences.get(rec.contig) or ""
        ordered = sorted(chain, key=lambda s: s.genomic_start)
        for a, b in zip(ordered, ordered[1:]):
            gap = b.genomic_start - a.genomic_end
            gaps.append(gap)
            if gap >= 0:
                stops.extend(_stops_between(seq, rec.strand or "+", a.genomic_end, b.genomic_start))
            if a.frame is not None and b.frame is not None and a.frame != b.frame and abs(gap) < 30:
                frames.append({"from_orf": a.orf_id, "to_orf": b.orf_id, "gap_bp": gap})
        rec.inter_segment_gaps = gaps
        rec.stop_codons = stops
        rec.frameshifts = frames
        genomic = [h for h in member_hits if h.search_kind in {"translated", "nucleotide"} and h.contig_id == rec.contig]
        if genomic:
            rec.sequence_identity = max(h.identity for h in genomic)
            rec.protein_coverage = max(h.query_coverage for h in genomic)
        if depth_by_contig and rec.contig in depth_by_contig:
            rec.local_depth = depth_by_contig.get(rec.contig)
        if annotation_orfs:
            rec.annotation_agreement = "agrees" if any(s.orf_id in annotation_orfs for s in chain) else "disagrees"
        rec.evidence_ids = ["E_family_hmm", "E_locus_reconstruction"]
    if not chain:
        homology = [
            h for h in list(member_hits) + list(query_hits or [])
            if h.search_kind in {"translated", "protein", "nucleotide"}
            and h.identity >= settings.thresholds.family_member_min_identity
            and h.query_coverage >= 0.50
        ]
        if homology:
            best = max(homology, key=lambda h: h.identity * h.query_coverage)
            rec.contig = best.contig_id
            rec.strand = best.strand or "+"
            rec.genomic_start = min(best.tstart, best.tend)
            rec.genomic_end = max(best.tstart, best.tend)
            rec.sequence_identity = best.identity
            rec.protein_coverage = best.query_coverage
            rec.contig_edge = bool(best.near_contig_edge)
            rec.evidence_ids = ["E_member_homology", "E_locus_reconstruction"]
            rec.hmm_coverage = 0.0
    identities = [h.identity for h in member_hits if h.search_kind in {"translated", "protein"}]
    if rec.sequence_identity is None and identities:
        rec.sequence_identity = max(identities)
    qhits = list(query_hits or [])
    if rec.contig and rec.genomic_start is not None and rec.genomic_end is not None and qhits:
        overlapping = [
            h for h in qhits
            if h.contig_id == rec.contig and min(h.tstart, h.tend) < rec.genomic_end and max(h.tstart, h.tend) > rec.genomic_start
        ]
        if overlapping:
            rec.query_identity = max(h.identity for h in overlapping)
            rec.protein_coverage = rec.protein_coverage or max(h.query_coverage for h in overlapping)
    if rec.query_identity is None and query_aa and rec.contig and rec.genomic_start is not None:
        from genome_skeptic.validators.divergence import _identity
        seq = contig_sequences.get(rec.contig) or ""
        window = seq[max(0, rec.genomic_start): min(len(seq), rec.genomic_end or 0)]
        if window:
            from genome_skeptic.tools.gene_search import reverse_complement, translate_frame
            if str(rec.strand or "+").startswith("-"):
                window = reverse_complement(window)
            aa = max((translate_frame(window, f).replace("*", "") for f in range(3)), key=len, default="")
            rec.query_identity = _identity(query_aa, aa, settings)
    if query_aa:
        from genome_skeptic.validators.divergence import family_identity_distribution, is_divergent_full_length
        dist = family_identity_distribution(family, query_aa, settings)
        dist["candidate_query_identity"] = rec.query_identity
        dist["divergent"] = is_divergent_full_length(rec.query_identity, dist)
        rec.divergence = dist
    from genome_skeptic.validators.paralogy import assess_paralogy, cluster_loci, _locus_blob
    all_loci_segs = cluster_loci(segs, model_length or 1, settings)
    blobs = [_locus_blob(loc, model_length or 1, contig_sequences, depth_by_contig) for loc in all_loci_segs]
    rec.secondary_loci = blobs[1:]
    rec.paralogue_record = assess_paralogy(
        loci=blobs,
        member_hits=member_hits,
        query_hits=qhits,
        settings=settings,
        locus_evidence=locus_evidence,
    )
    from genome_skeptic.validators.locus_multiplicity import assess_multiplicity
    rec.multiplicity = assess_multiplicity(
        family_id=family.family_id,
        member_hits=member_hits,
        query_hits=qhits,
        hmm_loci=blobs,
        contig_sequences=contig_sequences,
        settings=settings,
        paralogue_record=rec.paralogue_record,
    )
    multi_class = (rec.multiplicity or {}).get("classification")
    if rec.paralogue_record is None and multi_class in {"true_gene_duplication", "recent_duplication", "paralogous_copy", "plasmid_copy", "contaminant_copy"}:
        kind_map = {
            "true_gene_duplication": "true_duplicated_paralogue",
            "recent_duplication": "recent_gene_duplication",
            "paralogous_copy": "true_duplicated_paralogue",
            "plasmid_copy": "plasmid_copy",
            "contaminant_copy": "contaminant_copy",
        }
        rec.paralogue_record = {
            "kind": kind_map[multi_class],
            "classify_as": "close_paralogue",
            "multiplicity_class": multi_class,
            "evidence_ids": ["E_multiplicity", "E_paralogy"],
            "provenance": {"created_by": "deterministic_locus_multiplicity", "collapsed_near_identical_copies": False},
        }
    rec = classify_architecture(
        reconstruction=rec,
        family=family,
        member_hits=member_hits,
        partner_hits=partner_hits,
        partner_hmm=partner_hmm,
        settings=settings,
        query_hits=qhits,
        query_aa=query_aa,
        locus_evidence=locus_evidence,
    )
    from genome_skeptic.validators.competitive_family import discriminate_family
    dest = Path(out_dir) / "competitive" if out_dir else Path(tempfile.mkdtemp(prefix="gs_competitive_"))
    comp = discriminate_family(
        family=family,
        reconstruction=rec.model_dump(),
        contig_sequences=contig_sequences,
        settings=settings,
        out_dir=dest,
    )
    rec.competitive_family = comp.as_dict()
    if (comp.competitors_scored or family.competing_families) and rec.family_gate_passed:
        if comp.classification == "competing_family_preferred":
            rec.architecture = "true_no_candidate"
            rec.family_gate_passed = False
        elif comp.classification == "ambiguous_family":
            rec.architecture = "unresolved_candidate"
        elif comp.classification == "domain_only":
            rec.architecture = "domain_only"
            rec.family_gate_passed = False
    return rec
