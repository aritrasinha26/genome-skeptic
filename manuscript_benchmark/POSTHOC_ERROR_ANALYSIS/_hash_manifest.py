#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


named = [
    "POSTHOC_ERROR_CASES.csv",
    "POSTHOC_ERROR_DETAILED.md",
    "POSTHOC_ROOT_CAUSE_SUMMARY.csv",
    "POSTHOC_MODEL_INVARIANCE.md",
    "POSTHOC_MANUSCRIPT_INTERPRETATION.md",
]
file_sha = {n: sha256_file(OUT / n) for n in named}

manifest = {
    "kind": "POSTHOC_ERROR_ANALYSIS_MANIFEST",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "phase": "posthoc_mechanistic_error_analysis",
    "POST_HOC_ONLY": True,
    "SCIENTIFIC_CODE_MODIFIED": "NO",
    "THRESHOLDS_MODIFIED": "NO",
    "PREDICTIONS_RERUN": "NO",
    "D20_TOUCHED": "NO",
    "CASES_REPLACED": "NO",
    "V42_CREATED": "NO",
    "TRUTH_UNCERTAIN_REINTERPRETED": "NO",
    "n_shared_errors": 8,
    "teta_errors": 7,
    "rpob_errors": 1,
    "primary_root_causes": {
        "INSTRUMENTATION_FAILURE": 0,
        "ACTION_REGISTRY_OR_ELIGIBILITY_LIMIT": 0,
        "EVIDENCE_REPRESENTATION_FAILURE": 0,
        "VALIDATOR_DECISION_LIMIT": 8,
        "BIOLOGICAL_NONDISCRIMINATION": 0,
        "ASSEMBLY_INFORMATION_LIMIT": 0,
        "OTHER": 0,
    },
    "correct_evidence_recovered_by_any_frozen_action": "8 / 8",
    "correct_evidence_reached_targetmeasurements": "8 / 8",
    "errors_fixable_by_different_llm_action_alone": "0 / 8",
    "errors_requiring_new_or_better_scientific_evidence": "0 / 8",
    "errors_requiring_validator_or_representation_change": "8 / 8",
    "qwen_sol_different_investigation_path_among_errors": "8 / 8",
    "different_final_endpoint": "0 / 8",
    "source_sha256": {
        "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json": "a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9",
        "SOL56_M60_MANIFEST.json_file": "2a9f86956ca12026b4ff39fc7bcaf297db992ba4db53421a9482683ae1885a39",
    },
    "source_identity_check": {
        "det_evaluable_errors": 8,
        "same_eight_wrong_for_qwen_exhaustive_sol": True,
        "discrepancy": False,
    },
    "file_sha256": file_sha,
    "supporting_extracts_not_prediction_locks": [
        "_extracted/verification.json",
        "_extracted/error_identity.json",
        "_extracted/compact_forensics.json",
        "_extracted/forensic_print.txt",
    ],
}

path = OUT / "POSTHOC_ERROR_ANALYSIS_MANIFEST.json"
path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
digest = sha256_file(path)
sidecar = {
    "path": "manuscript_benchmark/POSTHOC_ERROR_ANALYSIS/POSTHOC_ERROR_ANALYSIS_MANIFEST.json",
    "sha256": digest,
    "hashed_utc": datetime.now(timezone.utc).isoformat(),
    "truth_opened": True,
    "d20_touched": False,
    "accuracy_scored": False,
    "scientific_code_modified": False,
    "predictions_rerun": False,
    "note": "Post-hoc forensic analysis of locked M60 errors. Truth was opened because the benchmark is unblinded. Predictions were not regenerated.",
}
(OUT / "POSTHOC_ERROR_ANALYSIS_MANIFEST.json.sha256.json").write_text(
    json.dumps(sidecar, indent=2) + "\n", encoding="utf-8"
)
print(digest)
