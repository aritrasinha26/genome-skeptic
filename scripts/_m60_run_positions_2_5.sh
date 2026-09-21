#!/usr/bin/env bash
set -euo pipefail
REPO="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/home/aritr/micromamba/bin:/usr/bin:/bin:${PATH}"
export CONDA_PREFIX="/home/aritr/micromamba/envs/genome-skeptic-prod"
export PYTHONPATH="${REPO}/src"
cd "$REPO"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ)"
# Restore freeze LF bytes if Windows CRLF dirtied hash-only files.
for f in \
  data/orthology_references/lacZ_beta_galactosidase/index.yaml \
  src/genome_skeptic/validators/ortholog_references.py \
  src/genome_skeptic/validators/locus_stages_v4_1_dev.py
do
  git show "HEAD:${f}" > "${f}"
done
python - <<'PY'
import hashlib, json
from pathlib import Path
from genome_skeptic.manuscript.scientific_core import scientific_core_hashes

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def sha_lf(p):
    return hashlib.sha256(Path(p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()

core = scientific_core_hashes()["scientific_core_hash"]
assert core == "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0", core
m60 = sha("manuscript_benchmark/M60_COHORT_MANIFEST.json")
assert m60 == "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655", m60
prot = sha_lf("manuscript_benchmark/M60_PROTOCOL_V1_1.md")
assert prot == "73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660", prot
amr = sha("manuscript_benchmark/ENVIRONMENT/AMRFINDER_DATABASE_FREEZE.json")
assert amr == "d7ae98063c3b7795fa443f90f51a267e5b28002e1e5d59f364f403dde8a188be", amr
freeze = json.loads(Path("manuscript_benchmark/ENVIRONMENT/AMRFINDER_DATABASE_FREEZE.json").read_text())
assert freeze["database_version"] == "2026-08-07.1"
assert freeze["amrfinder_executable_version"] == "4.2.7"
print("FREEZE_OK")
print("CORE", core)
print("M60", m60)
print("AMR_DB", freeze["database_version"])
PY
echo "RUN POSITIONS 2,3,4,5"
python -u "${REPO}/scripts/run_m60_position.py" --positions 2,3,4,5
echo "END $(date -u +%Y-%m-%dT%H:%M:%SZ)"
