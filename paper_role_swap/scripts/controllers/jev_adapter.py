"""Native TypeSafe System One / Jev adapter for the V5 5-case POC.

Jev is not forced into chat completion. It is asked Choice and Noul questions
over the same structured planner/critic state already available to V5.
"""
from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

import requests
from pydantic import BaseModel

from genome_skeptic.agents.providers import CALL_LOG, ModelUnavailable
from genome_skeptic.models import CriticDecision, PlannerDecision

try:
    from leakage import assert_no_forbidden_fields
except ImportError:
    from model_poc_v5.leakage import assert_no_forbidden_fields

T = TypeVar("T", bound=BaseModel)

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
JEV_ALIAS = "jev-latest"
NOUL_CHALLENGE_THRESHOLD = 0.50  # predefined before execution; noul > 0.50 => CHALLENGE
JEV_INPUT_USD_PER_MILLION = 0.042
JEV_OUTPUT_USD_PER_MILLION = 0.0
JEV_PRICING_SOURCE = "https://docs.typesafe.ai/models"
JEV_PRICING_DATE = "2026-09-22"
LOW_CONFIDENCE_FLAG = 0.60
NO_ACTION = "NO_ACTION"
RATIONALE_PLACEHOLDER = "jev_typed_decision"


def _api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY")
    if not isinstance(key, str) or not key.strip():
        raise ModelUnavailable("TYPESAFE_API_KEY is not configured")
    return key.strip()


def estimate_jev_cost_usd(input_tokens: int | None, output_tokens: int | None = None) -> float | None:
    if input_tokens is None and output_tokens is None:
        return None
    inp = int(input_tokens or 0)
    out = int(output_tokens or 0)
    return round(
        (inp / 1_000_000) * JEV_INPUT_USD_PER_MILLION
        + (out / 1_000_000) * JEV_OUTPUT_USD_PER_MILLION,
        10,
    )


def _choice_entropy(probabilities: dict[str, float] | None) -> float | None:
    if not probabilities:
        return None
    values = [float(p) for p in probabilities.values() if float(p) > 0]
    if not values:
        return 0.0
    return round(-sum(p * math.log2(p) for p in values), 6)


def _top_second(probabilities: dict[str, float] | None) -> tuple[float | None, float | None, float | None]:
    if not probabilities:
        return None, None, None
    ranked = sorted((float(p) for p in probabilities.values()), reverse=True)
    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else 0.0
    return top, second, round(top - second, 6)


def _action_ids(rows: Any) -> list[str]:
    out: list[str] = []
    for row in rows or []:
        if isinstance(row, dict):
            action_id = row.get("action_id") or row.get("id")
        else:
            action_id = row
        if action_id and str(action_id) not in out:
            out.append(str(action_id))
    return out


def _action_criteria(rows: Any, extra: list[str] | None = None) -> dict[str, str]:
    criteria: dict[str, str] = {}
    for row in rows or []:
        if isinstance(row, dict):
            action_id = str(row.get("action_id") or row.get("id") or "")
            if not action_id:
                continue
            tests = row.get("tests") or row.get("matched_needs") or row.get("endpoint_relevance") or []
            criteria[action_id] = (
                "Eligible registered follow-up analysis. "
                f"tests={list(tests)}; updates={list(row.get('updates') or [])}; "
                f"matched_needs={list(row.get('matched_needs') or [])}"
            )
        else:
            criteria[str(row)] = "Eligible registered follow-up analysis."
    for action_id in extra or []:
        criteria.setdefault(action_id, "Eligible registered follow-up analysis.")
    return criteria


def planner_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": payload.get("target"),
        "diagnostic_needs": payload.get("diagnostic_needs"),
        "decision_relevant_target_measurements": payload.get("current_result"),
        "evidence_identifiers": payload.get("valid_evidence_ids") or [e.get("id") for e in (payload.get("evidence") or []) if isinstance(e, dict)],
        "eligible_registered_actions": payload.get("available_actions") or [],
        "actions_that_can_change_a_measurement_now": payload.get("actions_that_can_change_a_measurement_now") or [],
        "actions_already_tried": payload.get("actions_already_tried") or [],
        "control_decision_ids": [row.get("decision_id") for row in (payload.get("control_decisions") or []) if isinstance(row, dict)],
        "key_observations": payload.get("key_observations") or [],
    }


