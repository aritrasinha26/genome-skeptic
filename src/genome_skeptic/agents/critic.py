from __future__ import annotations

from genome_skeptic.agents.ollama import OllamaJSONClient
from genome_skeptic.agents.questions import ADVERSARIAL_QUESTIONS
from genome_skeptic.models import AgentDecision, Anomaly, CriticReview, Evidence


CRITIC_SYSTEM = """You are an adversarial scientific reviewer of a bacterial genome analysis.
Your goal is to try to prove the proposed decision wrong using the supplied evidence.
Look for unsupported assumptions, confounding, missing validators, circular reasoning, and plausible alternative explanations.
Do not invent data. Cite only supplied evidence IDs.
If the decision is adequately supported, accept it. Otherwise challenge it and state concrete disconfirming tests.
"""


def critique(client: OllamaJSONClient, stage: str, decision: AgentDecision, evidence: list[Evidence], anomalies: list[Anomaly]) -> CriticReview:
    payload = {
        "stage": stage,
        "proposed_decision": decision.model_dump(),
        "evidence": [e.model_dump() for e in evidence],
        "anomalies": [a.model_dump() for a in anomalies],
        "adversarial_questions": ADVERSARIAL_QUESTIONS.get(stage, []),
        "constraints": [
            "Cite only supplied evidence IDs.",
            "Try to falsify the proposed decision.",
            "Do not accept a leap from 'not detected in this assembly' to 'absent from the organism'.",
            "Do not treat supported as certainty.",
            "Do not invent orthologues, identities, gene order, or reciprocal hits.",
            "Do not invent taxonomy, tree placement, read support, or simulation truth.",
        ],
    }
    return client.ask_json(CRITIC_SYSTEM, payload, CriticReview)
