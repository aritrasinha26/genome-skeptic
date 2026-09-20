#!/bin/bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
echo "=== freeze only; do not start held-out ==="
pgrep -af '_wsl_continue|evaluate-real-genomes' || echo 'no waiter/eval'
micromamba run -n genome-skeptic-prod python -m genome_skeptic freeze-heldout --out "$ROOT/heldout_freeze_manifest.json"
echo "=== freeze written ==="
ls -l "$ROOT/heldout_freeze_manifest.json"
python3 - <<'PY'
import json
from pathlib import Path
p = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/heldout_freeze_manifest.json")
d = json.loads(p.read_text())
print("sha256", d.get("sha256"))
print("fast_pilot", d.get("fast_pilot"))
print("note", (d.get("note") or "")[:200])
print("assembly", d.get("assembly"))
print("created_at", d.get("created_at"))
PY
echo "=== confirm no held-out eval started ==="
pgrep -af 'evaluate-real-genomes|generate-real-genomes' || echo 'NONE'
ls /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_held_eval 2>/dev/null | head || echo 'no held_eval dir (expected)'
