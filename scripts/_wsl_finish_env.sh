#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
micromamba install -y -n genome-skeptic-prod wgsim || micromamba install -y -n genome-skeptic-prod dwgsim || echo "WGSIM_SOLVE_FAILED"
micromamba install -y -n genome-skeptic-prod checkm2 || echo "CHECKM2_SOLVE_FAILED"
micromamba run -n genome-skeptic-prod pip install -e "$ROOT"
echo "--- tools ---"
for t in fastp fastqc spades.py quast.py minimap2 samtools mmseqs diamond hmmsearch wgsim FastTree bakta checkm2 kraken2 sourmash prodigal; do
  p=$(micromamba run -n genome-skeptic-prod which "$t" 2>/dev/null || true)
  echo "$t ${p:-MISSING}"
done
