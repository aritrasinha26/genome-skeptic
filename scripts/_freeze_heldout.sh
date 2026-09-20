#!/bin/bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
micromamba run -n genome-skeptic-prod python -m genome_skeptic freeze-heldout --out "$ROOT/heldout_freeze_manifest.json"
