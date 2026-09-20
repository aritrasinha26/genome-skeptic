#!/bin/bash
set -euo pipefail
EVAL="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval"
PRES=$(ls -td "$EVAL"/preserved/resource_rerun_stopped_* | head -1)
echo "PRES=$PRES"
for c in dev_02 dev_06; do
  if [ -d "$EVAL/$c/production/spades" ]; then
    mkdir -p "$PRES/$c/production"
    rm -rf "$PRES/$c/production/spades_tree"
    cp -a "$EVAL/$c/production/spades" "$PRES/$c/production/spades_tree"
    echo "copied $c spades tree"
  fi
  if [ -d "$EVAL/$c/production/fastp" ]; then
    rm -rf "$PRES/$c/production/fastp_tree"
    cp -a "$EVAL/$c/production/fastp" "$PRES/$c/production/fastp_tree"
    echo "copied $c fastp tree"
  fi
done

echo "=== signalling evaluate/spades ==="
mapfile -t PIDS < <(ps -ef | awk '/evaluate-real-genomes|bin\/spades.py|spades-core/ && !/awk/ {print $2}')
echo "pids: ${PIDS[*]:-none}"
if [ "${#PIDS[@]}" -gt 0 ]; then
  kill -TERM "${PIDS[@]}" || true
fi
sleep 5
mapfile -t LEFT < <(ps -ef | awk '/evaluate-real-genomes|bin\/spades.py|spades-core/ && !/awk/ {print $2}')
echo "remaining: ${LEFT[*]:-none}"
if [ "${#LEFT[@]}" -gt 0 ]; then
  echo "still running after SIGTERM; waiting 20s"
  sleep 20
  mapfile -t LEFT < <(ps -ef | awk '/evaluate-real-genomes|bin\/spades.py|spades-core/ && !/awk/ {print $2}')
  echo "remaining2: ${LEFT[*]:-none}"
fi
if ps -ef | grep -E "evaluate-real-genomes|spades-core" | grep -v grep >/dev/null; then
  echo "sending SIGKILL to leftovers"
  ps -ef | awk '/evaluate-real-genomes|bin\/spades.py|spades-core/ && !/awk/ {print $2}' | xargs -r kill -KILL || true
  sleep 2
fi
echo "=== after stop ==="
ps -ef | grep -E "evaluate-real-genomes|spades" | grep -v grep || echo "no spades/evaluate processes"
grep -E "MemTotal|MemAvailable" /proc/meminfo
# Final snapshot of live logs after signal
if [ -f "$EVAL/dev_06/production/spades/spades.log" ]; then
  cp -a "$EVAL/dev_06/production/spades/spades.log" "$PRES/dev_06/production/spades/spades.log.after_term"
  tail -n 8 "$EVAL/dev_06/production/spades/spades.log" || true
fi
echo STOP_OK
