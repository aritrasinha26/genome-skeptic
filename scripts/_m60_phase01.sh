#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/home/aritr/micromamba/bin:/usr/bin:/bin:${PATH}"
REPO="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$REPO"
export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"
python -V
python scripts/m60_env_preflight.py
python - <<'PY'
from pathlib import Path
import hashlib
p = Path("manuscript_benchmark/M60_PROTOCOL_V1_1.md")
print("PROTOCOL_V1_1_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
p2 = Path("manuscript_benchmark/M60_PROTOCOL.md")
print("PROTOCOL_ORIGINAL_SHA256", hashlib.sha256(p2.read_bytes()).hexdigest())
PY
python scripts/select_m60_cohort.py
