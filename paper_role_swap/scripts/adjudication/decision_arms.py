"""Decision-authority arms: deterministic validator, Qwen, Sol, Jev."""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Literal

import requests
from pydantic import BaseModel, Field, field_validator

from evidence_packet import assert_clean_for_models
from genome_skeptic.agents.providers import CALL_LOG, reset_call_log
from genome_skeptic.config import LLMConfig, load_settings
from sol_adapter import SolModelAdapter, estimate_sol_cost_usd
from jev_adapter import (
    JEV_ALIAS,
    TYPESAFE_URL,
    _api_key,
    _choice_entropy,
    _top_second,
    estimate_jev_cost_usd,
)

Endpoint = Literal["PRESENT", "ABSENT", "UNRESOLVED"]
Support = Literal["SUPPORTED", "NOT_SUPPORTED", "UNCERTAIN"]
YesNo = Literal["YES", "NO"]
LocusInterpretation = Literal["GENUINE_TARGET", "RELATED_NON_TARGET", "INSUFFICIENT_EVIDENCE"]

DECISION_SYSTEM = (
    "You are a biological decision authority for a bacterial AMR gene-family question. "
    "Based only on the supplied frozen evidence, decide whether the genome contains a "
    "genuine tet(A)/tet(B) family determinant. "
    "Allowed endpoint values: PRESENT, ABSENT, UNRESOLVED. "
    "Also return target_family_support, credible_competitor_support, evidence_sufficient, "
    "target_locus_interpretation, most_decisive_evidence_ids (at most 3 existing IDs), "
    "and a brief_evidence_summary of at most 2 sentences that refers only to evidence IDs. "
    "Do not request tools, analyses, BLAST, HMM, or follow-ups. "
    "Do not invent measurements or evidence IDs. "
    "Return only the required JSON object. Do not provide chain-of-thought."
)


class BiologicalDecision(BaseModel):
    endpoint: Endpoint
    target_family_support: Support
    credible_competitor_support: Support
    evidence_sufficient: YesNo
    target_locus_interpretation: LocusInterpretation = "INSUFFICIENT_EVIDENCE"
    most_decisive_evidence_ids: list[str] = Field(default_factory=list)
    brief_evidence_summary: str = Field(
        default="",
        description="At most 2 sentences; refer only to existing evidence IDs.",
    )
    self_reported_confidence: float = Field(
        default=0.0,
        description="SELF-REPORTED CONFIDENCE in [0,1]; not a calibrated probability.",
    )

    @field_validator("most_decisive_evidence_ids")
    @classmethod
    def _max_three(cls, value: list[str]) -> list[str]:
        return list(value or [])[:3]

    @field_validator("brief_evidence_summary")
    @classmethod
    def _brief(cls, value: str) -> str:
        text = (value or "").strip()
        # Cap length without inventing content.
        return text[:600]


def map_validator_endpoint(claim_type: str | None, status: str | None) -> Endpoint:
    ctype = str(claim_type or "")
    st = str(status or "")
    if st.endswith("unresolved") or st == "unresolved" or ctype.endswith("unresolved"):
        return "UNRESOLVED"
    if ctype in {"target_gene_detected", "POSITIVE", "PRESENT"}:
        return "PRESENT"
    if ctype in {"target_gene_not_detected", "NEGATIVE", "ABSENT"}:
        return "ABSENT"
    return "UNRESOLVED"


def map_family_support(family: dict[str, Any] | None, endpoint: Endpoint) -> Support:
    if not family:
        return "UNCERTAIN"
    competitive = family.get("competitive_family") or {}
    classification = str(competitive.get("classification") or "")
    if classification == "target_family_supported" or family.get("supports_orthologue") is True:
        return "SUPPORTED"
    if classification in {"competing_family_preferred", "domain_only"} or family.get("domain_only") is True:
        return "NOT_SUPPORTED"
    if classification in {"ambiguous_family", "unresolved_candidate"}:
        return "UNCERTAIN"
    if endpoint == "PRESENT":
        return "SUPPORTED"
    if endpoint == "ABSENT":
        return "NOT_SUPPORTED"
    return "UNCERTAIN"


