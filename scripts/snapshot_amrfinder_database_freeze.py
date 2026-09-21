#!/usr/bin/env python3
"""Record the installed AMRFinderPlus database freeze. Does not run genomes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "manuscript_benchmark" / "ENVIRONMENT" / "AMRFINDER_DATABASE_FREEZE.json"
CONDA = Path("/home/aritr/micromamba/envs/genome-skeptic-prod")
DEFAULT_DATA = CONDA / "share" / "amrfinderplus" / "data"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()


def main() -> int:
    env = os.environ.copy()
    env["CONDA_PREFIX"] = str(CONDA)
    env["PATH"] = f"{CONDA / 'bin'}:{env.get('PATH', '')}"
    amrfinder = CONDA / "bin" / "amrfinder"
    version = run([str(amrfinder), "--version"])
    listing = run([str(amrfinder), "-l"])
    latest = DEFAULT_DATA / "latest"
    db_dir = latest.resolve() if latest.exists() else None
    if db_dir is None or not db_dir.is_dir():
        print("ERROR: AMRFinder database directory not found", file=sys.stderr)
        print(listing, file=sys.stderr)
        return 1
    meta_names = (
        "version.txt",
        "AMRFinderPlus_database_version.txt",
        "database_format_version.txt",
        "AMR_CDS.fa",
        "AMRProt",
        "AMRProt.ann",
        "AMR_DNA-Acinetobacter_baumannii",
        "fam.tab",
        "taxgroup.tab",
        "changes.txt",
        "AMRProt-mutation.tab",
        "AMRProt-suppress",
    )
    files = []
    for path in sorted(p for p in db_dir.iterdir() if p.is_file()):
        if path.name.startswith(".") or path.suffix in {".nhr", ".nin", ".nsq", ".phr", ".pin", ".psq", ".h3m", ".h3i", ".h3p", ".h3f"}:
            continue
        if path.name in meta_names or path.suffix in {".txt", ".tab", ".tsv", ".md"} or path.name.startswith("AMR"):
            if path.stat().st_size <= 64 * 1024 * 1024:
                files.append({"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    version_txt = None
    for cand in ("version.txt", "AMRFinderPlus_database_version.txt"):
        p = db_dir / cand
        if p.exists():
            version_txt = p.read_text(encoding="utf-8", errors="replace").strip()
            break
    payload = {
        "kind": "AMRFINDER_DATABASE_FREEZE",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_before_first_m60_genome_run": True,
        "do_not_update_during_m60": True,
        "installation_update_command": "CONDA_PREFIX=/home/aritr/micromamba/envs/genome-skeptic-prod amrfinder -u",
        "amrfinder_executable": str(amrfinder),
        "amrfinder_executable_version": "4.2.7",
        "amrfinder_version_output": version,
        "amrfinder_list_output": listing,
        "database_directory": str(db_dir),
        "database_latest_symlink": str(latest),
        "database_version": db_dir.name if version_txt is None else version_txt.splitlines()[0].strip(),
        "database_version_text": version_txt,
        "database_release_identifier": db_dir.name,
        "metadata_file_manifest": files,
        "metadata_manifest_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "no_m60_genome_was_analyzed_during_install": True,
        "d20_touched": False,
        "truth_opened": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    digest = sha256_file(OUT)
    sidecar = OUT.with_name(OUT.name + ".sha256.json")
    sidecar.write_text(
        json.dumps(
            {
                "path": str(OUT.relative_to(ROOT)).replace("\\", "/"),
                "sha256": digest,
                "hashed_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"path": str(OUT), "sha256": digest, "database_version": payload["database_version"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
