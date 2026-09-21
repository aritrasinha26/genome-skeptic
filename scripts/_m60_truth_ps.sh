#!/usr/bin/env bash
ps -ef | grep -E 'diamond|hmmsearch|adjudicate|python' | grep -v grep | head -20
echo ---
ls /home/aritr/m60_work/truth_evidence 2>/dev/null | head
echo ---
ls /home/aritr/m60_work/truth_diamond 2>/dev/null
echo ---
ls /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/TRUTH_M60/CASE_RECORDS 2>/dev/null | head
