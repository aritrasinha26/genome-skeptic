#!/usr/bin/env bash
set -euo pipefail
BIN=/home/aritr/micromamba/envs/genome-skeptic-prod/bin
echo "BIN=$BIN"
ls "$BIN" | grep -E '^(hmmbuild|hmmsearch|diamond|tblastn|blastp|python|FastTree|fasttree)$' || true
echo "--- versions ---"
"$BIN/python" --version
"$BIN/hmmsearch" -h 2>&1 | head -n 1
"$BIN/hmmbuild" -h 2>&1 | head -n 1
"$BIN/diamond" version
"$BIN/tblastn" -version | head -n 1
"$BIN/blastp" -version | head -n 1
ls "$BIN" | grep -i tree || echo "NO_FASTTREE"
echo "FASTA_SOLVER=$({ ls /home/aritr/m60_work/fasta/solver/*.fna | wc -l; })"
echo "FASTA_ORIG=$({ ls /home/aritr/m60_work/fasta/original/*.fna | wc -l; })"
