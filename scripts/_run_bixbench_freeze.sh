#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
export PYTHONUNBUFFERED=1
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
sed -i 's/\r$//' scripts/_freeze_bixbench_v5_selection.py
micromamba run -n genome-skeptic-prod python scripts/_freeze_bixbench_v5_selection.py
