#!/bin/bash
# Preserve in-flight resource-rerun logs/provenance, then SIGTERM SPAdes/evaluate.
set -euo pipefail
ROOT="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
EVAL="$ROOT/benchmarks/real_genomes_dev_eval"
STAMP=$(date +%Y%m%dT%H%M%S)
PRES="$EVAL/preserved/resource_rerun_stopped_${STAMP}"
mkdir -p "$PRES"

python3 - "$EVAL" "$PRES" <<'PY'
import json, shutil, sys, time
from pathlib import Path

root = Path(sys.argv[1])
pres = Path(sys.argv[2])
meta = {
    "stopped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "reason": "FAST_PILOT requested; preserve resource-rerun logs then SIGTERM",
    "label": "production resource rerun (not FAST_PILOT)",
    "cases": {},
}
relatives = [
    "spades_resource_provenance.json",
    "production/spades/spades.log",
    "production/spades/params.txt",
    "production/spades/run_spades.yaml",
    "production/spades/run_spades.sh",
    "production/spades/input_dataset.yaml",
    "production/spades/spades.stdout.log",
    "production/spades/spades.stderr.log",
    "production/fastp/fastp.json",
    "production/fastp/fastp.stdout.log",
    "production/fastp/fastp.stderr.log",
]
for case in ("dev_02", "dev_06"):
    src = root / case
    dest = pres / case
    info = {"exists": src.exists(), "copied": []}
    meta["cases"][case] = info
    if not src.exists():
        continue
    dest.mkdir(parents=True, exist_ok=True)
    for rel in relatives:
        p = src / rel
        if p.is_file():
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
            info["copied"].append(rel)
    prod = src / "production"
    if prod.is_dir():
        for p in prod.glob("*.json"):
            shutil.copy2(p, dest / p.name)
            info["copied"].append(p.name)
(pres / "stop_preservation.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta, indent=2))
PY

for f in resource_rerun_selection.json production_stack.json environment_manifest.json \
         realgenome_production_report.json realgenome_production_report.md \
         real_genome_evaluation.json real_genome_report.md; do
  if [ -f "$EVAL/$f" ]; then
    cp -a "$EVAL/$f" "$PRES/$f"
    echo "copied $f"
  fi
done

echo "=== log tails ==="
for c in dev_02 dev_06; do
  lg="$EVAL/$c/production/spades/spades.log"
  echo "---- $c ----"
  if [ -f "$lg" ]; then
    wc -l "$lg"
    tail -n 15 "$lg"
  else
    echo "spades.log missing"
    ls -la "$EVAL/$c" 2>/dev/null || true
    ls -la "$EVAL/$c/production/spades" 2>/dev/null || true
  fi
done

echo "PRESERVE_DIR=$PRES"
echo "PRESERVE_OK"
