from __future__ import annotations

from dataclasses import dataclass, field

from genome_skeptic.claims.attack_plan import attack_plan_id, generate_attack_plan
from genome_skeptic.claims.confidence import confidence_for_target_type
from genome_skeptic.claims.state_machine import resolve_claim_status
from genome_skeptic.config import Settings
from genome_skeptic.models import (
    Anomaly,
    Claim,
    ClaimProvenance,
    ClaimStatus,
    ClaimType,
    FalsificationResult,
    FalsificationTest,
    GeneSearchHit,
    LocusEvidence,
    Severity,
    TargetProfile,
)
from genome_skeptic.tools.gene_search import is_nucleotide, reverse_complement, translate_frame
from genome_skeptic.validators.homology import (
    FORBIDDEN_ABSENCE_PHRASES,
    claim_id_for_query,
    homology_support_score,
    partial_hit,
    query_span_coverage,
    strong_hit,
)


@dataclass
class TargetMeasurements:
    query_id: str
    profile: TargetProfile
    hits: list[GeneSearchHit]
    coverage_by_hit: dict[str, dict] = field(default_factory=dict)
    neighborhood_by_hit: dict[str, dict] = field(default_factory=dict)
    contig_sequences: dict[str, str] = field(default_factory=dict)
    protein_sequences: dict[str, str] = field(default_factory=dict)
    contig_gc: dict[str, float] = field(default_factory=dict)
    genome_gc: float | None = None
    checkm_contamination: float | None = None
    measured_taxonomy: str | None = None
    tools_run: list[str] = field(default_factory=list)
    tools_unavailable: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    proteins_available: bool = False
    depth_available: bool = False
    annotation_available: bool = False
    locus_evidence: list[LocusEvidence] = field(default_factory=list)
    break_evidence: dict[str, dict] = field(default_factory=dict)
    contig_taxonomy: dict[str, dict] = field(default_factory=dict)
    phylogeny: dict = field(default_factory=dict)
    mapping_available: bool = False
    falsification_enabled: bool = True
    declared_organism: str | None = None
    depth_evidence_ids: list[str] = field(default_factory=list)
    family_evidence: object | None = None


def query_amino_acid(profile: TargetProfile) -> str:
    seq = profile.sequence.upper()
    if is_nucleotide(seq):
        aa = max((translate_frame(seq, f) for f in range(3)), key=len)
        return aa.split("*")[0] if aa else ""
    return seq.replace("*", "")


def classify_polarity(hits: list[GeneSearchHit], settings: Settings, target_type=None, family_evidence=None) -> ClaimType:
    from genome_skeptic.validators.family_orthology import family_detects_orthologue
    from genome_skeptic.models import TargetProfile, TargetType

    tt = target_type
    if family_evidence is not None and tt in {TargetType.gene_orthologue, TargetType.protein_family, None}:
        profile = TargetProfile(query_id="tmp", sequence="A", target_type=tt)
        if family_detects_orthologue(profile, hits, settings, family_evidence):
            return ClaimType.target_gene_detected
        # Family analysis already ran. Pairwise similarity cannot restore family identity
        # after a competitive-family or domain-only veto.
        return ClaimType.target_gene_not_detected
    strong = [h for h in hits if strong_hit(h, settings, target_type)]
    if strong:
        return ClaimType.target_gene_detected
    return ClaimType.target_gene_not_detected


def _loci(hits: list[GeneSearchHit], settings: Settings) -> list[GeneSearchHit]:
    t = settings.thresholds
    kept: list[GeneSearchHit] = []
    genomic = [h for h in hits if h.search_kind == "nucleotide"] or [h for h in hits if h.search_kind == "translated"]
    ranked_src = genomic if genomic else [h for h in hits if h.search_kind != "domain"]
    ranked = sorted(ranked_src, key=lambda h: h.identity * h.query_coverage, reverse=True)
    for hit in ranked:
        if hit.query_coverage < t.gene_paralogue_min_coverage:
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


def _best(hits: list[GeneSearchHit], kinds: set[str] | None = None) -> GeneSearchHit | None:
    subset = [h for h in hits if kinds is None or h.search_kind in kinds]
    if not subset:
        return None
    return max(subset, key=lambda h: (h.query_coverage * h.identity, h.alignment_length))


def _subject_residue(hit: GeneSearchHit, aa_pos: int, m: TargetMeasurements) -> str | None:
    if aa_pos < hit.qstart or aa_pos >= hit.qend:
        return None
    offset = aa_pos - hit.qstart
    if hit.search_kind == "protein":
        seq = m.protein_sequences.get(hit.contig_id, "")
        idx = hit.tstart + offset
        if 0 <= idx < len(seq):
            return seq[idx].upper()
        return None
    contig = m.contig_sequences.get(hit.contig_id, "")
    if not contig:
        return None
    if hit.search_kind == "nucleotide":
        query_nt_pos = aa_pos * 3
        if query_nt_pos < hit.qstart or query_nt_pos >= hit.qend:
            return None
        offset = query_nt_pos - hit.qstart
        if hit.strand == "+":
            nt_pos = hit.tstart + offset
            codon = contig[nt_pos:nt_pos + 3]
        else:
            nt_pos = hit.tend - offset - 3
            codon = reverse_complement(contig[nt_pos:nt_pos + 3])
        aa = translate_frame(codon, 0) if len(codon) == 3 else ""
        return aa[:1] or None
    if hit.strand == "+":
        nt_pos = hit.tstart + offset * 3
        codon = contig[nt_pos:nt_pos + 3]
    else:
        nt_pos = hit.tend - (offset + 1) * 3
        codon = reverse_complement(contig[nt_pos:nt_pos + 3])
    aa = translate_frame(codon, 0) if len(codon) == 3 else ""
    return aa[:1] or None


def _finish(test: FalsificationTest, status: str, result: FalsificationResult, metrics: dict, limitation: str | None = None) -> FalsificationTest:
    test.status = status  # type: ignore[assignment]
    test.result = result
    test.metrics = metrics
    test.limitation = limitation
    return test


def _take(by_id: dict, name: str) -> FalsificationTest | None:
    test = by_id.get(name)
    if test is None:
        return None
    if (test.limitation or "").startswith("VOI policy"):
        return None
    return test


