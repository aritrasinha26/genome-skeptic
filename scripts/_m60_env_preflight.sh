#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/home/aritr/micromamba/bin:${PATH}"
echo "OS=$(uname -a)"
echo "PYTHON=$(python --version 2>&1)"
echo "PYTHON_PATH=$(command -v python)"
echo "BLASTN_PATH=$(command -v blastn)"
echo "BLASTN_VERSION=$(blastn -version 2>&1 | head -1)"
echo "HMMSEARCH_PATH=$(command -v hmmsearch)"
echo "HMMSEARCH_VERSION=$(hmmsearch -h 2>&1 | head -2 | tr '\n' ' ')"
echo "MMSEQS_PATH=$(command -v mmseqs)"
echo "MMSEQS_VERSION=$(mmseqs version 2>&1 | head -1)"
echo "DIAMOND_PATH=$(command -v diamond)"
echo "DIAMOND_VERSION=$(diamond version 2>&1 | head -1)"
echo "AMRFINDER_PATH=$(command -v amrfinder)"
echo "AMRFINDER_VERSION=$(amrfinder --version 2>&1 | head -8 | tr '\n' ' | ')"
echo "EMAPPER_PATH=$(command -v emapper.py || true)"
if command -v emapper.py >/dev/null 2>&1; then
  echo "EMAPPER_VERSION=$(emapper.py --version 2>&1 | head -5 | tr '\n' ' | ')"
fi
echo "NPROC=$(nproc)"
echo "---CPU---"
lscpu | sed -n '1,20p'
echo "---MEM---"
free -h
echo "---SWAP---"
swapon --show || true
echo "---PIP_FREEZE---"
python -m pip freeze
echo "---AMRFINDER_DB---"
amrfinder -l 2>/dev/null | head -30 || true
