#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
export PYTHONUNBUFFERED=1
which python hmmsearch mmseqs
python -c "import genome_skeptic; print('genome_skeptic_ok')"
LOG="$ROOT/external_validation_agentic_d20/v5_prescreen.log"
python -u "$ROOT/scripts/run_cohort_d20_v5_prescreen.py" 2>&1 | tee -a "$LOG"
echo "PYTHON_EXIT:${PIPESTATUS[0]}" | tee -a "$LOG"
