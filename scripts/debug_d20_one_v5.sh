#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
echo "MEM_BEFORE"
free -h
which tblastn blastn || true
ls -la /home/aritr/d20_v5_work/runs/GCF_048282645.1/lacZ_beta_galactosidase/genome_skeptic || true
python - <<'PY'
import sys, time, traceback
from pathlib import Path
sys.path.insert(0, "/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/src")
from genome_skeptic.config import load_settings
from genome_skeptic.eval.evaluate_real import _run_system
print("start_one", flush=True)
settings = load_settings("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/config/qwen_external_v5.yaml")
assembly = Path("/home/aritr/d20_v5_work/fasta/GCF_048282645.1.fna")
target = Path("/home/aritr/d20_v5_work/runs/GCF_048282645.1/lacZ_beta_galactosidase/target.fa")
out = Path("/home/aritr/d20_v5_work/debug_one/genome_skeptic")
out.mkdir(parents=True, exist_ok=True)
refs = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/external_validation_agentic_d20/inputs/references.yaml")
t0 = time.perf_counter()
try:
    payload = _run_system("genome_skeptic", assembly, target, out, settings, refs, "Pimelobacter", None, None)
    print("OK seconds", payload.get("seconds"), time.perf_counter()-t0, flush=True)
except Exception:
    traceback.print_exc()
    raise
PY
echo "MEM_AFTER"
free -h
