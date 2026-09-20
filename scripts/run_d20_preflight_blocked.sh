#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
export PYTHONUNBUFFERED=1
# Prefer swap over OOM-kill. Infrastructure only; does not change the calculation.
sysctl -w vm.swappiness=100 >/dev/null 2>&1 || true
echo "MEMINFO"
grep -E 'MemTotal|MemAvailable|SwapTotal|SwapFree' /proc/meminfo
LOG="$ROOT/external_validation_agentic_d20/preflight_GCF_048282645.1_lacZ/preflight.log"
mkdir -p "$(dirname "$LOG")"
python -u "$ROOT/scripts/preflight_d20_blocked_case.py" 2>&1 | tee -a "$LOG"
echo "PYTHON_EXIT:${PIPESTATUS[0]}" | tee -a "$LOG"
