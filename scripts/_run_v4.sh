#!/usr/bin/env bash
set -eu
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
cd /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
export PYTHONPATH=src
export PYTHONUNBUFFERED=1
mkdir -p benchmarks/v4
python -m pytest tests/test_v4_locus.py tests/test_family_orthology.py tests/test_completeness.py -q --tb=short
python -u scripts/run_v4.py 2>&1 | tee -a benchmarks/v4/run.log
echo V4_FINISHED
