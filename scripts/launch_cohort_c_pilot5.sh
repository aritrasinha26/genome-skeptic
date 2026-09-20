#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
LOG="$ROOT/external_validation_agentic/cohort_C_pilot5_run.log"
PIDF="$ROOT/external_validation_agentic/cohort_C_pilot5_run.pid"
nohup bash "$ROOT/scripts/run_cohort_c_pilot5_only.sh" >>"$LOG" 2>&1 &
echo $! >"$PIDF"
echo "started pid=$(cat "$PIDF") log=$LOG"
