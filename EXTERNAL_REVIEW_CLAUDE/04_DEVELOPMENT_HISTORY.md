# Development history (not sanitized)

This section exists so a reviewer can assess **overfitting and researcher degrees of freedom**.

tetA and rpoB were chosen as manuscript primary endpoints **after** D8/D12 development experience and **before** M60 sampling (freeze `m60_cases_selected: false` at 01:52 UTC; cohort lock 03:07 UTC). tuf and lacZ were retained as limitation endpoints and **excluded from M60**.

That is a legitimate scientific decision **and** a degree of freedom: M60 does not test the endpoints that development showed were broken.

---

## D8 (`external_validation_agentic_d8/`)

- Name: `D8_MINI_EXTERNAL`
- Seed: `20260920`
- Frozen agentic: `GENOME_SKEPTIC_AGENTIC_V2_D20`
- n = 8 unique genomes / species / genera
- Targets: rpoB×2, tuf×2, lacZ×2, tetA×2
- Selection: metadata-only routine (`challenge_enriched: false`)
- D20 pool excluded; `d20_directory_modified: false`

Manifest SHA256 (working-tree / sidecar): `37862918643052fa8cb81ff5e180161973a6dd5311aef62bd78c59f8ea74cdbd`

### Endpoints scored

| Target | Endpoint |
|---|---|
| rpoB | ORTHOLOGOUS_GENE_PRESENCE_ABSENCE |
| tuf | EXACT_MULTIPLICITY |
| lacZ | ORTHOLOGOUS_GENE_PRESENCE_ABSENCE |
| tetA | FAMILY_PRESENCE_ABSENCE (tet(A)/tet(B) only; tet(C) excluded) |

### Primary accuracy (`D8_SYSTEM_SUMMARY.csv` / `D8_EXTERNAL_RESULTS.md`)

| System | Correct / evaluable |
|---|---|
| Conventional | 3 / 8 |
| Deterministic V5 | 3 / 8 |
| Agentic V2 end-to-end | 3 / 8 |
| Agentic completion | 6 / 8 |

NET CORRECTIONS V5 vs Agentic = **0**. McNemar NA (0 discordant pairs).

### Known D8 failures

1. **tetA family false positive / execution failure**  
   Position 7 `GCF_053618555.1` tetA truth **NEGATIVE**. V5 DETECTED. Agentic **EXECUTION_FAILURE** (`planner cited no evidence IDs`). `competitive_family` was available but not executed because of the failure.

2. **tuf locus / multiplicity**  
   Positions 3 and 5 truth multiplicity **1**; all systems scored multiplicity **0** (or execution failure on pos 3). Exact multiplicity was not recovered.

3. **lacZ discrimination**  
   Positions 4 and 6 truth **NEGATIVE**; V5 and Agentic **DETECTED**. Classified as toolbox gap (no competing-family instrument for lacZ).

4. **Agentic execution failures** 2 / 8 (pos 3 tuf, pos 7 tetA).

Truth for D8 used NCBI Gene Orthologs / phmmer / PGAP AMR corroboration — **different from M60 truth protocol**. D8 is development evidence, not the manuscript primary.

Scripts: `scripts/select_and_download_d8.py`, `run_d8_three_systems.py`, `score_d8_external.py`, `unblind_d8_external_truth.py`.

---

## D12 (`external_validation_agentic_d12/`)

- Name: `V3_D12_EXTERNAL`
- Seed: `20260920`
- Frozen agentic: `GENOME_SKEPTIC_AGENTIC_V3_EXTERNAL`
- n = 12 unique genomes / species / genera
- Targets: rpoB×3, tuf×3, lacZ×3, tetA×3
- Selection: **challenge-enriched**; V5 used for selection; ambiguity score used
- D8 excluded; D20 pool excluded

Manifest SHA256: `54b477d3cf8197ffa73d7ffb2e94ffe4a993b861565a3266085d33ae68b0546f`

### Primary accuracy (`D12_SYSTEM_SUMMARY.csv`)

| System | Correct / evaluable |
|---|---|
| Conventional | 5 / 12 |
| Deterministic V5 | 6 / 12 |
| Agentic V3 end-to-end | 6 / 12 |

**TARGET-SPECIFIC ENDPOINTS IDENTICAL (V5 vs Agentic V3): 12/12.** NET CORRECTIONS = 0.

### Dual-error cases (`D12_ERROR_ANALYSIS.md`) — both V5 and Agentic wrong

| Pos | Accession | Target | Class |
|---|---|---|---|
| 1 | GCF_060416925.1 | tetA | VALIDATOR_DECISION_LIMIT (FAMILY contract; remote homology treated as presence) |
| 3 | GCF_053795755.1 | tetA | VALIDATOR_DECISION_LIMIT |
| 6 | GCF_059683705.1 | tuf | VALIDATOR_DECISION_LIMIT (truth=1, both multiplicity=0) |
| 7 | GCF_048585425.2 | lacZ | MISSING_SCIENTIFIC_INSTRUMENT |
| 9 | GCF_052955985.1 | tuf | VALIDATOR_DECISION_LIMIT (truth=2, both multiplicity=0) |
| 11 | GCF_054055795.1 | tetA | VALIDATOR_DECISION_LIMIT (close_paralogue, 4 loci) |

