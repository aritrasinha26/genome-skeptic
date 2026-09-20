#!/bin/bash
set -euo pipefail
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
LOG="$ROOT/benchmarks/real_genomes_dev_eval/resource_rerun.nohup.log"
sed -i 's/\r$//' "$ROOT/scripts/_rerun_resource_failures.sh"
nohup bash "$ROOT/scripts/_rerun_resource_failures.sh" > "$LOG" 2>&1 &
echo "NOHUP_PID=$!"
echo "LOG=$LOG"
sleep 2
head -n 20 "$LOG" || true
