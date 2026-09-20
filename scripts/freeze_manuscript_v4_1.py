#!/usr/bin/env python3
"""Freeze GENOME_SKEPTIC_V4_1_MANUSCRIPT after active tests and core equivalence.

Does not select M60 cases. Does not rerun D8/D12. Does not access D20 results.
"""
from __future__ import annotations

import hashlib
import json
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
OUT_DIR = ROOT / "manuscript_benchmark"
OUT_MD = OUT_DIR / f"{FREEZE_ID}.md"
OUT_MANIFEST = OUT_DIR / f"{FREEZE_ID}_manifest.json"
OUT_SHA = OUT_DIR / f"{FREEZE_ID}_manifest.sha256.json"
OUT_ENV = OUT_DIR / "environment_manifest.json"

SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", "mmseqs", "tmp"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def git_commit() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def tool_version(*names: str) -> dict:
    for name in names:
        path = shutil.which(name)
        if path:
            return {"name": name, "path": path, "version": executable_version(name), "available": True}
    return {"name": names[0], "path": None, "version": None, "available": False}


def freeze_paths() -> list[Path]:
    paths: list[Path] = []
    for pattern in (
        "src/genome_skeptic/**/*.py",
        "src/genome_skeptic/**/*.yaml",
        "src/genome_skeptic/**/*.faa",
        "data/target_families/**/*",
        "data/orthology_references/**/*",
        "tests/test_agentic_v4_1_dev.py",
        "tests/test_manuscript_v4_1.py",
        "manuscript_benchmark/TARGET_READINESS.md",
        "manuscript_benchmark/M60_PROTOCOL.md",
        "manuscript_benchmark/TEST_HYGIENE.md",
        "manuscript_benchmark/M60_EXCLUSION_MANIFEST.json",
        "scripts/build_m60_exclusion_manifest.py",
        "scripts/freeze_manuscript_v4_1.py",
    ):
        paths.extend(sorted(ROOT.glob(pattern)))
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def main() -> dict:
    created = datetime.now(timezone.utc).isoformat()
    core = scientific_core_hashes()
    files = [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in freeze_paths()]
    files.sort(key=lambda row: row["path"])
    protocol = ROOT / "manuscript_benchmark" / "M60_PROTOCOL.md"
    exclusion = ROOT / "manuscript_benchmark" / "M60_EXCLUSION_MANIFEST.json"
    environment = {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "blast": tool_version("blastn", "blastp"),
        "hmmer": tool_version("hmmsearch"),
        "mmseqs": tool_version("mmseqs"),
        "diamond": tool_version("diamond"),
    }
    OUT_ENV.write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
    payload = {
        "freeze_id": FREEZE_ID,
        "kind": "manuscript_system_freeze",
        "immutable": True,
        "created_utc": created,
        "git_commit": git_commit(),
        "development_closed": True,
        "m60_cases_selected": False,
        "d8_rerun": False,
        "d12_rerun": False,
        "d20_touched": False,
        "external_truth_accessed": False,
        "biological_thresholds_changed": False,
        "primary_targets": ["tetA_tetracycline_efflux", "rpoB_RNAP_beta"],
        "limitation_targets": ["tuf_EF_Tu", "lacZ_beta_galactosidase"],
        "arms": ["GS_DETERMINISTIC_V4_1", "GS_AGENTIC_V4_1", "GS_EXHAUSTIVE_V4_1"],
        "scientific_core": core,
        "environment": environment,
        "environment_manifest_sha256": sha256_file(OUT_ENV),
        "m60_protocol_sha256": sha256_file(protocol) if protocol.is_file() else None,
        "exclusion_manifest_sha256": sha256_file(exclusion) if exclusion.is_file() else None,
        "action_registry_hash": core["action_registry_hash"],
        "validator_config_hash": core["validator_hash"],
        "planner_prompt_hash": core["planner_prompt_hash"],
        "critic_prompt_hash": core["critic_prompt_hash"],
        "reference_family_asset_hash": core["family_definitions_hash"],
        "ortholog_reference_asset_hash": core["reference_assets_hash"],
        "n_files": len(files),
        "files": files,
    }
    OUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OUT_MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    digest = sha256_file(OUT_MANIFEST)
    sidecar = {
        "path": OUT_MANIFEST.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "hashed_utc": datetime.now(timezone.utc).isoformat(),
        "freeze_id": FREEZE_ID,
        "immutable": True,
        "m60_cases_selected": False,
        "d20_touched": False,
    }
    OUT_SHA.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# {FREEZE_ID}",
        "",
        "Manuscript freeze of Genome Skeptic V4.1 after development close.",
        "Three arms share one scientific core. Follow-up policy is the only intended difference.",
        "M60 cases were not selected. D8/D12 were not rerun. D20 was not accessed.",
        "",
        f"- freeze name = {FREEZE_ID}",
        f"- git commit = `{payload['git_commit']}`",
        f"- freeze-manifest SHA256 = `{digest}`",
        f"- scientific-core hash = `{core['scientific_core_hash']}`",
        f"- M60 protocol SHA256 = `{payload['m60_protocol_sha256']}`",
        f"- exclusion-manifest SHA256 = `{payload['exclusion_manifest_sha256']}`",
        f"- action-registry hash = `{core['action_registry_hash']}`",
        f"- validator-config hash = `{core['validator_hash']}`",
        f"- Planner prompt hash = `{core['planner_prompt_hash']}`",
        f"- Critic prompt hash = `{core['critic_prompt_hash']}`",
        f"- Python = `{sys.version.split()[0]}`",
        f"- BLAST+ = `{environment['blast'].get('version')}`",
        f"- HMMER = `{environment['hmmer'].get('version')}`",
        f"- MMseqs = `{environment['mmseqs'].get('version')}`",
        f"- DIAMOND = `{environment['diamond'].get('version')}`",
        "- M60 CASES SELECTED = NO",
        "- D20 TOUCHED = NO",
        "",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"FREEZE {FREEZE_ID}")
    print(f"MANIFEST {OUT_MANIFEST}")
    print(f"SHA256 {digest}")
    return {"freeze_id": FREEZE_ID, "sha256": digest, "n_files": len(files)}


if __name__ == "__main__":
    main()
