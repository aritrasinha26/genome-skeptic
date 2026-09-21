# Files for review

Reference **repository paths**. Large binaries are not duplicated here.

Git status of bulky trees: many FASTA/evidence/run directories are gitignored. If a path is missing in a GitHub clone, see the “local-only” column.

---

## Frozen system

| Artifact | Path | Notes |
|---|---|---|
| Freeze manifest | `manuscript_benchmark/GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json` | SHA256 `97a94dfe…` |
| Freeze narrative | `manuscript_benchmark/GENOME_SKEPTIC_V4_1_MANUSCRIPT.md` | |
| Scientific core hasher | `src/genome_skeptic/manuscript/scientific_core.py` | |
| Tag | `GENOME_SKEPTIC_V4_1_MANUSCRIPT` | commit `8f66868` |

## M60 design / selection

| Artifact | Path | GitHub? |
|---|---|---|
| Protocol | `manuscript_benchmark/M60_PROTOCOL.md` | yes |
| Protocol v1.1 | `manuscript_benchmark/M60_PROTOCOL_V1_1.md` | yes |
| Exclusion | `manuscript_benchmark/M60_EXCLUSION_MANIFEST.json` | yes |
| Eligible pool | `manuscript_benchmark/M60_ELIGIBLE_POOL.json` | **no (gitignore)**; SHA256 in audit |
| Challenge pool | `manuscript_benchmark/M60_CHALLENGE_CANDIDATE_POOL.json` | yes |
| Ambiguity scores | `manuscript_benchmark/M60_CHALLENGE_AMBIGUITY_SCORES.json` | yes |
| Cohort JSON/CSV | `manuscript_benchmark/M60_COHORT_MANIFEST.json` `.csv` | yes |
| Selection audit | `manuscript_benchmark/M60_SELECTION_AUDIT.md` | yes |
| Selection script | `scripts/select_m60_cohort.py` | yes |
| Environment | `manuscript_benchmark/M60_ENVIRONMENT.json` | yes |
| AMRFinder DB freeze | `manuscript_benchmark/ENVIRONMENT/AMRFINDER_DATABASE_FREEZE.json` | yes |

## Predictions / locks

| Artifact | Path | GitHub? |
|---|---|---|
| Prediction-lock manifest | `manuscript_benchmark/M60_PREDICTION_LOCK_MANIFEST.json` | yes |
| 60 position locks | `manuscript_benchmark/POSITION_LOCKS/position_XX/` | yes (722 tracked files) |
| Aggregate locks | `M60_GS_{DETERMINISTIC,AGENTIC,EXHAUSTIVE}_LOCKED.json`, `M60_CONVENTIONAL_LOCKED.json`, `M60_SPECIALIST_COMPARATORS_LOCKED.json` | yes |
| Runner | `scripts/run_m60_position.py` | yes |
| Run logs | `manuscript_benchmark/RUN_LOGS/` | **no** |

## Truth

| Artifact | Path | GitHub? |
|---|---|---|
| Methods | `TRUTH_M60/M60_TRUTH_METHODS.md` | yes |
| Source manifest | `TRUTH_M60/M60_TRUTH_SOURCE_MANIFEST.json` | yes |
| Pre-truth chain | `TRUTH_M60/PRE_TRUTH_CHAIN.json` | yes |
| Original / final truth JSON | `M60_EXTERNAL_TRUTH_LOCKED.json`, `M60_EXTERNAL_TRUTH_FINAL_LOCKED.json` | yes |
| Case-level CSV | `M60_TRUTH_CASE_LEVEL.csv`, `M60_TRUTH_FINAL_CASE_LEVEL.csv` | yes |
| Human review CSVs | `M60_HUMAN_REVIEW_REQUIRED.csv`, `M60_HUMAN_ADJUDICATION.csv`, `M60_TRUTH_FINAL_REVIEW.csv` | yes |
| Evidence trees / SOURCE_FREEZE / HUMAN_REVIEW packets | `TRUTH_M60/EVIDENCE/` etc. | **no** |

## Primary results / statistics

| Artifact | Path |
|---|---|
| All Phase 4 outputs | `manuscript_benchmark/RESULTS_M60/` |
| Script | `scripts/score_m60_phase4.py` |

## Sol (post-hoc; copied into this repo for GitHub)

| Artifact | Path |
|---|---|
| Full ablation | `manuscript_benchmark/SOL56_FULL_ABLATION/` |
| 5-case preflight | `manuscript_benchmark/SOL56_SMALL_PREFLIGHT/` |
| Post-hoc code | `EXTERNAL_REVIEW_CLAUDE/posthoc_code/` |
| YAML | `config/sol56_high_posthoc.yaml` |

## Mechanistic error analysis (post-hoc)

`manuscript_benchmark/POSTHOC_ERROR_ANALYSIS/` (previously untracked; included on the audit branch).

## Development (D8/D12/D20)

| Cohort | Path | FASTA/runs |
|---|---|---|
| D8 | `external_validation_agentic_d8/` | inputs gitignored |
| D12 | `external_validation_agentic_d12/` | inputs/prescreen gitignored |
| D20 | `external_validation_agentic_d20/` | inputs/prescreen gitignored |

## Genome FASTA retrieval (not in git)

For each M60 accession in the cohort manifest:

- Expected original filename: `{assembly_accession}.fna` under `/home/aritr/m60_work/fasta/original/`
- Expected solver filename: same under `fasta/solver/`
- Source: NCBI Datasets API (see `13_REPRODUCIBILITY.md`)
- SHA256: `TRUTH_M60/M60_TRUTH_SOURCE_MANIFEST.json`

Do **not** add huge FASTA binaries to git solely for review.
