#!/usr/bin/env bash
set -euo pipefail
export MAMBA_ROOT_PREFIX=/home/aritr/micromamba
eval "$(/home/aritr/micromamba/bin/micromamba shell hook -s bash)"
micromamba activate genome-skeptic-prod
ROOT=/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor
TGT=/home/aritr/d20_v5_work/runs/GCF_048282645.1/lacZ_beta_galactosidase/target.fa
ASM=/home/aritr/d20_v5_work/fasta/GCF_048282645.1.fna
ls -lh "$TGT" "$ASM"
echo "BLAST_VERSION"
tblastn -version
echo "TBLASTN_START $(date -Is)"
timeout 180 tblastn -query "$TGT" -subject "$ASM" -evalue 1e-3 -outfmt '6 qseqid sseqid pident length qlen slen qstart qend sstart send evalue bitscore' -max_hsps 20 -max_target_seqs 20 -out /tmp/tblastn_d20.tsv || echo "TBLASTN_STATUS:$?"
echo "TBLASTN_END $(date -Is)"
wc -l /tmp/tblastn_d20.tsv || true
head -n 5 /tmp/tblastn_d20.tsv || true
echo "SEARCH_DIR"
ls -la /home/aritr/d20_v5_work/runs/GCF_048282645.1/lacZ_beta_galactosidase/genome_skeptic/search || true
ls -la /home/aritr/d20_v5_work/debug_one/genome_skeptic/search || true
