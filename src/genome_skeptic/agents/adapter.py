"""OpenAI-compatible and Ollama JSON adapters. Models are not substituted silently."""
from __future__ import annotations

import json
from typing import Type, TypeVar

import requests
from pydantic import BaseModel

from genome_skeptic.config import LLMConfig
from genome_skeptic.models import AgentDecision, CriticReview

T = TypeVar("T", bound=BaseModel)


KNOWN_MODELS = {
    "qwen": ["qwen3:8b", "qwen3:14b", "qwen2.5:7b", "qwen2.5:14b"],
    "deepseek": ["deepseek-r1:8b", "deepseek-r1:7b", "deepseek-r1-distill-qwen-7b", "deepseek-r1-distill-llama-8b"],
}


class ModelUnavailable(RuntimeError):
    pass


class ModelAdapter:
    def __init__(self, cfg: LLMConfig, model: str | None = None):
        self.cfg = cfg
        self.model = model or cfg.model
        self.base_url = cfg.base_url.rstrip("/")
        self.last_mode: str | None = None

    def ask_json(self, system: str, user_payload: dict, schema: Type[T]) -> T:
        prompt = (
            "Return only valid JSON matching this JSON schema. Do not add markdown.\n"
            + json.dumps(schema.model_json_schema(), indent=2)
            + "\n\nEvidence payload:\n"
            + json.dumps(user_payload, indent=2, default=str)
        )
        errors = []
        try:
            raw = self._chat_completions(system, prompt)
            self.last_mode = "openai_compatible"
            return schema.model_validate_json(raw)
        except Exception as exc:
            errors.append(f"openai_compatible: {exc}")
        try:
            raw = self._ollama_chat(system, prompt)
            self.last_mode = "ollama"
            return schema.model_validate_json(raw)
        except Exception as exc:
            errors.append(f"ollama: {exc}")
        raise ModelUnavailable(f"model {self.model} unavailable: {errors}")

    def _chat_completions(self, system: str, prompt: str) -> str:
        url = self.base_url + "/v1/chat/completions"
        body = {
            "model": self.model,
            "temperature": self.cfg.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        r = requests.post(url, json=body, timeout=self.cfg.timeout_seconds)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _ollama_chat(self, system: str, prompt: str) -> str:
        url = self.base_url + "/api/chat"
        body = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        r = requests.post(url, json=body, timeout=self.cfg.timeout_seconds)
        r.raise_for_status()
        return r.json()["message"]["content"]


def list_local_models(base_url: str, timeout: int = 8) -> list[str]:
    base = base_url.rstrip("/")
    names: list[str] = []
    try:
        r = requests.get(base + "/api/tags", timeout=timeout)
        if r.ok:
            for row in (r.json().get("models") or []):
                n = row.get("name") or row.get("model")
                if n:
                    names.append(str(n))
    except Exception:
        pass
    try:
        r = requests.get(base + "/v1/models", timeout=timeout)
        if r.ok:
            for row in (r.json().get("data") or []):
                n = row.get("id")
                if n:
                    names.append(str(n))
    except Exception:
        pass
    return list(dict.fromkeys(names))


def resolve_named_model(kind: str, available: list[str]) -> str | None:
    wanted = KNOWN_MODELS.get(kind) or []
    lower = {n.lower(): n for n in available}
    for cand in wanted:
        if cand.lower() in lower:
            return lower[cand.lower()]
        for name, orig in lower.items():
            if cand.split(":")[0] in name or kind in name:
                return orig
    return None


def run_planner_critic(
    adapter_planner: ModelAdapter,
    adapter_critic: ModelAdapter,
    *,
    stage: str,
    evidence: list,
    anomalies: list,
    registered_actions: list[str],
) -> dict:
    from genome_skeptic.agents.questions import ADVERSARIAL_QUESTIONS
    from genome_skeptic.agents.reasoner import REASONER_SYSTEM
    from genome_skeptic.agents.critic import CRITIC_SYSTEM

    payload = {
        "stage": stage,
        "evidence": [e.model_dump() if hasattr(e, "model_dump") else e for e in evidence],
        "anomalies": [a.model_dump() if hasattr(a, "model_dump") else a for a in anomalies],
        "registered_actions": registered_actions,
        "adversarial_questions": ADVERSARIAL_QUESTIONS.get(stage, []),
        "constraints": [
            "Cite only supplied evidence IDs.",
            "Do not invent measurements.",
            "Do not convert not-detected into organism-level absence.",
            "Requested actions must come only from registered_actions.",
        ],
    }
    decision: AgentDecision = adapter_planner.ask_json(REASONER_SYSTEM, payload, AgentDecision)
    critic_payload = dict(payload)
    critic_payload["proposed_decision"] = decision.model_dump()
    critic: CriticReview = adapter_critic.ask_json(CRITIC_SYSTEM, critic_payload, CriticReview)
    evidence_ids = {e.id if hasattr(e, "id") else e.get("id") for e in evidence}
    unsupported = [i for i in (decision.evidence_ids or []) if i not in evidence_ids]
    unregistered = [a for a in (decision.requested_actions or []) if a not in registered_actions]
    critic_bad = [i for i in (critic.evidence_ids or []) if i not in evidence_ids]
    return {
        "planner_model": adapter_planner.model,
        "critic_model": adapter_critic.model,
        "planner_transport": adapter_planner.last_mode,
        "critic_transport": adapter_critic.last_mode,
        "decision": decision.model_dump(),
        "critic": critic.model_dump(),
        "unsupported_evidence_citations": unsupported + critic_bad,
        "registered_action_violations": unregistered,
    }
