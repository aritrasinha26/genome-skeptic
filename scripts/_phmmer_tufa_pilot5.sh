#!/usr/bin/env bash
set -euo pipefail
CACHE=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/external_validation_agentic/cohort_C_pilot5_label_cache
OUT="$CACHE/phmmer"
mkdir -p "$OUT"
echo "RUN authentic tufA vs GCF_055394735.1 only"
phmmer --tblout "$OUT/tufA_vs_GCF_055394735.1.tbl" --domtblout "$OUT/tufA_vs_GCF_055394735.1.domtbl" -E 1e-5 --cpu 2 "$CACHE/tufA_NP_417546.faa" "$CACHE/GCF_055394735.1.faa" > "$OUT/tufA_vs_GCF_055394735.1.stdout"
awk '!/^#/ {print}' "$OUT/tufA_vs_GCF_055394735.1.tbl" | head -n 10
echo DOM
awk '!/^#/ {print}' "$OUT/tufA_vs_GCF_055394735.1.domtbl" | head -n 15
