#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
export PYTHONUNBUFFERED=1
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
echo "blastn=$(command -v blastn || true)"
echo "tblastn=$(command -v tblastn || true)"
echo "minimap2=$(command -v minimap2 || true)"
micromamba run -n genome-skeptic-prod python -u scripts/_fast_pilot_target_trace.py
echo EXIT:$?
