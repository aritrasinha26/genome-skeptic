#!/bin/bash
# FAST PILOT held-out after successful development. Does not overwrite production configs.
set -euo pipefail
export PYTHONUNBUFFERED=1
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
CFG="$ROOT/config/fast_pilot.yaml"
GS="micromamba run -n genome-skeptic-prod python -m genome_skeptic"
HELD_OUT="$ROOT/benchmarks/real_genomes_fast_pilot_held"
HELD_EVAL="$ROOT/benchmarks/real_genomes_fast_pilot_held_eval"
FREEZE="$ROOT/heldout_freeze_manifest_fast_pilot.json"
CACHE="$ROOT/benchmarks/real_genomes/hidden/genomes"

echo "FAST PILOT - NOT FINAL BENCHMARK: freeze then held-out"
$GS freeze-heldout --out "$FREEZE" --config "$CFG"

echo "== generate FAST_PILOT held-out cases =="
$GS generate-real-genomes \
  --out "$HELD_OUT" \
  --split held_out \
  --cache "$CACHE" \
  --config "$CFG" \
  --fast-pilot
ls "$HELD_OUT/agent_visible"

echo "== evaluate FAST_PILOT held-out =="
rm -rf "$HELD_EVAL"
$GS evaluate-real-genomes \
  --visible "$HELD_OUT/agent_visible" \
  --truth "$HELD_OUT/hidden/truth.yaml" \
  --out "$HELD_EVAL" \
  --split held_out \
  --no-ablations \
  --config "$CFG"

micromamba run -n genome-skeptic-prod python - <<'PY'
import json
from pathlib import Path
from genome_skeptic.eval.evaluate_real import write_fast_pilot_summary
root = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
dev = json.loads((root / "benchmarks/real_genomes_fast_pilot_dev_eval/realgenome_production_report.json").read_text())
held = json.loads((root / "benchmarks/real_genomes_fast_pilot_held_eval/realgenome_production_report.json").read_text())
out = root / "benchmarks/FAST_PILOT_REPORT.md"
write_fast_pilot_summary(out, dev, held=held)
print("wrote", out)
print("FAST PILOT - NOT FINAL BENCHMARK")
PY
echo "FAST_PILOT_HELDOUT_COMPLETE"
