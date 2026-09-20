#!/bin/bash
echo "=== procs ==="
ps -ef | grep -E 'spades|evaluate-real|fastp|micromamba' | grep -v grep || echo 'no matching procs'
echo "=== mem ==="
grep -E 'MemTotal|MemAvailable|MemFree|SwapFree' /proc/meminfo
echo "=== dev_02 production ==="
ls /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval/dev_02/production 2>/dev/null || echo missing
ls /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval/dev_02/production/spades/contigs.fasta 2>/dev/null || echo 'no dev_02 contigs'
echo "=== dev_06 production ==="
ls /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval/dev_06/production 2>/dev/null || echo missing
ls /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval/dev_06/production/spades/contigs.fasta 2>/dev/null || echo 'no dev_06 contigs'
echo "=== dev_06 spades tail ==="
tail -n 12 /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval/dev_06/production/spades/spades.log 2>/dev/null | tail -c 1500
echo
echo "=== report mtime ==="
ls -l /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval/realgenome_production_report.json
