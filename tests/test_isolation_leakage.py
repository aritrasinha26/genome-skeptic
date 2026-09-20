from pathlib import Path

import pytest

from genome_skeptic.claims.actions import classify_actions
from genome_skeptic.isolation import assert_action_args_accessible, assert_agent_accessible, reject_hidden_environment


def test_relative_and_absolute_hidden_paths(tmp_path, monkeypatch):
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    truth = hidden / "truth.yaml"
    truth.write_text("cases: {}\n")
    monkeypatch.setenv("GENOME_SKEPTIC_HIDDEN_ROOTS", str(hidden.resolve()))
    with pytest.raises(PermissionError):
        assert_agent_accessible(truth)
    with pytest.raises(PermissionError):
        assert_agent_accessible(truth.resolve())
    visible = tmp_path / "work" / "case"
    visible.mkdir(parents=True)
    rel = visible / ".." / ".." / "hidden" / "truth.yaml"
    with pytest.raises(PermissionError):
        assert_agent_accessible(rel)


def test_symlink_to_hidden_is_blocked(tmp_path, monkeypatch):
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    truth = hidden / "truth.yaml"
    truth.write_text("x: 1\n")
    monkeypatch.setenv("GENOME_SKEPTIC_HIDDEN_ROOTS", str(hidden.resolve()))
    visible = tmp_path / "agent_visible"
    visible.mkdir()
    link = visible / "sneak.yaml"
    try:
        link.symlink_to(truth)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(PermissionError):
        assert_agent_accessible(link)


def test_config_and_env_and_action_params(tmp_path, monkeypatch):
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    truth = hidden / "source_genome.fa"
    truth.write_text(">g\nAT\n")
    monkeypatch.setenv("GENOME_SKEPTIC_HIDDEN_ROOTS", str(hidden.resolve()))
    monkeypatch.setenv("GENOME_SKEPTIC_TRUTH", str(truth))
    with pytest.raises(PermissionError):
        reject_hidden_environment()
    with pytest.raises(PermissionError):
        assert_action_args_accessible({"fasta": str(truth)})
    with pytest.raises(PermissionError):
        assert_action_args_accessible({"references": str(truth)})
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"paths:\n  references: {truth.as_posix()}\n")
    from genome_skeptic.config import load_settings
    with pytest.raises(PermissionError):
        load_settings(cfg)


def test_extra_useful_actions_are_not_automatically_penalized():
    grouped = classify_actions(
        ["inspect_read_supported_breaks", "inspect_contig_edges_for_target"],
        acceptable_classes=["inspect_paired_end_support"],
    )
    assert grouped["useful"]
    assert not grouped["potentially_harmful"]
    assert not grouped["irrelevant"]
