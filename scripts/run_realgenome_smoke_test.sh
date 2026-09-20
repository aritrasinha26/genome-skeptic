#!/usr/bin/env bash
# Tiny valid-input smoke tests for every installed production program.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
OUT="${1:-$ROOT/production_smoke.json}"
python - "$OUT" <<'PY'
import json, sys
from pathlib import Path
from genome_skeptic.eval.stack import run_all_smoke_tests, write_production_stack
out = Path(sys.argv[1])
smokes = run_all_smoke_tests(out.parent / "smoke_work")
manifest = write_production_stack(out.parent / "production_stack.json", smoke=smokes)
out.write_text(json.dumps({"smoke": smokes, "stack": manifest}, indent=2, default=str))
failed = [k for k, v in smokes.items() if v.get("ran") and not v.get("ok")]
print(json.dumps({k: {"ok": v.get("ok"), "ran": v.get("ran"), "error": v.get("error")} for k, v in smokes.items()}, indent=2))
if failed:
    print("SMOKE FAILURES:", ", ".join(failed))
    sys.exit(1)
print("all executed smoke tests passed")
PY
