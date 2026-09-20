#!/usr/bin/env python3
"""Download official BixBench.jsonl and emit answer-blind task metadata.

Never writes hypothesis, result, answer, ideal_answer, distractors,
explanation, or other ground-truth fields.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

FORBIDDEN_KEYS = {
    "hypothesis",
    "result",
    "answer",
    "ideal",
    "ideal_answer",
    "target",
    "correct",
    "correct_letter",
    "distractor",
    "distractor_1",
    "distractor_2",
    "distractor_3",
    "distractors",
    "explanation",
    "solution",
    "reference",
    "notebook_output",
    "grader",
    "grade",
    "ground_truth",
    "groundtruth",
    "choices",
    "mcq_options",
    "options",
}

ALLOWED_TOP = {
    "uuid",
    "short_id",
    "categories",
    "paper",
    "dataset_folder",
    "data_folder",
    "capsule_uuid",
    "question_id",
    "id",
    "question",
    "questions",
    "question_format",
    "eval_mode",
    "evaluation_mode",
    "mode",
    "development",
    "tags",
    "category",
}


def strip_forbidden(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in FORBIDDEN_KEYS or any(tok in lk for tok in ("ideal", "distractor", "ground_truth", "grader")):
                continue
            if k in ALLOWED_TOP or k.lower() in {
                "uuid",
                "short_id",
                "categories",
                "paper",
                "dataset_folder",
                "data_folder",
                "capsule_uuid",
                "question_id",
                "id",
                "question",
                "questions",
                "question_format",
                "eval_mode",
                "evaluation_mode",
                "mode",
                "development",
                "tags",
                "category",
            }:
                out[k] = strip_forbidden(v)
        return out
    if isinstance(obj, list):
        return [strip_forbidden(x) for x in obj]
    return obj


def flatten_tasks(row: dict) -> list[dict]:
    tasks = []
    capsule = row.get("uuid") or row.get("capsule_uuid")
    categories = row.get("categories") or row.get("tags") or row.get("category") or []
    if isinstance(categories, str):
        categories = [categories]
    dataset_folder = row.get("dataset_folder") or row.get("data_folder")
    paper = row.get("paper")
    short_id = row.get("short_id")
    nested = row.get("questions")
    if isinstance(nested, list) and nested:
        for q in nested:
            if not isinstance(q, dict):
                continue
            qid = q.get("id") or q.get("question_id")
            tasks.append(
                {
                    "question_id": qid,
                    "question": q.get("question"),
                    "capsule_uuid": capsule,
                    "short_id": short_id,
                    "categories": categories,
                    "paper": paper,
                    "dataset_folder": dataset_folder or q.get("dataset_folder"),
                    "development": q.get("development"),
                    "question_format": q.get("question_format") or row.get("question_format"),
                    "evaluation_mode": q.get("eval_mode") or q.get("evaluation_mode") or row.get("eval_mode") or row.get("mode"),
                    "tag": q.get("tag") or row.get("tag"),
                    "version": row.get("version"),
                }
            )
        return tasks
    qid = row.get("question_id") or row.get("id")
    if row.get("question") or qid:
        tasks.append(
            {
                "question_id": qid,
                "question": row.get("question"),
                "capsule_uuid": capsule,
                "short_id": short_id,
                "categories": categories,
                "paper": paper,
                "dataset_folder": dataset_folder,
                "development": row.get("development"),
                "question_format": row.get("question_format"),
                "evaluation_mode": row.get("eval_mode") or row.get("evaluation_mode") or row.get("mode"),
                "tag": row.get("tag"),
                "version": row.get("version"),
            }
        )
    return tasks


def main() -> None:
    dest = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/external_validation")
    dest.mkdir(parents=True, exist_ok=True)
    raw_path = dest / "BixBench.jsonl"
    url = "https://huggingface.co/datasets/futurehouse/BixBench/resolve/main/BixBench.jsonl"
    if not raw_path.exists():
        print(f"DOWNLOAD {url}", flush=True)
        urllib.request.urlretrieve(url, raw_path)
    print(f"BYTES {raw_path.stat().st_size}", flush=True)
    keys = set()
    n_raw = 0
    tasks = []
    with raw_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n_raw += 1
            blob = json.loads(line)
            keys.update(blob.keys())
            safe = strip_forbidden(blob)
            tasks.extend(flatten_tasks(safe))
    meta = dest / "bixbench_v5_task_metadata_answerblind.jsonl"
    with meta.open("w", encoding="utf-8") as out:
        for t in tasks:
            out.write(json.dumps(t, ensure_ascii=False) + "\n")
    summary = {
        "n_source_rows": n_raw,
        "n_tasks": len(tasks),
        "source_keys": sorted(keys),
        "sanitized_path": str(meta),
        "forbidden_fields_written": False,
        "answers_inspected": False,
    }
    (dest / "bixbench_v5_metadata_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
