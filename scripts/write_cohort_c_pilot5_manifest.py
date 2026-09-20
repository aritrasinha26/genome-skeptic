#!/usr/bin/env python3
"""Write and hash the Cohort C 5-case external pilot manifest.

Selection uses only the pre-existing frozen Cohort C execution order:
input-manifest genome list × frozen targets_locked, matching
scripts/run_cohort_c_agentic.py. Does not inspect predictions, external
labels, annotations, or gene content. Does not modify Agentic V1, V5
science, or the Cohort C 40-case manifests.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation_agentic"
MANIFEST = OUT / "cohort_C_manifest.json"
MANIFEST_HASH = OUT / "cohort_C_manifest.sha256.json"
INPUT_MANIFEST = OUT / "cohort_C_input_manifest.json"
INPUT_HASH = OUT / "cohort_C_input_manifest.sha256.json"
PILOT = OUT / "cohort_C_pilot5_manifest.json"
PILOT_HASH = OUT / "cohort_C_pilot5_manifest.sha256.json"
RUNS = OUT / "cohort_C_runs"

FROZEN_TARGETS = [
    "rpoB_RNAP_beta",
    "tuf_EF_Tu",
    "lacZ_beta_galactosidase",
    "tetA_tetracycline_efflux",
]
CONDITIONS = [
    "GENOME_SKEPTIC_AGENTIC_V1",
    "DETERMINISTIC_GENOME_SKEPTIC_V5",
    "FROZEN_CONVENTIONAL_BASELINE",
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


def agentic_case_path(acc: str, target: str) -> Path:
    return RUNS / acc / "genome_skeptic_agentic" / target / "case_locked.json"


def main() -> None:
    cohort_lock = json.loads(MANIFEST_HASH.read_text(encoding="utf-8"))
    input_lock = json.loads(INPUT_HASH.read_text(encoding="utf-8"))
    cohort_hash = sha256_file(MANIFEST)
    input_hash = sha256_file(INPUT_MANIFEST)
    if cohort_hash != cohort_lock.get("sha256"):
        raise SystemExit(f"cohort_C_manifest.json hash mismatch: {cohort_hash} != {cohort_lock.get('sha256')}")
    if input_hash != input_lock.get("sha256"):
        raise SystemExit(f"cohort_C_input_manifest.json hash mismatch: {input_hash} != {input_lock.get('sha256')}")

    cohort = json.loads(MANIFEST.read_text(encoding="utf-8"))
    inputs = json.loads(INPUT_MANIFEST.read_text(encoding="utf-8"))
    if list(cohort.get("targets_locked") or []) != FROZEN_TARGETS:
        raise SystemExit("frozen targets_locked drifted from execution-order targets")
    genomes = inputs["genomes"]
    cohort_acc = [a["assembly_accession"] for a in cohort["assemblies"]]
    input_acc = [g["assembly_accession"] for g in genomes]
    if cohort_acc != input_acc:
        raise SystemExit("cohort_C_manifest assemblies order != input_manifest genomes order")

    full_order = []
    pos = 0
    for genome in genomes:
        acc = genome["assembly_accession"]
        for target in FROZEN_TARGETS:
            pos += 1
            full_order.append(
                {
                    "frozen_execution_position": pos,
                    "assembly_accession": acc,
                    "organism": genome.get("organism"),
                    "genus": genome.get("genus"),
                    "phylum": genome.get("phylum"),
                    "assembly_level": genome.get("assembly_level"),
                    "target": target,
                }
            )
    if len(full_order) != 40:
        raise SystemExit(f"expected 40 frozen genome-target cases, got {len(full_order)}")

    pilot_cases = []
    for row in full_order[:5]:
        dest = agentic_case_path(row["assembly_accession"], row["target"])
        immutable = dest.exists() and dest.stat().st_size > 50
        status = "reuse_immutable_case_locked_json" if immutable else "incomplete_may_rerun"
        if immutable:
            locked = json.loads(dest.read_text(encoding="utf-8"))
            ok = locked.get("ok") is True and locked.get("agent_execution_failure") is None
            validator = locked.get("final_validator_ran") is True
            planner = locked.get("planner_invoked") is True
            critic = locked.get("critic_invoked") is True
            fallback = locked.get("silent_deterministic_fallback") is True
            if not (ok and validator and planner and critic and not fallback):
                status = "locked_file_present_but_not_successful_rerun"
                immutable = False
        case = dict(row)
        case["agentic_case_locked_path"] = str(dest.relative_to(ROOT)).replace("\\", "/")
        case["immutable_agentic_result_present"] = immutable
        case["execution_plan"] = status
        pilot_cases.append(case)

    if [c["frozen_execution_position"] for c in pilot_cases] != [1, 2, 3, 4, 5]:
        raise SystemExit("pilot cases are not frozen positions 1-5")

    payload = {
        "kind": "cohort_C_pilot5_manifest",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "preliminary_external_pilot": True,
        "full_40_case_execution_stopped": True,
        "selection_rule": "exactly the first 5 genome-target cases in the already-frozen Cohort C execution order",
        "execution_order_definition": (
            "for genome in cohort_C_input_manifest.json['genomes'] "
            "(same accession order as cohort_C_manifest.json['assemblies']): "
            "for target in cohort_C_manifest.json['targets_locked']: emit (genome, target). "
            "This is the main loop of scripts/run_cohort_c_agentic.py."
        ),
        "selection_used_predictions": False,
        "selection_used_external_labels": False,
        "selection_used_annotations": False,
        "selection_used_gene_content": False,
        "external_labels_opened": False,
        "scores_computed": False,
        "adjudication_performed": False,
        "agent_modified": False,
        "cohort_C_manifest_modified": False,
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V1",
        "agentic_v1_freeze_hash": AGENTIC_FREEZE_SHA,
        "agentic_v1_freeze_summary_sha256": AGENTIC_SUMMARY_SHA,
        "genome_skeptic_v5_freeze_hash": V5_FREEZE,
        "cohort_C_manifest_sha256": cohort_hash,
        "cohort_C_input_manifest_sha256": input_hash,
        "model": "qwen3:4b",
        "model_digest": MODEL_DIGEST,
        "thinking": False,
        "temperature": 0,
        "structured_output": "Ollama native schema",
        "maximum_repairs": 1,
        "final_scientific_authority": "deterministic validator",
        "required_agentic_path": [
            "deterministic evidence",
            "Qwen planner",
            "registered action",
            "new deterministic evidence",
            "Qwen critic",
            "deterministic validator",
        ],
        "silent_deterministic_fallback_forbidden": True,
        "conditions": CONDITIONS,
        "n_frozen_genome_target_cases": 40,
        "n_pilot_genome_target_cases": 5,
        "n_predictions": 15,
        "frozen_targets_locked": FROZEN_TARGETS,
        "frozen_genome_order": input_acc,
        "proof_positions_1_to_5": {
            "method": "prefix of frozen cartesian execution order",
            "frozen_execution_positions": [1, 2, 3, 4, 5],
            "next_excluded_position": 6,
            "next_excluded_case": {
                "frozen_execution_position": 6,
                "assembly_accession": full_order[5]["assembly_accession"],
                "target": full_order[5]["target"],
            },
        },
        "pilot_cases": pilot_cases,
        "frozen_full_execution_order_genome_target_cases": full_order,
        "reused_immutable_agentic_results": [
            {
                "frozen_execution_position": c["frozen_execution_position"],
                "assembly_accession": c["assembly_accession"],
                "target": c["target"],
            }
            for c in pilot_cases
            if c["immutable_agentic_result_present"]
        ],
        "incomplete_cases_to_rerun": [
            {
                "frozen_execution_position": c["frozen_execution_position"],
                "assembly_accession": c["assembly_accession"],
                "target": c["target"],
                "reason": c["execution_plan"],
            }
            for c in pilot_cases
            if not c["immutable_agentic_result_present"]
        ],
        "lock_after_completion": "external_validation_agentic/cohort_C_pilot5_predictions_locked.jsonl",
        "stop_before_label_access": True,
    }
    PILOT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = sha256_file(PILOT)
    PILOT_HASH.write_text(
        json.dumps(
            {
                "file": "cohort_C_pilot5_manifest.json",
                "sha256": digest,
                "hashed_utc": datetime.now(timezone.utc).isoformat(),
                "hashed_before_label_access": True,
                "n_pilot_cases": 5,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"pilot_manifest_sha256": digest, "n_reuse": len(payload["reused_immutable_agentic_results"]), "n_rerun": len(payload["incomplete_cases_to_rerun"])}, indent=2), flush=True)


if __name__ == "__main__":
    main()
