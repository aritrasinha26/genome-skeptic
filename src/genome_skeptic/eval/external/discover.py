"""Discover and classify official local benchmark assets.

Tasks are never reconstructed from paper descriptions.
"""
from __future__ import annotations

import json
from pathlib import Path

from genome_skeptic.eval.external.compat import classify_task

OFFICIAL_KINDS = ("bioagent_bench", "promptbio_bench", "bixbench")


def _local_tasks(root: Path) -> list[dict]:
    rows = []
    seen = set()
    patterns = ("**/task.json", "**/*task*.json", "**/*benchmark*.json", "**/*.ipynb")
    files = []
    for pat in patterns:
        files.extend(root.glob(pat))
    for path in files:
        if path in seen:
            continue
        seen.add(path)
        prompt = ""
        name = path.stem
        tags: list[str] = []
        if path.suffix == ".json":
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(blob, dict):
                    name = str(blob.get("id") or blob.get("task_id") or blob.get("name") or name)
                    prompt = str(blob.get("prompt") or blob.get("question") or blob.get("instruction") or blob.get("description") or "")
                    tags = list(blob.get("tags") or blob.get("categories") or [])
                elif isinstance(blob, list):
                    for i, item in enumerate(blob[:200]):
                        if not isinstance(item, dict):
                            continue
                        rows.append({
                            "id": str(item.get("id") or item.get("task_id") or f"{path.stem}_{i}"),
                            "prompt": str(item.get("prompt") or item.get("question") or item.get("instruction") or ""),
                            "tags": list(item.get("tags") or []),
                            "local_path": str(path.parent),
                        })
                    continue
            except Exception:
                pass
        elif path.suffix == ".ipynb":
            prompt = path.stem.replace("_", " ")
            tags = ["notebook"]
        rows.append({"id": str(name), "prompt": prompt, "tags": tags, "local_path": str(path.parent)})
    return rows


def discover_benchmark(kind: str, search_roots: list[Path]) -> dict:
    local_root = None
    for root in search_roots:
        for cand in (root / kind.replace("_", "-"), root / kind, root / "benchmarks" / "external" / kind):
            if cand.exists():
                local_root = cand
                break
        if local_root:
            break
    if local_root is None:
        return {
            "benchmark": kind,
            "local_root": None,
            "source": "official_assets_unavailable",
            "n_tasks": 0,
            "n_supported": 0,
            "n_partial": 0,
            "n_unsupported": 0,
            "tasks": [],
            "note": "Official repository was not present locally. Tasks were not reconstructed from paper descriptions and were not scored.",
        }
    tasks = _local_tasks(local_root)
    classified = []
    for task in tasks:
        row = classify_task(str(task.get("id")), task.get("prompt") or "", task.get("tags") or [])
        row["local_path"] = task.get("local_path")
        row["original_prompt"] = task.get("prompt")
        row["inputs_present"] = bool(task.get("local_path"))
        classified.append(row)
    return {
        "benchmark": kind,
        "local_root": str(local_root),
        "source": "official_clone",
        "n_tasks": len(classified),
        "n_supported": sum(1 for r in classified if r["compatibility"] == "supported"),
        "n_partial": sum(1 for r in classified if r["compatibility"] == "partially_supported"),
        "n_unsupported": sum(1 for r in classified if r["compatibility"] == "unsupported"),
        "tasks": classified,
        "note": "Only files present in the official clone were classified. Prompts were not rewritten. Missing inputs were not fabricated.",
    }


def discover_all(root: Path) -> dict:
    benches = {k: discover_benchmark(k, [root, root / "benchmarks" / "external", Path.home()]) for k in OFFICIAL_KINDS}
    return {
        "kind": "external_benchmark_manifest",
        "benchmarks": benches,
        "scoring_rule": "only_supported_tasks_with_local_original_inputs_and_original_scorer",
        "truth_labels_modified": False,
        "tasks_reconstructed_from_papers": False,
    }
