#!/usr/bin/env bash
# Controlled database acquisition. Large taxonomy DBs are never downloaded
# unless explicitly requested.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${GENOME_SKEPTIC_DB_ROOT:-$ROOT/databases}"
mkdir -p "$DEST"

usage() {
  cat <<EOF
Usage: $0 <bakta-light|bakta-full|checkm2|kraken2-standard|kraken2-small>
Downloads are explicit. A missing taxonomy database must remain unavailable.
EOF
}

record() {
  python - "$1" "$2" "$3" <<'PY'
import json, hashlib, sys
from datetime import date
from pathlib import Path
name, path, source = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
meta = {
    "name": name,
    "path": str(path),
    "source": source,
    "download_date": date.today().isoformat(),
    "exists": path.exists(),
    "bytes": path.stat().st_size if path.exists() else 0,
}
print(json.dumps(meta, indent=2))
(path.parent / f"{name}_provenance.json").write_text(json.dumps(meta, indent=2))
PY
}

cmd="${1:-}"
case "$cmd" in
  bakta-light)
    echo "Bakta light DB: use bakta_db download --type light --output $DEST/bakta"
    if command -v bakta >/dev/null && command -v bakta_db >/dev/null; then
      bakta_db download --type light --output "$DEST/bakta"
    elif command -v bakta >/dev/null; then
      bakta download --output "$DEST/bakta" --type light || true
    else
      echo "bakta is not on PATH; install the production env first."
      exit 1
    fi
    record bakta "$DEST/bakta" "https://github.com/oschwengers/bakta"
    ;;
  bakta-full)
    echo "Bakta full DB is large. Refusing to start without confirmation via this explicit command."
    if command -v bakta_db >/dev/null; then
      bakta_db download --type full --output "$DEST/bakta"
    else
      bakta download --output "$DEST/bakta" --type full
    fi
    record bakta "$DEST/bakta" "https://github.com/oschwengers/bakta"
    ;;
  checkm2)
    echo "Downloading CheckM2 database into $DEST/checkm2"
    if command -v checkm2 >/dev/null; then
      checkm2 database --download --path "$DEST/checkm2"
    else
      echo "checkm2 is not on PATH; install the production env first."
      exit 1
    fi
    record checkm2 "$DEST/checkm2" "https://github.com/chklovski/CheckM2"
    ;;
  kraken2-standard)
    echo "Kraken2 standard DB is large and must be requested explicitly."
    mkdir -p "$DEST/kraken2_standard"
    echo "Place or build a Kraken2 DB under $DEST/kraken2_standard"
    echo "Example: kraken2-build --standard --db $DEST/kraken2_standard"
    record kraken2 "$DEST/kraken2_standard" "manual/explicit"
    ;;
  kraken2-small)
    echo "Documented small Kraken2 configuration: 8GB minikraken or a user-provided DB."
    mkdir -p "$DEST/kraken2_small"
    echo "Download a published MiniKraken DB yourself and unpack into $DEST/kraken2_small"
    echo "Genome Skeptic will not fetch it automatically."
    record kraken2 "$DEST/kraken2_small" "manual/explicit-small"
    ;;
  *)
    usage
    exit 2
    ;;
esac
