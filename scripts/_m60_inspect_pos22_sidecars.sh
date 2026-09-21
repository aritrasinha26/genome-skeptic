#!/usr/bin/env bash
set -euo pipefail
BASE="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/RUNS/position_22/GCF_049810315.1/tetA_tetracycline_efflux"
for s in CONVENTIONAL AMRFINDERPLUS GS_DETERMINISTIC_V4_1 GS_AGENTIC_V4_1; do
  echo "=== $s ==="
  ls -la "$BASE/$s" || true
done
