#!/usr/bin/env bash
set -euo pipefail
REPO="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/home/aritr/micromamba/bin:/usr/bin:/bin:${PATH}"
export CONDA_PREFIX="/home/aritr/micromamba/envs/genome-skeptic-prod"
export PYTHONPATH="${REPO}/src"
cd "$REPO"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ)"
for f in \
  data/orthology_references/lacZ_beta_galactosidase/index.yaml \
  src/genome_skeptic/validators/ortholog_references.py \
  src/genome_skeptic/validators/locus_stages_v4_1_dev.py
do
  git show "HEAD:${f}" > "${f}"
done
python - <<'PY'
import hashlib
from pathlib import Path
from genome_skeptic.manuscript.scientific_core import scientific_core_hashes
assert scientific_core_hashes()["scientific_core_hash"] == "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"
assert hashlib.sha256(Path("manuscript_benchmark/M60_COHORT_MANIFEST.json").read_bytes()).hexdigest() == "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655"
assert hashlib.sha256(Path("manuscript_benchmark/M60_PROTOCOL_V1_1.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest() == "73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660"
assert hashlib.sha256(Path("manuscript_benchmark/M60_POSITIONS_1_5_LOCK.json").read_bytes()).hexdigest() == "b62e71c91787b93d36d0fb3865486a7de5d812998e048d36ec1deb84795b08b3"
assert hashlib.sha256(Path("manuscript_benchmark/ENVIRONMENT/AMRFINDER_DATABASE_FREEZE.json").read_bytes()).hexdigest() == "d7ae98063c3b7795fa443f90f51a267e5b28002e1e5d59f364f403dde8a188be"
print("FREEZE_AND_1_5_LOCK_OK")
PY
echo "RUN POSITIONS 6-60 RESUME"
python -u "${REPO}/scripts/run_m60_position.py" --from-pos 6 --to-pos 60 --resume
echo "FINALIZE"
python -u "${REPO}/scripts/finalize_m60_predictions.py"
echo "END $(date -u +%Y-%m-%dT%H:%M:%SZ)"
