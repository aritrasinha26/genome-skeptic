"""Sol adapter tests. Do not change deterministic science; parser/validator stay production."""
from __future__ import annotations

import json

from pathlib import Path

from genome_skeptic.agents.assembly_loop_v2 import (
    critic_decision_to_review,
    planner_decision_to_agent,
)
from genome_skeptic.agents.assembly_loop_v2 import _validate_critic
from genome_skeptic.agents.assembly_loop_v4_1_dev import (
    AGENTIC_CRITIC_SYSTEM,
    AGENTIC_REASONER_SYSTEM,
    _validate_planner_v4_1_dev,
    select_critic_action_v4_1_dev,
)
from genome_skeptic.agents.ollama import OllamaJSONClient
from genome_skeptic.agents.providers import (
    CALL_LOG,
    ModelAdapter,
    OpenAIAPIProvider,
    SOL_ABLATION_ID,
    SOL_MODEL,
    SOL_PROVIDER,
    SOL_REASONING_EFFORT,
    openai_strict_schema,
    reset_call_log,
    sol_ablation_overlay,
)
from genome_skeptic.config import LLMConfig, load_settings
from genome_skeptic.models import CriticDecision, PlannerDecision

PLANNER_JSON = {
    "decision": "investigate",
    "leading_hypothesis": "target_present",
    "alternative_hypothesis": None,
    "evidence_ids": ["E001"],
    "requested_action": "search_target_proteins_mmseqs",
    "confidence": 0.5,
    "rationale": "Protein search can still change the measured state.",
}

CRITIC_JSON = {
    "verdict": "accept",
    "evidence_ids": ["E001"],
    "requested_action": None,
    "failure_mode": None,
    "rationale": "The planned measurement remains within the registered catalog.",
}

UNREGISTERED_JSON = {
    **PLANNER_JSON,
    "requested_action": "invent_a_new_instrument",
    "rationale": "This action is not registered.",
}


class _FakeUsage:
    input_tokens = 11
    output_tokens = 22
    total_tokens = 33

    class _Details:
        reasoning_tokens = 7

    output_tokens_details = _Details()


class _FakeResponse:
    def __init__(self, payload: dict, response_id: str = "resp_sol_test"):
        self.id = response_id
        self.status = "completed"
        self.output_text = json.dumps(payload)
        self.usage = _FakeUsage()
        self.output = []


class _FakeResponses:
    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payloads.pop(0)
        return _FakeResponse(payload, response_id=f"resp_{len(self.calls)}")


class _FakeClient:
    def __init__(self, payloads: list[dict]):
        self.responses = _FakeResponses(payloads)


def _sol_cfg() -> LLMConfig:
    return LLMConfig(
        enabled=True,
        provider="openai_api",
        model=SOL_MODEL,
        timeout_seconds=30,
        max_output_tokens=16000,
    )


def test_sol_model_uses_openai_api_provider_from_production_compatible_config():
    cfg = LLMConfig(provider="openai_compatible", model=SOL_MODEL)
    adapter = ModelAdapter(cfg)
    assert len(adapter.providers) == 1
    assert isinstance(adapter.providers[0], OpenAIAPIProvider)
    assert adapter.providers[0].model == SOL_MODEL


def test_sol_yaml_keeps_frozen_thresholds():
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "config" / "sol56_high_posthoc.yaml")
    from genome_skeptic.config import Settings

    frozen = Settings()
    assert settings.llm.model == SOL_MODEL
    assert settings.llm.provider == "openai_api"
    assert settings.thresholds.model_dump() == frozen.thresholds.model_dump()
    assert settings.execution.enable_critic is True
    assert settings.execution.allow_model_to_choose_actions is True


def test_openai_strict_schema_does_not_change_pydantic_models():
    raw = PlannerDecision.model_json_schema()
    strict = openai_strict_schema(raw)
    assert set(strict["required"]) == set(strict["properties"])
    assert PlannerDecision.model_json_schema() == raw
    again = PlannerDecision.model_validate(PLANNER_JSON)
    assert again.requested_action == "search_target_proteins_mmseqs"


