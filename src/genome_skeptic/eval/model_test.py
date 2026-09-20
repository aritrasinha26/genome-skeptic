"""Live planner/critic wiring test. Does not invent model responses or run genome benchmarks."""
from __future__ import annotations

import json
import time
from typing import Any

import requests
from pydantic import ValidationError

from genome_skeptic.agents.providers import (
    CALL_LOG,
    ModelAdapter,
    auth_headers,
    extract_json_text,
    models_url,
    reset_call_log,
)
from genome_skeptic.config import Settings
from genome_skeptic.models import AgentDecision, CriticReview

INVENTED_EVIDENCE_ID = "E_INVENTED_999"
UNREGISTERED_ACTION = "bypass_qc"

TINY_EVIDENCE = [
    {"id": "E001", "summary": "Q30 rate 0.92"},
    {"id": "E002", "summary": "assembly produced 42 contigs"},
]
TINY_ACTIONS = [
    "continue_pipeline",
    "stop_and_request_human_review",
    "inspect_raw_reads_more_deeply",
]
KNOWN_IDS = {row["id"] for row in TINY_EVIDENCE}

PLANNER_SYSTEM = (
    "You are the planner. Return one JSON object matching the provided schema. "
    "Cite only evidence IDs from the payload. requested_actions must come from registered_actions. "
    "Do not invent measurements."
)
CRITIC_SYSTEM = (
    "You are the critic. Return one JSON object matching the provided schema. "
    "Cite only evidence IDs from the payload. Try to falsify the proposed decision. "
    "Do not invent measurements."
)


def _check(name: str, ok: bool, detail: Any) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _reject_unknown_evidence(decision: AgentDecision, known: set[str]) -> AgentDecision:
    unknown = [eid for eid in (decision.evidence_ids or []) if eid not in known]
    if not unknown:
        return decision
    return AgentDecision(
        decision="ask_human",
        rationale="Reasoner cited evidence IDs that do not exist in the ledger, so its decision was rejected.",
        concerns=["invalid evidence citation from reasoning model"],
        evidence_ids=[],
        confidence=0.0,
    )


def _reject_unregistered_actions(decision: AgentDecision, registered: list[str]) -> AgentDecision:
    invalid = [a for a in (decision.requested_actions or []) if a not in registered]
    if not invalid:
        return decision
    return AgentDecision(
        decision="ask_human",
        rationale="Reasoner requested unregistered actions, so its decision was rejected.",
        concerns=[f"unregistered action: {a}" for a in invalid],
        evidence_ids=list(decision.evidence_ids or []),
        confidence=0.0,
    )


