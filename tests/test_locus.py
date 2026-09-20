from pathlib import Path

from genome_skeptic.config import ExecutionConfig, Settings
from genome_skeptic.locus.orthology import classify_orthology, reciprocal_best_hits
from genome_skeptic.locus.pipeline import analyze_targets_on_assembly
from genome_skeptic.locus.synteny import compare_neighborhood
from genome_skeptic.locus.validate import build_locus_evidence
from genome_skeptic.models import (
    ClaimStatus,
    ClaimType,
    FalsificationResult,
    GeneOrderItem,
    GeneSearchHit,
    LocusEvidence,
    TargetProfile,
)
from genome_skeptic.orchestrator import REGISTERED_ACTIONS
from genome_skeptic.tools.gene_search import translate_frame
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim
from genome_skeptic.validators.homology import FORBIDDEN_ABSENCE_PHRASES


GENE = "ATG" + ("CGTAGC") * 20 + "TAA"
DNAA = "ATG" + ("GATCGA") * 18 + "TAA"
RPOC = "ATG" + ("TTAGGC") * 18 + "TAA"


def _aa(seq: str) -> str:
    return translate_frame(seq, 0).split("*")[0]


def _hit(**kwargs) -> GeneSearchHit:
    data = {
        "query_id": "rpoB",
        "contig_id": "c1",
        "search_kind": "nucleotide",
        "qstart": 0,
        "qend": len(GENE),
        "tstart": 144,
        "tend": 144 + len(GENE),
        "strand": "+",
        "identity": 1.0,
        "query_coverage": 1.0,
        "alignment_length": len(GENE),
        "query_length": len(GENE),
        "contig_length": 500,
    }
    data.update(kwargs)
    return GeneSearchHit.model_validate(data)


def test_registered_locus_actions_remain_whitelisted():
    assert "compare_locus_to_reference" in REGISTERED_ACTIONS
    assert "reciprocal_best_hit_search" in REGISTERED_ACTIONS
    assert "inspect_gene_order_against_reference" in REGISTERED_ACTIONS


def test_reciprocal_best_hit_is_deterministic():
    settings = Settings()
    query = [("rpoB", _aa(GENE))]
    ref = [("dnaA", _aa(DNAA)), ("rpoB", _aa(GENE)), ("rpoC", _aa(RPOC))]
    records = reciprocal_best_hits(query, ref, settings)
    assert records
    best = max(records, key=lambda r: r.identity * r.query_coverage)
    assert best.subject_id == "rpoB"
    assert best.reciprocal_best_hit is True
    kind, conflicts = classify_orthology(records, settings)
    assert kind == "ortholog"
    assert "not_reciprocal_best_hit" not in conflicts


def test_synteny_detects_inverted_gene_order():
    query = [
        GeneOrderItem(gene_id="rpoC", product="rpoC", start=1, end=20, strand="+", is_target=False),
        GeneOrderItem(gene_id="rpoB", product="rpoB", start=30, end=50, strand="+", is_target=True),
        GeneOrderItem(gene_id="dnaA", product="dnaA", start=60, end=80, strand="+", is_target=False),
    ]
    ref = [
        GeneOrderItem(gene_id="dnaA", product="dnaA", start=1, end=20, strand="+", is_target=False),
        GeneOrderItem(gene_id="rpoB", product="rpoB", start=30, end=50, strand="+", is_target=True),
        GeneOrderItem(gene_id="rpoC", product="rpoC", start=60, end=80, strand="+", is_target=False),
    ]
    assert "gene_order_inverted" in compare_neighborhood(query, ref)


