#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
export PYTHONUNBUFFERED=1
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
echo "=== genome-skeptic model-test (schema-constrained) ==="
micromamba run -n genome-skeptic-prod python -m genome_skeptic model-test --config config/qwen_external_v5.yaml
echo EXIT:$?