def _skip(test: FalsificationTest, limitation: str, blocking: bool | None = None) -> FalsificationTest:
    if blocking is not None:
        test.blocking = blocking
    return _finish(test, "skipped", FalsificationResult.not_run, {}, limitation)


def _break_metrics(m: TargetMeasurements, hits: list[GeneSearchHit]) -> dict:
    best = _best([h for h in hits if h.search_kind != "domain"])
    if best is None:
        for key, rec in (m.break_evidence or {}).items():
            if rec:
                return rec
        return {}
    key = f"{best.contig_id}:{min(best.tstart, best.tend)}-{max(best.tstart, best.tend)}"
    if key in (m.break_evidence or {}):
        return m.break_evidence[key]
    for rec in (m.break_evidence or {}).values():
        if rec:
            return rec
    return {}


def execute_detected_tests(plan: list[FalsificationTest], m: TargetMeasurements, settings: Settings) -> list[FalsificationTest]:
    t = settings.thresholds
    by_id = {test.test_id.split(":")[0]: test for test in plan}
    qhits = [h for h in m.hits if h.query_id == m.query_id]
    best = _best(qhits, {"nucleotide", "translated", "protein"})
    loci = _loci(qhits, settings)
    domain_hits = [h for h in qhits if h.search_kind == "domain"]

    if test := _take(by_id,"wrong_paralogue"):
        paralogue = len(loci) >= t.gene_paralogue_min_loci
        metrics = {"n_loci": len(loci), "loci": [h.contig_id for h in loci]}
        if paralogue:
            _finish(test, "completed", FalsificationResult.weakens_claim, metrics)
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, metrics)

    if test := _take(by_id,"short_conserved_domain"):
        if m.profile.domains:
            covered = []
            for domain in m.profile.domains:
                domain_hits_here = [
                    h for h in (domain_hits or qhits)
                    if h.qend > domain.start and h.qstart < domain.end
                ]
                dlen = max(1, domain.end - domain.start)
                dspan = 0
                for h in domain_hits_here:
                    dspan = max(dspan, min(h.qend, domain.end) - max(h.qstart, domain.start))
                covered.append(dspan / dlen)
            n_covered = sum(1 for c in covered if c >= 0.5)
            metrics = {"domain_coverage": covered, "n_domains_covered": n_covered, "n_domains": len(m.profile.domains)}
            if n_covered < len(m.profile.domains):
                _finish(test, "completed", FalsificationResult.weakens_claim, metrics)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, metrics)
        elif best and best.query_coverage < t.gene_domain_short_coverage and best.identity >= t.gene_aa_min_identity:
            _finish(test, "completed", FalsificationResult.weakens_claim, {"query_coverage": best.query_coverage, "identity": best.identity})
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, {"query_coverage": best.query_coverage if best else None})

    if test := _take(by_id,"low_alignment_coverage"):
        qcov = best.query_coverage if best else 0.0
        metrics = {"query_coverage": qcov, "threshold": t.gene_coverage_weaken_below}
        if qcov < t.gene_coverage_weaken_below:
            _finish(test, "completed", FalsificationResult.weakens_claim, metrics)
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, metrics)

    if test := _take(by_id,"abnormal_protein_length"):
        expected = m.profile.expected_length_aa or (len(query_amino_acid(m.profile)) or None)
        fam = getattr(m, "family_evidence", None)
        if fam is not None and getattr(fam, "fusion", {}).get("supported"):
            _finish(test, "completed", FalsificationResult.weakens_claim, {
                "reason": "protein longer than canonical family length; fusion architecture recorded separately",
                "fusion": fam.fusion,
            })
        elif best is None or expected is None or expected <= 0:
            _skip(test, "no expected protein length or no hit against which to measure length", blocking=False)
        else:
            if best.search_kind == "nucleotide":
                observed = max(1, abs(best.tend - best.tstart) // 3)
            elif best.search_kind == "protein":
                observed = max(1, abs(best.tend - best.tstart))
            else:
                observed = max(1, abs(best.tend - best.tstart) // 3)
            ratio = observed / expected
            metrics = {"expected_aa": expected, "observed_aa": observed, "ratio": ratio}
            if ratio < t.gene_length_ratio_min or ratio > t.gene_length_ratio_max:
                _finish(test, "completed", FalsificationResult.weakens_claim, metrics)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, metrics)

    if test := _take(by_id,"missing_catalytic_residues"):
        if not m.profile.catalytic_residues:
            _skip(test, "no catalytic residue pattern was provided; residues were not invented", blocking=False)
        elif best is None:
            _skip(test, "no alignment available to inspect catalytic residues", blocking=False)
        else:
            missing = []
            observed = []
            for res in m.profile.catalytic_residues:
                got = _subject_residue(best, res.position, m)
                observed.append({"position": res.position, "expected": res.residue, "observed": got})
                if got != res.residue:
                    missing.append(res.position)
            metrics = {"residues": observed, "n_missing": len(missing)}
            if missing:
                _finish(test, "completed", FalsificationResult.weakens_claim, metrics)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, metrics)

    if test := _take(by_id,"contamination"):
        reasons = []
        if m.checkm_contamination is not None and m.checkm_contamination > settings.thresholds.max_contamination_soft:
            reasons.append(f"checkm_contamination={m.checkm_contamination}")
        if best:
            cov = m.coverage_by_hit.get(f"{best.query_id}:{best.contig_id}:{best.tstart}-{best.tend}", {})
            rel = cov.get("relative_depth")
            if rel is not None and (rel < t.gene_relative_depth_low or rel > t.gene_relative_depth_high):
                reasons.append(f"relative_depth={rel}")
            gc = m.contig_gc.get(best.contig_id)
            if gc is not None and m.genome_gc is not None and abs(gc - m.genome_gc) > t.gene_gc_outlier:
                reasons.append(f"gc_outlier contig={gc:.3f} genome={m.genome_gc:.3f}")
            tax = (m.contig_taxonomy or {}).get(best.contig_id) or {}
            measured = tax.get("taxonomy")
            declared = m.declared_organism or m.profile.expected_taxonomy
            if measured and declared:
                if declared.lower() not in str(measured).lower() and str(measured).lower() not in declared.lower():
                    reasons.append(f"contig_taxonomy={measured}")
        has_tax = any((m.contig_taxonomy or {}).values())
        if reasons:
            _finish(test, "completed", FalsificationResult.weakens_claim, {"reasons": reasons})
        elif m.checkm_contamination is None and not m.depth_available and not m.contig_gc and not has_tax:
            _skip(test, "no contamination, depth, contig-GC, or contig-taxonomy measurement was available", blocking=False)
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, {"reasons": []})

    if test := _take(by_id,"abnormal_contig_coverage"):
        if not m.depth_available or not best:
            _skip(test, "read-back depth was unavailable for the candidate locus", blocking=False)
        else:
            cov = m.coverage_by_hit.get(f"{best.query_id}:{best.contig_id}:{best.tstart}-{best.tend}", {})
            rel = cov.get("relative_depth")
            metrics = dict(cov)
            if rel is None:
                _skip(test, "local depth could not be computed for the candidate locus", blocking=False)
            elif rel < t.gene_relative_depth_low or rel > t.gene_relative_depth_high:
                _finish(test, "completed", FalsificationResult.weakens_claim, metrics)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, metrics)
            if m.depth_evidence_ids:
                test.evidence_ids = list(dict.fromkeys(list(test.evidence_ids) + list(m.depth_evidence_ids)))

    if test := _take(by_id,"taxonomic_inconsistency"):
        declared = m.declared_organism or m.profile.expected_taxonomy
        measured = m.measured_taxonomy
        if best and (m.contig_taxonomy or {}).get(best.contig_id, {}).get("taxonomy"):
            measured = m.contig_taxonomy[best.contig_id]["taxonomy"]
        if not declared or not measured:
            _skip(test, "no measured contig taxonomy was available; taxonomy was not invented from reference metadata", blocking=False)
        elif declared.lower() not in str(measured).lower() and str(measured).lower() not in declared.lower():
            _finish(test, "completed", FalsificationResult.weakens_claim, {
                "expected": declared, "measured": measured,
            })
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, {
                "expected": declared, "measured": measured,
            })

    if test := _take(by_id,"inconsistent_genomic_neighborhood"):
        if not m.profile.expected_neighbors:
            _skip(test, "no expected neighboring genes were specified", blocking=False)
        elif not m.annotation_available:
            _skip(test, "annotation neighborhood could not be measured", blocking=False)
        else:
            observed = []
            for nb in m.neighborhood_by_hit.values():
                for feat in nb.get("flanking_features", []) + nb.get("overlapping_features", []):
                    if feat.get("product"):
                        observed.append(feat["product"])
            if not observed:
                for le in m.locus_evidence:
                    observed.extend(le.distance.get("query_upstream") or [])
                    observed.extend(le.distance.get("query_downstream") or [])
                    observed.extend(g.product for g in le.gene_order if not g.is_target)
            matched = [n for n in m.profile.expected_neighbors if any(n.lower() in o.lower() for o in observed)]
            metrics = {"expected": m.profile.expected_neighbors, "observed": observed, "matched": matched}
            if not matched:
                _finish(test, "completed", FalsificationResult.weakens_claim, metrics)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, metrics)
    _run_family_architecture_tests(plan, m, detected=True)
    apply_locus_tests(plan, m, settings, detected=True)
    return plan


