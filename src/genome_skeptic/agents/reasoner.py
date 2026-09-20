from __future__ import annotations

from genome_skeptic.agents.ollama import OllamaJSONClient
from genome_skeptic.agents.questions import ADVERSARIAL_QUESTIONS
from genome_skeptic.models import AgentDecision, Evidence, Anomaly


REASONER_SYSTEM = """You are the scientific reasoning component of a bacterial genome assembly agent.
Your job is not to praise a completed workflow. Your job is to decide whether the evidence justifies continuing.
Use only the supplied evidence. Never invent measurements. Cite evidence IDs exactly.
Actively consider alternative explanations for every anomaly. Prefer a test that can distinguish explanations over a narrative guess.
A successful tool exit is not evidence that a biological conclusion is correct.
Do not convert 'not observed' into 'absent'. If evidence is insufficient, choose ask_human or rerun.
Requested actions must come only from the supplied registered_actions list.
"""


def reason(client: OllamaJSONClient, stage: str, evidence: list[Evidence], anomalies: list[Anomaly], registered_actions: list[str]) -> AgentDecision:
    payload = {
        "stage": stage,
        "evidence": [e.model_dump() for e in evidence],
        "anomalies": [a.model_dump() for a in anomalies],
        "registered_actions": registered_actions,
        "adversarial_questions": ADVERSARIAL_QUESTIONS.get(stage, []),
        "constraints": [
            "Cite only supplied evidence IDs.",
            "Do not invent measurements.",
            "Do not convert not-detected or not-observed into organism-level absence.",
            "Supported is not certainty.",
            "Do not invent orthologues, identities, gene order, or reciprocal hits.",
            "Do not invent taxonomy, tree placement, read support, or simulation truth.",
        ],
    }
    return client.ask_json(REASONER_SYSTEM, payload, AgentDecision)
