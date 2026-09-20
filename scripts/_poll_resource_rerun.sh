#!/bin/bash
LOG="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval/resource_rerun.nohup.log"
while true; do
  if grep -q "=== rerun finished ===" "$LOG" 2>/dev/null; then
    echo "[$(date +%H:%M:%S)] RERUN FINISHED"
    tail -n 40 "$LOG"
    exit 0
  fi
  if ! pgrep -f "evaluate-real-genomes --only-cases" >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] evaluate process gone before finish"
    tail -n 50 "$LOG"
    exit 1
  fi
  echo "[$(date +%H:%M:%S)] still running"
  ps -ef | grep -E 'spades-core|spades.py|fastp|evaluate-real' | grep -v grep || true
  sleep 180
done