def test_sol_planner_and_critic_use_production_parser_and_validator(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-secret")
    fake = _FakeClient([PLANNER_JSON, CRITIC_JSON])
    monkeypatch.setattr(
        "genome_skeptic.agents.providers._openai_client",
        lambda api_key, timeout: fake,
    )
    reset_call_log()
    client = OllamaJSONClient(_sol_cfg())
    planner_payload = {"valid_evidence_ids": ["E001"], "available_actions": ["search_target_proteins_mmseqs"]}
    planner = client.ask_json(AGENTIC_REASONER_SYSTEM, planner_payload, PlannerDecision)
    critic = client.ask_json(AGENTIC_CRITIC_SYSTEM, {"proposed": "x"}, CriticDecision)

    assert planner.requested_action == "search_target_proteins_mmseqs"
    agent = planner_decision_to_agent(planner)
    choice, grounding, control, fatal = _validate_planner_v4_1_dev(
        agent, {"E001"}, {"search_target_proteins_mmseqs"}
    )
    assert fatal is None
    assert control is None
    assert choice == "search_target_proteins_mmseqs"
    assert grounding == "GROUNDED"

    review = critic_decision_to_review(critic)
    ok, err = _validate_critic(review, {"E001"})
    assert err is None
    assert ok is not None
    second, reason = select_critic_action_v4_1_dev(ok, ["search_target_proteins_mmseqs"], ["search_target_proteins_mmseqs"])
    assert second is None
    assert "accepted" in reason

    assert fake.responses.calls[0]["model"] == SOL_MODEL
    assert fake.responses.calls[0]["reasoning"] == {"effort": SOL_REASONING_EFFORT}
    assert fake.responses.calls[0]["input"][0] == {"role": "system", "content": AGENTIC_REASONER_SYSTEM}
    assert fake.responses.calls[1]["input"][0] == {"role": "system", "content": AGENTIC_CRITIC_SYSTEM}
    user0 = fake.responses.calls[0]["input"][1]["content"]
    assert user0 == json.dumps(planner_payload, separators=(",", ":"), default=str)
    assert fake.responses.calls[0]["text"]["format"]["name"] == "PlannerDecision"
    assert fake.responses.calls[1]["text"]["format"]["name"] == "CriticDecision"

    roles = [row.get("role") for row in CALL_LOG]
    assert roles == ["planner", "critic"]
    for row in CALL_LOG:
        assert row["provider"] == SOL_PROVIDER
        assert row["model"] == SOL_MODEL
        assert row["reasoning_effort"] == SOL_REASONING_EFFORT
        assert row["schema_valid"] is True
        assert row["response_id"]
        assert "OPENAI_API_KEY" not in json.dumps(row)
        assert "sk-test" not in json.dumps(row)

    overlay = sol_ablation_overlay(CALL_LOG)
    assert overlay["POST_HOC_MODEL_ABLATION"] is True
    assert overlay["MANUSCRIPT_PRIMARY_SYSTEM"] is False
    assert overlay["ablation_config"] == SOL_ABLATION_ID
    assert overlay["sol_total_tokens"] == 66


def test_sol_unregistered_action_is_rejected_by_production_validator(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-secret")
    fake = _FakeClient([UNREGISTERED_JSON])
    monkeypatch.setattr(
        "genome_skeptic.agents.providers._openai_client",
        lambda api_key, timeout: fake,
    )
    reset_call_log()
    client = OllamaJSONClient(_sol_cfg())
    planner = client.ask_json(AGENTIC_REASONER_SYSTEM, {"x": 1}, PlannerDecision)
    agent = planner_decision_to_agent(planner)
    choice, _grounding, _control, fatal = _validate_planner_v4_1_dev(
        agent, {"E001"}, {"search_target_proteins_mmseqs"}
    )
    assert choice is None
    assert fatal == "planner requested an unregistered action: invent_a_new_instrument"


def test_missing_openai_key_fails_closed(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_call_log()
    adapter = ModelAdapter(_sol_cfg())
    try:
        adapter.ask_json(AGENTIC_REASONER_SYSTEM, {"x": 1}, PlannerDecision)
    except Exception as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("missing key must fail closed")
