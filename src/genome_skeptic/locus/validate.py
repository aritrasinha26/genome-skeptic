from __future__ import annotations

from typing import Any

from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit, LocusEvidence, TargetProfile
from genome_skeptic.tools.gene_search import is_nucleotide, translate_frame
from genome_skeptic.validators.homology import strong_hit

from .orthology import classify_orthology, reciprocal_best_hits
from .synteny import annotate_target, compare_neighborhood, flanks, genes_from_features, intergenic_distances, names


def _unique_loci(hits: list[GeneSearchHit], settings: Settings) -> list[GeneSearchHit]:
    kept: list[GeneSearchHit] = []
    ranked = sorted(
        [h for h in hits if h.search_kind == "nucleotide"] or [h for h in hits if h.search_kind == "translated"],
        key=lambda h: h.identity * h.query_coverage,
        reverse=True,
    )
    for hit in ranked:
        if not strong_hit(hit, settings):
            continue
        overlapped = False
        for prev in kept:
            if prev.contig_id != hit.contig_id:
                continue
            if min(prev.tend, hit.tend) - max(prev.tstart, hit.tstart) > 30:
                overlapped = True
                break
        if not overlapped:
            kept.append(hit)
    return kept


def _neighbor_edge_conflicts(genes: list, contig_sequences: dict[str, str], proximity: int) -> list[str]:
    conflicts: list[str] = []
    for gene in genes:
        contig = gene.contig
        if contig is None and len(contig_sequences) == 1:
            contig = next(iter(contig_sequences))
        if contig is None:
            continue
        clen = len(contig_sequences.get(contig, ""))
        if not clen:
            continue
        edge = min(max(gene.start, 0), max(clen - gene.end, 0))
        if edge <= proximity:
            conflicts.append("contig_edge")
            break
    return conflicts


def _query_aa(profile: TargetProfile) -> str:
    seq = profile.sequence.upper()
    if not seq:
        return ""
    if is_nucleotide(seq):
        aa = max((translate_frame(seq, f) for f in range(3)), key=len)
        return aa.split("*")[0] if aa else ""
    return seq.replace("*", "")


def _best_hit(hits: list[GeneSearchHit], settings: Settings) -> GeneSearchHit | None:
    ranked = [h for h in hits if h.search_kind != "domain"]
    if not ranked:
        return None
    strong = [h for h in ranked if strong_hit(h, settings)]
    pool = strong or ranked
    return max(pool, key=lambda h: (h.query_coverage * h.identity, h.alignment_length))


def _candidate_protein(hit: GeneSearchHit | None, contig_seqs: dict[str, str], profile: TargetProfile) -> str:
    if hit is None:
        return _query_aa(profile)
    contig = contig_seqs.get(hit.contig_id, "")
    if hit.search_kind == "protein":
        return ""
    start, end = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
    seq = contig[start:end]
    if hit.strand == "-":
        from genome_skeptic.tools.gene_search import reverse_complement
        seq = reverse_complement(seq)
    if is_nucleotide(seq):
        aa = translate_frame(seq, 0).split("*")[0]
        return aa
    return seq


