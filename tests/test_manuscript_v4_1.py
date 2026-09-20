"""Shared scientific core and manuscript follow-up arms for V4.1."""
from pathlib import Path

from genome_skeptic.agents.assembly_loop_v4_1_dev import (
    POLICY_AGENTIC,
    POLICY_DETERMINISTIC,
    POLICY_EXHAUSTIVE,
    run_gs_agentic_v4_1,
    run_gs_deterministic_v4_1,
    run_gs_exhaustive_v4_1,
)
from genome_skeptic.config import Settings
from genome_skeptic.manuscript.scientific_core import assert_shared_scientific_core, scientific_core_hashes


def _write_case(tmp_path: Path) -> tuple[Path, Path]:
    from genome_skeptic.eval.synthetic import DNAA, RPOB, RPOC, _fa, _operon

    seq, _genes = _operon([("dnaA", DNAA), ("rpoB", RPOB), ("rpoC", RPOC)])
    assembly = tmp_path / "assembly.fa"
    assembly.write_text(_fa({"c1": seq}))
    targets = tmp_path / "targets.fa"
    targets.write_text(f">rpoB\n{RPOB}\n")
    return assembly, targets


def _fit_schema(schema, data: dict):
    payload = dict(data)
    if "requested_actions" in payload and "requested_action" not in payload:
        acts = payload.get("requested_actions") or []
        payload["requested_action"] = acts[0] if acts else None
    dec = payload.get("decision")
    if dec in {"continue", "rerun"}:
        payload["decision"] = "investigate"
    fields = getattr(schema, "model_fields", payload)
    return schema.model_validate({k: v for k, v in payload.items() if k in fields})


def test_scientific_core_hashes_are_identical_across_arms():
    hashes = scientific_core_hashes()
    core = hashes["scientific_core_hash"]
    assert len(core) == 64
    again = scientific_core_hashes()
    shared_keys = (
        "initial_measurement_code_hash",
        "reference_assets_hash",
        "family_definitions_hash",
        "target_measurements_schema_hash",
        "validator_hash",
        "biological_thresholds_hash",
        "action_registry_hash",
        "endpoint_contracts_hash",
        "scientific_core_hash",
    )
    for key in shared_keys:
        assert hashes[key] == again[key]
        assert hashes[key]
    policies = hashes["follow_up_policy_hashes"]
    assert policies[POLICY_DETERMINISTIC] != policies[POLICY_AGENTIC]
    assert policies[POLICY_EXHAUSTIVE] != policies[POLICY_AGENTIC]
    assert policies[POLICY_DETERMINISTIC] != policies[POLICY_EXHAUSTIVE]
    assert assert_shared_scientific_core()["scientific_core_hash"] == core


def test_deterministic_and_exhaustive_share_m0_and_validator(tmp_path):
    assembly, targets = _write_case(tmp_path)
    settings = Settings()
    settings.llm.enabled = False
    det_claims, _det_loci, det = run_gs_deterministic_v4_1(
        assembly, targets, tmp_path / "det", settings, query_ids=["rpoB"]
    )
    exh_claims, _exh_loci, exh = run_gs_exhaustive_v4_1(
        assembly, targets, tmp_path / "exh", settings, query_ids=["rpoB"]
    )
    assert det["follow_up_policy"] == POLICY_DETERMINISTIC
    assert exh["follow_up_policy"] == POLICY_EXHAUSTIVE
    assert det["measurement_state"]["m0"]["hash"] == exh["measurement_state"]["m0"]["hash"]
    assert det["planner_invoked"] is False
    assert exh["planner_invoked"] is False
    assert det["final_validator_ran"] is True
    assert exh["final_validator_ran"] is True
    assert det_claims[0].provenance.created_by == "deterministic_validator"
    assert exh_claims[0].provenance.created_by == "deterministic_validator"
    assert det["system"] == "genome_skeptic_deterministic_v4_1"
    assert exh["system"] == "genome_skeptic_exhaustive_v4_1"
    det_n = len(det.get("actions_executed") or [])
    exh_n = len(exh.get("actions_executed") or [])
    assert exh_n >= det_n


def test_agentic_arm_uses_same_core_and_planner_critic(tmp_path, monkeypatch):
    class _Stub:
        def __init__(self, cfg):
            self.cfg = cfg

        def ask_json(self, system, payload, schema):
            if schema.__name__ in {"AgentDecision", "PlannerDecision"}:
                rows = payload.get("available_actions") or []
                action = rows[0]["action_id"] if rows else "FINALIZE_WITH_CURRENT_EVIDENCE"
                return _fit_schema(
                    schema,
                    {
                        "decision": "continue",
                        "rationale": "stub",
                        "evidence_ids": [payload["valid_evidence_ids"][0]],
                        "requested_actions": [action],
                    },
                )
            return _fit_schema(
                schema,
                {"verdict": "accept", "rationale": "stub", "evidence_ids": [payload["valid_evidence_ids"][0]]},
            )

    assembly, targets = _write_case(tmp_path)
    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v4_1_dev.OllamaJSONClient", _Stub)
    claims, _loci, prov = run_gs_agentic_v4_1(
        assembly, targets, tmp_path / "ag", Settings(), query_ids=["rpoB"]
    )
    assert prov["follow_up_policy"] == POLICY_AGENTIC
    assert prov["system"] == "genome_skeptic_agentic_v4_1"
    assert prov["final_validator_ran"] is True
    assert claims[0].provenance.created_by == "deterministic_validator"
    assert prov["llm_measurement_entered_claim"] is False
    core = scientific_core_hashes()
    assert prov["prompt_hash"]
    assert core["planner_prompt_hash"]
    assert core["critic_prompt_hash"]
