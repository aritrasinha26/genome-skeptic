#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
export PYTHONUNBUFFERED=1
echo "PYTHON=$(command -v python)"
python -c "import sys; print(sys.executable); print(sys.version)"
command -v hmmsearch || echo "hmmsearch missing"
command -v hmmbuild || echo "hmmbuild missing"
command -v mmseqs || echo "mmseqs missing"
command -v diamond || echo "diamond missing"
command -v blastp || echo "blastp missing"
python -u "$ROOT/scripts/run_v3_production_readiness_gate.py" "$@"
