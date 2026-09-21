"""Planner/critic providers. Scientific claims stay deterministic across swaps."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Protocol, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from genome_skeptic.config import LLMConfig

T = TypeVar("T", bound=BaseModel)

KNOWN = {
    "qwen3": ["qwen3:8b", "qwen3:14b", "qwen3:32b", "qwen2.5:7b", "qwen2.5:14b"],
    "deepseek-r1-distill": [
        "deepseek-r1:8b",
        "deepseek-r1:7b",
        "deepseek-r1-distill-qwen-7b",
        "deepseek-r1-distill-llama-8b",
        "deepseek-r1-distill-qwen-14b",
    ],
    "gpt": ["gpt-5.6-sol", "gpt-4o", "gpt-4.1", "gpt-4o-mini", "gpt-5"],
    "local": [],
}

CALL_LOG: list[dict[str, Any]] = []

SOL_MODEL = "gpt-5.6-sol"
SOL_PROVIDER = "openai"
SOL_REASONING_EFFORT = "high"
SOL_ABLATION_ID = "GS_AGENTIC_V4_1_SOL56_HIGH_POSTHOC"
SOL_INPUT_USD_PER_MILLION = 4.0
SOL_OUTPUT_USD_PER_MILLION = 20.0
SOL_MIN_OUTPUT_TOKENS = 8192


class ModelUnavailable(RuntimeError):
    pass


class ChatProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str, **kwargs) -> str: ...


def reset_call_log() -> None:
    CALL_LOG.clear()


def ollama_root(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base[: -len("/v1")]
    return base


def native_chat_url(base_url: str) -> str:
    return ollama_root(base_url) + "/api/chat"


def chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def models_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/models"
    return base + "/v1/models"


def extract_json_text(raw: str) -> str:
    """Strip thinking tags and fences. Does not invent a scientific payload."""
    import re

    text = (raw or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def auth_headers(cfg: LLMConfig) -> dict:
    key = getattr(cfg, "api_key", None)
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


def constrained_schema(model: Type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    defs = schema.pop("$defs", None) or schema.pop("definitions", None)
    if defs:
        schema["$defs"] = defs
    return _additional_properties_false(schema)


def _additional_properties_false(node: Any) -> Any:
    if isinstance(node, dict):
        out = {k: _additional_properties_false(v) for k, v in node.items()}
        if out.get("type") == "object":
            out.setdefault("additionalProperties", False)
        return out
    if isinstance(node, list):
        return [_additional_properties_false(v) for v in node]
    return node


def _est_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _cfg_thinking(cfg: LLMConfig) -> bool | None:
    return getattr(cfg, "thinking", None)


def _cfg_keep_alive(cfg: LLMConfig) -> str | None:
    return getattr(cfg, "keep_alive", None)


def _cfg_max_tokens(cfg: LLMConfig) -> int:
    value = getattr(cfg, "max_output_tokens", None)
    return int(value) if value else 256


def _openai_api_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
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
    if "repair" in kind.lower() and "critic" in kind.lower():
        return "critic"
    if "repair" in kind.lower() and "planner" in kind.lower():
        return "planner"
    return "unknown"


def openai_strict_schema(schema: dict | None) -> dict | None:
    """Adapter-only OpenAI strict wrapper. Does not change Planner/Critic Pydantic models."""
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
            "total_tokens": None,
        }
    if isinstance(usage, dict):
        details = usage.get("output_tokens_details") or usage.get("output_token_details") or {}
        reasoning = None
        if isinstance(details, dict):
            reasoning = details.get("reasoning_tokens")
        return {
            "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens"),
            "output_tokens": usage.get("output_tokens") or usage.get("completion_tokens"),
            "reasoning_tokens": reasoning,
            "total_tokens": usage.get("total_tokens"),
        }
    details = getattr(usage, "output_tokens_details", None) or getattr(usage, "output_token_details", None)
    reasoning = getattr(details, "reasoning_tokens", None) if details is not None else None
    return {
        "input_tokens": getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None),
        "reasoning_tokens": reasoning,
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def estimate_sol_cost_usd(
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    if input_tokens is None and output_tokens is None:
        return None
    inp = int(input_tokens or 0)
    out = int(output_tokens or 0)
    return round(
        (inp / 1_000_000) * SOL_INPUT_USD_PER_MILLION
        + (out / 1_000_000) * SOL_OUTPUT_USD_PER_MILLION,
        6,
    )


def sol_ablation_overlay(call_log: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = list(call_log if call_log is not None else CALL_LOG)
    sol_calls = []
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    total_tokens = 0
    for row in rows:
        inp = int(row.get("input_tokens") or 0)
        out = int(row.get("output_tokens") or 0)
        rea = int(row.get("reasoning_tokens") or 0)
        tot = int(row.get("total_tokens") or (inp + out))
        input_tokens += inp
        output_tokens += out
        reasoning_tokens += rea
        total_tokens += tot
        sol_calls.append(
            {
                "provider": row.get("provider") or SOL_PROVIDER,
                "model": row.get("model"),
                "reasoning_effort": row.get("reasoning_effort"),
                "request_timestamp": row.get("start_time"),
                "wall_clock_latency_seconds": row.get("elapsed_seconds"),
                "input_tokens": row.get("input_tokens"),
                "output_tokens": row.get("output_tokens"),
                "reasoning_tokens": row.get("reasoning_tokens"),
                "total_tokens": row.get("total_tokens"),
                "response_id": row.get("response_id"),
                "role": row.get("role") or _role_from_request_type(str(row.get("request_type") or "")),
                "parse_success": row.get("schema_valid"),
                "retry_count": row.get("retry_count", 0),
            }
        )
    return {
        "POST_HOC_MODEL_ABLATION": True,
        "MANUSCRIPT_PRIMARY_SYSTEM": False,
        "ablation_config": SOL_ABLATION_ID,
        "llm_provider": SOL_PROVIDER,
        "llm_model": SOL_MODEL,
        "reasoning_effort": SOL_REASONING_EFFORT,
        "sol_calls": sol_calls,
        "sol_input_tokens": input_tokens,
        "sol_output_tokens": output_tokens,
        "sol_reasoning_tokens": reasoning_tokens,
        "sol_total_tokens": total_tokens,
        "estimated_api_cost_usd": estimate_sol_cost_usd(input_tokens, output_tokens),
    }


def _openai_client(api_key: str, timeout_seconds: int):
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout_seconds)


def _response_text(resp: Any) -> str:
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text
    chunks: list[str] = []
    for item in getattr(resp, "output", None) or []:
        if isinstance(item, dict):
            contents = item.get("content") or []
        else:
            contents = getattr(item, "content", None) or []
        for content in contents:
            if isinstance(content, dict):
                if content.get("type") in {"output_text", "text"}:
                    chunks.append(content.get("text") or "")
            else:
                if getattr(content, "type", None) in {"output_text", "text"}:
                    chunks.append(getattr(content, "text", "") or "")
    return "".join(chunks)


def _log_request(record: dict[str, Any]) -> None:
    print(
        "[LLM request {n}] type={t} prompt_chars={p} est_tokens={e} schema={s} "
        "max_output_tokens={m} thinking={th} start={start}".format(
            n=record["request_number"],
            t=record["request_type"],
            p=record["prompt_chars"],
            e=record["estimated_tokens"],
            s=record.get("schema") or "none",
            m=record["max_output_tokens"],
            th=record["thinking"],
            start=record["start_time"],
        ),
        file=sys.stderr,
        flush=True,
    )


def _log_response(record: dict[str, Any]) -> None:
    print(
        "[LLM response {n}] elapsed_s={el} finish_reason={fr} response_chars={rc} "
        "schema_valid={sv} retry_count={rt} load_s={ld}".format(
            n=record["request_number"],
            el=record.get("elapsed_seconds"),
            fr=record.get("finish_reason"),
            rc=record.get("response_chars"),
            sv=record.get("schema_valid"),
            rt=record.get("retry_count", 0),
            ld=record.get("load_duration_seconds"),
        ),
        file=sys.stderr,
        flush=True,
    )


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, cfg: LLMConfig, model: str):
        self.cfg = cfg
        self.model = model
        self.base_url = cfg.base_url.rstrip("/")

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
        url = native_chat_url(self.base_url)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        thinking = _cfg_thinking(self.cfg)
        max_tokens = _cfg_max_tokens(self.cfg)
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": messages,
            "options": {"temperature": self.cfg.temperature, "num_predict": max_tokens},
        }
        if thinking is None:
            body["think"] = False
        else:
            body["think"] = bool(thinking)
        keep_alive = _cfg_keep_alive(self.cfg)
        if keep_alive:
            body["keep_alive"] = keep_alive
        if json_schema:
            body["format"] = json_schema
        else:
            body["format"] = "json"
        prompt_chars = len(system) + len(user)
        record = {
            "request_number": len(CALL_LOG) + 1,
            "request_type": request_type + ("_repair" if repair else ""),
            "prompt_chars": prompt_chars,
            "estimated_tokens": _est_tokens(system + user),
            "schema": schema_name if json_schema else None,
            "max_output_tokens": max_tokens,
            "thinking": False if thinking is None else thinking,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "retry_count": 1 if repair else 0,
            "url": url,
        }
        _log_request(record)
        started = time.perf_counter()
        try:
            r = requests.post(url, json=body, headers=auth_headers(self.cfg), timeout=self.cfg.timeout_seconds)
            r.raise_for_status()
            payload = r.json()
            message = payload.get("message") or {}
            content = message.get("content") or ""
            finish = payload.get("done_reason")
            load = payload.get("load_duration")
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            record["finish_reason"] = finish
            record["response_chars"] = len(content or "")
            record["load_duration_seconds"] = round(load / 1e9, 3) if isinstance(load, (int, float)) else None
            record["raw_excerpt"] = (content or "")[:300]
            text = extract_json_text(content)
            record["schema_valid"] = None
            CALL_LOG.append(record)
            _log_response(record)
            if not text.strip():
                raise RuntimeError("empty structured content")
            return text
        except Exception:
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            if record not in CALL_LOG:
                CALL_LOG.append(record)
                _log_response(record)
            raise


class OllamaProvider:
    name = "ollama"

    def __init__(self, cfg: LLMConfig, model: str):
        self.cfg = cfg
        self.model = model
        self.base_url = cfg.base_url.rstrip("/")

    def complete_json(self, system: str, user: str, **kwargs) -> str:
        url = self.base_url + "/api/chat"
        if self.base_url.endswith("/v1"):
            url = self.base_url[: -len("/v1")] + "/api/chat"
        max_tokens = _cfg_max_tokens(self.cfg)
        thinking = _cfg_thinking(self.cfg)
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": self.cfg.temperature, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        json_schema = kwargs.get("json_schema")
        body["format"] = json_schema if json_schema else "json"
        if thinking is None:
            body["think"] = False
        else:
            body["think"] = bool(thinking)
        keep_alive = _cfg_keep_alive(self.cfg)
        if keep_alive:
            body["keep_alive"] = keep_alive
        r = requests.post(url, json=body, timeout=self.cfg.timeout_seconds)
        r.raise_for_status()
        return r.json()["message"]["content"]


class OpenAIAPIProvider:
    """Official OpenAI Responses API. Used only when the configured model/provider selects OpenAI."""

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
            raise ModelUnavailable("OPENAI_API_KEY is not configured; GPT was not substituted with a local model")
        sol = _is_sol_model(self.model)
        reasoning_effort = SOL_REASONING_EFFORT if sol else None
        max_tokens = _cfg_max_tokens(self.cfg)
        if sol and max_tokens < SOL_MIN_OUTPUT_TOKENS:
            max_tokens = SOL_MIN_OUTPUT_TOKENS
        role = _role_from_request_type(request_type)
        prompt_chars = len(system) + len(user)
        record: dict[str, Any] = {
            "request_number": len(CALL_LOG) + 1,
            "request_type": request_type + ("_repair" if repair else ""),
            "role": role,
            "provider": SOL_PROVIDER,
            "model": self.model,
            "reasoning_effort": reasoning_effort,
            "prompt_chars": prompt_chars,
            "estimated_tokens": _est_tokens(system + user),
            "schema": schema_name if json_schema else None,
            "max_output_tokens": max_tokens,
            "thinking": None,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "retry_count": 1 if repair else 0,
            "url": "https://api.openai.com/v1/responses",
        }
        _log_request(record)
        started = time.perf_counter()
        try:
            client = _openai_client(self.api_key, int(self.cfg.timeout_seconds))
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
            resp = client.responses.create(**body)
            content = _response_text(resp)
            usage = _usage_tokens(getattr(resp, "usage", None))
            status = getattr(resp, "status", None)
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            record["finish_reason"] = status
            record["response_chars"] = len(content or "")
            record["raw_excerpt"] = (content or "")[:300]
            record["response_id"] = getattr(resp, "id", None)
            record["input_tokens"] = usage["input_tokens"]
            record["output_tokens"] = usage["output_tokens"]
            record["reasoning_tokens"] = usage["reasoning_tokens"]
            record["total_tokens"] = usage["total_tokens"]
            record["estimated_api_cost_usd"] = estimate_sol_cost_usd(
                usage["input_tokens"], usage["output_tokens"]
            )
            record["schema_valid"] = None
            CALL_LOG.append(record)
            _log_response(record)
            if status and status not in {"completed", "complete"}:
                raise RuntimeError(f"OpenAI response status={status}")
            if not (content or "").strip():
                raise RuntimeError("empty structured content")
            return content
        except Exception:
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            if record not in CALL_LOG:
                CALL_LOG.append(record)
                _log_response(record)
            raise


class DryRunProvider:
    """Validates adapter wiring without inventing scientific conclusions."""

    name = "dry_run"

    def __init__(self, model: str):
        self.model = model

    def complete_json(self, system: str, user: str, **kwargs) -> str:
        raise ModelUnavailable(f"dry-run only; model {self.model} was not invoked and no output was invented")


def list_local_models(base_url: str, timeout: int = 8) -> list[str]:
    base = base_url.rstrip("/")
    names: list[str] = []
    paths = [("/api/tags", "models"), ("/v1/models", "data"), ("/models", "data")]
    extra_bases = [base]
    if base.endswith("/v1"):
        extra_bases.append(base[: -len("/v1")])
    for host in extra_bases:
        for path, key in paths:
            try:
                r = requests.get(host + path, timeout=timeout)
                if not r.ok:
                    continue
                blob = r.json()
                rows = blob.get(key) or blob.get("models") or blob.get("data") or []
                for row in rows:
                    n = row.get("name") or row.get("model") or row.get("id")
                    if n:
                        names.append(str(n))
            except Exception:
                pass
    return list(dict.fromkeys(names))


def resolve_named_model(kind: str, available: list[str]) -> str | None:
    wanted = list(KNOWN.get(kind) or [])
    lower = {n.lower(): n for n in available}
    for cand in wanted:
        if cand.lower() in lower:
            return lower[cand.lower()]
        stem = cand.split(":")[0]
        for name, orig in lower.items():
            if stem in name or kind.replace("-", "") in name.replace("-", ""):
                return orig
    if kind == "gpt":
        import os
        if os.environ.get("OPENAI_API_KEY") or os.environ.get("GENOME_SKEPTIC_OPENAI_API_KEY"):
            return wanted[0] if wanted else "gpt-4o"
        return None
    if kind == "local" and available:
        return available[0]
    return None


def hardware_estimate() -> dict:
    info: dict = {"nvidia_smi": None, "ollama": None, "notes": []}
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"],
                text=True,
                timeout=8,
            )
            info["nvidia_smi"] = out.strip()
        except Exception as exc:
            info["notes"].append(f"nvidia-smi failed: {exc}")
    else:
        info["notes"].append("nvidia-smi not on PATH; VRAM estimate unavailable")
    try:
        r = requests.get("http://localhost:11434/api/ps", timeout=3)
        if r.ok:
            info["ollama"] = r.json()
    except Exception:
        info["notes"].append("Ollama /api/ps not reachable")
    info["expected_vram_gb"] = {
        "qwen3:8b": "~8–12 GB",
        "qwen3:14b": "~12–18 GB",
        "deepseek-r1:8b": "~8–12 GB",
        "deepseek-r1-distill-qwen-7b": "~8–12 GB",
    }
    return info


def setup_instructions(available: list[str]) -> dict:
    return {
        "openai_compatible": "Serve an OpenAI-compatible /v1/chat/completions endpoint (vLLM, llama.cpp server, Ollama with OpenAI API).",
        "ollama": "Install Ollama and pull models, e.g. `ollama pull qwen3:8b` and `ollama pull deepseek-r1:8b`.",
        "gpt": "Set OPENAI_API_KEY. GPT is optional and is never used as a substitute for missing Qwen/DeepSeek weights.",
        "expected_model_names": KNOWN,
        "available_now": available,
        "no_silent_substitution": True,
    }


class ModelAdapter:
    def __init__(self, cfg: LLMConfig, model: str | None = None, *, dry_run: bool = False):
        self.cfg = cfg
        self.model = model or cfg.model
        self.dry_run = dry_run
        self.last_mode: str | None = None
        self.providers: list[ChatProvider]
        provider = (cfg.provider or "").strip().lower()
        if dry_run:
            self.providers = [DryRunProvider(self.model)]
        elif provider in {"openai_api", "openai"} or self.model.lower().startswith("gpt"):
            self.providers = [OpenAIAPIProvider(cfg, self.model)]
        elif provider == "openai_compatible":
            self.providers = [OpenAICompatibleProvider(cfg, self.model)]
        elif provider == "ollama":
            self.providers = [OllamaProvider(cfg, self.model)]
        else:
            self.providers = [
                OpenAICompatibleProvider(cfg, self.model),
                OllamaProvider(cfg, self.model),
            ]

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
                self.last_mode = prov.name
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
                    self.last_mode = prov.name
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


def run_planner_critic(adapter_planner: ModelAdapter, adapter_critic: ModelAdapter, **kwargs) -> dict:
    from genome_skeptic.agents.adapter import run_planner_critic as _run

    return _run(adapter_planner, adapter_critic, **kwargs)


def dry_run_adapter(cfg: LLMConfig, kind: str) -> dict:
    available = list_local_models(cfg.base_url)
    resolved = resolve_named_model(kind, available)
    hw = hardware_estimate()
    return {
        "kind": kind,
        "resolved_model": resolved,
        "available_models": available,
        "endpoint_reachable": bool(available),
        "would_call": bool(resolved),
        "invented_output": False,
        "hardware": hw,
        "setup": setup_instructions(available),
        "note": "Dry-run does not call the model and does not invent planner/critic JSON.",
    }
