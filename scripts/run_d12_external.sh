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
mkdir -p /home/aritr/d12_work
echo "PYTHON=$(command -v python)"
python -c "import sys; print(sys.executable); print(sys.version)"
STEP="${1:-}"
if [[ -z "$STEP" ]]; then
  echo "usage: $0 pool|prescreen|select|stage1|stage2|stage3" >&2
  exit 2
fi
case "$STEP" in
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
