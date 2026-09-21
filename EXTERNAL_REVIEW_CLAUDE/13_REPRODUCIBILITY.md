# Reproducibility

## Execution host (M60 production)

Source of truth: `manuscript_benchmark/M60_ENVIRONMENT.json` (`2026-09-20T02:06:42Z`).

| Item | Observed |
|---|---|
| Host | WSL2 Linux (`Linux-6.18.33.2-microsoft-standard-WSL2`) |
| Python | **3.11.16** (`/home/aritr/micromamba/envs/genome-skeptic-prod/bin/python`) |
| BLAST+ | **2.16.0+** |
| HMMER | **3.4** (Aug 2023) |
| MMseqs | **18.8cc5c** |
| DIAMOND | **2.2.6** |
| AMRFinderPlus | **4.2.7** |
| AMRFinder database | **2026-08-07.1** |
| FastTree | **2.2.0** (truth adjudication) |
| eggNOG-mapper | **not installed** (explicitly not an M60 comparator) |

`environment.yml` specifies `python=3.11` and the bioconda/conda-forge stack. Exact pip freeze (71 entries) is inside `M60_ENVIRONMENT.json` (`pip_freeze`). See `ENVIRONMENT_MANIFEST.txt` in this folder.

**Do not use** the freeze-manifest `environment` object as the M60 host: it records Windows Python **3.13.1** with BLAST/HMMER/MMseqs/DIAMOND `available: false`. That is a Windows-side snapshot taken when hashing the freeze, not the WSL production run.

---

## Qwen (prospective Agentic)

| Item | Observed |
|---|---|
| Model | `qwen3:4b` |
| Quantization | **Q4_K_M** (recorded in `agentic_freeze/GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json` with the same digest; not in `M60_ENVIRONMENT.json`) |
| Digest | `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` (M60 position locks) |
| Config | `config/qwen_agentic_dev.yaml` |
| Temperature | 0.0 |
| thinking | false |
| Provider | `openai_compatible` → Ollama `http://localhost:11434/v1` |

---

## Sol (post-hoc only)

| Item | Observed |
|---|---|
| Model | `gpt-5.6-sol` |
| reasoning | `high` (`SOL_REASONING_EFFORT` in post-hoc providers) |
| Config | `config/sol56_high_posthoc.yaml` |
| Provider | `openai_api` |
| Requires | `OPENAI_API_KEY` in the environment (**do not commit**) |

---

## Random seeds

| Use | Seed |
|---|---|
| D8 / D12 / M60 sampling hashes | `20260920` (string in SHA256 formulas) |
| Paired bootstrap | integer `20260920` |
| Bootstrap resamples | 10,000 |

---

## Entry points and working directory

Assume repository root = directory containing `src/genome_skeptic` and `manuscript_benchmark/`.

M60 was executed on WSL with FASTA work dir `/home/aritr/m60_work/fasta/{original,solver}/`. Windows fallback `manuscript_benchmark/m60_work/` is gitignored.

| Stage | Command class |
|---|---|
| Freeze | `scripts/freeze_manuscript_v4_1.py` (already done; do not rerun to “update”) |
| Select cohort | `scripts/select_m60_cohort.py` (already locked) |
| Run one position | `scripts/run_m60_position.py` |
| Lock predictions | `scripts/finalize_m60_predictions.py` |
| Truth | `scripts/freeze_m60_truth_sources.py` → `adjudicate_m60_truth.py` → `lock_m60_truth.py` → `lock_m60_phase3b.py` |
| Unblind | `scripts/score_m60_phase4.py` |
| Sol (post-hoc) | `EXTERNAL_REVIEW_CLAUDE/posthoc_code/scripts/run_sol56_full_ablation.py` |

**Do not regenerate predictions or truth for this review.** Locked JSON is the scientific record.

---

## Genome retrieval (FASTA not in git)

`scripts/select_and_download_d20.fetch_genome_fasta`:

1. NCBI Datasets API  
   `https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{GCF}/download?include_annotation_type=GENOME_FASTA`
2. Fallback: `ftp_path` from the cohort manifest
3. Write original + sanitized solver FASTA (`GCF_*.fna`)

Per-assembly SHA256, bytes, and solver path: `TRUTH_M60/M60_TRUTH_SOURCE_MANIFEST.json` → `assemblies[]`.

`.gitignore` excludes `*.fna` / `*.fasta`.

---

## Package / project metadata

- `pyproject.toml`: python `>=3.11`; pydantic, typer, PyYAML, requests
- Editable install recorded in pip freeze: `-e /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor`
- Tests: `tests/test_manuscript_v4_1.py` (scientific-core identity), `tests/test_sol56_adapter.py` (post-hoc, copied)

---

## What independent reproduction can do without huge binaries

1. Re-hash locked JSON/CSV/MD (this package’s HASH_MANIFEST)
2. Re-run `score_m60_phase4.py` **read-only against locked predictions + truth** (should not change them)
3. Inspect validator code vs 8-error forensics
4. Re-download FASTA by accession and compare SHA256 to the truth-source manifest **if** performing a full rerun (not required for claim audit)

A full Agentic rerun requires Ollama `qwen3:4b` at the recorded digest and the WSL tool stack.
