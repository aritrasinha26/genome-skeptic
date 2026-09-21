# Data provenance

## M60 assemblies

| Field | Value |
|---|---|
| n | 60 unique GCF accessions |
| Source | NCBI RefSeq / NCBI Datasets API v2 genome FASTA download; FTP fallback from cohort `ftp_path` |
| Release cutoff | `seq_rel_date >= 2025-01-01` |
| Retrieval script | `scripts/select_and_download_d20.py` `fetch_genome_fasta` used by `select_m60_cohort.py` / `run_m60_position.ensure_solver_fasta` |
| Cohort lock | `2026-09-20T03:07:15Z` |
| Local original path (WSL) | `/home/aritr/m60_work/fasta/original/{GCF_*.fna}` |
| Local solver path | `/home/aritr/m60_work/fasta/solver/{GCF_*.fna}` |
| Expected filename | `{assembly_accession}.fna` |
| In git? | **NO** (`*.fna` gitignored) |
| SHA256 of each assembly | `manuscript_benchmark/TRUTH_M60/M60_TRUTH_SOURCE_MANIFEST.json` → `assemblies[]` |

Headers sanitized to opaque `contig_N` identifiers (product/gene/organism text stripped) for solver copies.

## Family / ortholog reference assets (tracked)

Packaged families under `data/target_families/` and `src/genome_skeptic/data/target_families/` (duplicate trees; freeze hashes both). Ortholog references under `data/orthology_references/`.

These **were copied into truth SOURCE_FREEZE** for adjudication. That is disclosed circularity of reference panels, not of prediction JSON.

## D8 / D12 / D20 genomes

Same NCBI Datasets pattern. Solver FASTA under each campaign `inputs/` tree — **gitignored**. Manifests record per-file SHA256.

D20: 40-candidate pool SHA256 `61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c`. Partial v5_prescreen gitignored. Final D20 not locked.

## Predictions

Per-position JSON under `manuscript_benchmark/POSITION_LOCKS/` (tracked). Aggregates `M60_*_LOCKED.json`. Prediction-lock manifest SHA256 `5317b33f…`.

## Truth

Locked JSON/CSV/MD tracked. Evidence ORF trees, rebuilt HMMs, UniProt dumps, human-review packets: **gitignored**. Reconstruct from source manifest + methods if needed; not required to verify the locked labels.

## Sol

Copied for GitHub review into `manuscript_benchmark/SOL56_*`. Originally produced in a local worktree (`GenomeSkeptic_SolAblation`) after the prospective unblind.

## Eligible pool

`M60_ELIGIBLE_POOL.json` SHA256 `3d1f95e3c8613a5c7848758d02433518b319b9096103fbfde1a9fcfcd3600d02`, n=104291, **gitignored**.

## What a GitHub clone lacks

1. Raw M60/D8/D12/D20 FASTA
2. `TRUTH_M60/{EVIDENCE,CASE_RECORDS,SOURCE_FREEZE,HUMAN_REVIEW,REVIEW,FINAL}/`
3. `M60_ELIGIBLE_POOL.json`
4. `RUNS/`, `RUN_LOGS/`, D12/D20 `v5_prescreen/`
5. Ollama model weights
6. AMRFinder database files (version recorded; data dir gitignored)

Hashes and accessions are sufficient to re-fetch and verify FASTA if a reviewer does that independently.
