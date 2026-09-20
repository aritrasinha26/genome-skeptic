from genome_skeptic.config import Settings
from genome_skeptic.families import load_family
from genome_skeptic.models import LocusReconstruction, LocusSegment, GeneSearchHit
from genome_skeptic.validators.locus_reconstruction import classify_architecture, reconstruct_locus
from genome_skeptic.validators.paralogy import assess_paralogy, cluster_loci
from genome_skeptic.validators.divergence import is_divergent_full_length
from genome_skeptic.eval.external.compat import classify_task
from genome_skeptic.agents.providers import DryRunProvider, ModelUnavailable, dry_run_adapter
from genome_skeptic.config import LLMConfig


def _hit(contig, start, end, ident=0.99, cov=0.99, qid="NP_418414.1"):
    return GeneSearchHit(
        query_id=qid, contig_id=contig, search_kind="translated",
        qstart=0, qend=1200, tstart=start, tend=end, strand="+",
        identity=ident, query_coverage=cov, alignment_length=end - start,
        query_length=1342, contig_length=20000,
    )


def test_two_full_copies_are_close_paralogue_not_canonical():
    settings = Settings()
    family = load_family("rpoB_RNAP_beta")
    rec = LocusReconstruction(
        contig="chr", strand="+", genomic_start=100, genomic_end=4200,
        hmm_coverage=0.99, sequence_identity=0.99, query_identity=0.99, contig_edge=False,
        candidate_segments=[LocusSegment(contig="chr", strand="+", genomic_start=100, genomic_end=4200, hmm_from=1, hmm_to=1200, orf_id="chr:100-4200:+")],
        paralogue_record={
            "kind": "true_duplicated_paralogue",
            "classify_as": "close_paralogue",
            "primary_locus": {"contig": "chr"},
            "secondary_locus": {"contig": "c2"},
        },
    )
    rec = classify_architecture(reconstruction=rec, family=family, member_hits=[], partner_hits=[], partner_hmm={}, settings=settings)
    assert rec.architecture == "close_paralogue"


def test_complementary_fragments_are_not_paralogue():
    settings = Settings()
    segs = [
        LocusSegment(contig="c1", strand="+", genomic_start=100, genomic_end=2000, hmm_from=1, hmm_to=500, orf_id="c1:100-2000:+"),
        LocusSegment(contig="c2", strand="+", genomic_start=0, genomic_end=1900, hmm_from=501, hmm_to=1200, orf_id="c2:0-1900:+"),
    ]
    loci = cluster_loci(segs, 1200, settings)
    blobs = [
        {"contig": "c1", "genomic_start": 100, "genomic_end": 2000, "hmm_from": 1, "hmm_to": 500, "hmm_coverage": 0.42, "contig_length": 2500, "contig_edge": True, "gc": 0.5, "orf_ids": ["c1:100-2000:+"]},
        {"contig": "c2", "genomic_start": 0, "genomic_end": 1900, "hmm_from": 501, "hmm_to": 1200, "hmm_coverage": 0.58, "contig_length": 2500, "contig_edge": True, "gc": 0.5, "orf_ids": ["c2:0-1900:+"]},
    ]
    rec = assess_paralogy(loci=blobs, member_hits=[_hit("c1", 100, 2000, 0.99, 0.4), _hit("c2", 0, 1900, 0.99, 0.4, qid="NP_215181.1")], query_hits=[], settings=settings)
    assert rec is not None
    assert rec["classify_as"] == "assembly_fragmented"
    assert rec["kind"] == "assembly_fragments_of_one_gene"


def test_same_orf_hmm_domains_are_one_locus():
    settings = Settings()
    segs = [
        LocusSegment(contig="c1", strand="+", genomic_start=0, genomic_end=4926, hmm_from=3, hmm_to=1218, orf_id="c1:0-4926:+"),
        LocusSegment(contig="c1", strand="+", genomic_start=0, genomic_end=4926, hmm_from=257, hmm_to=391, orf_id="c1:0-4926:+"),
    ]
    loci = cluster_loci(segs, 1221, settings)
    assert len(loci) == 1
    blobs = [
        {"contig": "c1", "genomic_start": 0, "genomic_end": 4926, "hmm_from": 3, "hmm_to": 1218, "hmm_coverage": 0.99, "contig_length": 5829, "contig_edge": True, "gc": 0.43, "orf_ids": ["c1:0-4926:+"], "identity": 1.0, "coverage": 1.0},
        {"contig": "c1", "genomic_start": 0, "genomic_end": 4926, "hmm_from": 257, "hmm_to": 391, "hmm_coverage": 0.11, "contig_length": 5829, "contig_edge": True, "gc": 0.43, "orf_ids": ["c1:0-4926:+"], "identity": 1.0, "coverage": 1.0},
    ]
    rec = assess_paralogy(loci=blobs, member_hits=[_hit("c1", 0, 4926)], query_hits=[_hit("c1", 0, 4926)], settings=settings)
    assert rec is None


def test_plasmid_length_not_overwritten_by_gc():
    settings = Settings()
    blobs = [
        {"contig": "chr", "genomic_start": 100, "genomic_end": 4200, "hmm_from": 1, "hmm_to": 1200, "hmm_coverage": 0.99, "contig_length": 80_000, "contig_edge": False, "gc": 0.02, "orf_ids": ["a"], "query_identity": 0.99, "identity": 0.99, "coverage": 0.99},
        {"contig": "plasmid", "genomic_start": 50, "genomic_end": 4150, "hmm_from": 1, "hmm_to": 1200, "hmm_coverage": 0.99, "contig_length": 4_400, "contig_edge": False, "gc": 0.55, "orf_ids": ["b"], "query_identity": 0.99, "identity": 0.99, "coverage": 0.99},
    ]
    rec = assess_paralogy(loci=blobs, member_hits=[], query_hits=[], settings=settings)
    assert rec["kind"] == "plasmid_copy"
    assert rec["classify_as"] == "close_paralogue"


