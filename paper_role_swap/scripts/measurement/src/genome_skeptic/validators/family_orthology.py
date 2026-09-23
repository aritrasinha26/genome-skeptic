"""Family-aware orthology: multi-reference hits, profile-HMM, fusion/split/fragment tests.

Pairwise identity against a single reference is not sufficient to reject a candidate
when family-profile evidence supports orthology. Domain-only hits are not full orthologues.
No species-name special cases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.families import family_paths, load_family, resolve_family_for_profile
from genome_skeptic.models import GeneSearchHit, TargetFamily, TargetProfile, TargetType
from genome_skeptic.tools.gene_search import extract_orfs, is_nucleotide, run_gene_search, search_proteins, translate_frame
from genome_skeptic.tools.hmmer import hmmer_tools_available, run_hmmbuild, run_hmmsearch
from genome_skeptic.validators.homology import strong_hit


def _query_aa(profile: TargetProfile) -> str | None:
    seq = profile.sequence or ""
    if not seq:
        return None
    if is_nucleotide(seq):
        aa = max((translate_frame(seq.upper(), f) for f in range(3)), key=len)
        return aa.replace("*", "") or None
    return seq


def _write_fa(path: Path, records: list[tuple[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f">{name}\n{seq}\n" for name, seq in records if seq), encoding="utf-8")
    return path


def _union_coverage(hits: list[GeneSearchHit], query_length: int) -> float:
    if query_length <= 0 or not hits:
        return 0.0
    covered = [False] * query_length
    for hit in hits:
        for i in range(max(0, hit.qstart), min(query_length, hit.qend)):
            covered[i] = True
    return sum(covered) / query_length


@dataclass
class FamilyEvidence:
    family_id: str | None = None
    member_hits: list[GeneSearchHit] = field(default_factory=list)
    partner_hits: list[GeneSearchHit] = field(default_factory=list)
    hmm_by_target: dict = field(default_factory=dict)
    partner_hmm_by_target: dict = field(default_factory=dict)
    architecture: str = "absent"
    hierarchy: list[str] = field(default_factory=list)
    supports_orthologue: bool = False
    domain_only: bool = False
    fusion: dict = field(default_factory=dict)
    split: dict = field(default_factory=dict)
    fragmented: dict = field(default_factory=dict)
    paralogue: dict = field(default_factory=dict)
    reconstruction: dict = field(default_factory=dict)
    best_hmm: dict | None = None
    metrics: dict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    tools_run: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "family_id": self.family_id,
            "n_member_hits": len(self.member_hits),
            "architecture": self.architecture,
            "hierarchy": list(self.hierarchy),
            "supports_orthologue": self.supports_orthologue,
            "domain_only": self.domain_only,
            "fusion": self.fusion,
            "split": self.split,
            "fragmented": self.fragmented,
            "paralogue": self.paralogue,
            "reconstruction": self.reconstruction,
            "competitive_family": (self.reconstruction or {}).get("competitive_family"),
            "multiplicity": (self.reconstruction or {}).get("multiplicity"),
            "best_hmm": self.best_hmm,
            "metrics": self.metrics,
            "limitations": self.limitations,
            "tools_run": self.tools_run,
            "provenance": self.provenance,
            "member_hit_summaries": [
                {
                    "query_id": h.query_id,
                    "contig_id": h.contig_id,
                    "identity": h.identity,
                    "query_coverage": h.query_coverage,
                    "search_kind": h.search_kind,
                    "evalue": h.evalue,
                    "near_contig_edge": h.near_contig_edge,
                    "tstart": h.tstart,
                    "tend": h.tend,
                    "strand": h.strand,
                }
                for h in self.member_hits[:30]
            ],
        }


def _ensure_family_hmm(family: TargetFamily, out_dir: Path) -> Path | None:
    paths = family_paths(family.family_id)
    packaged = paths["hmm"]
    if packaged.exists() and packaged.stat().st_size > 0:
        return packaged
    src = paths["alignment"] if paths["alignment"].exists() else paths["members"]
    if not src.exists():
        return None
    dest = out_dir / f"{family.family_id}.hmm"
    built = run_hmmbuild(src, dest, out_dir / "hmmbuild")
    if built.ok:
        out = Path(built.outputs.get("hmm") or dest)
        return out if out.exists() else None
    return None


def _search_members(family: TargetFamily, assembly: Path, proteins: list[tuple[str, str]], out_dir: Path, settings: Settings) -> list[GeneSearchHit]:
    hits: list[GeneSearchHit] = []
    recs = [(m.protein_id, m.sequence) for m in family.members if m.sequence]
    if not recs:
        return hits
    fa = _write_fa(out_dir / f"{family.family_id}_members.faa", recs)
    search = run_gene_search(fa, assembly, out_dir / f"search_{family.family_id}", settings)
    if search.ok:
        from genome_skeptic.validators.gene_target import hits_from_metrics
        hits.extend(hits_from_metrics(search.metrics))
    if proteins:
        for pid, seq in recs:
            hits.extend(search_proteins(pid, seq, proteins, settings))
    forbidden = set(family.forbidden_protein_ids or [])
    return [h for h in hits if h.query_id not in forbidden]


def _hmm_search_family(family: TargetFamily, seq_fa: Path, out_dir: Path, settings: Settings) -> tuple[dict, list[str]]:
    limitations: list[str] = []
    if "hmmsearch" not in hmmer_tools_available() or "hmmbuild" not in hmmer_tools_available():
        limitations.append("HMMER unavailable; profile-HMM evidence was not invented")
        return {}, limitations
    hmm = _ensure_family_hmm(family, out_dir)
    if hmm is None:
        limitations.append(f"family HMM could not be built for {family.family_id}")
        return {}, limitations
    result = run_hmmsearch(hmm, seq_fa, out_dir / f"hmmsearch_{family.family_id}", settings.project.threads)
    if not result.ok:
        limitations.append(result.error or "hmmsearch failed")
        return {}, limitations
    by_target = result.metrics.get("by_target") or {}
    return by_target, limitations


def _supporting_members(hits: list[GeneSearchHit], family: TargetFamily, settings: Settings) -> list[dict]:
    t = settings.thresholds
    by_member: dict[str, GeneSearchHit] = {}
    for hit in hits:
        if hit.search_kind == "nucleotide":
            continue
        prev = by_member.get(hit.query_id)
        score = hit.identity * hit.query_coverage
        if prev is None or score > prev.identity * prev.query_coverage:
            by_member[hit.query_id] = hit
    rows = []
    for member in family.members:
        hit = by_member.get(member.protein_id)
        if hit is None:
            continue
        if hit.identity >= t.family_member_min_identity and hit.query_coverage >= t.family_member_min_coverage:
            rows.append(
                {
                    "protein_id": member.protein_id,
                    "species": member.species,
                    "identity": hit.identity,
                    "query_coverage": hit.query_coverage,
                    "contig_id": hit.contig_id,
                    "search_kind": hit.search_kind,
                }
            )
    return rows


def _best_hmm(by_target: dict, settings: Settings) -> dict | None:
    if not by_target:
        return None
    ranked = [v for v in by_target.values() if v]
    if not ranked:
        return None
    return min(ranked, key=lambda h: (h.get("full_evalue") if h.get("full_evalue") is not None else 1e9, -(h.get("model_coverage") or 0)))


def _hmm_full_match(hmm: dict | None, settings: Settings) -> bool:
    if not hmm:
        return False
    t = settings.thresholds
    ev = hmm.get("full_evalue")
    cov = hmm.get("model_coverage") or 0.0
    if ev is None:
        return False
    return ev <= t.hmm_full_evalue_max and cov >= t.hmm_model_coverage_orthologue


def _hmm_domain_only(hmm: dict | None, settings: Settings) -> bool:
    if not hmm:
        return False
    cov = hmm.get("model_coverage") or 0.0
    n_dom = hmm.get("n_domains") or 0
    if cov <= settings.thresholds.hmm_domain_only_max_model_coverage and n_dom:
        return True
    return False


def _parse_orf_id(orf_id: str) -> dict | None:
    # contig:start-end:strand  (contig may contain colons in rare cases; split from right)
    try:
        contig_span, strand = orf_id.rsplit(":", 1)
        contig, span = contig_span.rsplit(":", 1)
        start_s, end_s = span.split("-", 1)
        return {"contig_id": contig, "start": int(start_s), "end": int(end_s), "strand": strand, "orf_id": orf_id}
    except ValueError:
        return None


def _family_fraction_of_orf(orf: dict, hits: list[GeneSearchHit]) -> float:
    """Fraction of the ORF spanned by family hits. Near 1.0 means a long RpoB, not extra fusion sequence."""
    length = max(1, int(orf["end"]) - int(orf["start"]))
    intervals = []
    for h in hits:
        if not _hit_overlaps_orf(h, orf):
            continue
        if h.contig_id == orf.get("orf_id"):
            intervals.append((0, length))
            continue
        hs, he = min(h.tstart, h.tend), max(h.tstart, h.tend)
        lo = max(int(orf["start"]), hs)
        hi = min(int(orf["end"]), he)
        if hi > lo:
            intervals.append((lo - int(orf["start"]), hi - int(orf["start"])))
    if not intervals:
        return 0.0
    intervals.sort()
    merged = [list(intervals[0])]
    for a, b in intervals[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    covered = sum(b - a for a, b in merged)
    return min(1.0, covered / length)


def _hit_overlaps_orf(hit: GeneSearchHit, orf: dict | None) -> bool:
    """Partner-family evidence must sit inside the candidate ORF, not merely on the same contig.

    Adjacent rpoB/rpoC genes in an operon are not a fusion.
    """
    if not orf:
        return False
    if hit.contig_id == orf.get("orf_id"):
        return True
    if hit.contig_id != orf.get("contig_id"):
        return False
    hs, he = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
    return hs < int(orf["end"]) and he > int(orf["start"])


def _architecture(
    *,
    family: TargetFamily,
    member_hits: list[GeneSearchHit],
    hmm_by_target: dict,
    partner_hmm: dict,
    partner_hits: list[GeneSearchHit],
    orfs: list[dict],
    settings: Settings,
) -> tuple[str, dict, dict, dict, dict]:
    t = settings.thresholds
    expected = family.expected_length_aa or 0
    orf_by_id = {o["orf_id"]: o for o in orfs}
    best_hmm = _best_hmm(hmm_by_target, settings)
    fusion = {"state": "not_fusion", "supported": False}
    split = {"state": "not_split", "supported": False}
    fragmented = {"state": "not_fragmented", "supported": False}
    paralogue = {"state": "single_locus", "supported": False}

    genomic = [h for h in member_hits if h.search_kind in {"translated", "nucleotide"}]
    proteinish = [h for h in member_hits if h.search_kind in {"translated", "protein"}]

    clusters: list[dict] = []
    window = 2000
    genomic_loci = [
        h for h in genomic
        if h.identity >= t.family_member_min_identity and h.query_coverage >= 0.20
    ]
    for h in sorted(genomic_loci, key=lambda x: (x.contig_id, min(x.tstart, x.tend))):
        start = min(h.tstart, h.tend)
        placed = False
        for cl in clusters:
            if cl["contig"] == h.contig_id and abs(start - cl["start"]) < window:
                placed = True
                break
        if not placed:
            clusters.append({"contig": h.contig_id, "start": start, "strand": h.strand})
    if len(clusters) >= 2:
        paralogue = {"state": "multiple_loci", "n_loci": len(clusters), "supported": True}

    # Fusion: long ORF with family region inside + partner family on extra sequence
    # of the SAME ORF. Adjacent operon genes on the same contig are not a fusion.
    fusion_candidates = []
    if expected:
        for orf in orfs:
            if orf["length_aa"] < t.fusion_length_ratio_min * expected:
                continue
            covering = [
                h for h in proteinish
                if _hit_overlaps_orf(h, orf) and h.query_coverage >= t.family_member_min_coverage
            ]
            if not covering:
                continue
            family_orf_frac = _family_fraction_of_orf(orf, covering)
            extra_supported = False
            partner_row = None
            phmm = partner_hmm.get(orf["orf_id"]) if partner_hmm else None
            if phmm and phmm.get("full_evalue") is not None and phmm["full_evalue"] <= t.fusion_partner_evalue_max:
                extra_supported = True
                partner_row = phmm
            for ph in partner_hits:
                if not _hit_overlaps_orf(ph, orf):
                    continue
                if ph.query_coverage >= 0.40:
                    extra_supported = True
                    partner_row = {
                        "identity": ph.identity,
                        "query_coverage": ph.query_coverage,
                        "query_id": ph.query_id,
                        "tool": ph.tool,
                    }
                    break
            if not extra_supported:
                continue
            if family_orf_frac >= 0.90:
                continue
            fusion_candidates.append(
                {
                    "orf_id": orf["orf_id"],
                    "orf_length_aa": orf["length_aa"],
                    "expected_family_aa": expected,
                    "length_ratio": orf["length_aa"] / expected,
                    "family_hit_coverage": max(h.query_coverage for h in covering),
                    "family_fraction_of_orf": round(family_orf_frac, 4),
                    "partner_family_hit": partner_row,
                    "additional_sequence_known_family": extra_supported,
                    "evidence_type": "long_orf_family_region",
                }
            )
    for tid, hmm in hmm_by_target.items():
        if not hmm:
            continue
        orf = orf_by_id.get(tid)
        length = (orf or {}).get("length_aa") or hmm.get("query_length") or 0
        if expected and length >= t.fusion_length_ratio_min * expected and _hmm_full_match(hmm, settings):
            extra_supported = False
            partner_row = partner_hmm.get(tid) if partner_hmm else None
            if partner_row and partner_row.get("full_evalue") is not None and partner_row["full_evalue"] <= t.fusion_partner_evalue_max:
                extra_supported = True
            if not extra_supported:
                for ph in partner_hits:
                    if not _hit_overlaps_orf(ph, orf):
                        continue
                    if ph.identity >= 0.30 and ph.query_coverage >= 0.40:
                        extra_supported = True
                        partner_row = {"identity": ph.identity, "query_coverage": ph.query_coverage, "query_id": ph.query_id, "tool": ph.tool}
                        break
            family_orf_frac = float(hmm.get("query_coverage") or 0.0)
            if extra_supported and family_orf_frac < 0.90:
                fusion_candidates.append(
                    {
                        "orf_id": tid,
                        "orf_length_aa": length,
                        "expected_family_aa": expected,
                        "length_ratio": (length / expected) if expected else None,
                        "family_fraction_of_orf": round(family_orf_frac, 4),
                        "family_hmm": {k: hmm.get(k) for k in ("full_evalue", "full_score", "model_coverage", "query_coverage", "n_domains", "domain_order")},
                        "partner_family_hit": partner_row,
                        "additional_sequence_known_family": extra_supported,
                    }
                )
    if fusion_candidates:
        best_f = max(fusion_candidates, key=lambda r: (r.get("length_ratio") or 0))
        fusion = {**best_f, "state": "fusion", "supported": True}

    # Split: two adjacent ORFs, same contig/strand, combined HMM/model coverage, correct order.
    hmm_orfs = []
    for tid, hmm in hmm_by_target.items():
        loc = _parse_orf_id(tid)
        if not loc or not hmm:
            continue
        hmm_orfs.append((loc, hmm))
    hmm_orfs.sort(key=lambda x: (x[0]["contig_id"], x[0]["start"]))
    for i, (a, ha) in enumerate(hmm_orfs):
        for b, hb in hmm_orfs[i + 1 : i + 4]:
            if a["contig_id"] != b["contig_id"] or a["strand"] != b["strand"]:
                continue
            if a["near_contig_edge"] if False else False:
                pass
            orf_a = orf_by_id.get(a["orf_id"]) or {}
            orf_b = orf_by_id.get(b["orf_id"]) or {}
            if orf_a.get("near_contig_edge") or orf_b.get("near_contig_edge"):
                continue
            gap = b["start"] - a["end"]
            if gap < 0 or gap > t.split_max_intergenic_bp:
                continue
            # Model order: first ORF should cover earlier HMM coordinates than the second.
            a_hmm_from = min((d.get("hmm_from") or 0) for d in (ha.get("domains") or [{"hmm_from": 0}]))
            b_hmm_from = min((d.get("hmm_from") or 0) for d in (hb.get("domains") or [{"hmm_from": 0}]))
            if a["strand"] == "-" :
                ordered = b_hmm_from <= a_hmm_from
            else:
                ordered = a_hmm_from <= b_hmm_from
            combined_model = min(1.0, (ha.get("model_coverage") or 0) + (hb.get("model_coverage") or 0))
            if ordered and combined_model >= t.hmm_model_coverage_orthologue:
                split = {
                    "state": "biological_split",
                    "supported": True,
                    "orfs": [a["orf_id"], b["orf_id"]],
                    "gap_bp": gap,
                    "combined_model_coverage": round(combined_model, 4),
                    "domain_order_consistent": True,
                }
                break
        if split["supported"]:
            break

    # Assembly fragmentation: family coverage split across contigs or contig-edge truncated pieces.
    # Assembly fragmentation: the best family-supported region is broken across contigs
    # or truncated at a contig end. Stray HSPs near other edges are not a biological state.
    best_orf = orf_by_id.get((best_hmm or {}).get("target_id") or "")
    best_orf_edge = bool(best_orf and best_orf.get("near_contig_edge"))
    qlen = next((h.query_length for h in member_hits if h.query_length), expected or 0)
    combined = _union_coverage([h for h in member_hits if h.search_kind != "domain"], qlen) if qlen else 0.0
    n_contigs = len({h.contig_id for h in genomic})
    if not fusion["supported"] and not split["supported"] and not _hmm_domain_only(best_hmm, settings):
        if n_contigs > 1 and combined >= t.family_member_min_coverage and not _hmm_full_match(best_hmm, settings):
            fragmented = {
                "state": "assembly_fragmented",
                "supported": True,
                "n_contigs": n_contigs,
                "combined_query_span": round(combined, 4),
                "best_orf_edge": best_orf_edge,
                "not_biological_split": True,
            }
        elif best_orf_edge and (best_hmm or {}).get("model_coverage", 0) < t.hmm_model_coverage_orthologue:
            fragmented = {
                "state": "assembly_fragmented",
                "supported": True,
                "n_contigs": n_contigs,
                "combined_query_span": round(combined, 4),
                "best_orf_edge": True,
                "not_biological_split": True,
            }

    canonical_hmm = bool(best_hmm and _hmm_full_match(best_hmm, settings))
    fusion_is_best = bool(fusion.get("orf_id") and fusion.get("orf_id") == (best_hmm or {}).get("target_id"))
    domain_only_arch = bool(_hmm_domain_only(best_hmm, settings) and not canonical_hmm)

    if fusion["supported"] and (fusion_is_best or not canonical_hmm):
        arch = "fusion"
    elif split["supported"]:
        arch = "biological_split"
    elif domain_only_arch:
        arch = "domain_only"
    elif fragmented["supported"]:
        arch = "assembly_fragmented"
    elif paralogue.get("supported") and not _hmm_full_match(best_hmm, settings) and not any(
        strong_hit(h, settings, TargetType.gene_orthologue) for h in proteinish
    ):
        arch = "close_paralogue"
    elif _hmm_full_match(best_hmm, settings) or any(h.identity >= 0.60 and h.query_coverage >= 0.80 for h in proteinish):
        best_id = max((h.identity for h in proteinish), default=0.0)
        arch = "canonical_full_length" if best_id >= 0.60 else "divergent_full_length"
    elif proteinish:
        arch = "divergent_full_length"
    else:
        arch = "absent"
    return arch, fusion, split, fragmented, paralogue


def classify_family_orthology(ev: FamilyEvidence, family: TargetFamily, settings: Settings, *, query_hits: list[GeneSearchHit], locus_evidence: list | None = None) -> FamilyEvidence:
    """Hierarchy: exact strong homolog → multi-reference → HMM → RBH → synteny → phylogeny if needed."""
    t = settings.thresholds
    supporting = _supporting_members(ev.member_hits, family, settings)
    exact = []
    for h in ev.member_hits + query_hits:
        if h.search_kind in {"translated", "protein"} and strong_hit(h, settings, TargetType.gene_orthologue):
            exact.append(h)
    hmm_full = _hmm_full_match(ev.best_hmm, settings)
    domain_only = _hmm_domain_only(ev.best_hmm, settings) and not hmm_full
    ev.domain_only = domain_only

    hierarchy: list[str] = []
    if exact:
        hierarchy.append("exact_strong_homolog")
    if len(supporting) >= t.family_min_supporting_members:
        hierarchy.append("multi_reference_protein_homolog")
    if hmm_full:
        hierarchy.append("profile_hmm_family_match")

    rbh = None
    synteny_ok = None
    phylo = None
    for le in locus_evidence or []:
        sim = le.sequence_similarity or {}
        if any(o.reciprocal_best_hit is True for o in (le.orthologues or [])):
            rbh = True
        elif any(o.reciprocal_best_hit is False for o in (le.orthologues or [])):
            rbh = False if rbh is None else rbh
        if sim.get("orthology_class") == "ortholog":
            synteny_ok = True
        conflicts = set(le.conflicts or [])
        if "gene_order_mismatch" in conflicts or "missing_flanking_orthologues" in conflicts:
            synteny_ok = False if synteny_ok is None else synteny_ok
        placed = (sim.get("placement") or {})
        if placed:
            phylo = placed

    cheaper_ambiguous = (not exact) and (len(supporting) < t.family_min_supporting_members) and not hmm_full
    if rbh is True:
        hierarchy.append("reciprocal_best_hit")
    elif rbh is False and cheaper_ambiguous:
        hierarchy.append("reciprocal_best_hit_rejected")
    if synteny_ok is True:
        hierarchy.append("synteny")
    if cheaper_ambiguous and phylo:
        hierarchy.append("phylogenetic_placement")

    supports = bool(
        exact
        or len(supporting) >= t.family_min_supporting_members
        or hmm_full
        or ev.fusion.get("supported")
        or ev.split.get("supported")
        or (ev.fragmented.get("supported") and (ev.fragmented.get("combined_query_span") or 0) >= t.family_member_min_coverage)
    )
    recon = ev.reconstruction or {}
    recon_arch = recon.get("architecture") or ev.architecture
    recon_cov = float(recon.get("hmm_coverage") or 0.0)
    if recon_arch in {"canonical_full_length", "divergent_full_length", "fusion", "biological_split", "close_paralogue"} and recon_cov >= t.hmm_unresolved_model_coverage:
        supports = True
    if recon_arch == "assembly_fragmented" and recon_cov >= t.hmm_unresolved_model_coverage:
        supports = True
    if recon_arch == "unresolved_candidate" and recon_cov >= t.hmm_model_coverage_orthologue:
        supports = True
    if recon_arch in {"domain_only", "true_no_candidate"}:
        supports = False
    competitive = recon.get("competitive_family") or {}
    if competitive.get("competitors_scored") or (family.competing_families):
        cls = competitive.get("classification")
        if cls == "target_family_supported":
            supports = True
        elif cls in {"competing_family_preferred", "domain_only", "ambiguous_family"}:
            supports = False
    if domain_only:
        supports = False
    ev.hierarchy = hierarchy
    ev.supports_orthologue = supports
    ev.metrics.update(
        {
            "n_supporting_members": len(supporting),
            "supporting_members": supporting,
            "n_family_members": len(family.members),
            "reference_set_agreement": (len(supporting) / len(family.members)) if family.members else 0.0,
            "hmm_model_coverage": (ev.best_hmm or {}).get("model_coverage"),
            "hmm_query_coverage": (ev.best_hmm or {}).get("query_coverage"),
            "hmm_full_evalue": (ev.best_hmm or {}).get("full_evalue"),
            "hmm_full_score": (ev.best_hmm or {}).get("full_score"),
            "hmm_n_domains": (ev.best_hmm or {}).get("n_domains"),
            "hmm_domain_order": (ev.best_hmm or {}).get("domain_order"),
            "domain_completeness": (ev.best_hmm or {}).get("domain_completeness"),
            "best_member_identity": max((h.identity for h in ev.member_hits), default=None),
            "best_member_coverage": max((h.query_coverage for h in ev.member_hits), default=None),
            "domain_only": domain_only,
            "pairwise_identity_not_used_as_sole_reject": True,
            "competitive_family_classification": (recon.get("competitive_family") or {}).get("classification"),
            "multiplicity_classification": (recon.get("multiplicity") or {}).get("classification"),
        }
    )
    return ev


def collect_family_evidence(
    *,
    profile: TargetProfile,
    assembly: Path,
    contig_sequences: dict[str, str],
    proteins: dict[str, str],
    query_hits: list[GeneSearchHit],
    settings: Settings,
    out_dir: Path,
    locus_evidence: list | None = None,
) -> FamilyEvidence:
    ev = FamilyEvidence(provenance={"created_by": "deterministic_family_orthology", "llm_invented_scores": False})
    if profile.target_type not in {TargetType.gene_orthologue, TargetType.protein_family, None}:
        return ev
    if not settings.execution.enable_family_orthology:
        ev.limitations.append("family orthology disabled")
        return ev
    family = resolve_family_for_profile(profile, Path(settings.paths.family_dir) if settings.paths.family_dir else None)
    if family is None:
        ev.limitations.append("no curated family was configured; pairwise query search remains")
        return ev
    ev.family_id = family.family_id
    ev.provenance.update(
        {
            "family_id": family.family_id,
            "msa_provenance": family.msa_provenance,
            "hmm_provenance": family.hmm_provenance,
            "phylo_provenance": family.phylo_provenance,
            "n_reference_proteins": len(family.members),
            "reference_species": [m.species for m in family.members],
            "reference_protein_ids": [m.protein_id for m in family.members],
            "reference_gene_ids": [m.gene_id for m in family.members],
            "protein_lengths": [m.length_aa for m in family.members],
            "domain_architecture": family.domain_architecture,
            "known_fusion_or_split": family.known_fusion_or_split,
        }
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    prot_pairs = list(proteins.items())
    ev.member_hits = _search_members(family, assembly, prot_pairs, out_dir, settings)
    ev.tools_run.append("family_member_search")

    orfs = extract_orfs(list(contig_sequences.items()), min_aa=settings.thresholds.orf_min_aa, edge_bp=settings.thresholds.contig_edge_proximity_bp)
    expected = family.expected_length_aa or 0
    hit_windows = []
    for h in ev.member_hits:
        if h.search_kind in {"translated", "nucleotide"}:
            lo, hi = min(h.tstart, h.tend), max(h.tstart, h.tend)
            hit_windows.append((h.contig_id, max(0, lo - 3000), hi + 3000))
    if hit_windows:
        filtered = []
        for orf in orfs:
            if any(orf["contig_id"] == cid and orf["start"] < hi and orf["end"] > lo for cid, lo, hi in hit_windows):
                filtered.append(orf)
        orfs = filtered
    seq_records = [(o["orf_id"], o["sequence"]) for o in orfs]
    seq_fa = _write_fa(out_dir / "hmm_targets.faa", seq_records)
    hmm_by, hmm_lim = _hmm_search_family(family, seq_fa, out_dir, settings)
    ev.hmm_by_target = hmm_by
    ev.limitations.extend(hmm_lim)
    if hmm_by:
        ev.tools_run.append("hmmsearch")
    ev.best_hmm = _best_hmm(hmm_by, settings)

    partner_hmm: dict = {}
    partner_hits: list[GeneSearchHit] = []
    for pfid in family.partner_families:
        partner = load_family(pfid, Path(settings.paths.family_dir) if settings.paths.family_dir else None)
        if partner is None:
            ev.limitations.append(f"partner family {pfid} was not available")
            continue
        phits = _search_members(partner, assembly, prot_pairs, out_dir / "partner", settings)
        partner_hits.extend(phits)
        p_by, p_lim = _hmm_search_family(partner, seq_fa, out_dir / "partner", settings)
        partner_hmm.update(p_by)
        ev.limitations.extend(p_lim)
    ev.partner_hits = partner_hits
    ev.partner_hmm_by_target = partner_hmm

    recon_orfs = list(orfs)
    if settings.execution.enable_locus_reconstruction:
        from genome_skeptic.validators.locus_reconstruction import reconstruct_locus, window_orfs
        centers: list[tuple[str, int, int]] = []
        for h in ev.member_hits:
            if h.search_kind in {"translated", "nucleotide"}:
                centers.append((h.contig_id, min(h.tstart, h.tend), max(h.tstart, h.tend)))
        for o in orfs:
            centers.append((o["contig_id"], o["start"], o["end"]))
        if centers:
            recon_orfs = window_orfs(contig_sequences, centers, settings)
            extra = [(o["orf_id"], o["sequence"]) for o in recon_orfs]
            extra_fa = _write_fa(out_dir / "reconstruction_orfs.faa", extra)
            extra_hmm, extra_lim = _hmm_search_family(family, extra_fa, out_dir / "reconstruction", settings)
            hmm_by.update({k: v for k, v in extra_hmm.items() if v})
            ev.limitations.extend(extra_lim)
            ev.hmm_by_target = hmm_by
            ev.best_hmm = _best_hmm(hmm_by, settings)
            p_extra, p_lim = {}, []
            for pfid in family.partner_families:
                partner = load_family(pfid, Path(settings.paths.family_dir) if settings.paths.family_dir else None)
                if partner is None:
                    continue
                p_extra, p_lim = _hmm_search_family(partner, extra_fa, out_dir / "reconstruction" / "partner", settings)
                partner_hmm.update(p_extra)
                ev.limitations.extend(p_lim)
        rec = reconstruct_locus(
            family=family,
            contig_sequences=contig_sequences,
            member_hits=ev.member_hits,
            hmm_by_target=hmm_by,
            orfs=recon_orfs,
            partner_hits=partner_hits,
            partner_hmm=partner_hmm,
            settings=settings,
            proteins=proteins,
            query_hits=query_hits,
            query_aa=_query_aa(profile),
            locus_evidence=locus_evidence,
            out_dir=out_dir,
        )
        ev.reconstruction = rec.model_dump()
        arch = rec.architecture
        fusion = {"state": rec.architecture if rec.architecture == "fusion" else "not_fusion", "supported": rec.architecture == "fusion", **{k: rec.model_dump().get(k) for k in ("hmm_coverage", "contig", "genomic_start", "genomic_end")}}
        split = {"state": rec.architecture if rec.architecture == "biological_split" else "not_split", "supported": rec.architecture == "biological_split", "gaps": rec.inter_segment_gaps}
        fragmented = {"state": rec.architecture if rec.architecture == "assembly_fragmented" else "not_fragmented", "supported": rec.architecture == "assembly_fragmented", "contig_edge": rec.contig_edge, "combined_query_span": rec.hmm_coverage, "not_biological_split": rec.architecture == "assembly_fragmented"}
        paralogue = rec.paralogue_record or {"state": "single_locus", "supported": rec.architecture == "close_paralogue"}
        if rec.architecture == "close_paralogue":
            paralogue = {**paralogue, "state": "multiple_loci", "supported": True}
        ev.architecture = arch
        ev.fusion = fusion
        ev.split = split
        ev.fragmented = fragmented
        ev.paralogue = paralogue
        ev.domain_only = rec.architecture == "domain_only"
    else:
        arch, fusion, split, fragmented, paralogue = _architecture(
            family=family,
            member_hits=ev.member_hits,
            hmm_by_target=hmm_by,
            partner_hmm=partner_hmm,
            partner_hits=partner_hits,
            orfs=orfs,
            settings=settings,
        )
        ev.architecture = arch
        ev.fusion = fusion
        ev.split = split
        ev.fragmented = fragmented
        ev.paralogue = paralogue
    classify_family_orthology(ev, family, settings, query_hits=query_hits, locus_evidence=locus_evidence)
    if ev.reconstruction:
        rarch = ev.reconstruction.get("architecture")
        if rarch == "domain_only":
            ev.domain_only = True
            ev.supports_orthologue = False
        elif rarch in {"canonical_full_length", "divergent_full_length", "fusion", "biological_split", "close_paralogue"}:
            ev.domain_only = False
        elif rarch == "true_no_candidate":
            ev.domain_only = False
            ev.supports_orthologue = False
    (out_dir / "family_evidence.json").write_text(
        __import__("json").dumps(ev.as_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    return ev


def family_detects_orthologue(profile: TargetProfile, query_hits: list[GeneSearchHit], settings: Settings, family_evidence: FamilyEvidence | None) -> bool:
    if profile.target_type == TargetType.protein_family:
        if family_evidence and family_evidence.best_hmm:
            hmm = family_evidence.best_hmm
            ev = hmm.get("full_evalue")
            cov = hmm.get("model_coverage") or 0.0
            if ev is not None and ev <= 1e-5 and cov >= 0.30:
                return True
        return any(strong_hit(h, settings, profile.target_type) for h in query_hits)
    if profile.target_type == TargetType.gene_orthologue or profile.target_type is None:
        if family_evidence and family_evidence.domain_only:
            return False
        comp = ((family_evidence.reconstruction or {}).get("competitive_family") if family_evidence else None) or {}
        cls = comp.get("classification")
        if cls in {"competing_family_preferred", "ambiguous_family"}:
            return False
        if family_evidence and family_evidence.supports_orthologue:
            return True
        return any(strong_hit(h, settings, profile.target_type) for h in query_hits)
    return any(strong_hit(h, settings, profile.target_type) for h in query_hits)
