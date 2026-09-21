#!/usr/bin/env bash
set -euo pipefail
PUB="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/RUNS/position_46/GCF_053612185.1/tetA_tetracycline_efflux"
WORK="/home/aritr/m60_work/runs/position_46/GCF_053612185.1/tetA_tetracycline_efflux"
STAMP="interrupted_attempt_20260921T062400Z"

preserve() {
  local parent="$1"
  local src="$parent/GS_EXHAUSTIVE_V4_1"
  local dest="$parent/GS_EXHAUSTIVE_V4_1__${STAMP}"
  if [ -d "$src" ]; then
    if [ -f "$src/case_locked.json" ]; then
      echo "REFUSE_MOVE complete arm at $src"
      exit 1
    fi
    mv "$src" "$dest"
    echo "PRESERVED $dest"
  else
    echo "NO_DIR $src"
  fi
}

preserve "$PUB"
preserve "$WORK"

python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
row = {
    "kind": "infrastructure_retry",
    "event": "process_interruption_then_resume",
    "position": 46,
    "case_id": "M60_tetA_tetracycline_efflux_GCF_053612185.1",
    "accession": "GCF_053612185.1",
    "target": "tetA_tetracycline_efflux",
    "stratum": "routine",
    "original_failure": "process_interruption",
    "detail": "Background runner disappeared after GS_AGENTIC_V4_1 persisted and while GS_EXHAUSTIVE_V4_1 was in progress. No case_locked.json for exhaustive. Incomplete exhaustive artifacts preserved as GS_EXHAUSTIVE_V4_1__interrupted_attempt_20260921T062400Z. Completed arms CONVENTIONAL, AMRFINDERPLUS, GS_DETERMINISTIC_V4_1, GS_AGENTIC_V4_1 will not be rerun.",
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

for path in [
    ROOT / "manuscript_benchmark" / "RUN_LOGS" / "M60_EXECUTION_LEDGER.jsonl",
    ROOT / "manuscript_benchmark" / "RUN_LOGS" / "M60_INFRASTRUCTURE_RETRIES.jsonl",
]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
print("INFRA_RECORDED")
PY
