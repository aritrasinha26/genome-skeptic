#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
export PYTHONUNBUFFERED=1
BASE=/mnt/c/Users/aritr/Downloads
ROOT="$BASE/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
micromamba run -n genome-skeptic-prod python -u scripts/run_semantics_v2.py
echo EXIT:$?
