#!/usr/bin/env bash
set -euo pipefail
BASE="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/RUNS/position_22/GCF_049810315.1/tetA_tetracycline_efflux"
ls -la "$BASE" || true
for s in CONVENTIONAL AMRFINDERPLUS GS_DETERMINISTIC_V4_1 GS_AGENTIC_V4_1 GS_EXHAUSTIVE_V4_1; do
  p="$BASE/$s/case_locked.json"
  if [ -f "$p" ]; then
    echo "OK $s $(stat -c%s "$p")"
  else
    echo "MISSING $s"
  fi
done
echo "--- position locks ---"
ls /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/POSITION_LOCKS | sed -n '1,80p'
