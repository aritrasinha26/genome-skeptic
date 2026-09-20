#!/usr/bin/env python3
"""Run frozen Agentic V1, deterministic V5, and frozen conventional baseline on Cohort C.

Does not inspect external labels, download annotations, score, adjudicate, or
modify the Agentic V1 freeze, deterministic V5 science, or Cohort A.
Resumes completed cases. Locks predictions only after all 40×3 cases finish.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.assembly_loop import SYSTEM_NAME, run_skeptic_agentic  # noqa: E402
from genome_skeptic.agents.providers import CALL_LOG, extract_json_text, reset_call_log  # noqa: E402
from genome_skeptic.config import load_settings  # noqa: E402
from genome_skeptic.eval.evaluate_real import _run_system  # noqa: E402
from genome_skeptic.families import load_family  # noqa: E402
from genome_skeptic.io_utils import iter_fasta_records  # noqa: E402
from genome_skeptic.orchestrator import REGISTERED_ACTIONS  # noqa: E402

OUT = ROOT / "external_validation_agentic"
RUNS = OUT / "cohort_C_runs"
INPUTS = OUT / "cohort_C_inputs"
SOLVER = INPUTS / "solver"
TARGETS = INPUTS / "targets.fa"
EMPTY_REFS = INPUTS / "references.yaml"
MANIFEST = OUT / "cohort_C_manifest.json"
INPUT_MANIFEST = OUT / "cohort_C_input_manifest.json"
INPUT_HASH_SIDECAR = OUT / "cohort_C_input_manifest.sha256.json"

FROZEN_TARGETS = [
    "rpoB_RNAP_beta",
    "tuf_EF_Tu",
    "lacZ_beta_galactosidase",
    "tetA_tetracycline_efflux",
]
CONDITIONS = [
    ("GENOME_SKEPTIC_AGENTIC_V1", "genome_skeptic_agentic"),
    ("DETERMINISTIC_GENOME_SKEPTIC_V5", "genome_skeptic"),
    ("FROZEN_CONVENTIONAL_BASELINE", "conventional"),
]
AGENTIC_FREEZE_SHA = "9ca874bb38efa073b2e0801f6f492e6bb1fdabd27ba2a225c70e559ba5bf8c54"
AGENTIC_SUMMARY_SHA = "e5cc95523e18c9472211bb89235ccb624bc6cbbbad0d0ba5f56fddb1e8f9b38e"
MODEL_DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"
V5_FREEZE = "0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_targets() -> None:
    chunks = []
    for fid in FROZEN_TARGETS:
        fam = load_family(fid)
        if not fam or not fam.members:
            raise SystemExit(f"frozen family missing: {fid}")
        member = max(fam.members, key=lambda m: len(m.sequence or ""))
        seq = member.sequence
        chunks.append(
            f">{fid} target_type=gene_orthologue family={fid} length_aa={len(seq)}\n{seq}\n"
        )
    TARGETS.write_text("".join(chunks), encoding="utf-8")
    if not EMPTY_REFS.exists():
        EMPTY_REFS.write_text("references: []\n", encoding="utf-8")


def write_one_target(dest_fa: Path, query_id: str) -> None:
    chosen = [(header, seq) for seq_id, header, seq in iter_fasta_records(TARGETS) if seq_id == query_id]
    if not chosen:
        raise SystemExit(f"target {query_id} not found in {TARGETS}")
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


def _call_stats(log: list[dict]) -> dict:
    n = len(log)
    repairs = sum(
        1
        for r in log
        if r.get("retry_count") or str(r.get("request_type") or "").endswith("_repair")
    )
    malformed = sum(1 for r in log if r.get("schema_valid") is False)
    timeouts = sum(
        1
        for r in log
        if "timeout" in str(r.get("finish_reason") or "").lower() or "timeout" in str(r).lower()
    )
    return {
        "model_call_count": n,
        "repair_count": repairs,
        "malformed_output_count": malformed,
        "timeout_count": timeouts,
        "call_log": log,
    }


def load_family_blob(sys_dir: Path, qid: str) -> dict | None:
    path = sys_dir / "family" / qid / "family_evidence.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _coords_from(claim, family_blob: dict | None, locus: dict | None) -> dict | None:
    recon = (family_blob or {}).get("reconstruction") or {}
    multi = (family_blob or {}).get("multiplicity") or recon.get("multiplicity") or {}
    if locus and (locus.get("genomic_start") is not None):
        return {
            "contig": locus.get("contig"),
            "start": locus.get("genomic_start"),
            "end": locus.get("genomic_end"),
            "strand": locus.get("strand"),
        }
    if recon.get("coordinates"):
        return recon.get("coordinates")
    if multi.get("coordinates"):
        return multi.get("coordinates")
    return None


def prediction_row(
    acc: str,
    condition: str,
    target: str,
    claim,
    family_blob: dict | None,
    locus: dict | None,
    seconds: float,
    extra: dict | None = None,
) -> dict:
    tests = [t.model_dump(mode="json") for t in (claim.falsification_tests or [])] if claim else []
    recon = (family_blob or {}).get("reconstruction") or {}
    multi = (family_blob or {}).get("multiplicity") or recon.get("multiplicity") or {}
    row = {
        "assembly_accession": acc,
        "condition": condition,
        "target": target,
        "final_claim": claim.claim_type.value if claim and claim.claim_type else None,
        "classification": claim.status.value if claim and claim.status else None,
        "confidence": claim.confidence if claim else None,
        "evidence_ids": (
            list(claim.supporting_evidence_ids or []) + list(claim.contradicting_evidence_ids or [])
            if claim
            else []
        ),
        "supporting_evidence": list(claim.supporting_evidence_ids or []) if claim else [],
        "contradictory_evidence": list(claim.contradicting_evidence_ids or []) if claim else [],
        "alternative_hypotheses": list(claim.alternative_explanations or []) if claim else [],
        "falsification_actions": tests,
        "final_selected_action_path": list(claim.recommended_next_actions or []) if claim else [],
        "locus_coordinates": _coords_from(claim, family_blob, locus),
        "architecture_classification": (
            (claim.architecture_state if claim else None)
            or (family_blob or {}).get("architecture")
            or (locus or {}).get("architecture")
        ),
        "multiplicity_estimate": {
            "number_of_candidate_loci": multi.get("number_of_candidate_loci"),
            "classification": multi.get("classification"),
        }
        if multi
        else None,
        "unresolved_status": claim.status.value if claim and claim.status and claim.status.value == "unresolved" else None,
        "orthology_class": claim.orthology_class if claim else None,
        "homology_support": claim.homology_support if claim else None,
        "statement": claim.statement if claim else None,
        "runtime_seconds": seconds,
        "external_labels_opened": False,
    }
    if extra:
        row.update(extra)
    return row


def agentic_case_path(acc: str, target: str) -> Path:
    return RUNS / acc / SYSTEM_NAME / target / "case_locked.json"


def extract_agentic_extra(provenance: dict, claim, case_dir: Path) -> dict:
    graph = provenance.get("call_graph") or []
    before = list(provenance.get("evidence_ids_before_action") or [])
    after = list(provenance.get("evidence_ids_after_action") or provenance.get("evidence_ids") or [])
    known = set(after or before)
    call_log = []
    log_path = case_dir / "call_log.json"
    if log_path.exists():
        call_log = json.loads(log_path.read_text(encoding="utf-8"))
    invalid_e, invalid_a = _invalid_from_calls(call_log, known, set(REGISTERED_ACTIONS))
    critic = provenance.get("critic_challenge") or {}
    stats = _call_stats(call_log)
    repairs = sum(1 for step in graph if str(step).endswith("_repair"))
    action = provenance.get("selected_action")
    failure = provenance.get("agent_failure")
    return {
        "architecture": "GENOME_SKEPTIC_AGENTIC_V1",
        "initial_evidence_ids": before,
        "planner_call_count": provenance.get("planner_model_call_count"),
        "planner_cited_evidence": list(provenance.get("cited_evidence_ids") or []),
        "planner_preferred_interpretation": provenance.get("preferred_hypothesis"),
        "alternative_explanations": list(claim.alternative_explanations or []) if claim else list(provenance.get("final_claim_state", {}).get("alternative_explanations") or []),
        "requested_action": action,
        "action_registered": bool(action) and action in REGISTERED_ACTIONS,
        "action_executed": any(str(step).startswith("execute_registered_action:") for step in graph),
        "new_evidence_ids": [eid for eid in after if eid not in before],
        "critic_call_count": provenance.get("critic_model_call_count"),
        "critic_verdict": critic.get("verdict"),
        "critic_cited_evidence": list(provenance.get("critic_cited_evidence_ids") or []),
        "critic_failure_modes": list(critic.get("failure_modes") or []),
        "repair_count": repairs if repairs else int(provenance.get("repair_count") or 0),
        "invalid_evidence_attempts": invalid_e,
        "invalid_action_attempts": invalid_a,
        "final_validator_state": {
            "ran": provenance.get("final_validator_ran") is True,
            "claim": provenance.get("final_claim_state"),
        },
        "agent_execution_failure": failure,
        "agent_execution_failure_recorded": failure is not None,
        "planner_invoked": provenance.get("planner_invoked") is True,
        "critic_invoked": provenance.get("critic_invoked") is True,
        "final_validator_ran": provenance.get("final_validator_ran") is True,
        "model_call_count": provenance.get("model_call_count"),
        "malformed_output_count": stats["malformed_output_count"],
        "timeout_count": stats["timeout_count"],
        "call_graph": graph,
        "llm_measurement_entered_claim": provenance.get("llm_measurement_entered_claim"),
        "silent_deterministic_fallback": False,
        "model": provenance.get("model_name") or "qwen3:4b",
        "model_digest": MODEL_DIGEST,
        "thinking": False,
        "temperature": 0,
        "structured_output": "Ollama native schema",
        "maximum_repairs": 1,
        "final_scientific_authority": "deterministic validator",
    }


def run_agentic_case(acc: str, target: str, assembly: Path, settings, genus: str | None) -> dict:
    dest = agentic_case_path(acc, target)
    if dest.exists() and dest.stat().st_size > 50:
        print(f"skip completed agentic {acc} {target}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    case_dir = dest.parent
    case_dir.mkdir(parents=True, exist_ok=True)
    one_target = case_dir / f"{target}.fa"
    write_one_target(one_target, target)
    print(f"AGENTIC START {acc} {target}", flush=True)
    t0 = time.perf_counter()
    try:
        claims, loci, provenance = run_skeptic_agentic(
            assembly,
            one_target,
            case_dir,
            settings,
            query_ids=[target],
        )
        elapsed = time.perf_counter() - t0
        claim = claims[0] if claims else None
        extra = extract_agentic_extra(provenance, claim, case_dir)
        extra["runtime_seconds"] = provenance.get("seconds") or round(elapsed, 3)
        loc = None
        if loci:
            le = loci[0]
            loc = le.model_dump(mode="json") if hasattr(le, "model_dump") else le
        fam = load_family_blob(case_dir, target)
        row = prediction_row(acc, "GENOME_SKEPTIC_AGENTIC_V1", target, claim, fam, loc, extra["runtime_seconds"], extra)
        row["ok"] = extra.get("agent_execution_failure") is None and extra.get("final_validator_ran") is True
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"AGENT_EXECUTION_FAILURE {acc} {target}: {exc}", flush=True)
        row = {
            "assembly_accession": acc,
            "condition": "GENOME_SKEPTIC_AGENTIC_V1",
            "target": target,
            "ok": False,
            "agent_execution_failure": f"planner/critic could not complete under frozen policy: {exc}",
            "agent_execution_failure_recorded": True,
            "silent_deterministic_fallback": False,
            "runtime_seconds": round(elapsed, 3),
            "traceback": traceback.format_exc(limit=8),
            "external_labels_opened": False,
        }
    dest.write_text(json.dumps(row, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(
        f"AGENTIC DONE {acc} {target} ok={row.get('ok')} action={row.get('requested_action')} fail={row.get('agent_execution_failure')}",
        flush=True,
    )
    return row


def deterministic_lock_path(acc: str, condition: str) -> Path:
    sys_name = "genome_skeptic" if condition == "DETERMINISTIC_GENOME_SKEPTIC_V5" else "conventional"
    return RUNS / acc / sys_name / "condition_locked.json"


def run_deterministic_condition(acc: str, condition: str, sys_name: str, assembly: Path, settings, genus: str | None) -> list[dict]:
    dest = deterministic_lock_path(acc, condition)
    if dest.exists() and dest.stat().st_size > 50:
        print(f"skip completed {condition} {acc}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    sys_dir = dest.parent
    sys_dir.mkdir(parents=True, exist_ok=True)
    print(f"{condition} START {acc}", flush=True)
    reset_call_log()
    t0 = time.perf_counter()
    flags = {"enable_falsification": True} if sys_name == "genome_skeptic" else None
    try:
        payload = _run_system(
            sys_name,
            assembly,
            TARGETS,
            sys_dir,
            settings,
            EMPTY_REFS,
            genus,
            None,
            flags,
        )
        elapsed = time.perf_counter() - t0
        claims = payload.get("claims") or []
        loci = payload.get("loci") or []
        locus_by_q = {}
        for le in loci:
            q = getattr(le, "query_id", None) or (le.get("query_id") if isinstance(le, dict) else None)
            if q and q not in locus_by_q:
                locus_by_q[q] = le.model_dump(mode="json") if hasattr(le, "model_dump") else le
        rows = []
        for claim in claims:
            qid = claim.claim_id.replace("C_target_", "")
            if qid not in FROZEN_TARGETS:
                continue
            fam = load_family_blob(sys_dir, qid)
            loc = locus_by_q.get(qid)
            row = prediction_row(acc, condition, qid, claim, fam, loc, elapsed)
            row["ok"] = True
            row["model_call_count"] = 0
            row["repair_count"] = 0
            row["malformed_output_count"] = 0
            row["timeout_count"] = 0
            row["reused"] = bool(payload.get("reused"))
            rows.append(row)
        if len(rows) != 4:
            missing = [t for t in FROZEN_TARGETS if t not in {r["target"] for r in rows}]
            raise RuntimeError(f"{condition} {acc} missing targets: {missing}")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"FAIL {condition} {acc}: {exc}", flush=True)
        rows = [
            {
                "assembly_accession": acc,
                "condition": condition,
                "target": t,
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=8),
                "runtime_seconds": round(elapsed, 3),
                "external_labels_opened": False,
            }
            for t in FROZEN_TARGETS
        ]
    dest.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"{condition} DONE {acc} n={len(rows)} s={elapsed:.1f}", flush=True)
    return rows


def lock_cohort(all_rows: list[dict], genomes: list[dict], started_utc: str, wall: float, input_hash: str, cohort_hash: str) -> None:
    jsonl = OUT / "cohort_C_predictions_locked.jsonl"
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":"), default=str) for r in all_rows]
    jsonl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    pred_hash = sha256_file(jsonl)

    agentic = [r for r in all_rows if r.get("condition") == "GENOME_SKEPTIC_AGENTIC_V1"]
    v5 = [r for r in all_rows if r.get("condition") == "DETERMINISTIC_GENOME_SKEPTIC_V5"]
    conv = [r for r in all_rows if r.get("condition") == "FROZEN_CONVENTIONAL_BASELINE"]
    agentic_ok = [r for r in agentic if r.get("ok") and not r.get("agent_execution_failure")]
    agentic_fail = [r for r in agentic if r.get("agent_execution_failure") or r.get("ok") is False]
    actions = [r.get("requested_action") for r in agentic if r.get("requested_action")]
    action_counts = dict(Counter(actions))
    invalid_e = sum(len(r.get("invalid_evidence_attempts") or []) for r in agentic)
    invalid_a = sum(len(r.get("invalid_action_attempts") or []) for r in agentic)

    exec_manifest = {
        "kind": "cohort_C_execution_manifest",
        "locked_utc": datetime.now(timezone.utc).isoformat(),
        "started_utc": started_utc,
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V1",
        "agentic_v1_freeze_hash": AGENTIC_FREEZE_SHA,
        "agentic_v1_freeze_summary_sha256": AGENTIC_SUMMARY_SHA,
        "genome_skeptic_v5_freeze_hash": V5_FREEZE,
        "cohort_manifest_sha256": cohort_hash,
        "input_manifest_sha256": input_hash,
        "predictions_locked_sha256": pred_hash,
        "model": "qwen3:4b",
        "model_digest": MODEL_DIGEST,
        "thinking": False,
        "temperature": 0,
        "structured_output": "Ollama native schema",
        "maximum_repairs": 1,
        "final_scientific_authority": "deterministic validator",
        "conditions": [c[0] for c in CONDITIONS],
        "n_genomes": 10,
        "n_genome_target_cases": 40,
        "all_genome_accessions": [g["assembly_accession"] for g in genomes],
        "predictions_per_condition": {
            "GENOME_SKEPTIC_AGENTIC_V1": len(agentic),
            "DETERMINISTIC_GENOME_SKEPTIC_V5": len(v5),
            "FROZEN_CONVENTIONAL_BASELINE": len(conv),
        },
        "successful_agentic_cases": len(agentic_ok),
        "agent_execution_failures": len(agentic_fail),
        "agent_execution_failure_cases": [
            {
                "assembly_accession": r.get("assembly_accession"),
                "target": r.get("target"),
                "reason": r.get("agent_execution_failure") or r.get("error"),
            }
            for r in agentic_fail
        ],
        "planner_calls": int(sum(int(r.get("planner_call_count") or 0) for r in agentic)),
        "critic_calls": int(sum(int(r.get("critic_call_count") or 0) for r in agentic)),
        "repair_calls": int(sum(int(r.get("repair_count") or 0) for r in agentic)),
        "timeouts": int(sum(int(r.get("timeout_count") or 0) for r in agentic)),
        "malformed_responses": int(sum(int(r.get("malformed_output_count") or 0) for r in agentic)),
        "invalid_evidence_attempts": invalid_e,
        "invalid_action_attempts": invalid_a,
        "distinct_registered_actions_selected": sorted({a for a in actions if a}),
        "n_distinct_registered_actions_selected": len(set(actions)),
        "action_frequency_table": action_counts,
        "planner_selected_action_differs_between_cases": len(set(actions)) > 1,
        "action_diversity_is_descriptive_endpoint": True,
        "deterministic_v5_predictions_completed": sum(1 for r in v5 if r.get("ok")),
        "conventional_baseline_predictions_completed": sum(1 for r in conv if r.get("ok")),
        "total_runtime_seconds": wall,
        "external_labels_opened": False,
        "scores_computed": False,
        "adjudication_performed": False,
        "agent_modified": False,
        "thresholds_tuned_after_outputs": False,
        "silent_deterministic_fallback_used": False,
    }
    exec_path = OUT / "cohort_C_execution_manifest.json"
    exec_path.write_text(json.dumps(exec_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    exec_hash = sha256_file(exec_path)
    stamp = datetime.now(timezone.utc).isoformat()
    lock_txt = (
        "COHORT_C_PREDICTIONS_LOCKED\n"
        f"timestamp_utc: {stamp}\n"
        f"cohort_C_predictions_locked.jsonl sha256: {pred_hash}\n"
        f"cohort_C_execution_manifest.json sha256: {exec_hash}\n"
        "external_labels_opened: false\n"
        "do_not_score\n"
        "do_not_adjudicate\n"
        "do_not_modify_predictions\n"
        "do_not_modify_agent\n"
    )
    (OUT / "COHORT_C_PREDICTIONS_LOCKED.txt").write_text(lock_txt, encoding="utf-8")
    (OUT / "cohort_C_predictions_locked.sha256.json").write_text(
        json.dumps({"file": "cohort_C_predictions_locked.jsonl", "sha256": pred_hash}, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "cohort_C_execution_manifest.sha256.json").write_text(
        json.dumps({"file": "cohort_C_execution_manifest.json", "sha256": exec_hash}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "predictions_sha256": pred_hash,
                "execution_sha256": exec_hash,
                "agentic_ok": len(agentic_ok),
                "agentic_fail": len(agentic_fail),
                "v5_ok": sum(1 for r in v5 if r.get("ok")),
                "conv_ok": sum(1 for r in conv if r.get("ok")),
                "planner_calls": exec_manifest["planner_calls"],
                "critic_calls": exec_manifest["critic_calls"],
                "repairs": exec_manifest["repair_calls"],
                "actions": action_counts,
                "wall": wall,
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    if not INPUT_HASH_SIDECAR.exists():
        raise SystemExit("input manifest was not hashed before execution")
    lock = json.loads(INPUT_HASH_SIDECAR.read_text(encoding="utf-8"))
    input_hash = sha256_file(INPUT_MANIFEST)
    if input_hash != lock.get("sha256"):
        raise SystemExit(f"input manifest hash mismatch: {input_hash} != {lock.get('sha256')}")
    cohort_hash = json.loads((OUT / "cohort_C_manifest.sha256.json").read_text(encoding="utf-8"))["sha256"]
    actual_cohort = sha256_file(MANIFEST)
    if actual_cohort != cohort_hash:
        raise SystemExit(f"cohort manifest hash mismatch: {actual_cohort} != {cohort_hash}")

    started_utc = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    RUNS.mkdir(parents=True, exist_ok=True)
    write_targets()
    agentic_settings = load_settings(ROOT / "config" / "qwen_agentic_dev.yaml")
    v5_settings = load_settings(ROOT / "config" / "qwen_external_v5.yaml")
    inputs = json.loads(INPUT_MANIFEST.read_text(encoding="utf-8"))
    genomes = inputs["genomes"]
    all_rows: list[dict] = []
    for row in genomes:
        acc = row["assembly_accession"]
        genus = row.get("genus")
        assembly = SOLVER / f"{acc}.fna"
        if not assembly.exists():
            raise FileNotFoundError(assembly)
        for target in FROZEN_TARGETS:
            all_rows.append(run_agentic_case(acc, target, assembly, agentic_settings, genus))
        all_rows.extend(
            run_deterministic_condition(
                acc, "DETERMINISTIC_GENOME_SKEPTIC_V5", "genome_skeptic", assembly, v5_settings, genus
            )
        )
        all_rows.extend(
            run_deterministic_condition(
                acc, "FROZEN_CONVENTIONAL_BASELINE", "conventional", assembly, v5_settings, genus
            )
        )
    lock_cohort(all_rows, genomes, started_utc, time.perf_counter() - t0, input_hash, cohort_hash)


if __name__ == "__main__":
    main()
