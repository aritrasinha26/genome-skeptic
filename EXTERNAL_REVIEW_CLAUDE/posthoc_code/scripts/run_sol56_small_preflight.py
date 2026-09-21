#!/usr/bin/env python3
"""Four additional Sol cases, then lock a 5-case blinded model-behaviour preflight.

Reuses the real production GS_AGENTIC_V4_1 path. Does not rerun position 1.
Does not open truth or score accuracy. Does not change prompts or science.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from genome_skeptic.agents.action_catalog import ACTION_IDS  # noqa: E402
from genome_skeptic.agents.action_catalog_v4_1_dev import V41_EXTRA_ACTION_IDS  # noqa: E402
from genome_skeptic.agents.action_contract import CONTROL_DECISIONS  # noqa: E402
from genome_skeptic.agents.providers import (  # noqa: E402
    CALL_LOG,
    SOL_ABLATION_ID,
    SOL_MODEL,
    SOL_PROVIDER,
    SOL_REASONING_EFFORT,
    reset_call_log,
    sol_ablation_overlay,
)
from genome_skeptic.config import load_settings  # noqa: E402
from genome_skeptic.manuscript.arms import run_gs_agentic_v4_1  # noqa: E402
from genome_skeptic.manuscript.scientific_core import scientific_core_hashes  # noqa: E402
from run_sol56_one_case_preflight import (  # noqa: E402
    ABLATION_YAML,
    EXPECTED_CORE,
    EXPECTED_INVARIANT_HASHES,
    OUT_ROOT,
    load_case,
    manuscript_root,
    sol_confirmed,
    solver_fasta,
    write_target_fa,
)

NEW_POSITIONS = (2, 5, 6, 8)
ALL_POSITIONS = (1, 2, 5, 6, 8)
LOCK_DIR = ROOT / "manuscript_benchmark" / "SOL56_SMALL_PREFLIGHT"
REGISTERED = set(ACTION_IDS) | set(V41_EXTRA_ACTION_IDS) | set(CONTROL_DECISIONS)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def locked_by_position(name: str) -> dict[int, dict]:
    path = manuscript_root() / "manuscript_benchmark" / name
    data = json.loads(path.read_text(encoding="utf-8"))
    return {int(p["position"]): p for p in data["predictions"] if int(p["position"]) in ALL_POSITIONS}


def action_rows(actions) -> list[dict]:
    rows = []
    for item in actions or []:
        if isinstance(item, dict):
            rows.append(
                {
                    "action_id": item.get("action_id"),
                    "status": item.get("status"),
                    "n_new_measurements": item.get("n_new_measurements"),
                    "updated_measurement_fields": item.get("updated_measurement_fields") or [],
                    "summary": item.get("summary"),
                }
            )
        elif item:
            rows.append({"action_id": item, "status": None})
    return rows


def first_nonrepair(call_log: list[dict], role: str) -> dict:
    for row in call_log:
        if row.get("role") == role and "_repair" not in str(row.get("request_type") or ""):
            return row
    for row in call_log:
        if row.get("role") == role:
            return row
    return {}


def role_stats(call_log: list[dict], role: str) -> dict:
    rows = [r for r in call_log if r.get("role") == role]
    primary = first_nonrepair(call_log, role)
    return {
        "latency": primary.get("elapsed_seconds"),
        "input_tokens": sum(int(r.get("input_tokens") or 0) for r in rows),
        "output_tokens": sum(int(r.get("output_tokens") or 0) for r in rows),
        "reasoning_tokens": sum(int(r.get("reasoning_tokens") or 0) for r in rows),
        "total_tokens": sum(int(r.get("total_tokens") or 0) for r in rows),
        "retry_count": sum(int(r.get("retry_count") or 0) for r in rows),
        "parse_failures": sum(1 for r in rows if r.get("schema_valid") is False),
        "n_calls": len(rows),
        "response_id": primary.get("response_id"),
        "model": primary.get("model"),
        "provider": primary.get("provider"),
        "reasoning_effort": primary.get("reasoning_effort"),
    }


def endpoint_of(claim) -> str | None:
    if claim is None:
        return None
    ctype = claim.claim_type
    return ctype.value if hasattr(ctype, "value") else ctype


def verify_production_path(rec: dict, provenance: dict, call_log: list[dict], endpoint: str | None) -> list[str]:
    errors: list[str] = []
    if provenance.get("follow_up_policy") != "GS_AGENTIC_V4_1":
        errors.append("follow_up_policy is not GS_AGENTIC_V4_1")
    if provenance.get("silent_deterministic_fallback"):
        errors.append("silent deterministic fallback")
    if not sol_confirmed(call_log, "planner") or not provenance.get("planner_invoked"):
        errors.append("Sol Planner did not execute")
    planner_stats = role_stats(call_log, "planner")
    if planner_stats["parse_failures"] and planner_stats["n_calls"] and all(
        r.get("schema_valid") is False for r in call_log if r.get("role") == "planner"
    ):
        errors.append("Planner parse never succeeded")
    planner_action = provenance.get("selected_action") or provenance.get("control_decision")
    offered = set(provenance.get("actions_exposed_to_planner") or provenance.get("available_actions") or [])
    if planner_action and planner_action not in REGISTERED:
        errors.append(f"planner selected unregistered action {planner_action}")
    if planner_action and planner_action not in CONTROL_DECISIONS and offered and planner_action not in offered:
        errors.append(f"planner selected inapplicable action {planner_action}")
    executed = action_rows(provenance.get("actions_executed"))
    executed_ids = [r["action_id"] for r in executed if r.get("action_id")]
    unregistered = [a for a in executed_ids if a not in REGISTERED]
    if unregistered:
        errors.append(f"unregistered actions executed: {unregistered}")
    if planner_action and planner_action not in CONTROL_DECISIONS:
        if planner_action not in executed_ids:
            errors.append(f"planner action {planner_action} did not execute")
        else:
            first = next(r for r in executed if r["action_id"] == planner_action)
            if first.get("status") not in {"INFORMATIVE", "NO_NEW_INFORMATION", "UNAVAILABLE"}:
                errors.append(f"first action status missing: {first}")
            if first.get("status") == "INFORMATIVE" and not (
                first.get("n_new_measurements") or first.get("updated_measurement_fields")
            ):
                errors.append("informative first action left no measurement/evidence update")
    if not sol_confirmed(call_log, "critic") or not provenance.get("critic_invoked"):
        errors.append("Sol Critic did not execute")
    second = provenance.get("critic_second_action")
    if second:
        if second not in REGISTERED:
            errors.append(f"critic selected unregistered action {second}")
        if second not in executed_ids:
            errors.append(f"critic action {second} did not execute")
    if provenance.get("agent_failure"):
        errors.append(f"agent_failure: {provenance.get('agent_failure')}")
    if not provenance.get("final_validator_ran") or not endpoint:
        errors.append("frozen validator did not produce a final endpoint")
    if any(r.get("model") not in {None, SOL_MODEL} for r in call_log):
        errors.append("non-Sol model appeared in call log")
    return errors


def record_from_run(rec: dict, provenance: dict, call_log: list[dict], endpoint: str | None, runtime: float) -> dict:
    overlay = sol_ablation_overlay(call_log)
    executed = action_rows(provenance.get("actions_executed"))
    planner = role_stats(call_log, "planner")
    critic = role_stats(call_log, "critic")
    planner_action = provenance.get("selected_action") or provenance.get("control_decision")
    critic_disp = (provenance.get("critic_challenge") or {}).get("verdict")
    second = provenance.get("critic_second_action")
    first = executed[0] if executed else None
    second_row = executed[1] if len(executed) > 1 else None
    return {
        "position": rec["execution_position"],
        "case_id": rec["case_id"],
        "accession": rec["accession"],
        "target": rec["target"],
        "stratum": rec["stratum"],
        "rerun": rec["execution_position"] != 1,
        "sol_planner_action": planner_action,
        "sol_planner_latency": planner["latency"],
        "sol_planner_input_tokens": planner["input_tokens"],
        "sol_planner_output_tokens": planner["output_tokens"],
        "sol_planner_reasoning_tokens": planner["reasoning_tokens"],
        "first_deterministic_action_result": first,
        "sol_critic_disposition": critic_disp,
        "sol_critic_action": second,
        "sol_critic_latency": critic["latency"],
        "sol_critic_input_tokens": critic["input_tokens"],
        "sol_critic_output_tokens": critic["output_tokens"],
        "sol_critic_reasoning_tokens": critic["reasoning_tokens"],
        "second_deterministic_action_result": second_row,
        "n_follow_up_actions": len(executed),
        "final_endpoint": endpoint,
        "total_case_runtime": runtime,
        "api_cost_usd": overlay.get("estimated_api_cost_usd"),
        "parse_failures": planner["parse_failures"] + critic["parse_failures"],
        "retry_count": planner["retry_count"] + critic["retry_count"],
        "planner_sol_call_confirmed": sol_confirmed(call_log, "planner"),
        "critic_sol_call_confirmed": sol_confirmed(call_log, "critic"),
        "final_validator_ran": provenance.get("final_validator_ran"),
        "agent_failure": provenance.get("agent_failure"),
        "model": provenance.get("model_name"),
        "provider": SOL_PROVIDER,
        "reasoning_effort": SOL_REASONING_EFFORT,
        "ablation_config": SOL_ABLATION_ID,
        "truth_opened": False,
        "accuracy_scored": False,
        "call_log": call_log,
        "production_path_errors": [],
    }


def load_position_1() -> dict:
    rec = load_case(1)
    out_dir = OUT_ROOT / rec["case_id"] / "GS_AGENTIC_V4_1_SOL56_HIGH_POSTHOC"
    provenance = json.loads((out_dir / "agentic_provenance.json").read_text(encoding="utf-8"))
    call_log = json.loads((out_dir / "call_log.json").read_text(encoding="utf-8"))
    summary = json.loads((out_dir / "preflight_summary.json").read_text(encoding="utf-8"))
    row = record_from_run(rec, provenance, call_log, summary.get("final_endpoint"), summary.get("total_runtime"))
    row["production_path_errors"] = verify_production_path(rec, provenance, call_log, summary.get("final_endpoint"))
    if row["production_path_errors"]:
        raise SystemExit(f"position 1 production path invalid: {row['production_path_errors']}")
    return row


def run_new_case(position: int) -> dict:
    rec = load_case(position)
    if int(rec["execution_position"]) == 1:
        raise SystemExit("refusing to rerun position 1")
    expected = {
        2: ("GCF_052786815.1", "rpoB_RNAP_beta", "routine"),
        5: ("GCF_054452975.1", "tetA_tetracycline_efflux", "challenge"),
        6: ("GCF_052658775.1", "tetA_tetracycline_efflux", "routine"),
        8: ("GCF_056173045.1", "tetA_tetracycline_efflux", "challenge"),
    }[position]
    if (rec["accession"], rec["target"], rec["stratum"]) != expected:
        raise SystemExit(f"position {position} identity mismatch {rec['accession']} {rec['target']} {rec['stratum']}")
    out_dir = OUT_ROOT / rec["case_id"] / "GS_AGENTIC_V4_1_SOL56_HIGH_POSTHOC"
    if out_dir.exists():
        raise SystemExit(f"refusing to overwrite existing Sol output {out_dir}")
    assembly = solver_fasta(rec)
    settings = load_settings(ABLATION_YAML)
    if settings.llm.model != SOL_MODEL or settings.llm.provider != "openai_api":
        raise SystemExit("ablation yaml does not select gpt-5.6-sol / openai_api")
    out_dir.mkdir(parents=True, exist_ok=True)
    target_fa = out_dir / "target.fa"
    write_target_fa(target_fa, rec["target"])
    reset_call_log()
    started = time.perf_counter()
    claims, _loci, provenance = run_gs_agentic_v4_1(
        assembly,
        target_fa,
        out_dir,
        settings,
        declared_organism=rec.get("organism"),
        query_ids=[rec["target"]],
    )
    elapsed = round(time.perf_counter() - started, 3)
    overlay = sol_ablation_overlay(CALL_LOG)
    provenance.update(overlay)
    provenance["POST_HOC_MODEL_ABLATION"] = True
    provenance["MANUSCRIPT_PRIMARY_SYSTEM"] = False
    provenance["truth_opened"] = False
    provenance["accuracy_scored"] = False
    provenance["preflight_position"] = rec["execution_position"]
    (out_dir / "agentic_provenance.json").write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")
    (out_dir / "call_log.json").write_text(json.dumps(CALL_LOG, indent=2, default=str) + "\n", encoding="utf-8")
    endpoint = endpoint_of(claims[0] if claims else None)
    errors = verify_production_path(rec, provenance, list(CALL_LOG), endpoint)
    row = record_from_run(rec, provenance, list(CALL_LOG), endpoint, elapsed)
    row["production_path_errors"] = errors
    (out_dir / "preflight_summary.json").write_text(
        json.dumps({k: v for k, v in row.items() if k != "call_log"}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: row[k] for k in (
        "position", "case_id", "sol_planner_action", "sol_critic_disposition",
        "sol_critic_action", "n_follow_up_actions", "final_endpoint",
        "total_case_runtime", "planner_sol_call_confirmed", "critic_sol_call_confirmed",
        "production_path_errors",
    )}, indent=2), flush=True)
    if errors:
        raise SystemExit(f"STOP position {position}: {errors}")
    return row


def classify(qwen_action, sol_action, qwen_endpoint, sol_endpoint) -> str:
    same_action = (qwen_action or None) == (sol_action or None)
    same_end = (qwen_endpoint or None) == (sol_endpoint or None)
    if same_action and same_end:
        return "SAME_ACTION_SAME_ENDPOINT"
    if not same_action and same_end:
        return "DIFFERENT_ACTION_SAME_ENDPOINT"
    if not same_action and not same_end:
        return "DIFFERENT_ACTION_DIFFERENT_ENDPOINT"
    return "SAME_ACTION_DIFFERENT_ENDPOINT"


def critic_key(verdict, action) -> tuple:
    return (verdict or None, action or None)


def qwen_planner_action(pred: dict):
    acts = pred.get("planner_actions")
    if isinstance(acts, list) and acts:
        return acts[0]
    return acts or pred.get("planner_control_decision")


def lock_five(rows: list[dict]) -> dict:
    qwen = locked_by_position("M60_GS_AGENTIC_LOCKED.json")
    det = locked_by_position("M60_GS_DETERMINISTIC_LOCKED.json")
    exh = locked_by_position("M60_GS_EXHAUSTIVE_LOCKED.json")
    comparisons = []
    for row in rows:
        pos = int(row["position"])
        q = qwen[pos]
        d = det[pos]
        e = exh[pos]
        q_plan = qwen_planner_action(q)
        q_crit_v = q.get("critic_verdict")
        q_crit_a = q.get("critic_actions")
        q_n = len(q.get("actions_executed") or [])
        q_end = q.get("final_result")
        comparisons.append(
            {
                "position": pos,
                "case_id": row["case_id"],
                "accession": row["accession"],
                "target": row["target"],
                "stratum": row["stratum"],
                "qwen_planner_action": q_plan,
                "sol_planner_action": row["sol_planner_action"],
                "qwen_critic_disposition": q_crit_v,
                "qwen_critic_action": q_crit_a,
                "sol_critic_disposition": row["sol_critic_disposition"],
                "sol_critic_action": row["sol_critic_action"],
                "qwen_n_follow_up_actions": q_n,
                "sol_n_follow_up_actions": row["n_follow_up_actions"],
                "qwen_final_endpoint": q_end,
                "sol_final_endpoint": row["final_endpoint"],
                "gs_deterministic_endpoint": d.get("final_result"),
                "gs_exhaustive_endpoint": e.get("final_result"),
                "action_endpoint_class": classify(q_plan, row["sol_planner_action"], q_end, row["final_endpoint"]),
                "planner_action_changed_vs_qwen": q_plan != row["sol_planner_action"],
                "critic_behaviour_changed_vs_qwen": critic_key(q_crit_v, q_crit_a)
                != critic_key(row["sol_critic_disposition"], row["sol_critic_action"]),
                "endpoint_changed_vs_qwen": q_end != row["final_endpoint"],
                "endpoint_changed_vs_gs_deterministic": d.get("final_result") != row["final_endpoint"],
                "endpoint_different_from_gs_exhaustive": e.get("final_result") != row["final_endpoint"],
            }
        )

    def median(vals):
        vals = [v for v in vals if v is not None]
        return round(statistics.median(vals), 3) if vals else None

    n = len(rows)
    totals = {
        "planner_action_changed_vs_qwen": sum(c["planner_action_changed_vs_qwen"] for c in comparisons),
        "critic_behaviour_changed_vs_qwen": sum(c["critic_behaviour_changed_vs_qwen"] for c in comparisons),
        "endpoint_changed_vs_qwen": sum(c["endpoint_changed_vs_qwen"] for c in comparisons),
        "endpoint_changed_vs_gs_deterministic": sum(c["endpoint_changed_vs_gs_deterministic"] for c in comparisons),
        "endpoint_different_from_gs_exhaustive": sum(c["endpoint_different_from_gs_exhaustive"] for c in comparisons),
        "mean_sol_follow_up_actions": round(sum(r["n_follow_up_actions"] for r in rows) / n, 3),
        "mean_qwen_follow_up_actions": round(sum(c["qwen_n_follow_up_actions"] for c in comparisons) / n, 3),
        "total_sol_api_cost_usd": round(sum(float(r.get("api_cost_usd") or 0) for r in rows), 6),
        "median_sol_planner_latency": median([r["sol_planner_latency"] for r in rows]),
        "median_sol_critic_latency": median([r["sol_critic_latency"] for r in rows]),
        "median_sol_case_runtime": median([r["total_case_runtime"] for r in rows]),
        "total_sol_tokens": sum(
            int(r["sol_planner_input_tokens"] or 0)
            + int(r["sol_planner_output_tokens"] or 0)
            + int(r["sol_critic_input_tokens"] or 0)
            + int(r["sol_critic_output_tokens"] or 0)
            for r in rows
        ),
        "parse_failures": sum(int(r["parse_failures"] or 0) for r in rows),
        "retries": sum(int(r["retry_count"] or 0) for r in rows),
    }
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    results_path = LOCK_DIR / "SOL56_5CASE_RESULTS.json"
    call_log_path = LOCK_DIR / "SOL56_5CASE_CALL_LOG.jsonl"
    csv_path = LOCK_DIR / "SOL56_5CASE_COMPARISON.csv"
    manifest_path = LOCK_DIR / "SOL56_5CASE_MANIFEST.json"

    results_payload = {
        "kind": "SOL56_5CASE_RESULTS",
        "ablation_config": SOL_ABLATION_ID,
        "POST_HOC_MODEL_ABLATION": True,
        "MANUSCRIPT_PRIMARY_SYSTEM": False,
        "model": SOL_MODEL,
        "reasoning_effort": SOL_REASONING_EFFORT,
        "provider": SOL_PROVIDER,
        "truth_opened": False,
        "accuracy_scored": False,
        "n_cases": n,
        "positions": [r["position"] for r in rows],
        "cases": [{k: v for k, v in r.items() if k != "call_log"} for r in rows],
        "totals": totals,
    }
    results_sha = write_json(results_path, results_payload)
    with call_log_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            for call in r.get("call_log") or []:
                rec = dict(call)
                rec["case_id"] = r["case_id"]
                rec["position"] = r["position"]
                fh.write(json.dumps(rec, default=str) + "\n")
    call_sha = sha256_file(call_log_path)
    fieldnames = list(comparisons[0].keys())
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparisons)
    csv_sha = sha256_file(csv_path)
    hashes = scientific_core_hashes()
    manifest = {
        "kind": "SOL56_5CASE_MANIFEST",
        "ablation_config": SOL_ABLATION_ID,
        "POST_HOC_MODEL_ABLATION": True,
        "MANUSCRIPT_PRIMARY_SYSTEM": False,
        "model": SOL_MODEL,
        "reasoning_effort": SOL_REASONING_EFFORT,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "positions": list(ALL_POSITIONS),
        "new_positions": list(NEW_POSITIONS),
        "position_1_rerun": False,
        "truth_opened": False,
        "accuracy_scored": False,
        "all_production_paths_verified": all(not r["production_path_errors"] for r in rows),
        "scientific_invariant_hashes": {k: hashes[k] for k in EXPECTED_INVARIANT_HASHES},
        "scientific_core_hash_manuscript": EXPECTED_CORE,
        "files": {
            "SOL56_5CASE_RESULTS.json": results_sha,
            "SOL56_5CASE_CALL_LOG.jsonl": call_sha,
            "SOL56_5CASE_COMPARISON.csv": csv_sha,
        },
        "totals": totals,
        "comparisons": comparisons,
    }
    body = json.dumps(manifest, indent=2, default=str) + "\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    manifest["manifest_sha256"] = digest
    write_json(manifest_path, manifest)
    sidecar = {
        "path": "manuscript_benchmark/SOL56_SMALL_PREFLIGHT/SOL56_5CASE_MANIFEST.json",
        "sha256": sha256_file(manifest_path),
        "hashed_utc": datetime.now(timezone.utc).isoformat(),
        "truth_opened": False,
        "accuracy_scored": False,
    }
    (LOCK_DIR / "SOL56_5CASE_MANIFEST.json.sha256.json").write_text(
        json.dumps(sidecar, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"lock": str(LOCK_DIR), "manifest_sha256": sidecar["sha256"], "totals": totals}, indent=2), flush=True)
    return sidecar


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise SystemExit("OPENAI_API_KEY is not set")
    hashes = scientific_core_hashes()
    for key, expected in EXPECTED_INVARIANT_HASHES.items():
        if hashes[key] != expected:
            raise SystemExit(f"STOP scientific invariant {key} changed")
    rows = [load_position_1()]
    for pos in NEW_POSITIONS:
        print(f"RUN position {pos}", flush=True)
        rows.append(run_new_case(pos))
    rows.sort(key=lambda r: int(r["position"]))
    lock_five(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
