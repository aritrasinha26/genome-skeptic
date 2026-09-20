from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.eval.freeze import build_freeze_manifest
from genome_skeptic.eval.stack import STACK_TOOLS, build_production_stack, inspect_tool


def test_manifest_does_not_mark_missing_tools_operational():
    row = inspect_tool("spades.py")
    if not row["available"]:
        assert row["operational"] is False
        assert row["available"] is False


def test_database_tools_are_not_operational_without_db(monkeypatch):
    monkeypatch.delenv("BAKTA_DB", raising=False)
    monkeypatch.delenv("CHECKM2DB", raising=False)
    monkeypatch.delenv("GENOME_SKEPTIC_TAXONOMY_DB", raising=False)
    payload = build_production_stack(settings=Settings(), smoke=None)
    names = {t["name"] for t in payload["tools"]}
    assert set(STACK_TOOLS) <= names
    for t in payload["tools"]:
        assert t["operational"] is False
        if t["database_required"]:
            assert t.get("database_present") in {False, None} or t["database_path"]


def test_executable_is_not_operational_without_passing_smoke():
    row = inspect_tool("fastp", smoke={"fastp": {"ok": False, "ran": True, "error": "forced failure"}})
    assert row["operational"] is False


def test_production_simulator_is_required_when_requested():
    from genome_skeptic.eval.simulate import simulate_paired_reads
    from genome_skeptic.tools.base import available
    import pytest
    if available("wgsim"):
        return
    with pytest.raises(RuntimeError, match="wgsim is required"):
        simulate_paired_reads(Path("missing.fa"), Path("out"), require_production_simulator=True)


def test_freeze_manifest_has_hashes():
    payload = build_freeze_manifest(Settings())
    assert payload["sha256"]
    assert payload["component_hashes"]["thresholds"]
    assert "development" in payload["catalog_genome_ids"]
    assert "held_out" in payload["catalog_genome_ids"]