def execute_not_detected_tests(plan: list[FalsificationTest], m: TargetMeasurements, settings: Settings) -> list[FalsificationTest]:
    by_id = {test.test_id.split(":")[0]: test for test in plan}
    qhits = [h for h in m.hits if h.query_id == m.query_id]
    nt = [h for h in qhits if h.search_kind == "nucleotide"]
    aa = [h for h in qhits if h.search_kind == "translated"]
    prot = [h for h in qhits if h.search_kind == "protein"]
    domain = [h for h in qhits if h.search_kind == "domain"]
    tt = m.profile.target_type
    partial = [h for h in qhits if partial_hit(h, settings, tt)]
    edge = [h for h in qhits if h.possible_edge_truncation or (h.near_contig_edge and h.query_coverage < 0.95)]
    qlen = next((h.query_length for h in nt + aa + prot), len(m.profile.sequence))
    split = query_span_coverage(nt or aa or prot, qlen)
    fragmented = len({h.contig_id for h in (nt or aa or prot)}) > 1 and split >= settings.thresholds.gene_aa_min_query_coverage

    def homology_result(hits: list[GeneSearchHit]) -> FalsificationResult:
        if any(strong_hit(h, settings, tt) for h in hits):
            return FalsificationResult.rejects_claim
        if any(partial_hit(h, settings, tt) for h in hits):
            return FalsificationResult.weakens_claim
        return FalsificationResult.supports_claim

    if test := _take(by_id,"nucleotide_homology"):
        _finish(test, "completed", homology_result(nt), {"n_hits": len(nt), "evalues": [h.evalue for h in nt if h.evalue is not None]})
    if test := _take(by_id,"translated_homology"):
        _finish(test, "completed", homology_result(aa), {"n_hits": len(aa), "evalues": [h.evalue for h in aa if h.evalue is not None]})
    if test := _take(by_id,"predicted_protein_homology"):
        if not m.proteins_available:
            _skip(test, "predicted proteins were unavailable", blocking=False)
        else:
            _finish(test, "completed", homology_result(prot), {"n_hits": len(prot)})
    if test := _take(by_id,"partial_domain_hits"):
        hits = domain or partial
        if any(h.evalue is not None and h.evalue <= 1e-3 for h in domain) or domain or partial:
            result = FalsificationResult.weakens_claim
        else:
            result = FalsificationResult.supports_claim
        _finish(test, "completed", result, {"n_domain_hits": len(domain), "n_partial_hits": len(partial)})
    if test := _take(by_id,"contig_edge_truncation"):
        br = _break_metrics(m, qhits)
        if br.get("status") == "completed" and br.get("read_supported_break") is True:
            _finish(test, "completed", FalsificationResult.weakens_claim, br)
        elif br.get("status") == "completed" and br.get("read_supported_break") is False:
            _finish(test, "completed", FalsificationResult.supports_claim, br)
        elif edge:
            _finish(test, "completed", FalsificationResult.weakens_claim, {"n_edge_hits": len(edge), "fallback": "geometric_truncation"})
        elif m.mapping_available:
            _skip(test, "mapping was present but locus-edge read support was inconclusive", blocking=False)
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, {"n_edge_hits": 0})
    if test := _take(by_id,"assembly_fragmentation"):
        result = FalsificationResult.weakens_claim if fragmented else FalsificationResult.supports_claim
        _finish(test, "completed", result, {"fragmented": fragmented, "combined_query_span": split})
    if test := _take(by_id,"local_read_coverage"):
        if not m.depth_available:
            _skip(test, "read-back depth was unavailable", blocking=False)
        elif not qhits:
            _finish(test, "completed", FalsificationResult.supports_claim, {"note": "no homologous window; coverage cannot hide a detected locus"})
        else:
            low = [v for v in m.coverage_by_hit.values() if v.get("relative_depth") is not None and v["relative_depth"] < settings.thresholds.gene_relative_depth_low]
            disc = [v for v in m.coverage_by_hit.values() if v.get("coverage_discontinuity")]
            metrics = {"loci": m.coverage_by_hit, "n_low_relative_depth": len(low), "n_discontinuity": len(disc)}
            if low or disc:
                _finish(test, "completed", FalsificationResult.weakens_claim, metrics)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, metrics)
            if m.depth_evidence_ids:
                test.evidence_ids = list(dict.fromkeys(list(test.evidence_ids) + list(m.depth_evidence_ids)))
    if test := _take(by_id,"expected_neighboring_genes"):
        if not m.profile.expected_neighbors:
            _skip(test, "no expected neighboring genes were specified", blocking=False)
        elif not m.annotation_available and not m.neighborhood_by_hit:
            _skip(test, "neighborhood could not be measured", blocking=False)
        else:
            observed = []
            for nb in m.neighborhood_by_hit.values():
                for feat in nb.get("flanking_features", []) + nb.get("overlapping_features", []):
                    if feat.get("product"):
                        observed.append(feat["product"])
            # Allow tests to pass observed neighbors without a hit locus.
            extra = m.neighborhood_by_hit.get("_assembly", {})
            observed.extend(extra.get("products", []))
            matched = [n for n in m.profile.expected_neighbors if any(n.lower() in o.lower() for o in observed)]
            metrics = {"expected": m.profile.expected_neighbors, "observed": observed, "matched": matched}
            if matched and not qhits:
                _finish(test, "completed", FalsificationResult.supports_claim, metrics)
            elif not matched:
                _finish(test, "completed", FalsificationResult.inconclusive, metrics)
                test.status = "unresolved"
            else:
                _finish(test, "completed", FalsificationResult.inconclusive, metrics)
    if test := _take(by_id,"divergent_homologues"):
        proteinish = [h for h in aa + prot + domain if not any(strong_hit(n, settings) for n in nt)]
        fam = getattr(m, "family_evidence", None)
        if fam is not None and getattr(fam, "supports_orthologue", False):
            _finish(test, "completed", FalsificationResult.rejects_claim, {"family_evidence": True, "architecture": getattr(fam, "architecture", None)})
        elif proteinish and not nt:
            result = FalsificationResult.rejects_claim if any(strong_hit(h, settings) for h in aa + prot) else FalsificationResult.weakens_claim
            _finish(test, "completed", result, {"n_protein_or_domain_hits": len(proteinish)})
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, {"n_protein_or_domain_hits": len(proteinish)})
    _run_family_architecture_tests(plan, m, detected=False)
    apply_locus_tests(plan, m, settings, detected=False)
    return plan


