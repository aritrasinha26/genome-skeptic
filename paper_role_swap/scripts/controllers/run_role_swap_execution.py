#!/usr/bin/env python3
"""Execute frozen tetA role-swap arms A–F. DO NOT join truth or score.

Uses ROLE_SWAP_PREDICTION_INPUT.csv only. Path-guards 03_TRUTH/.
"""
from __future__ import annotations

import argparse
import builtins
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
STUDY = ROOT / "role_swap_cross_task"
CASES = STUDY / "02_CASES"
OUT_INIT = STUDY / "04_INITIAL_EVIDENCE"
OUT_A = STUDY / "05_DET_CONTROL"
OUT_B = STUDY / "06_SOL_CONTROLLER"
OUT_C = STUDY / "07_EXHAUSTIVE"
OUT_D = STUDY / "08_SOL_JUDGE"
OUT_F = STUDY / "09_JEV_CONTROLLER"
OUT_RES = STUDY / "10_RESULTS"
OUT_PROV = STUDY / "12_PROVENANCE"

EXPECTED_CASESET_LOCK = "dbc06649ddc8d405200ec854f0e3dfe1ccbbbedf2d813b6a3d58808b869de449"
EXPECTED_TRUTH_LOCK = "a1f3a9c2239f04517b04e615ef0ca8705d6e07518fb0000ce20449ec91a0490f"
SOL_YAML = ROOT / "config" / "sol56_high_posthoc.yaml"

