#!/usr/bin/env python3
"""Write immutable GENOME_SKEPTIC_AGENTIC_V3_EXTERNAL freeze + SHA256.

Call only after the production-readiness gate passes. Does not read D8 or D20.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FREEZE_ID = "GENOME_SKEPTIC_AGENTIC_V3_EXTERNAL"
OUT_MD = ROOT / "agentic_freeze" / f"{FREEZE_ID}.md"
OUT_MANIFEST = ROOT / "agentic_freeze" / f"{FREEZE_ID}_manifest.json"
OUT_SHA = ROOT / "agentic_freeze" / f"{FREEZE_ID}_manifest.sha256.json"
LACZ = ROOT / "agentic_freeze" / "CURRENT_LACZ_LIMITATION.md"

SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", "mmseqs", "tmp"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def freeze_paths() -> list[Path]:
    paths: list[Path] = []
    for pattern in (
        "src/genome_skeptic/**/*.py",
        "src/genome_skeptic/**/*.yaml",
        "src/genome_skeptic/**/*.faa",
        "config/qwen_agentic_dev.yaml",
        "tests/test_agentic_v3.py",
        "scripts/run_v3_production_readiness_gate.py",
        "scripts/run_v3_production_readiness_gate.sh",
        "scripts/freeze_agentic_v3_external.py",
        "agentic_freeze/CURRENT_LACZ_LIMITATION.md",
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


def main(gate_report: dict | None = None) -> dict:
    created = datetime.now(timezone.utc).isoformat()
    files = []
    for path in freeze_paths():
        rel = path.relative_to(ROOT).as_posix()
        files.append({"path": rel, "sha256": sha256_file(path)})
    files.sort(key=lambda row: row["path"])
    payload = {
        "freeze_id": FREEZE_ID,
        "kind": "agentic_implementation_freeze",
        "immutable": True,
        "created_utc": created,
        "system": "genome_skeptic_agentic_v3",
        "live_loop": "src/genome_skeptic/agents/assembly_loop_v3.py",
        "parent_agentic_v2": "GENOME_SKEPTIC_AGENTIC_V2_D20",
        "separate_from": [
            "frozen deterministic V5",
            "GENOME_SKEPTIC_AGENTIC_V1",
            "GENOME_SKEPTIC_AGENTIC_V2_D20",
        ],
        "d8_rerun": False,
        "d20_touched": False,
        "external_truth_accessed": False,
        "biological_thresholds_changed": False,
        "current_lacz_limitation": LACZ.read_text(encoding="utf-8") if LACZ.exists() else None,
        "environment": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        "gate": gate_report or {},
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
    }
    OUT_SHA.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# {FREEZE_ID}",
        "",
        "Immutable freeze of Agentic V3 after the production-readiness gate.",
        "Frozen V2, frozen V5, D8, and D20 were not modified.",
        "",
        f"- freeze name = {FREEZE_ID}",
        f"- live loop = `src/genome_skeptic/agents/assembly_loop_v3.py`",
        f"- frozen files = {len(files)}",
        f"- freeze-manifest SHA256 = `{digest}`",
        f"- created_utc = {created}",
        "- D8 rerun = NO",
        "- D20 touched = NO",
        "- external truth accessed = NO",
        "",
        "## CURRENT_LACZ_LIMITATION",
        "",
        "No frozen deterministic instrument currently distinguishes true LacZ",
        "orthology from relevant competing beta-galactosidase families when",
        "reference/GFF/orthology resources are absent.",
        "",
        "This limitation remains visible for the next benchmark.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"FREEZE {FREEZE_ID}", flush=True)
    print(f"MANIFEST {OUT_MANIFEST}", flush=True)
    print(f"SHA256 {digest}", flush=True)
    return {"freeze_id": FREEZE_ID, "manifest": str(OUT_MANIFEST), "sha256": digest, "n_files": len(files)}


if __name__ == "__main__":
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path else None
    main(report)