def test_contaminant_kind_from_gc_without_plasmid_length():
    settings = Settings()
    blobs = [
        {"contig": "chr", "genomic_start": 100, "genomic_end": 4200, "hmm_from": 1, "hmm_to": 1200, "hmm_coverage": 0.99, "contig_length": 8_000, "contig_edge": False, "gc": 0.51, "contig_gc": 0.51, "orf_ids": ["a"], "query_identity": 0.99, "identity": 0.99, "coverage": 0.99},
        {"contig": "foreign", "genomic_start": 100, "genomic_end": 4200, "hmm_from": 1, "hmm_to": 1200, "hmm_coverage": 0.99, "contig_length": 9_000, "contig_edge": False, "gc": 0.20, "contig_gc": 0.20, "orf_ids": ["b"], "query_identity": 0.99, "identity": 0.99, "coverage": 0.99},
    ]
    rec = assess_paralogy(loci=blobs, member_hits=[], query_hits=[], settings=settings)
    assert rec["kind"] == "contaminant_copy"
    assert rec["classify_as"] == "close_paralogue"


def test_same_contig_edge_is_not_two_fragments():
    settings = Settings()
    blobs = [
        {"contig": "c1", "genomic_start": 0, "genomic_end": 2100, "hmm_from": 1, "hmm_to": 600, "hmm_coverage": 0.5, "contig_length": 9000, "contig_edge": True, "gc": 0.5, "orf_ids": ["a"], "identity": 0.9, "coverage": 0.5},
        {"contig": "c1", "genomic_start": 2200, "genomic_end": 4300, "hmm_from": 601, "hmm_to": 1200, "hmm_coverage": 0.5, "contig_length": 9000, "contig_edge": False, "gc": 0.5, "orf_ids": ["b"], "identity": 0.9, "coverage": 0.5},
    ]
    rec = assess_paralogy(loci=blobs, member_hits=[], query_hits=[], settings=settings)
    assert rec is None or rec.get("classify_as") != "assembly_fragmented"


def test_recent_duplication_kind_when_identities_match():
    settings = Settings()
    blobs = [
        {"contig": "chr", "genomic_start": 100, "genomic_end": 4200, "hmm_from": 1, "hmm_to": 1200, "hmm_coverage": 0.99, "contig_length": 20000, "contig_edge": False, "gc": 0.51, "orf_ids": ["a"], "query_identity": 0.99, "identity": 0.99, "coverage": 0.99},
        {"contig": "c2", "genomic_start": 100, "genomic_end": 4200, "hmm_from": 1, "hmm_to": 1200, "hmm_coverage": 0.99, "contig_length": 18000, "contig_edge": False, "gc": 0.51, "orf_ids": ["b"], "query_identity": 0.99, "identity": 0.99, "coverage": 0.99},
    ]
    rec = assess_paralogy(loci=blobs, member_hits=[], query_hits=[], settings=settings)
    assert rec["kind"] == "recent_gene_duplication"
    assert rec["classify_as"] == "close_paralogue"


def test_equivalent_rbh_not_auto_paralogue():
    settings = Settings()
    blobs = [
        {"contig": "chr", "genomic_start": 100, "genomic_end": 4200, "hmm_from": 1, "hmm_to": 1200, "hmm_coverage": 0.99, "contig_length": 20000, "contig_edge": False, "gc": 0.5, "orf_ids": ["a"], "identity": 0.9, "coverage": 0.99, "orthologue_flags": {"rbh": True}},
        {"contig": "c2", "genomic_start": 100, "genomic_end": 4200, "hmm_from": 1, "hmm_to": 1200, "hmm_coverage": 0.99, "contig_length": 20000, "contig_edge": False, "gc": 0.5, "orf_ids": ["b"], "identity": 0.9, "coverage": 0.99, "orthologue_flags": {"rbh": True}},
    ]
    rec = assess_paralogy(loci=blobs, member_hits=[], query_hits=[], settings=settings)
    assert rec["classify_as"] is None
    assert rec["kind"] == "equivalent_orthologue_copies"


def test_divergence_uses_family_split_not_hard_060():
    dist = {"split": 0.74, "median_close": 1.0, "median_other": 0.48}
    assert is_divergent_full_length(0.55, dist) is True
    assert is_divergent_full_length(0.99, dist) is False
    assert is_divergent_full_length(0.80, dist) is False


def test_domain_gate_unchanged():
    settings = Settings()
    assert settings.thresholds.hmm_min_gate_model_coverage == 0.20


def test_external_classifier_does_not_rewrite():
    rna = classify_task("scrna", "Seurat single-cell RNA-seq", ["single-cell"])
    assert rna["compatibility"] == "unsupported"
    assert rna["prompt_rewritten"] is False
    assert rna["scored_as_genome_skeptic"] is False
    bact = classify_task("amr", "Detect AMR genes in a bacterial isolate FASTA", ["bacterial", "amr gene"])
    assert bact["compatibility"] == "supported"


def test_dry_run_does_not_invent_output():
    p = DryRunProvider("qwen3:8b")
    try:
        p.complete_json("sys", "user")
        assert False, "dry-run must not return invented JSON"
    except ModelUnavailable:
        pass
    cfg = LLMConfig()
    report = dry_run_adapter(cfg, "qwen3")
    assert report["invented_output"] is False
