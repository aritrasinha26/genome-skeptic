#!/usr/bin/env python3
"""One internal smoke test for genome_skeptic_agentic_v2.

Uses existing FAST_PILOT development genome dev_01 / rpoB gene_orthologue.
Does not run Cohort A, benchmarks, or inspect external labels.

Beyond the V1 execution checks, this asserts the V2 property that V1 lacked:
the measured state handed to the final validator is auditable, and whenever an
action reports INFORMATIVE the measurement fingerprint must actually have moved.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.action_contract import ActionStatus
from genome_skeptic.agents.assembly_loop_v2 import SYSTEM_NAME, run_skeptic_agentic_v2
from genome_skeptic.config import load_settings
from genome_skeptic.io_utils import iter_fasta_records


def _write_one_target(src_fa: Path, dest_fa: Path, query_id: str) -> None:
    chosen = [(header, seq) for seq_id, header, seq in iter_fasta_records(src_fa) if seq_id == query_id]
    if not chosen:
        raise SystemExit(f"target {query_id} not found in {src_fa}")
    dest_fa.parent.mkdir(parents=True, exist_ok=True)
    header, seq = chosen[0]
    dest_fa.write_text(f">{header}\n{seq}\n", encoding="utf-8")


def _require(ok: bool, name: str, detail) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> int:
    query_id = "rpoB"
    assembly = ROOT / "benchmarks" / "real_genomes_fast_pilot_dev_eval" / "dev_01" / "production" / "spades" / "contigs.fasta"
    src_targets = ROOT / "benchmarks" / "real_genomes_fast_pilot_dev" / "agent_visible" / "dev_01" / "targets.fa"
    refs = ROOT / "benchmarks" / "real_genomes_fast_pilot_dev" / "agent_visible" / "dev_01" / "references.yaml"
    out_dir = ROOT / "dev_work" / "agentic_v2_smoke"
    if not assembly.exists():
        raise SystemExit(f"missing internal development assembly: {assembly}")
    if not src_targets.exists():
        raise SystemExit(f"missing internal development targets: {src_targets}")
    out_dir.mkdir(parents=True, exist_ok=True)
    one_target = out_dir / "rpoB.fa"
    _write_one_target(src_targets, one_target, query_id)
    settings = load_settings(ROOT / "config" / "qwen_agentic_dev.yaml")
    claims, _loci, provenance = run_skeptic_agentic_v2(
        assembly,
        one_target,
        out_dir / SYSTEM_NAME,
        settings,
        references=refs if refs.exists() else None,
        declared_organism="Escherichia coli",
        query_ids=[query_id],
    )
    graph = provenance.get("call_graph") or []
    before = provenance.get("evidence_ids_before_action") or []
    after = provenance.get("evidence_ids") or []
    executed = provenance.get("actions_executed") or []
    trajectory = provenance.get("measurement_trajectory") or []
    states = provenance.get("measurement_state") or {}
    control = provenance.get("control_decision")

    informative_moved_the_state = all(
        step["measurement_state_changed"]
        for step in trajectory
        if step["status"] == ActionStatus.informative.value
    )
    inert_left_the_state_alone = all(
        not step["measurement_state_changed"]
        for step in trajectory
        if step["status"] != ActionStatus.informative.value
    )

    checks = [
        _require(bool(before), "deterministic_evidence_created", before),
        _require(provenance.get("planner_invoked") is True, "planner_qwen_call", provenance.get("planner_model_call_count")),
        _require(bool(provenance.get("cited_evidence_ids")), "planner_cited_evidence", provenance.get("cited_evidence_ids")),
        _require(
            all(eid in set(after) for eid in (provenance.get("cited_evidence_ids") or [])),
            "planner_evidence_ids_valid",
            provenance.get("cited_evidence_ids"),
        ),
        _require(
            bool(provenance.get("selected_action")) or bool(control),
            "planner_made_a_registered_choice",
            {"action": provenance.get("selected_action"), "control_decision": control},
        ),
        _require(
            bool(control) or any(str(step).startswith("execute_registered_action:") for step in graph),
            "deterministic_action_executed",
            [s for s in graph if str(s).startswith("execute_registered_action:")],
        ),
        _require(len(after) > len(before), "new_evidence_added", {"n_before": len(before), "n_after": len(after)}),
        _require(provenance.get("critic_invoked") is True, "critic_qwen_call", provenance.get("critic_model_call_count")),
        _require(bool(provenance.get("critic_cited_evidence_ids")), "critic_cited_evidence", provenance.get("critic_cited_evidence_ids")),
        _require(provenance.get("final_validator_ran") is True, "final_deterministic_validator_ran", provenance.get("final_claim_state")),
        _require(bool(claims), "final_claim_produced", [c.claim_id for c in claims]),
        _require(provenance.get("agent_failure") is None, "no_agent_failure", provenance.get("agent_failure")),
        _require(provenance.get("llm_measurement_entered_claim") is False, "no_llm_measurement_in_claim", None),
        # V2-specific: the action contract must be honest about what it achieved.
        _require(all(step.get("status") for step in executed), "every_action_reported_a_status", [s["status"] for s in executed]),
        _require(informative_moved_the_state, "informative_actions_changed_the_measured_state", trajectory),
        _require(inert_left_the_state_alone, "non_informative_actions_changed_nothing", trajectory),
        _require(
            provenance.get("planner_chose_unavailable_action") is False,
            "planner_did_not_choose_an_unavailable_action",
            provenance.get("available_actions"),
        ),
    ]
    passed = all(c["ok"] for c in checks)
    report = {
        "system": SYSTEM_NAME,
        "genome": "fast_pilot_dev_01",
        "target": query_id,
        "passed": passed,
        "call_graph": graph,
        "planner_model_call_count": provenance.get("planner_model_call_count"),
        "critic_model_call_count": provenance.get("critic_model_call_count"),
        "model_call_count": provenance.get("model_call_count"),
        "repair_count": provenance.get("repair_count"),
        "action_executed": provenance.get("selected_action"),
        "control_decision": control,
        "critic_second_action": provenance.get("critic_second_action"),
        "action_status_counts": provenance.get("action_status_counts"),
        "informative_action_count": provenance.get("informative_action_count"),
        "measurements_changed_before_validation": provenance.get("measurements_changed_before_validation"),
        "measurement_state": states,
        "measurement_trajectory": trajectory,
        "available_actions": provenance.get("available_actions"),
        "final_claim_state": provenance.get("final_claim_state"),
        "total_runtime_seconds": provenance.get("seconds"),
        "agent_failure": provenance.get("agent_failure"),
        "checks": checks,
    }
    (out_dir / "smoke_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
