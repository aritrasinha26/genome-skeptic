from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


_VERSION_PROBES: dict[str, list[list[str]]] = {
    "mmseqs": [["mmseqs", "version"], ["mmseqs", "-h"]],
    "hmmsearch": [["hmmsearch", "-h"]],
    "hmmbuild": [["hmmbuild", "-h"]],
    "wgsim": [["wgsim"]],
    "FastTree": [["FastTree"]],
    "fasttree": [["fasttree"]],
    "quast.py": [["quast.py", "--version"]],
    "quast": [["quast", "--version"]],
    "diamond": [["diamond", "version"], ["diamond", "--version"]],
}


def _version_line(text: str) -> str | None:
    skip_prefixes = (
        "warning: python locale",
        "usage:",
        "invalid option",
        "unknown or incorrect",
        "failed to parse",
    )
    first = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith(skip_prefixes):
            continue
        if "locale settings" in line.lower():
            continue
        if line.startswith("#") and "HMMER" not in line.upper():
            continue
        if "HMMER" in line.upper() and any(ch.isdigit() for ch in line):
            return line.lstrip("# ").strip()[:300]
        first = first or line[:300]
    return first


def executable_version(exe: str) -> str | None:
    resolved = shutil.which(exe)
    if not resolved:
        return None
    probes = list(_VERSION_PROBES.get(Path(exe).name, []))
    probes.extend(([exe, "--version"], [exe, "-v"], [exe, "version"]))
    seen: set[tuple[str, ...]] = set()
    for cmd in probes:
        key = tuple(cmd)
        if key in seen:
            continue
        seen.add(key)
        try:
            p = subprocess.run(
                cmd, capture_output=True, text=True, timeout=8,
                stdin=subprocess.DEVNULL,
            )
        except Exception:
            continue
        line = _version_line((p.stdout or "") + "\n" + (p.stderr or ""))
        if line:
            return line
    return resolved


def write_manifest(out_dir: Path, payload: dict) -> Path:
    path = out_dir / "provenance.json"
    path.write_text(json.dumps(payload, indent=2))
    return path
