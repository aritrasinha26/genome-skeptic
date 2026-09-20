#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
FastTree 2>&1 | head -n 1 || true
diamond version 2>&1 | head -n 1 || true
mmseqs version 2>&1 | head -n 1 || true
minimap2 --version 2>&1 | head -n 1 || true
samtools --version 2>&1 | head -n 1 || true
