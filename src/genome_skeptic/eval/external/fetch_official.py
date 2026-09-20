"""Attempt to retrieve official public benchmark assets. Do not fabricate tasks."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


OFFICIAL = {
    "bioagent_bench": {
        "repo": "https://github.com/bioagent-bench/bioagent-bench.git",
        "license": "see upstream repository",
    },
    "promptbio_bench": {
        "repo": "https://github.com/PromptBio/promptbio-bench.git",
        "license": "see upstream repository",
        "data": "https://huggingface.co/datasets/promptbio-ai/promptbio-bench-data",
    },
    "bixbench": {
        "repo": "https://github.com/Future-House/BixBench.git",
        "license": "Apache-2.0",
        "data": "https://huggingface.co/datasets/futurehouse/BixBench",
    },
}


def _git_clone(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (dest / ".git").exists():
        try:
            commit = subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"], text=True, timeout=30).strip()
            return {"ok": True, "path": str(dest), "commit": commit, "cloned": False}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": str(dest)}
    try:
        subprocess.check_call(["git", "clone", "--depth", "1", url, str(dest)], timeout=180)
        commit = subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"], text=True, timeout=30).strip()
        return {"ok": True, "path": str(dest), "commit": commit, "cloned": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "repo": url}


def fetch_official_benchmarks(root: Path) -> dict:
    dest_root = root / "benchmarks" / "external"
    dest_root.mkdir(parents=True, exist_ok=True)
    benches = {}
    for name, spec in OFFICIAL.items():
        row = {
            "benchmark": name,
            "repository": spec["repo"],
            "license": spec.get("license"),
            "download_date": datetime.now(timezone.utc).date().isoformat(),
            "data_hint": spec.get("data"),
            "fabricated": False,
        }
        git = _git_clone(spec["repo"], dest_root / name)
        row.update(git)
        if git.get("ok"):
            n_tasks = 0
            local = Path(git["path"])
            for pat in ("**/task.json", "**/tasks/**", "**/*.ipynb"):
                n_tasks += len(list(local.glob(pat)))
            row["n_local_files_matched"] = n_tasks
        benches[name] = row
    return {
        "kind": "external_benchmark_sources",
        "benchmarks": benches,
        "note": "Only official repositories were contacted. Missing authentication or network access is reported, not filled with invented tasks.",
    }
