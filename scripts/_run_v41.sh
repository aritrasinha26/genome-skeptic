#!/usr/bin/env bash
set -eu
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
cd /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
export PYTHONPATH=src
export PYTHONUNBUFFERED=1
python -m pytest tests/test_v41.py tests/test_v4_locus.py -q --tb=short
python -u scripts/run_v41.py
echo V41_FINISHED
