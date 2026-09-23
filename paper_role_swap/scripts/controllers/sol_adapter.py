"""Harness-only GPT-5.6 Sol adapter. Does not modify frozen providers.py."""
from __future__ import annotations

import copy
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from genome_skeptic.agents.providers import (
    CALL_LOG,
    DryRunProvider,
    ModelUnavailable,
    OpenAICompatibleProvider,
    OllamaProvider,
    _est_tokens,
    constrained_schema,
    extract_json_text,
)
from genome_skeptic.config import LLMConfig

T = TypeVar("T", bound=BaseModel)

SOL_MODEL = "gpt-5.6-sol"
SOL_REASONING_EFFORT = "high"
SOL_MIN_OUTPUT_TOKENS = 8192
SOL_INPUT_USD_PER_MILLION = 4.0
SOL_CACHED_INPUT_USD_PER_MILLION = 0.40
SOL_OUTPUT_USD_PER_MILLION = 20.0
SOL_PRICING_SOURCE = "https://help.openai.com/en/articles/20001415-chatgpt-rate-card-enterprise-token-based-pricing"
SOL_PRICING_DATE = "2026-09-22"
SOL_PRICING_NOTE = (
    "GPT-5.6 Sol promotional API price through at least 2026-11-21: "
    "$4.00 / $0.40 cached / $20.00 output per million tokens. "
    "Reasoning tokens are billed as output."
)


def _openai_api_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GENOME_SKEPTIC_OPENAI_API_KEY")
    return key.strip() if isinstance(key, str) and key.strip() else None


def _is_sol_model(model: str) -> bool:
    name = (model or "").strip().lower()
    return name == SOL_MODEL or name.startswith("gpt-5.6-sol") or name == "gpt-5.6"


def _role_from_request_type(request_type: str) -> str:
    kind = str(request_type or "")
    if kind.startswith(("AgentDecision", "PlannerDecision")):
        return "planner"
    if kind.startswith(("CriticReview", "CriticDecision")):
        return "critic"
    return "unknown"


def openai_strict_schema(schema: dict | None) -> dict | None:
    if not schema:
        return None
    node = copy.deepcopy(schema)

    def _walk(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                _walk(child)
            return
        if not isinstance(item, dict):
            return
        for key in ("$defs", "definitions", "properties"):
            blob = item.get(key)
            if isinstance(blob, dict):
                for child in blob.values():
                    _walk(child)
        for key in ("items", "not"):
            if key in item:
                _walk(item[key])
        for key in ("anyOf", "oneOf", "allOf"):
            if key in item:
                _walk(item[key])
        if item.get("type") == "object" or "properties" in item:
            props = item.get("properties") or {}
            item["additionalProperties"] = False
            if props:
                item["required"] = list(props.keys())
                item.setdefault("type", "object")

    _walk(node)
    return node


def _usage_tokens(usage: Any) -> dict[str, int | None]:
    if usage is None:
        return {
            "input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "cached_tokens": None,
            "total_tokens": None,
        }
    if isinstance(usage, dict):
        details = usage.get("output_tokens_details") or usage.get("output_token_details") or {}
        input_details = usage.get("input_tokens_details") or usage.get("input_token_details") or {}
        reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
        cached = input_details.get("cached_tokens") if isinstance(input_details, dict) else None
        return {
            "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens"),
            "output_tokens": usage.get("output_tokens") or usage.get("completion_tokens"),
            "reasoning_tokens": reasoning,
            "cached_tokens": cached or usage.get("cached_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    return {
        "input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
        "cached_tokens": None,
        "total_tokens": None,
    }


def estimate_sol_cost_usd(
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None = None,
) -> float | None:
    if input_tokens is None and output_tokens is None and cached_tokens is None:
        return None
    inp = int(input_tokens or 0)
    cached = min(int(cached_tokens or 0), inp)
    uncached = max(0, inp - cached)
    out = int(output_tokens or 0)
    return round(
        (uncached / 1_000_000) * SOL_INPUT_USD_PER_MILLION
        + (cached / 1_000_000) * SOL_CACHED_INPUT_USD_PER_MILLION
        + (out / 1_000_000) * SOL_OUTPUT_USD_PER_MILLION,
        8,
    )


def _response_text(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text") or "")
    return "".join(chunks)


class OpenAIResponsesProvider:
    """Existing V5 Sol adapter behaviour, loaded only by the POC harness."""

    name = "openai_api"

    def __init__(self, cfg: LLMConfig, model: str):
        self.cfg = cfg
        self.model = model
        self.api_key = _openai_api_key()

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        schema_name: str = "object",
        request_type: str = "complete_json",
        repair: bool = False,
    ) -> str:
        if not self.api_key:
            raise ModelUnavailable("OPENAI_API_KEY is not configured")
        sol = _is_sol_model(self.model)
        reasoning_effort = SOL_REASONING_EFFORT if sol else None
        max_tokens = int(getattr(self.cfg, "max_output_tokens", None) or 256)
        if sol and max_tokens < SOL_MIN_OUTPUT_TOKENS:
            max_tokens = SOL_MIN_OUTPUT_TOKENS
        role = _role_from_request_type(request_type)
        record: dict[str, Any] = {
            "request_number": len(CALL_LOG) + 1,
            "request_type": request_type + ("_repair" if repair else ""),
            "role": role,
            "provider": "openai_api",
            "model": self.model,
            "reasoning_effort": reasoning_effort,
            "prompt_chars": len(system) + len(user),
            "estimated_tokens": _est_tokens(system + user),
            "schema": schema_name if json_schema else None,
            "max_output_tokens": max_tokens,
            "thinking": None,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "retry_count": 1 if repair else 0,
            "url": "https://api.openai.com/v1/responses",
            "first_attempt": not repair,
        }
        started = time.perf_counter()
        try:
            body: dict[str, Any] = {
                "model": self.model,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_output_tokens": max_tokens,
            }
            if reasoning_effort:
                body["reasoning"] = {"effort": reasoning_effort}
            if json_schema:
                body["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name or "object",
                        "strict": True,
                        "schema": openai_strict_schema(json_schema),
                    }
                }
            else:
                body["text"] = {"format": {"type": "json_object"}}
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=self.cfg.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = _response_text(payload)
            usage = _usage_tokens(payload.get("usage"))
            status = payload.get("status")
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            record["finish_reason"] = status
            record["response_chars"] = len(content or "")
            record["raw_excerpt"] = (content or "")[:300]
            record["response_id"] = payload.get("id")
            record["http_status"] = response.status_code
            record["input_tokens"] = usage["input_tokens"]
            record["output_tokens"] = usage["output_tokens"]
            record["reasoning_tokens"] = usage["reasoning_tokens"]
            record["cached_tokens"] = usage["cached_tokens"]
            record["total_tokens"] = usage["total_tokens"]
            record["estimated_api_cost_usd"] = estimate_sol_cost_usd(
                usage["input_tokens"], usage["output_tokens"], usage["cached_tokens"]
            )
            record["pricing_source"] = SOL_PRICING_SOURCE
            record["pricing_date"] = SOL_PRICING_DATE
            record["schema_valid"] = None
            CALL_LOG.append(record)
            if status and status not in {"completed", "complete"}:
                raise RuntimeError(f"OpenAI response status={status}")
            if not (content or "").strip():
                raise RuntimeError("empty structured content")
            return content
        except Exception:
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            if record not in CALL_LOG:
                CALL_LOG.append(record)
            raise


