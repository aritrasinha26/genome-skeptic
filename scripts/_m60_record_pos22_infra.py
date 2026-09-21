#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
LEDGER = ROOT / "manuscript_benchmark" / "RUN_LOGS" / "M60_EXECUTION_LEDGER.jsonl"
row = {
    "kind": "infrastructure_retry",
    "event": "process_interruption_then_resume",
    "position": 22,
    "case_id": "M60_tetA_tetracycline_efflux_GCF_049810315.1",
    "accession": "GCF_049810315.1",
    "target": "tetA_tetracycline_efflux",
    "stratum": "challenge",
    "original_failure": "process_interruption",
    "detail": "Runner exited code 1 after GS_AGENTIC_V4_1 persisted and before GS_EXHAUSTIVE_V4_1 started or persisted. No Python traceback. Completed arms will not be rerun.",
    "completed_arms_preserved": [
        "CONVENTIONAL",
        "AMRFINDERPLUS",
        "GS_DETERMINISTIC_V4_1",
        "GS_AGENTIC_V4_1",
    ],
    "arm_to_resume": "GS_EXHAUSTIVE_V4_1",
    "scientific_failure": False,
    "retry_allowed": True,
    "identical_inputs": True,
    "git_commit": "8f66868850a98494778966bd729b88a6fc2952eb",
    "scientific_core_hash": "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0",
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "truth_opened": False,
    "accuracy_scored": False,
    "d20_touched": False,
}
LEDGER.parent.mkdir(parents=True, exist_ok=True)
with LEDGER.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(row, default=str) + "\n")
    fh.flush()
    os.fsync(fh.fileno())
print("LEDGER_INFRA_RECORDED")
