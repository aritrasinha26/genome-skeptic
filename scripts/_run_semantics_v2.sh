#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
export PYTHONUNBUFFERED=1
BASE=/mnt/c/Users/aritr/Downloads
ROOT="$BASE/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
echo "blastn=$(command -v blastn || true)"
echo "tblastn=$(command -v tblastn || true)"
micromamba run -n genome-skeptic-prod python -m pytest tests/test_locate_target.py tests/test_completeness.py tests/test_calibration.py tests/test_eval.py tests/test_fast_pilot.py tests/test_gene_search.py -q --tb=short
micromamba run -n genome-skeptic-prod python -u scripts/run_semantics_v2.py
echo EXIT:$?
