#!/usr/bin/env bash
set -euo pipefail
E=/home/aritr/m60_work/truth_evidence/position_01_GCF_049943055.1_rpoB_RNAP_beta
echo "=== orfs ==="
python3 - <<'PY'
import json
from pathlib import Path
p=Path("/home/aritr/m60_work/truth_evidence/position_01_GCF_049943055.1_rpoB_RNAP_beta/orfs.json")
print(p.exists(), p.stat().st_size if p.exists() else None)
if p.exists():
    d=json.loads(p.read_text())
    for o in d:
        print({k:o[k] for k in o if k!='aa'})
PY
echo "=== hmm logs ==="
ls -la "$E"/orf_00 "$E"/orf_01 2>/dev/null | head
echo ---
ls "$E"/orf_00/hmm_target 2>/dev/null
cat "$E"/orf_00/hmm_target/hmmsearch.stderr.log 2>/dev/null | tail -20
echo === candidate lens ===
wc -c "$E"/orf_*/candidate.faa 2>/dev/null | head
echo === hmm files ===
ls -la /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/TRUTH_M60/SOURCE_FREEZE/hmm | head