def test_locus_evidence_records_required_fields():
    settings = Settings()
    assembly = "N" * 30 + DNAA + "N" * 30 + GENE + "N" * 30 + RPOC + "N" * 30
    rpo_start = 30 + len(DNAA) + 30
    features = [
        {"seqid": "c1", "type": "cds", "start": 31, "end": 30 + len(DNAA), "strand": "+", "product": "dnaA", "gene_id": "dnaA"},
        {"seqid": "c1", "type": "cds", "start": rpo_start + 1, "end": rpo_start + len(GENE), "strand": "+", "product": "rpoB", "gene_id": "rpoB"},
        {"seqid": "c1", "type": "cds", "start": rpo_start + len(GENE) + 31, "end": rpo_start + len(GENE) + 30 + len(RPOC), "strand": "+", "product": "rpoC", "gene_id": "rpoC"},
    ]
    ref_features = list(features)
    for feat in ref_features:
        feat = dict(feat)
        feat["seqid"] = "ref"
    refs = [{
        "id": "trusted_reference",
        "taxonomy": "Escherichia coli",
        "features": [
            {**features[0], "seqid": "ref"},
            {**features[1], "seqid": "ref"},
            {**features[2], "seqid": "ref"},
        ],
        "protein_sequences": {"dnaA": _aa(DNAA), "rpoB": _aa(GENE), "rpoC": _aa(RPOC)},
        "sequences": {"ref": assembly},
    }]
    loci = build_locus_evidence(
        profile=TargetProfile(query_id="rpoB", sequence=GENE, expected_taxonomy="Escherichia", expected_neighbors=["dnaA", "rpoC"]),
        hits=[_hit(tstart=rpo_start, tend=rpo_start + len(GENE), contig_length=len(assembly))],
        settings=settings,
        assembly_features=features,
        contig_sequences={"c1": assembly},
        query_proteins={"rpoB": _aa(GENE)},
        references=refs,
    )
    assert loci
    le = loci[0]
    assert isinstance(le, LocusEvidence)
    assert le.target == "rpoB"
    assert le.candidate_locus and le.candidate_locus["contig"] == "c1"
    assert le.reference_genome == "trusted_reference"
    assert le.orthologues
    assert le.gene_order
    assert le.orientation == "+"
    assert "query" in le.distance and "reference" in le.distance
    assert le.sequence_similarity.get("identity") is not None
    assert "query_coverage" in le.sequence_similarity
    assert le.provenance["created_by"] == "deterministic_locus_validator"
    assert "LLM did not invent" in le.provenance["notes"]


def test_inconsistent_synteny_rejects_or_weakens_detection():
    settings = Settings()
    query_genes = [
        {"seqid": "c1", "type": "cds", "start": 1, "end": 20, "strand": "+", "product": "rpoC", "gene_id": "rpoC"},
        {"seqid": "c1", "type": "cds", "start": 144, "end": 144 + len(GENE), "strand": "+", "product": "rpoB", "gene_id": "rpoB"},
        {"seqid": "c1", "type": "cds", "start": 300, "end": 320, "strand": "+", "product": "dnaA", "gene_id": "dnaA"},
    ]
    ref_genes = [
        {"seqid": "ref", "type": "cds", "start": 1, "end": 20, "strand": "+", "product": "dnaA", "gene_id": "dnaA"},
        {"seqid": "ref", "type": "cds", "start": 144, "end": 144 + len(GENE), "strand": "+", "product": "rpoB", "gene_id": "rpoB"},
        {"seqid": "ref", "type": "cds", "start": 300, "end": 320, "strand": "+", "product": "rpoC", "gene_id": "rpoC"},
    ]
    loci = build_locus_evidence(
        profile=TargetProfile(query_id="rpoB", sequence=GENE),
        hits=[_hit()],
        settings=settings,
        assembly_features=query_genes,
        contig_sequences={"c1": "N" * 144 + GENE + "N" * 80},
        query_proteins={},
        references=[{
            "id": "trusted_reference",
            "features": ref_genes,
            "protein_sequences": {"rpoB": _aa(GENE)},
            "sequences": {"ref": "N" * 144 + GENE + "N" * 80},
        }],
    )
    claim, _anoms, tests = build_target_gene_claim(
        TargetMeasurements(
            query_id="rpoB",
            profile=TargetProfile(query_id="rpoB", sequence=GENE),
            hits=[_hit()],
            contig_sequences={"c1": "N" * 144 + GENE + "N" * 80},
            locus_evidence=loci,
            tools_run=["internal_gene_search"],
            annotation_available=True,
        ),
        settings,
        ["E001"],
    )
    order = next(t for t in tests if t.test_id.startswith("local_gene_order"))
    assert order.result in {FalsificationResult.weakens_claim, FalsificationResult.rejects_claim}
    assert claim.status in {ClaimStatus.weakened, ClaimStatus.rejected}
    assert claim.claim_type == ClaimType.target_gene_detected


