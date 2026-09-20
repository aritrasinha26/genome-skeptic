#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/external/bioagent_bench
cd "$ROOT"
echo "=== git remote -v ==="
git remote -v
echo "=== git rev-parse HEAD ==="
git rev-parse HEAD
echo "=== git status ==="
git status
echo "=== tasks ==="
ls -1 tasks