def build_locus_evidence(
    *,
    profile: TargetProfile,
    hits: list[GeneSearchHit],
    settings: Settings,
    assembly_features: list[dict],
    contig_sequences: dict[str, str],
    query_proteins: dict[str, str],
    references: list[dict],
    coverage: dict[str, Any] | None = None,
    tools_run: list[str] | None = None,
    tool_hits_by_reference: dict[str, list] | None = None,
    break_evidence: dict[str, dict] | None = None,
    contig_taxonomy: dict[str, dict] | None = None,
    mapping_available: bool = False,
) -> list[LocusEvidence]:
    records: list[LocusEvidence] = []
    best = _best_hit(hits, settings)
    candidate = None
    if best:
        candidate = {
            "contig": best.contig_id,
            "start": min(best.tstart, best.tend),
            "end": max(best.tstart, best.tend),
            "strand": best.strand,
        }
    seqid = best.contig_id if best else None
    query_genes = genes_from_features(assembly_features, seqid)
    if candidate:
        query_genes = annotate_target(query_genes, candidate["start"], candidate["end"])
    cand_aa = _candidate_protein(best, contig_sequences, profile)

    if not references:
        records.append(LocusEvidence(
            target=profile.query_id,
            candidate_locus=candidate,
            reference_genome=None,
            gene_order=query_genes,
            orientation=candidate["strand"] if candidate else None,
            coverage=coverage or {},
            conflicts=["no_reference_genome"],
            provenance={
                "created_by": "deterministic_locus_validator",
                "tools": tools_run or ["internal_gene_search"],
                "notes": "LLM did not invent orthologues, identities, gene order, or reciprocal hits.",
            },
        ))
        return records

    for ref in references:
        ref_proteins = list((ref.get("protein_sequences") or {}).items())
        if not ref_proteins and ref.get("sequences"):
            ref_proteins = [(gid, translate_frame(seq.upper(), 0).split("*")[0]) for gid, seq in ref["sequences"].items()]
        orthos = reciprocal_best_hits(
            [(profile.query_id, cand_aa)] if cand_aa else [],
            ref_proteins,
            settings,
            tool_hits=(tool_hits_by_reference or {}).get(ref.get("id") or ""),
        )
        if not settings.execution.enable_orthology:
            orthos = []
            kind, ortho_conflicts = "unassigned", []
        else:
            kind, ortho_conflicts = classify_orthology(orthos, settings)
            extra_loci = _unique_loci(hits, settings)
            if len(extra_loci) >= settings.thresholds.gene_paralogue_min_loci:
                ortho_conflicts.append("paralogous_copies")
                kind = "paralog"
        ref_genes = genes_from_features(ref.get("features") or [], None)
        target_ref = next((g for g in ref_genes if profile.query_id.lower() in (g.product.lower() + g.gene_id.lower())), None)
        if target_ref:
            ref_genes = annotate_target(ref_genes, target_ref.start, target_ref.end)
        synteny_conflicts = []
        if not settings.execution.enable_synteny:
            pass
        elif candidate and target_ref:
            if query_genes:
                synteny_conflicts = compare_neighborhood(
                    query_genes, ref_genes,
                    flank=settings.thresholds.synteny_flank_genes,
                    spacing_fold=settings.thresholds.synteny_spacing_fold,
                )
            else:
                synteny_conflicts.append("query_annotation_missing")
        elif candidate and not target_ref:
            synteny_conflicts.append("reference_target_not_annotated")
        if candidate and candidate.get("start") is not None:
            contig_len = len(contig_sequences.get(candidate["contig"], ""))
            key = f"{candidate['contig']}:{candidate['start']}-{candidate['end']}"
            br = (break_evidence or {}).get(key) or {}
            if br.get("status") == "completed" and br.get("read_supported_break") is True:
                synteny_conflicts.append("contig_edge")
            elif mapping_available:
                pass
            elif best is not None and best.possible_edge_truncation:
                synteny_conflicts.append("contig_edge")
        if not candidate:
            if mapping_available:
                if any((break_evidence or {}).get(k, {}).get("read_supported_break") for k in (break_evidence or {})):
                    synteny_conflicts.append("contig_edge")
            else:
                synteny_conflicts.extend(_neighbor_edge_conflicts(query_genes, contig_sequences, settings.thresholds.contig_edge_proximity_bp))
            assembly_products = names(genes_from_features(assembly_features, None))
            ref_neighbor_names = [g.product for g in ref_genes if not g.is_target]
            present_neighbors = [n for n in ref_neighbor_names if n in assembly_products]
            if ref_neighbor_names and not present_neighbors:
                synteny_conflicts.append("missing_flanking_orthologues")
        q_dist = intergenic_distances(query_genes)
        r_dist = intergenic_distances(ref_genes)
        best_ortho = max(orthos, key=lambda r: r.identity * r.query_coverage, default=None)
        similarity = {
            "identity": best_ortho.identity if best_ortho else None,
            "query_coverage": best_ortho.query_coverage if best_ortho else None,
            "subject_coverage": best_ortho.subject_coverage if best_ortho else None,
            "evalue": best_ortho.evalue if best_ortho else None,
            "orthology_class": kind,
        }
        length_ratio = None
        if cand_aa and best_ortho:
            ref_aa = dict(ref_proteins).get(best_ortho.subject_id, "")
            if ref_aa:
                length_ratio = len(cand_aa) / max(1, len(ref_aa))
        similarity["length_ratio"] = length_ratio
        placement = {}
        labeled = []
        for item in ref.get("homologues") or []:
            hid = item.get("id")
            hseq = item.get("sequence") or dict(ref_proteins).get(hid or "", "")
            if hid and hseq:
                labeled.append({"id": hid, "sequence": hseq, "clade": item.get("clade") or "unlabeled"})
        if cand_aa and labeled and settings.execution.enable_phylogeny and kind in {"paralog", "paralog_or_xenolog", "putative_homolog", "unassigned"}:
            from .phylo import place_query
            placement = place_query(profile.query_id, cand_aa, labeled, settings)
            if placement.get("clade") == "paralog":
                kind = "paralog"
                ortho_conflicts.append("phylogenetic_paralog")
            elif placement.get("clade") == "ortholog" and "paralogous_copies" not in ortho_conflicts:
                kind = "ortholog"
        similarity["orthology_class"] = kind
        similarity["placement"] = placement
        conflicts = list(dict.fromkeys(ortho_conflicts + synteny_conflicts))
        tax = None
        if candidate:
            tax = ((contig_taxonomy or {}).get(candidate["contig"]) or {}).get("taxonomy")
        declared = profile.expected_taxonomy
        if tax and declared:
            if declared.lower() not in str(tax).lower() and str(tax).lower() not in declared.lower():
                conflicts.append("taxonomic_inconsistency")
        q_up, _, q_down = flanks(query_genes, settings.thresholds.synteny_flank_genes)
        r_up, _, r_down = flanks(ref_genes, settings.thresholds.synteny_flank_genes)
        records.append(LocusEvidence(
            target=profile.query_id,
            candidate_locus=candidate,
            reference_genome=ref.get("id"),
            orthologues=orthos,
            gene_order=query_genes,
            orientation=candidate["strand"] if candidate else None,
            distance={
                "query": q_dist,
                "reference": r_dist,
                "query_upstream": names(q_up),
                "query_downstream": names(q_down),
                "reference_upstream": names(r_up),
                "reference_downstream": names(r_down),
                "assembly_neighbor_products": names(genes_from_features(assembly_features, None)),
                "reference_neighbor_products": [g.product for g in ref_genes if not g.is_target],
            },
            sequence_similarity=similarity,
            coverage=coverage or {},
            conflicts=conflicts,
            provenance={
                "created_by": "deterministic_locus_validator",
                "reference_id": ref.get("id"),
                "reference_gff": ref.get("gff"),
                "tools": tools_run or ["internal_gene_search"],
                "notes": "LLM did not invent orthologues, identities, gene order, or reciprocal hits.",
            },
        ))
    return records