def test_missing_reference_does_not_block_clean_detection():
    settings = Settings()
    hit = _hit(tstart=80, tend=80 + len(GENE), contig_length=80 + len(GENE) + 80)
    claim, _anoms, tests = build_target_gene_claim(
        TargetMeasurements(
            query_id="rpoB",
            profile=TargetProfile(query_id="rpoB", sequence=GENE),
            hits=[hit],
            contig_sequences={"c1": "A" * 80 + GENE + "C" * 80},
            tools_run=["internal_gene_search"],
        ),
        settings,
        ["E001"],
    )
    assert claim.status == ClaimStatus.supported
    skipped = {t.test_id.split(":")[0] for t in tests if t.status == "skipped"}
    assert "local_gene_order" in skipped
    assert "reciprocal_best_hit" in skipped
    assert all(not t.blocking for t in tests if t.test_id.startswith("local_gene_order"))


def test_not_detected_uses_reference_neighbors(tmp_path: Path):
    # Frozen locus validator still records reference_neighbor_presence.
    # Default VOI policy drops that supporting test because it is not in the
    # diagnostic catalog; disable VOI in this harness only.
    settings = Settings(execution=ExecutionConfig(enable_voi_policy=False))
    from genome_skeptic.eval.synthetic import DNAA as D, RPOC as C, RPOB, SPACER, _fa, _gff, _operon, _proteins, translate

    seq, genes = _operon([("dnaA", D), ("rpoC", C)])
    (tmp_path / "assembly.fa").write_text(_fa({"c1": seq}))
    (tmp_path / "assembly.gff").write_text(_gff("c1", genes))
    (tmp_path / "assembly.faa").write_text(_fa(_proteins({"dnaA": D, "rpoC": C})))
    (tmp_path / "targets.fa").write_text(f">rpoB neighbors=dnaA,rpoC\n{RPOB}\n")
    ref_seq, ref_genes = _operon([("dnaA", D), ("rpoB", RPOB), ("rpoC", C)])
    (tmp_path / "ref.fa").write_text(_fa({"ref": ref_seq}))
    (tmp_path / "ref.gff").write_text(_gff("ref", ref_genes))
    (tmp_path / "ref.faa").write_text(_fa(_proteins({"dnaA": D, "rpoB": RPOB, "rpoC": C})))
    (tmp_path / "references.yaml").write_text(
        "references:\n  - id: trusted_reference\n    fasta: ref.fa\n    gff: ref.gff\n    proteins: ref.faa\n    taxonomy: Escherichia coli\n"
    )
    claims, loci, _ = analyze_targets_on_assembly(
        targets=tmp_path / "targets.fa",
        assembly=tmp_path / "assembly.fa",
        settings=settings,
        assembly_gff=tmp_path / "assembly.gff",
        proteins=tmp_path / "assembly.faa",
        references_yaml=tmp_path / "references.yaml",
        out_dir=tmp_path / "out",
    )
    assert claims
    claim = claims[0]
    assert claim.claim_type == ClaimType.target_gene_not_detected
    blob = (claim.statement + " " + claim.rationale).lower()
    assert all(p not in blob for p in FORBIDDEN_ABSENCE_PHRASES)
    neighbor = next(t for t in claim.falsification_tests if t.test_id.startswith("reference_neighbor_presence"))
    assert neighbor.status == "completed"
    assert loci[0].distance.get("reference_neighbor_products")