def _run_family_architecture_tests(plan: list[FalsificationTest], m: TargetMeasurements, *, detected: bool) -> None:
    by_id = {test.test_id.split(":")[0]: test for test in plan}
    fam = getattr(m, "family_evidence", None)
    if fam is None:
        for key in ("family_profile_hmm", "fusion_orf", "split_gene", "competitive_family", "locus_multiplicity"):
            if test := _take(by_id,key):
                _skip(test, "no curated family evidence was collected", blocking=False)
        return
    metrics_hmm = {
        "architecture": fam.architecture,
        "hierarchy": fam.hierarchy,
        "supports_orthologue": fam.supports_orthologue,
        "domain_only": fam.domain_only,
        "hmm": fam.best_hmm,
        "invented": False,
    }
    if test := _take(by_id,"family_profile_hmm"):
        if fam.domain_only:
            result = FalsificationResult.weakens_claim if detected else FalsificationResult.supports_claim
            _finish(test, "completed", result, {**metrics_hmm, "note": "domain-only HMM hit is not a full gene_orthologue"})
        elif fam.supports_orthologue and (fam.best_hmm or (fam.metrics or {}).get("n_supporting_members", 0) >= 2):
            result = FalsificationResult.supports_claim if detected else FalsificationResult.rejects_claim
            _finish(test, "completed", result, metrics_hmm)
        else:
            result = FalsificationResult.supports_claim if not detected else FalsificationResult.weakens_claim
            _finish(test, "completed", result, metrics_hmm)
    if test := _take(by_id,"fusion_orf"):
        if fam.fusion.get("supported"):
            result = FalsificationResult.supports_claim if detected else FalsificationResult.rejects_claim
            _finish(test, "completed", result, fam.fusion)
        else:
            result = FalsificationResult.supports_claim
            _finish(test, "completed", result, fam.fusion or {"state": "not_fusion"})
    if test := _take(by_id,"split_gene"):
        if fam.split.get("supported"):
            result = FalsificationResult.supports_claim if detected else FalsificationResult.rejects_claim
            _finish(test, "completed", result, fam.split)
        elif fam.fragmented.get("supported"):
            result = FalsificationResult.weakens_claim
            _finish(test, "completed", result, {**fam.fragmented, "note": "fragments follow contig boundaries, not a biological split"})
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, fam.split or {"state": "not_split"})
    if detected:
        if test := _take(by_id,"assembly_fragmentation"):
            if fam.fragmented.get("supported"):
                _finish(test, "completed", FalsificationResult.weakens_claim, fam.fragmented)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, fam.fragmented or {"state": "not_fragmented"})
    recon = fam.reconstruction or {}
    if test := _take(by_id, "competitive_family"):
        comp = recon.get("competitive_family") or {}
        cls = comp.get("classification")
        metrics = {"classification": cls, "best_competing_family": comp.get("best_competing_family"), "score_margin": comp.get("score_margin"), "invented": False}
        if cls == "competing_family_preferred":
            result = FalsificationResult.rejects_claim if detected else FalsificationResult.supports_claim
            _finish(test, "completed", result, metrics)
        elif cls in {"ambiguous_family", "domain_only", "unresolved_candidate"}:
            result = FalsificationResult.weakens_claim if detected else FalsificationResult.supports_claim
            _finish(test, "completed", result, metrics)
        else:
            result = FalsificationResult.supports_claim if detected else FalsificationResult.weakens_claim
            _finish(test, "completed", result, metrics)
    if test := _take(by_id, "locus_multiplicity"):
        multi = recon.get("multiplicity") or {}
        cls = multi.get("classification")
        metrics = {"classification": cls, "n_loci": multi.get("number_of_candidate_loci"), "invented": False}
        if cls in {"true_gene_duplication", "recent_duplication", "paralogous_copy", "plasmid_copy"}:
            result = FalsificationResult.weakens_claim if detected else FalsificationResult.rejects_claim
            _finish(test, "completed", result, metrics)
        elif cls == "assembly_fragments_of_one_gene":
            result = FalsificationResult.weakens_claim if detected else FalsificationResult.supports_claim
            _finish(test, "completed", result, metrics)
        else:
            _finish(test, "completed", FalsificationResult.supports_claim, metrics)


