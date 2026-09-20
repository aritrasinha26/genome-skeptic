from __future__ import annotations

import json
from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.io_utils import read_fasta
from genome_skeptic.models import Claim, GeneSearchHit, LocusEvidence, TargetType
from genome_skeptic.isolation import assert_agent_accessible
from genome_skeptic.targets import load_target_profiles
from genome_skeptic.tools.breaks import run_break_analysis
from genome_skeptic.tools.gene_search import is_nucleotide, parse_gff_features, neighborhood_for_hits, run_gene_search, search_proteins, translate_frame, local_coverage_for_hits
from genome_skeptic.tools.similarity import run_preferred_similarity_search, similarity_tools_available
from genome_skeptic.tools.taxonomy import run_contig_taxonomy
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim
from genome_skeptic.validators.gene_target import hits_from_metrics

from .references import load_reference_set
from .validate import build_locus_evidence


def _write_fa(path: Path, records: list[tuple[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f">{name}\n{seq}\n" for name, seq in records if seq))
    return path


def _preferred_tool_hits(query_proteins: list[tuple[str, str]], ref_proteins: list[tuple[str, str]], out_dir: Path, settings: Settings) -> list[GeneSearchHit]:
    """Use MMseqs2 or DIAMOND when present. Never invent hits if they are missing."""
    if not query_proteins or not ref_proteins or not similarity_tools_available():
        return []
    qfa = _write_fa(out_dir / "query.faa", query_proteins)
    tfa = _write_fa(out_dir / "ref.faa", ref_proteins)
    result = run_preferred_similarity_search(qfa, tfa, out_dir / "preferred", settings, "protein")
    if not result.ok:
        return []
    return hits_from_metrics(result.metrics)


def analyze_targets_on_assembly(
    *,
    targets: Path,
    assembly: Path,
    settings: Settings,
    assembly_gff: Path | None = None,
    proteins: Path | None = None,
    references_yaml: Path | None = None,
    out_dir: Path,
    declared_organism: str | None = None,
    mapping_sam: Path | None = None,
    depth_tsv: Path | None = None,
) -> tuple[list[Claim], list[LocusEvidence], list]:
    """Gene-search + locus validation + claims. Does not read evaluation ground truth."""
    assert_agent_accessible(targets)
    assert_agent_accessible(assembly)
    assert_agent_accessible(assembly_gff)
    assert_agent_accessible(proteins)
    assert_agent_accessible(references_yaml)
    assert_agent_accessible(mapping_sam)
    out_dir.mkdir(parents=True, exist_ok=True)
    search = run_gene_search(targets, assembly, out_dir / "search", settings)
    hits = hits_from_metrics(search.metrics) if search.ok else []
    profiles = load_target_profiles(str(targets))
    contig_seqs = dict(read_fasta(assembly))
    feats = parse_gff_features(assembly_gff) if assembly_gff and assembly_gff.exists() else []
    prot = dict(read_fasta(proteins)) if proteins and proteins.exists() else {}
    refs = load_reference_set(references_yaml) if references_yaml and Path(references_yaml).exists() else []
    tools_run = ["internal_gene_search"]
    tools_unavailable: list[str] = []
    if feats:
        tools_run.append("gff_synteny")
    if similarity_tools_available():
        tools_run.extend(similarity_tools_available())

    contig_taxonomy: dict[str, dict] = {}
    tax_db = settings.paths.taxonomy_db
    if tax_db:
        tax = run_contig_taxonomy(assembly, out_dir / "taxonomy", tax_db, settings.project.threads)
        if tax.ok:
            contig_taxonomy = tax.metrics.get("by_contig") or {}
            tools_run.append(tax.name)
        else:
            tools_unavailable.append("contig_taxonomy")
    else:
        tools_unavailable.append("contig_taxonomy")

    break_evidence: dict[str, dict] = {}
    mapping_available = bool(mapping_sam and Path(mapping_sam).exists()) and settings.execution.enable_mapping_breaks
    if mapping_available:
        loci_spec = [
            {
                "contig": h.contig_id,
                "start": min(h.tstart, h.tend),
                "end": max(h.tstart, h.tend),
                "contig_length": h.contig_length or len(contig_seqs.get(h.contig_id, "")),
            }
            for h in hits if h.search_kind == "nucleotide"
        ]
        if loci_spec:
            br = run_break_analysis(Path(mapping_sam), out_dir / "breaks", loci_spec)
            break_evidence = br.metrics.get("by_locus") or {}
            tools_run.append("break_analysis")

    if depth_tsv is None and mapping_sam:
        cand = Path(mapping_sam).with_name("depth.tsv")
        if cand.exists():
            depth_tsv = cand
    depth_available = bool(depth_tsv and Path(depth_tsv).exists())
    coverage_by_hit: dict[str, dict] = {}
    depth_evidence_ids: list[str] = []
    if depth_available:
        coverage_by_hit = local_coverage_for_hits(depth_tsv, hits) if hits else {}
        tools_run.append("samtools_depth")
        depth_evidence_ids.extend(["E_local_read_depth", "E_relative_locus_coverage", "E_coverage_discontinuity"])
        (out_dir / "depth_coverage.json").write_text(json.dumps({
            "depth_tsv": str(depth_tsv),
            "by_hit": coverage_by_hit,
            "reused_existing_depth": True,
            "evidence_ids": list(depth_evidence_ids),
            "provenance": {"created_by": "existing_depth.tsv", "regenerated_mapping": False},
        }, indent=2))
    else:
        tools_unavailable.append("local_read_depth")
    if break_evidence:
        depth_evidence_ids.append("E_contig_break")

    all_claims: list[Claim] = []
    all_loci: list[LocusEvidence] = []
    anomalies = []
    for profile in profiles:
        if declared_organism and not profile.expected_taxonomy:
            profile.expected_taxonomy = declared_organism
        q_hits = [h for h in hits if h.query_id == profile.query_id]
        qaa = profile.sequence
        if qaa and is_nucleotide(qaa):
            qaa = max((translate_frame(qaa.upper(), f) for f in range(3)), key=len).split("*")[0]
        if prot and qaa:
            q_hits.extend(search_proteins(profile.query_id, qaa, list(prot.items()), settings))
        neighborhood = neighborhood_for_hits(feats, q_hits) if feats and q_hits else {}
        tool_hits_by_reference: dict[str, list] = {}
        cand_pairs = [(profile.query_id, qaa)] if qaa else []
        for ref in refs:
            ref_prot = list((ref.get("protein_sequences") or {}).items())
            if not ref_prot:
                continue
            tool_hits = _preferred_tool_hits(cand_pairs, ref_prot, out_dir / "orthology" / str(ref.get("id") or "ref"), settings)
            if tool_hits:
                tool_hits_by_reference[str(ref.get("id") or "")] = tool_hits
        loci = build_locus_evidence(
            profile=profile,
            hits=q_hits,
            settings=settings,
            assembly_features=feats,
            contig_sequences=contig_seqs,
            query_proteins=prot,
            references=refs,
            tools_run=tools_run,
            tool_hits_by_reference=tool_hits_by_reference,
            break_evidence=break_evidence,
            contig_taxonomy=contig_taxonomy,
            mapping_available=mapping_available,
        )
        all_loci.extend(loci)
        phy = {}
        for le in loci:
            placed = (le.sequence_similarity or {}).get("placement") or {}
            if placed:
                phy = placed
                break
        measurements = TargetMeasurements(
            query_id=profile.query_id,
            profile=profile,
            hits=q_hits,
            contig_sequences=contig_seqs,
            protein_sequences=prot,
            neighborhood_by_hit=neighborhood,
            coverage_by_hit={k: v for k, v in coverage_by_hit.items() if k.startswith(f"{profile.query_id}:")},
            annotation_available=bool(feats),
            proteins_available=bool(prot),
            locus_evidence=loci,
            tools_run=tools_run,
            tools_unavailable=tools_unavailable,
            falsification_enabled=settings.execution.enable_falsification,
            break_evidence=break_evidence,
            contig_taxonomy=contig_taxonomy,
            phylogeny=phy,
            mapping_available=mapping_available,
            depth_available=depth_available,
            declared_organism=declared_organism,
            depth_evidence_ids=depth_evidence_ids,
        )
        if profile.target_type != TargetType.exact_allele:
            from genome_skeptic.validators.family_orthology import collect_family_evidence
            try:
                fam_ev = collect_family_evidence(
                    profile=profile,
                    assembly=assembly,
                    contig_sequences=contig_seqs,
                    proteins=prot,
                    query_hits=q_hits,
                    settings=settings,
                    out_dir=out_dir / "family" / profile.query_id,
                    locus_evidence=loci,
                )
                measurements.family_evidence = fam_ev
                measurements.tools_run = list(dict.fromkeys(list(tools_run) + list(fam_ev.tools_run or [])))
                measurements.limitations.extend(fam_ev.limitations or [])
                if fam_ev.reconstruction:
                    (out_dir / "family" / profile.query_id / "locus_reconstruction.json").write_text(
                        json.dumps(fam_ev.reconstruction, indent=2, default=str), encoding="utf-8"
                    )
                if "HMMER unavailable" in " ".join(fam_ev.limitations or []):
                    measurements.tools_unavailable = list(dict.fromkeys(list(tools_unavailable) + ["hmmsearch"]))
            except Exception as exc:
                measurements.limitations.append(f"family orthology failed: {exc}")
        claim, anoms, _tests = build_target_gene_claim(measurements, settings, [])
        all_claims.append(claim)
        anomalies.extend(anoms)
    (out_dir / "locus_evidence.json").write_text(json.dumps([le.model_dump() for le in all_loci], indent=2))
    (out_dir / "claims.json").write_text(json.dumps([c.model_dump(mode="json") for c in all_claims], indent=2))
    return all_claims, all_loci, anomalies
