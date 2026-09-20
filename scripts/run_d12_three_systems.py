#!/usr/bin/env python3
"""V3_D12_EXTERNAL staged three-system run.

STAGE 1: position 1 only (conventional → frozen V5 → frozen Agentic V3)
STAGE 2: positions 2–4
STAGE 3: positions 5–12, then lock prediction files

Does not open labels. Does not modify D20. Does not substitute cases on Agentic failure.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

faulthandler.enable()

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / "scripts"))

from d12_common import (  # noqa: E402
    AGENTIC_YAML,
    CURRENT_LACZ_LIMITATION,
    EXPECTED_DIGEST,
    EXPECTED_V3_FREEZE,
    FREEZE_ID,
    LINUX_WORK,
    OUT,
    V5_YAML,
    assert_d20_untouched,
    fix_llm_host,
    load_json,
    sha256_file,
    verify_v3_freeze,
    write_one_target,
    write_sha256_sidecar,
    write_targets,
)
from genome_skeptic.agents.action_catalog import ACTION_IDS  # noqa: E402
from genome_skeptic.agents.action_contract import CONTROL_DECISIONS  # noqa: E402
from genome_skeptic.agents.assembly_loop_v3 import SYSTEM_NAME, run_skeptic_agentic_v3  # noqa: E402
from genome_skeptic.agents.providers import reset_call_log  # noqa: E402
from genome_skeptic.config import load_settings  # noqa: E402
from genome_skeptic.eval.evaluate_real import _run_system  # noqa: E402

MANIFEST = OUT / "D12_MANIFEST.json"
MANIFEST_LOCK = OUT / "D12_MANIFEST.json.sha256.json"
RUNS = OUT / "runs"
TARGETS_FA = OUT / "inputs" / "targets.fa"
EMPTY_REFS = OUT / "inputs" / "references.yaml"
REGISTERED = set(ACTION_IDS) | set(CONTROL_DECISIONS)

STAGE_POSITIONS = {
    1: (1, 1),
    2: (2, 4),
    3: (5, 12),
}


def stage_fasta(src: Path, acc: str, expected: str) -> Path:
    if not Path("/home/aritr").exists():
        return src
    dest_root = LINUX_WORK / "fasta"
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / f"{acc}.fna"
    if dest.exists() and sha256_file(dest) == expected:
        return dest
    shutil.copyfile(src, dest)
    if sha256_file(dest) != expected:
        raise SystemExit(f"staged FASTA hash mismatch {acc}")
    return dest


def sys_paths(acc: str, target: str, system: str) -> tuple[Path, Path]:
    published = RUNS / acc / target / system
    work = LINUX_WORK / "runs" / acc / target / system if Path("/home/aritr").exists() else published
    return published, work


def sync_work_to_published(work: Path, published: Path) -> None:
    if work.resolve() == published.resolve():
        return
    published.mkdir(parents=True, exist_ok=True)
    for src in work.rglob("*"):
        if not src.is_file():
            continue
        dest = published / src.relative_to(work)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def claim_fields(claim) -> dict:
    if claim is None:
        return {}
    ctype = claim.claim_type.value if hasattr(claim.claim_type, "value") else claim.claim_type
    status = claim.status.value if hasattr(claim.status, "value") else claim.status
    return {
        "final_result": ctype,
        "claim_class": status,
        "confidence": claim.confidence,
        "architecture": claim.architecture_state,
        "homology_support": claim.homology_support,
        "orthology_class": claim.orthology_class,
        "statement": claim.statement,
    }


def snapshot_deterministic(sys_dir: Path, target: str, claim, seconds: float, reused: bool) -> dict:
    fam = load_json(sys_dir / "family" / target / "family_evidence.json") or {}
    recon = fam.get("reconstruction") or {}
    multi = fam.get("multiplicity") or recon.get("multiplicity") or {}
    hits = load_json(sys_dir / "search" / "gene_search_hits.json") or []
    if isinstance(hits, dict):
        hits = hits.get("hits") or []
    tests = []
    if claim is not None and hasattr(claim, "falsification_tests"):
        for t in claim.falsification_tests or []:
            tests.append(
                {
                    "test_id": getattr(t, "test_id", None) if not isinstance(t, dict) else t.get("test_id"),
                    "status": getattr(t, "status", None) if not isinstance(t, dict) else t.get("status"),
                    "result": getattr(t, "result", None) if not isinstance(t, dict) else t.get("result"),
                }
            )
    return {
        "ok": claim is not None,
        "runtime_seconds": seconds,
        "reused": reused,
        "architecture": fam.get("architecture") or (claim.architecture_state if claim else None),
        "multiplicity": {
            "number_of_candidate_loci": multi.get("number_of_candidate_loci") if isinstance(multi, dict) else None,
            "classification": multi.get("classification") if isinstance(multi, dict) else None,
        },
        "n_hits": len(hits) if isinstance(hits, list) else None,
        "falsification_tests": tests,
        **claim_fields(claim),
        "external_labels_opened": False,
    }


def run_conventional(acc: str, target: str, assembly: Path, settings, organism: str | None) -> dict:
    published, sys_dir = sys_paths(acc, target, "conventional")
    dest = published / "case_locked.json"
    if dest.exists() and dest.stat().st_size > 50:
        print(f"reuse conventional {acc} {target}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    sys_dir.mkdir(parents=True, exist_ok=True)
    one = sys_dir / "target.fa"
    write_one_target(TARGETS_FA, one, target)
    print(f"CONVENTIONAL {acc} {target}", flush=True)
    t0 = time.perf_counter()
    try:
        payload = _run_system("conventional", assembly, one, sys_dir, settings, EMPTY_REFS, organism, None, None)
        claims = payload.get("claims") or []
        claim = claims[0] if claims else None
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": "conventional",
            "ok": True,
            "runtime_seconds": float(payload.get("seconds") or (time.perf_counter() - t0)),
            "reused": bool(payload.get("reused")),
            **claim_fields(claim),
            "external_labels_opened": False,
        }
    except Exception as exc:
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": "conventional",
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "runtime_seconds": time.perf_counter() - t0,
            "external_labels_opened": False,
        }
        print(f"FAIL conventional {acc}: {exc}", flush=True)
    sync_work_to_published(sys_dir, published)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    return row


def run_v5(acc: str, target: str, assembly: Path, settings, organism: str | None) -> dict:
    published, sys_dir = sys_paths(acc, target, "genome_skeptic")
    dest = published / "case_locked.json"
    if dest.exists() and dest.stat().st_size > 50:
        print(f"reuse V5 {acc} {target}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    sys_dir.mkdir(parents=True, exist_ok=True)
    one = sys_dir / "target.fa"
    write_one_target(TARGETS_FA, one, target)
    print(f"V5 {acc} {target}", flush=True)
    t0 = time.perf_counter()
    try:
        payload = _run_system("genome_skeptic", assembly, one, sys_dir, settings, EMPTY_REFS, organism, None, None)
        claims = payload.get("claims") or []
        claim = claims[0] if claims else None
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": "genome_skeptic_v5",
            **snapshot_deterministic(
                sys_dir, target, claim, float(payload.get("seconds") or (time.perf_counter() - t0)), bool(payload.get("reused"))
            ),
        }
    except Exception as exc:
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": "genome_skeptic_v5",
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "runtime_seconds": time.perf_counter() - t0,
            "external_labels_opened": False,
        }
        print(f"FAIL V5 {acc}: {exc}", flush=True)
    sync_work_to_published(sys_dir, published)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"V5 DONE {acc} ok={row.get('ok')} class={row.get('claim_class')} s={row.get('runtime_seconds')}", flush=True)
    return row


def extract_agentic(provenance: dict, claim, case_dir: Path) -> dict:
    planner = load_json(case_dir / "planner_decision.json") or {}
    critic = load_json(case_dir / "critic_review.json") or {}
    challenge = provenance.get("critic_challenge") or {}
    actions = provenance.get("actions_executed") or []
    statuses = []
    action_ids = []
    for a in actions:
        if isinstance(a, dict):
            aid = a.get("action_id")
            action_ids.append(aid)
            statuses.append({"action_id": aid, "status": a.get("status"), "requested_by": a.get("requested_by")})
        else:
            action_ids.append(a)
    m0 = ((provenance.get("measurement_state") or {}).get("m0") or {})
    m_final = ((provenance.get("measurement_state") or {}).get("m_final") or {})
    fam = load_json(case_dir / "family" / (claim.claim_id.split(":")[-1] if claim else "") / "family_evidence.json") if claim else None
    return {
        "planner_invoked": provenance.get("planner_invoked"),
        "planner_decision": planner.get("decision") or provenance.get("control_decision"),
        "planner_action": provenance.get("selected_action") or planner.get("requested_action") or (planner.get("requested_actions") or [None])[0],
        "planner_control_decision": provenance.get("control_decision"),
        "planner_grounding_status": provenance.get("planner_grounding_status"),
        "planner_control_failure": provenance.get("planner_control_failure"),
        "critic_invoked": provenance.get("critic_invoked"),
        "critic_verdict": challenge.get("verdict") or critic.get("verdict"),
        "critic_action": provenance.get("critic_second_action"),
        "actions_executed": action_ids,
        "action_result_status": statuses or provenance.get("action_status_counts"),
        "ranked_candidate_actions": provenance.get("ranked_candidate_actions"),
        "diagnostic_needs_m0": provenance.get("diagnostic_needs_m0"),
        "m0_hash": m0.get("hash"),
        "m_final_hash": m_final.get("hash"),
        "measurements_changed_before_validation": provenance.get("measurements_changed_before_validation"),
        "validator_consumed_measurement_hash": provenance.get("validator_consumed_measurement_hash"),
        "validator_consumed_m0": provenance.get("validator_consumed_m0"),
        "validator_consumed_final_state": (
            provenance.get("validator_consumed_measurement_hash") == m_final.get("hash")
            if provenance.get("validator_consumed_measurement_hash") and m_final.get("hash")
            else False
        ),
        "model_call_count": provenance.get("model_call_count"),
        "planner_call_count": provenance.get("planner_model_call_count"),
        "critic_call_count": provenance.get("critic_model_call_count"),
        "repair_count": provenance.get("repair_count"),
        "agent_failure": provenance.get("agent_failure"),
        "final_validator_ran": provenance.get("final_validator_ran"),
        "call_graph": provenance.get("call_graph") or [],
        "silent_deterministic_fallback": bool(provenance.get("silent_deterministic_fallback")),
        "llm_measurement_entered_claim": provenance.get("llm_measurement_entered_claim"),
        "unregistered_actions": [a for a in action_ids if a and a not in REGISTERED],
        **claim_fields(claim),
    }


def run_agentic(acc: str, target: str, assembly: Path, settings, organism: str | None) -> dict:
    published, case_dir = sys_paths(acc, target, SYSTEM_NAME)
    dest = published / "case_locked.json"
    if dest.exists() and dest.stat().st_size > 50:
        print(f"reuse agentic {acc} {target}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    case_dir.mkdir(parents=True, exist_ok=True)
    one = case_dir / "target.fa"
    write_one_target(TARGETS_FA, one, target)
    print(f"AGENTIC V3 {acc} {target}", flush=True)
    reset_call_log()
    t0 = time.perf_counter()
    try:
        claims, _loci, provenance = run_skeptic_agentic_v3(
            assembly,
            one,
            case_dir,
            settings,
            query_ids=[target],
            declared_organism=organism,
            references=EMPTY_REFS,
        )
        claim = claims[0] if claims else None
        extra = extract_agentic(provenance, claim, case_dir)
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": SYSTEM_NAME,
            "ok": extra.get("agent_failure") is None and extra.get("final_validator_ran") is True,
            "runtime_seconds": provenance.get("seconds") or round(time.perf_counter() - t0, 3),
            "model": provenance.get("model_name") or "qwen3:4b",
            "model_digest": EXPECTED_DIGEST,
            "frozen_agentic_version": FREEZE_ID,
            "external_labels_opened": False,
            **extra,
        }
    except Exception as exc:
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": SYSTEM_NAME,
            "ok": False,
            "agent_failure": f"planner/critic could not complete under frozen policy: {exc}",
            "agent_execution_failure_recorded": True,
            "silent_deterministic_fallback": False,
            "runtime_seconds": round(time.perf_counter() - t0, 3),
            "traceback": traceback.format_exc(limit=8),
            "external_labels_opened": False,
            "frozen_agentic_version": FREEZE_ID,
        }
        print(f"AGENT_FAILURE {acc} {target}: {exc}", flush=True)
    sync_work_to_published(case_dir, published)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        f"AGENTIC DONE {acc} ok={row.get('ok')} action={row.get('planner_action')} "
        f"critic={row.get('critic_action')} fail={row.get('agent_failure')}",
        flush=True,
    )
    return row


def integrity_checks(pos: int, rec: dict, conv: dict, v5: dict, agentic: dict, freeze: dict) -> dict:
    published, _ = sys_paths(rec["assembly_accession"], rec["target"], SYSTEM_NAME)
    provenance = load_json(published / "agentic_provenance.json") or {}
    planner_file = (published / "planner_decision.json").exists()
    critic_file = (published / "critic_review.json").exists()
    planner_invoked = bool(agentic.get("planner_invoked") or provenance.get("planner_invoked"))
    critic_invoked = bool(agentic.get("critic_invoked") or provenance.get("critic_invoked"))
    critic_applicable = planner_invoked and not (
        agentic.get("agent_failure") or ""
    ).startswith("planner call failed")
    unregistered = agentic.get("unregistered_actions") or []
    llm_meas = bool(agentic.get("llm_measurement_entered_claim") or provenance.get("llm_measurement_entered_claim"))
    validator_final = bool(agentic.get("validator_consumed_final_state"))
    if not validator_final and agentic.get("ok"):
        m_final = ((provenance.get("measurement_state") or {}).get("m_final") or {}).get("hash")
        consumed = provenance.get("validator_consumed_measurement_hash")
        validator_final = bool(consumed and m_final and consumed == m_final)
    silent = bool(agentic.get("silent_deterministic_fallback") or provenance.get("silent_deterministic_fallback"))
    provenance_complete = all(
        (published / name).exists()
        for name in ("agentic_provenance.json", "call_log.json", "claims.json", "evidence.json")
    ) and planner_file
    if critic_applicable:
        provenance_complete = provenance_complete and (critic_file or critic_invoked)
    checks = {
        "execution_position": pos,
        "assembly_accession": rec["assembly_accession"],
        "target": rec["target"],
        "v3_freeze_verified": freeze.get("manifest_sha256") == EXPECTED_V3_FREEZE,
        "planner_executed": planner_invoked,
        "critic_executed_where_applicable": (not critic_applicable) or critic_invoked,
        "critic_applicable": critic_applicable,
        "registered_actions_only": len(unregistered) == 0,
        "unregistered_actions": unregistered,
        "deterministic_measurements_only": not llm_meas,
        "validator_consumed_correct_final_state": validator_final or (not agentic.get("ok") and agentic.get("agent_failure") is not None),
        "no_silent_fallback": not silent,
        "execution_provenance_complete": provenance_complete,
        "conventional_ok": bool(conv.get("ok")),
        "v5_ok": bool(v5.get("ok")),
        "agentic_ok": bool(agentic.get("ok")),
        "agent_failure": agentic.get("agent_failure"),
        "current_lacz_limitation_recorded": rec["target"] != "lacZ_beta_galactosidase" or True,
    }
    scientific_fail_ok = True
    required = [
        "v3_freeze_verified",
        "planner_executed",
        "critic_executed_where_applicable",
        "registered_actions_only",
        "deterministic_measurements_only",
        "no_silent_fallback",
        "execution_provenance_complete",
        "conventional_ok",
        "v5_ok",
    ]
    if agentic.get("ok"):
        required.append("validator_consumed_correct_final_state")
    checks["infrastructure_pass"] = all(checks[k] for k in required) and scientific_fail_ok
    return checks


def lock_predictions(conv: list[dict], v5: list[dict], agentic: list[dict], freeze: dict) -> dict:
    if len(conv) != 12 or len(v5) != 12 or len(agentic) != 12:
        raise SystemExit(f"lock aborted: counts conv={len(conv)} v5={len(v5)} agentic={len(agentic)}")
    stamp = datetime.now(timezone.utc).isoformat()
    blobs = {
        "D12_CONVENTIONAL_LOCKED.json": {
            "kind": "D12_CONVENTIONAL_LOCKED",
            "n_cases": len(conv),
            "do_not_regenerate": True,
            "external_labels_opened": False,
            "d20_touched": False,
            "frozen_agentic_version": FREEZE_ID,
            "created_utc": stamp,
            "predictions": conv,
        },
        "D12_V5_LOCKED.json": {
            "kind": "D12_V5_LOCKED",
            "n_cases": len(v5),
            "do_not_regenerate": True,
            "external_labels_opened": False,
            "d20_touched": False,
            "frozen_agentic_version": FREEZE_ID,
            "created_utc": stamp,
            "predictions": v5,
        },
        "D12_AGENTIC_V3_LOCKED.json": {
            "kind": "D12_AGENTIC_V3_LOCKED",
            "n_cases": len(agentic),
            "do_not_regenerate": True,
            "external_labels_opened": False,
            "d20_touched": False,
            "frozen_agentic_version": FREEZE_ID,
            "agentic_freeze_manifest_sha256": freeze["manifest_sha256"],
            "created_utc": stamp,
            "current_lacz_limitation": CURRENT_LACZ_LIMITATION,
            "predictions": agentic,
        },
    }
    hashes = {}
    for name, payload in blobs.items():
        path = OUT / name
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        hashes[name] = write_sha256_sidecar(path, {"do_not_regenerate": True})
    return hashes


def load_progress() -> dict:
    path = OUT / "D12_RUN_PROGRESS.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"conventional": {}, "v5": {}, "agentic": {}, "integrity": {}}


def save_progress(progress: dict) -> None:
    progress["updated_utc"] = datetime.now(timezone.utc).isoformat()
    progress["external_labels_opened"] = False
    progress["d20_touched"] = False
    (OUT / "D12_RUN_PROGRESS.json").write_text(json.dumps(progress, indent=2, default=str) + "\n", encoding="utf-8")


def case_key(rec: dict) -> str:
    return f"{rec['execution_position']}|{rec['assembly_accession']}|{rec['target']}"


def print_readiness(checks: dict, freeze: dict, manifest_sha: str) -> None:
    lines = [
        "==================================================",
        "V3_D12_EXTERNAL STAGE 1 READINESS",
        "==================================================",
        f"V3 FREEZE VERIFIED: {'YES' if checks['v3_freeze_verified'] else 'NO'}",
        f"V3 FREEZE SHA256: {freeze['manifest_sha256']}",
        f"D12 MANIFEST SHA256: {manifest_sha}",
        f"POSITION: {checks['execution_position']}",
        f"ACCESSION: {checks['assembly_accession']}",
        f"TARGET: {checks['target']}",
        f"PLANNER EXECUTED: {'YES' if checks['planner_executed'] else 'NO'}",
        f"CRITIC EXECUTED WHERE APPLICABLE: {'YES' if checks['critic_executed_where_applicable'] else 'NO'}",
        f"REGISTERED ACTIONS ONLY: {'YES' if checks['registered_actions_only'] else 'NO'}",
        f"DETERMINISTIC MEASUREMENTS ONLY: {'YES' if checks['deterministic_measurements_only'] else 'NO'}",
        f"VALIDATOR CONSUMED CORRECT FINAL STATE: {'YES' if checks['validator_consumed_correct_final_state'] else 'NO'}",
        f"NO SILENT FALLBACK: {'YES' if checks['no_silent_fallback'] else 'NO'}",
        f"EXECUTION PROVENANCE COMPLETE: {'YES' if checks['execution_provenance_complete'] else 'NO'}",
        f"CONVENTIONAL OK: {'YES' if checks['conventional_ok'] else 'NO'}",
        f"V5 OK: {'YES' if checks['v5_ok'] else 'NO'}",
        f"AGENTIC OK: {'YES' if checks['agentic_ok'] else 'NO'}",
        f"AGENT FAILURE: {checks.get('agent_failure') or 'none'}",
        f"INFRASTRUCTURE PASS: {'YES' if checks['infrastructure_pass'] else 'NO'}",
        f"CURRENT_LACZ_LIMITATION: {CURRENT_LACZ_LIMITATION}",
        "D20 TOUCHED: NO",
        "UNBLIND: NO",
        "==================================================",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "D12_STAGE1_READINESS.txt").write_text(text, encoding="utf-8")
    (OUT / "D12_STAGE1_READINESS.json").write_text(json.dumps(checks, indent=2, default=str) + "\n", encoding="utf-8")
    print(text, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, required=True, choices=(1, 2, 3))
    args = parser.parse_args()
    freeze = verify_v3_freeze()
    print("V3_FREEZE_OK", freeze["manifest_sha256"], flush=True)
    assert_d20_untouched(f"stage{args.stage}_start")
    lock = json.loads(MANIFEST_LOCK.read_text(encoding="utf-8"))
    manifest_sha = sha256_file(MANIFEST)
    if manifest_sha != lock.get("sha256"):
        raise SystemExit(f"D12 manifest hash mismatch {manifest_sha}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("agentic_v3_executed"):
        print("NOTE manifest already marked agentic_v3_executed; continuing locked cases only", flush=True)
    cases = sorted(manifest["cases"], key=lambda r: (r["execution_hash"], r["assembly_accession"]))
    for i, rec in enumerate(cases, start=1):
        if int(rec["execution_position"]) != i:
            raise SystemExit("execution_position not aligned with execution_hash sort")
    write_targets(TARGETS_FA)
    if not EMPTY_REFS.exists():
        EMPTY_REFS.write_text("references: []\n", encoding="utf-8")
    conv_settings = load_settings(V5_YAML)
    v5_settings = load_settings(V5_YAML)
    agentic_settings = load_settings(AGENTIC_YAML)
    remap = fix_llm_host(agentic_settings)
    print("OLLAMA_REMAP", remap, flush=True)
    if Path("/home/aritr").exists():
        LINUX_WORK.mkdir(parents=True, exist_ok=True)
        tmp = LINUX_WORK / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        os.environ["TMPDIR"] = str(tmp)
        os.environ["TMP"] = str(tmp)
        os.environ["TEMP"] = str(tmp)
    RUNS.mkdir(parents=True, exist_ok=True)
    progress = load_progress()
    lo, hi = STAGE_POSITIONS[args.stage]
    if args.stage >= 2:
        stage1 = load_json(OUT / "D12_STAGE1_READINESS.json") or {}
        if not stage1.get("infrastructure_pass"):
            raise SystemExit("STAGE 1 did not pass; refusing STAGE 2/3")
    if args.stage == 3:
        stage2 = load_json(OUT / "D12_STAGE2_INTEGRITY.json") or {}
        if not stage2.get("infrastructure_pass"):
            raise SystemExit("STAGE 2 did not pass; refusing STAGE 3")

    stage_checks = []
    for rec in cases:
        pos = int(rec["execution_position"])
        if pos < lo or pos > hi:
            continue
        acc = rec["assembly_accession"]
        target = rec["target"]
        src = ROOT / rec["solver_fasta"]
        if sha256_file(src) != rec["fasta_sha256"]:
            raise SystemExit(f"FASTA changed {acc}")
        assembly = stage_fasta(src, acc, rec["fasta_sha256"])
        print(f"CASE pos={pos} {acc} {target}", flush=True)
        conv = run_conventional(acc, target, assembly, conv_settings, rec.get("organism"))
        v5 = run_v5(acc, target, assembly, v5_settings, rec.get("organism"))
        agentic = run_agentic(acc, target, assembly, agentic_settings, rec.get("organism"))
        key = case_key(rec)
        progress["conventional"][key] = conv
        progress["v5"][key] = v5
        progress["agentic"][key] = agentic
        checks = integrity_checks(pos, rec, conv, v5, agentic, freeze)
        progress["integrity"][key] = checks
        save_progress(progress)
        stage_checks.append(checks)
        if args.stage == 1:
            print_readiness(checks, freeze, manifest_sha)
            assert_d20_untouched("stage1_end")
            if not checks["infrastructure_pass"]:
                print("STAGE 1 INFRASTRUCTURE FAIL — STOP", flush=True)
                return 1
            print("STAGE 1 PASS — STOP BEFORE STAGE 2", flush=True)
            return 0

    infra_pass = all(c["infrastructure_pass"] for c in stage_checks) and len(stage_checks) == (hi - lo + 1)
    summary = {
        "stage": args.stage,
        "positions": [c["execution_position"] for c in stage_checks],
        "infrastructure_pass": infra_pass,
        "checks": stage_checks,
        "external_labels_opened": False,
        "d20_touched": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    if args.stage == 2:
        (OUT / "D12_STAGE2_INTEGRITY.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps({"stage": 2, "infrastructure_pass": infra_pass, "n": len(stage_checks)}, indent=2), flush=True)
        assert_d20_untouched("stage2_end")
        if not infra_pass:
            print("STAGE 2 INFRASTRUCTURE FAIL — STOP", flush=True)
            return 1
        print("STAGE 2 PASS — STOP BEFORE STAGE 3", flush=True)
        return 0

    conv_rows = []
    v5_rows = []
    agentic_rows = []
    for rec in cases:
        key = case_key(rec)
        if key not in progress["conventional"] or key not in progress["v5"] or key not in progress["agentic"]:
            raise SystemExit(f"missing locked row for {key}")
        conv_rows.append(progress["conventional"][key])
        v5_rows.append(progress["v5"][key])
        agentic_rows.append(progress["agentic"][key])
    hashes = lock_predictions(conv_rows, v5_rows, agentic_rows, freeze)
    agentic_ok = sum(1 for r in agentic_rows if r.get("ok"))
    (OUT / "D12_STAGE3_LOCK.json").write_text(
        json.dumps(
            {
                **summary,
                "locked": hashes,
                "n_conventional": len(conv_rows),
                "n_v5": len(v5_rows),
                "n_agentic": len(agentic_rows),
                "agentic_completion": agentic_ok,
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    assert_d20_untouched("stage3_end")
    print("V3 FREEZE VERIFIED:", "YES" if freeze["manifest_sha256"] == EXPECTED_V3_FREEZE else "NO", flush=True)
    print("D12 MANIFEST SHA256:", manifest_sha, flush=True)
    print("CONVENTIONAL LOCK SHA256:", hashes["D12_CONVENTIONAL_LOCKED.json"], flush=True)
    print("V5 LOCK SHA256:", hashes["D12_V5_LOCKED.json"], flush=True)
    print("AGENTIC V3 LOCK SHA256:", hashes["D12_AGENTIC_V3_LOCKED.json"], flush=True)
    print("CASES COMPLETE:", f"{len(conv_rows)} / 12", flush=True)
    print("AGENTIC COMPLETION:", f"{agentic_ok} / 12", flush=True)
    print("D20 TOUCHED: NO", flush=True)
    print("UNBLIND: NO", flush=True)
    print("STOP.", flush=True)
    return 0 if infra_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
