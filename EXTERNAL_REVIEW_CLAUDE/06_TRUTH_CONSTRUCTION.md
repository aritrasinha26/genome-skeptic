# Truth construction

This section must be read as **independence engineering**, not as two human experts.

> This is **not** two independent human reviewers. One automated adjudication pipeline applied two distinct evidence routes, then a separate automated second pass over the same evidence records.

Source: `manuscript_benchmark/TRUTH_M60/M60_TRUTH_METHODS.md`.

---

## Order (critical)

1. All 60 position prediction locks complete
2. `M60_PREDICTION_LOCK_MANIFEST.json` (`2026-09-21T07:34:59Z`, SHA256 `5317b33f…`)
3. `PREDICTIONS_LOCKED_BEFORE_TRUTH.txt` = `YES`
4. `PRE_TRUTH_CHAIN.json` (`2026-09-21T09:23:04Z`) verifies freeze / protocol v1.1 / cohort / prediction-lock hashes  
   `prediction_payloads_opened: false`, `accuracy_scored: false`
5. Truth-source freeze (`M60_TRUTH_SOURCE_MANIFEST.json`, `09:23:43Z`, SHA256 `640138da…`)
6. Automated two-route adjudication
7. Original truth lock (`10:01:42Z`, SHA256 `bb375390…`)
8. Human review of 20 flagged cases
9. Final truth lock (`10:10:56Z`, SHA256 `a64dea4f…`)
10. Phase 4 unblind (`10:17:58Z`)

**Prediction payloads were not used during truth construction** — attested by:

- `PREDICTIONS_LOCKED_BEFORE_TRUTH.txt`
- `PRE_TRUTH_CHAIN.json`
- every truth sidecar `"prediction_payloads_opened": false`
- HUMAN_REVIEW packets `"prediction_payloads_included": false`
- path guard in `scripts/m60_truth_common.py` (aborts if truth scripts open GS prediction / POSITION_LOCKS / D20 / AMRFinder-as-truth paths)
- flags: `gs_predictions_used_as_truth: false`, `amrfinder_used_as_truth: false`, `pgap_used_as_truth: false`, `d20_touched: false`

A reviewer can still ask whether **shared family FASTA / HMM resources** create circularity between GS instruments and truth Route 1/2 (see below). That is a different question from “did they open the prediction JSON.”

---

## Two independent EVIDENCE ROUTES

Canonical names in locked truth JSON:

- Route 1: `target_vs_competitor_sequence_reference`
- Route 2: `independent_profile_or_phylogenetic_placement`

### tetA

| Route | Method |
|---|---|
| 1 | Sequence comparison of recovered candidate ORFs vs frozen tet(A)/tet(B) panel (UniProt P02982/P02980 + packaged family members) vs competing MFS/RND/non-target tet-class references |
| 2 | HMMER profile placement on frozen tetA vs competitor HMMs; FastTree when hmmalign succeeded |

A generic MFS match is not sufficient. Remote HMM alone is not sufficient.

### rpoB

| Route | Method |
|---|---|
| 1 | Full/near-full-length similarity + length-ratio vs independently verified RpoB references |
| 2 | RpoB vs RpoC profile placement; FastTree when borderline |

PGAP gene-name equality was not used. Negative rpoB labels were not manufactured for class balance. Uncertainty was not forced into NEGATIVE.

Concordance after Phase 3 automated adjudication: **49 CONCORDANT / 11 DISCORDANT** (of 60).

Second automated pass over the same evidence records: `second_pass_reviewed: 31` (Phase 3 summary).

---

## Decision gates (truth protocol)

From `M60_TRUTH_METHODS.md` / `scripts/m60_truth_common.py` / protocol v1.1:

| Gate | Value |
|---|---|
| Gene AA min identity | 0.60 |
| Gene AA min query coverage | 0.80 |
| Length ratio | 0.80–1.20 |
| Family competitive margin | 0.10 |
| Ambiguous band | 0.05 |
| HMM min gate model coverage | 0.20 |
| HMM domain-only max coverage | 0.45 |
| Sequence-decisive identity×coverage | ≥ 0.70 |
| Sequence-decisive competitor delta | ≥ 0.20 |

These numeric gates **overlap the GS validator thresholds**. Shared numbers do not by themselves prove leakage of **predictions**, but they are a circularity/dependence risk for **endpoint definition**.

---

## Reference panels (`M60_TRUTH_SOURCE_MANIFEST.json`)

Five packaged families copied into `TRUTH_M60/SOURCE_FREEZE/packaged_families/` (gitignored bulky tree; hashes in the source manifest):