def apply_locus_tests(plan: list[FalsificationTest], m: TargetMeasurements, settings: Settings, *, detected: bool) -> None:
    by_id = {test.test_id.split(":")[0]: test for test in plan}
    loci = [le for le in m.locus_evidence if le.target == m.query_id]
    has_ref = any(le.reference_genome for le in loci)
    skip_reason = "no trusted reference genome was configured; orthologues and gene order were not invented"

    def skip_all(keys: list[str]) -> None:
        for key in keys:
            if test := _take(by_id,key):
                _skip(test, skip_reason, blocking=False)

    if detected:
        keys = [
            "orthology_versus_paralogy", "reciprocal_best_hit", "gene_length_conservation",
            "protein_identity_and_coverage", "gene_orientation", "upstream_downstream_orthologues",
            "local_gene_order", "intergenic_spacing", "contig_edge_effects", "taxonomic_consistency_of_locus",
            "phylogenetic_placement",
        ]
    else:
        keys = ["reference_neighbor_presence", "missing_in_fragmented_region"]
    if test := _take(by_id,"read_supported_break"):
        br = _break_metrics(m, m.hits)
        if br.get("status") == "completed" and br.get("read_supported_break") is True:
            _finish(test, "completed", FalsificationResult.weakens_claim, br)
        elif br.get("status") == "completed":
            _finish(test, "completed", FalsificationResult.supports_claim, br)
        else:
            _skip(test, br.get("limitation") or "paired-end mapping was unavailable; read support was not invented", blocking=False)
    if not has_ref:
        skip_all(keys)
        return

    le = next((x for x in loci if x.reference_genome), loci[0])
    conflicts = set(le.conflicts)
    sim = le.sequence_similarity or {}
    dist = le.distance or {}

    if detected:
        if test := _take(by_id,"orthology_versus_paralogy"):
            if "paralogous_copies" in conflicts or sim.get("orthology_class") in {"paralog", "paralog_or_xenolog"}:
                test.blocking = True
                _finish(test, "completed", FalsificationResult.weakens_claim, {"class": sim.get("orthology_class"), "conflicts": le.conflicts})
            elif sim.get("orthology_class") == "ortholog":
                test.blocking = True
                _finish(test, "completed", FalsificationResult.supports_claim, {"class": "ortholog"})
            else:
                _finish(test, "completed", FalsificationResult.inconclusive, {"class": sim.get("orthology_class")})
                test.status = "unresolved"
        if test := _take(by_id,"reciprocal_best_hit"):
            rbh = [o.reciprocal_best_hit for o in le.orthologues]
            if any(v is True for v in rbh):
                test.blocking = True
                _finish(test, "completed", FalsificationResult.supports_claim, {"rbh": True})
            elif any(v is False for v in rbh):
                test.blocking = True
                _finish(test, "completed", FalsificationResult.weakens_claim, {"rbh": False})
            else:
                _skip(test, "reciprocal search could not be completed", blocking=False)
        if test := _take(by_id,"gene_length_conservation"):
            ratio = sim.get("length_ratio")
            if ratio is None:
                _skip(test, "reference orthologue length was not measured", blocking=False)
            elif ratio < settings.thresholds.gene_length_ratio_min or ratio > settings.thresholds.gene_length_ratio_max:
                _finish(test, "completed", FalsificationResult.weakens_claim, {"length_ratio": ratio})
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, {"length_ratio": ratio})
        if test := _take(by_id,"protein_identity_and_coverage"):
            ident, cov = sim.get("identity"), sim.get("query_coverage")
            fam = getattr(m, "family_evidence", None)
            family_ok = bool(fam is not None and getattr(fam, "supports_orthologue", False) and not getattr(fam, "domain_only", False))
            if ident is None and family_ok:
                _finish(test, "completed", FalsificationResult.supports_claim, {
                    "identity": ident, "coverage": cov,
                    "note": "pairwise identity vs a single reference was not required; family-profile evidence supports orthology",
                })
            elif ident is None:
                _skip(test, "no reference protein identity was measured", blocking=False)
            elif family_ok and (ident < settings.thresholds.orthologue_min_identity or (cov is not None and cov < settings.thresholds.orthologue_min_coverage)):
                _finish(test, "completed", FalsificationResult.supports_claim, {
                    "identity": ident, "coverage": cov,
                    "note": "pairwise identity alone did not reject a family-profile orthologue",
                })
            elif ident < settings.thresholds.orthologue_min_identity or (cov is not None and cov < settings.thresholds.orthologue_min_coverage):
                _finish(test, "completed", FalsificationResult.weakens_claim, {"identity": ident, "coverage": cov})
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, {"identity": ident, "coverage": cov})
        if test := _take(by_id,"gene_orientation"):
            if "orientation_mismatch" in conflicts:
                _finish(test, "completed", FalsificationResult.weakens_claim, {"orientation": le.orientation})
            elif "reference_target_not_annotated" in conflicts or "query_annotation_missing" in conflicts:
                _skip(test, "orientation could not be compared because a locus annotation was missing", blocking=False)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, {"orientation": le.orientation})
        if test := _take(by_id,"upstream_downstream_orthologues"):
            if "missing_flanking_orthologues" in conflicts:
                _finish(test, "completed", FalsificationResult.weakens_claim, dist)
            elif "reference_target_not_annotated" in conflicts or "query_annotation_missing" in conflicts:
                _skip(test, "flanking orthologues could not be compared because a locus annotation was missing", blocking=False)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, dist)
        if test := _take(by_id,"local_gene_order"):
            if "gene_order_mismatch" in conflicts or "gene_order_inverted" in conflicts:
                test.blocking = True
                result = FalsificationResult.rejects_claim if "gene_order_inverted" in conflicts else FalsificationResult.weakens_claim
                _finish(test, "completed", result, {"conflicts": le.conflicts, "order": [g.product for g in le.gene_order]})
            elif "reference_target_not_annotated" in conflicts or "query_annotation_missing" in conflicts:
                _skip(test, "gene order could not be compared because a locus annotation was missing", blocking=False)
            else:
                test.blocking = True
                _finish(test, "completed", FalsificationResult.supports_claim, {"order": [g.product for g in le.gene_order]})
        if test := _take(by_id,"intergenic_spacing"):
            if "spacing_outlier" in conflicts or "overlapping_neighbors" in conflicts:
                _finish(test, "completed", FalsificationResult.weakens_claim, dist)
            elif "reference_target_not_annotated" in conflicts or "query_annotation_missing" in conflicts:
                _skip(test, "intergenic spacing could not be compared because a locus annotation was missing", blocking=False)
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, dist)
        if test := _take(by_id,"contig_edge_effects"):
            br = _break_metrics(m, m.hits)
            if br.get("status") == "completed" and br.get("read_supported_break") is True:
                _finish(test, "completed", FalsificationResult.weakens_claim, br)
            elif br.get("status") == "completed" and br.get("read_supported_break") is False:
                _finish(test, "completed", FalsificationResult.supports_claim, br)
            elif "contig_edge" in conflicts:
                _finish(test, "completed", FalsificationResult.weakens_claim, {"locus": le.candidate_locus, "fallback": "geometric_truncation"})
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, {"locus": le.candidate_locus})
        if test := _take(by_id,"taxonomic_consistency_of_locus"):
            if "taxonomic_inconsistency" in conflicts:
                _finish(test, "completed", FalsificationResult.weakens_claim, {"conflicts": le.conflicts})
            elif any((m.contig_taxonomy or {}).values()):
                _finish(test, "completed", FalsificationResult.supports_claim, {"taxonomy": m.contig_taxonomy})
            else:
                _skip(test, "no measured contig taxonomy was available; taxonomy was not invented from reference metadata", blocking=False)
        if test := _take(by_id,"phylogenetic_placement"):
            phy = m.phylogeny or (le.sequence_similarity or {}).get("placement") or {}
            if phy.get("status") == "completed" and phy.get("clade") == "paralog":
                _finish(test, "completed", FalsificationResult.weakens_claim, phy)
            elif phy.get("status") == "completed" and phy.get("clade") == "ortholog":
                _finish(test, "completed", FalsificationResult.supports_claim, phy)
            else:
                _skip(test, (phy or {}).get("limitation") or "placement among labeled homologues was not measured", blocking=False)
    else:
        if test := _take(by_id,"reference_neighbor_presence"):
            expected = list(dist.get("reference_neighbor_products") or []) or ((dist.get("reference_upstream") or []) + (dist.get("reference_downstream") or []))
            observed = list(dist.get("assembly_neighbor_products") or []) + (dist.get("query_upstream") or []) + (dist.get("query_downstream") or [])
            products = [g.product for g in le.gene_order]
            present = [n for n in expected if n in observed or n in products]
            if expected and present:
                _finish(test, "completed", FalsificationResult.supports_claim, {"expected": expected, "present": present})
            elif expected:
                _finish(test, "completed", FalsificationResult.inconclusive, {"expected": expected, "present": present})
                test.status = "unresolved"
            else:
                _skip(test, "reference did not define neighboring genes", blocking=False)
        if test := _take(by_id,"missing_in_fragmented_region"):
            br = _break_metrics(m, m.hits)
            if br.get("read_supported_break") is True or "contig_edge" in conflicts or "missing_flanking_orthologues" in conflicts:
                _finish(test, "completed", FalsificationResult.weakens_claim, {"conflicts": le.conflicts, "break": br})
            else:
                _finish(test, "completed", FalsificationResult.supports_claim, {"conflicts": le.conflicts})
        if test := _take(by_id,"read_supported_break"):
            br = _break_metrics(m, m.hits)
            if br.get("status") == "completed" and br.get("read_supported_break") is True:
                _finish(test, "completed", FalsificationResult.weakens_claim, br)
            elif br.get("status") == "completed":
                _finish(test, "completed", FalsificationResult.supports_claim, br)
            else:
                _skip(test, br.get("limitation") or "paired-end mapping was unavailable; read support was not invented", blocking=False)


