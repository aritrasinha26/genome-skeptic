from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit, LocusSegment
from genome_skeptic.validators.locus_multiplicity import assess_multiplicity, _cluster_hits
from genome_skeptic.validators.competitive_family import CompetitiveFamilyEvidence, _hydrophobic_tm_windows
from genome_skeptic.eval.external.compat import classify_task
from genome_skeptic.agents.providers import resolve_named_model, ModelUnavailable, DryRunProvider, setup_instructions
from genome_skeptic.config import LLMConfig


def _hit(contig, start, end, ident=0.99, cov=0.99):
    return GeneSearchHit(
        query_id="tuf", contig_id=contig, search_kind="translated",
        qstart=0, qend=350, tstart=start, tend=end, strand="+",
        identity=ident, query_coverage=cov, alignment_length=end - start,
        query_length=359, contig_length=20000,
    )


def test_near_identical_copies_are_two_loci():
    settings = Settings()
    hits = [_hit("chr", 100, 1200, 0.99, 0.99), _hit("chr", 5000, 6100, 0.99, 0.99)]
    rec = assess_multiplicity(family_id="tuf_EF_Tu", member_hits=hits, query_hits=hits, hmm_loci=[], contig_sequences={"chr": "A" * 8000}, settings=settings)
    assert rec["number_of_candidate_loci"] >= 2
    assert rec["classification"] in {"true_gene_duplication", "recent_duplication", "paralogous_copy"}
    assert rec["provenance"]["collapsed_near_identical_copies"] is False


def test_overlapping_hits_are_one_locus():
    settings = Settings()
    hits = [_hit("chr", 100, 1200, 0.99, 0.99), _hit("chr", 150, 1180, 0.98, 0.95)]
    rec = assess_multiplicity(family_id="tuf_EF_Tu", member_hits=hits, query_hits=[], hmm_loci=[], contig_sequences={"chr": "A" * 3000}, settings=settings)
    assert rec["number_of_candidate_loci"] == 1
    assert rec["classification"] == "single_locus"


def test_competitive_object_fields():
    ev = CompetitiveFamilyEvidence(target_family="tetA_tetracycline_efflux", classification="competing_family_preferred")
    blob = ev.as_dict()
    for key in ("target_family", "candidate_locus", "score_margin", "best_competing_family", "classification", "evidence_ids", "provenance"):
        assert key in blob
    assert blob["classification"] != "target_family_supported"


def test_hydrophobic_windows_are_measured():
    aa = "AILMFWV" * 20 + "DEKR" * 10
    assert _hydrophobic_tm_windows(aa) >= 1


def test_domain_gate_unchanged():
    settings = Settings()
    assert settings.thresholds.hmm_min_gate_model_coverage == 0.20


def test_gpt_is_not_a_silent_substitute_for_qwen():
    assert resolve_named_model("qwen3", []) is None
    p = DryRunProvider("qwen3:8b")
    try:
        p.complete_json("s", "u")
        assert False
    except ModelUnavailable:
        pass
    setup = setup_instructions([])
    assert setup["no_silent_substitution"] is True


def test_external_classifier_still_does_not_rewrite():
    rna = classify_task("scrna", "Seurat single-cell RNA-seq", ["single-cell"])
    assert rna["compatibility"] == "unsupported"
    assert rna["prompt_rewritten"] is False
    assert rna["scored_as_genome_skeptic"] is False


def test_recA_family_class_is_not_biological_property():
    from genome_skeptic.families import load_family
    rec = load_family("recA_recombinase")
    assert rec is not None
    assert rec.family_class == ""
    assert rec.competing_families == []


def test_pairwise_hits_cannot_override_competing_family():
    from genome_skeptic.models import ClaimType, TargetType
    from genome_skeptic.validators.falsification import classify_polarity
    from genome_skeptic.validators.family_orthology import FamilyEvidence

    settings = Settings()
    hits = [_hit("chr", 100, 1200, 0.99, 0.99)]
    fam = FamilyEvidence(
        family_id="tetA_tetracycline_efflux",
        reconstruction={"competitive_family": {"classification": "competing_family_preferred", "competitors_scored": [{"family_id": "mfs_multidrug_efflux"}]}, "architecture": "true_no_candidate"},
        supports_orthologue=False,
    )
    assert classify_polarity(hits, settings, TargetType.gene_orthologue, family_evidence=fam) == ClaimType.target_gene_not_detected
