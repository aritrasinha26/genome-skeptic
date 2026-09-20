#!/usr/bin/env bash
# Inspect the production stack. Does not treat an executable as operational
# until a smoke test has succeeded.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${1:-$ROOT/production_stack.json}"
if command -v genome-skeptic >/dev/null; then
  GS=genome-skeptic
else
  export PYTHONPATH="$ROOT/src"
  GS="python -m genome_skeptic.cli"
fi
eval $GS doctor --smoke --out "$OUT"
python - "$OUT" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text())
missing = [t["name"] for t in data.get("tools", []) if not t.get("available")]
not_op = [t["name"] for t in data.get("tools", []) if t.get("available") and not t.get("operational")]
print(f"available={sum(1 for t in data.get('tools', []) if t.get('available'))}")
print(f"operational={sum(1 for t in data.get('tools', []) if t.get('operational'))}")
if missing:
    print("missing:", ", ".join(missing))
if not_op:
    print("installed-but-not-operational:", ", ".join(not_op))
PY
