#!/usr/bin/env python3
"""Freeze BixBench V5 task selection from answer-blind metadata only."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from genome_skeptic.eval.external.bixbench_v5_select import (
    classify_bixbench_task,
    load_answerblind,
    select_supported,
)

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
OUT = ROOT / "external_validation"
META = OUT / "bixbench_v5_task_metadata_answerblind.jsonl"
MANIFEST = OUT / "bixbench_v5_task_manifest.json"
CLASSIFICATION = OUT / "bixbench_v5_task_classification.json"
RAW_JSONL = OUT / "BixBench.jsonl"
V5_FREEZE = ROOT / "v5_freeze_manifest.json"
BIX = ROOT / "benchmarks" / "external" / "bixbench"


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=BIX, text=True).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = load_answerblind(META)
    classified = [classify_bixbench_task(t) for t in tasks]
    selected = select_supported(classified, limit=5)
    n_sup = sum(1 for r in classified if r["compatibility"] == "SUPPORTED")
    n_part = sum(1 for r in classified if r["compatibility"] == "PARTIALLY_SUPPORTED")
    n_uns = sum(1 for r in classified if r["compatibility"] == "UNSUPPORTED")
    freeze_hash = json.loads(V5_FREEZE.read_text(encoding="utf-8"))["aggregate_sha256"]
    created = datetime.now(timezone.utc).isoformat()
    classification_payload = {
        "kind": "bixbench_v5_task_classification",
        "created_utc": created,
        "answers_inspected": False,
        "n_tasks": len(classified),
        "n_supported": n_sup,
        "n_partially_supported": n_part,
        "n_unsupported": n_uns,
        "tasks": classified,
    }
    CLASSIFICATION.write_text(json.dumps(classification_payload, indent=2), encoding="utf-8")
    manifest = {
        "kind": "bixbench_v5_task_manifest",
        "created_utc": created,
        "benchmark": "BixBench",
        "benchmark_repository": "https://github.com/Future-House/BixBench.git",
        "benchmark_commit": git(["rev-parse", "HEAD"]),
        "benchmark_git_status_clean": "nothing to commit, working tree clean" in git(["status"]),
        "task_metadata_source": "https://huggingface.co/datasets/futurehouse/BixBench/resolve/main/BixBench.jsonl",
        "genome_skeptic_v5_freeze_hash": freeze_hash,
        "model": "qwen3:4b",
        "selection_performed_without_access_to_answers": True,
        "answers_inspected": False,
        "ideal_answers_inspected": False,
        "capsules_downloaded": False,
        "capsules_executed": False,
        "scored": False,
        "internal_benchmark_run": False,
        "genome_skeptic_modified_for_compatibility": False,
        "prefer_deterministic_verifiers": True,
        "max_supported_selected": 5,
        "n_official_tasks": len(classified),
        "n_supported": n_sup,
        "n_partially_supported": n_part,
        "n_unsupported": n_uns,
        "task_ids": [r["question_id"] for r in selected],
        "selected_tasks": [
            {
                "question_id": r["question_id"],
                "capsule_uuid": r["capsule_uuid"],
                "original_task_category": r["categories"],
                "evaluation_mode": r["evaluation_mode"],
                "compatibility": r["compatibility"],
                "compatibility_rationale": r["compatibility_rationale"],
            }
            for r in selected
        ],
        "selection_rule": (
            "At most 5 SUPPORTED original BixBench tasks that frozen Genome Skeptic V5 "
            "can address without adding scientific functionality. Deterministic "
            "str_verifier/range_verifier preferred over llm_verifier. PARTIALLY_SUPPORTED "
            "and UNSUPPORTED tasks are not selected."
        ),
    }
    text = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    MANIFEST.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    sidecar = {"path": str(MANIFEST), "sha256": digest, "created_utc": created}
    (OUT / "bixbench_v5_task_manifest.sha256.json").write_text(
        json.dumps(sidecar, indent=2) + "\n", encoding="utf-8"
    )
    if RAW_JSONL.exists():
        RAW_JSONL.unlink()
    print("SELECTED_TASK_IDS", json.dumps(manifest["task_ids"]))
    print("N_SUPPORTED", n_sup)
    print("N_PARTIALLY_SUPPORTED", n_part)
    print("N_UNSUPPORTED", n_uns)
    print("MANIFEST", MANIFEST)
    print("SHA256", digest)
    print(json.dumps(manifest["selected_tasks"], indent=2))


if __name__ == "__main__":
    main()
