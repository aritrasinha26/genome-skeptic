#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
micromamba run -n genome-skeptic-prod python -m genome_skeptic doctor --smoke --out "$ROOT/production_stack.json"
micromamba run -n genome-skeptic-prod python - <<'PY'
from pathlib import Path
from genome_skeptic.eval.stack import run_all_smoke_tests
import json
smokes = run_all_smoke_tests(Path("smoke_work"))
Path("production_smoke.json").write_text(json.dumps(smokes, indent=2))
failed = [k for k,v in smokes.items() if v.get("ran") and not v.get("ok")]
print(json.dumps({k: {"ok": v.get("ok"), "ran": v.get("ran"), "error": v.get("error")} for k,v in smokes.items()}, indent=2))
raise SystemExit(1 if failed else 0)
PY
