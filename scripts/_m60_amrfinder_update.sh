#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/home/aritr/micromamba/bin:/usr/bin:/bin:${PATH}"
export CONDA_PREFIX="/home/aritr/micromamba/envs/genome-skeptic-prod"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "AMRFINDER=$(command -v amrfinder)"
amrfinder --version
echo "COMMAND: amrfinder -u"
amrfinder -u
echo "END $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--- amrfinder -l ---"
amrfinder -l || true
echo "--- db dir ---"
ls -la "${CONDA_PREFIX}/share/amrfinderplus/data/" || true
readlink -f "${CONDA_PREFIX}/share/amrfinderplus/data/latest" || true
