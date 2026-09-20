#!/bin/bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
EVAL="$ROOT/benchmarks/real_genomes_dev_eval"
PRES="$EVAL/preserved/dev_06_rerun_m2_oom"
mkdir -p "$PRES"
if [ -d "$EVAL/dev_06/production/spades" ]; then
  cp -a "$EVAL/dev_06/production/spades/spades.log" "$PRES/spades.log" 2>/dev/null || true
  cp -a "$EVAL/dev_06/production/spades/params.txt" "$PRES/params.txt" 2>/dev/null || true
fi
rm -rf "$EVAL/dev_06/production/spades"
echo "=== meminfo before isolated dev_06 rerun ==="
grep -E 'MemTotal|MemAvailable|SwapTotal' /proc/meminfo
micromamba run -n genome-skeptic-prod python - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "src")
from genome_skeptic.config import Settings
from genome_skeptic.eval.pipeline import select_spades_resources
mem, threads, info = select_spades_resources(Settings())
print({"memory_gb": mem, "threads": threads, **info})
Path("benchmarks/real_genomes_dev_eval/resource_rerun_selection.json").write_text(json.dumps({"memory_gb": mem, "threads": threads, **info}, indent=2))
PY
echo "=== isolated dev_06 rerun ==="
micromamba run -n genome-skeptic-prod python -m genome_skeptic evaluate-real-genomes \
  --visible "$ROOT/benchmarks/real_genomes_dev/agent_visible" \
  --truth "$ROOT/benchmarks/real_genomes_dev/hidden/truth.yaml" \
  --out "$EVAL" \
  --split development \
  --no-ablations \
  --only-cases dev_06 \
  --merge-existing
echo "=== isolated dev_06 rerun finished ==="
