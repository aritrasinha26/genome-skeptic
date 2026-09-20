#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
echo "PYTHON=$(command -v python)"
python --version
for t in hmmsearch hmmbuild blastp blastn FastTree diamond mmseqs minimap2 samtools python; do
  if command -v "$t" >/dev/null 2>&1; then
    echo "PATH_$t=$(command -v $t)"
  else
    echo "PATH_$t=MISSING"
  fi
done
hmmsearch -h 2>&1 | head -n 3 || true
hmmbuild -h 2>&1 | head -n 3 || true
blastp -version 2>&1 | head -n 2 || true
blastn -version 2>&1 | head -n 2 || true
python -c "import genome_skeptic,sys; print('GS', genome_skeptic.__file__); print(sys.version)"
curl -sS --max-time 8 http://172.17.32.1:11434/api/version
echo
curl -sS --max-time 15 http://172.17.32.1:11434/api/show -d '{"name":"qwen3:4b"}' | python -c "import sys,json; d=json.load(sys.stdin); print('MODEL', d.get('modelfile','')[:200]); print('DIGEST', (d.get('details') or {})); print('KEYS', list(d)[:20])"
