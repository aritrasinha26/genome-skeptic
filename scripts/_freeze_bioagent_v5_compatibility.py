#!/usr/bin/env python3
"""Freeze BioAgent Bench V5 compatibility from solver-visible metadata only."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from genome_skeptic.eval.external.bioagent_v5_select import classify_bioagent_task

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
BENCH = ROOT / "benchmarks" / "external" / "bioagent_bench"
META = BENCH / "src" / "task_metadata.json"
OUT = ROOT / "external_validation"
MANIFEST = OUT / "bioagent_v5_compatibility_manifest.json"
V5_FREEZE = ROOT / "v5_freeze_manifest.json"


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=BENCH, text=True).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_tasks = json.loads(META.read_text(encoding="utf-8"))
    classified = [classify_bioagent_task(t) for t in raw_tasks]
    n_sup = sum(1 for r in classified if r["compatibility"] == "SUPPORTED")
    n_part = sum(1 for r in classified if r["compatibility"] == "PARTIALLY_SUPPORTED")
    n_uns = sum(1 for r in classified if r["compatibility"] == "UNSUPPORTED")
    freeze_hash = json.loads(V5_FREEZE.read_text(encoding="utf-8"))["aggregate_sha256"]
    created = datetime.now(timezone.utc).isoformat()
    remote = git(["remote", "get-url", "origin"])
    commit = git(["rev-parse", "HEAD"])
    status = git(["status"])
    manifest = {
        "kind": "bioagent_v5_compatibility_manifest",
        "created_utc": created,
        "benchmark": "BioAgent Bench",
        "benchmark_repository": remote,
        "benchmark_commit": commit,
        "benchmark_git_status_clean": "nothing to commit, working tree clean" in status,
        "genome_skeptic_v5_freeze_hash": freeze_hash,
        "model": "qwen3:4b",
        "selection_before_answer_reference_inspection": True,
        "answers_inspected": False,
        "expected_outputs_inspected": False,
        "judge_outputs_inspected": False,
        "solution_scripts_inspected": False,
        "historical_trajectories_inspected": False,
        "result_scores_inspected": False,
        "tasks_executed": False,
        "tasks_scored": False,
        "internal_benchmark_run": False,
        "genome_skeptic_modified_for_compatibility": False,
        "tool_availability_alone_not_sufficient": True,
        "not_an_accuracy_score": True,
        "n_tasks_examined": len(classified),
        "n_supported": n_sup,
        "n_partially_supported": n_part,
        "n_unsupported": n_uns,
        "supported_task_ids": [r["task_id"] for r in classified if r["compatibility"] == "SUPPORTED"],
        "tasks": [
            {
                "task_id": r["task_id"],
                "name": r["name"],
                "category": r["name"],
                "original_prompt": r["task_prompt"],
                "description": r["description"],
                "input_artifact_filenames": r["input_artifact_filenames"],
                "reference_artifact_filenames": r["reference_artifact_filenames"],
                "required_deliverable": r["task_prompt"],
                "classification": r["compatibility"],
                "capability_rationale": r["capability_rationale"],
            }
            for r in classified
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    (OUT / "bioagent_v5_compatibility_manifest.sha256.json").write_text(
        json.dumps({"path": str(MANIFEST), "sha256": digest, "created_utc": created}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("N_EXAMINED", len(classified))
    print("N_SUPPORTED", n_sup)
    print("N_PARTIALLY_SUPPORTED", n_part)
    print("N_UNSUPPORTED", n_uns)
    print("SUPPORTED_IDS", json.dumps(manifest["supported_task_ids"]))
    print("SHA256", digest)


if __name__ == "__main__":
    main()