class SolModelAdapter:
    def __init__(self, cfg: LLMConfig, model: str | None = None, *, dry_run: bool = False):
        self.cfg = cfg
        self.model = model or cfg.model
        provider = (cfg.provider or "").strip().lower()
        if dry_run:
            self.providers = [DryRunProvider(self.model)]
        elif provider in {"openai_api", "openai"} or str(self.model).lower().startswith("gpt"):
            self.providers = [OpenAIResponsesProvider(cfg, self.model)]
        elif provider == "openai_compatible":
            self.providers = [OpenAICompatibleProvider(cfg, self.model)]
        elif provider == "ollama":
            self.providers = [OllamaProvider(cfg, self.model)]
        else:
            self.providers = [OpenAIResponsesProvider(cfg, self.model)]

    def ask_json(
        self,
        system: str,
        user_payload: dict,
        schema: Type[T],
        *,
        request_type: str | None = None,
    ) -> T:
        schema_dict = constrained_schema(schema)
        user = json.dumps(user_payload, separators=(",", ":"), default=str)
        kind = request_type or schema.__name__
        errors: list[str] = []
        for prov in self.providers:
            try:
                raw = prov.complete_json(
                    system,
                    user,
                    json_schema=schema_dict,
                    schema_name=schema.__name__,
                    request_type=kind,
                )
                parsed = schema.model_validate_json(extract_json_text(raw) or raw)
                if CALL_LOG:
                    CALL_LOG[-1]["schema_valid"] = True
                return parsed
            except (ValidationError, json.JSONDecodeError, ValueError, TypeError, RuntimeError) as exc:
                errors.append(f"{prov.name}: {exc}")
                if CALL_LOG:
                    CALL_LOG[-1]["schema_valid"] = False
                try:
                    repair_user = (
                        user
                        + "\nPrevious output was invalid. Return one JSON object matching the schema. No prose."
                    )
                    raw = prov.complete_json(
                        system,
                        repair_user,
                        json_schema=schema_dict,
                        schema_name=schema.__name__,
                        request_type=kind,
                        repair=True,
                    )
                    parsed = schema.model_validate_json(extract_json_text(raw) or raw)
                    if CALL_LOG:
                        CALL_LOG[-1]["schema_valid"] = True
                    return parsed
                except Exception as repair_exc:
                    errors.append(f"{prov.name}_repair: {repair_exc}")
                    if CALL_LOG:
                        CALL_LOG[-1]["schema_valid"] = False
                    break
            except Exception as exc:
                errors.append(f"{prov.name}: {exc}")
                if CALL_LOG:
                    CALL_LOG[-1]["schema_valid"] = False
                break
        raise ModelUnavailable(f"model {self.model} unavailable; fail-closed: {errors}")
