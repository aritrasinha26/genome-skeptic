#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
PY="/home/aritr/micromamba/envs/genome-skeptic-prod/bin/python"
KEYFILE="/mnt/c/Users/aritr/AppData/Local/Temp/gs_poc_keys.env"
cd "$ROOT"
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="$ROOT/src:$ROOT/scripts:$ROOT/scripts/model_poc_v5:$ROOT/scripts/decision_authority_poc"
export PYTHONUNBUFFERED=1
if [ -f "$KEYFILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$KEYFILE"
  set +a
fi
if [ -n "${OPENAI_API_KEY:-}" ]; then echo "OPENAI=yes"; else echo "OPENAI=no"; fi
if [ -n "${TYPESAFE_API_KEY:-}" ]; then echo "TYPESAFE=yes"; else echo "TYPESAFE=no"; fi
which diamond tblastn hmmsearch >/dev/null
mkdir -p "$ROOT/role_swap_cross_task/_work"
exec "$PY" -u "$ROOT/scripts/run_role_swap_execution.py" --phase all 2>&1 | tee "$ROOT/role_swap_cross_task/_work/execution.log"
