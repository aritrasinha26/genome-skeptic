#!/bin/bash
set -u
EVAL_ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval"
PID="${1:-21675}"
while kill -0 "$PID" 2>/dev/null; do
  echo "[$(date +%H:%M:%S)] python $PID still running"
  ps -ef | grep -E 'spades-core|spades.py|fastp|FastQC|minimap2|samtools|quast' | grep -v grep || true
  echo "cases:"
  ls -1 "$EVAL_ROOT" | grep '^dev_' || true
  if [ -f "$EVAL_ROOT/realgenome_production_report.json" ]; then
    echo "report: YES"
  else
    echo "report: no"
  fi
  latest=$(ls -t "$EVAL_ROOT"/dev_*/production/spades/spades.log 2>/dev/null | head -1 || true)
  if [ -n "${latest:-}" ]; then
    echo "log=$latest"
    tail -n 4 "$latest" | tail -c 900
  fi
  echo
  sleep 180
done
echo "[$(date +%H:%M:%S)] python $PID EXITED"
ls -l "$EVAL_ROOT/realgenome_production_report.json" 2>/dev/null || echo "no report file"
ps -ef | grep -E 'evaluate-real-genomes|spades' | grep -v grep || echo "no eval/spades processes"
