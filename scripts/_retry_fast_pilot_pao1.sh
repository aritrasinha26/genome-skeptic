#!/bin/bash
# Retry FAST_PILOT PAO1 (dev_02) after K55 mmap OOM. Keep failed logs. Do not touch production eval.
set -euo pipefail
export PYTHONUNBUFFERED=1
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
EVAL="$ROOT/benchmarks/real_genomes_fast_pilot_dev_eval"
PRES="$EVAL/preserved_dev_02_k55_oom"
mkdir -p "$PRES"
if [ -d "$EVAL/dev_02/production/spades" ]; then
  cp -a "$EVAL/dev_02/production/spades/spades.log" "$PRES/spades.log" 2>/dev/null || true
  cp -a "$EVAL/dev_02/production/spades/warnings.log" "$PRES/warnings.log" 2>/dev/null || true
  date > "$PRES/README.txt"
  echo "FAST PILOT - NOT FINAL BENCHMARK. PAO1 first attempt OOM at K55 mmap; retry with thread cap when -m < 5 GB." >> "$PRES/README.txt"
  rm -rf "$EVAL/dev_02/production/spades"
fi
grep -E "MemTotal|MemAvailable" /proc/meminfo
micromamba run -n genome-skeptic-prod python -m genome_skeptic evaluate-real-genomes \
  --visible "$ROOT/benchmarks/real_genomes_fast_pilot_dev/agent_visible" \
  --truth "$ROOT/benchmarks/real_genomes_fast_pilot_dev/hidden/truth.yaml" \
  --out "$EVAL" \
  --split development \
  --no-ablations \
  --config "$ROOT/config/fast_pilot.yaml" \
  --only-cases dev_02 \
  --merge-existing
echo RETRY_DONE
