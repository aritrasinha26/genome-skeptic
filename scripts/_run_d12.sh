#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
export PYTHONUNBUFFERED=1
export PYTHONFAULTHANDLER=1
mkdir -p /home/aritr/d12_work/tmp
export TMPDIR=/home/aritr/d12_work/tmp
export TMP=/home/aritr/d12_work/tmp
export TEMP=/home/aritr/d12_work/tmp
STEP="${1:-preflight}"
echo "PYTHON=$(command -v python) STEP=$STEP"
python -c "import sys; print(sys.executable); print(sys.version)"
case "$STEP" in
  preflight)
    python -u "$ROOT/scripts/_d12_preflight.py"
    ;;
  pool)
    python -u "$ROOT/scripts/select_and_download_d12.py"
    ;;
  prescreen)
    python -u "$ROOT/scripts/run_d12_v5_prescreen.py"
    ;;
  select)
    python -u "$ROOT/scripts/lock_d12_challenge_selection.py"
    ;;
  stage1)
    python -u "$ROOT/scripts/run_d12_three_systems.py" --stage 1
    ;;
  stage2)
    python -u "$ROOT/scripts/run_d12_three_systems.py" --stage 2
    ;;
  stage3)
    python -u "$ROOT/scripts/run_d12_three_systems.py" --stage 3
    ;;
  *)
    echo "unknown step $STEP" >&2
    exit 2
    ;;
esac
