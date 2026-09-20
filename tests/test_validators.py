from genome_skeptic.config import Settings
from genome_skeptic.models import Severity
from genome_skeptic.validators.core import (
    validate_annotation,
    validate_assembly,
    validate_completeness,
    validate_fastp,
    validate_mapping,
)


def test_large_fragmented_assembly_is_flagged():
    a = validate_assembly({"total_bp": 20_000_000, "contigs": 900, "n50_bp": 5_000}, Settings())
    ids = {x.id for x in a}
    assert "assembly_too_large" in ids
    assert "assembly_fragmented" in ids
    assert "assembly_low_n50" in ids


def test_high_contamination_is_hard_gate():
    a = validate_completeness({"completeness": 99.0, "contamination": 15.0}, Settings())
    assert any(x.id == "high_contamination_hard" and x.severity == Severity.hard for x in a)


def test_fastp_low_q30_and_heavy_loss_are_warnings():
    a = validate_fastp({"q30_rate": 0.4, "before_total_reads": 1000, "after_total_reads": 200}, Settings())
    ids = {x.id for x in a}
    assert "qc_low_q30" in ids
    assert "qc_heavy_read_loss" in ids
    assert all(x.severity == Severity.warning for x in a)


def test_mapping_anomalies_are_warnings_not_hard_gates():
    a = validate_mapping({"mapping_rate": 0.4, "zero_coverage_fraction": 0.2, "depth_cv": 1.5}, Settings())
    ids = {x.id for x in a}
    assert "mapping_low_rate" in ids
    assert "mapping_zero_coverage" in ids
    assert "mapping_heterogeneous_depth" in ids
    assert all(x.severity != Severity.hard for x in a)


def test_annotation_unusual_density_is_flagged():
    metrics = {"cds": 10}
    a = validate_annotation(metrics, {"total_bp": 1_000_000}, Settings())
    assert any(x.id == "annotation_gene_density" for x in a)
    assert "gene_density_per_kb" in metrics
