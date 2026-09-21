#!/usr/bin/env bash
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$HERE/GenomeSkeptic.code-workspace"
if command -v cursor >/dev/null 2>&1; then
  cursor "$WORKSPACE" >/dev/null 2>&1 &
elif [ "$(uname)" = "Darwin" ]; then
  open -a Cursor "$WORKSPACE"
else
  echo "Cursor CLI not found. Open GenomeSkeptic.code-workspace from Cursor manually."
  exit 1
fi