def critic_state(payload: dict[str, Any]) -> dict[str, Any]:
    remaining = payload.get("remaining_actions") or payload.get("available_actions") or []
    return {
        "target": payload.get("target") or (payload.get("planner_decision") or {}).get("target"),
        "planner_decision": payload.get("planner_decision") or payload.get("decision"),
        "diagnostic_needs": payload.get("diagnostic_needs"),
        "decision_relevant_target_measurements": payload.get("current_result") or payload.get("updated_result"),
        "evidence_identifiers": payload.get("valid_evidence_ids") or [],
        "remaining_eligible_registered_actions": remaining,
        "actions_already_tried": payload.get("actions_already_tried") or payload.get("actions_already_run") or [],
        "new_evidence": payload.get("new_evidence") or [],
        "key_observations": payload.get("key_observations") or [],
    }


def _post_systemone(state: dict[str, Any], questions: dict[str, Any], *, request_type: str) -> dict[str, Any]:
    assert_no_forbidden_fields(state, label=f"jev:{request_type}:state")
    assert_no_forbidden_fields(questions, label=f"jev:{request_type}:questions")
    body = {"state": state, "model": JEV_ALIAS, "questions": questions}
    assert_no_forbidden_fields(body, label=f"jev:{request_type}:request")
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    record: dict[str, Any] = {
        "request_number": len(CALL_LOG) + 1,
        "request_type": request_type,
        "role": "planner" if "Planner" in request_type else "critic",
        "provider": "typesafe_systemone",
        "model_alias": JEV_ALIAS,
        "model": JEV_ALIAS,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "url": TYPESAFE_URL,
        "retry_count": 0,
        "first_attempt": True,
        "n_questions": len(questions),
        "schema": "typesafe_choice_noul",
        "prompt_chars": 0,
        "estimated_tokens": 0,
        "max_output_tokens": None,
        "thinking": None,
    }
    started = time.perf_counter()
    try:
        response = requests.post(TYPESAFE_URL, headers=headers, json=body, timeout=180)
        elapsed = round(time.perf_counter() - started, 3)
        record["elapsed_seconds"] = elapsed
        record["http_status"] = response.status_code
        record["http_latency_s"] = elapsed
        record["x_envoy_upstream_service_time"] = (
            response.headers.get("x-envoy-upstream-service-time")
            or response.headers.get("x-envoy-upstream-service-time-ms")
        )
        record["request_id"] = (
            response.headers.get("x-request-id")
            or response.headers.get("x-typesafe-request-id")
            or response.headers.get("request-id")
        )
        record["response_headers"] = {
            k: v
            for k, v in response.headers.items()
            if k.lower() in {
                "x-envoy-upstream-service-time",
                "x-request-id",
                "x-typesafe-request-id",
                "cf-ray",
                "server-timing",
            }
        }
        if not response.ok:
            record["error"] = response.text[:500]
            CALL_LOG.append(record)
            raise ModelUnavailable(f"TypeSafe HTTP {response.status_code}: {response.text[:300]}")
        payload = response.json()
        usage = payload.get("usage") or {}
        record["concrete_model"] = payload.get("model")
        record["model"] = payload.get("model") or JEV_ALIAS
        record["response_id"] = payload.get("id") or record.get("request_id")
        record["input_tokens"] = usage.get("input_tokens")
        record["output_tokens"] = usage.get("output_tokens")
        record["reasoning_tokens"] = usage.get("reasoning_tokens")
        record["cached_tokens"] = usage.get("cached_tokens")
        record["estimated_api_cost_usd"] = estimate_jev_cost_usd(
            usage.get("input_tokens"), usage.get("output_tokens")
        )
        record["pricing_source"] = JEV_PRICING_SOURCE
        record["pricing_date"] = JEV_PRICING_DATE
        record["answers"] = payload.get("answers")
        record["schema_valid"] = True
        if record.get("request_id") is None:
            record["request_id"] = payload.get("id")
        CALL_LOG.append(record)
        return payload
    except Exception as exc:
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        record["error"] = str(exc)
        record["schema_valid"] = False
        if record not in CALL_LOG:
            CALL_LOG.append(record)
        raise


