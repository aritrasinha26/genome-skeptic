#!/bin/bash
set -euo pipefail
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
EVAL="$ROOT/benchmarks/real_genomes_dev_eval"
PRES="$EVAL/preserved"
mkdir -p "$PRES"
cp -a "$EVAL/realgenome_production_report.json" "$PRES/realgenome_production_report.original_m2.json"
cp -a "$EVAL/realgenome_production_report.md" "$PRES/realgenome_production_report.original_m2.md"
if [ -f "$EVAL/real_genome_evaluation.json" ]; then
  cp -a "$EVAL/real_genome_evaluation.json" "$PRES/real_genome_evaluation.original_m2.json"
fi
if [ -d "$EVAL/dev_02" ] && [ ! -d "$PRES/dev_02_m2_oom" ]; then
  cp -a "$EVAL/dev_02" "$PRES/dev_02_m2_oom"
fi
if [ -d "$EVAL/dev_06" ] && [ ! -d "$PRES/dev_06_m2_oom" ]; then
  cp -a "$EVAL/dev_06" "$PRES/dev_06_m2_oom"
fi
echo PRESERVED
ls -la "$PRES"
du -sh "$PRES/dev_02_m2_oom" "$PRES/dev_06_m2_oom" "$PRES"/*.json
