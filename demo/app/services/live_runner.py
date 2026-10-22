"""Live analysis controller: tool detection, limits, and subprocess execution.

Live mode is offered only when the external sequence-search programs that the
frozen pipeline calls are installed. It never falls back to a precomputed
result and never substitutes a different tool or model.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from demo.app.services.live_worker import AGENTIC_URL_ENV, ARMS, SUPPORTED_TARGETS

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "demo" / "fixtures"

REQUIRED_TOOLS = ("blastn", "tblastn", "makeblastdb", "hmmbuild", "hmmsearch")
OPTIONAL_TOOLS = ("mmseqs", "diamond")
VERSION_ARGS = {
    "blastn": ["-version"],
    "tblastn": ["-version"],
    "makeblastdb": ["-version"],
    "hmmbuild": ["-h"],
    "hmmsearch": ["-h"],
    "mmseqs": ["version"],
    "diamond": ["version"],
}
TIMEOUT_SECONDS = {
    "GS_DETERMINISTIC_V4_1": int(os.environ.get("GS_DEMO_TIMEOUT_DET", "300")),
    "GS_EXHAUSTIVE_V4_1": int(os.environ.get("GS_DEMO_TIMEOUT_EXH", "420")),
    "GS_AGENTIC_V4_1": int(os.environ.get("GS_DEMO_TIMEOUT_AGENTIC", "900")),
}
DISABLE_ENV = "GS_DEMO_DISABLE_LIVE"

_job_lock = threading.Semaphore(1)


@dataclass
class ToolReport:
    available: dict[str, str | None] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)

    @property
    def live_ready(self) -> bool:
        return not self.missing_required


def _version(exe: str) -> str | None:
    path = shutil.which(exe)
    if not path:
        return None
    try:
        proc = subprocess.run(
            [path, *VERSION_ARGS.get(exe, ["--version"])], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "installed (version not reported)"
    text = (proc.stdout or proc.stderr or "").strip().splitlines()
    for line in text:
        line = line.strip().lstrip("#").strip()
        if line and any(ch.isdigit() for ch in line):
            return line[:120]
    return "installed (version not reported)"


def detect_tools() -> ToolReport:
    rep = ToolReport()
    for exe in REQUIRED_TOOLS + OPTIONAL_TOOLS:
        rep.available[exe] = _version(exe)
    rep.missing_required = [t for t in REQUIRED_TOOLS if not rep.available.get(t)]
    rep.missing_optional = [t for t in OPTIONAL_TOOLS if not rep.available.get(t)]
    return rep


def live_disabled_reason() -> str | None:
    if os.environ.get(DISABLE_ENV, "").strip() in {"1", "true", "yes"}:
        return "Live analysis is disabled on this deployment by the operator."
    return None


def agentic_endpoint() -> str | None:
    url = os.environ.get(AGENTIC_URL_ENV, "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def agentic_endpoint_host() -> str | None:
    url = agentic_endpoint()
    return urlparse(url).netloc if url else None


def example_assemblies() -> list[dict[str, Any]]:
    path = FIXTURES / "SOURCES.json"
    if not path.is_file():
        return []
    return [e for e in json.loads(path.read_text(encoding="utf-8"))["examples"] if (FIXTURES / e["file"]).is_file()]


def load_example_text(accession: str) -> str:
    """Decompress a bundled example assembly and verify it against its recorded SHA256."""
    import gzip
    import hashlib

    entry = next((e for e in example_assemblies() if e["accession"] == accession), None)
    if entry is None:
        raise KeyError(accession)
    data = gzip.decompress((FIXTURES / entry["file"]).read_bytes())
    if hashlib.sha256(data).hexdigest() != entry["uncompressed_sha256"]:
        raise ValueError(f"example assembly {accession} failed its integrity check")
    return data.decode("ascii")


@dataclass
class LiveResult:
    ok: bool
    arm: str
    target: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class LiveBusy(RuntimeError):
    pass


def run_live(sanitized_fasta: str, target: str, arm: str, *, timeout: int | None = None) -> LiveResult:
    """Run one arm on a validated, header-sanitised assembly in a throwaway directory."""
    if target not in SUPPORTED_TARGETS:
        return LiveResult(False, arm, target, "Unsupported target.")
    if arm not in ARMS:
        return LiveResult(False, arm, target, "Unsupported analysis arm.")
    if arm == "GS_AGENTIC_V4_1" and not agentic_endpoint():
        return LiveResult(False, arm, target, "The agentic arm needs a configured model endpoint; none is configured.")
    if not sanitized_fasta.startswith(">contig_1"):
        return LiveResult(False, arm, target, "Assembly must be validated and sanitised before live analysis.")
    if not _job_lock.acquire(blocking=False):
        raise LiveBusy("Another live analysis is running on this server. Please try again shortly.")
    try:
        with tempfile.TemporaryDirectory(prefix="gs_live_") as tmp:
            tmpdir = Path(tmp)
            assembly = tmpdir / "assembly.fna"
            assembly.write_text(sanitized_fasta, encoding="ascii")
            env = {k: v for k, v in os.environ.items() if not k.upper().endswith(("_KEY", "_TOKEN", "_SECRET"))}
            env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), str(REPO_ROOT / "src")])
            if arm == "GS_AGENTIC_V4_1":
                env[AGENTIC_URL_ENV] = agentic_endpoint() or ""
            cmd = [
                sys.executable,
                "-m",
                "demo.app.services.live_worker",
                "--assembly",
                str(assembly),
                "--target",
                target,
                "--arm",
                arm,
                "--out",
                str(tmpdir),
            ]
            limit = timeout or TIMEOUT_SECONDS[arm]
            try:
                subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=limit, check=False)
            except subprocess.TimeoutExpired:
                return LiveResult(False, arm, target, f"Analysis exceeded the {limit} s limit and was stopped.")
            result_path = tmpdir / "result.json"
            if not result_path.exists():
                return LiveResult(False, arm, target, "The analysis process ended without producing a result.")
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["tool_versions"] = {k: v for k, v in detect_tools().available.items() if v}
    finally:
        _job_lock.release()
    if not payload.get("ok"):
        return LiveResult(False, arm, target, payload.get("error") or "The pipeline did not complete.", payload)
    return LiveResult(True, arm, target, "", payload)
