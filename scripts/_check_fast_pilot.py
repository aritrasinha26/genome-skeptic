from pathlib import Path
from tempfile import TemporaryDirectory

from genome_skeptic.config import Settings, is_fast_pilot, load_settings
from genome_skeptic.eval.catalog import FAST_PILOT_GENOME_IDS, GenomeSpec, genomes_for
from genome_skeptic.eval.evaluate_real import _markdown
from genome_skeptic.eval.freeze import build_freeze_manifest
from genome_skeptic.eval.generate import _unique_cds
from genome_skeptic.eval.production import spades_argv
from genome_skeptic.eval.real_genomes import write_real_genome_benchmark
import yaml

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")


def main():
    r1 = Path("/tmp/gs_r1.fastq")
    r2 = Path("/tmp/gs_r2.fastq")
    r1.write_text("@a\nACGT\n+\nIIII\n")
    r2.write_text("@a\nACGT\n+\nIIII\n")
    cmd = spades_argv(r1, r2, Path("/tmp/spades"), 2, 4)
    assert "--isolate" in cmd and "--only-assembler" not in cmd and "--careful" not in cmd
    cmd2 = spades_argv(r1, r2, Path("/tmp/spades"), 4, 3, only_assembler=True, kmers="21,33,55", careful=False, isolate=False)
    assert "--only-assembler" in cmd2 and "--careful" not in cmd2 and "--isolate" not in cmd2
    assert cmd2[cmd2.index("-k") + 1] == "21,33,55"
    settings = Settings()
    assert not is_fast_pilot(settings)
    loaded = load_settings(ROOT / "config" / "fast_pilot.yaml")
    default = Settings()
    assert loaded.thresholds.model_dump() == default.thresholds.model_dump()
    assert is_fast_pilot(loaded)
    dev = genomes_for("development", profile="fast_pilot")
    held = genomes_for("held_out", profile="fast_pilot")
    assert [g.genome_id for g in dev] == list(FAST_PILOT_GENOME_IDS["development"])
    assert [g.genome_id for g in held] == list(FAST_PILOT_GENOME_IDS["held_out"])
    assert len(genomes_for("development")) == 4
    payload = build_freeze_manifest(loaded)
    assert payload["fast_pilot"] is True
    assert len(payload["catalog_genome_ids"]["development"]) == 3
    prod = build_freeze_manifest(Settings())
    assert prod["fast_pilot"] is False
    md = _markdown({"fast_pilot": True, "split": "development", "production": {}, "systems": {}, "highlights": [], "error_analysis": []})
    assert "FAST PILOT - NOT FINAL BENCHMARK" in md
    with TemporaryDirectory() as td:
        tmp = Path(td)
        seq = _unique_cds("rpoB", 40)
        genomes = []
        for i, gid in enumerate(("ecoli_k12", "pao1", "hpylori")):
            fa = tmp / f"{gid}.fa"
            fa.write_text(f">chrom\n{'A' * 200}{seq}{'C' * 200}\n")
            genomes.append((
                GenomeSpec(gid, f"NC_T{i}", "Escherichia coli TEST", "complete", "development", "local", "file://x", 0.001, 50.0, "fixture"),
                fa,
                {"ok": True, "accession": f"NC_T{i}"},
            ))
        summary = write_real_genome_benchmark(tmp / "bench", genomes, split="development", require_production_simulator=False, profile="fast_pilot")
        assert summary["n_cases"] == 3
        assert summary["clean_coverage"] == 25
        truth = yaml.safe_load((tmp / "bench" / "hidden" / "truth.yaml").read_text())
        assert all(c["simulation"]["coverage"] == 25 for c in truth["cases"].values())
    print("FAST_PILOT_TESTS_OK")


if __name__ == "__main__":
    main()
