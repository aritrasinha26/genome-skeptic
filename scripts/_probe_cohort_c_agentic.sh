#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
cd /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
export PYTHONPATH=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/src
export PYTHONUNBUFFERED=1
python -c 'import genome_skeptic,sys; print("PYTHON", sys.executable); print("GS", genome_skeptic.__file__)'
curl -sS --max-time 15 http://172.17.32.1:11434/api/show -d '{"name":"qwen3:4b"}' | python -c 'import sys,json; d=json.load(sys.stdin); print("DIGEST", d.get("digest")); print("DETAILS", d.get("details"))'
