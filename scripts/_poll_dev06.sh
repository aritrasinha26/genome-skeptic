#!/bin/bash
set -u
PID="${1:-6510}"
EVAL="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval"
while kill -0 "$PID" 2>/dev/null; do
  echo "[$(date +%H:%M:%S)] python $PID still running"
  ps -ef | grep -E 'spades-core|spades.py|fastp|FastQC|minimap|samtools|quast' | grep -v grep || true
  grep -E 'MemAvailable|SwapFree' /proc/meminfo
  if [ -f "$EVAL/dev_06/production/spades/params.txt" ]; then
    grep -E 'Memory limit|Threads' "$EVAL/dev_06/production/spades/params.txt" | head -4
  fi
  if [ -f "$EVAL/dev_06/production/spades/contigs.fasta" ]; then
    echo "contigs: YES $(stat -c%s "$EVAL/dev_06/production/spades/contigs.fasta")"
  else
    echo "contigs: NO"
  fi
  latest=$(ls -t "$EVAL/dev_06/production/spades/spades.log" 2>/dev/null | head -1 || true)
  if [ -n "${latest:-}" ]; then
    tail -n 3 "$latest" | tail -c 700
    echo
  fi
  sleep 180
done
echo "[$(date +%H:%M:%S)] python $PID EXITED"
ls -l "$EVAL/dev_06/production/spades/contigs.fasta" 2>/dev/null || echo "no contigs"
pgrep -af 'evaluate-real-genomes|spades' || echo "no eval/spades"
