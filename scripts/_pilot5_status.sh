#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
echo "=== processes ==="
pgrep -af "run_cohort_c_pilot5|hmmsearch|hmmbuild|blast|mmseqs" || echo none
echo "=== pidfile ==="
cat external_validation_agentic/cohort_C_pilot5_run.pid 2>/dev/null || echo no_pidfile
echo "=== ollama ==="
curl -sS --max-time 5 http://172.17.32.1:11434/api/ps || echo ollama_fail
echo "=== lacZ dir ==="
ls -la external_validation_agentic/cohort_C_runs/GCF_055394735.1/genome_skeptic_agentic/lacZ_beta_galactosidase 2>/dev/null || echo no_lacz
echo "=== case locks ==="
find external_validation_agentic/cohort_C_runs -name case_locked.json -o -name condition_locked.json
echo "=== log tail ==="
tail -n 30 external_validation_agentic/cohort_C_pilot5_run.log
