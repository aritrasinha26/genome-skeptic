#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
LOCK="$ROOT/manuscript_benchmark/POSITION_LOCKS"
RUNS="$ROOT/manuscript_benchmark/RUNS"
LEDGER="$ROOT/manuscript_benchmark/RUN_LOGS/M60_EXECUTION_LEDGER.jsonl"

echo "=== LOCKED POSITIONS ==="
for i in $(seq -w 1 60); do
  if [ -f "$LOCK/position_$i/POSITION_LOCK.json" ]; then
    echo "LOCKED $i"
  else
    echo "NOLOCK $i"
  fi
done

echo "=== PROCESSES ==="
ps -ef | grep -E 'run_m60_position|finalize_m60' | grep -v grep || true

echo "=== LEDGER TAIL ==="
python3 - <<'PY'
from pathlib import Path
p = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/RUN_LOGS/M60_EXECUTION_LEDGER.jsonl")
lines = p.read_text(encoding="utf-8").splitlines()
print("ledger_lines", len(lines))
for line in lines[-15:]:
    print(line[:400])
PY

echo "=== INCOMPLETE RUN DIRS 46-60 ==="
for i in $(seq 46 60); do
  d=$(printf "%s/position_%02d" "$RUNS" "$i")
  if [ -d "$d" ]; then
    echo "-- position $i --"
    find "$d" -maxdepth 5 -type d | sed "s|$RUNS/||"
    for p in "$d"/*/*/{CONVENTIONAL,AMRFINDERPLUS,NCBI_REFSEQ_PGAP,GS_DETERMINISTIC_V4_1,GS_AGENTIC_V4_1,GS_EXHAUSTIVE_V4_1}/case_locked.json; do
      if [ -f "$p" ]; then
        echo "OK $(echo "$p" | sed "s|$RUNS/||") $(stat -c%s "$p")"
      fi
    done
  else
    echo "NO_RUN_DIR position_$i"
  fi
done
