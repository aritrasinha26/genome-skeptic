#!/usr/bin/env python3
"""Freeze hashes onto the internal agentic gate manifest, then hash the manifest."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dev_work" / "agentic_gate" / "agentic_internal_gate_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    code = {
        "assembly_loop.py": sha256_file(ROOT / "src" / "genome_skeptic" / "agents" / "assembly_loop.py"),
        "qwen_agentic_dev.yaml": sha256_file(ROOT / "config" / "qwen_agentic_dev.yaml"),
        "run_agentic_internal_gate.py": sha256_file(ROOT / "scripts" / "run_agentic_internal_gate.py"),
    }
    payload["code_fingerprint"]["sha256"] = code
    payload["frozen_utc"] = datetime.now(timezone.utc).isoformat()
    for case in payload["cases"]:
        asm = ROOT / case["assembly"]
        tgt = ROOT / case["targets_source"]
        if not asm.exists():
            raise SystemExit(f"missing existing V5 assembly: {asm}")
        if not tgt.exists():
            raise SystemExit(f"missing existing V5 target FASTA: {tgt}")
        case["assembly_sha256"] = sha256_file(asm)
        case["targets_source_sha256"] = sha256_file(tgt)
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    digest = sha256_file(MANIFEST)
    lock = {
        "path": "dev_work/agentic_gate/agentic_internal_gate_manifest.json",
        "sha256": digest,
        "hashed_utc": datetime.now(timezone.utc).isoformat(),
        "hashed_before_execution": True,
    }
    (MANIFEST.parent / "agentic_internal_gate_manifest.sha256.json").write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )
    print(digest)


if __name__ == "__main__":
    main()
