#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/home/aritr/micromamba/bin:/usr/bin:/bin:${PATH}"
REPO="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$REPO"
export PYTHONPATH="$REPO/src"
mkdir -p /home/aritr/m60_work
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ)"
python scripts/m60_env_preflight.py
python -u scripts/select_m60_cohort.py
echo "END $(date -u +%Y-%m-%dT%H:%M:%SZ)"
