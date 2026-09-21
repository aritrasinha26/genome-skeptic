#!/usr/bin/env bash
set -euo pipefail
REPO="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/home/aritr/micromamba/bin:/usr/bin:/bin:${PATH}"
export CONDA_PREFIX="/home/aritr/micromamba/envs/genome-skeptic-prod"
export PYTHONPATH="${REPO}/src"
cd "$REPO"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ)"
python - <<'PY'
from pathlib import Path
import hashlib
from genome_skeptic.manuscript.scientific_core import scientific_core_hashes
core = scientific_core_hashes()["scientific_core_hash"]
exp = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"
print("CORE", core, "OK" if core==exp else "MISMATCH")
if core != exp:
    raise SystemExit(1)
p = Path("manuscript_benchmark/ENVIRONMENT/RPOB_COMPARATOR_PROVENANCE.json")
print("RPOB_PROVENANCE_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
PY
echo "OLLAMA_TAGS"
curl -s http://172.17.32.1:11434/api/tags | python -c 'import sys,json; d=json.load(sys.stdin); [print(m.get("name"), m.get("digest")) for m in d.get("models",[])]' || echo "ollama unreachable"
echo "RUN POSITION 1"
python -u "${REPO}/scripts/run_m60_position.py" --positions 1
echo "END $(date -u +%Y-%m-%dT%H:%M:%SZ)"