def map_competitor_support(family: dict[str, Any] | None) -> Support:
    if not family:
        return "UNCERTAIN"
    competitive = family.get("competitive_family") or {}
    classification = str(competitive.get("classification") or "")
    if classification == "competing_family_preferred":
        return "SUPPORTED"
    if classification == "target_family_supported":
        return "NOT_SUPPORTED"
    if classification in {"ambiguous_family", "unresolved_candidate"}:
        scored = competitive.get("competitors_scored") or []
        if scored:
            return "UNCERTAIN"
        return "NOT_SUPPORTED"
    if classification == "domain_only":
        return "UNCERTAIN"
    return "UNCERTAIN"


def validate_evidence_ids(ids: list[str] | None, valid: set[str]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    invalid: list[str] = []
    for eid in ids or []:
        if eid in valid:
            if eid not in kept:
                kept.append(eid)
        else:
            invalid.append(eid)
    return kept[:3], invalid


def classify_mechanism(row: dict[str, Any]) -> str:
    """Classify rescue/failure mechanism from structured outputs only."""
    issues = count_internal_inconsistencies(row)
    endpoint = row.get("endpoint")
    family = row.get("target_family_support")
    competitor = row.get("credible_competitor_support")
    sufficient = row.get("evidence_sufficient")
    if issues:
        return "E. INTERNAL_INCONSISTENCY"
    if (
        family == "SUPPORTED"
        and competitor != "SUPPORTED"
        and endpoint == "PRESENT"
    ):
        return "A. TARGET_RECOGNIZED"
    if competitor == "SUPPORTED" and endpoint in {"ABSENT", "UNRESOLVED"}:
        return "B. COMPETITOR_DOMINATED"
    if family in {"UNCERTAIN", "NOT_SUPPORTED"} and endpoint != "PRESENT":
        return "C. TARGET_EVIDENCE_JUDGED_INSUFFICIENT"
    if sufficient == "NO" and endpoint == "UNRESOLVED":
        return "D. CONSERVATIVE_ABSTENTION"
    return "F. OTHER_STRUCTURED_PATTERN"


def count_internal_inconsistencies(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    endpoint = row.get("endpoint")
    family = row.get("target_family_support")
    competitor = row.get("credible_competitor_support")
    sufficient = row.get("evidence_sufficient")
    locus = row.get("target_locus_interpretation")
    if endpoint == "PRESENT" and family == "NOT_SUPPORTED":
        issues.append("PRESENT_with_family_NOT_SUPPORTED")
    if endpoint == "ABSENT" and family == "SUPPORTED" and competitor == "NOT_SUPPORTED":
        issues.append("ABSENT_with_family_SUPPORTED_and_competitor_NOT_SUPPORTED")
    if endpoint in {"PRESENT", "ABSENT"} and sufficient == "NO":
        issues.append("binary_endpoint_with_evidence_sufficient_NO")
    if endpoint == "UNRESOLVED" and sufficient == "YES" and family in {"SUPPORTED", "NOT_SUPPORTED"}:
        issues.append("UNRESOLVED_with_sufficient_YES")
    if endpoint == "PRESENT" and locus == "RELATED_NON_TARGET":
        issues.append("PRESENT_with_RELATED_NON_TARGET")
    if endpoint == "ABSENT" and locus == "GENUINE_TARGET":
        issues.append("ABSENT_with_GENUINE_TARGET")
    return issues


def deterministic_decision(
    *,
    claim: dict[str, Any] | None,
    family: dict[str, Any] | None,
    evidence_ids: list[str],
) -> dict[str, Any]:
    claim = claim or {}
    endpoint = map_validator_endpoint(claim.get("claim_type"), claim.get("status"))
    family_support = map_family_support(family, endpoint)
    competitor = map_competitor_support(family)
    sufficient: YesNo = "NO" if endpoint == "UNRESOLVED" else "YES"
    decisive = list(claim.get("supporting_evidence_ids") or [])[:3]
    if not decisive:
        decisive = list(evidence_ids)[:3]
    valid, invalid = validate_evidence_ids(decisive, set(evidence_ids))
    return {
        "system": "deterministic_validator",
        "endpoint": endpoint,
        "target_family_support": family_support,
        "credible_competitor_support": competitor,
        "evidence_sufficient": sufficient,
        "target_locus_interpretation": (
            "GENUINE_TARGET"
            if endpoint == "PRESENT"
            else ("RELATED_NON_TARGET" if endpoint == "ABSENT" else "INSUFFICIENT_EVIDENCE")
        ),
        "brief_evidence_summary": "",
        "most_decisive_evidence_ids": valid,
        "invalid_evidence_ids": invalid,
        "confidence": claim.get("confidence"),
        "endpoint_probability_present": None,
        "endpoint_probability_absent": None,
        "endpoint_probability_unresolved": None,
        "probability_margin": None,
        "entropy": None,
        "family_state": (family or {}).get("architecture"),
        "competitor_state": ((family or {}).get("competitive_family") or {}).get("classification"),
        "orthology_state": (family or {}).get("supports_orthologue"),
        "architecture_state": claim.get("architecture_state") or (family or {}).get("architecture"),
        "latency_s": 0.0,
        "input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
        "cost_usd": 0.0,
        "retries": 0,
        "provider_service_time_s": None,
        "request_id": None,
        "concrete_model": "V5_deterministic_validator",
        "raw": {"claim": claim},
    }


def _usage_from_call_log(call_log: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "latency_s": round(sum(float(r.get("elapsed_seconds") or 0) for r in call_log), 6),
        "input_tokens": sum(int(r.get("input_tokens") or 0) for r in call_log) or None,
        "output_tokens": sum(int(r.get("output_tokens") or 0) for r in call_log) or None,
        "reasoning_tokens": sum(int(r.get("reasoning_tokens") or 0) for r in call_log) or None,
        "cached_tokens": sum(int(r.get("cached_tokens") or 0) for r in call_log) or None,
        "cost_usd": round(sum(float(r.get("estimated_api_cost_usd") or 0) for r in call_log), 8),
        "retries": sum(int(r.get("retry_count") or 0) for r in call_log),
        "call_log": call_log,
    }


def qwen_decision(packet: dict[str, Any], *, settings_path) -> dict[str, Any]:
    assert_clean_for_models(packet, label="qwen:packet")
    settings = load_settings(settings_path)
    cfg = settings.llm.for_role("planner")
    override = os.environ.get("GENOME_SKEPTIC_OLLAMA_BASE_URL")
    if override:
        cfg.base_url = override
    cfg.max_output_tokens = max(int(cfg.max_output_tokens or 256), 512)
    reset_call_log()
    from genome_skeptic.agents.providers import ModelAdapter

    t0 = time.perf_counter()
    retries = 0
    last_err = None
    decision = None
    for attempt in range(2):
        try:
            client = ModelAdapter(cfg)
            decision = client.ask_json(DECISION_SYSTEM, packet, BiologicalDecision)
            break
        except Exception as exc:
            last_err = exc
            retries += 1
            if attempt == 1:
                raise
    latency = round(time.perf_counter() - t0, 6)
    usage = _usage_from_call_log(list(CALL_LOG))
    valid_ids = set(packet.get("valid_evidence_ids") or [])
    kept, invalid = validate_evidence_ids(decision.most_decisive_evidence_ids, valid_ids)
    return {
        "system": "qwen",
        "endpoint": decision.endpoint,
        "target_family_support": decision.target_family_support,
        "credible_competitor_support": decision.credible_competitor_support,
        "evidence_sufficient": decision.evidence_sufficient,
        "target_locus_interpretation": decision.target_locus_interpretation,
        "brief_evidence_summary": decision.brief_evidence_summary,
        "most_decisive_evidence_ids": kept,
        "invalid_evidence_ids": invalid,
        "confidence": decision.self_reported_confidence,
        "confidence_label": "SELF-REPORTED CONFIDENCE",
        "endpoint_probability_present": None,
        "endpoint_probability_absent": None,
        "endpoint_probability_unresolved": None,
        "probability_margin": None,
        "entropy": None,
        "latency_s": usage["latency_s"] or latency,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": usage["reasoning_tokens"],
        "cost_usd": 0.0,
        "retries": retries,
        "provider_service_time_s": None,
        "request_id": None,
        "concrete_model": "qwen3:4b",
        "raw": decision.model_dump(),
        "error": None if decision is not None else str(last_err),
    }


def sol_decision(packet: dict[str, Any], *, settings_path) -> dict[str, Any]:
    assert_clean_for_models(packet, label="sol:packet")
    settings = load_settings(settings_path)
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
    usage = _usage_from_call_log(list(CALL_LOG))
    valid_ids = set(packet.get("valid_evidence_ids") or [])
    kept, invalid = validate_evidence_ids(decision.most_decisive_evidence_ids, valid_ids)
    return {
        "system": "sol",
        "endpoint": decision.endpoint,
        "target_family_support": decision.target_family_support,
        "credible_competitor_support": decision.credible_competitor_support,
        "evidence_sufficient": decision.evidence_sufficient,
        "target_locus_interpretation": decision.target_locus_interpretation,
        "brief_evidence_summary": decision.brief_evidence_summary,
        "most_decisive_evidence_ids": kept,
        "invalid_evidence_ids": invalid,
        "confidence": decision.self_reported_confidence,
        "confidence_label": "SELF-REPORTED CONFIDENCE",
        "endpoint_probability_present": None,
        "endpoint_probability_absent": None,
        "endpoint_probability_unresolved": None,
        "probability_margin": None,
        "entropy": None,
        "latency_s": usage["latency_s"] or latency,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": usage["reasoning_tokens"],
        "cost_usd": usage["cost_usd"],
        "retries": retries,
        "provider_service_time_s": None,
        "request_id": (usage["call_log"][-1].get("response_id") if usage["call_log"] else None),
        "concrete_model": "gpt-5.6-sol",
        "raw": decision.model_dump(),
        "error": None if decision is not None else str(last_err),
    }


def _jev_post(state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
    assert_clean_for_models(state, label="jev:state")
    assert_clean_for_models(questions, label="jev:questions")
    body = {"state": state, "model": JEV_ALIAS, "questions": questions}
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    record: dict[str, Any] = {
        "request_number": len(CALL_LOG) + 1,
        "request_type": "BiologicalDecisionAuthority",
        "role": "decision",
        "provider": "typesafe_systemone",
        "model_alias": JEV_ALIAS,
        "model": JEV_ALIAS,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "url": TYPESAFE_URL,
        "retry_count": 0,
        "first_attempt": True,
        "n_questions": len(questions),
    }
    started = time.perf_counter()
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
    if not response.ok:
        record["error"] = response.text[:500]
        CALL_LOG.append(record)
        raise RuntimeError(f"TypeSafe HTTP {response.status_code}: {response.text[:300]}")
    payload = response.json()
    usage = payload.get("usage") or {}
    record["concrete_model"] = payload.get("model")
    record["model"] = payload.get("model") or JEV_ALIAS
    record["response_id"] = payload.get("id") or record.get("request_id")
    record["input_tokens"] = usage.get("input_tokens")
    record["output_tokens"] = usage.get("output_tokens")
    record["estimated_api_cost_usd"] = estimate_jev_cost_usd(
        usage.get("input_tokens"), usage.get("output_tokens")
    )
    record["answers"] = payload.get("answers")
    CALL_LOG.append(record)
    return payload


def jev_decision(packet: dict[str, Any]) -> dict[str, Any]:
    assert_clean_for_models(packet, label="jev:packet")
    valid_ids = [str(x) for x in (packet.get("valid_evidence_ids") or [])]
    # Choice limit is 255; keep evidence-ID selection only when practical.
    evidence_id_selection = "implemented" if 0 < len(valid_ids) <= 40 else "EVIDENCE_ID_SELECTION_NOT_TESTED"
    questions: dict[str, Any] = {
        "endpoint": {
            "type": "choice",
            "instructions": (
                "Based only on the supplied biological evidence, does this genome contain a "
                "genuine tet(A)/tet(B) family determinant?"
            ),
            "criteria": {
                "PRESENT": "The evidence supports a genuine tet(A)/tet(B) determinant.",
                "ABSENT": (
                    "The evidence supports that the observed locus is not a genuine "
                    "tet(A)/tet(B) determinant."
                ),
                "UNRESOLVED": (
                    "The supplied evidence does not support a reliable binary conclusion."
                ),
            },
        },
        "target_family_support": {
            "type": "choice",
            "instructions": (
                "Does the supplied evidence support that the candidate belongs to the "
                "tet(A)/tet(B) target family?"
            ),
            "criteria": {
                "SUPPORTED": "Target-family support is present in the measurements.",
                "NOT_SUPPORTED": "Target-family support is absent or vetoed.",
                "UNCERTAIN": "Target-family support cannot be reliably decided from the evidence.",
            },
        },
        "credible_competitor_support": {
            "type": "choice",
            "instructions": (
                "Does the supplied evidence support a credible competing non-target family "
                "explanation for the observed similarity?"
            ),
            "criteria": {
                "SUPPORTED": "A credible competitor family is supported.",
                "NOT_SUPPORTED": "No credible competitor family is supported.",
                "UNCERTAIN": "Competitor support cannot be reliably decided.",
            },
        },
        "target_locus_interpretation": {
            "type": "choice",
            "instructions": (
                "How should the strongest observed locus be interpreted biologically "
                "with respect to tet(A)/tet(B)?"
            ),
            "criteria": {
                "GENUINE_TARGET": "The locus is a genuine tet(A)/tet(B) family determinant.",
                "RELATED_NON_TARGET": (
                    "The locus is a related non-target protein rather than a genuine "
                    "tet(A)/tet(B) determinant."
                ),
                "INSUFFICIENT_EVIDENCE": (
                    "The supplied evidence is insufficient to interpret the locus as "
                    "genuine target or related non-target."
                ),
            },
        },
        "evidence_sufficient": {
            "type": "noul",
            "instructions": (
                "Is the supplied evidence sufficient to make a reliable PRESENT versus "
                "ABSENT biological decision?"
            ),
            "criteria": {
                "true": "Evidence is sufficient for a reliable PRESENT vs ABSENT decision.",
                "false": "Evidence is not sufficient for a reliable binary decision.",
            },
        },
    }
    if evidence_id_selection == "implemented":
        criteria = {eid: f"Evidence identifier present in packet: {eid}" for eid in valid_ids}
        criteria["NONE"] = "No decisive evidence identifier should be selected."
        for idx in (1, 2, 3):
            questions[f"MOST_DECISIVE_EVIDENCE_{idx}"] = {
                "type": "choice",
                "instructions": (
                    f"Select the #{idx} most decisive evidence ID already present in "
                    "`valid_evidence_ids`, or NONE."
                ),
                "criteria": criteria,
            }

    reset_call_log()
    t0 = time.perf_counter()
    payload = _jev_post(
        {
            "biological_evidence": packet,
            "target": packet.get("target"),
            "valid_evidence_ids": valid_ids,
        },
        questions,
    )
    latency = round(time.perf_counter() - t0, 6)
    answers = payload.get("answers") or {}
    endpoint_ans = answers.get("endpoint") or {}
    family_ans = answers.get("target_family_support") or {}
    competitor_ans = answers.get("credible_competitor_support") or {}
    locus_ans = answers.get("target_locus_interpretation") or {}
    noul_ans = answers.get("evidence_sufficient") or {}
    endpoint = str(endpoint_ans.get("choice") or "UNRESOLVED").upper()
    if endpoint not in {"PRESENT", "ABSENT", "UNRESOLVED"}:
        endpoint = "UNRESOLVED"
    family = str(family_ans.get("choice") or "UNCERTAIN").upper()
    competitor = str(competitor_ans.get("choice") or "UNCERTAIN").upper()
    locus = str(locus_ans.get("choice") or "INSUFFICIENT_EVIDENCE").upper()
    if locus not in {"GENUINE_TARGET", "RELATED_NON_TARGET", "INSUFFICIENT_EVIDENCE"}:
        locus = "INSUFFICIENT_EVIDENCE"
    noul = float(noul_ans.get("noul") if noul_ans.get("noul") is not None else 0.5)
    sufficient = "YES" if noul > 0.5 else "NO"
    probs = {str(k): float(v) for k, v in (endpoint_ans.get("probabilities") or {}).items()}
    top, second, margin = _top_second(probs)
    entropy = _choice_entropy(probs)
    decisive: list[str] = []
    invalid: list[str] = []
    if evidence_id_selection == "implemented":
        for idx in (1, 2, 3):
            choice = str(((answers.get(f"MOST_DECISIVE_EVIDENCE_{idx}") or {}).get("choice")) or "NONE")
            if choice == "NONE" or not choice:
                continue
            if choice in valid_ids and choice not in decisive:
                decisive.append(choice)
            elif choice not in valid_ids:
                invalid.append(choice)
    usage = _usage_from_call_log(list(CALL_LOG))
    provider_raw = usage["call_log"][-1].get("x_envoy_upstream_service_time") if usage["call_log"] else None
    provider_s = None
    if provider_raw is not None:
        try:
            val = float(provider_raw)
            provider_s = val / 1000.0 if val > 20 else val
        except (TypeError, ValueError):
            provider_s = None
    return {
        "system": "jev",
        "endpoint": endpoint,
        "target_family_support": family if family in {"SUPPORTED", "NOT_SUPPORTED", "UNCERTAIN"} else "UNCERTAIN",
        "credible_competitor_support": competitor
        if competitor in {"SUPPORTED", "NOT_SUPPORTED", "UNCERTAIN"}
        else "UNCERTAIN",
        "evidence_sufficient": sufficient,
        "target_locus_interpretation": locus,
        "brief_evidence_summary": "",
        "most_decisive_evidence_ids": decisive
        if evidence_id_selection == "implemented"
        else ["EVIDENCE_ID_SELECTION_NOT_TESTED"],
        "invalid_evidence_ids": invalid,
        "evidence_id_selection": evidence_id_selection,
        "confidence": float(endpoint_ans.get("confidence") or top or 0.0),
        "endpoint_probability_present": probs.get("PRESENT"),
        "endpoint_probability_absent": probs.get("ABSENT"),
        "endpoint_probability_unresolved": probs.get("UNRESOLVED"),
        "probability_margin": margin,
        "entropy": entropy,
        "family_support_probabilities": family_ans.get("probabilities"),
        "competitor_probabilities": competitor_ans.get("probabilities"),
        "locus_interpretation_probabilities": locus_ans.get("probabilities"),
        "evidence_sufficient_noul": noul,
        "latency_s": usage["latency_s"] or latency,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": None,
        "cost_usd": usage["cost_usd"],
        "retries": 0,
        "provider_service_time_s": provider_s,
        "request_id": usage["call_log"][-1].get("request_id") if usage["call_log"] else None,
        "concrete_model": payload.get("model") or JEV_ALIAS,
        "raw": answers,
    }
