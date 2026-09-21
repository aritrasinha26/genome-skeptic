# M60 final results

One-shot unblind of GENOME_SKEPTIC_V4_1_MANUSCRIPT on the frozen M60 cohort.
Numbers below are the manuscript result. No post-unblind development, threshold
change, case replacement, or prediction regeneration was performed.

## 1. Cohort and independent truth

The locked cohort contains 60 genome-target cases (30 tetA, 30 rpoB; 30 routine,
30 challenge). Independent truth was assigned and human-reviewed before this
unblind.

Frozen final truth distribution:

- Total: 60
- tetA: 7 POSITIVE, 19 NEGATIVE, 4 TRUTH_UNCERTAIN
- rpoB: 15 POSITIVE, 0 NEGATIVE, 15 TRUTH_UNCERTAIN

Truth-evaluable primary denominator: **41 / 60**.
TRUTH_UNCERTAIN cases (n = 19) remain in case-level output and completion
statistics and are excluded from primary accuracy, McNemar, and bootstrap
tables.

Unresolved or failed-closed predictions count as incorrect when truth is
POSITIVE or NEGATIVE.

## 2. Overall performance

Truth-evaluable N = 41.

- Conventional: 20 / 41 (0.488; Wilson 95% CI 0.343–0.635); completion 60/60
- Specialist comparator (AMRFinderPlus on tetA; NCBI RefSeq/PGAP on rpoB): 34 / 41 (0.829; Wilson 95% CI 0.687–0.915); completion 60/60
- GS-Deterministic V4.1: 33 / 41 (0.805; Wilson 95% CI 0.660–0.898); completion 60/60
- GS-Agentic V4.1: 33 / 41 (0.805; Wilson 95% CI 0.660–0.898); completion 60/60
- GS-Exhaustive V4.1: 33 / 41 (0.805; Wilson 95% CI 0.660–0.898); completion 60/60

Primary comparison is GS-Agentic V4.1 versus GS-Deterministic V4.1.

Absolute accuracy difference (Agent − Deterministic): **+0.0 percentage points**.
Paired bootstrap 95% CI (10,000 resamples, seed 20260920): **0.000–0.000**.

## 3. Agent vs deterministic paired comparison

Among 41 evaluable cases:

- A (both correct): 33
- B (Det correct, Agent wrong): 0
- C (Det wrong, Agent correct): 0
- D (both wrong): 8

DET ERRORS CORRECTED BY AGENT = 0
DET CORRECT CALLS DEGRADED BY AGENT = 0
NET CORRECTIONS = 0

McNemar not applicable (B+C = 0).

Discordant cases are listed in `M60_AGENT_VS_DETERMINISTIC.csv`.

GS-Agentic did not outperform GS-Deterministic on exact endpoint accuracy in this prospective blinded benchmark (difference +0.0 percentage points).


## 4. Agent vs exhaustive comparison

- GS-Agentic accuracy: 33 / 41 (0.805)
- GS-Exhaustive accuracy: 33 / 41 (0.805)
- Absolute difference (Agent − Exhaustive): +0.0 percentage points
- Paired bootstrap 95% CI: 0.000–0.000
- Exhaustive wrong → Agent correct: 0
- Exhaustive correct → Agent wrong: 0

No equivalence margin was preregistered. Statistical equivalence is not claimed.
Agentic performance differed from Exhaustive by 0.0 percentage points, while Agent used 67.7% fewer follow-up analyses.

## 5. Established comparator performance

Specialist tools were not pooled into one biological method. AMRFinderPlus 4.2.7
(database 2026-08-07.1) is the tetA specialist. NCBI RefSeq/PGAP annotation is
the rpoB specialist. The overall specialist row above is a composite of those
two frozen converters.

tetA evaluable n = 26:

- Conventional: 20 / 26 (0.769; Wilson 95% CI 0.579–0.890)
- Specialist comparator: 19 / 26 (0.731; Wilson 95% CI 0.539–0.863)
- GS-Deterministic V4.1: 19 / 26 (0.731; Wilson 95% CI 0.539–0.863)
- GS-Agentic V4.1: 19 / 26 (0.731; Wilson 95% CI 0.539–0.863)
- GS-Exhaustive V4.1: 19 / 26 (0.731; Wilson 95% CI 0.539–0.863)

rpoB evaluable n = 15:

- Conventional: 0 / 15 (0.000; Wilson 95% CI 0.000–0.204)
- Specialist comparator: 15 / 15 (1.000; Wilson 95% CI 0.796–1.000)
- GS-Deterministic V4.1: 14 / 15 (0.933; Wilson 95% CI 0.702–0.988)
- GS-Agentic V4.1: 14 / 15 (0.933; Wilson 95% CI 0.702–0.988)
- GS-Exhaustive V4.1: 14 / 15 (0.933; Wilson 95% CI 0.702–0.988)


## 6. Target-specific performance

### tetA (evaluable n = 26; 7 POSITIVE, 19 NEGATIVE)

GS-Agentic: 19 / 26.
Sensitivity 0 / 7; specificity 19 / 19; PPV undefined (0 predicted positives); NPV 19 / 26.

Agent vs Det on tetA: corrections 0, degradations 0, net 0.

Full per-system sensitivity/specificity/PPV/NPV with denominators are in
`M60_TARGET_SPECIFIC_RESULTS.csv`.

### rpoB (evaluable n = 15; all POSITIVE)

GS-Agentic: 14 / 15 (sensitivity / recall 14 / 15).

Specificity could not be estimated for rpoB because no independently resolved
negative cases were present.

Agent vs Det on rpoB: corrections 0, degradations 0, net 0.

## 7. Routine vs challenge performance

Secondary analysis on truth-evaluable cases.

- Routine evaluable N = 21; GS-Agentic 15 / 21; corrections 0, degradations 0, net 0
- Challenge evaluable N = 20; GS-Agentic 18 / 20; corrections 0, degradations 0, net 0

Per-system stratum accuracies are in `M60_STRATUM_RESULTS.csv`.

## 8. Computational efficiency

All 60 cases (completion statistics), not the accuracy denominator.

GS-Agentic:

- follow-up actions: total 61, mean 1.017, median 1.0, IQR 1.0–1.0
- runtime seconds: total 12090.8, median 206.7, IQR 163.7–238.5
- completion: 60 / 60

GS-Exhaustive:

- follow-up actions: total 189, mean 3.150, median 3.0, IQR 1.8–5.0
- runtime seconds: total 1421.3, median 19.4, IQR 17.1–25.7
- completion: 60 / 60

FOLLOW-UP ACTION REDUCTION = 67.7%
Agent / Exhaustive median runtime ratio = 10.63

Action efficiency and wall-clock efficiency are reported separately. Agent
wall-clock includes local LLM inference (qwen3:4b). Fewer follow-up tool calls
did not produce a shorter wall-clock runtime.

## 9. Agent behavior

Across all 60 Agentic cases:

- planner action frequencies: competitive_family=30, inspect_contig_edges_for_target=15, inspect_hit_contig_contamination=15
- critic challenge frequency: 1
- critic second-action frequency: 1
- INFORMATIVE actions: 38
- NO_NEW_INFORMATION actions: 23
- UNAVAILABLE actions: 0
- FAILED actions: 0
- m0 ≠ m_final: 60
- Agent endpoint ≠ GS-Det endpoint: 0
- Agent endpoint == GS-Det endpoint: 60

On 41 evaluable cases, decision changes vs Deterministic: BENEFICIAL 0, HARMFUL 0, NEUTRAL 41.

## 10. Error analysis

Post-hoc descriptive taxonomy only; not used for tuning.

GS-Agentic errors on evaluable cases: 8
GS-Deterministic errors on evaluable cases: 8

See `M60_ERROR_TAXONOMY.csv`.

## 11. Limitations

- Primary accuracy uses 41 of 60 cases because 19 remained TRUTH_UNCERTAIN after independent adjudication and human review.
- rpoB has no independently resolved NEGATIVE truth, so rpoB specificity cannot be estimated.
- Specialist performance is a composite of two different tools (AMRFinderPlus for tetA; RefSeq/PGAP for rpoB).
- Wilson intervals and the paired bootstrap describe this locked 41-case denominator; they were not used to change the frozen protocol.
- Agent runtime includes local LLM latency and is not a proxy for follow-up-action count.
- Error taxonomy is post-hoc and must not be read as a licence to retune V4.1.

Final truth SHA256: `a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9`
Prediction lock SHA256: `5317b33fa554f81855fa6c68854ad732c5f5127fc0ad41f224fede9159a90791`