def _evidence_ids(payload: dict[str, Any]) -> list[str]:
    ids = payload.get("valid_evidence_ids")
    if isinstance(ids, list) and ids:
        return [str(x) for x in ids]
    evidence = payload.get("evidence") or []
    return [str(e.get("id")) for e in evidence if isinstance(e, dict) and e.get("id")]


def _choice_answer(answers: dict[str, Any], key: str) -> dict[str, Any]:
    ans = (answers or {}).get(key) or {}
    if ans.get("type") != "choice" or not ans.get("choice"):
        raise ModelUnavailable(f"Jev choice output invalid for {key}: {ans}")
    return ans


def plan_from_payload(payload: dict[str, Any]) -> PlannerDecision:
    eligible = _action_ids(payload.get("available_actions") or payload.get("registered_actions") or [])
    action_criteria = _action_criteria(payload.get("available_actions") or [])
    if not action_criteria:
        action_criteria = {NO_ACTION: "No eligible registered action is currently available."}
    elif NO_ACTION not in action_criteria and not eligible:
        action_criteria[NO_ACTION] = "No eligible registered action is currently available."
    questions = {
        "planner_control": {
            "type": "choice",
            "instructions": (
                "Choose the planner control decision for this bacterial genome target-gene analysis. "
                "Use only the structured state. Do not invent measurements."
            ),
            "criteria": {
                "INVESTIGATE": "additional registered evidence should be acquired",
                "FINALIZE": "current evidence is sufficient for downstream deterministic validation",
                "ABSTAIN": (
                    "available evidence cannot currently support a defensible decision "
                    "and no useful registered action should be selected"
                ),
            },
        },
        "requested_action": {
            "type": "choice",
            "instructions": (
                "If additional registered evidence should be acquired, choose exactly one currently "
                "eligible registered action ID. If no follow-up should run, choose NO_ACTION when present, "
                "otherwise choose any listed option; the control decision is authoritative."
            ),
            "criteria": action_criteria,
        },
    }
    response = _post_systemone(planner_state(payload), questions, request_type="PlannerDecision")
    answers = response.get("answers") or {}
    control = _choice_answer(answers, "planner_control")
    action = _choice_answer(answers, "requested_action")
    control_choice = str(control["choice"]).upper()
    action_choice = str(action["choice"])
    control_probs = {str(k): float(v) for k, v in (control.get("probabilities") or {}).items()}
    action_probs = {str(k): float(v) for k, v in (action.get("probabilities") or {}).items()}
    control_top, control_second, control_margin = _top_second(control_probs)
    action_top, action_second, action_margin = _top_second(action_probs)
    if control_choice == "INVESTIGATE":
        decision = "investigate"
        requested = action_choice if action_choice != NO_ACTION else None
        if requested and eligible and requested not in eligible:
            raise ModelUnavailable(f"Jev requested ineligible action {requested}; fail closed")
        if not requested:
            raise ModelUnavailable("Jev INVESTIGATE with no eligible action; fail closed")
        confidence = float(action.get("confidence") or action_top or 0.5)
    elif control_choice == "FINALIZE":
        decision = "finalize"
        requested = None
        confidence = float(control.get("confidence") or control_top or 0.5)
    elif control_choice == "ABSTAIN":
        decision = "abstain"
        requested = None
        confidence = float(control.get("confidence") or control_top or 0.5)
    else:
        raise ModelUnavailable(f"Jev planner_control invalid: {control_choice}")
    if CALL_LOG:
        CALL_LOG[-1]["jev_planner"] = {
            "control": control_choice,
            "requested_action": requested,
            "control_confidence": control.get("confidence"),
            "action_confidence": action.get("confidence"),
            "control_probabilities": control_probs,
            "action_probabilities": action_probs,
            "control_top_probability": control_top,
            "control_second_probability": control_second,
            "control_probability_margin": control_margin,
            "control_entropy": _choice_entropy(control_probs),
            "action_top_probability": action_top,
            "action_second_probability": action_second,
            "action_probability_margin": action_margin,
            "action_entropy": _choice_entropy(action_probs),
            "low_confidence": bool(confidence < LOW_CONFIDENCE_FLAG),
            "concrete_model": response.get("model"),
            "n_decisions": 2,
        }
    return PlannerDecision(
        decision=decision,  # type: ignore[arg-type]
        leading_hypothesis=None,
        alternative_hypothesis=None,
        evidence_ids=_evidence_ids(payload),
        requested_action=requested,
        confidence=max(0.0, min(1.0, confidence)),
        rationale=RATIONALE_PLACEHOLDER,
    )


