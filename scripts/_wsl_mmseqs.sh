#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
export PATH="$HOME/micromamba/bin:$PATH"
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
micromamba run -n genome-skeptic-prod python - <<'PY'
from pathlib import Path
from genome_skeptic.eval.stack import _tiny_fasta
from genome_skeptic.tools.base import run_command
work = Path("/tmp/gs_mmseqs_smoke")
work.mkdir(exist_ok=True)
fa = _tiny_fasta(work / "tiny.fa")
out = work / "mmseqs"
out.mkdir(exist_ok=True)
res = run_command("mmseqs", "smoke", [
    "mmseqs", "easy-search", str(fa), str(fa), str(out / "hits.m8"), str(out / "tmp"),
    "--threads", "1", "--search-type", "3", "--split-memory-limit", "512M", "-s", "1",
], out)
hits = out / "hits.m8"
print("ok", res.ok, "err", res.error, "hits", hits.exists(), "size", hits.stat().st_size if hits.exists() else 0)
errp = out / "mmseqs.stderr.log"
if errp.exists():
    print(errp.read_text()[-1200:])
PY
