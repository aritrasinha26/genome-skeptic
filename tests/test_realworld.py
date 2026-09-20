from pathlib import Path

import pytest
import yaml

from genome_skeptic.config import Settings
from genome_skeptic.eval.baselines import run_conventional
from genome_skeptic.eval.generate import write_realworld_benchmark
from genome_skeptic.eval.realworld import evaluate_realworld
from genome_skeptic.isolation import assert_agent_accessible
from genome_skeptic.locus.pipeline import analyze_targets_on_assembly
from genome_skeptic.models import ClaimStatus


def test_agent_cannot_read_hidden_truth(tmp_path: Path):
    hidden = tmp_path / "hidden" / "truth.yaml"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("cases: {}\n")
    with pytest.raises(PermissionError):
        assert_agent_accessible(hidden)
    with pytest.raises(PermissionError):
        analyze_targets_on_assembly(
            targets=hidden,
            assembly=hidden,
            settings=Settings(),
            out_dir=tmp_path / "out",
        )


def test_visible_fastq_does_not_contain_scorer_metadata(tmp_path: Path):
    root = write_realworld_benchmark(tmp_path / "rw")
    visible = root / "agent_visible"
    hidden = root / "hidden" / "truth.yaml"
    assert hidden.exists()
    blob = "\n".join(p.read_text() for p in visible.rglob("case.yaml"))
    assert "corruption" not in blob
    assert "true_organism" not in blob
    assert "simulation_provenance" not in blob
    assert (visible / "case_01" / "reads_R1.fastq").exists()
    assert len([p for p in visible.iterdir() if p.is_dir()]) == 14
    truth = yaml.safe_load(hidden.read_text())
    labels = {row.get("label") for row in truth["cases"].values()}
    assert "cross_species_contamination" in labels
    assert "genuine_absence" in labels
    assert all(cid.startswith("case_") for cid in truth["cases"])


def test_conventional_uses_assembly_scoped_homology(tmp_path: Path):
    asm = tmp_path / "empty.fa"
    asm.write_text(">c1\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n")
    targets = tmp_path / "targets.fa"
    targets.write_text(">rpoB\nATGCGTAGCTAAATGCGTAGCTAAATGCGTAGCTAAATGCGTAGCTAA\n")
    claims = run_conventional(asm, targets, tmp_path / "conv", Settings())
    assert claims
    blob = claims[0].statement.lower()
    assert "absent from the organism" not in blob
    assert "present in the isolate" not in blob
    assert "assembly" in blob
    assert claims[0].confidence < 0.95


def test_realworld_three_system_comparison(tmp_path: Path):
    root = write_realworld_benchmark(tmp_path / "rw")
    report = evaluate_realworld(root / "agent_visible", root / "hidden" / "truth.yaml", tmp_path / "eval", Settings())
    assert set(report["systems"]) == {"conventional", "skeptic_no_falsification", "genome_skeptic"}
    assert len(report["cases"]) == 14
    gs = report["systems"]["genome_skeptic"]
    conv = report["systems"]["conventional"]
    assert conv["totals"]["unsupported_overclaiming"]["n"] >= 1
    assert conv["totals"]["unsupported_overclaiming"]["correct"] < conv["totals"]["unsupported_overclaiming"]["n"]
    assert gs["totals"]["unsupported_overclaiming"]["correct"] >= conv["totals"]["unsupported_overclaiming"]["correct"]
    no_f = report["systems"]["skeptic_no_falsification"]["targets"]
    assert any(row.get("claim_status") == ClaimStatus.unresolved.value for row in no_f)
    assert (tmp_path / "eval" / "realworld_report.md").exists()
    assert report["limitations"]
