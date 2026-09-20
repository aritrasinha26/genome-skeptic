#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
curl -sS --max-time 15 http://172.17.32.1:11434/api/tags | python -c 'import sys,json; d=json.load(sys.stdin);
for m in d.get("models") or []:
    name=m.get("name") or m.get("model")
    if name and "qwen3:4b" in str(name):
        print(json.dumps({k:m.get(k) for k in ("name","model","digest","size","modified_at","details")}, indent=2, default=str))
'
