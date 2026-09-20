from genome_skeptic.eval.catalog import GenomeSpec, genomes_for
from genome_skeptic.eval.generate import _unique_cds
from genome_skeptic.eval.production import assemble_with_spades
from genome_skeptic.eval.real_genomes import write_real_genome_benchmark
from genome_skeptic.eval.sandbox import make_sandbox
from genome_skeptic.isolation import assert_agent_accessible
import pytest


def test_catalog_has_disjoint_splits():
    dev = {g.accession for g in genomes_for("development")}
    held = {g.accession for g in genomes_for("held_out")}
    assert dev
    assert held
    assert dev.isdisjoint(held)
    assert any("Pseudomonas" in g.species for g in genomes_for("development"))
    assert sum("Pseudomonas" in g.species for g in genomes_for("development") + genomes_for("held_out")) >= 2
    assert any(g.plasmids for g in genomes_for("held_out") + genomes_for("development"))


def test_toy_assembler_not_used_by_production_helper(tmp_path):
    r1 = tmp_path / "r1.fastq"
    r1.write_text("@a\nACGT\n+\nIIII\n")
    contigs, info = assemble_with_spades(r1, None, tmp_path / "asm")
    if contigs is None:
        assert "toy" in info.get("note", "").lower() or info.get("unavailable") == "spades.py"
    else:
        assert info.get("assembler") == "SPAdes"


def test_sandbox_copy_cannot_include_hidden(tmp_path):
    vis = tmp_path / "agent_visible" / "case_01"
    vis.mkdir(parents=True)
    (vis / "reads_R1.fastq").write_text("@a\nACGT\n+\nIIII\n")
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    (hidden / "truth.yaml").write_text("cases: {}\n")
    sandbox = make_sandbox(vis, tmp_path / "work", hidden)
    assert sandbox.exists()
    assert not (sandbox / "truth.yaml").exists()
    with pytest.raises(PermissionError):
        assert_agent_accessible(hidden / "truth.yaml")


def test_real_genome_generator_from_local_fasta_keeps_accessions_hidden(tmp_path):
    seq = _unique_cds("rpoB", 40)
    fa = tmp_path / "src.fa"
    fa.write_text(f">chrom\n{'A' * 200}{seq}{'C' * 200}\n")
    spec = GenomeSpec(
        "toy_dev", "NC_TEST", "Escherichia coli TEST", "complete", "development",
        "local fixture", "file://local", 0.001, 50.0, "unit-test fixture",
    )
    root = tmp_path / "bench"
    summary = write_real_genome_benchmark(root, [(spec, fa, {"ok": True, "accession": "NC_TEST"})], split="development", require_production_simulator=False)
    assert summary["n_cases"] >= 1
    visible_blob = "\n".join(p.read_text() for p in (root / "agent_visible").rglob("case.yaml"))
    assert "NC_TEST" not in visible_blob
    assert "accession" not in visible_blob
    hidden_truth = (root / "hidden" / "truth.yaml").read_text()
    assert "development" in hidden_truth
    catalog = (root / "hidden" / "genome_catalog.yaml").read_text()
    assert "NC_TEST" in catalog
    visible_reads = "\n".join(p.read_text()[:200] for p in (root / "agent_visible").rglob("*.fastq"))
    assert "NC_TEST" not in visible_reads
    assert "NC_000913" not in visible_reads
