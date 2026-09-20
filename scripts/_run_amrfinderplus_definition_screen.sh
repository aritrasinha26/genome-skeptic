#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
export PYTHONUNBUFFERED=1
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
sed -i 's/\r$//' scripts/_amrfinderplus_definition_screen.py
micromamba run -n genome-skeptic-prod python scripts/_amrfinderplus_definition_screen.py
