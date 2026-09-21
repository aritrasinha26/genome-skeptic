# Primary M60 results

**PROSPECTIVE PRIMARY VALIDATION.** Numbers verified from `manuscript_benchmark/RESULTS_M60/` against `M60_PHASE4_STOP.json` and the CSVs named below. Unblind timestamp `2026-09-21T10:17:58.831848+00:00`.

No post-unblind development, threshold change, case replacement, or prediction regeneration is claimed in `M60_FINAL_RESULTS.md`.

---

## Denominator

- Cohort: 60
- Final truth: tetA 7 POS / 19 NEG / 4 UNCERTAIN; rpoB 15 POS / 0 NEG / 15 UNCERTAIN
- **Truth-evaluable: 41 / 60**
- TRUTH_UNCERTAIN n=19 excluded from accuracy, McNemar, bootstrap
- Completion: 60 / 60 for all listed systems

Source: `M60_FINAL_RESULTS.md`, `M60_PHASE4_STOP.json`, `M60_UNCERTAIN_CASES.csv`.

---

## Overall exact-endpoint accuracy (N = 41)

Verified `M60_FINAL_SYSTEM_SUMMARY.csv`:

| System | Correct | Accuracy | Wilson 95% CI |
|---|---:|---:|---|
| Conventional | **20 / 41** | 0.488 | 0.343–0.635 |
| Specialist comparator (composite) | **34 / 41** | 0.829 | 0.687–0.915 |
| GS-Deterministic V4.1 | **33 / 41** | 0.805 | 0.660–0.898 |
| GS-Agentic V4.1 (Qwen) | **33 / 41** | 0.805 | 0.660–0.898 |
| GS-Exhaustive V4.1 | **33 / 41** | 0.805 | 0.660–0.898 |

MATCH to expected headline: **YES**.

---

## GS-Agent vs GS-Det

Verified `M60_AGENT_VS_DETERMINISTIC.csv`:

| Metric | Value |
|---|---|
| Accuracy difference (Agent − Det) | **0.000** |
| Paired bootstrap 95% CI (10,000; seed 20260920) | **0.000–0.000** |
| A both correct | 33 |
| B Det correct, Agent wrong | 0 |
| C Det wrong, Agent correct | 0 |
| D both wrong | 8 |
| Corrections | **0** |
| Degradations | **0** |
| Net | **0** |
| McNemar | **NA** (B+C=0) |

Agent vs Exhaustive: same 33/41, difference 0.000, CI 0.000–0.000 (`M60_AGENT_VS_EXHAUSTIVE.csv`). **Statistical equivalence is not claimed** (`M60_FINAL_RESULTS.md`).

---

## Target-specific (Agent / all GS arms identical)

Verified `M60_TARGET_SPECIFIC_RESULTS.csv`:

### tetA evaluable n = 26 (7 POSITIVE, 19 NEGATIVE)

| System | Correct | Sensitivity | Specificity |
|---|---:|---|---|
| Conventional | 20 / 26 | 1 / 7 | 19 / 19 |
| Specialist (AMRFinderPlus) | 19 / 26 | **0 / 7** | 19 / 19 |
| GS-Det / Agent / Exhaustive | **19 / 26** | **0 / 7** | 19 / 19 |

GS-Agentic tetA: 19 / 26. PPV undefined (0 predicted positives). NPV 19 / 26.

**All 7 resolved tetA positives are false negatives for every GS arm and for AMRFinderPlus.** Conventional recovered 1 / 7.

### rpoB evaluable n = 15 (all POSITIVE)

| System | Correct | Sensitivity | Specificity |
|---|---:|---|---|
| Conventional | 0 / 15 | 0 / 15 | NA |
| Specialist (PGAP) | 15 / 15 | 15 / 15 | NA |
| GS-Det / Agent / Exhaustive | **14 / 15** | 14 / 15 | **NA — no negative truth** |

GS-Agentic rpoB: **14 / 15**.

---

## Routine vs challenge (secondary)

Verified `M60_STRATUM_RESULTS.csv`:

| Stratum | Evaluable N | GS-Agentic | Agent vs Det net |
|---|---:|---|---|
| Routine | 21 | **15 / 21** | 0 |
| Challenge | 20 | **18 / 20** | 0 |

MATCH expected: YES.

---

## Efficiency (all 60 cases, not the 41)

Verified `M60_EFFICIENCY_RESULTS.csv`:

| | GS-Agentic Qwen | GS-Exhaustive |
|---|---:|---:|
| Follow-up actions total | **61** | **189** |
| Mean / median actions | 1.017 / 1.0 | 3.15 / 3.0 |
| Follow-up reduction | **67.7%** | — |
| Median runtime (s) | **206.6875** | **19.4455** |
| Runtime IQR (s) | 163.7–238.5 | 17.1–25.7 |
| Total runtime (s) | 12090.8 | 1421.3 |
| Agent / Exhaustive median runtime ratio | **10.63** | — |
| Completion | 60 / 60 | 60 / 60 |

MATCH expected medians 206.7 s and 19.4 s: **YES**.

Fewer follow-up tool calls did **not** produce shorter wall-clock time. Agent runtime includes local `qwen3:4b` inference.

---

## Agent behaviour (60 cases)

From `M60_FINAL_RESULTS.md` §9:

- Planner actions: `competitive_family=30`, `inspect_contig_edges_for_target=15`, `inspect_hit_contig_contamination=15`
- Critic challenge frequency: 1
- Critic second-action frequency: 1
- INFORMATIVE 38 / NO_NEW_INFORMATION 23 / UNAVAILABLE 0 / FAILED 0
- m0 ≠ m_final: 60
- Agent endpoint ≠ GS-Det endpoint: **0 / 60**
- Agent endpoint == GS-Det: 60

On 41 evaluable cases, decision changes vs Deterministic: BENEFICIAL 0, HARMFUL 0, NEUTRAL 41.

The agent **did run follow-ups** (measurements changed) but **never changed the scored endpoint** versus Det.

---

## Case-level and figures

| Artifact | Path |
|---|---|
| Case-level scored table | `manuscript_benchmark/RESULTS_M60/M60_FINAL_CASE_LEVEL_RESULTS.csv` |
| System summary | `M60_FINAL_SYSTEM_SUMMARY.csv` |
| Target / stratum / efficiency | CSVs above |
| Error taxonomy (descriptive, post-unblind) | `M60_ERROR_TAXONOMY.csv` |
| Agent mechanisms | `M60_AGENT_MECHANISMS.csv` |
| Narrative | `M60_FINAL_RESULTS.md` |
| Integrity | `M60_FINAL_INTEGRITY_STATEMENT.md` |
| Figures 1–6 | `FIGURE1_overall_accuracy.png` … `FIGURE6_runtime.png` (+ PDF) |
| Position locks | `manuscript_benchmark/POSITION_LOCKS/position_XX/` |
| Aggregate prediction locks | `M60_GS_*_LOCKED.json`, `M60_CONVENTIONAL_LOCKED.json`, `M60_SPECIALIST_COMPARATORS_LOCKED.json` |
| Statistics script | `scripts/score_m60_phase4.py` |

Runtime logs under `manuscript_benchmark/RUN_LOGS/` are **gitignored**. Position lock JSON is the durable per-case prediction record.

---

## Specialist pooling caution

Specialist 34/41 = AMRFinder tetA 19/26 + PGAP rpoB 15/15.

Do **not** treat 33/41 vs 34/41 as a single-tool comparison. tetA specialist is **worse than conventional** on this endpoint (19 vs 20 / 26) and tied with GS (19/26), all with tetA sensitivity 0 or 1 / 7.
