#!/usr/bin/env bash
set -euo pipefail
rm -rf /home/aritr/m60_work/truth_evidence
mkdir -p /home/aritr/m60_work/truth_evidence
REC=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/TRUTH_M60/CASE_RECORDS
EV=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/TRUTH_M60/EVIDENCE
rm -rf "$REC" "$EV"
mkdir -p "$REC" "$EV"
echo cleaned
