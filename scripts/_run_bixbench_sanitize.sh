#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
export PYTHONUNBUFFERED=1
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
sed -i 's/\r$//' scripts/_bixbench_sanitize_metadata.py
micromamba run -n genome-skeptic-prod python scripts/_bixbench_sanitize_metadata.py
