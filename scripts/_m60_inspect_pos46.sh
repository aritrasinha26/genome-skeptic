#!/usr/bin/env bash
set -euo pipefail
BASE="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/RUNS/position_46/GCF_053612185.1/tetA_tetracycline_efflux"
for s in CONVENTIONAL AMRFINDERPLUS GS_DETERMINISTIC_V4_1 GS_AGENTIC_V4_1 GS_EXHAUSTIVE_V4_1; do
  echo "=== $s ==="
  if [ -d "$BASE/$s" ]; then
    ls -la "$BASE/$s" | sed -n '1,40p'
  else
    echo MISSING_DIR
  fi
done
python3 - <<'PY'
from pathlib import Path
import json, hashlib
base = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/RUNS/position_46/GCF_053612185.1/tetA_tetracycline_efflux")
for s in ["CONVENTIONAL","AMRFINDERPLUS","GS_DETERMINISTIC_V4_1","GS_AGENTIC_V4_1"]:
    p = base/s/"case_locked.json"
    side = Path(str(p)+".sha256.json")
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    expected = json.loads(side.read_text())["sha256"] if side.exists() else None
    print(s, "bytes", p.stat().st_size, "match", actual==expected, actual)
PY
