#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
export M60_TRUTH_BIN=/home/aritr/micromamba/envs/genome-skeptic-prod/bin
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PY="$M60_TRUTH_BIN/python"
cd "$ROOT"
echo "=== PHASE 3 freeze independent truth sources ==="
if [ -f "$ROOT/manuscript_benchmark/TRUTH_M60/M60_TRUTH_SOURCE_MANIFEST.json" ]; then
  echo "truth source already frozen; not altering"
else
  "$PY" -u scripts/freeze_m60_truth_sources.py
fi
export PYTHONUNBUFFERED=1
export M60_TRUTH_THREADS=4
echo "=== PHASE 3 adjudicate 60 cases ==="
"$PY" -u scripts/adjudicate_m60_truth.py
echo "=== PHASE 3 second pass + lock ==="
"$PY" -u scripts/lock_m60_truth.py
echo "=== PHASE 3 done ==="
