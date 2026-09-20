#!/usr/bin/env python3
"""One internal smoke test for genome_skeptic_agentic.

Uses existing FAST_PILOT development genome dev_01 / rpoB gene_orthologue.
Does not run Cohort A, benchmarks, or inspect external labels.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.assembly_loop import SYSTEM_NAME, run_skeptic_agentic
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
    out_dir = ROOT / "dev_work" / "agentic_smoke"
    if not assembly.exists():
        raise SystemExit(f"missing internal development assembly: {assembly}")
    if not src_targets.exists():
        raise SystemExit(f"missing internal development targets: {src_targets}")
    out_dir.mkdir(parents=True, exist_ok=True)
    one_target = out_dir / "rpoB.fa"
    _write_one_target(src_targets, one_target, query_id)
    settings = load_settings(ROOT / "config" / "qwen_agentic_dev.yaml")
    claims, loci, provenance = run_skeptic_agentic(
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
    after = provenance.get("evidence_ids_after_action") or provenance.get("evidence_ids") or []
    checks = [
        _require(bool(before), "deterministic_evidence_created", before),
        _require(provenance.get("planner_invoked") is True, "planner_qwen_call", provenance.get("planner_model_call_count")),
        _require(bool(provenance.get("cited_evidence_ids")), "planner_cited_evidence", provenance.get("cited_evidence_ids")),
        _require(all(eid in set(before + after) for eid in (provenance.get("cited_evidence_ids") or [])), "planner_evidence_ids_valid", provenance.get("cited_evidence_ids")),
        _require(bool(provenance.get("selected_action")), "registered_action_chosen", provenance.get("selected_action")),
        _require(any(str(step).startswith("execute_registered_action:") for step in graph), "deterministic_action_executed", [s for s in graph if str(s).startswith("execute_registered_action:")]),
        _require(len(after) > len(before), "new_evidence_added", {"before": before, "after": after}),
        _require(provenance.get("critic_invoked") is True, "critic_qwen_call", provenance.get("critic_model_call_count")),
        _require(bool(provenance.get("critic_cited_evidence_ids")), "critic_cited_evidence", provenance.get("critic_cited_evidence_ids")),
        _require(all(eid in set(after) for eid in (provenance.get("critic_cited_evidence_ids") or [])), "critic_evidence_ids_valid", provenance.get("critic_cited_evidence_ids")),
        _require(provenance.get("final_validator_ran") is True, "final_deterministic_validator_ran", provenance.get("final_claim_state")),
        _require(bool(claims), "final_claim_produced", [c.claim_id for c in claims]),
        _require(provenance.get("agent_failure") is None, "no_agent_failure", provenance.get("agent_failure")),
        _require(provenance.get("llm_measurement_entered_claim") is False, "no_llm_measurement_in_claim", provenance.get("llm_measurement_entered_claim")),
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
        "evidence_ids_before_action": before,
        "evidence_ids_after_action": after,
        "final_claim_state": provenance.get("final_claim_state"),
        "llm_measurement_entered_claim": provenance.get("llm_measurement_entered_claim"),
        "total_runtime_seconds": provenance.get("seconds"),
        "agent_failure": provenance.get("agent_failure"),
        "checks": checks,
    }
    (out_dir / "smoke_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
