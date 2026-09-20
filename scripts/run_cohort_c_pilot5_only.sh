#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
cd /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
export PYTHONPATH=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/src
export PYTHONUNBUFFERED=1
LOG=external_validation_agentic/cohort_C_pilot5_run.log
HB=external_validation_agentic/cohort_C_pilot5_heartbeat.log
echo "RESUME $(date -Is) python=$(command -v python)" | tee -a "$LOG"
(
  while true; do
    echo "$(date -Is) alive python=$(pgrep -c -f 'scripts/run_cohort_c_pilot5.py' || true)" >>"$HB"
    sleep 30
  done
) &
HBPID=$!
trap 'kill $HBPID 2>/dev/null || true' EXIT
python -u scripts/run_cohort_c_pilot5.py
echo "PYTHON_EXIT $? $(date -Is)" | tee -a "$LOG"
