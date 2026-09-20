#!/bin/bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
EVAL="$ROOT/benchmarks/real_genomes_dev_eval"
PRES="$EVAL/preserved"
# Restore the original development report so merge keeps successful cases.
cp -a "$PRES/realgenome_production_report.original_m2.json" "$EVAL/realgenome_production_report.json"
cp -a "$PRES/realgenome_production_report.original_m2.md" "$EVAL/realgenome_production_report.md"
# Incomplete killed SPAdes for dev_06 only. Keep successful PAO1 contigs.
rm -rf "$EVAL/dev_06/production/spades"
echo "=== meminfo ==="
grep -E 'MemTotal|MemAvailable|SwapTotal' /proc/meminfo
echo "=== which spades ==="
micromamba run -n genome-skeptic-prod bash -lc 'which spades.py fastp'
echo "=== starting resource rerun (reuse PAO1 assembly; assemble dev_06) ==="
micromamba run -n genome-skeptic-prod python -m genome_skeptic evaluate-real-genomes \
  --visible "$ROOT/benchmarks/real_genomes_dev/agent_visible" \
  --truth "$ROOT/benchmarks/real_genomes_dev/hidden/truth.yaml" \
  --out "$EVAL" \
  --split development \
  --no-ablations \
  --only-cases dev_02,dev_06 \
  --merge-existing \
  --reuse-assembly
echo "=== rerun finished ==="
