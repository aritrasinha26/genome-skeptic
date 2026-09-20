#!/usr/bin/env bash
set -eu
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
cd /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
export PYTHONPATH=src
export PYTHONUNBUFFERED=1
python -u scripts/run_orthology_v3.py --reuse-held
echo RUN_FINISHED
