# Genome Skeptic role-swap study

This directory contains the code and frozen artifacts required to reproduce the experiments reported in the manuscript:

"AI Models Excel at Orchestration but Falter at Biological Judgment"

The remainder of the repository contains development material and is not required to reproduce the results reported in this manuscript.

## Primary reproduction route (no API keys)

```bash
# 1. Clone the repository and enter this folder
cd paper_role_swap

# 2. Install dependencies (Python 3.11+; matplotlib, numpy, scipy for figure/stats regen)
pip install numpy scipy matplotlib

# 3. Verify locked manuscript claims
python scripts/scoring/verify_locked_claims.py

# 4. Regenerate statistics, Table 1, and Figures 2–4 from locked case-level records
python scripts/reproduce/reproduce_all.py
```

- **Verification** (`verify_locked_claims.py`) reads frozen outputs under `results/` and `data/` and checks every reported numerical claim.
- **Reproduction** (`scripts/reproduce/`) recomputes statistics, tables and figures from locked predictions + truth + pre-unblind behaviour **inside this folder only**.
- Neither path requires an API key.
- Rerunning GPT-5.6 Sol or Jev is **optional** and is **not required** to reproduce the manuscript findings.

Regenerated artifacts are written to `reproduced/` and do **not** overwrite locked results.

## 1. What the study tested

Genome Skeptic separates three jobs: deterministic measurement, workflow control (which follow-up analyses to run), and final biological adjudication. The prospective experiment asked whether GPT-5.6 Sol improves accuracy when it controls follow-ups, and whether transferring final decision authority to Sol helps when the evidence state is held fixed.

## 2. Three central experiments

1. **60-case precursor (M60).** Different controller policies produced different evidence states and follow-up counts, but final endpoints stayed identical. Eight shared evaluable errors traced to two adjudication defects; the repaired adjudicator was frozen as V5 before the prospective study.
2. **Prospective 20-genome tet(A)/tet(B) controller comparison.** Locked 10 POSITIVE / 10 NEGATIVE genomes; Arms A (fixed), B (Sol controller), C (exhaustive), F (Jev controller) all retained the deterministic validator. Endpoints matched (18/20); follow-ups differed (57 / 39 / 74).
3. **Identical-evidence role swap.** Arm D (Sol final judge) received Arm B’s locked final evidence states. Result: 18/20 vs 11/20; 0 corrections / 7 degradations; 9 ABSENT→UNRESOLVED; exact McNemar *P* = 0.015625; paired accuracy difference −0.35 (bootstrap 95% CI −0.55 to −0.15).

## 3. Directory structure

```
paper_role_swap/
├── README.md
├── STUDY_MANIFEST.json
├── REPRODUCIBILITY_AUDIT.md
├── BUNDLE_MINIMIZATION_AUDIT.md
├── protocol/
├── config/                      # freeze, action registry, prompts, Sol YAML
├── scripts/
│   ├── scoring/verify_locked_claims.py
│   └── reproduce/               # paper-local stats/table/figure regeneration
├── data/                        # cases, truth, locks, predictions, Arm B evidence
├── results/                     # locked scored tables, stats, figure sources
├── reproduced/                  # outputs of scripts/reproduce/ (generated)
└── provenance/
```

## 4. Software requirements

For the **primary path** (locked verification + regeneration): Python 3.11+ with `numpy`, `scipy`, `matplotlib`.

For an optional **model-dependent re-run** of Sol/Jev (not required for manuscript numbers): the full Genome Skeptic production environment outside this folder, plus API credentials. Keys are never stored here.

## 5. How to retrieve the public genome assemblies

Assemblies are not bundled. Use `data/accessions_and_checksums.csv` (also `data/GENOME_RETRIEVAL.md`).

```bash
datasets download genome accession GCF_047713185.1 --include genome
```

Verify the genomic FASTA SHA256 against `assembly_sha256` before any optional re-run.

## 6. Precursor analysis (locked)

Inspect `results/precursor/`:

- Policy ≠ endpoint: `POSTHOC_MODEL_INVARIANCE.md`, `SOL56_M60_SUMMARY.json`
- Eight shared errors → two adjudication defects: `POSTHOC_MANUSCRIPT_INTERPRETATION.md`, `POSTHOC_ERROR_CASES.csv`, `ABLATION_VALIDATOR_R1_SUMMARY.md`
- Locked reanalysis: `M60_REANALYSIS_SUMMARY.md`, `M60_FINAL_CASE_LEVEL_RESULTS.csv`

Figure 2 regeneration uses the locked precursor CSVs via `scripts/reproduce/reproduce_figure2.py`.

## 7–9. Prospective controller comparison, role-swap scoring, statistics

Use the primary route above. Locked published numbers also live in:

| Claim | Locked file |
| --- | --- |
| 18/20 vs 11/20 | `results/controller_summary.csv`, `results/statistics.json` |
| 0 corrections / 7 degradations | `results/statistics.json` → `b_vs_d` |
| 9 ABSENT→UNRESOLVED | `results/statistics.json` → `transitions` |
| McNemar *P* = 0.015625 | `results/statistics.json` |
| Paired diff −0.35 [−0.55, −0.15] | `results/statistics.json` → `paired_bootstrap_D_minus_B` |
| Follow-ups 39 / 57 / 74 | `results/controller_efficiency.csv` |
| Sol 10.28 s vs Jev 2.22 s median latency | `results/controller_efficiency.csv` |
| B↔D evidence 20/20 | `data/arm_b_vs_d_evidence_hashes.csv` |

## 10. Manuscript figures / tables

| Item | Locked source | Paper-local regeneration |
| --- | --- | --- |
| **Table 1** | `protocol/ARM_DEFINITIONS.md` + arm scores | `scripts/reproduce/reproduce_table1.py` → `reproduced/table1.csv` |
| **Figure 2** (precursor) | `results/precursor/M60_*` CSVs | `reproduce_figure2.py` → `reproduced/figure2.png` |
| **Figure 3** (controller efficiency) | follow-ups + `preunblind_behaviour.csv` | `reproduce_figure3.py` → `reproduced/figure3.png` |
| **Figure 4** (role swap) | B vs D discordances | `reproduce_figure4.py` → `reproduced/figure4.png` |
| **Figure 1** (architecture schematic) | `results/figure_source_data/FIGURE1_architecture.png` | schematic already locked (not recomputed biologically) |

`scripts/scoring/score_role_swap_unblind.py` is retained as the historical full-repo scorer; manuscript regeneration for this bundle uses `scripts/reproduce/` instead.

## Model reproducibility pins

**GPT-5.6 Sol:** alias `gpt-5.6-sol`; reasoning `high`; temperature `0.0`; prompt hashes in `config/prompts/PROMPT_AND_MODEL_HASHES.json`.

**Jev:** alias `jev-latest`; TypeSafe System One (Choice / Noul); controller only.

## Integrity

See `STUDY_MANIFEST.json`, `REPRODUCIBILITY_AUDIT.md`, and `reproduced/REPRODUCTION_REPORT.md`.
