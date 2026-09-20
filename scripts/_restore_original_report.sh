#!/bin/bash
set -euo pipefail
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
EVAL="$ROOT/benchmarks/real_genomes_dev_eval"
PRES="$EVAL/preserved"
cp -a "$PRES/realgenome_production_report.original_m2.json" "$EVAL/realgenome_production_report.json"
cp -a "$PRES/realgenome_production_report.original_m2.md" "$EVAL/realgenome_production_report.md"
cp -a "$PRES/real_genome_evaluation.original_m2.json" "$EVAL/real_genome_evaluation.json"
cp -a "$PRES/realgenome_production_report.original_m2.md" "$EVAL/real_genome_report.md"
for case in dev_02 dev_06; do
  rm -rf "$EVAL/$case/production" "$EVAL/$case/conventional" "$EVAL/$case/skeptic_no_falsification" "$EVAL/$case/genome_skeptic"
done
echo restored original reports and cleared stale production
ls -la "$EVAL/dev_02" "$EVAL/dev_06"
