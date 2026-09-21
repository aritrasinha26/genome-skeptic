# Statistical methods

Primary script: `scripts/score_m60_phase4.py`  
Pre-registered seed in protocol: `20260920`.

---

## Wilson 95% confidence intervals

`wilson_ci(k, n, z=1.959963984540054)` in `score_m60_phase4.py`.

Applied to binomial exact-endpoint accuracy on the **evaluable** denominator for each system, and to target-specific / stratum tables.

---

## Paired bootstrap

- Function: `paired_bootstrap_diff(a, b)`
- `BOOTSTRAP_N = 10000`
- `BOOTSTRAP_SEED = 20260920`
- Percentile 2.5 / 97.5 of resampled accuracy differences

Used for Agent vs Det and Agent vs Exhaustive (and Sol vs Qwen in the post-hoc Sol scorer).

On M60 Agent vs Det, every paired resample is 0 because there are **no discordant pairs**. CI **0.000–0.000** is therefore **mechanical**, not an estimate of a small non-zero effect.

---

## Exact McNemar

Discordant pairs:

- B: Det correct, Agent wrong
- C: Det wrong, Agent correct

Exact two-sided test: `scipy.stats.binomtest(len(C), n=len(B)+len(C), p=0.5)` when B+C > 0.

**Why McNemar is NA for Agent vs Det:** B+C = 0. There is no binomial trial.

Same for Agent vs Exhaustive and Sol vs Qwen.

---

## Handling of uncertain truth

Evaluable = truth in {POSITIVE, NEGATIVE}.

`TRUTH_UNCERTAIN` excluded from accuracy, McNemar, bootstrap.

Unresolved/failed predictions vs resolved truth count as incorrect.

---

## Target-specific and stratum denominators

| Slice | Evaluable N | Source |
|---|---:|---|
| Pooled | 41 | all resolved |
| tetA | 26 | 7 POS + 19 NEG |
| rpoB | 15 | 15 POS + 0 NEG |
| Routine | 21 | secondary |
| Challenge | 20 | secondary |

Sensitivity / specificity / PPV / NPV: `M60_TARGET_SPECIFIC_RESULTS.csv`.

rpoB specificity field: `NA_no_negative_truth`.

---

## Do not pool endpoints as if specialists were identical

AMRFinderPlus is the tetA specialist. PGAP is the rpoB specialist. The overall specialist row is a **composite converter**.

**Ask specifically:** Is pooled 41-case accuracy scientifically reasonable given two distinct endpoints?

Disaggregated tetA 19/26 vs rpoB 14/15 are different biological questions. Pooled 33/41 weights tetA more (26 vs 15) and mixes a zero-sensitivity tetA problem with high rpoB recall.

---

## Sensitivity analyses that do **not** change primary results

**Do not alter the primary preregistered analysis.** The following can be recommended or computed **as labelled post-hoc / secondary** on existing frozen data:

1. Best/worst-case bounds for the 19 `TRUTH_UNCERTAIN` cases (Agent vs Det still 0 discordant among the 41; uncertain cases could in principle create discordance **if** one scored them — they were not scored).
2. Target-specific rather than pooled interpretation (already computed; should be **primary narrative**).
3. Sensitivity excluding the one human-changed truth (position 34 tetA UNCERTAIN→NEGATIVE). If excluded, tetA evaluable becomes 25 (7 POS + 18 NEG) unless that case is treated as uncertain again.
4. Confidence intervals for **accuracy differences** — already degenerate at 0 for Agent vs Det.
5. Action-count **distributions**, not means only (`M60_EFFICIENCY_RESULTS.csv` has median/IQR).
6. Runtime distributions (IQR reported; raw per-case times in position locks / efficiency case fields).
7. Per-case concordance matrix (Agent=Det=Exhaustive=Sol on all 60 endpoints).
8. Results stratified routine/challenge (already secondary CSVs).
9. Positive/negative class performance (tetA 0/7 vs 19/19 is the critical table).
10. Qualitative analysis of 19 unresolved truth cases (`M60_UNCERTAIN_CASES.csv` + gitignored HUMAN_REVIEW packets).
11. Specialist comparators **by endpoint** (already in target-specific CSV).

Do **not** calculate new analyses merely to improve the result unless clearly labelled post-hoc.

---

## What the primary script does not do

- Equivalence tests (TOST / margin)
- Multiple-comparison adjustment (not needed for a single primary Agent vs Det contrast that is exactly 0)
- Mixed-effects / clustering by genus (60 unique genera)
- Re-scoring under counterfactual validator rules (explicitly forbidden)
