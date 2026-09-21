#!/usr/bin/env bash
set -euo pipefail
REPO="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$REPO"
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/home/aritr/micromamba/bin:/usr/bin:/bin:${PATH}"
export PYTHONPATH="${REPO}/src"
export CONDA_PREFIX="/home/aritr/micromamba/envs/genome-skeptic-prod"

# Restore freeze-commit LF bytes for files whose working-tree CRLF changed hashes only.
# This does not change scientific content; it restores the frozen byte images.
for f in \
  data/orthology_references/lacZ_beta_galactosidase/index.yaml \
  src/genome_skeptic/validators/ortholog_references.py \
  src/genome_skeptic/validators/locus_stages_v4_1_dev.py
do
  git show "HEAD:${f}" > "${f}"
  echo "restored ${f}"
done

python - <<'PY'
import hashlib
from pathlib import Path
from genome_skeptic.manuscript.scientific_core import scientific_core_hashes
h = scientific_core_hashes()
exp = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"
print("scientific_core_hash", h["scientific_core_hash"])
print("scientific_core_ok", h["scientific_core_hash"] == exp)
print("reference_assets_hash", h["reference_assets_hash"])
print("validator_hash", h["validator_hash"])
files = {
    "manuscript_benchmark/GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json": "97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b",
    "manuscript_benchmark/M60_PROTOCOL_V1_1.md": "73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660",
    "manuscript_benchmark/M60_COHORT_MANIFEST.json": "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655",
    "manuscript_benchmark/M60_COHORT_MANIFEST.csv": "8756823e9ec214f2c14bbeb1a8e916f312db4acd6c8d2d7d3b1d78601d199d02",
    "manuscript_benchmark/M60_SELECTION_AUDIT.md": "a09283e15cc00b6e2dc366b5f3f8661c7ff617abc33517b052991e160aee1573",
}
for rel, exp_h in files.items():
    b = Path(rel).read_bytes()
    raw = hashlib.sha256(b).hexdigest()
    lf = hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest()
    print(rel, "raw_ok" if raw == exp_h else "raw_no", "lf_ok" if lf == exp_h else "lf_no")
PY