def anomalies_from_tests(query_id: str, tests: list[FalsificationTest]) -> list[Anomaly]:
    out: list[Anomaly] = []
    for test in tests:
        if test.result not in {FalsificationResult.weakens_claim, FalsificationResult.rejects_claim}:
            continue
        out.append(Anomaly(
            id=f"falsify:{test.test_id}",
            stage="target_gene",
            severity=Severity.warning,
            message=f"{test.name} challenged the claim: {test.hypothesis}",
            evidence_ids=list(test.evidence_ids),
            possible_explanations=[test.hypothesis],
        ))
    return out


def bounded_statement(claim_type: ClaimType, query_id: str) -> str:
    if claim_type == ClaimType.target_gene_detected:
        return f"Target gene '{query_id}' is detected in the current assembly."
    return f"Target gene '{query_id}' was not detected in the current assembly."


def assert_claim_not_stronger_than_evidence(claim: Claim) -> None:
    blob = f"{claim.statement} {claim.rationale}".lower()
    for phrase in FORBIDDEN_ABSENCE_PHRASES:
        if phrase in blob:
            raise ValueError(f"Claim language overreaches the evidence: {phrase}")
    forbidden_certainty = (
        "certainly present",
        "confirmed functional",
        "proves that",
        "the organism lacks",
        "the organism has this gene",
        "absent from the genome of the organism",
        "true biological presence",
    )
    for phrase in forbidden_certainty:
        if phrase in blob:
            raise ValueError(f"Claim language overreaches the evidence: {phrase}")
    if claim.status == ClaimStatus.supported and claim.confidence >= 0.95:
        raise ValueError("Supported was treated as certainty")
    if claim.claim_type == ClaimType.target_gene_not_detected and "absent from the organism" in blob:
        raise ValueError("Non-detection was converted into organism-level absence")


