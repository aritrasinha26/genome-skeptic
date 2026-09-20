from __future__ import annotations

import json
from typing import Type, TypeVar

import requests
from pydantic import BaseModel

from genome_skeptic.config import LLMConfig

T = TypeVar("T", bound=BaseModel)


class OllamaJSONClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def ask_json(self, system: str, user_payload: dict, schema: Type[T]) -> T:
        provider = (self.cfg.provider or "").strip().lower()
        if provider == "openai_compatible":
            from genome_skeptic.agents.providers import ModelAdapter

            return ModelAdapter(self.cfg).ask_json(system, user_payload, schema)
        url = self.cfg.base_url.rstrip("/") + "/api/chat"
        prompt = (
            "Return only valid JSON matching this JSON schema. Do not add markdown.\n"
            + json.dumps(schema.model_json_schema(), indent=2)
            + "\n\nEvidence payload:\n"
            + json.dumps(user_payload, indent=2)
        )
        body = {
            "model": self.cfg.model,
            "stream": False,
            "options": {
                "temperature": self.cfg.temperature,
                "num_predict": int(getattr(self.cfg, "max_output_tokens", None) or 256),
            },
            "think": False if getattr(self.cfg, "thinking", None) is None else bool(self.cfg.thinking),
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        keep_alive = getattr(self.cfg, "keep_alive", None)
        if keep_alive:
            body["keep_alive"] = keep_alive
        r = requests.post(url, json=body, timeout=self.cfg.timeout_seconds)
        r.raise_for_status()
        raw = r.json()["message"]["content"]
        return schema.model_validate_json(raw)
