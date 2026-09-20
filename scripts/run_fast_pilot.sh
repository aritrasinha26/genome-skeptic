#!/usr/bin/env bash
# FAST PILOT - NOT FINAL BENCHMARK
# Separate from scripts/_wsl_pilot.sh. Does not overwrite production cases or config.
set -euo pipefail
export PYTHONUNBUFFERED=1
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
CFG="$ROOT/config/fast_pilot.yaml"
GS="micromamba run -n genome-skeptic-prod python -m genome_skeptic"
DEV_OUT="$ROOT/benchmarks/real_genomes_fast_pilot_dev"
HELD_OUT="$ROOT/benchmarks/real_genomes_fast_pilot_held"
DEV_EVAL="$ROOT/benchmarks/real_genomes_fast_pilot_dev_eval"
HELD_EVAL="$ROOT/benchmarks/real_genomes_fast_pilot_held_eval"
FREEZE="$ROOT/heldout_freeze_manifest_fast_pilot.json"
CACHE="$ROOT/benchmarks/real_genomes/hidden/genomes"

echo "============================================================"
echo "FAST PILOT - NOT FINAL BENCHMARK"
echo "Scientific thresholds, claim rules, falsification, and scoring are unchanged."
echo "This run is not the full production benchmark."
echo "============================================================"

micromamba run -n genome-skeptic-prod python - <<'PY'
from genome_skeptic.config import load_settings
from genome_skeptic.eval.catalog import genomes_for
from genome_skeptic.eval.pipeline import select_spades_resources
from pathlib import Path
settings = load_settings(Path("config/fast_pilot.yaml"))
mem, threads, info = select_spades_resources(settings)
dev = genomes_for("development", profile="fast_pilot")
held = genomes_for("held_out", profile="fast_pilot")
print("=== FAST_PILOT resource selection ===")
for k in ("mem_total_gb", "mem_available_gb", "selected_memory_gb", "selected_threads",
          "twelve_gb_available", "six_gb_safe", "used_preferred_t4_m8", "nproc", "note"):
    print(f"{k}: {info.get(k)}")
print(f"SPAdes: -t {threads} -m {mem} --only-assembler -k {settings.assembly.kmers}")
print("development genomes:", [f"{g.genome_id} ({g.species}, ~{g.approx_mb} Mb)" for g in dev])
print("held-out genomes:", [f"{g.genome_id} ({g.species}, ~{g.approx_mb} Mb)" for g in held])
print("clean coverage: 25x (25-30x band); low-coverage cases are not generated in this 3+3 set")
print()
print("=== expected runtime (before execution) ===")
print("Assumptions: --only-assembler, k=21,33,55, no FastQC, no ablations, assembly reused across 3 systems.")
print("Development (3 clean genomes): about 45-70 minutes")
print("  H. pylori 1.67 Mb: ~4-8 min SPAdes; E. coli 4.64 Mb: ~10-18 min; PAO1 6.26 Mb: ~15-25 min")
print("  plus fastp/QUAST/mapping/three systems ~4-8 min/case; wgsim generation ~3-6 min")
print("Held-out if development succeeds: about 45-75 minutes (P. putida similar to PAO1)")
print("Total: about 1.5-2.5 hours wall-clock")
print("This is a FAST_PILOT estimate, not a full-benchmark schedule.")
Path("benchmarks/fast_pilot_resource_selection.json").write_text(
    __import__("json").dumps({"memory_gb": mem, "threads": threads, **info}, indent=2)
)
PY

echo "== generate FAST_PILOT development cases =="
$GS generate-real-genomes \
  --out "$DEV_OUT" \
  --split development \
  --cache "$CACHE" \
  --config "$CFG" \
  --fast-pilot
ls "$DEV_OUT/agent_visible"

echo "== evaluate FAST_PILOT development (no ablations) =="
rm -rf "$DEV_EVAL"
$GS evaluate-real-genomes \
  --visible "$DEV_OUT/agent_visible" \
  --truth "$DEV_OUT/hidden/truth.yaml" \
  --out "$DEV_EVAL" \
  --split development \
  --no-ablations \
  --config "$CFG"

micromamba run -n genome-skeptic-prod python - <<'PY'
import json, sys
from pathlib import Path
p = Path("benchmarks/real_genomes_fast_pilot_dev_eval/realgenome_production_report.json")
report = json.loads(p.read_text())
prod = report.get("production") or {}
assembled = int(prod.get("assembled") or 0)
unavailable = int(prod.get("assembly_unavailable") or 0)
n = len(report.get("cases") or [])
print(f"development assembled={assembled} unavailable={unavailable} cases={n}")
print("banner:", report.get("banner"))
if assembled < n or unavailable:
    print("DEVELOPMENT_FAILED")
    sys.exit(2)
print("DEVELOPMENT_OK")
PY

echo "== freeze FAST_PILOT configuration =="
$GS freeze-heldout --out "$FREEZE" --config "$CFG"

echo "== generate FAST_PILOT held-out cases =="
$GS generate-real-genomes \
  --out "$HELD_OUT" \
  --split held_out \
  --cache "$CACHE" \
  --config "$CFG" \
  --fast-pilot
ls "$HELD_OUT/agent_visible"

echo "== evaluate FAST_PILOT held-out (no ablations) =="
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
held_p = root / "benchmarks/real_genomes_fast_pilot_held_eval/realgenome_production_report.json"
held = json.loads(held_p.read_text()) if held_p.exists() else None
out = root / "benchmarks/FAST_PILOT_REPORT.md"
write_fast_pilot_summary(out, dev, held=held)
print("wrote", out)
print("FAST PILOT - NOT FINAL BENCHMARK")
PY
echo "FAST_PILOT COMPLETE"
