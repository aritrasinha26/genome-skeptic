#!/bin/bash
set -u
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
EVAL="$ROOT/benchmarks/real_genomes_dev_eval"
echo "=== date ==="
date
echo "=== procs ==="
ps -ef | grep -E 'evaluate-real-genomes|spades.py|spades-core|fastp' | grep -v grep || echo none
echo "=== mem ==="
grep -E 'MemTotal|MemAvailable|MemFree|SwapFree' /proc/meminfo
echo "=== dev_06 spades ==="
ls -la "$EVAL/dev_06/production/spades" 2>/dev/null | head
if [ -f "$EVAL/dev_06/production/spades/params.txt" ]; then
  grep -E 'Memory limit|Threads' "$EVAL/dev_06/production/spades/params.txt"
fi
if [ -f "$EVAL/dev_06/production/spades/contigs.fasta" ]; then
  echo "contigs YES $(stat -c%s "$EVAL/dev_06/production/spades/contigs.fasta")"
else
  echo "contigs NO"
fi
if [ -f "$EVAL/dev_06/production/spades/spades.log" ]; then
  echo "--- log tail ---"
  tail -n 8 "$EVAL/dev_06/production/spades/spades.log" | tail -c 1200
fi
echo
echo "=== waiter ==="
pgrep -af _wsl_continue || echo 'NO waiter'
