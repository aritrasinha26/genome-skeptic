#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
python "$ROOT/scripts/run_cohort_d20_v5_prescreen.py"
python "$ROOT/scripts/lock_cohort_d20_final.py"
