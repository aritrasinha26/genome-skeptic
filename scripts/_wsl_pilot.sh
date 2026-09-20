#!/usr/bin/env bash
# Development then held-out genuine-genome production pilot (WSL micromamba).
# Doctor/smoke is assumed to have already been run in this session.
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
GS="micromamba run -n genome-skeptic-prod python -m genome_skeptic"

echo "== generate development cases (wgsim required; wipes leftover visible cases) =="
$GS generate-real-genomes --out "$ROOT/benchmarks/real_genomes_dev" --split development --cache "$ROOT/benchmarks/real_genomes/hidden/genomes"
rm -rf "$ROOT/benchmarks/real_genomes_dev_eval"
ls "$ROOT/benchmarks/real_genomes_dev/agent_visible"

echo "== evaluate development (no ablations) =="
$GS evaluate-real-genomes \
  --visible "$ROOT/benchmarks/real_genomes_dev/agent_visible" \
  --truth "$ROOT/benchmarks/real_genomes_dev/hidden/truth.yaml" \
  --out "$ROOT/benchmarks/real_genomes_dev_eval" \
  --split development \
  --no-ablations

echo "== freeze held-out configuration =="
$GS freeze-heldout --out "$ROOT/heldout_freeze_manifest.json"

echo "== generate held-out cases =="
$GS generate-real-genomes --out "$ROOT/benchmarks/real_genomes_held" --split held_out --cache "$ROOT/benchmarks/real_genomes/hidden/genomes"
rm -rf "$ROOT/benchmarks/real_genomes_held_eval"
ls "$ROOT/benchmarks/real_genomes_held/agent_visible"

echo "== evaluate held-out once =="
$GS evaluate-real-genomes \
  --visible "$ROOT/benchmarks/real_genomes_held/agent_visible" \
  --truth "$ROOT/benchmarks/real_genomes_held/hidden/truth.yaml" \
  --out "$ROOT/benchmarks/real_genomes_held_eval" \
  --split held_out \
  --no-ablations

micromamba run -n genome-skeptic-prod python - <<'PY'
import json, shutil
from pathlib import Path
from genome_skeptic.eval.evaluate_real import combine_production_reports, write_combined_production_report
root = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
dev_p = root / "benchmarks/real_genomes_dev_eval/realgenome_production_report.json"
held_p = root / "benchmarks/real_genomes_held_eval/realgenome_production_report.json"
dev = json.loads(dev_p.read_text()) if dev_p.exists() else None
held = json.loads(held_p.read_text()) if held_p.exists() else None
freeze = json.loads((root / "heldout_freeze_manifest.json").read_text()) if (root / "heldout_freeze_manifest.json").exists() else None
stack = json.loads((root / "production_stack.json").read_text()) if (root / "production_stack.json").exists() else None
combined = combine_production_reports(dev, held)
write_combined_production_report(root / "realgenome_production_report.md", combined, freeze=freeze, stack=stack)
if (root / "production_stack.json").exists() and (root / "benchmarks/real_genomes_held_eval").exists():
    shutil.copy2(root / "production_stack.json", root / "benchmarks/real_genomes_held_eval/production_stack.json")
print("wrote combined realgenome_production_report.md")
PY
echo "PILOT COMPLETE"
