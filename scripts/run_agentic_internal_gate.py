#!/usr/bin/env python3
"""Run the frozen 6-case internal genome_skeptic_agentic gate once.

Does not modify the agent, V5 science, Cohort A, or external labels.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.assembly_loop import SYSTEM_NAME, run_skeptic_agentic
from genome_skeptic.agents.providers import extract_json_text
from genome_skeptic.config import load_settings
from genome_skeptic.io_utils import iter_fasta_records
from genome_skeptic.orchestrator import REGISTERED_ACTIONS

MANIFEST = ROOT / "dev_work" / "agentic_gate" / "agentic_internal_gate_manifest.json"
LOCK = ROOT / "dev_work" / "agentic_gate" / "agentic_internal_gate_manifest.sha256.json"
OUT = ROOT / "dev_work" / "agentic_gate" / "runs"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_one_target(src_fa: Path, dest_fa: Path, query_id: str) -> None:
    chosen = [(header, seq) for seq_id, header, seq in iter_fasta_records(src_fa) if seq_id == query_id]
    if not chosen:
        raise SystemExit(f"target {query_id} not found in {src_fa}")
    dest_fa.parent.mkdir(parents=True, exist_ok=True)
    header, seq = chosen[0]
    dest_fa.write_text(f">{header}\n{seq}\n", encoding="utf-8")


def _parse_excerpt(raw: str) -> dict:
    text = extract_json_text(raw or "") or (raw or "")
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _invalid_from_calls(call_log: list, known_ids: set[str], registered: set[str]) -> tuple[list[str], list[str]]:
    bad_e: list[str] = []
    bad_a: list[str] = []
    for row in call_log or []:
        obj = _parse_excerpt(row.get("raw_excerpt") or "")
        for eid in obj.get("evidence_ids") or []:
            if eid not in known_ids:
                bad_e.append(str(eid))
        for act in obj.get("requested_actions") or []:
            if act not in registered:
                bad_a.append(str(act))
    return list(dict.fromkeys(bad_e)), list(dict.fromkeys(bad_a))


def evaluate_case(case: dict, provenance: dict, claim) -> dict:
    graph = provenance.get("call_graph") or []
    before = list(provenance.get("evidence_ids_before_action") or [])
    after = list(provenance.get("evidence_ids_after_action") or provenance.get("evidence_ids") or [])
    known = set(after or before)
    planner_ids = list(provenance.get("cited_evidence_ids") or [])
    critic_ids = list(provenance.get("critic_cited_evidence_ids") or [])
    action = provenance.get("selected_action")
    call_log = []
    log_path = OUT / case["case_id"] / SYSTEM_NAME / "call_log.json"
    if log_path.exists():
        call_log = json.loads(log_path.read_text(encoding="utf-8"))
    invalid_e, invalid_a = _invalid_from_calls(call_log, known, set(REGISTERED_ACTIONS))
    repairs = sum(1 for step in graph if str(step).endswith("_repair"))
    final_class = (claim.architecture_state if claim is not None else None) or None
    expected = case["expected_v5_class"]
    checks = {
        "A_planner_invoked": provenance.get("planner_invoked") is True,
        "B_critic_invoked": provenance.get("critic_invoked") is True,
        "C_qwen_invoked": int(provenance.get("model_call_count") or 0) > 0,
        "D_planner_ids_valid": bool(planner_ids) and all(eid in known for eid in planner_ids),
        "E_critic_ids_valid": bool(critic_ids) and all(eid in known for eid in critic_ids),
        "F_action_registered": bool(action) and action in REGISTERED_ACTIONS,
        "G_action_executed": any(str(step).startswith("execute_registered_action:") for step in graph),
        "H_new_evidence": len(after) > len(before),
        "I_no_llm_measurement_in_claim": provenance.get("llm_measurement_entered_claim") is False,
        "J_validator_final_authority": provenance.get("final_validator_ran") is True,
        "K_no_silent_deterministic_fallback": provenance.get("agent_failure") is None and provenance.get("planner_invoked") is True,
        "L_matches_frozen_v5_class": final_class == expected,
    }
    critic = provenance.get("critic_challenge") or {}
    return {
        "case": case["case_id"],
        "role": case["role"],
        "target": case["target"],
        "expected_class": expected,
        "expected_claim_type": case["expected_claim_type"],
        "planner_calls": provenance.get("planner_model_call_count"),
        "critic_calls": provenance.get("critic_model_call_count"),
        "model_calls": provenance.get("model_call_count"),
        "action_selected": action,
        "new_evidence_ids": [eid for eid in after if eid not in before],
        "evidence_ids_before": before,
        "evidence_ids_after": after,
        "critic_verdict": critic.get("verdict"),
        "final_class": final_class,
        "final_claim_type": claim.claim_type.value if claim is not None else None,
        "final_status": claim.status.value if claim is not None else None,
        "matches_expected": checks["L_matches_frozen_v5_class"],
        "invalid_evidence_attempts": invalid_e,
        "invalid_action_attempts": invalid_a,
        "repairs": repairs,
        "runtime": provenance.get("seconds"),
        "agent_failure": provenance.get("agent_failure"),
        "checks": checks,
        "process_pass": all(v for k, v in checks.items() if k != "L_matches_frozen_v5_class") and checks["L_matches_frozen_v5_class"],
        "call_graph": graph,
    }


def main() -> int:
    if not LOCK.exists():
        raise SystemExit("manifest was not hashed before execution")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    digest = sha256_file(MANIFEST)
    if digest != lock.get("sha256"):
        raise SystemExit(f"manifest hash mismatch: {digest} != {lock.get('sha256')}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    settings = load_settings(ROOT / "config" / "qwen_agentic_dev.yaml")
    rows = []
    t0 = time.perf_counter()
    for case in manifest["cases"]:
        case_out = OUT / case["case_id"]
        case_out.mkdir(parents=True, exist_ok=True)
        one_target = case_out / f"{case['target']}.fa"
        write_one_target(ROOT / case["targets_source"], one_target, case["target"])
        print(f"GATE START {case['case_id']} {case['target']}", flush=True)
        claims, _loci, provenance = run_skeptic_agentic(
            ROOT / case["assembly"],
            one_target,
            case_out / SYSTEM_NAME,
            settings,
            query_ids=[case["target"]],
        )
        claim = claims[0] if claims else None
        row = evaluate_case(case, provenance, claim)
        (case_out / "gate_case.json").write_text(json.dumps(row, indent=2, default=str), encoding="utf-8")
        rows.append(row)
        print(f"GATE DONE {case['case_id']} process_pass={row['process_pass']} class={row['final_class']}", flush=True)
    total_s = round(time.perf_counter() - t0, 3)
    actions = [r["action_selected"] for r in rows if r["action_selected"]]
    n_ok = sum(1 for r in rows if r["process_pass"])
    report = {
        "system": SYSTEM_NAME,
        "manifest_sha256": digest,
        "n_cases": len(rows),
        "n_pass": n_ok,
        "gate": "PASS" if n_ok == 6 else "FAIL",
        "total_model_calls": sum(int(r.get("model_calls") or 0) for r in rows),
        "total_runtime_seconds": total_s,
        "n_distinct_registered_actions": len(set(actions)),
        "distinct_registered_actions": sorted(set(actions)),
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    (OUT.parent / "agentic_internal_gate_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("gate", "n_pass", "total_model_calls", "total_runtime_seconds", "distinct_registered_actions")}, indent=2))
    return 0 if n_ok == 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
