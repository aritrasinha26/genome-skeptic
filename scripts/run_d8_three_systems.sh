#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
export PYTHONUNBUFFERED=1
grep -E 'MemTotal|SwapTotal' /proc/meminfo
export PYTHONFAULTHANDLER=1
export PYTHONUNBUFFERED=1
mkdir -p /home/aritr/d8_work
python -u "$ROOT/scripts/run_d8_three_systems.py" 2>&1 | tee -a /home/aritr/d8_work/runner.log