| Family | Role | members.faa SHA256 |
|---|---|---|
| tetA_tetracycline_efflux | target | `cc4737c3ab9dc07178f655beb8c108565c44eb2541cce6144ec0e254a2807364` |
| mfs_multidrug_efflux | competitor | `09c34a3dde72ff127f396c5226a9b3c0887edc1cfd5c8726dff88c6555c8a880` |
| rnd_efflux | competitor | `bc8a7c9f8d2d90dd0fb50ddadb32a6cd0b57679e2825b5b5e7bdb5ec39f3c56a` |
| rpoB_RNAP_beta | target | `c284f245e24285d8633cc9fac4f63b1e18b94995ad721e3cc117724f61f68c42` |
| rpoC_RNAP_beta_prime | competitor | `2b7609f19c0ce06c6224cf32023549df9a32bb67d4c1d4d422ce61ba4caa4840` |

These **match the packaged GS family member files**. UniProt records (18) retrieved 2026-09-21 ~09:23 UTC. HMMs rebuilt with hmmbuild for truth (not necessarily byte-identical to GS runtime HMMs).

`m60_cases_used_as_references: false`. All 60 assembly SHA256s recorded with `m60_case_used_as_reference: false`.

---

## Initial truth (Phase 3, before human review)

From `M60_TRUTH_CASE_LEVEL.csv` / `BLINDED_TRUTH_SET_SUMMARY.json`:

| | POSITIVE | NEGATIVE | TRUTH_UNCERTAIN |
|---|---:|---:|---:|
| tetA | 7 | 18 | 5 |
| rpoB | 15 | 0 | 15 |
| **Total** | **22** | **18** | **20** |

`human_review_required: 20`.

Original truth SHA256: `bb37539060efd3e89e0bd548fe1d0e573991dab0816bdead729286cbfcfedb38`.

---

## Human review

20 flagged cases: `M60_HUMAN_REVIEW_REQUIRED.csv`  
positions 3, 7, 8, 9, 11, 20, 23, 25, 26, 29, 31, 34, 35, 39, 40, 50, 52, 55, 56, 60.

Reviewer identifier: `blinded_human_adjudicator_phase3b` (date `2026-09-21`). This is **one** human pass over automated flags, not a second independent expert panel.

**Only change:**

| Field | Value |
|---|---|
| Position | **34** |
| Target | tetA |
| Accession | **GCF_054953385.1** |
| Change | UNCERTAIN → NEGATIVE |
| Rationale (summary) | No independent sequence match to P02980/P02982; recovered locus is competitor P0AEJ0; protocol: no tetA family candidate → NEGATIVE |

Other 19 flagged cases: **retained TRUTH_UNCERTAIN**.

Per-case review packets live in `TRUTH_M60/HUMAN_REVIEW/` (**gitignored**). Tracked CSVs: `M60_HUMAN_ADJUDICATION.csv`, `M60_TRUTH_FINAL_REVIEW.csv`.

---

## Final truth

| | POSITIVE | NEGATIVE | TRUTH_UNCERTAIN |
|---|---:|---:|---:|
| tetA | 7 | 19 | 4 |
| rpoB | 15 | 0 | 15 |
| **Total** | **22** | **19** | **19** |

**41 / 60 truth-evaluable.**

Final truth SHA256: `a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9`.  
`original_truth_lock_unaltered: true` (original file not overwritten; final is a new lock).

---

## How TRUTH_UNCERTAIN was treated

- Remain in the dataset (case-level output, completion statistics)
- **Excluded** from exact accuracy denominators, McNemar, paired bootstrap
- Not forced to NEGATIVE during construction
- `M60_UNCERTAIN_CASES.csv`: 19 rows, `scored_correct_or_incorrect: NOT_SCORED`
- Unresolved/failed-closed **predictions** count as **incorrect** when truth is POSITIVE or NEGATIVE

---

## Explicit limitation: rpoB negatives

rpoB has **ZERO** independently resolved negatives (0 / 30 Phase 3 and Phase 3B).

Therefore **rpoB specificity cannot be estimated**.

All 15 truth-evaluable rpoB cases are POSITIVE. rpoB 14/15 is a **recall/sensitivity** figure, not a balanced accuracy.

---

## Scripts

| Script | Role |
|---|---|
| `scripts/m60_truth_common.py` | Gates, path guards, pre-truth verification |
| `scripts/freeze_m60_truth_sources.py` | Freeze UniProt/HMM/panels/assembly hashes |
| `scripts/adjudicate_m60_truth.py` | Two-route automated adjudication |
| `scripts/lock_m60_truth.py` | Second automated pass + Phase 3 lock |
| `scripts/lock_m60_phase3b.py` | Human adjudication + final lock |
| `scripts/_m60_human_review_dump.py` | Review packets |
| `scripts/_m60_phase3b_verify.py` | Integrity |

---

## Circularity questions for the reviewer (do not pre-answer)

1. Packaged family member FASTAs used by GS **and** copied into truth SOURCE_FREEZE — circularity of **reference**, not of predictions?
2. Shared numeric gates (0.60/0.80/0.45/0.70) — shared endpoint definition vs independent measurement?
3. Truth recovers candidate ORFs from the **same assemblies** GS used — appropriate for presence/absence, but not an orthogonal wet-lab assay.
4. One human adjudicator, not two independent experts.
5. 15/30 rpoB left uncertain — is remaining 15/15 positive evaluable set a selected easy-positive slice?