def critic_from_payload(payload: dict[str, Any]) -> CriticDecision:
    remaining_rows = payload.get("remaining_actions") or payload.get("available_actions") or []
    remaining = _action_ids(remaining_rows)
    noul_q = {
        "critic_unresolved_alternative": {
            "type": "noul",
            "instructions": (
                "Does a credible unresolved alternative remain that can be tested by one of the "
                "remaining eligible registered analyses?"
            ),
            "criteria": {
                "true": "A credible unresolved alternative remains and a remaining eligible registered analysis can test it.",
                "false": "No credible unresolved alternative remains that a remaining eligible registered analysis can test.",
            },
        }
    }
    noul_response = _post_systemone(critic_state(payload), noul_q, request_type="CriticDecision")
    noul_ans = (noul_response.get("answers") or {}).get("critic_unresolved_alternative") or {}
    if noul_ans.get("type") != "noul" or noul_ans.get("noul") is None:
        raise ModelUnavailable(f"Jev noul output invalid: {noul_ans}")
    noul = float(noul_ans["noul"])
    if CALL_LOG:
        CALL_LOG[-1]["jev_noul"] = noul
        CALL_LOG[-1]["jev_noul_threshold"] = NOUL_CHALLENGE_THRESHOLD
    challenge = noul > NOUL_CHALLENGE_THRESHOLD and bool(remaining)
    requested = None
    second_probs: dict[str, float] = {}
    second_conf = None
    if challenge:
        action_q = {
            "requested_action": {
                "type": "choice",
                "instructions": (
                    "A credible unresolved alternative remains. Choose exactly one remaining eligible "
                    "registered action ID to run as the single additional follow-up analysis."
                ),
                "criteria": _action_criteria(remaining_rows, extra=remaining),
            }
        }
        choice_response = _post_systemone(critic_state(payload), action_q, request_type="CriticDecision")
        choice_ans = _choice_answer(choice_response.get("answers") or {}, "requested_action")
        requested = str(choice_ans["choice"])
        if requested not in remaining:
            raise ModelUnavailable(f"Jev critic requested ineligible action {requested}; fail closed")
        second_probs = {str(k): float(v) for k, v in (choice_ans.get("probabilities") or {}).items()}
        second_conf = choice_ans.get("confidence")
    verdict = "challenge" if challenge else "accept"
    if CALL_LOG:
        top, second, margin = _top_second(second_probs)
        CALL_LOG[-1]["jev_critic"] = {
            "noul": noul,
            "threshold": NOUL_CHALLENGE_THRESHOLD,
            "decision": "CHALLENGE" if verdict == "challenge" else "ACCEPT",
            "raw_noul_even_if_no_eligible_action": noul,
            "remaining_eligible": remaining,
            "requested_action": requested,
            "second_action_probabilities": second_probs,
            "second_action_confidence": second_conf,
            "second_action_top_probability": top,
            "second_action_second_probability": second,
            "second_action_probability_margin": margin,
            "second_action_entropy": _choice_entropy(second_probs),
            "concrete_model": (choice_response if challenge else noul_response).get("model"),
            "n_decisions": 2 if challenge else 1,
        }
    return CriticDecision(
        verdict=verdict,  # type: ignore[arg-type]
        evidence_ids=_evidence_ids(payload),
        requested_action=requested,
        failure_mode=None,
        rationale=RATIONALE_PLACEHOLDER,
    )


class JevJSONClient:
    def __init__(self, cfg=None):
        self.cfg = cfg

    def ask_json(self, system: str, user_payload: dict, schema: Type[T]) -> T:
        assert_no_forbidden_fields(system, label="jev:system")
        assert_no_forbidden_fields(user_payload, label="jev:user_payload")
        if user_payload.get("repair") or user_payload.get("defects_to_fix"):
            raise ModelUnavailable("Jev fail closed: no silent repair substitution of an invalid typed decision")
        name = getattr(schema, "__name__", "")
        if name == "PlannerDecision":
            return plan_from_payload(user_payload)  # type: ignore[return-value]
        if name == "CriticDecision":
            return critic_from_payload(user_payload)  # type: ignore[return-value]
        raise ModelUnavailable(f"Jev adapter does not implement schema {name}")
