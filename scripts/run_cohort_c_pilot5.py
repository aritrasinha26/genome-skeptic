#!/usr/bin/env python3
"""Run the frozen 5-case Cohort C external pilot.

Does not modify GENOME_SKEPTIC_AGENTIC_V1, its 92-file freeze, model
settings, prompts, planner, critic, actions, validators, target
definitions, or the Cohort C 40-case manifest. Reuses immutable
case-level agentic results. Stops before label access.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.config import load_settings  # noqa: E402
from genome_skeptic.eval.evaluate_real import _run_system  # noqa: E402
from genome_skeptic.agents.providers import reset_call_log  # noqa: E402

SPEC = importlib.util.spec_from_file_location("run_cohort_c_agentic", ROOT / "scripts" / "run_cohort_c_agentic.py")
C40 = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(C40)

OUT = C40.OUT
RUNS = C40.RUNS
SOLVER = C40.SOLVER
TARGETS = C40.TARGETS
EMPTY_REFS = C40.EMPTY_REFS
PILOT = OUT / "cohort_C_pilot5_manifest.json"
PILOT_HASH = OUT / "cohort_C_pilot5_manifest.sha256.json"
FROZEN_TARGETS = C40.FROZEN_TARGETS
CONDITIONS = C40.CONDITIONS


def sha256_file(path: Path) -> str:
    return C40.sha256_file(path)


def require_real_agentic_path(row: dict) -> None:
    if row.get("silent_deterministic_fallback") is True:
        raise SystemExit(f"silent deterministic fallback: {row.get('assembly_accession')} {row.get('target')}")
    if row.get("agent_execution_failure") or row.get("ok") is False:
        return
    graph = [str(s) for s in (row.get("call_graph") or [])]
    needed = [
        ("deterministic evidence", any(s in graph for s in ("collect_assembly_target_measurements", "measurements_to_evidence", "run_gene_search"))),
        ("Qwen planner", row.get("planner_invoked") is True and any("AgentDecision" in s for s in graph)),
        ("registered action", row.get("action_registered") is True and row.get("action_executed") is True),
        ("new deterministic evidence", bool(row.get("new_evidence_ids"))),
        ("Qwen critic", row.get("critic_invoked") is True and any("CriticReview" in s for s in graph)),
        ("deterministic validator", row.get("final_validator_ran") is True),
    ]
    missing = [name for name, ok in needed if not ok]
    if missing:
        raise SystemExit(
            f"agentic path incomplete for {row.get('assembly_accession')} {row.get('target')}: missing {missing}"
        )


def run_deterministic_targets(
    acc: str,
    condition: str,
    sys_name: str,
    assembly: Path,
    settings,
    genus: str | None,
    targets: list[str],
) -> list[dict]:
    if targets == list(FROZEN_TARGETS):
        return C40.run_deterministic_condition(acc, condition, sys_name, assembly, settings, genus)
    rows = []
    for target in targets:
        dest = RUNS / acc / sys_name / target / "case_locked.json"
        if dest.exists() and dest.stat().st_size > 50:
            print(f"skip completed {condition} {acc} {target}", flush=True)
            rows.append(json.loads(dest.read_text(encoding="utf-8")))
            continue
        sys_dir = dest.parent
        sys_dir.mkdir(parents=True, exist_ok=True)
        one_target = sys_dir / f"{target}.fa"
        C40.write_one_target(one_target, target)
        print(f"{condition} START {acc} {target}", flush=True)
        reset_call_log()
        t0 = time.perf_counter()
        flags = {"enable_falsification": True} if sys_name == "genome_skeptic" else None
        try:
            payload = _run_system(
                sys_name,
                assembly,
                one_target,
                sys_dir,
                settings,
                EMPTY_REFS,
                genus,
                None,
                flags,
            )
            elapsed = time.perf_counter() - t0
            claims = payload.get("claims") or []
            loci = payload.get("loci") or []
            loc = None
            for le in loci:
                q = getattr(le, "query_id", None) or (le.get("query_id") if isinstance(le, dict) else None)
                if q == target:
                    loc = le.model_dump(mode="json") if hasattr(le, "model_dump") else le
                    break
            claim = None
            for c in claims:
                qid = c.claim_id.replace("C_target_", "")
                if qid == target:
                    claim = c
                    break
            if claim is None:
                raise RuntimeError(f"{condition} {acc} missing target {target}")
            fam = C40.load_family_blob(sys_dir, target)
            row = C40.prediction_row(acc, condition, target, claim, fam, loc, elapsed)
            row["ok"] = True
            row["model_call_count"] = 0
            row["repair_count"] = 0
            row["malformed_output_count"] = 0
            row["timeout_count"] = 0
            row["reused"] = bool(payload.get("reused"))
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            print(f"FAIL {condition} {acc} {target}: {exc}", flush=True)
            row = {
                "assembly_accession": acc,
                "condition": condition,
                "target": target,
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=8),
                "runtime_seconds": round(elapsed, 3),
                "external_labels_opened": False,
            }
        dest.write_text(json.dumps(row, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        print(f"{condition} DONE {acc} {target} ok={row.get('ok')} s={elapsed:.1f}", flush=True)
        rows.append(row)
    return rows


def lock_pilot(all_rows: list[dict], pilot: dict, started_utc: str, wall: float) -> None:
    jsonl = OUT / "cohort_C_pilot5_predictions_locked.jsonl"
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":"), default=str) for r in all_rows]
    jsonl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    pred_hash = sha256_file(jsonl)

    agentic = [r for r in all_rows if r.get("condition") == "GENOME_SKEPTIC_AGENTIC_V1"]
    v5 = [r for r in all_rows if r.get("condition") == "DETERMINISTIC_GENOME_SKEPTIC_V5"]
    conv = [r for r in all_rows if r.get("condition") == "FROZEN_CONVENTIONAL_BASELINE"]
    agentic_ok = [r for r in agentic if r.get("ok") and not r.get("agent_execution_failure")]
    agentic_fail = [r for r in agentic if r.get("agent_execution_failure") or r.get("ok") is False]
    actions = [r.get("requested_action") for r in agentic if r.get("requested_action")]
    case_runtimes = []
    for case in pilot["pilot_cases"]:
        acc = case["assembly_accession"]
        target = case["target"]
        per = {}
        for cond, bucket in (
            ("GENOME_SKEPTIC_AGENTIC_V1", agentic),
            ("DETERMINISTIC_GENOME_SKEPTIC_V5", v5),
            ("FROZEN_CONVENTIONAL_BASELINE", conv),
        ):
            hit = next((r for r in bucket if r.get("assembly_accession") == acc and r.get("target") == target), None)
            per[cond] = None if hit is None else hit.get("runtime_seconds")
        case_runtimes.append(
            {
                "frozen_execution_position": case["frozen_execution_position"],
                "assembly_accession": acc,
                "target": target,
                "runtime_seconds_by_condition": per,
                "agentic_runtime_seconds": per["GENOME_SKEPTIC_AGENTIC_V1"],
            }
        )
    exec_manifest = {
        "kind": "cohort_C_pilot5_execution_manifest",
        "locked_utc": datetime.now(timezone.utc).isoformat(),
        "started_utc": started_utc,
        "preliminary_external_pilot": True,
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V1",
        "agentic_v1_freeze_hash": C40.AGENTIC_FREEZE_SHA,
        "agentic_v1_freeze_summary_sha256": C40.AGENTIC_SUMMARY_SHA,
        "genome_skeptic_v5_freeze_hash": C40.V5_FREEZE,
        "cohort_manifest_sha256": json.loads((OUT / "cohort_C_manifest.sha256.json").read_text(encoding="utf-8"))["sha256"],
        "input_manifest_sha256": json.loads((OUT / "cohort_C_input_manifest.sha256.json").read_text(encoding="utf-8"))["sha256"],
        "pilot_manifest_sha256": json.loads(PILOT_HASH.read_text(encoding="utf-8"))["sha256"],
        "predictions_locked_sha256": pred_hash,
        "model": "qwen3:4b",
        "model_digest": C40.MODEL_DIGEST,
        "thinking": False,
        "temperature": 0,
        "structured_output": "Ollama native schema",
        "maximum_repairs": 1,
        "final_scientific_authority": "deterministic validator",
        "conditions": [c[0] for c in CONDITIONS],
        "n_pilot_genome_target_cases": 5,
        "n_predictions": len(all_rows),
        "pilot_cases": [
            {
                "frozen_execution_position": c["frozen_execution_position"],
                "assembly_accession": c["assembly_accession"],
                "target": c["target"],
            }
            for c in pilot["pilot_cases"]
        ],
        "predictions_per_condition": {
            "GENOME_SKEPTIC_AGENTIC_V1": len(agentic),
            "DETERMINISTIC_GENOME_SKEPTIC_V5": len(v5),
            "FROZEN_CONVENTIONAL_BASELINE": len(conv),
        },
        "successful_agentic_cases": len(agentic_ok),
        "agent_execution_failures": len(agentic_fail),
        "completed_cases": [
            {
                "frozen_execution_position": c["frozen_execution_position"],
                "assembly_accession": c["assembly_accession"],
                "target": c["target"],
                "agentic_ok": any(
                    r.get("assembly_accession") == c["assembly_accession"]
                    and r.get("target") == c["target"]
                    and r.get("ok")
                    and not r.get("agent_execution_failure")
                    for r in agentic
                ),
                "v5_ok": any(
                    r.get("assembly_accession") == c["assembly_accession"] and r.get("target") == c["target"] and r.get("ok")
                    for r in v5
                ),
                "conventional_ok": any(
                    r.get("assembly_accession") == c["assembly_accession"] and r.get("target") == c["target"] and r.get("ok")
                    for r in conv
                ),
                "reused_immutable_agentic": c.get("immutable_agentic_result_present"),
            }
            for c in pilot["pilot_cases"]
        ],
        "planner_calls": int(sum(int(r.get("planner_call_count") or 0) for r in agentic)),
        "critic_calls": int(sum(int(r.get("critic_call_count") or 0) for r in agentic)),
        "repair_calls": int(sum(int(r.get("repair_count") or 0) for r in agentic)),
        "timeouts": int(sum(int(r.get("timeout_count") or 0) for r in agentic)),
        "malformed_responses": int(sum(int(r.get("malformed_output_count") or 0) for r in agentic)),
        "distinct_registered_actions_selected": sorted({a for a in actions if a}),
        "action_frequency_table": dict(Counter(actions)),
        "runtime_per_case": case_runtimes,
        "total_runtime_seconds": wall,
        "external_labels_opened": False,
        "scores_computed": False,
        "adjudication_performed": False,
        "agent_modified": False,
        "silent_deterministic_fallback_used": False,
        "stop_before_label_access": True,
    }
    exec_path = OUT / "cohort_C_pilot5_execution_manifest.json"
    exec_path.write_text(json.dumps(exec_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    exec_hash = sha256_file(exec_path)
    (OUT / "cohort_C_pilot5_predictions_locked.sha256.json").write_text(
        json.dumps({"file": "cohort_C_pilot5_predictions_locked.jsonl", "sha256": pred_hash}, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "cohort_C_pilot5_execution_manifest.sha256.json").write_text(
        json.dumps({"file": "cohort_C_pilot5_execution_manifest.json", "sha256": exec_hash}, indent=2) + "\n",
        encoding="utf-8",
    )
    stamp = (
        "COHORT_C_PILOT5_PREDICTIONS_LOCKED\n"
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}\n"
        f"cohort_C_pilot5_predictions_locked.jsonl sha256: {pred_hash}\n"
        f"cohort_C_pilot5_manifest.json sha256: {exec_manifest['pilot_manifest_sha256']}\n"
        f"cohort_C_pilot5_execution_manifest.json sha256: {exec_hash}\n"
        "external_labels_opened: false\n"
        "do_not_unblind\n"
        "do_not_score\n"
        "do_not_adjudicate\n"
        "do_not_modify_predictions\n"
        "do_not_modify_agent\n"
    )
    (OUT / "COHORT_C_PILOT5_PREDICTIONS_LOCKED.txt").write_text(stamp, encoding="utf-8")
    print(
        json.dumps(
            {
                "pilot_manifest_sha256": exec_manifest["pilot_manifest_sha256"],
                "predictions_sha256": pred_hash,
                "execution_sha256": exec_hash,
                "completed_cases": exec_manifest["completed_cases"],
                "planner_calls": exec_manifest["planner_calls"],
                "critic_calls": exec_manifest["critic_calls"],
                "repairs": exec_manifest["repair_calls"],
                "actions": exec_manifest["action_frequency_table"],
                "runtime_per_case": case_runtimes,
                "total_runtime_seconds": wall,
                "external_labels_opened": False,
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    if not PILOT.exists() or not PILOT_HASH.exists():
        raise SystemExit("pilot5 manifest was not written/hashed before execution")
    lock = json.loads(PILOT_HASH.read_text(encoding="utf-8"))
    actual = sha256_file(PILOT)
    if actual != lock.get("sha256"):
        raise SystemExit(f"pilot5 manifest hash mismatch: {actual} != {lock.get('sha256')}")
    cohort_hash = json.loads((OUT / "cohort_C_manifest.sha256.json").read_text(encoding="utf-8"))["sha256"]
    if sha256_file(OUT / "cohort_C_manifest.json") != cohort_hash:
        raise SystemExit("cohort C manifest hash mismatch")
    input_hash = json.loads((OUT / "cohort_C_input_manifest.sha256.json").read_text(encoding="utf-8"))["sha256"]
    if sha256_file(OUT / "cohort_C_input_manifest.json") != input_hash:
        raise SystemExit("input manifest hash mismatch")

    pilot = json.loads(PILOT.read_text(encoding="utf-8"))
    cases = pilot["pilot_cases"]
    if [c["frozen_execution_position"] for c in cases] != [1, 2, 3, 4, 5]:
        raise SystemExit("pilot manifest is not frozen positions 1-5")
    started_utc = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    RUNS.mkdir(parents=True, exist_ok=True)
    C40.write_targets()
    agentic_settings = load_settings(ROOT / "config" / "qwen_agentic_dev.yaml")
    v5_settings = load_settings(ROOT / "config" / "qwen_external_v5.yaml")
    genomes = {g["assembly_accession"]: g for g in json.loads((OUT / "cohort_C_input_manifest.json").read_text(encoding="utf-8"))["genomes"]}

    agentic_rows = []
    for case in cases:
        acc = case["assembly_accession"]
        target = case["target"]
        genome = genomes[acc]
        assembly = SOLVER / f"{acc}.fna"
        if not assembly.exists():
            raise FileNotFoundError(assembly)
        try:
            row = C40.run_agentic_case(acc, target, assembly, agentic_settings, genome.get("genus"))
        except BaseException as exc:
            print(f"FATAL agentic {acc} {target}: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            raise
        if case.get("immutable_agentic_result_present"):
            row = dict(row)
            row["reused_immutable_case_result"] = True
        try:
            require_real_agentic_path(row)
        except SystemExit as exc:
            if case.get("immutable_agentic_result_present"):
                raise
            row = dict(row)
            row["ok"] = False
            row["agent_execution_failure"] = str(exc)
            dest = C40.agentic_case_path(acc, target)
            dest.write_text(json.dumps(row, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
            print(f"AGENTIC PATH FAIL {acc} {target}: {exc}", flush=True)
        agentic_rows.append(row)

    by_genome: dict[str, list[str]] = {}
    for case in cases:
        by_genome.setdefault(case["assembly_accession"], []).append(case["target"])

    det_rows: list[dict] = []
    for acc, targets in by_genome.items():
        genome = genomes[acc]
        assembly = SOLVER / f"{acc}.fna"
        genus = genome.get("genus")
        det_rows.extend(
            run_deterministic_targets(
                acc, "DETERMINISTIC_GENOME_SKEPTIC_V5", "genome_skeptic", assembly, v5_settings, genus, targets
            )
        )
        det_rows.extend(
            run_deterministic_targets(
                acc, "FROZEN_CONVENTIONAL_BASELINE", "conventional", assembly, v5_settings, genus, targets
            )
        )

    wanted = {(c["assembly_accession"], c["target"]) for c in cases}
    det_rows = [r for r in det_rows if (r.get("assembly_accession"), r.get("target")) in wanted]
    all_rows = []
    for case in cases:
        key = (case["assembly_accession"], case["target"])
        all_rows.extend([r for r in agentic_rows if (r.get("assembly_accession"), r.get("target")) == key])
    all_rows.extend(det_rows)
    if len(all_rows) != 15:
        raise SystemExit(f"expected 15 locked predictions, got {len(all_rows)}")
    lock_pilot(all_rows, pilot, started_utc, time.perf_counter() - t0)


if __name__ == "__main__":
    main()
