#!/usr/bin/env python3
"""Phase B: M60 execution-environment preflight in the intended Linux host.

Does not select genomes. Does not run manuscript prediction arms. Does not
open truth or D20 results. Does not modify scientific source.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.manuscript.scientific_core import scientific_core_hashes  # noqa: E402
from genome_skeptic.provenance import executable_version  # noqa: E402

FREEZE_ID = "GENOME_SKEPTIC_V4_1_MANUSCRIPT"
EXPECTED_MANIFEST = "97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b"
EXPECTED_CORE = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"
EXPECTED_PROTOCOL = "30de5efc92d1b2b0db9de0db6f8f98b965397b6adac17052603b3ab44b74df4f"
EXPECTED_EXCLUSION = "7fe225d0bc779e8b887a3f7980141272f85f3cc8c58c309f99118ff91fe4ef55"

OUT = ROOT / "manuscript_benchmark" / "M60_ENVIRONMENT.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Path) -> dict:
    files = []
    if root.exists():
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if any(part in {"__pycache__", ".pytest_cache", "mmseqs", "tmp"} for part in path.parts):
                continue
            files.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"root": str(root), "n_files": len(files), "sha256": digest, "files": files}


def _raw_version(path: str, args: list[str]) -> str | None:
    try:
        proc = subprocess.run([path, *args], capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    if lines[0].upper() in {"USAGE", "USAGE:"} or lines[0].lower().startswith("usage:"):
        return None
    return " | ".join(lines[:3])


def tool(name: str, *alts: str) -> dict:
    for cand in (name, *alts):
        path = shutil.which(cand)
        if not path:
            continue
        version = None
        if cand in {"blastn", "blastp", "blastx", "tblastn"}:
            version = _raw_version(path, ["-version"])
        if not version:
            try:
                version = executable_version(cand)
            except Exception:
                version = None
        if not version or str(version).strip().upper() in {"USAGE", "USAGE:"}:
            for args in (["-version"], ["--version"], ["version"], ["-v"]):
                version = _raw_version(path, args)
                if version:
                    break
        return {"name": cand, "path": path, "version": version, "available": True}
    return {"name": name, "path": None, "version": None, "available": False}


def cmd_text(args: list[str]) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return ((proc.stdout or "") + (proc.stderr or "")).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def pip_freeze() -> list[str]:
    try:
        proc = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, timeout=60)
        return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    except Exception:
        return []


def meminfo() -> dict:
    info: dict[str, str] = {}
    path = Path("/proc/meminfo")
    if path.exists():
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith(("MemTotal:", "MemFree:", "MemAvailable:", "SwapTotal:", "SwapFree:")):
                key, val = ln.split(":", 1)
                info[key] = val.strip()
    return info


def cpuinfo() -> dict:
    out = {"nproc": os.cpu_count(), "model": None, "lscpu": None}
    cpu = Path("/proc/cpuinfo")
    if cpu.exists():
        for ln in cpu.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.lower().startswith("model name"):
                out["model"] = ln.split(":", 1)[1].strip()
                break
    if shutil.which("lscpu"):
        out["lscpu"] = cmd_text(["lscpu"])
    return out


def verify_freeze() -> dict:
    manifest_path = ROOT / "manuscript_benchmark" / f"{FREEZE_ID}_manifest.json"
    protocol = ROOT / "manuscript_benchmark" / "M60_PROTOCOL.md"
    exclusion = ROOT / "manuscript_benchmark" / "M60_EXCLUSION_MANIFEST.json"
    manifest_sha = sha256_file(manifest_path)
    protocol_sha = sha256_file(protocol)
    exclusion_sha = sha256_file(exclusion)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    file_mismatches = []
    for row in payload.get("files") or []:
        path = ROOT / row["path"]
        if not path.is_file():
            file_mismatches.append({"path": row["path"], "error": "missing"})
            continue
        got = sha256_file(path)
        if got != row["sha256"]:
            file_mismatches.append({"path": row["path"], "expected": row["sha256"], "got": got})
    core = scientific_core_hashes()
    core_ok = core["scientific_core_hash"] == EXPECTED_CORE
    return {
        "manifest_sha256": manifest_sha,
        "manifest_sha256_ok": manifest_sha == EXPECTED_MANIFEST,
        "scientific_core_hash": core["scientific_core_hash"],
        "scientific_core_hash_ok": core_ok,
        "protocol_sha256": protocol_sha,
        "protocol_sha256_ok": protocol_sha == EXPECTED_PROTOCOL,
        "exclusion_sha256": exclusion_sha,
        "exclusion_sha256_ok": exclusion_sha == EXPECTED_EXCLUSION,
        "n_file_mismatches": len(file_mismatches),
        "file_mismatches": file_mismatches[:50],
        "family_dir": core.get("family_dir"),
        "ortholog_dir": core.get("ortholog_dir"),
        "reference_assets_hash": core.get("reference_assets_hash"),
        "family_definitions_hash": core.get("family_definitions_hash"),
    }


def main() -> int:
    freeze = verify_freeze()
    family_src = ROOT / "src" / "genome_skeptic" / "data" / "target_families"
    family_data = ROOT / "data" / "target_families"
    ortholog = ROOT / "data" / "orthology_references"
    blast = tool("blastn", "blastp")
    hmmer = tool("hmmsearch", "hmmbuild")
    mmseqs = tool("mmseqs")
    diamond = tool("diamond")
    amrfinder = tool("amrfinder")
    required = {
        "HMMER available": "YES" if hmmer["available"] else "NO",
        "MMseqs available": "YES" if mmseqs["available"] else "NO",
        "DIAMOND available": "YES" if diamond["available"] else "NO",
        "BLAST+ available": "YES" if blast["available"] else "NO",
    }
    freeze_ok = (
        freeze["manifest_sha256_ok"]
        and freeze["scientific_core_hash_ok"]
        and freeze["protocol_sha256_ok"]
        and freeze["exclusion_sha256_ok"]
        and freeze["n_file_mismatches"] == 0
    )
    tools_ok = all(v == "YES" for v in required.values())
    ready = freeze_ok and tools_ok and sys.platform.startswith("linux")
    payload = {
        "kind": "M60_ENVIRONMENT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "intended_host": "WSL/Linux production environment for M60",
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "os_kernel": platform.uname()._asdict(),
        "cpu": cpuinfo(),
        "meminfo": meminfo(),
        "swap": cmd_text(["swapon", "--show"]) if shutil.which("swapon") else None,
        "blast": blast,
        "hmmer": hmmer,
        "mmseqs": mmseqs,
        "diamond": diamond,
        "amrfinder": amrfinder,
        "amrfinder_databases": cmd_text(["amrfinder", "-l"]) if amrfinder["available"] else None,
        "emapper": tool("emapper.py"),
        "pip_freeze": pip_freeze(),
        "required_tools": required,
        "freeze_verification": freeze,
        "hashed_assets": {
            "src_target_families": sha256_tree(family_src),
            "data_target_families": sha256_tree(family_data),
            "orthology_references": sha256_tree(ortholog),
        },
        "manuscript_freeze_verified": freeze_ok,
        "production_environment_ready": ready,
        "d20_touched": False,
        "truth_opened": False,
        "predictions_run": False,
        "m60_cases_selected": False,
        "stop_if_not_ready": not ready,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {OUT}", flush=True)
    print(f"MANUSCRIPT_FREEZE_VERIFIED {'YES' if freeze_ok else 'NO'}", flush=True)
    print(f"PRODUCTION_ENVIRONMENT_READY {'YES' if ready else 'NO'}", flush=True)
    print(f"BLAST {blast.get('version')} PATH={blast.get('path')}", flush=True)
    print(f"HMMER {hmmer.get('version')} PATH={hmmer.get('path')}", flush=True)
    print(f"MMSEQS {mmseqs.get('version')} PATH={mmseqs.get('path')}", flush=True)
    print(f"DIAMOND {diamond.get('version')} PATH={diamond.get('path')}", flush=True)
    if not sys.platform.startswith("linux"):
        print("NOT_LINUX: M60 preflight must run in the WSL/Linux production host", flush=True)
        return 2
    if not ready:
        print("STOP: required tool missing or frozen asset hash differs", flush=True)
        if freeze["file_mismatches"]:
            print("mismatches:", json.dumps(freeze["file_mismatches"][:10], indent=2), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
