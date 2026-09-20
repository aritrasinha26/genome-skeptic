#!/bin/bash
set -euo pipefail
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
EVAL="$ROOT/benchmarks/real_genomes_dev_eval"
# Fresh production for resource reruns; original trees live under preserved/.
for case in dev_02 dev_06; do
  if [ -d "$EVAL/$case/production" ]; then
    rm -rf "$EVAL/$case/production"
  fi
  for sys in conventional skeptic_no_falsification genome_skeptic; do
    rm -rf "$EVAL/$case/$sys"
  done
done
echo "cleared failed production dirs; provenance JSON kept:"
ls -la "$EVAL/dev_02" "$EVAL/dev_06"
