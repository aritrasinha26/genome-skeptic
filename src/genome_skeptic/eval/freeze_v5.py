"""Hash the frozen V5 scientific system. Do not change these files after external scoring."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _files(root: Path) -> list[Path]:
    out = []
    for rel in (
        "src/genome_skeptic",
        "config",
        "data/target_families",
    ):
        p = root / rel
        if p.is_file():
            out.append(p)
            continue
        if not p.exists():
            continue
        for f in p.rglob("*"):
            if f.is_file() and f.suffix in {".py", ".yaml", ".yml", ".json", ".faa", ".hmm", ".md"}:
                if "benchmarks" in f.parts:
                    continue
                out.append(f)
    for extra in (
        root / "calibration_v5.json",
        root / "config" / "fast_pilot.yaml",
    ):
        if extra.exists() and extra not in out:
            out.append(extra)
    return sorted(set(out))


def write_freeze_manifest(root: Path, dest: Path) -> dict:
    files = []
    h = hashlib.sha256()
    for path in _files(root):
        digest = _sha256(path)
        rel = str(path.relative_to(root)).replace("\\", "/")
        files.append({"path": rel, "sha256": digest})
        h.update(rel.encode())
        h.update(digest.encode())
    tools = {}
    for name in ("hmmsearch", "hmmbuild", "blastp", "blastn", "python"):
        try:
            tools[name] = subprocess.check_output([name, "-h"], stderr=subprocess.STDOUT, timeout=5, text=True)[:120]
        except Exception:
            try:
                tools[name] = subprocess.check_output([name, "-version"], stderr=subprocess.STDOUT, timeout=5, text=True)[:120]
            except Exception as exc:
                tools[name] = f"unavailable:{exc.__class__.__name__}"
    blob = {
        "kind": "v5_freeze_manifest",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "aggregate_sha256": h.hexdigest(),
        "n_files": len(files),
        "files": files,
        "tool_versions_recorded": tools,
        "note": "After this file is written, thresholds, prompts, calibration, and family references must not be changed in response to external answers. Later fixes belong to V5.1.",
    }
    dest.write_text(json.dumps(blob, indent=2), encoding="utf-8")
    return blob