def build_target_gene_claim(m: TargetMeasurements, settings: Settings, measurement_evidence_ids: list[str]) -> tuple[Claim, list[Anomaly], list[FalsificationTest]]:
    tt = m.profile.target_type
    polarity = classify_polarity(m.hits, settings, tt, family_evidence=getattr(m, "family_evidence", None))
    homology = homology_support_score(m.hits, settings, tt)
    hscore = homology["score"]
    fam = getattr(m, "family_evidence", None)
    if fam is not None and getattr(fam, "supports_orthologue", False) and not getattr(fam, "domain_only", False):
        hmm_cov = (fam.metrics or {}).get("hmm_model_coverage") or 0.0
        ref_ag = (fam.metrics or {}).get("reference_set_agreement") or 0.0
        family_score = max(0.55 * float(hmm_cov or 0), 0.50 * float(ref_ag or 0))
        if fam.architecture in {"fusion", "biological_split", "divergent_full_length"} and (hmm_cov or 0) >= 0.70:
            family_score = max(family_score, 0.62)
        elif fam.architecture == "fusion" and fam.fusion.get("supported"):
            family_score = max(family_score, 0.58)
        hscore = max(hscore, family_score)
        homology["family_support"] = round(family_score, 4)
        homology["architecture"] = fam.architecture
        homology["hierarchy"] = list(fam.hierarchy or [])
    elif fam is not None and getattr(fam, "domain_only", False):
        hscore = min(hscore, 0.35)
        homology["domain_only"] = True
    rels = [v.get("relative_depth") for v in (m.coverage_by_hit or {}).values() if v.get("relative_depth") is not None]
    if rels:
        rel = max(float(x) for x in rels)
        homology["relative_locus_coverage"] = rel
        if rel < settings.thresholds.gene_relative_depth_low:
            hscore = min(hscore, 0.55)
        elif settings.thresholds.gene_relative_depth_low <= rel <= settings.thresholds.gene_relative_depth_high:
            hscore = min(1.0, hscore + 0.03)
    if any(v.get("coverage_discontinuity") for v in (m.coverage_by_hit or {}).values()):
        homology["coverage_discontinuity"] = True
        hscore = min(hscore, 0.62)
    n_loci = len(_loci(m.hits, settings))
    if n_loci >= settings.thresholds.gene_paralogue_min_loci:
        homology["paralogue_loci"] = n_loci
        hscore = min(hscore, 0.58)
    homology["score"] = round(max(0.0, min(1.0, hscore)), 4)
    plan = generate_attack_plan(polarity, m.query_id)
    voi_log: list[dict] = []
    graph = None
    if m.falsification_enabled and settings.execution.enable_hypothesis_graph:
        from genome_skeptic.claims.hypothesis_graph import build_hypothesis_graph
        recon = (getattr(fam, "reconstruction", None) or {}) if fam is not None else {}
        graph = build_hypothesis_graph(
            target_id=m.query_id,
            polarity_detected=polarity == ClaimType.target_gene_detected,
            architecture=None if fam is None else fam.architecture,
            family_supports=bool(fam and fam.supports_orthologue),
            domain_only=bool(fam and fam.domain_only),
            n_loci=n_loci,
            contig_edge=bool(recon.get("contig_edge") or (fam.fragmented.get("supported") if fam and fam.fragmented else False)),
            contamination_flag=False,
            evidence_ids=list(measurement_evidence_ids),
            competitive_class=(recon.get("competitive_family") or {}).get("classification"),
            multiplicity_class=(recon.get("multiplicity") or {}).get("classification"),
            unavailable=[t for t in ("contig_taxonomy", "local_read_depth") if True],
        )
        if settings.execution.enable_voi_policy:
            from genome_skeptic.claims.action_policy import filter_tests
            plan, voi_log = filter_tests(plan, graph)
    if not m.falsification_enabled:
        for test in plan:
            _skip(test, "falsification engine disabled for this comparison run", blocking=False)
        tests = plan
        alternatives = ["falsification was not executed; homology polarity is not a completed adversarial claim"]
        base = 0.4
        status = ClaimStatus.unresolved
    elif polarity == ClaimType.target_gene_detected:
        tests = execute_detected_tests(plan, m, settings)
        alternatives = [
            "the hit may be a paralogue",
            "the hit may be a conserved domain fragment",
            "the hit may lie on a contaminant contig",
            "detection in this assembly is not proof of function",
            "inconsistent synteny can indicate paralogy, rearrangement, or a wrong locus",
        ]
        base = 0.7
    else:
        tests = execute_not_detected_tests(plan, m, settings)
        alternatives = [
            "the gene may be too diverged for nucleotide search",
            "the gene may be truncated at a contig edge",
            "the gene may be fragmented across contigs",
            "non-detection in this assembly is not organism-level absence",
        ]
        base = 0.55
    if m.falsification_enabled:
        status = resolve_claim_status(tests)
    fam_metrics = {}
    if fam is not None:
        fam_metrics = dict(fam.metrics or {})
        fam_metrics["architecture"] = fam.architecture
        fam_metrics["hierarchy"] = list(fam.hierarchy or [])
        fam_metrics["paralogue"] = bool(fam.paralogue.get("supported")) if fam.paralogue else False
        fam_metrics["contig_edge"] = bool(fam.fragmented.get("supported")) if fam.fragmented else False
        rels2 = [v.get("relative_depth") for v in (m.coverage_by_hit or {}).values() if v.get("relative_depth") is not None]
        if rels2:
            rel = max(float(x) for x in rels2)
            fam_metrics["depth_ok"] = 1.0 if settings.thresholds.gene_relative_depth_low <= rel <= settings.thresholds.gene_relative_depth_high else 0.2
        tax_conflict = any("taxonomic" in (c or "") for le in m.locus_evidence for c in (le.conflicts or []))
        fam_metrics["contradictory_taxonomy"] = tax_conflict
        if fam.best_hmm and fam.best_hmm.get("domain_completeness"):
            n = len(fam.best_hmm["domain_completeness"])
            fam_metrics["domain_completeness_score"] = sum(1 for d in fam.best_hmm["domain_completeness"] if d.get("complete")) / n if n else 0.0
    best_nt = next((h for h in m.hits if h.search_kind == "nucleotide"), None)
    conf = confidence_for_target_type(
        status, tests,
        target_type=tt,
        homology_support=homology["score"],
        not_detected=polarity == ClaimType.target_gene_not_detected,
        max_supported=settings.thresholds.max_claim_confidence,
        family_metrics=fam_metrics,
        identity=best_nt.identity if best_nt else None,
        coverage=best_nt.query_coverage if best_nt else None,
    )
    if polarity == ClaimType.target_gene_not_detected:
        conf = min(conf, settings.thresholds.max_not_detected_confidence)
    contradicting = []
    supporting = list(measurement_evidence_ids) + list(m.depth_evidence_ids or [])
    for test in tests:
        if test.result in {FalsificationResult.weakens_claim, FalsificationResult.rejects_claim}:
            contradicting.extend(test.evidence_ids)
        elif test.result == FalsificationResult.supports_claim:
            supporting.extend(test.evidence_ids)
    if not m.falsification_enabled:
        rationale = (
            "Falsification was disabled. Homology polarity was recorded without executing the attack plan. "
            "Status is unresolved because disconfirming tests were not run. "
        )
    else:
        rationale = (
            f"Adversarial attack plan {attack_plan_id(polarity, m.query_id)} was executed with deterministic measurements. "
            f"Status '{status.value}' is a claim-state, not certainty. "
        )
    if polarity == ClaimType.target_gene_not_detected:
        rationale += "The statement is limited to non-detection in the current assembly; it is not a claim that the gene is missing from the organism. "
    else:
        rationale += "Detection means homology survived the attack plan in this assembly; it is not a functional or organism-level proof. "
    skipped = [t.test_id for t in tests if t.status != "completed"]
    if graph is not None:
        alt = graph.runner_up or "none"
        rationale += (
            f" Leading interpretation '{graph.leading}' is ranked above '{alt}' on deterministic evidence "
            f"(relative support, not a calibrated probability). "
        )
        if graph.stop_reason:
            rationale += graph.stop_reason + " "
        rationale += "Unfinished tests: " + ", ".join(skipped) + "."
    if m.tools_unavailable:
        rationale += " Unavailable instruments: " + ", ".join(m.tools_unavailable) + "."
    claim = Claim(
        claim_id=claim_id_for_query(m.query_id),
        claim_type=polarity,
        statement=bounded_statement(polarity, m.query_id),
        supporting_evidence_ids=list(dict.fromkeys(eid for eid in supporting if eid)),
        contradicting_evidence_ids=list(dict.fromkeys(eid for eid in contradicting if eid)),
        alternative_explanations=alternatives,
        falsification_tests=tests,
        status=status,
        confidence=conf,
        homology_support=homology["score"],
        raw_confidence=conf,
        orthology_class=(None if fam is None else ",".join(fam.hierarchy or []) or fam.architecture),
        architecture_state=None if fam is None else fam.architecture,
        provenance=ClaimProvenance(
            created_by="deterministic_validator",
            stage="target_gene",
            tool_names=m.tools_run or ["internal_gene_search"],
            attack_plan_id=attack_plan_id(polarity, m.query_id),
            notes=(
                "LLM did not supply identity, coverage, E-values, domain hits, catalytic residues, orthologues, gene order, or reciprocal hits. "
                f"homology_support={homology['score']} n_strong={homology['n_strong']} n_partial={homology['n_partial']} "
                f"full_length={homology['full_length']} target_type={getattr(tt, 'value', None)} "
                f"architecture={None if fam is None else fam.architecture} hierarchy={None if fam is None else fam.hierarchy} "
                f"hypothesis_leading={None if graph is None else graph.leading} voi_skipped={sum(1 for row in voi_log if not row.get('selected'))}."
            ),
        ),
        rationale=rationale,
    )
    from genome_skeptic.claims.actions import recommended_followups
    from genome_skeptic.claims.completeness import attach_completeness
    apply_c = getattr(settings.execution, "apply_completeness_to_confidence", True)
    attach_completeness(claim, tools_unavailable=m.tools_unavailable, apply_to_confidence=apply_c and m.falsification_enabled)
    claim.raw_confidence = claim.confidence
    claim.recommended_next_actions = recommended_followups([claim])
    for row in voi_log:
        prefix = str(row.get("test_id") or "").split(":")[0]
        executed = next((t for t in tests if t.test_id.split(":")[0] == prefix), None)
        row["evidence_produced"] = list(executed.evidence_ids) if executed else []
        row["changed_claim"] = bool(executed and executed.result in {FalsificationResult.rejects_claim, FalsificationResult.weakens_claim})
        row["changed_confidence"] = bool(executed and executed.result != FalsificationResult.not_run)
        row["changed_recommended_next_action"] = bool(executed and executed.status == "completed")
    if voi_log:
        n_unnec = sum(1 for r in voi_log if not r.get("selected"))
        n_sel = sum(1 for r in voi_log if r.get("selected"))
        claim.provenance.notes += (
            f" unnecessary_tool_call_rate={0 if not voi_log else round(n_unnec / max(1, n_unnec + n_sel), 4)}"
            f" voi_selected={n_sel} voi_skipped={n_unnec}"
        )
    assert_claim_not_stronger_than_evidence(claim)
    return claim, anomalies_from_tests(m.query_id, tests), tests