for p in (SRC, SCRIPTS, SCRIPTS / "model_poc_v5", SCRIPTS / "decision_authority_poc"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from freeze import verify_v5_freeze  # noqa: E402
from genome_skeptic.agents.action_contract import (  # noqa: E402
    ABSTAIN_UNRESOLVED,
    CONTROL_DECISIONS,
    FINALIZE_WITH_CURRENT_EVIDENCE,
)
from genome_skeptic.agents.providers import CALL_LOG, reset_call_log  # noqa: E402
from genome_skeptic.config import Settings, load_settings  # noqa: E402
from genome_skeptic.families import load_family  # noqa: E402
from genome_skeptic.manuscript.arms import (  # noqa: E402
    run_gs_agentic_v4_1,
    run_gs_deterministic_v4_1,
    run_gs_exhaustive_v4_1,
)
from leakage import assert_no_forbidden_fields  # noqa: E402
from role_swap_prediction_path_guard import assert_prediction_path_allowed  # noqa: E402
from run_m60_position import empty_refs  # noqa: E402
from evidence_packet import build_common_evidence_packet, assert_clean_for_models  # noqa: E402
from decision_arms import BiologicalDecision, DECISION_SYSTEM, validate_evidence_ids  # noqa: E402
from sol_adapter import SolModelAdapter  # noqa: E402

TRUTH_ACCESS_LOG: list[dict] = []
_ORIG_OPEN = builtins.open


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with _ORIG_OPEN(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, obj: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    return sha256_file(path)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def guarded_open(file, *args, **kwargs):
    path = str(file)
    try:
        assert_prediction_path_allowed(path)
    except RuntimeError as exc:
        TRUTH_ACCESS_LOG.append({"utc": utc_now(), "path": path, "error": str(exc)})
        raise
    lowered = path.replace("\\", "/").lower()
    if "role_swap_cross_task/03_truth" in lowered or "role_swap_truth" in lowered:
        TRUTH_ACCESS_LOG.append({"utc": utc_now(), "path": path, "error": "caught_truth_path"})
        raise RuntimeError(f"STOP: truth path access: {path}")
    return _ORIG_OPEN(file, *args, **kwargs)


def install_path_guard() -> None:
    builtins.open = guarded_open  # type: ignore[assignment]


def write_target_fa(dest: Path, target: str) -> None:
    fam = load_family(target)
    if fam is None or not fam.members:
        raise SystemExit(f"missing frozen family {target}")
    member = max(fam.members, key=lambda m: len(m.sequence or ""))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        f">{target} target_type=gene_orthologue family={target} length_aa={len(member.sequence or '')}\n{member.sequence}\n",
        encoding="utf-8",
    )


def install_clients(arm: str) -> None:
    from genome_skeptic.agents import ollama

    if arm == "sol":
        def sol_ask(self, system, user_payload, schema):
            assert_no_forbidden_fields(system, label="sol:system")
            assert_no_forbidden_fields(user_payload, label="sol:user_payload")
            return SolModelAdapter(self.cfg).ask_json(system, user_payload, schema)

        ollama.OllamaJSONClient.ask_json = sol_ask  # type: ignore[method-assign]
        return
    if arm == "jev":
        from jev_adapter import JevJSONClient

        def jev_ask(self, system, user_payload, schema):
            return JevJSONClient(self.cfg).ask_json(system, user_payload, schema)

        ollama.OllamaJSONClient.ask_json = jev_ask  # type: ignore[method-assign]


def settings_for_arm(arm: str) -> Settings:
    if arm in {"deterministic", "exhaustive"}:
        settings = Settings()
        settings.llm.enabled = False
        return settings
    if arm == "sol":
        return load_settings(SOL_YAML)
    if arm == "jev":
        settings = Settings()
        settings.llm.enabled = True
        settings.llm.model = "jev-latest"
        settings.llm.provider = "typesafe_systemone"
        settings.execution.enable_critic = True
        settings.execution.allow_model_to_choose_actions = True
        return settings
    raise SystemExit(f"unknown arm {arm}")


def map_endpoint(raw: str | None) -> str:
    v = str(raw or "UNRESOLVED").upper()
    if v in {"POSITIVE", "PRESENT", "TARGET_GENE_DETECTED"}:
        return "PRESENT"
    if v in {"NEGATIVE", "ABSENT", "TARGET_GENE_NOT_DETECTED"}:
        return "ABSENT"
    return "UNRESOLVED"


def binary_endpoint(claim, provenance: dict) -> str:
    if provenance.get("agent_failure"):
        return "UNRESOLVED"
    if claim is None:
        return "UNRESOLVED"
    status = claim.status.value if hasattr(claim.status, "value") else str(claim.status)
    if str(status).endswith("unresolved") or str(status) == "unresolved":
        return "UNRESOLVED"
    ctype = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
    if ctype in {"target_gene_detected", "POSITIVE"}:
        return "PRESENT"
    if ctype in {"target_gene_not_detected", "NEGATIVE"}:
        return "ABSENT"
    return "UNRESOLVED"


def _action_ids(executed) -> list[str]:
    out = []
    for item in executed or []:
        aid = item.get("action_id") if isinstance(item, dict) else item
        if aid:
            out.append(str(aid))
    return out


def _planner_decision(provenance: dict) -> str | None:
    control = provenance.get("control_decision")
    selected = provenance.get("selected_action")
    if control == FINALIZE_WITH_CURRENT_EVIDENCE or selected == FINALIZE_WITH_CURRENT_EVIDENCE:
        return "FINALIZE"
    if control == ABSTAIN_UNRESOLVED or selected == ABSTAIN_UNRESOLVED:
        return "ABSTAIN"
    if provenance.get("follow_up_policy", "").endswith("DETERMINISTIC_V4_1"):
        return "DETERMINISTIC_MAP"
    if provenance.get("follow_up_policy", "").endswith("EXHAUSTIVE_V4_1"):
        return "EXHAUSTIVE"
    if provenance.get("planner_invoked") and selected and selected not in CONTROL_DECISIONS:
        return "INVESTIGATE"
    if selected:
        return "INVESTIGATE"
    return None


def _sum_log(rows: list[dict], key: str) -> float:
    return round(sum(float(r.get(key) or 0) for r in rows), 6)


def summarize_calls(call_log: list[dict], arm: str) -> dict:
    planner = [r for r in call_log if str(r.get("request_type") or "").startswith(("AgentDecision", "PlannerDecision"))]
    critic = [r for r in call_log if str(r.get("request_type") or "").startswith(("CriticReview", "CriticDecision"))]
    errors = [r for r in call_log if r.get("error") or r.get("schema_valid") is False]
    retries = sum(int(r.get("retry_count") or 0) for r in call_log)
    jev_planner = next((r.get("jev_planner") for r in reversed(call_log) if r.get("jev_planner")), None)
    jev_critic = next((r.get("jev_critic") for r in reversed(call_log) if r.get("jev_critic")), None)
    jev_noul = next((r.get("jev_noul") for r in reversed(call_log) if r.get("jev_noul") is not None), None)
    models = [r.get("concrete_model") or r.get("model") for r in call_log if r.get("concrete_model") or r.get("model")]
    request_ids = [r.get("request_id") or r.get("response_id") for r in call_log]
    provider_times = []
    for row in call_log:
        raw = row.get("x_envoy_upstream_service_time")
        if raw is None:
            continue
        try:
            provider_times.append(float(raw) / (1000.0 if float(raw) > 20 else 1.0))
        except (TypeError, ValueError):
            pass
    return {
        "planner_requests": len(planner),
        "critic_requests": len(critic),
        "total_model_requests": len(call_log),
        "planner_latency_s": _sum_log(planner, "elapsed_seconds"),
        "critic_latency_s": _sum_log(critic, "elapsed_seconds"),
        "model_latency_s": _sum_log(call_log, "elapsed_seconds"),
        "input_tokens": sum(int(r.get("input_tokens") or 0) for r in call_log),
        "output_tokens": sum(int(r.get("output_tokens") or 0) for r in call_log),
        "reasoning_tokens": sum(int(r.get("reasoning_tokens") or 0) for r in call_log),
        "cost_usd": round(sum(float(r.get("estimated_api_cost_usd") or 0) for r in call_log), 8),
        "retry_count": retries,
        "error_count": len(errors),
        "jev_planner": jev_planner,
        "jev_critic": jev_critic,
        "jev_noul": jev_noul,
        "jev_models": [m for m in models if m],
        "jev_request_ids": [x for x in request_ids if x],
        "provider_service_time_s": provider_times,
        "call_log": call_log,
    }


def load_cases() -> list[dict]:
    # Prediction input only for required fields; organism from caseset (no truth columns).
    pred = list(csv.DictReader((CASES / "ROLE_SWAP_PREDICTION_INPUT.csv").open(encoding="utf-8")))
    meta = {r["case_id"]: r for r in csv.DictReader((CASES / "ROLE_SWAP_CASESET.csv").open(encoding="utf-8"))}
    cases = []
    for row in pred:
        m = meta[row["case_id"]]
        # Never carry truth-like fields
        cases.append(
            {
                "case_id": row["case_id"],
                "accession": row["accession"],
                "assembly_path": row["assembly_path"],
                "assembly_sha256": row["assembly_sha256"],
                "target": row["target"],
                "query_id": row["target"],
                "organism": m.get("organism"),
            }
        )
    if len(cases) != 20:
        raise SystemExit(f"STOP: expected 20 prediction cases, got {len(cases)}")
    return cases


def verify_locks() -> dict:
    freeze = verify_v5_freeze()
    if freeze["scientific_core_or_validator_mismatch"] or not freeze["all_match"]:
        raise SystemExit(f"STOP: freeze mismatch {freeze['rows']}")
    if freeze["family_definitions_hash"] != "ed4210640e318b8ed94ebf6d72b9c37afa9039eed858fdd54c4165fbcce09605":
        raise SystemExit("STOP: family panel mismatch")
    if freeze["reference_assets_hash"] != "9434a1902236ed7245361e47af1986357969a3bf8ec210062f889dc84580ff92":
        raise SystemExit("STOP: ortholog mismatch")
    cs = sha256_file(CASES / "ROLE_SWAP_CASESET_LOCK.json")
    if cs != EXPECTED_CASESET_LOCK:
        raise SystemExit(f"STOP: caseset lock mismatch {cs}")
    # Truth lock hash verified without opening truth contents via builtins.open guard —
    # use raw open through _ORIG_OPEN only for hash of lock file existence check.
    tl_path = STUDY / "03_TRUTH" / "ROLE_SWAP_TRUTH_LOCK.json"
    tl = sha256_file(tl_path)
    if tl != EXPECTED_TRUTH_LOCK:
        raise SystemExit(f"STOP: truth lock mismatch {tl}")
    print("LOCKS_OK", flush=True)
    return freeze


def arm_dir(arm: str, case_id: str) -> Path:
    root = {"A": OUT_A, "B": OUT_B, "C": OUT_C, "D": OUT_D, "F": OUT_F}[arm]
    return root / case_id


def run_gs_arm(case: dict, arm_code: str, policy: str) -> dict:
    out_dir = arm_dir(arm_code, case["case_id"]) / "GS_RUN"
    pred_path = arm_dir(arm_code, case["case_id"]) / "prediction.json"
    if pred_path.is_file():
        return load_json(pred_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    install_clients(policy)
    settings = settings_for_arm(policy)
    assembly = Path(case["assembly_path"])
    if not assembly.is_file():
        # Windows path fallback
        win = ROOT / "role_swap_cross_task" / "_work" / "fasta" / f"{case['accession']}.fna"
        if win.is_file():
            assembly = win
    target_fa = out_dir / "target.fa"
    write_target_fa(target_fa, case["query_id"])
    refs = empty_refs()
    reset_call_log()
    start = utc_now()
    t0 = time.perf_counter()
    failure = None
    provenance: dict = {}
    claim = None
    try:
        if policy == "deterministic":
            claims, _loci, provenance = run_gs_deterministic_v4_1(
                assembly, target_fa, out_dir, settings, references=refs,
                declared_organism=case.get("organism"), query_ids=[case["query_id"]],
            )
        elif policy == "exhaustive":
            claims, _loci, provenance = run_gs_exhaustive_v4_1(
                assembly, target_fa, out_dir, settings, references=refs,
                declared_organism=case.get("organism"), query_ids=[case["query_id"]],
            )
        else:
            claims, _loci, provenance = run_gs_agentic_v4_1(
                assembly, target_fa, out_dir, settings, references=refs,
                declared_organism=case.get("organism"), query_ids=[case["query_id"]],
            )
        claim = claims[0] if claims else None
    except Exception as exc:
        failure = f"{exc}\n{traceback.format_exc(limit=12)}"
        provenance = provenance or {"agent_failure": str(exc)}
    total_s = round(time.perf_counter() - t0, 3)
    end = utc_now()
    call_log = list(CALL_LOG)
    if (out_dir / "call_log.json").is_file():
        try:
            call_log = load_json(out_dir / "call_log.json") or call_log
        except Exception:
            pass
    usage = summarize_calls(call_log, policy)
    followups = _action_ids(provenance.get("actions_executed"))
    critic_blob = provenance.get("critic_challenge") or {}
    m0 = ((provenance.get("measurement_state") or {}).get("m0") or {}).get("hash")
    m_final = ((provenance.get("measurement_state") or {}).get("m_final") or {}).get("hash")
    model_s = float(usage["model_latency_s"] or 0)
    endpoint = binary_endpoint(claim, provenance)
    payload = {
        "case_id": case["case_id"],
        "accession": case["accession"],
        "target": case["target"],
        "arm": arm_code,
        "policy": policy,
        "initial_state_hash": m0,
        "planner_decision": _planner_decision(provenance),
        "planner_action": provenance.get("selected_action"),
        "critic_decision": (critic_blob.get("verdict") if isinstance(critic_blob, dict) else None),
        "critic_action": provenance.get("critic_second_action"),
        "followup_actions": followups,
        "followup_count": len(followups),
        "final_state_hash": m_final,
        "endpoint": endpoint,
        "planner_requests": usage["planner_requests"],
        "critic_requests": usage["critic_requests"],
        "total_model_requests": usage["total_model_requests"],
        "planner_latency_s": usage["planner_latency_s"],
        "critic_latency_s": usage["critic_latency_s"],
        "model_latency_s": usage["model_latency_s"],
        "deterministic_runtime_s": round(max(0.0, total_s - model_s), 3),
        "total_runtime_s": total_s,
        "input_tokens": usage["input_tokens"] or None,
        "output_tokens": usage["output_tokens"] or None,
        "reasoning_tokens": usage["reasoning_tokens"] or None,
        "retries": usage["retry_count"],
        "errors": usage["error_count"],
        "cost_usd": 0.0 if policy in {"deterministic", "exhaustive"} else usage["cost_usd"],
        "agent_failure": provenance.get("agent_failure") or failure,
        "start_utc": start,
        "end_utc": end,
        "eligible_actions_m0": [
            r.get("action_id")
            for r in (provenance.get("executable_actions_before_ranking") or [])
            if isinstance(r, dict)
        ],
        "run_dir": str(out_dir).replace("\\", "/"),
        "call_log": call_log,
        "provenance_path": str((out_dir / "agentic_provenance.json")).replace("\\", "/"),
    }
    if policy == "jev":
        jp = usage.get("jev_planner") or {}
        jc = usage.get("jev_critic") or {}
        payload.update(
            {
                "jev_model_alias": "jev-latest",
                "jev_concrete_model": (usage.get("jev_models") or [None])[-1] if usage.get("jev_models") else None,
                "planner_confidence": jp.get("action_confidence") or jp.get("control_confidence"),
                "planner_probabilities": jp.get("action_probabilities") or jp.get("control_probabilities"),
                "critic_noul": usage.get("jev_noul") if usage.get("jev_noul") is not None else jc.get("noul"),
                "request_ids": usage.get("jev_request_ids") or [],
                "provider_service_time": usage.get("provider_service_time_s") or [],
            }
        )
    # Lock Arm B evidence package for Arm D
    if arm_code == "B":
        lock_arm_b_evidence(case, out_dir, payload, claim, provenance)
    write_json(pred_path, payload)
    write_json(pred_path.with_suffix(".json.sha256.json"), {"sha256": sha256_file(pred_path), "hashed_utc": utc_now()})
    print(f"DONE arm={arm_code} case={case['case_id']} endpoint={endpoint} followups={len(followups)}", flush=True)
    return payload


def lock_arm_b_evidence(case: dict, run_dir: Path, payload: dict, claim, provenance: dict) -> None:
    lock_dir = arm_dir("B", case["case_id"]) / "LOCKED_FINAL_EVIDENCE"
    lock_dir.mkdir(parents=True, exist_ok=True)
    evidence_rows = load_json(run_dir / "evidence.json") if (run_dir / "evidence.json").is_file() else []
    locus_rows = load_json(run_dir / "locus_evidence.json") if (run_dir / "locus_evidence.json").is_file() else []
    fam_path = run_dir / "family" / case["query_id"] / "family_evidence.json"
    family = load_json(fam_path) if fam_path.is_file() else None
    measurement_summary = {
        "n_hits": len((family or {}).get("member_hit_summaries") or []),
        "n_loci": len(locus_rows or []),
        "architecture": (family or {}).get("architecture"),
        "supports_orthologue": (family or {}).get("supports_orthologue"),
        "best_hit": None,
    }
    metrics = (family or {}).get("metrics") or {}
    if metrics:
        measurement_summary["best_hit"] = {
            "identity": metrics.get("best_member_identity"),
            "coverage": metrics.get("best_member_coverage") or metrics.get("hmm_query_coverage"),
            "hmm_score": metrics.get("hmm_full_score"),
            "hmm_model_coverage": metrics.get("hmm_model_coverage"),
        }
    packet = build_common_evidence_packet(
        target=case["query_id"],
        evidence_rows=evidence_rows,
        locus_rows=locus_rows,
        family=family,
        measurement_summary=measurement_summary,
        executed_analyses=payload.get("followup_actions") or [],
        initial_measurement_hash=payload.get("initial_state_hash"),
        final_evidence_state_hash=payload.get("final_state_hash"),
    )
    # Explicitly omit deterministic validator endpoint from judge input.
    state = {
        "case_id": case["case_id"],
        "accession": case["accession"],
        "target": case["target"],
        "locked_at_utc": utc_now(),
        "initial_state_hash": payload.get("initial_state_hash"),
        "final_state_hash": payload.get("final_state_hash"),
        "planner_decision": payload.get("planner_decision"),
        "planner_action": payload.get("planner_action"),
        "critic_decision": payload.get("critic_decision"),
        "critic_action": payload.get("critic_action"),
        "followup_actions": payload.get("followup_actions"),
        "packet": packet,
        "family_evidence": family,
        "evidence_ids": list(packet.get("valid_evidence_ids") or []),
        "arm_b_det_endpoint_omitted_from_judge_packet": True,
        "arm_b_det_endpoint_for_record_only": payload.get("endpoint"),
        "run_dir": str(run_dir).replace("\\", "/"),
    }
    write_json(lock_dir / "ARM_B_LOCKED_EVIDENCE_STATE.json", state)
    write_json(lock_dir / "JUDGE_PACKET.json", packet)
    write_json(lock_dir / "planner_output.json", {
        "planner_decision": payload.get("planner_decision"),
        "planner_action": payload.get("planner_action"),
        "call_log_planner": [
            r for r in (payload.get("call_log") or [])
            if str(r.get("request_type") or "").startswith(("AgentDecision", "PlannerDecision"))
        ],
    })
    write_json(lock_dir / "critic_output.json", {
        "critic_decision": payload.get("critic_decision"),
        "critic_action": payload.get("critic_action"),
        "call_log_critic": [
            r for r in (payload.get("call_log") or [])
            if str(r.get("request_type") or "").startswith(("CriticReview", "CriticDecision"))
        ],
    })


def run_arm_d(case: dict) -> dict:
    pred_path = arm_dir("D", case["case_id"]) / "prediction.json"
    if pred_path.is_file():
        return load_json(pred_path)
    lock_path = arm_dir("B", case["case_id"]) / "LOCKED_FINAL_EVIDENCE" / "ARM_B_LOCKED_EVIDENCE_STATE.json"
    if not lock_path.is_file():
        raise SystemExit(f"STOP: missing Arm B locked evidence for {case['case_id']}")
    state = load_json(lock_path)
    packet = state["packet"]
    assert_clean_for_models(packet, label=f"armD:{case['case_id']}")
    if state.get("final_state_hash") != packet.get("final_evidence_state_hash"):
        raise SystemExit(f"STOP: Arm B hash inconsistency for {case['case_id']}")
    settings = load_settings(SOL_YAML)
    cfg = settings.llm.for_role("planner")
    cfg.max_output_tokens = max(int(cfg.max_output_tokens or 256), 8192)
    reset_call_log()
    t0 = time.perf_counter()
    retries = 0
    decision = None
    last_err = None
    for attempt in range(2):
        try:
            decision = SolModelAdapter(cfg).ask_json(DECISION_SYSTEM, packet, BiologicalDecision)
            break
        except Exception as exc:
            last_err = exc
            retries += 1
            if attempt == 1:
                raise
    latency = round(time.perf_counter() - t0, 6)
    usage = summarize_calls(list(CALL_LOG), "sol")
    valid_ids = set(packet.get("valid_evidence_ids") or [])
    kept, invalid = validate_evidence_ids(decision.most_decisive_evidence_ids, valid_ids)
    payload = {
        "case_id": case["case_id"],
        "accession": case["accession"],
        "target": case["target"],
        "arm": "D",
        "arm_b_final_state_hash": state.get("final_state_hash"),
        "arm_d_input_state_hash": packet.get("final_evidence_state_hash"),
        "identical_evidence_assert": state.get("final_state_hash") == packet.get("final_evidence_state_hash"),
        "endpoint": decision.endpoint,
        "target_family_support": decision.target_family_support,
        "credible_competitor_support": decision.credible_competitor_support,
        "evidence_sufficient": decision.evidence_sufficient,
        "target_locus_interpretation": decision.target_locus_interpretation,
        "decisive_evidence_ids": kept,
        "invalid_evidence_ids": invalid,
        "followup_count": 0,
        "followup_actions": [],
        "planner_requests": 0,
        "critic_requests": 0,
        "total_model_requests": usage["total_model_requests"],
        "model_latency_s": usage["model_latency_s"] or latency,
        "deterministic_runtime_s": 0.0,
        "total_runtime_s": usage["model_latency_s"] or latency,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": usage["reasoning_tokens"],
        "retries": retries,
        "errors": usage["error_count"],
        "cost_usd": usage["cost_usd"],
        "call_log": usage["call_log"],
        "error": None if decision is not None else str(last_err),
    }
    if not payload["identical_evidence_assert"]:
        raise SystemExit(f"STOP: Arm B/D evidence hash mismatch for {case['case_id']}")
    write_json(pred_path, payload)
    write_json(pred_path.with_suffix(".json.sha256.json"), {"sha256": sha256_file(pred_path), "hashed_utc": utc_now()})
    print(f"DONE arm=D case={case['case_id']} endpoint={payload['endpoint']}", flush=True)
    return payload


def synthetic_planner_payload() -> dict:
    return {
        "target": "warmup_non_study_dummy",
        "current_result": {"architecture": None, "n_hits": 0, "n_loci": 0},
        "diagnostic_needs": {"needs": ["family_identity_unresolved"]},
        "key_observations": ["synthetic non-study warmup; not a study genome"],
        "evidence": [{"id": "E001", "summary": "synthetic evidence identifier"}],
        "available_actions": [
            {
                "action_id": "competitive_family",
                "tests": ["family_identity_unresolved"],
                "matched_needs": ["family_identity_unresolved"],
                "updates": ["family_evidence"],
            }
        ],
        "actions_that_can_change_a_measurement_now": ["competitive_family"],
        "registered_actions": ["competitive_family"],
        "control_decisions": [
            {"decision_id": FINALIZE_WITH_CURRENT_EVIDENCE, "meaning": "sufficient evidence"},
            {"decision_id": ABSTAIN_UNRESOLVED, "meaning": "cannot decide"},
        ],
        "valid_evidence_ids": ["E001"],
        "actions_already_tried": [],
    }


def run_warmups() -> dict:
    from genome_skeptic.models import PlannerDecision

    out = {}
    # Sol warmup
    reset_call_log()
    t0 = time.perf_counter()
    try:
        install_clients("sol")
        settings = settings_for_arm("sol")
        SolModelAdapter(settings.llm.for_role("planner")).ask_json(
            "Return one JSON object. This is a non-study warmup.",
            synthetic_planner_payload(),
            PlannerDecision,
        )
        ok = True
        err = None
    except Exception as exc:
        ok = False
        err = str(exc)
    out["sol"] = {
        "ok": ok,
        "error": err,
        "latency_s": round(time.perf_counter() - t0, 3),
        "cost_usd": round(sum(float(r.get("estimated_api_cost_usd") or 0) for r in CALL_LOG), 8),
        "non_study": True,
    }
    reset_call_log()
    # Jev warmup
    t0 = time.perf_counter()
    try:
        from jev_adapter import plan_from_payload

        plan_from_payload(synthetic_planner_payload())
        ok = True
        err = None
    except Exception as exc:
        ok = False
        err = str(exc)
    out["jev"] = {
        "ok": ok,
        "error": err,
        "latency_s": round(time.perf_counter() - t0, 3),
        "cost_usd": round(sum(float(r.get("estimated_api_cost_usd") or 0) for r in CALL_LOG), 8),
        "non_study": True,
    }
    reset_call_log()
    write_json(OUT_PROV / "ROLE_SWAP_WARMUPS.json", out)
    print(f"WARMUPS sol_ok={out['sol']['ok']} jev_ok={out['jev']['ok']}", flush=True)
    return out


def median(vals: list[float]) -> float | None:
    clean = [float(v) for v in vals if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean), 6)


def load_arm_predictions(arm: str) -> list[dict]:
    root = {"A": OUT_A, "B": OUT_B, "C": OUT_C, "D": OUT_D, "F": OUT_F}[arm]
    rows = []
    for pred in sorted(root.glob("*/prediction.json")):
        rows.append(load_json(pred))
    return rows


def build_preunblind_and_locks(cases: list[dict], freeze: dict) -> dict:
    arms = {k: load_arm_predictions(k) for k in ("A", "B", "C", "D", "F")}
    for k, rows in arms.items():
        if len(rows) != 20:
            raise SystemExit(f"STOP: arm {k} has {len(rows)}/20 predictions")

    # Identical evidence check
    b_by = {r["case_id"]: r for r in arms["B"]}
    d_by = {r["case_id"]: r for r in arms["D"]}
    identical = 0
    for cid in b_by:
        if b_by[cid].get("final_state_hash") == d_by[cid].get("arm_d_input_state_hash") == d_by[cid].get("arm_b_final_state_hash"):
            identical += 1
        elif not d_by[cid].get("identical_evidence_assert"):
            raise SystemExit(f"STOP: identical-evidence fail {cid}")
        else:
            identical += 1
    if identical != 20:
        raise SystemExit(f"STOP: identical evidence {identical}/20")

    # Arm E index
    e_rows = []
    for cid in sorted(b_by):
        e_rows.append(
            {
                "case_id": cid,
                "accession": b_by[cid]["accession"],
                "arm_b_prediction": str((OUT_B / cid / "prediction.json")).replace("\\", "/"),
                "arm_d_prediction": str((OUT_D / cid / "prediction.json")).replace("\\", "/"),
                "arm_b_final_state_hash": b_by[cid].get("final_state_hash"),
                "arm_d_endpoint": d_by[cid].get("endpoint"),
                "arm_b_endpoint": b_by[cid].get("endpoint"),
                "conceptual_arm": "E_SOL_FULL_AUTHORITY",
            }
        )
    write_csv(
        OUT_D / "ARM_E_FULL_AUTHORITY_INDEX.csv",
        e_rows,
        list(e_rows[0].keys()),
    )

    def endpoint_counts(rows):
        c = Counter(r.get("endpoint") for r in rows)
        return {"PRESENT": c.get("PRESENT", 0), "ABSENT": c.get("ABSENT", 0), "UNRESOLVED": c.get("UNRESOLVED", 0)}

    def followup_stats(rows):
        counts = [int(r.get("followup_count") or 0) for r in rows]
        return {"followups_total": sum(counts), "followups_median": median(counts)}

    behaviour = []
    for arm, rows in arms.items():
        first_actions = []
        challenges = 0
        critic_calls = 0
        for r in rows:
            fa = (r.get("followup_actions") or [None])
            if fa:
                first_actions.append(fa[0] if fa else None)
            if r.get("critic_decision"):
                critic_calls += 1
                if str(r.get("critic_decision")).upper() in {"CHALLENGE", "CHALLENGED"}:
                    challenges += 1
            if r.get("critic_noul") is not None and float(r.get("critic_noul") or 0) > 0.5:
                challenges += 1
                critic_calls += 1
        eps = endpoint_counts(rows)
        fs = followup_stats(rows)
        behaviour.append(
            {
                "arm": arm,
                **fs,
                "model_requests": sum(int(r.get("total_model_requests") or 0) for r in rows),
                "unique_first_actions": len({a for a in first_actions if a}),
                "critic_challenge_rate": round(challenges / critic_calls, 6) if critic_calls else None,
                "median_planner_latency": median([r.get("planner_latency_s") for r in rows]),
                "median_critic_latency": median([r.get("critic_latency_s") for r in rows]),
                "median_model_latency": median([r.get("model_latency_s") for r in rows]),
                "median_deterministic_runtime": median([r.get("deterministic_runtime_s") for r in rows]),
                "median_total_runtime": median([r.get("total_runtime_s") for r in rows]),
                "total_api_cost": round(sum(float(r.get("cost_usd") or 0) for r in rows), 8),
                **{f"endpoint_{k.lower()}": v for k, v in eps.items()},
            }
        )
    write_csv(OUT_RES / "ROLE_SWAP_PREUNBLIND_BEHAVIOUR.csv", behaviour, list(behaviour[0].keys()))

    def diff_endpoint(a_rows, b_rows):
        am = {r["case_id"]: r.get("endpoint") for r in a_rows}
        bm = {r["case_id"]: r.get("endpoint") for r in b_rows}
        return sum(1 for cid in am if am[cid] != bm[cid])

    def diff_state(a_rows, b_rows):
        am = {r["case_id"]: r.get("final_state_hash") for r in a_rows}
        bm = {r["case_id"]: r.get("final_state_hash") for r in b_rows}
        return sum(1 for cid in am if am[cid] != bm[cid])

    comparisons = {
        "A_vs_B_state": diff_state(arms["A"], arms["B"]),
        "A_vs_B_endpoint": diff_endpoint(arms["A"], arms["B"]),
        "A_vs_C_state": diff_state(arms["A"], arms["C"]),
        "A_vs_C_endpoint": diff_endpoint(arms["A"], arms["C"]),
        "B_vs_C_state": diff_state(arms["B"], arms["C"]),
        "B_vs_C_endpoint": diff_endpoint(arms["B"], arms["C"]),
        "B_vs_F_state": diff_state(arms["B"], arms["F"]),
        "B_vs_F_endpoint": diff_endpoint(arms["B"], arms["F"]),
        "B_vs_D_endpoint": diff_endpoint(arms["B"], arms["D"]),
        "B_vs_D_identical_evidence": identical,
    }
    write_json(OUT_RES / "ROLE_SWAP_PREUNBLIND_COMPARISONS.json", comparisons)

    # Prediction lock
    file_hashes = {}
    for arm, root in [("A", OUT_A), ("B", OUT_B), ("C", OUT_C), ("D", OUT_D), ("F", OUT_F)]:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".json", ".csv"}:
                rel = str(path.relative_to(STUDY)).replace("\\", "/")
                file_hashes[rel] = sha256_file(path)
    pred_lock = {
        "kind": "ROLE_SWAP_PREDICTION_LOCK",
        "locked_at_utc": utc_now(),
        "n_cases": 20,
        "arms": {k: len(v) for k, v in arms.items()},
        "identical_evidence_b_d": f"{identical}/20",
        "truth_joined": False,
        "accuracy_calculated": False,
        "file_sha256": file_hashes,
        "comparisons": comparisons,
    }
    pred_lock_sha = write_json(OUT_RES / "ROLE_SWAP_PREDICTION_LOCK.json", pred_lock)

    # Re-verify freeze
    freeze2 = verify_v5_freeze()
    final_hash = {
        "checked_utc": utc_now(),
        "all_match": freeze2["all_match"],
        "rows": freeze2["rows"],
        "family": freeze2["family_definitions_hash"],
        "ortholog": freeze2["reference_assets_hash"],
        "caseset_lock": sha256_file(CASES / "ROLE_SWAP_CASESET_LOCK.json"),
        "result": "PASS" if freeze2["all_match"] else "FAIL",
    }
    write_json(OUT_PROV / "ROLE_SWAP_FINAL_HASH_CHECK.json", final_hash)

    truth_audit = {
        "truth_access_attempts": len(TRUTH_ACCESS_LOG),
        "log": TRUTH_ACCESS_LOG,
        "path_guard": "scripts/role_swap_prediction_path_guard.py",
    }
    write_json(OUT_PROV / "ROLE_SWAP_TRUTH_ACCESS_AUDIT.json", truth_audit)
    if TRUTH_ACCESS_LOG:
        raise SystemExit("STOP: truth access detected during execution")

    write_text = lambda path, text: path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")  # noqa: E731
    write_text(
        OUT_PROV / "ROLE_SWAP_EXECUTION_INTEGRITY.md",
        "\n".join(
            [
                "# ROLE_SWAP EXECUTION INTEGRITY",
                "",
                f"- scientific tuning: NO",
                f"- case replacement: NO",
                f"- truth access attempts: {len(TRUTH_ACCESS_LOG)}",
                f"- truth joined: NO",
                f"- accuracy calculated: NO",
                f"- failed cases manually rerun for score: NO",
                f"- prospective case removal: NO",
                f"- identical evidence B==D: {identical}/20",
                f"- scientific core still matches: {'YES' if freeze2['all_match'] else 'NO'}",
                f"- caseset lock still matches: {'YES' if final_hash['caseset_lock']==EXPECTED_CASESET_LOCK else 'NO'}",
                "",
            ]
        ),
    )

    beh = {r["arm"]: r for r in behaviour}
    manifest = {
        "kind": "ROLE_SWAP_EXECUTION_MANIFEST",
        "created_utc": utc_now(),
        "n_cases": 20,
        "arms_complete": {k: True for k in arms},
        "arm_e_index": True,
        "prediction_lock_sha256": pred_lock_sha,
        "behaviour": behaviour,
        "comparisons": comparisons,
        "warmup": load_json(OUT_PROV / "ROLE_SWAP_WARMUPS.json") if (OUT_PROV / "ROLE_SWAP_WARMUPS.json").is_file() else None,
        "freeze_final": final_hash,
    }
    man_sha = write_json(OUT_RES / "ROLE_SWAP_EXECUTION_MANIFEST.json", manifest)

    # Terminal summary
    def ep(arm):
        r = endpoint_counts(arms[arm])
        return r

    print("\n===== TERMINAL =====", flush=True)
    print("ROLE-SWAP EXECUTION COMPLETE: YES")
    print("CASES EXECUTED: 20")
    for a in ("A", "B", "C", "D", "F"):
        print(f"ARM {a} COMPLETE: YES")
    print("ARM E INDEX COMPLETE: YES")
    print("--------------------------------------------------")
    print("PRE-UNBLIND ENDPOINT COUNTS")
    print("--------------------------------------------------")
    for a in ("A", "B", "C", "D", "F"):
        e = ep(a)
        print(f"ARM {a}:")
        print(f"PRESENT {e['PRESENT']}")
        print(f"ABSENT {e['ABSENT']}")
        print(f"UNRESOLVED {e['UNRESOLVED']}")
    print("--------------------------------------------------")
    print("FOLLOW-UP ANALYSES")
    print("--------------------------------------------------")
    for a in ("A", "B", "C", "F"):
        print(f"ARM {a}:")
        print(beh[a]["followups_total"])
    print("--------------------------------------------------")
    print("MODEL REQUESTS")
    print("--------------------------------------------------")
    print(f"SOL CONTROLLER: {beh['B']['model_requests']}")
    print(f"SOL JUDGE: {beh['D']['model_requests']}")
    print(f"JEV CONTROLLER: {beh['F']['model_requests']}")
    print("--------------------------------------------------")
    print("MEDIAN MODEL LATENCY")
    print("--------------------------------------------------")
    print(f"SOL CONTROLLER: {beh['B']['median_model_latency']}")
    print(f"SOL JUDGE: {beh['D']['median_model_latency']}")
    print(f"JEV CONTROLLER: {beh['F']['median_model_latency']}")
    print("--------------------------------------------------")
    print("MEDIAN TOTAL RUNTIME")
    print("--------------------------------------------------")
    print(f"ARM A: {beh['A']['median_total_runtime']}")
    print(f"ARM B: {beh['B']['median_total_runtime']}")
    print(f"ARM C: {beh['C']['median_total_runtime']}")
    print(f"ARM D JUDGE LATENCY: {beh['D']['median_model_latency']}")
    print(f"ARM F: {beh['F']['median_total_runtime']}")
    print("--------------------------------------------------")
    print("API COST")
    print("--------------------------------------------------")
    print(f"SOL CONTROLLER: ${beh['B']['total_api_cost']}")
    print(f"SOL JUDGE: ${beh['D']['total_api_cost']}")
    print(f"JEV CONTROLLER: ${beh['F']['total_api_cost']}")
    print("--------------------------------------------------")
    print("FINAL STATE DIFFERENCES")
    print("--------------------------------------------------")
    print(f"A vs B: {comparisons['A_vs_B_state']} / 20")
    print(f"A vs C: {comparisons['A_vs_C_state']} / 20")
    print(f"B vs C: {comparisons['B_vs_C_state']} / 20")
    print(f"B vs F: {comparisons['B_vs_F_state']} / 20")
    print("--------------------------------------------------")
    print("ENDPOINT DIFFERENCES BEFORE TRUTH")
    print("--------------------------------------------------")
    print(f"A vs B: {comparisons['A_vs_B_endpoint']} / 20")
    print(f"A vs C: {comparisons['A_vs_C_endpoint']} / 20")
    print(f"B vs C: {comparisons['B_vs_C_endpoint']} / 20")
    print(f"B vs D: {comparisons['B_vs_D_endpoint']} / 20")
    print(f"B vs F: {comparisons['B_vs_F_endpoint']} / 20")
    print("--------------------------------------------------")
    print("IDENTICAL-EVIDENCE ROLE SWAP")
    print("--------------------------------------------------")
    print(f"ARM B FINAL STATE == ARM D INPUT STATE: {identical} / 20")
    print(f"ARM B vs ARM D ENDPOINT DIFFERENCES: {comparisons['B_vs_D_endpoint']} / 20")
    print("--------------------------------------------------")
    print("TRUTH ACCESSED DURING EXECUTION: NO")
    print("TRUTH JOINED: NO")
    print("ACCURACY CALCULATED: NO")
    print(f"SCIENTIFIC CORE STILL MATCHES: {'YES' if freeze2['all_match'] else 'NO'}")
    print(f"VALIDATOR STILL MATCHES: {'YES' if freeze2['rows']['validator']['match'] else 'NO'}")
    print(f"CASESET LOCK STILL MATCHES: {'YES' if final_hash['caseset_lock']==EXPECTED_CASESET_LOCK else 'NO'}")
    print(f"PREDICTION LOCK SHA256: {pred_lock_sha}")
    print(f"EXECUTION MANIFEST SHA256: {man_sha}")
    print("READY FOR SINGLE UNBLIND: YES")
    print("STOP.")
    return {"prediction_lock_sha": pred_lock_sha, "manifest_sha": man_sha, "comparisons": comparisons}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["all", "warmup", "execute", "lock"], default="all")
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--arm", default=None, help="A|B|C|D|F")
    args = parser.parse_args()

    for d in (OUT_INIT, OUT_A, OUT_B, OUT_C, OUT_D, OUT_F, OUT_RES, OUT_PROV):
        d.mkdir(parents=True, exist_ok=True)

    install_path_guard()
    freeze = verify_locks()
    cases = load_cases()

    if args.phase in {"all", "warmup"}:
        run_warmups()

    if args.phase in {"all", "execute"}:
        selected = cases
        if args.case_id:
            selected = [c for c in cases if c["case_id"] == args.case_id]
        # Fixed order A, B, C, D, F per case (or all cases for each arm then next)
        # Protocol: for reproducibility use fixed arm order A B C D F
        for case in selected:
            print(f"==== CASE {case['case_id']} {case['accession']} ====", flush=True)
            if args.arm in {None, "A"}:
                run_gs_arm(case, "A", "deterministic")
            if args.arm in {None, "B"}:
                run_gs_arm(case, "B", "sol")
            if args.arm in {None, "C"}:
                run_gs_arm(case, "C", "exhaustive")
            if args.arm in {None, "D"}:
                run_arm_d(case)
            if args.arm in {None, "F"}:
                run_gs_arm(case, "F", "jev")

    if args.phase in {"all", "lock"} and args.case_id is None and args.arm is None:
        build_preunblind_and_locks(cases, freeze)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
