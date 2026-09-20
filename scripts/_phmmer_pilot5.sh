#!/usr/bin/env bash
set -euo pipefail
CACHE=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/external_validation_agentic/cohort_C_pilot5_label_cache
OUT="$CACHE/phmmer"
mkdir -p "$OUT"
for seed in NP_418414.1 NP_418240.1 NP_414878.1; do
  for acc in GCF_055394735.1 GCF_055378285.1; do
    echo "RUN $seed $acc"
    phmmer --tblout "$OUT/${seed}_vs_${acc}.tbl" --domtblout "$OUT/${seed}_vs_${acc}.domtbl" -E 1e-5 --cpu 2 "$CACHE/${seed}.faa" "$CACHE/${acc}.faa" > "$OUT/${seed}_vs_${acc}.stdout"
    echo TOP
    awk '!/^#/ {print}' "$OUT/${seed}_vs_${acc}.tbl" | head -n 8
    echo
  done
done
