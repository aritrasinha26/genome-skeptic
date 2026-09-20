from pathlib import Path

import yaml

from genome_skeptic.config import Settings, is_fast_pilot, load_settings
from genome_skeptic.eval.catalog import FAST_PILOT_GENOME_IDS, genomes_for
from genome_skeptic.eval.evaluate_real import _markdown
from genome_skeptic.eval.freeze import build_freeze_manifest
from genome_skeptic.eval.production import spades_argv
from genome_skeptic.eval.real_genomes import write_real_genome_benchmark
from genome_skeptic.eval.generate import _unique_cds
from genome_skeptic.eval.catalog import GenomeSpec


ROOT = Path(__file__).resolve().parents[1]


def test_production_spades_command_unchanged_by_default(tmp_path):
    r1 = tmp_path / "r1.fastq"
    r1.write_text("@a\nACGT\n+\nIIII\n")
    r2 = tmp_path / "r2.fastq"
    r2.write_text("@a\nACGT\n+\nIIII\n")
    cmd = spades_argv(r1, r2, tmp_path / "spades", 2, 4)
    assert "--isolate" in cmd
    assert "--only-assembler" not in cmd
    assert "--careful" not in cmd
    assert "-k" not in cmd
    settings = Settings()
    assert settings.assembly.profile == "production"
    assert settings.assembly.isolate is True
    assert settings.assembly.only_assembler is False
    assert settings.assembly.careful is False
    assert not is_fast_pilot(settings)


def test_fast_pilot_spades_skips_large_kmers_and_careful(tmp_path):
    r1 = tmp_path / "r1.fastq"
    r1.write_text("@a\nACGT\n+\nIIII\n")
    r2 = tmp_path / "r2.fastq"
    r2.write_text("@a\nACGT\n+\nIIII\n")
    cmd = spades_argv(
        r1, r2, tmp_path / "spades", 4, 3,
        only_assembler=True, kmers="21,33,55", careful=False, isolate=False,
    )
    assert "--only-assembler" in cmd
    assert cmd[cmd.index("-k") + 1] == "21,33,55"
    assert "--careful" not in cmd
    assert "--isolate" not in cmd
    joined = " ".join(cmd)
    assert "77" not in joined and "99" not in joined and "127" not in joined


def test_fast_pilot_genomes_are_three_plus_three_and_diverse():
    dev = genomes_for("development", profile="fast_pilot")
    held = genomes_for("held_out", profile="fast_pilot")
    assert [g.genome_id for g in dev] == list(FAST_PILOT_GENOME_IDS["development"])
    assert [g.genome_id for g in held] == list(FAST_PILOT_GENOME_IDS["held_out"])
    assert len(dev) == 3
    assert len(held) == 3
    assert any("Pseudomonas" in g.species for g in dev)
    assert any("Escherichia" in g.species for g in dev)
    assert any(g.approx_mb < 2.0 for g in dev)
    assert any("Pseudomonas" in g.species for g in held)
    assert any("Salmonella" in g.species for g in held)
    assert any(g.approx_mb < 3.5 for g in held)
    full_dev = genomes_for("development")
    assert len(full_dev) == 4


def test_fast_pilot_yaml_does_not_change_thresholds():
    loaded = load_settings(ROOT / "config" / "fast_pilot.yaml")
    default = Settings()
    assert loaded.thresholds.model_dump() == default.thresholds.model_dump()
    assert loaded.execution.enable_falsification is True
    assert is_fast_pilot(loaded)
    assert loaded.assembly.kmers == "21,33,55"
    assert loaded.assembly.only_assembler is True
    assert loaded.assembly.careful is False


def test_fast_pilot_generator_uses_25x_and_three_cases(tmp_path):
    seq = _unique_cds("rpoB", 40)
    genomes = []
    for i, gid in enumerate(("ecoli_k12", "pao1", "hpylori")):
        fa = tmp_path / f"{gid}.fa"
        fa.write_text(f">chrom\n{'A' * 200}{seq}{'C' * 200}\n")
        genomes.append((
            GenomeSpec(gid, f"NC_T{i}", "Escherichia coli TEST", "complete", "development", "local", "file://x", 0.001, 50.0, "fixture"),
            fa,
            {"ok": True, "accession": f"NC_T{i}"},
        ))
    root = tmp_path / "bench"
    summary = write_real_genome_benchmark(
        root, genomes, split="development", require_production_simulator=False, profile="fast_pilot",
    )
    assert summary["n_cases"] == 3
    assert summary["kind"] == "fast_pilot_real_genome"
    assert summary["clean_coverage"] == 25
    truth = yaml.safe_load((root / "hidden" / "truth.yaml").read_text())
    assert set(truth["cases"]) == {"dev_01", "dev_02", "dev_03"}
    assert all(c["simulation"]["coverage"] == 25 for c in truth["cases"].values())
    assert all(c["corruption"] == "none" for c in truth["cases"].values())


def test_fast_pilot_freeze_and_report_are_labelled():
    settings = load_settings(ROOT / "config" / "fast_pilot.yaml")
    payload = build_freeze_manifest(settings)
    assert payload["fast_pilot"] is True
    assert "FAST PILOT - NOT FINAL BENCHMARK" in payload["note"]
    assert len(payload["catalog_genome_ids"]["development"]) == 3
    assert payload["assembly"]["only_assembler"] is True
    md = _markdown({
        "fast_pilot": True,
        "split": "development",
        "production": {"assembled": 3, "assembly_unavailable": 0, "inventory": {}},
        "missing_dimensions": [],
        "failed_tools": [],
        "missing_databases": ["Bakta database"],
        "systems": {},
        "highlights": [],
        "error_analysis": [],
    })
    assert "FAST PILOT - NOT FINAL BENCHMARK" in md
    prod = build_freeze_manifest(Settings())
    assert prod["fast_pilot"] is False
    assert len(prod["catalog_genome_ids"]["development"]) == 4
