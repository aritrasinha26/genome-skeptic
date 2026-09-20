#!/bin/bash
set -euo pipefail
EVAL="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval"
NOTE="$EVAL/preserved/resource_rerun_killed_again_during_fast_pilot.txt"
date > "$NOTE"
echo "Killing leftover production evaluate/spades so FAST_PILOT can use WSL RAM." >> "$NOTE"
ps -ef | grep -E "evaluate-real-genomes|spades" | grep -v grep | grep -v fast_pilot >> "$NOTE" || true
mapfile -t PIDS < <(ps -ef | awk '/evaluate-real-genomes --only-cases dev_02,dev_06|bin\/spades.py .*real_genomes_dev_eval|spades-core .*real_genomes_dev_eval/ && !/awk/ {print $2}')
echo "pids ${PIDS[*]:-none}"
if [ "${#PIDS[@]}" -gt 0 ]; then
  kill -TERM "${PIDS[@]}" || true
  sleep 4
fi
if ps -ef | grep -E "only-cases dev_02,dev_06|real_genomes_dev_eval/.*/spades" | grep -v grep >/dev/null; then
  ps -ef | awk '/evaluate-real-genomes --only-cases dev_02,dev_06|bin\/spades.py .*real_genomes_dev_eval|spades-core .*real_genomes_dev_eval/ && !/awk/ {print $2}' | xargs -r kill -KILL || true
fi
echo "remaining production:"
ps -ef | grep -E "only-cases dev_02,dev_06|real_genomes_dev_eval" | grep -v grep || echo none
echo "fast_pilot still running:"
ps -ef | grep fast_pilot | grep -v grep || true
grep -E "MemTotal|MemAvailable" /proc/meminfo