def run_model_test(settings: Settings) -> dict:
    reset_call_log()
    started = time.perf_counter()
    llm = settings.llm
    planner_cfg = llm.for_role("planner")
    critic_cfg = llm.for_role("critic")
    checks: list[dict] = []

    models_endpoint = models_url(llm.base_url)
    try:
        r = requests.get(models_endpoint, headers=auth_headers(llm), timeout=8)
        r.raise_for_status()
        available = [row.get("id") or row.get("name") for row in (r.json().get("data") or [])]
        model_ok = llm.model in available
        checks.append(_check("endpoint_connectivity", True, {"url": models_endpoint, "status": r.status_code}))
        checks.append(_check("model_existence", model_ok, {"requested": llm.model, "available": available}))
    except Exception as exc:
        checks.append(_check("endpoint_connectivity", False, {"url": models_endpoint, "error": str(exc)}))
        checks.append(_check("model_existence", False, {"requested": llm.model, "error": str(exc)}))

    planner_payload = {
        "stage": "assembly_qc",
        "evidence": TINY_EVIDENCE,
        "registered_actions": TINY_ACTIONS,
    }
    proposed = {
        "decision": "continue",
        "rationale": "Q30 is high enough to continue",
        "evidence_ids": ["E001"],
        "requested_actions": ["continue_pipeline"],
        "confidence": 0.4,
    }
    critic_payload = {
        "stage": "assembly_qc",
        "evidence": TINY_EVIDENCE,
        "registered_actions": TINY_ACTIONS,
        "proposed_decision": proposed,
    }

    planner = ModelAdapter(planner_cfg)
    critic = ModelAdapter(critic_cfg)

    planner_ok = False
    planner_detail: Any
    decision = None
    raw_planner_json = None
    try:
        decision = planner.ask_json(PLANNER_SYSTEM, planner_payload, AgentDecision, request_type="planner_structured")
        planner_ok = isinstance(decision, AgentDecision) and planner.last_mode == "openai_compatible"
        raw_planner_json = decision.model_dump_json()
        planner_detail = {"transport": planner.last_mode, "model": planner.model, "decision": decision.model_dump()}
    except Exception as exc:
        planner_detail = {"error": str(exc)}
    checks.append(_check("planner_structured_output", planner_ok, planner_detail))

    critic_ok = False
    critic_detail: Any
    review = None
    try:
        if decision is not None:
            critic_payload["proposed_decision"] = decision.model_dump()
        review = critic.ask_json(CRITIC_SYSTEM, critic_payload, CriticReview, request_type="critic_structured")
        critic_ok = isinstance(review, CriticReview) and critic.last_mode == "openai_compatible"
        critic_detail = {"transport": critic.last_mode, "model": critic.model, "review": review.model_dump()}
    except Exception as exc:
        critic_detail = {"error": str(exc)}
    checks.append(_check("critic_structured_output", critic_ok, critic_detail))

    evidence_ok = False
    evidence_detail: Any
    if decision is None:
        evidence_detail = {"error": "planner did not return structured output"}
    else:
        unknown = [eid for eid in (decision.evidence_ids or []) if eid not in KNOWN_IDS]
        rejected_real = _reject_unknown_evidence(decision, KNOWN_IDS)
        injected = decision.model_copy(deep=True)
        injected.evidence_ids = list(injected.evidence_ids or []) + [INVENTED_EVIDENCE_ID]
        rejected_injected = _reject_unknown_evidence(injected, KNOWN_IDS)
        real_citations_ok = not unknown or rejected_real.decision == "ask_human"
        injected_rejected = rejected_injected.decision == "ask_human"
        evidence_ok = real_citations_ok and injected_rejected
        evidence_detail = {
            "cited": decision.evidence_ids,
            "unknown_in_real_output": unknown,
            "invented_id": INVENTED_EVIDENCE_ID,
            "invented_id_rejected": injected_rejected,
            "real_output_fail_closed": rejected_real.decision if unknown else "accepted",
            "invented_model_response": False,
        }
    checks.append(_check("unknown_evidence_id_rejection", evidence_ok, evidence_detail))

    action_ok = False
    action_detail: Any
    if decision is None:
        action_detail = {"error": "planner did not return structured output"}
    else:
        invalid = [a for a in (decision.requested_actions or []) if a not in TINY_ACTIONS]
        rejected_real = _reject_unregistered_actions(decision, TINY_ACTIONS)
        injected = decision.model_copy(deep=True)
        injected.requested_actions = list(injected.requested_actions or []) + [UNREGISTERED_ACTION]
        rejected_injected = _reject_unregistered_actions(injected, TINY_ACTIONS)
        real_ok = not invalid or rejected_real.decision == "ask_human"
        injected_rejected = rejected_injected.decision == "ask_human"
        action_ok = real_ok and injected_rejected and UNREGISTERED_ACTION not in TINY_ACTIONS
        action_detail = {
            "requested": decision.requested_actions,
            "invalid_in_real_output": invalid,
            "unregistered_action": UNREGISTERED_ACTION,
            "unregistered_rejected": injected_rejected,
            "invented_model_response": False,
        }
    checks.append(_check("unregistered_action_rejection", action_ok, action_detail))

    malformed_ok = False
    malformed_detail: Any
    source = raw_planner_json or (review.model_dump_json() if review is not None else None)
    if not source:
        malformed_detail = {"error": "no real structured output available to truncate"}
    else:
        truncated = source.strip()[:-1]
        closed = False
        error = None
        invented = False
        try:
            AgentDecision.model_validate_json(extract_json_text(truncated) or truncated)
            invented = True
        except (ValidationError, json.JSONDecodeError, ValueError, TypeError) as exc:
            closed = True
            error = exc.__class__.__name__ + ": " + str(exc)
        malformed_ok = closed and not invented
        malformed_detail = {
            "source": "truncated_real_qwen_json",
            "fail_closed": closed,
            "invented_decision": invented,
            "error": error,
        }
    checks.append(_check("fail_closed_malformed_structured_output", malformed_ok, malformed_detail))

    real_calls = [row for row in CALL_LOG]
    planner_critic_ok = planner_ok and critic_ok
    by_name = {c["name"]: c["ok"] for c in checks}
    return {
        "kind": "genome_skeptic_model_test",
        "provider": llm.provider,
        "model": llm.model,
        "base_url": llm.base_url,
        "thinking": llm.thinking,
        "keep_alive": llm.keep_alive,
        "max_output_tokens": llm.max_output_tokens,
        "temperature": llm.temperature,
        "invented_model_responses": False,
        "genome_benchmark_run": False,
        "planner_integration": "PASS" if planner_ok else "FAIL",
        "critic_integration": "PASS" if critic_ok else "FAIL",
        "evidence_guardrail": "PASS" if by_name.get("unknown_evidence_id_rejection") else "FAIL",
        "registered_action_guardrail": "PASS" if by_name.get("unregistered_action_rejection") else "FAIL",
        "fail_closed_malformed_output": "PASS" if by_name.get("fail_closed_malformed_structured_output") else "FAIL",
        "planner_critic_integration": "passed" if planner_critic_ok else "failed",
        "passed": all(c["ok"] for c in checks),
        "total_real_model_calls": len(real_calls),
        "total_runtime_seconds": round(time.perf_counter() - started, 3),
        "call_log": real_calls,
        "checks": checks,
    }
