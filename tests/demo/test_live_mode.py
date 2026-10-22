import hashlib
import json
import subprocess

import pytest

from demo.app.services import core_check
from demo.app.services import live_runner as lr
from demo.app.services import live_worker as lw

SANITISED = ">contig_1\n" + "ACGT" * 200 + "\n"


def test_missing_tools_disable_live_mode(monkeypatch):
    monkeypatch.setattr(lr.shutil, "which", lambda exe: None)
    rep = lr.detect_tools()
    assert not rep.live_ready
    assert set(rep.missing_required) == set(lr.REQUIRED_TOOLS)


def test_operator_can_disable_live_mode(monkeypatch):
    monkeypatch.setenv(lr.DISABLE_ENV, "1")
    assert lr.live_disabled_reason()
    monkeypatch.delenv(lr.DISABLE_ENV)
    assert lr.live_disabled_reason() is None


def test_agentic_endpoint_requires_http_url(monkeypatch):
    monkeypatch.delenv(lw.AGENTIC_URL_ENV, raising=False)
    assert lr.agentic_endpoint() is None
    monkeypatch.setenv(lw.AGENTIC_URL_ENV, "file:///etc/passwd")
    assert lr.agentic_endpoint() is None
    monkeypatch.setenv(lw.AGENTIC_URL_ENV, "http://model-host:11434/v1")
    assert lr.agentic_endpoint_host() == "model-host:11434"


def test_run_live_rejects_bad_requests_without_running_anything(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(lr.subprocess, "run", boom)
    monkeypatch.delenv(lw.AGENTIC_URL_ENV, raising=False)
    assert not lr.run_live(SANITISED, "lacZ", "GS_DETERMINISTIC_V4_1").ok
    assert not lr.run_live(SANITISED, "rpoB_RNAP_beta", "SOMETHING_ELSE").ok
    assert not lr.run_live(SANITISED, "rpoB_RNAP_beta", "GS_AGENTIC_V4_1").ok
    assert not lr.run_live(">user header\nACGT\n", "rpoB_RNAP_beta", "GS_DETERMINISTIC_V4_1").ok


def test_worker_is_invoked_with_argument_list_and_temp_files_removed(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        if "--out" not in cmd:
            return subprocess.CompletedProcess(cmd, 0, "tool 1.0", "")
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        out = cmd[cmd.index("--out") + 1]
        assembly = cmd[cmd.index("--assembly") + 1]
        seen["assembly_text"] = open(assembly, encoding="ascii").read()
        seen["out"] = out
        payload = {"ok": True, "arm": "GS_DETERMINISTIC_V4_1", "target": "rpoB_RNAP_beta", "record": {}}
        with open(f"{out}/result.json", "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(lr.subprocess, "run", fake_run)
    monkeypatch.setenv("SOME_API_KEY", "secret-value")
    res = lr.run_live(SANITISED, "rpoB_RNAP_beta", "GS_DETERMINISTIC_V4_1")
    assert res.ok
    assert isinstance(seen["cmd"], list)
    assert seen["kwargs"].get("shell") in (None, False)
    assert seen["cmd"][1:3] == ["-m", "demo.app.services.live_worker"]
    assert seen["assembly_text"] == SANITISED
    assert "SOME_API_KEY" not in seen["kwargs"]["env"]
    import os

    assert not os.path.exists(seen["out"])


def test_timeout_is_reported_without_traceback(monkeypatch):
    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(lr.subprocess, "run", slow)
    res = lr.run_live(SANITISED, "rpoB_RNAP_beta", "GS_DETERMINISTIC_V4_1", timeout=1)
    assert not res.ok
    assert "limit" in res.message
    assert "Traceback" not in res.message


def test_only_one_live_job_at_a_time():
    assert lr._job_lock.acquire(blocking=False)
    try:
        with pytest.raises(lr.LiveBusy):
            lr.run_live(SANITISED, "rpoB_RNAP_beta", "GS_DETERMINISTIC_V4_1")
    finally:
        lr._job_lock.release()


def test_worker_failure_returns_short_message(tmp_path, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError(f"tool failed in {tmp_path}/work")

    monkeypatch.setattr(lw, "run", broken)
    code = lw.main(["--assembly", "a.fna", "--target", "rpoB_RNAP_beta", "--arm", "GS_DETERMINISTIC_V4_1", "--out", str(tmp_path)])
    assert code == 1
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert str(tmp_path) not in result["error"]
    assert "Traceback" not in result["error"]


def test_scrub_removes_endpoints_keys_and_paths():
    obj = {
        "base_url": "http://10.0.0.1:11434/v1",
        "api_key": "x",
        "nested": [{"url": "http://h", "path": "/tmp/gs_live_abc/work/x.tsv", "keep": 1}],
    }
    out = lw.scrub(obj, "/tmp/gs_live_abc")
    assert "base_url" not in out and "api_key" not in out
    assert out["nested"][0] == {"path": "<work>/work/x.tsv", "keep": 1}


def test_core_check_treats_line_endings_as_equivalent(tmp_path):
    lf = b"line one\nline two\n"
    frozen = hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()
    p = tmp_path / "f.py"
    p.write_bytes(lf)
    assert core_check.file_matches(p, frozen)
    p.write_bytes(b"line one\nline 2\n")
    assert not core_check.file_matches(p, frozen)


def test_bundled_example_assemblies_pass_integrity_and_validation():
    from demo.app.utils import fasta

    exs = lr.example_assemblies()
    assert {e["accession"] for e in exs} == {"GCF_965183925.1", "GCF_051052775.1"}
    for e in exs:
        res = fasta.validate_assembly_fasta(lr.load_example_text(e["accession"]))
        assert res.ok, res.errors
