#!/usr/bin/env python3
"""Full 60-case post-hoc GPT-5.6 Sol ablation of frozen GS_AGENTIC_V4_1.

Reuses positions 1, 2, 5, 6, 8 only if the locked 5-case preflight hashes match.
Runs remaining positions sequentially on the real production path.
Locks each completed position. Scores only after all 60 predictions are locked.
Does not change prompts, schemas, validator, thresholds, or scientific core.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import statistics
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

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
    OUT_ROOT as PREFLIGHT_OUT_ROOT,
    load_case,
    manuscript_root,
    sol_confirmed,
    solver_fasta,
    write_target_fa,
)
from run_sol56_small_preflight import (  # noqa: E402
    LOCK_DIR as SMALL_LOCK_DIR,
    action_rows,
    classify,
    critic_key,
    endpoint_of,
    qwen_planner_action,
    record_from_run,
    verify_production_path,
)

REUSE_POSITIONS = (1, 2, 5, 6, 8)
ALL_POSITIONS = tuple(range(1, 61))
SMALL_MANIFEST_SHA256 = "7b8ef9e24a5a6a395b6a685ef035f2671fff84bc75b7c3d9ab88553ef0bebc27"
SMALL_FILE_SHA256 = {
    "SOL56_5CASE_RESULTS.json": "d2301a4520aa9bc61705ec151543a25e40b189c69a73b16d15e8b440977154b6",
    "SOL56_5CASE_CALL_LOG.jsonl": "a208ad21928a59f5227c13cdf6cb25f0629d440a7911c361f2235ae40221e8e0",
    "SOL56_5CASE_COMPARISON.csv": "14c6a4912ad09d84ca52bd52467540ccd337048b2a9015a976eebe8ca6bb58e1",
}
EXPECTED_TRUTH_SHA256 = "a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9"
BOOTSTRAP_SEED = 20260920
BOOTSTRAP_N = 10000
MAX_CASE_ATTEMPTS = 3
CASE_RETRY_SLEEP = (20, 60, 120)

OUT_DIR = ROOT / "manuscript_benchmark" / "SOL56_FULL_ABLATION"
LOCKS_DIR = OUT_DIR / "locks"
CASE_OUT_ROOT = ROOT / "manuscript_benchmark" / "ABLATION_SOL56_HIGH_POSTHOC" / "full"
PREDICTION_LOCK_NAME = "SOL56_M60_PREDICTION_LOCK.json"
OUTPUT_NAMES = (
    "SOL56_M60_CASE_LEVEL.csv",
    "SOL56_M60_MODEL_BEHAVIOUR.csv",
    "SOL56_M60_SCORING.csv",
    "SOL56_M60_CALL_LOG.jsonl",
    "SOL56_M60_SUMMARY.json",
    "SOL56_M60_MANIFEST.json",
    "SOL56_M60_RESULTS.md",
    PREDICTION_LOCK_NAME,
)

TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "rate limit",
    "429",
    "500",
    "502",
    "503",
    "529",
    "connection",
    "temporarily unavailable",
    "overloaded",
    "apiconnection",
    "apitimeout",
    "ratelimit",
    "internalserver",
    "empty structured content",
    "response status",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")
    return sha256_file(path)


def lock_path(position: int) -> Path:
    return LOCKS_DIR / f"position_{int(position):02d}.json"


def progress_path() -> Path:
    return OUT_DIR / "progress.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def median(vals):
    vals = [v for v in vals if v is not None]
    return round(float(statistics.median(vals)), 6) if vals else None


def mean(vals):
    vals = [v for v in vals if v is not None]
    return round(float(sum(vals) / len(vals)), 6) if vals else None


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / den
    margin = (z / den) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def fmt_ci(ci: tuple[float, float]) -> str:
    if any(math.isnan(x) for x in ci):
        return "NA"
    return f"{ci[0]:.3f}–{ci[1]:.3f}"


def fmt_pct_pts(x: float) -> str:
    return f"{100.0 * x:+.1f} pp"


def gs_binary_from_endpoint(endpoint: str | None) -> str:
    if endpoint == "target_gene_detected":
        return "POSITIVE"
    if endpoint == "target_gene_not_detected":
        return "NEGATIVE"
    return "UNRESOLVED"


def is_correct(truth: str, pred: str) -> bool | None:
    if truth == "TRUTH_UNCERTAIN":
        return None
    if truth in {"POSITIVE", "NEGATIVE"}:
        return pred == truth
    return None


def paired_bootstrap_diff(a: list[int], b: list[int]) -> tuple[float, float]:
    import numpy as np

    n = len(a)
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    diffs = np.empty(BOOTSTRAP_N, dtype=float)
    for i in range(BOOTSTRAP_N):
        idx = rng.integers(0, n, size=n)
        diffs[i] = aa[idx].mean() - bb[idx].mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(lo), float(hi)


def exact_mcnemar_p(corrections: int, degradations: int) -> float | None:
    n = corrections + degradations
    if n == 0:
        return None
    try:
        from scipy.stats import binomtest

        return float(binomtest(corrections, n=n, p=0.5, alternative="two-sided").pvalue)
    except Exception:
        from math import comb

        tail = min(corrections, n - corrections)
        p = sum(comb(n, i) for i in range(0, tail + 1)) / (2**n)
        return min(1.0, 2.0 * p)


def is_transient(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = f"{name} {exc}".lower()
    return any(marker in text for marker in TRANSIENT_MARKERS)


def qwen_critic_action(pred: dict):
    acts = pred.get("critic_actions")
    if isinstance(acts, list):
        return acts[0] if acts else None
    return acts


def index_locked(name: str) -> dict[int, dict]:
    path = manuscript_root() / "manuscript_benchmark" / name
    data = load_json(path)
    out = {int(p["position"]): p for p in data["predictions"]}
    if len(out) != 60:
        raise SystemExit(f"{name} n={len(out)}")
    return out


def followups(pred: dict) -> int:
    integ = pred.get("integrity") or {}
    if integ.get("n_deterministic_followup_analyses") is not None:
        try:
            return int(integ["n_deterministic_followup_analyses"])
        except (TypeError, ValueError):
            pass
    acts = pred.get("actions_executed") or []
    return len(acts) if isinstance(acts, list) else 0


def update_progress(**kwargs) -> None:
    path = progress_path()
    state = load_json(path) if path.exists() else {
        "kind": "SOL56_FULL_ABLATION_PROGRESS",
        "ablation_config": SOL_ABLATION_ID,
        "POST_HOC_MODEL_ABLATION": True,
        "MANUSCRIPT_PRIMARY_VALIDATION": False,
        "completed_positions": [],
        "failed_positions": [],
        "truth_opened": False,
        "accuracy_scored": False,
    }
    state.update(kwargs)
    completed = sorted({int(p) for p in state.get("completed_positions") or []})
    state["completed_positions"] = completed
    state["n_completed"] = len(completed)
    state["updated_utc"] = utc_now()
    write_json(path, state)


def verify_invariants() -> dict:
    hashes = scientific_core_hashes()
    for key, expected in EXPECTED_INVARIANT_HASHES.items():
        if hashes[key] != expected:
            raise SystemExit(f"STOP scientific invariant {key} changed: {hashes[key]} != {expected}")
    return {k: hashes[k] for k in EXPECTED_INVARIANT_HASHES}


def verify_small_preflight() -> dict:
    manifest_path = SMALL_LOCK_DIR / "SOL56_5CASE_MANIFEST.json"
    got = sha256_file(manifest_path)
    if got != SMALL_MANIFEST_SHA256:
        raise SystemExit(
            f"STOP 5-case manifest SHA256 mismatch: {got} != {SMALL_MANIFEST_SHA256}; refusing reuse"
        )
    files = {}
    for name, expected in SMALL_FILE_SHA256.items():
        path = SMALL_LOCK_DIR / name
        digest = sha256_file(path)
        if digest != expected:
            raise SystemExit(f"STOP 5-case file hash mismatch {name}: {digest} != {expected}")
        files[name] = digest
    return {"manifest_sha256": got, "files": files}


def enrich_row(row: dict, provenance: dict, rec: dict, *, reused: bool, case_dir: Path) -> dict:
    claim = provenance.get("final_claim_state") or {}
    mstate = provenance.get("measurement_state") or {}
    m0 = mstate.get("m0") or {}
    m_final = mstate.get("m_final") or {}
    overlay = sol_ablation_overlay(row.get("call_log") or [])
    row["reused_from_small_preflight"] = reused
    row["case_dir"] = str(case_dir)
    row["sol_architecture"] = claim.get("architecture_state")
    row["sol_homology_support"] = claim.get("homology_support")
    row["sol_claim_class"] = claim.get("status") or claim.get("claim_class")
    row["m0_hash"] = m0.get("hash")
    row["m_final_hash"] = m_final.get("hash")
    row["measurements_changed_before_validation"] = provenance.get("measurements_changed_before_validation")
    row["sol_input_tokens"] = overlay.get("sol_input_tokens")
    row["sol_output_tokens"] = overlay.get("sol_output_tokens")
    row["sol_reasoning_tokens"] = overlay.get("sol_reasoning_tokens")
    row["sol_total_tokens"] = overlay.get("sol_total_tokens")
    row["case_dir_sha256"] = {
        "agentic_provenance.json": sha256_file(case_dir / "agentic_provenance.json") if (case_dir / "agentic_provenance.json").exists() else None,
        "call_log.json": sha256_file(case_dir / "call_log.json") if (case_dir / "call_log.json").exists() else None,
    }
    row["POST_HOC_MODEL_ABLATION"] = True
    row["MANUSCRIPT_PRIMARY_VALIDATION"] = False
    row["truth_opened"] = False
    row["accuracy_scored"] = False
    return row


def persist_lock(row: dict) -> None:
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in row.items() if k != "call_log"}
    slim["locked_utc"] = utc_now()
    write_json(lock_path(int(row["position"])), slim)
    completed = [int(p.stem.split("_")[1]) for p in LOCKS_DIR.glob("position_*.json")]
    update_progress(completed_positions=sorted(completed), truth_opened=False, accuracy_scored=False)


def load_lock(position: int) -> dict | None:
    path = lock_path(position)
    if not path.exists():
        return None
    row = load_json(path)
    case_dir = Path(row["case_dir"])
    call_path = case_dir / "call_log.json"
    row["call_log"] = load_json(call_path) if call_path.exists() else []
    return row


def load_reused_case(position: int) -> dict:
    rec = load_case(position)
    case_dir = PREFLIGHT_OUT_ROOT / rec["case_id"] / "GS_AGENTIC_V4_1_SOL56_HIGH_POSTHOC"
    if not case_dir.exists():
        raise SystemExit(f"STOP reused position {position} missing case dir {case_dir}")
    provenance = load_json(case_dir / "agentic_provenance.json")
    call_log = load_json(case_dir / "call_log.json")
    summary = load_json(case_dir / "preflight_summary.json")
    endpoint = summary.get("final_endpoint")
    errors = verify_production_path(rec, provenance, call_log, endpoint)
    if errors:
        raise SystemExit(f"STOP reused position {position} production path invalid: {errors}")
    row = record_from_run(rec, provenance, call_log, endpoint, summary.get("total_case_runtime") or summary.get("total_runtime"))
    row["production_path_errors"] = errors
    row["case_attempt"] = 1
    row["transient_retries"] = 0
    enrich_row(row, provenance, rec, reused=True, case_dir=case_dir)
    if row["model"] != SOL_MODEL or row["reasoning_effort"] != SOL_REASONING_EFFORT:
        raise SystemExit(f"STOP reused position {position} is not Sol high")
    persist_lock(row)
    print(f"REUSE position {position} {rec['case_id']} endpoint={endpoint}", flush=True)
    return row


def run_one_position(position: int) -> dict:
    rec = load_case(position)
    settings = load_settings(ABLATION_YAML)
    if settings.llm.model != SOL_MODEL or settings.llm.provider != "openai_api":
        raise SystemExit("ablation yaml does not select gpt-5.6-sol / openai_api")
    assembly = solver_fasta(rec)
    case_dir = CASE_OUT_ROOT / rec["case_id"] / "GS_AGENTIC_V4_1_SOL56_HIGH_POSTHOC"
    last_error = None
    for attempt in range(1, MAX_CASE_ATTEMPTS + 1):
        if case_dir.exists():
            shutil.rmtree(case_dir)
        case_dir.mkdir(parents=True, exist_ok=True)
        write_target_fa(case_dir / "target.fa", rec["target"])
        reset_call_log()
        started = time.perf_counter()
        try:
            claims, _loci, provenance = run_gs_agentic_v4_1(
                assembly,
                case_dir / "target.fa",
                case_dir,
                settings,
                declared_organism=rec.get("organism"),
                query_ids=[rec["target"]],
            )
            elapsed = round(time.perf_counter() - started, 3)
            overlay = sol_ablation_overlay(CALL_LOG)
            provenance.update(overlay)
            provenance["POST_HOC_MODEL_ABLATION"] = True
            provenance["MANUSCRIPT_PRIMARY_SYSTEM"] = False
            provenance["MANUSCRIPT_PRIMARY_VALIDATION"] = False
            provenance["truth_opened"] = False
            provenance["accuracy_scored"] = False
            provenance["full_ablation_position"] = rec["execution_position"]
            (case_dir / "agentic_provenance.json").write_text(
                json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8"
            )
            (case_dir / "call_log.json").write_text(
                json.dumps(CALL_LOG, indent=2, default=str) + "\n", encoding="utf-8"
            )
            endpoint = endpoint_of(claims[0] if claims else None)
            errors = verify_production_path(rec, provenance, list(CALL_LOG), endpoint)
            row = record_from_run(rec, provenance, list(CALL_LOG), endpoint, elapsed)
            row["production_path_errors"] = errors
            row["case_attempt"] = attempt
            row["transient_retries"] = attempt - 1
            enrich_row(row, provenance, rec, reused=False, case_dir=case_dir)
            (case_dir / "case_summary.json").write_text(
                json.dumps({k: v for k, v in row.items() if k != "call_log"}, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "event": "case_complete",
                        "position": position,
                        "case_id": rec["case_id"],
                        "attempt": attempt,
                        "sol_planner_action": row["sol_planner_action"],
                        "sol_critic_disposition": row["sol_critic_disposition"],
                        "sol_critic_action": row["sol_critic_action"],
                        "n_follow_up_actions": row["n_follow_up_actions"],
                        "final_endpoint": endpoint,
                        "total_case_runtime": elapsed,
                        "production_path_errors": errors,
                    },
                    default=str,
                ),
                flush=True,
            )
            if errors:
                raise RuntimeError(f"production path errors: {errors}")
            persist_lock(row)
            return row
        except Exception as exc:
            last_error = exc
            elapsed = round(time.perf_counter() - started, 3)
            failure = {
                "position": position,
                "case_id": rec["case_id"],
                "attempt": attempt,
                "transient": is_transient(exc),
                "error_type": type(exc).__name__,
                "error": str(exc)[:800],
                "elapsed": elapsed,
                "utc": utc_now(),
            }
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            with (OUT_DIR / "failures.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(failure, default=str) + "\n")
            print(json.dumps({"event": "case_failure", **failure}, default=str), flush=True)
            if (not is_transient(exc)) or attempt >= MAX_CASE_ATTEMPTS:
                raise
            time.sleep(CASE_RETRY_SLEEP[min(attempt - 1, len(CASE_RETRY_SLEEP) - 1)])
    raise RuntimeError(f"position {position} failed after retries: {last_error}")


def load_all_locks() -> list[dict]:
    rows = []
    missing = []
    for pos in ALL_POSITIONS:
        row = load_lock(pos)
        if row is None:
            missing.append(pos)
        else:
            rows.append(row)
    if missing:
        raise SystemExit(f"STOP cannot lock 60 predictions; missing positions {missing}")
    rows.sort(key=lambda r: int(r["position"]))
    return rows


def blinded_comparison(rows: list[dict]) -> list[dict]:
    qwen = index_locked("M60_GS_AGENTIC_LOCKED.json")
    det = index_locked("M60_GS_DETERMINISTIC_LOCKED.json")
    exh = index_locked("M60_GS_EXHAUSTIVE_LOCKED.json")
    comparisons = []
    for row in rows:
        pos = int(row["position"])
        q = qwen[pos]
        d = det[pos]
        e = exh[pos]
        q_plan = qwen_planner_action(q)
        q_crit_v = q.get("critic_verdict")
        q_crit_a = qwen_critic_action(q)
        q_n = followups(q)
        e_n = followups(e)
        q_end = q.get("final_result")
        d_end = d.get("final_result")
        e_end = e.get("final_result")
        extra = int(row["n_follow_up_actions"] or 0) - int(q_n or 0)
        endpoint_changed = q_end != row["final_endpoint"]
        extra_effect = None
        if extra > 0:
            extra_effect = "DECISION_CHANGE" if endpoint_changed else "NO_DECISION_CHANGE"
        fields = []
        for key in ("first_deterministic_action_result", "second_deterministic_action_result"):
            act = row.get(key) or {}
            if isinstance(act, dict):
                fields.extend(act.get("updated_measurement_fields") or [])
        evidence_reason = None
        if endpoint_changed:
            evidence_reason = (
                f"qwen_endpoint={q_end} sol_endpoint={row['final_endpoint']}; "
                f"qwen_architecture={q.get('architecture')} sol_architecture={row.get('sol_architecture')}; "
                f"qwen_homology={q.get('homology_support')} sol_homology={row.get('sol_homology_support')}; "
                f"actions={row.get('sol_planner_action')}"
                + (f"+{row.get('sol_critic_action')}" if row.get("sol_critic_action") else "")
                + f"; updated_measurement_fields={fields}; "
                f"m0={row.get('m0_hash')} m_final={row.get('m_final_hash')}; "
                f"measurements_changed={row.get('measurements_changed_before_validation')}"
            )
        comparisons.append(
            {
                "position": pos,
                "case_id": row["case_id"],
                "accession": row["accession"],
                "target": row["target"],
                "stratum": row["stratum"],
                "reused_from_small_preflight": row.get("reused_from_small_preflight"),
                "qwen_planner_action": q_plan,
                "sol_planner_action": row["sol_planner_action"],
                "planner_action_changed_vs_qwen": q_plan != row["sol_planner_action"],
                "qwen_critic_disposition": q_crit_v,
                "qwen_critic_action": q_crit_a,
                "sol_critic_disposition": row["sol_critic_disposition"],
                "sol_critic_action": row["sol_critic_action"],
                "critic_behaviour_changed_vs_qwen": critic_key(q_crit_v, q_crit_a)
                != critic_key(row["sol_critic_disposition"], row["sol_critic_action"]),
                "qwen_n_follow_up_actions": q_n,
                "sol_n_follow_up_actions": row["n_follow_up_actions"],
                "exhaustive_n_follow_up_actions": e_n,
                "follow_up_action_count_changed": int(q_n or 0) != int(row["n_follow_up_actions"] or 0),
                "qwen_final_endpoint": q_end,
                "sol_final_endpoint": row["final_endpoint"],
                "gs_deterministic_endpoint": d_end,
                "gs_exhaustive_endpoint": e_end,
                "endpoint_changed_vs_qwen": endpoint_changed,
                "endpoint_changed_vs_gs_deterministic": d_end != row["final_endpoint"],
                "endpoint_different_from_gs_exhaustive": e_end != row["final_endpoint"],
                "action_endpoint_class": classify(q_plan, row["sol_planner_action"], q_end, row["final_endpoint"]),
                "extra_sol_follow_up_actions": extra,
                "extra_sol_action_effect": extra_effect,
                "sol_new_evidence_fields": ";".join(dict.fromkeys(str(f) for f in fields)),
                "validator_state_change_reason": evidence_reason,
                "qwen_architecture": q.get("architecture"),
                "sol_architecture": row.get("sol_architecture"),
                "qwen_homology_support": q.get("homology_support"),
                "sol_homology_support": row.get("sol_homology_support"),
                "qwen_runtime_seconds": q.get("runtime_seconds"),
                "sol_runtime_seconds": row.get("total_case_runtime"),
                "exhaustive_runtime_seconds": e.get("runtime_seconds"),
                "sol_planner_latency": row.get("sol_planner_latency"),
                "sol_critic_latency": row.get("sol_critic_latency"),
                "sol_input_tokens": row.get("sol_input_tokens"),
                "sol_output_tokens": row.get("sol_output_tokens"),
                "sol_reasoning_tokens": row.get("sol_reasoning_tokens"),
                "sol_api_cost_usd": row.get("api_cost_usd"),
            }
        )
    return comparisons


def write_prediction_lock(rows: list[dict], comparisons: list[dict]) -> str:
    payload = {
        "kind": "SOL56_M60_PREDICTION_LOCK",
        "ablation_config": SOL_ABLATION_ID,
        "POST_HOC_MODEL_ABLATION": True,
        "MANUSCRIPT_PRIMARY_VALIDATION": False,
        "model": SOL_MODEL,
        "reasoning_effort": SOL_REASONING_EFFORT,
        "provider": SOL_PROVIDER,
        "n_cases": 60,
        "do_not_regenerate": True,
        "truth_opened": False,
        "accuracy_scored": False,
        "created_utc": utc_now(),
        "reused_positions": list(REUSE_POSITIONS),
        "small_preflight_manifest_sha256": SMALL_MANIFEST_SHA256,
        "predictions": [
            {
                "position": r["position"],
                "case_id": r["case_id"],
                "accession": r["accession"],
                "target": r["target"],
                "stratum": r["stratum"],
                "system": SOL_ABLATION_ID,
                "model": SOL_MODEL,
                "reasoning_effort": SOL_REASONING_EFFORT,
                "final_result": r["final_endpoint"],
                "planner_action": r["sol_planner_action"],
                "critic_verdict": r["sol_critic_disposition"],
                "critic_action": r["sol_critic_action"],
                "actions_executed": [
                    (r.get("first_deterministic_action_result") or {}).get("action_id"),
                    (r.get("second_deterministic_action_result") or {}).get("action_id"),
                ],
                "n_follow_up_actions": r["n_follow_up_actions"],
                "architecture": r.get("sol_architecture"),
                "homology_support": r.get("sol_homology_support"),
                "runtime_seconds": r.get("total_case_runtime"),
                "reused_from_small_preflight": r.get("reused_from_small_preflight"),
                "ok": True,
                "completion_status": "complete",
                "truth_opened": False,
                "accuracy_scored": False,
            }
            for r in rows
        ],
        "blinded_totals": {
            "planner_action_changed_vs_qwen": sum(c["planner_action_changed_vs_qwen"] for c in comparisons),
            "critic_behaviour_changed_vs_qwen": sum(c["critic_behaviour_changed_vs_qwen"] for c in comparisons),
            "follow_up_action_count_changed": sum(c["follow_up_action_count_changed"] for c in comparisons),
            "endpoint_changed_vs_qwen": sum(c["endpoint_changed_vs_qwen"] for c in comparisons),
            "endpoint_changed_vs_gs_deterministic": sum(c["endpoint_changed_vs_gs_deterministic"] for c in comparisons),
            "endpoint_different_from_gs_exhaustive": sum(c["endpoint_different_from_gs_exhaustive"] for c in comparisons),
        },
    }
    return write_json(OUT_DIR / PREDICTION_LOCK_NAME, payload)


def write_csv(path: Path, rows: list[dict]) -> str:
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") if row.get(k) is not None else "" for k in fields})
    return sha256_file(path)


def join_truth(comparisons: list[dict], rows: list[dict]) -> tuple[list[dict], dict]:
    truth_path = manuscript_root() / "manuscript_benchmark" / "TRUTH_M60" / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json"
    got = sha256_file(truth_path)
    if got != EXPECTED_TRUTH_SHA256:
        raise SystemExit(f"STOP frozen truth SHA256 mismatch: {got} != {EXPECTED_TRUTH_SHA256}")
    truth = load_json(truth_path)
    by_id = {c["case_id"]: c for c in truth["cases"]}
    joined = []
    for cmp_row, sol_row in zip(comparisons, rows):
        tcase = by_id[cmp_row["case_id"]]
        truth_value = tcase["truth_value"]
        sol_bin = gs_binary_from_endpoint(cmp_row["sol_final_endpoint"])
        qwen_bin = gs_binary_from_endpoint(cmp_row["qwen_final_endpoint"])
        det_bin = gs_binary_from_endpoint(cmp_row["gs_deterministic_endpoint"])
        exh_bin = gs_binary_from_endpoint(cmp_row["gs_exhaustive_endpoint"])
        joined.append(
            {
                **cmp_row,
                "truth": truth_value,
                "truth_status": tcase.get("truth_status"),
                "evaluable": truth_value in {"POSITIVE", "NEGATIVE"},
                "sol_pred": sol_bin,
                "qwen_pred": qwen_bin,
                "gs_det_pred": det_bin,
                "gs_exh_pred": exh_bin,
                "sol_correct": is_correct(truth_value, sol_bin),
                "qwen_correct": is_correct(truth_value, qwen_bin),
                "gs_det_correct": is_correct(truth_value, det_bin),
                "gs_exh_correct": is_correct(truth_value, exh_bin),
                "sol_planner_latency": sol_row.get("sol_planner_latency"),
                "sol_critic_latency": sol_row.get("sol_critic_latency"),
                "parse_failures": sol_row.get("parse_failures"),
                "retry_count": sol_row.get("retry_count"),
            }
        )
    eval_rows = [r for r in joined if r["evaluable"]]
    if len(eval_rows) != 41:
        raise SystemExit(f"evaluable {len(eval_rows)} != 41")

    def n_truth(prefix, value):
        return sum(1 for r in joined if r["target"].startswith(prefix) and r["truth"] == value)

    dist = {
        "total": 60,
        "tetA_POSITIVE": n_truth("tetA", "POSITIVE"),
        "tetA_NEGATIVE": n_truth("tetA", "NEGATIVE"),
        "tetA_TRUTH_UNCERTAIN": n_truth("tetA", "TRUTH_UNCERTAIN"),
        "rpoB_POSITIVE": n_truth("rpoB", "POSITIVE"),
        "rpoB_NEGATIVE": n_truth("rpoB", "NEGATIVE"),
        "rpoB_TRUTH_UNCERTAIN": n_truth("rpoB", "TRUTH_UNCERTAIN"),
    }
    expected = {
        "total": 60,
        "tetA_POSITIVE": 7,
        "tetA_NEGATIVE": 19,
        "tetA_TRUTH_UNCERTAIN": 4,
        "rpoB_POSITIVE": 15,
        "rpoB_NEGATIVE": 0,
        "rpoB_TRUTH_UNCERTAIN": 15,
    }
    if dist != expected:
        raise SystemExit(f"TRUTH DISTRIBUTION MISMATCH {dist}")
    return joined, {"truth_sha256": got, "distribution": dist, "evaluable_n": 41}


def subset_score(name: str, rows: list[dict], pred_key: str, corr_key: str) -> dict:
    k = sum(1 for r in rows if r[corr_key] is True)
    n = len(rows)
    acc = k / n if n else float("nan")
    ci = wilson_ci(k, n)
    return {
        "system": name,
        "correct": k,
        "evaluable_n": n,
        "accuracy": acc,
        "wilson_ci_low": ci[0],
        "wilson_ci_high": ci[1],
        "wilson_ci": fmt_ci(ci),
        "correct_over_n": f"{k} / {n}",
        "pred_key": pred_key,
    }


def paired_vs(eval_rows: list[dict], left_corr: str, right_corr: str) -> dict:
    corrections = [r for r in eval_rows if (not r[right_corr]) and r[left_corr]]
    degradations = [r for r in eval_rows if r[right_corr] and (not r[left_corr])]
    left = [1 if r[left_corr] else 0 for r in eval_rows]
    right = [1 if r[right_corr] else 0 for r in eval_rows]
    acc_diff = (sum(left) / len(left)) - (sum(right) / len(right))
    ci = paired_bootstrap_diff(left, right)
    p = exact_mcnemar_p(len(corrections), len(degradations))
    return {
        "corrections": len(corrections),
        "degradations": len(degradations),
        "net": len(corrections) - len(degradations),
        "accuracy_difference": acc_diff,
        "paired_bootstrap_95_ci": ci,
        "paired_bootstrap_95_ci_text": fmt_ci(ci),
        "mcnemar_p": p,
        "correction_case_ids": [r["case_id"] for r in corrections],
        "degradation_case_ids": [r["case_id"] for r in degradations],
    }


def analyze(rows: list[dict]) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    comparisons = blinded_comparison(rows)
    pred_sha = write_prediction_lock(rows, comparisons)
    print(json.dumps({"event": "phase1_locked", "prediction_lock_sha256": pred_sha, "n": 60}, indent=2), flush=True)

    joined, truth_meta = join_truth(comparisons, rows)
    eval_rows = [r for r in joined if r["evaluable"]]
    tetA = [r for r in eval_rows if r["target"].startswith("tetA")]
    rpob = [r for r in eval_rows if r["target"].startswith("rpoB")]
    routine = [r for r in eval_rows if r["stratum"] == "routine"]
    challenge = [r for r in eval_rows if r["stratum"] == "challenge"]
    if len(tetA) != 26 or len(rpob) != 15:
        raise SystemExit(f"target evaluable tetA={len(tetA)} rpoB={len(rpob)}")

    sol_all = subset_score("GS_AGENTIC_V4_1_SOL56_HIGH_POSTHOC", eval_rows, "sol_pred", "sol_correct")
    qwen_all = subset_score("GS_AGENTIC_V4_1_QWEN", eval_rows, "qwen_pred", "qwen_correct")
    det_all = subset_score("GS_DETERMINISTIC_V4_1", eval_rows, "gs_det_pred", "gs_det_correct")
    exh_all = subset_score("GS_EXHAUSTIVE_V4_1", eval_rows, "gs_exh_pred", "gs_exh_correct")
    vs_qwen = paired_vs(eval_rows, "sol_correct", "qwen_correct")
    vs_det = paired_vs(eval_rows, "sol_correct", "gs_det_correct")
    vs_exh = paired_vs(eval_rows, "sol_correct", "gs_exh_correct")

    extra_change = [c for c in comparisons if c["extra_sol_action_effect"] == "DECISION_CHANGE"]
    extra_nochange = [c for c in comparisons if c["extra_sol_action_effect"] == "NO_DECISION_CHANGE"]
    endpoint_changes = [c for c in comparisons if c["endpoint_changed_vs_qwen"]]

    qwen_follow = [c["qwen_n_follow_up_actions"] for c in comparisons]
    sol_follow = [c["sol_n_follow_up_actions"] for c in comparisons]
    exh_follow = [c["exhaustive_n_follow_up_actions"] for c in comparisons]
    qwen_challenge = sum(1 for c in comparisons if str(c.get("qwen_critic_disposition") or "").lower() == "challenge")
    sol_challenge = sum(1 for c in comparisons if str(c.get("sol_critic_disposition") or "").lower() == "challenge")

    total_in = sum(int(r.get("sol_input_tokens") or 0) for r in rows)
    total_out = sum(int(r.get("sol_output_tokens") or 0) for r in rows)
    total_reason = sum(int(r.get("sol_reasoning_tokens") or 0) for r in rows)
    total_cost = round(sum(float(r.get("api_cost_usd") or 0) for r in rows), 6)

    qwen_runtime = [c["qwen_runtime_seconds"] for c in comparisons if c.get("qwen_runtime_seconds") is not None]
    exh_runtime = [c["exhaustive_runtime_seconds"] for c in comparisons if c.get("exhaustive_runtime_seconds") is not None]
    sol_runtime = [c["sol_runtime_seconds"] for c in comparisons if c.get("sol_runtime_seconds") is not None]

    scoring_rows = []
    for subset, label in (
        (eval_rows, "overall"),
        (tetA, "tetA"),
        (rpob, "rpoB"),
        (routine, "routine"),
        (challenge, "challenge"),
    ):
        for name, pred, corr in (
            ("sol", "sol_pred", "sol_correct"),
            ("qwen_agentic", "qwen_pred", "qwen_correct"),
            ("gs_deterministic", "gs_det_pred", "gs_det_correct"),
            ("gs_exhaustive", "gs_exh_pred", "gs_exh_correct"),
        ):
            rec = subset_score(name, subset, pred, corr)
            rec["subset"] = label
            scoring_rows.append(rec)

    call_log_path = OUT_DIR / "SOL56_M60_CALL_LOG.jsonl"
    with call_log_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            for call in r.get("call_log") or []:
                rec = dict(call)
                rec["case_id"] = r["case_id"]
                rec["position"] = r["position"]
                if "api_key" in rec:
                    rec["api_key"] = None
                fh.write(json.dumps(rec, default=str) + "\n")

    behaviour_path = OUT_DIR / "SOL56_M60_MODEL_BEHAVIOUR.csv"
    case_path = OUT_DIR / "SOL56_M60_CASE_LEVEL.csv"
    scoring_path = OUT_DIR / "SOL56_M60_SCORING.csv"
    write_csv(behaviour_path, comparisons)
    write_csv(case_path, joined)
    write_csv(scoring_path, scoring_rows)

    hashes = verify_invariants()
    summary = {
        "kind": "SOL56_M60_SUMMARY",
        "ablation_config": SOL_ABLATION_ID,
        "POST_HOC_MODEL_ABLATION": True,
        "MANUSCRIPT_PRIMARY_VALIDATION": False,
        "PROMPTS_MODIFIED": "NO",
        "SCIENTIFIC_CORE_MODIFIED": "NO",
        "VALIDATOR_MODIFIED": "NO",
        "model": SOL_MODEL,
        "reasoning_effort": SOL_REASONING_EFFORT,
        "n_cases": 60,
        "truth_evaluable": 41,
        "truth_uncertain": 19,
        "truth_sha256": truth_meta["truth_sha256"],
        "small_preflight_manifest_sha256": SMALL_MANIFEST_SHA256,
        "prediction_lock_sha256": pred_sha,
        "scientific_invariant_hashes": hashes,
        "scientific_core_hash_manuscript": EXPECTED_CORE,
        "sol": sol_all,
        "qwen_agentic": qwen_all,
        "gs_deterministic": det_all,
        "gs_exhaustive": exh_all,
        "sol_vs_qwen": vs_qwen,
        "sol_vs_det": vs_det,
        "sol_vs_exhaustive": vs_exh,
        "subsets": {
            "tetA_sol": subset_score("sol", tetA, "sol_pred", "sol_correct"),
            "rpoB_sol": subset_score("sol", rpob, "sol_pred", "sol_correct"),
            "routine_sol": subset_score("sol", routine, "sol_pred", "sol_correct"),
            "challenge_sol": subset_score("sol", challenge, "sol_pred", "sol_correct"),
        },
        "model_behaviour": {
            "planner_action_changed_vs_qwen": sum(c["planner_action_changed_vs_qwen"] for c in comparisons),
            "critic_behaviour_changed_vs_qwen": sum(c["critic_behaviour_changed_vs_qwen"] for c in comparisons),
            "final_endpoint_changed_vs_qwen": sum(c["endpoint_changed_vs_qwen"] for c in comparisons),
            "follow_up_action_count_changed": sum(c["follow_up_action_count_changed"] for c in comparisons),
            "endpoint_changed_vs_gs_deterministic": sum(c["endpoint_changed_vs_gs_deterministic"] for c in comparisons),
            "endpoint_different_from_gs_exhaustive": sum(c["endpoint_different_from_gs_exhaustive"] for c in comparisons),
            "qwen_follow_up_actions_mean": mean(qwen_follow),
            "qwen_follow_up_actions_median": median(qwen_follow),
            "qwen_follow_up_actions_total": int(sum(qwen_follow)),
            "sol_follow_up_actions_mean": mean(sol_follow),
            "sol_follow_up_actions_median": median(sol_follow),
            "sol_follow_up_actions_total": int(sum(sol_follow)),
            "exhaustive_follow_up_actions_mean": mean(exh_follow),
            "exhaustive_follow_up_actions_median": median(exh_follow),
            "exhaustive_follow_up_actions_total": int(sum(exh_follow)),
            "qwen_critic_challenge_rate": qwen_challenge / 60,
            "sol_critic_challenge_rate": sol_challenge / 60,
            "qwen_critic_challenges": qwen_challenge,
            "sol_critic_challenges": sol_challenge,
            "extra_sol_actions_DECISION_CHANGE": len(extra_change),
            "extra_sol_actions_NO_DECISION_CHANGE": len(extra_nochange),
            "endpoint_change_cases": [
                {
                    "position": c["position"],
                    "case_id": c["case_id"],
                    "reason": c["validator_state_change_reason"],
                }
                for c in endpoint_changes
            ],
        },
        "cost_latency": {
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_reasoning_tokens": total_reason,
            "total_api_cost_usd": total_cost,
            "median_planner_latency": median([r.get("sol_planner_latency") for r in rows]),
            "median_critic_latency": median([r.get("sol_critic_latency") for r in rows]),
            "median_sol_case_runtime": median(sol_runtime),
            "median_qwen_case_runtime": median(qwen_runtime),
            "median_exhaustive_case_runtime": median(exh_runtime),
            "sol_deterministic_analysis_count": int(sum(sol_follow)),
            "qwen_deterministic_analysis_count": int(sum(qwen_follow)),
            "exhaustive_deterministic_analysis_count": int(sum(exh_follow)),
        },
        "parse_failures": sum(int(r.get("parse_failures") or 0) for r in rows),
        "adapter_retries": sum(int(r.get("retry_count") or 0) for r in rows),
        "created_utc": utc_now(),
    }
    write_json(OUT_DIR / "SOL56_M60_SUMMARY.json", summary)

    md = []
    md.append("# SOL56 full M60 post-hoc model ablation\n")
    md.append("POST_HOC_MODEL_ABLATION = TRUE. MANUSCRIPT_PRIMARY_VALIDATION = FALSE.\n")
    md.append("The only variable relative to original Agentic M60 is qwen3:4b → gpt-5.6-sol, reasoning=high.\n")
    md.append("## Phase 1 — blinded model comparison\n")
    md.append(f"- Planner action changed vs Qwen: {summary['model_behaviour']['planner_action_changed_vs_qwen']} / 60")
    md.append(f"- Critic behaviour changed vs Qwen: {summary['model_behaviour']['critic_behaviour_changed_vs_qwen']} / 60")
    md.append(f"- Follow-up action count changed: {summary['model_behaviour']['follow_up_action_count_changed']} / 60")
    md.append(f"- Final endpoint changed vs Qwen: {summary['model_behaviour']['final_endpoint_changed_vs_qwen']} / 60")
    md.append(f"- Final endpoint changed vs GS-Det: {summary['model_behaviour']['endpoint_changed_vs_gs_deterministic']} / 60")
    md.append(f"- Final endpoint differs from GS-Exhaustive: {summary['model_behaviour']['endpoint_different_from_gs_exhaustive']} / 60")
    md.append("\n## Phase 2 — post-hoc truth join\n")
    md.append(f"Truth SHA256: `{truth_meta['truth_sha256']}`")
    md.append("Truth-evaluable N = 41. TRUTH_UNCERTAIN n = 19 remain descriptive only.\n")
    md.append(f"- Sol: {sol_all['correct_over_n']} accuracy {sol_all['accuracy']:.3f} Wilson 95% CI {sol_all['wilson_ci']}")
    md.append(f"- Qwen Agentic: {qwen_all['correct_over_n']}")
    md.append(f"- GS-Deterministic: {det_all['correct_over_n']}")
    md.append(f"- GS-Exhaustive: {exh_all['correct_over_n']}")
    md.append(f"- tetA Sol: {summary['subsets']['tetA_sol']['correct_over_n']}")
    md.append(f"- rpoB Sol: {summary['subsets']['rpoB_sol']['correct_over_n']}")
    md.append(f"- routine Sol: {summary['subsets']['routine_sol']['correct_over_n']}")
    md.append(f"- challenge Sol: {summary['subsets']['challenge_sol']['correct_over_n']}")
    md.append("\n## Sol vs Qwen Agentic\n")
    md.append(f"- Qwen wrong → Sol correct: {vs_qwen['corrections']}")
    md.append(f"- Qwen correct → Sol wrong: {vs_qwen['degradations']}")
    md.append(f"- Net corrections: {vs_qwen['net']}")
    md.append(f"- Accuracy difference: {fmt_pct_pts(vs_qwen['accuracy_difference'])}")
    md.append(f"- Paired bootstrap 95% CI (10,000; seed {BOOTSTRAP_SEED}): {vs_qwen['paired_bootstrap_95_ci_text']}")
    md.append(f"- Exact McNemar P: {vs_qwen['mcnemar_p'] if vs_qwen['mcnemar_p'] is not None else 'NA'}")
    md.append("\n## Sol vs GS-Deterministic\n")
    md.append(f"- Det wrong → Sol correct: {vs_det['corrections']}")
    md.append(f"- Det correct → Sol wrong: {vs_det['degradations']}")
    md.append(f"- Net: {vs_det['net']}")
    md.append("\n## Sol vs GS-Exhaustive\n")
    md.append(f"- Exhaustive wrong → Sol correct: {vs_exh['corrections']}")
    md.append(f"- Exhaustive correct → Sol wrong: {vs_exh['degradations']}")
    md.append(f"- Net: {vs_exh['net']}")
    md.append("\n## Model behaviour\n")
    md.append(f"- Qwen follow-up actions mean/median/total: {mean(qwen_follow)} / {median(qwen_follow)} / {int(sum(qwen_follow))}")
    md.append(f"- Sol follow-up actions mean/median/total: {mean(sol_follow)} / {median(sol_follow)} / {int(sum(sol_follow))}")
    md.append(f"- Exhaustive follow-up actions mean/median/total: {mean(exh_follow)} / {median(exh_follow)} / {int(sum(exh_follow))}")
    md.append(f"- Qwen critic challenges: {qwen_challenge} / 60")
    md.append(f"- Sol critic challenges: {sol_challenge} / 60")
    md.append(f"- Extra Sol actions → DECISION_CHANGE: {len(extra_change)}")
    md.append(f"- Extra Sol actions → NO_DECISION_CHANGE: {len(extra_nochange)}")
    if endpoint_changes:
        md.append("\n### Endpoint changes vs Qwen and new evidence consumed by the frozen validator\n")
        for c in endpoint_changes:
            md.append(f"- Position {c['position']} `{c['case_id']}`: {c['validator_state_change_reason']}")
    else:
        md.append("\nNo Sol endpoint differed from locked Qwen Agentic on the 60-case cohort.\n")
    md.append("\n## Cost and latency\n")
    md.append(f"- Total input tokens: {total_in}")
    md.append(f"- Total output tokens: {total_out}")
    md.append(f"- Total reasoning tokens: {total_reason}")
    md.append(f"- Total API cost: ${total_cost:.6f}")
    md.append(f"- Median Planner latency: {summary['cost_latency']['median_planner_latency']}")
    md.append(f"- Median Critic latency: {summary['cost_latency']['median_critic_latency']}")
    md.append(f"- Median Sol case runtime: {summary['cost_latency']['median_sol_case_runtime']}")
    md.append(f"- Median Qwen Agentic case runtime: {summary['cost_latency']['median_qwen_case_runtime']}")
    md.append(f"- Median GS-Exhaustive case runtime: {summary['cost_latency']['median_exhaustive_case_runtime']}")
    md.append("LLM latency and deterministic-analysis count are separate efficiency concepts.")
    md.append("\nPROMPTS MODIFIED: NO")
    md.append("SCIENTIFIC CORE MODIFIED: NO")
    md.append("VALIDATOR MODIFIED: NO")
    (OUT_DIR / "SOL56_M60_RESULTS.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    hashed_names = [name for name in OUTPUT_NAMES if name != "SOL56_M60_MANIFEST.json"]
    file_hashes = {name: sha256_file(OUT_DIR / name) for name in hashed_names}
    manifest = {
        "kind": "SOL56_M60_MANIFEST",
        "ablation_config": SOL_ABLATION_ID,
        "POST_HOC_MODEL_ABLATION": True,
        "MANUSCRIPT_PRIMARY_VALIDATION": False,
        "model": SOL_MODEL,
        "reasoning_effort": SOL_REASONING_EFFORT,
        "created_utc": utc_now(),
        "n_cases": 60,
        "reused_positions": list(REUSE_POSITIONS),
        "small_preflight_manifest_sha256": SMALL_MANIFEST_SHA256,
        "truth_sha256": truth_meta["truth_sha256"],
        "prediction_lock_sha256": pred_sha,
        "scientific_invariant_hashes": hashes,
        "PROMPTS_MODIFIED": "NO",
        "SCIENTIFIC_CORE_MODIFIED": "NO",
        "VALIDATOR_MODIFIED": "NO",
        "files": file_hashes,
    }
    body = json.dumps(manifest, indent=2, default=str) + "\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    manifest["manifest_sha256"] = digest
    write_json(OUT_DIR / "SOL56_M60_MANIFEST.json", manifest)
    sidecar_sha = sha256_file(OUT_DIR / "SOL56_M60_MANIFEST.json")
    write_json(
        OUT_DIR / "SOL56_M60_MANIFEST.json.sha256.json",
        {
            "path": "manuscript_benchmark/SOL56_FULL_ABLATION/SOL56_M60_MANIFEST.json",
            "sha256": sidecar_sha,
            "hashed_utc": utc_now(),
            "POST_HOC_MODEL_ABLATION": True,
            "MANUSCRIPT_PRIMARY_VALIDATION": False,
        },
    )
    update_progress(
        completed_positions=list(ALL_POSITIONS),
        truth_opened=True,
        accuracy_scored=True,
        phase="complete",
        manifest_sha256=sidecar_sha,
    )
    print_stop(summary, sidecar_sha)
    return summary


def print_stop(summary: dict, manifest_sha: str) -> None:
    mb = summary["model_behaviour"]
    cl = summary["cost_latency"]
    vs = summary["sol_vs_qwen"]
    vd = summary["sol_vs_det"]
    print(
        "\n".join(
            [
                "FULL SOL ABLATION COMPLETE: YES",
                "CASES: 60 / 60",
                "TRUTH-EVALUABLE: 41",
                f"SOL: {summary['sol']['correct_over_n']}",
                "QWEN AGENTIC: 33 / 41",
                "GS-DETERMINISTIC: 33 / 41",
                "GS-EXHAUSTIVE: 33 / 41",
                f"SOL vs QWEN: CORRECTIONS {vs['corrections']} DEGRADATIONS {vs['degradations']} NET {vs['net']}",
                f"SOL vs DET: CORRECTIONS {vd['corrections']} DEGRADATIONS {vd['degradations']} NET {vd['net']}",
                f"SOL vs QWEN ACCURACY DIFFERENCE: {fmt_pct_pts(vs['accuracy_difference'])}",
                f"PAIRED BOOTSTRAP 95% CI: {vs['paired_bootstrap_95_ci_text']}",
                f"MCNEMAR P: {vs['mcnemar_p'] if vs['mcnemar_p'] is not None else 'NA'}",
                f"PLANNER ACTION CHANGED VS QWEN: {mb['planner_action_changed_vs_qwen']} / 60",
                f"CRITIC BEHAVIOUR CHANGED VS QWEN: {mb['critic_behaviour_changed_vs_qwen']} / 60",
                f"FINAL ENDPOINT CHANGED VS QWEN: {mb['final_endpoint_changed_vs_qwen']} / 60",
                f"QWEN FOLLOW-UP ACTIONS: mean {mb['qwen_follow_up_actions_mean']} median {mb['qwen_follow_up_actions_median']} total {mb['qwen_follow_up_actions_total']}",
                f"SOL FOLLOW-UP ACTIONS: mean {mb['sol_follow_up_actions_mean']} median {mb['sol_follow_up_actions_median']} total {mb['sol_follow_up_actions_total']}",
                f"EXHAUSTIVE FOLLOW-UP ACTIONS: {mb['exhaustive_follow_up_actions_total']}",
                f"SOL TOTAL API COST: ${cl['total_api_cost_usd']:.6f}",
                f"SOL MEDIAN PLANNER LATENCY: {cl['median_planner_latency']}",
                f"SOL MEDIAN CRITIC LATENCY: {cl['median_critic_latency']}",
                f"SOL MEDIAN CASE RUNTIME: {cl['median_sol_case_runtime']}",
                "PROMPTS MODIFIED: NO",
                "SCIENTIFIC CORE MODIFIED: NO",
                "VALIDATOR MODIFIED: NO",
                "POST_HOC_MODEL_ABLATION: TRUE",
                f"MANIFEST SHA256: {manifest_sha}",
                "STOP.",
            ]
        ),
        flush=True,
    )


def preflight_fastas() -> None:
    missing = []
    for pos in ALL_POSITIONS:
        rec = load_case(pos)
        try:
            solver_fasta(rec)
        except SystemExit:
            missing.append((pos, rec["accession"]))
    if missing:
        raise SystemExit(f"STOP missing frozen solver FASTAs: {missing}")


def run_remaining() -> None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise SystemExit("OPENAI_API_KEY is not set")
    verify_invariants()
    small = verify_small_preflight()
    print(json.dumps({"event": "small_preflight_verified", **small}, indent=2), flush=True)
    preflight_fastas()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    update_progress(phase="running", small_preflight=small)

    for pos in REUSE_POSITIONS:
        if lock_path(pos).exists():
            print(f"SKIP locked reused position {pos}", flush=True)
            continue
        load_reused_case(pos)

    for pos in ALL_POSITIONS:
        if lock_path(pos).exists():
            continue
        print(f"RUN position {pos}", flush=True)
        run_one_position(pos)

    rows = load_all_locks()
    if len(rows) != 60:
        raise SystemExit(f"STOP incomplete cohort {len(rows)} / 60")
    analyze(rows)


def main() -> int:
    args = sys.argv[1:]
    if args == ["--analyze-only"]:
        verify_invariants()
        verify_small_preflight()
        rows = load_all_locks()
        analyze(rows)
        return 0
    try:
        run_remaining()
        return 0
    except Exception:
        traceback.print_exc()
        n = len(list(LOCKS_DIR.glob("position_*.json"))) if LOCKS_DIR.exists() else 0
        print(f"FULL SOL ABLATION COMPLETE: NO\nCASES: {n} / 60\nSTOP.", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
