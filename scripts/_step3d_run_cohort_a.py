#!/usr/bin/env python3
"""STEP 3D-C/D/E: run frozen conditions on sanitized Cohort A FASTA and lock predictions.

Does not inspect external labels, download annotations, score, or change V5 science.
Resumes genomes that already have a locked result. Does not regenerate successes.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.providers import CALL_LOG, reset_call_log
from genome_skeptic.config import load_settings
from genome_skeptic.eval.evaluate_real import _run_system
from genome_skeptic.families import load_family, list_family_ids

OUT = ROOT / "external_validation"
RUNS = OUT / "cohort_A_runs"
INPUTS = OUT / "cohort_A_inputs"
SOLVER = INPUTS / "solver"
TARGETS = INPUTS / "targets.fa"
EMPTY_REFS = INPUTS / "references.yaml"

CONDITIONS = [
    ("FULL_GENOME_SKEPTIC_V5", "genome_skeptic"),
    ("V5_NO_FALSIFICATION", "skeptic_no_falsification"),
    ("FROZEN_CONVENTIONAL_BASELINE", "conventional"),
]
FROZEN_TARGETS = [
    "tetA_tetracycline_efflux",
    "mfs_multidrug_efflux",
    "rnd_efflux",
    "recA_recombinase",
    "tuf_EF_Tu",
    "lacZ_beta_galactosidase",
    "rpoB_RNAP_beta",
    "rpoC_RNAP_beta_prime",
]


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


def _call_stats(log: list[dict]) -> dict:
    n = len(log)
    repairs = sum(1 for r in log if r.get("retry_count") or str(r.get("request_type") or "").endswith("_repair"))
    malformed = sum(1 for r in log if r.get("schema_valid") is False)
    timeouts = sum(1 for r in log if "timeout" in str(r.get("finish_reason") or "").lower() or "timeout" in str(r).lower())
    return {
        "model_call_count": n,
        "repair_count": repairs,
        "malformed_output_count": malformed,
        "timeout_count": timeouts,
        "call_log": log,
    }


def _prediction_row(acc: str, condition: str, claim, family_blob: dict | None, locus: dict | None, sys_seconds: float, call_stats: dict, tools_used: list[str]) -> dict:
    qid = claim.claim_id.replace("C_target_", "")
    tests = [t.model_dump(mode="json") for t in (claim.falsification_tests or [])]
    recon = (family_blob or {}).get("reconstruction") or {}
    multi = (family_blob or {}).get("multiplicity") or recon.get("multiplicity") or {}
    comp = (family_blob or {}).get("competitive_family") or recon.get("competitive_family") or {}
    coords = None
    if locus and (locus.get("genomic_start") is not None):
        coords = {
            "contig": locus.get("contig"),
            "start": locus.get("genomic_start"),
            "end": locus.get("genomic_end"),
            "strand": locus.get("strand"),
        }
    elif recon.get("coordinates"):
        coords = recon.get("coordinates")
    elif multi.get("coordinates"):
        coords = multi.get("coordinates")
    return {
        "assembly_accession": acc,
        "condition": condition,
        "target": qid,
        "final_claim": claim.claim_type.value if claim.claim_type else None,
        "classification": claim.status.value if claim.status else None,
        "confidence": claim.confidence,
        "evidence_ids": list(claim.supporting_evidence_ids or []) + list(claim.contradicting_evidence_ids or []),
        "supporting_evidence": list(claim.supporting_evidence_ids or []),
        "contradictory_evidence": list(claim.contradicting_evidence_ids or []),
        "alternative_hypotheses": list(claim.alternative_explanations or []),
        "falsification_actions": tests,
        "final_selected_action_path": list(claim.recommended_next_actions or []),
        "locus_coordinates": coords,
        "architecture_classification": claim.architecture_state or (family_blob or {}).get("architecture") or (locus or {}).get("architecture"),
        "multiplicity_estimate": {
            "number_of_candidate_loci": multi.get("number_of_candidate_loci"),
            "classification": multi.get("classification"),
        } if multi else None,
        "unresolved_status": claim.status.value if claim.status and claim.status.value == "unresolved" else None,
        "orthology_class": claim.orthology_class,
        "homology_support": claim.homology_support,
        "statement": claim.statement,
        "model_call_count": call_stats["model_call_count"],
        "repair_count": call_stats["repair_count"],
        "runtime_seconds": sys_seconds,
        "deterministic_tools_used": tools_used,
        "requires_adjudication_endpoint": qid in {"mfs_multidrug_efflux", "rnd_efflux"},
    }


def load_family_blob(sys_dir: Path, qid: str) -> dict | None:
    path = sys_dir / "family" / qid / "family_evidence.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def run_genome(acc: str, genus: str | None, settings, input_row: dict) -> dict:
    dest = RUNS / acc / "locked.json"
    if dest.exists() and dest.stat().st_size > 50:
        print(f"skip completed {acc}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    assembly = SOLVER / f"{acc}.fna"
    if not assembly.exists():
        raise FileNotFoundError(assembly)
    genome_out = RUNS / acc
    genome_out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    predictions = []
    condition_status = {}
    totals = {"model_call_count": 0, "repair_count": 0, "malformed_output_count": 0, "timeout_count": 0}
    for cond_name, sys_name in CONDITIONS:
        print(f"{acc} {cond_name}", flush=True)
        sys_dir = genome_out / sys_name
        reset_call_log()
        started = time.perf_counter()
        try:
            flags = None
            if sys_name == "skeptic_no_falsification":
                flags = {"enable_falsification": False}
            elif sys_name == "genome_skeptic":
                flags = {"enable_falsification": True}
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
            elapsed = time.perf_counter() - started
            stats = _call_stats(list(CALL_LOG))
            for k in ("model_call_count", "repair_count", "malformed_output_count", "timeout_count"):
                totals[k] += stats[k]
            claims = payload.get("claims") or []
            loci = payload.get("loci") or []
            locus_by_q = {}
            for le in loci:
                q = getattr(le, "query_id", None) or (le.get("query_id") if isinstance(le, dict) else None)
                if q and q not in locus_by_q:
                    locus_by_q[q] = le.model_dump(mode="json") if hasattr(le, "model_dump") else le
            tools = []
            for claim in claims:
                qid = claim.claim_id.replace("C_target_", "")
                fam = load_family_blob(sys_dir, qid)
                tools = list(dict.fromkeys(tools + ((fam or {}).get("tools_run") or [])))
                loc = locus_by_q.get(qid)
                predictions.append(_prediction_row(acc, cond_name, claim, fam, loc, elapsed, stats, tools))
            condition_status[cond_name] = {
                "ok": True,
                "seconds": elapsed,
                "n_claims": len(claims),
                "reused": bool(payload.get("reused")),
                **{k: stats[k] for k in ("model_call_count", "repair_count", "malformed_output_count", "timeout_count")},
            }
        except Exception as exc:
            elapsed = time.perf_counter() - started
            stats = _call_stats(list(CALL_LOG))
            for k in ("model_call_count", "repair_count", "malformed_output_count", "timeout_count"):
                totals[k] += stats[k]
            condition_status[cond_name] = {
                "ok": False,
                "seconds": elapsed,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=8),
                **{k: stats[k] for k in ("model_call_count", "repair_count", "malformed_output_count", "timeout_count")},
            }
            print(f"FAIL {acc} {cond_name}: {exc}", flush=True)
    result = {
        "assembly_accession": acc,
        "solver_fasta_sha256": input_row.get("solver_fasta_sha256"),
        "original_fasta_sha256": input_row.get("original_fasta_sha256"),
        "completed": all(v.get("ok") for v in condition_status.values()) and len(condition_status) == 3,
        "wall_seconds": time.perf_counter() - t0,
        "conditions": condition_status,
        "n_predictions": len(predictions),
        "totals": totals,
        "predictions": predictions,
        "external_labels_opened": False,
    }
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(dest)
    print(f"locked genome {acc} completed={result['completed']} n={len(predictions)} s={result['wall_seconds']:.1f}", flush=True)
    return result


def lock_cohort(results: list[dict], settings, started_utc: str, wall: float) -> None:
    run_hash = json.loads((OUT / "cohort_A_run_config.sha256.json").read_text(encoding="utf-8"))["sha256"]
    input_hash = json.loads((OUT / "cohort_A_input_manifest.sha256.json").read_text(encoding="utf-8"))["sha256"]
    jsonl = OUT / "cohort_A_predictions_locked.jsonl"
    lines = []
    for rec in results:
        for pred in rec.get("predictions") or []:
            lines.append(json.dumps(pred, ensure_ascii=False, separators=(",", ":")))
    jsonl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    pred_hash = sha256_file(jsonl)
    completed = [r["assembly_accession"] for r in results if r.get("completed")]
    failed = [r["assembly_accession"] for r in results if not r.get("completed")]
    by_cond = {}
    for r in results:
        for p in r.get("predictions") or []:
            by_cond[p["condition"]] = by_cond.get(p["condition"], 0) + 1
    totals = {"model_call_count": 0, "repair_count": 0, "malformed_output_count": 0, "timeout_count": 0}
    for r in results:
        t = r.get("totals") or {}
        for k in totals:
            totals[k] += int(t.get(k) or 0)
    exec_manifest = {
        "kind": "cohort_A_execution_manifest",
        "locked_utc": datetime.now(timezone.utc).isoformat(),
        "started_utc": started_utc,
        "cohort_description": "taxonomically stratified external cohort",
        "not_a_natural_refseq_prevalence_sample": True,
        "run_config_sha256": run_hash,
        "input_manifest_sha256": input_hash,
        "genome_skeptic_v5_freeze_hash": "0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b",
        "model": "qwen3:4b",
        "conditions": [c[0] for c in CONDITIONS],
        "n_genomes": len(results),
        "all_genome_accessions": [r["assembly_accession"] for r in results],
        "successfully_completed_genomes": completed,
        "failed_or_incomplete_genomes": failed,
        "n_successfully_completed": len(completed),
        "n_failed_or_incomplete": len(failed),
        "target_prediction_counts_by_condition": by_cond,
        "model_call_counts": totals["model_call_count"],
        "malformed_output_counts": totals["malformed_output_count"],
        "repair_counts": totals["repair_count"],
        "timeout_counts": totals["timeout_count"],
        "total_wall_time_seconds": wall,
        "software_versions": json.loads((OUT / "cohort_A_run_config.json").read_text(encoding="utf-8")).get("deterministic_tools_available_at_freeze"),
        "llm": json.loads((OUT / "cohort_A_run_config.json").read_text(encoding="utf-8")).get("llm"),
        "input_hashes": {
            r["assembly_accession"]: {
                "original_fasta_sha256": r.get("original_fasta_sha256"),
                "solver_fasta_sha256": r.get("solver_fasta_sha256"),
            }
            for r in results
        },
        "predictions_locked_sha256": pred_hash,
        "external_labels_opened": False,
        "scores_computed": False,
        "v5_scientific_logic_modified": False,
        "thresholds_tuned_after_outputs": False,
    }
    exec_path = OUT / "cohort_A_execution_manifest.json"
    exec_path.write_text(json.dumps(exec_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    exec_hash = sha256_file(exec_path)
    stamp = datetime.now(timezone.utc).isoformat()
    lock_txt = (
        "COHORT_A_PREDICTIONS_LOCKED\n"
        f"timestamp_utc: {stamp}\n"
        f"cohort_A_predictions_locked.jsonl sha256: {pred_hash}\n"
        f"cohort_A_execution_manifest.json sha256: {exec_hash}\n"
        "external_labels_opened: false\n"
        "do_not_modify_predictions\n"
    )
    (OUT / "COHORT_A_PREDICTIONS_LOCKED.txt").write_text(lock_txt, encoding="utf-8")
    print(json.dumps({
        "predictions_sha256": pred_hash,
        "execution_sha256": exec_hash,
        "completed": len(completed),
        "failed": len(failed),
        "by_cond": by_cond,
        "model_calls": totals["model_call_count"],
        "wall": wall,
    }, indent=2), flush=True)


def main() -> None:
    started_utc = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    RUNS.mkdir(parents=True, exist_ok=True)
    write_targets()
    settings = load_settings(ROOT / "config" / "qwen_external_v5.yaml")
    inputs = json.loads((OUT / "cohort_A_input_manifest.json").read_text(encoding="utf-8"))
    results = []
    for row in inputs["genomes"]:
        acc = row["assembly_accession"]
        try:
            results.append(run_genome(acc, row.get("genus"), settings, row))
        except Exception as exc:
            print(f"GENOME FAIL {acc}: {exc}", flush=True)
            traceback.print_exc()
            results.append({
                "assembly_accession": acc,
                "completed": False,
                "error": str(exc),
                "predictions": [],
                "totals": {"model_call_count": 0, "repair_count": 0, "malformed_output_count": 0, "timeout_count": 0},
                "original_fasta_sha256": row.get("original_fasta_sha256"),
                "solver_fasta_sha256": row.get("solver_fasta_sha256"),
            })
    lock_cohort(results, settings, started_utc, time.perf_counter() - t0)


if __name__ == "__main__":
    main()
