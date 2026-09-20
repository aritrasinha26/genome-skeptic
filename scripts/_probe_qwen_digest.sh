#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
curl -sS --max-time 15 http://172.17.32.1:11434/api/show -d '{"name":"qwen3:4b"}' | python -c 'import sys,json; d=json.load(sys.stdin); print("KEYS", sorted(d)); print("DIGEST", d.get("digest")); print("MODELINFO_KEYS", sorted((d.get("model_info") or {}))[:30] if isinstance(d.get("model_info"), dict) else d.get("model_info"));
for k,v in d.items():
    if "digest" in k.lower() or "sha" in k.lower():
        print("FIELD", k, v)
'
