#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
PY="/home/aritr/micromamba/envs/genome-skeptic-prod/bin/python"
cd "$ROOT"
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="$ROOT/src:$ROOT/scripts:$ROOT/scripts/model_poc_v5:$ROOT/scripts/decision_authority_poc"
export PYTHONUNBUFFERED=1
export MPLBACKEND=Agg
mkdir -p "$ROOT/role_swap_cross_task/_work"
exec "$PY" -u "$ROOT/scripts/score_role_swap_unblind.py" 2>&1 | tee "$ROOT/role_swap_cross_task/_work/unblind.log"
