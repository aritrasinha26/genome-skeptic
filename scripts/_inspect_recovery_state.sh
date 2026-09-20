#!/bin/bash
set -u
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
EVAL="$ROOT/benchmarks/real_genomes_dev_eval"
echo "=== date ==="
date
echo "=== waiter ==="
pgrep -af '_wsl_continue' || echo 'NO _wsl_continue.sh'
echo "=== eval/spades procs ==="
ps -ef | grep -E 'evaluate-real-genomes|spades.py|spades-core|fastp|minimap|samtools|quast' | grep -v grep || echo 'none'
echo "=== process tree of evaluate ==="
pgrep -af 'evaluate-real-genomes' || true
echo "=== meminfo ==="
grep -E 'MemTotal|MemAvailable|MemFree|SwapTotal|SwapFree' /proc/meminfo
echo "=== free ==="
free -h
echo "=== nproc ==="
nproc
echo "=== eval dir ==="
ls -la "$EVAL" | head -80
echo "=== cases ==="
ls -1d "$EVAL"/dev_* 2>/dev/null
echo "=== reports ==="
ls -l "$EVAL"/realgenome_production_report.json "$EVAL"/realgenome_production_report.md "$ROOT"/realgenome_production_report.json "$ROOT"/realgenome_production_report.md "$ROOT"/heldout_freeze_manifest.json 2>/dev/null
echo "=== per-case production ==="
for c in "$EVAL"/dev_0*; do
  [ -d "$c" ] || continue
  name=$(basename "$c")
  echo "--- $name ---"
  ls "$c" 2>/dev/null
  if [ -f "$c/production/spades/contigs.fasta" ]; then
    echo "contigs: YES ($(stat -c%s "$c/production/spades/contigs.fasta") bytes)"
  else
    echo "contigs: NO"
  fi
  if [ -f "$c/production/spades/params.txt" ]; then
    grep -E 'Memory limit|Threads' "$c/production/spades/params.txt" | head -5
  fi
  if [ -f "$c/production/spades/spades.log" ]; then
    echo "spades.log last:"
    tail -n 4 "$c/production/spades/spades.log" | tail -c 500
    echo
  fi
  if [ -f "$c/spades_resource_provenance.json" ]; then
    echo "provenance present"
  fi
done
echo "=== preserved ==="
ls -la "$EVAL/preserved" 2>/dev/null | head -40
echo "=== rerun log tail ==="
tail -n 30 "$EVAL/resource_rerun.nohup.log" 2>/dev/null || echo 'no rerun log'
echo "=== .wslconfig ==="
cat /mnt/c/Users/aritr/.wslconfig 2>/dev/null || echo 'no .wslconfig'