D12 tetA errors are **false positives** on a FAMILY_PRESENCE_ABSENCE contract (truth NEGATIVE, systems DETECTED). M60 tetA errors are **false negatives** (truth POSITIVE, systems NEGATIVE) under V4.1 `ambiguous_family` veto. The failure **direction** changed after V4.1 family-identity repair. That is exactly the kind of development-informed shift a reviewer should scrutinize.

Scripts: `select_and_download_d12.py`, `lock_d12_challenge_selection.py`, `run_d12_v5_prescreen.py`, `run_d12_three_systems.py`, `run_d12_v4_1_dev_replay.py`, `score_d12_external.py`.

---

## V3 → V4 / V4.1 (using development evidence)

Documents:

- `GENOME_SKEPTIC_V4.md`, `GENOME_SKEPTIC_V4_1.md`
- `manuscript_benchmark/GENOME_SKEPTIC_V4_1_MANUSCRIPT.md`
- `manuscript_benchmark/TARGET_READINESS.md` (freeze tree)
- `manuscript_benchmark/TEST_HYGIENE.md` (254 tests passed after harness repairs; states no V4.1 scientific changes for that audit)
- `paralogue_validation_v4_1.json`, `divergence_validation_v4_1.json`
- `agentic_freeze/` V1, V2_D20, V3_EXTERNAL
- `agentic_freeze/CURRENT_LACZ_LIMITATION.md`

Freeze commit contains `scripts/run_d12_v4_dev_replay.py` and `scripts/run_d12_v4_1_dev_replay.py`: D12 cases were used as a **development replay** while building V4.1.

### TARGET_READINESS (before M60 selection; in freeze commit)

**tetA READY** because:

- generic FAMILY_IDENTITY_UNRESOLVED logic repaired
- sequence-decisive competitive_family action now executes
- **D12 development positions 1/3/11 corrected 3/3**
- no accession-specific logic

**rpoB READY** because:

- controlled divergent-orthologue rescue demonstrated
- HMMER/MMseqs/DIAMOND available
- D12 rpoB 3/3 correct before V4 development

**tuf NOT READY:**

- pos6 truth=1 reconstructed one locus; pos9 truth=2 reconstructed one locus
- final endpoint still `target_gene_not_detected`
- exact multiplicity not reliable

**lacZ NOT READY:**

- D12 5/7/8 remain UNRESOLVED_CANDIDATE
- assay lacks demonstrated discriminatory power

These decisions were made **before M60 sampling**. M60 therefore never measures tuf/lacZ. That hides unresolved endpoint/instrument failures from the primary table. It also means tetA/rpoB were **pre-selected as the endpoints most likely to look coherent** after D8/D12.

V4.1 freeze: `d8_rerun: false`, `d12_rerun: false`, `biological_thresholds_changed: false` after the freeze record.

---

## Why tuf/lacZ were excluded — timing relative to M60

| Fact | Source |
|---|---|
| Readiness decision predates M60 cohort | `TARGET_READINESS.md`; freeze `m60_cases_selected: false` |
| M60 protocol lists only tetA + rpoB | `M60_PROTOCOL.md` / `M60_PROTOCOL_V1_1.md` |
| M60 cohort is 30 tetA + 30 rpoB | `M60_COHORT_MANIFEST.json` |
| Freeze lists limitation targets | freeze manifest `limitation_targets` |

**WHY:** development showed tuf multiplicity and lacZ competitor discrimination were not manuscript-ready. Including them would have mixed unresolved instrument failures into the primary accuracy claim.

**COST:** the paper cannot claim general genome-annotation performance. Endpoint choice is informed by the same research programme that later “tests” those endpoints on new genomes.

---

## Regression / hygiene artifacts (development, not M60)

- `tests/test_manuscript_v4_1.py`, `tests/test_agentic_v4_1_dev.py`
- `TEST_HYGIENE.md`
- JSON campaign files at repo root (`divergence_validation_v4_1.json`, `paralogue_validation_v4_1.json`, `model_independence_v4_1.json`, …)

These are **not** the prospective M60 result.

---

## Implications for M60 (reviewer)

1. Adaptive LLM follow-up already showed **zero endpoint corrections** on D8 and D12. M60’s 0 corrections is a **replication of a development pattern**, not a surprise.
2. tetA V4.1 was repaired using D12 false-positive cases. M60 then observed **seven false negatives** on a related (not identical) family contract. Repair may have over-tightened family-state rules.
3. Challenge sampling for M60 used frozen V4.1 deterministic ambiguity scores — the same core that was tuned on development genomes (different accessions; 0 overlap).
4. D8/D12 **accessions** were excluded from M60 (verified 0 overlap). That reduces case-level leakage; it does not remove endpoint-level researcher degrees of freedom.
