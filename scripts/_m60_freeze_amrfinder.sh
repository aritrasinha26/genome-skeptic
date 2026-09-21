#!/usr/bin/env bash
set -euo pipefail
REPO="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/usr/bin:/bin:${PATH}"
export CONDA_PREFIX="/home/aritr/micromamba/envs/genome-skeptic-prod"
export PYTHONPATH="${REPO}/src"
python "${REPO}/scripts/snapshot_amrfinder_database_freeze.py"
mkdir -p "${REPO}/manuscript_benchmark/RUN_LOGS"
if [ ! -f "${REPO}/manuscript_benchmark/RUN_LOGS/M60_EXECUTION_LEDGER.jsonl" ]; then
  : > "${REPO}/manuscript_benchmark/RUN_LOGS/M60_EXECUTION_LEDGER.jsonl"
fi
python - <<'PY'
from pathlib import Path
import hashlib, json
p = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/ENVIRONMENT/AMRFINDER_DATABASE_FREEZE.json")
print("FREEZE_EXISTS", p.exists())
print("FREEZE_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
data = json.loads(p.read_text())
print("DB_VERSION", data.get("database_version"))
print("DB_DIR", data.get("database_directory"))
print("EXE_VERSION", data.get("amrfinder_executable_version"))
print("N_META", len(data.get("metadata_file_manifest") or []))
PY
