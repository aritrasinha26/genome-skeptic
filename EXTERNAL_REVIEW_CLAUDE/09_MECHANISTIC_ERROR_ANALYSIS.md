# Mechanistic error analysis

```
POST-HOC
NOT PRIMARY VALIDATION
MECHANISTIC ERROR ANALYSIS STATUS: COMPLETE
```

Location: `manuscript_benchmark/POSTHOC_ERROR_ANALYSIS/`

Manifest: `POSTHOC_ERROR_ANALYSIS_MANIFEST.json`  
`created_utc`: `2026-09-21T12:18:50.807284+00:00`  
Flags: `POST_HOC_ONLY: true`; scientific code / thresholds / predictions / D20 / cases / V4.2 / uncertain-truth reinterpretation: **NO**.

This package does **not** invent results. The following is a **pointer and count extract** from the completed forensic files. Claude must verify case by case.

---

## Scope

Eight truth-evaluable M60 cases on which GS-Deterministic, GS-Agentic (Qwen), GS-Exhaustive, **and** Sol all disagreed with independent truth.

7 tetA + 1 rpoB.

Identity check in manifest: `same_eight_wrong_for_qwen_exhaustive_sol: true`.

All eight independent-truth labels are **POSITIVE**. Frozen predictions are **NEGATIVE**.

---

## Exact counts (from manifest + `POSTHOC_ROOT_CAUSE_SUMMARY.csv`)

| Quantity | Count |
|---|---|
| Shared errors | **8 / 8** (positions 13, 14, 19, 36, 37, 41, 44, 48) |
| tetA | 7 |
| rpoB | 1 |
| Primary root cause `VALIDATOR_DECISION_LIMIT` | **8** |
| INSTRUMENTATION_FAILURE | 0 |
| ACTION_REGISTRY_OR_ELIGIBILITY_LIMIT | 0 |
| EVIDENCE_REPRESENTATION_FAILURE (primary) | 0 (position 48 recorded as *contributing* coverage mismatch) |
| BIOLOGICAL_NONDISCRIMINATION | 0 |
| ASSEMBLY_INFORMATION_LIMIT | 0 |
| Correct evidence recovered by any frozen action | **8 / 8** |
| Correct evidence reached TargetMeasurements | **8 / 8** |
| Theoretically fixable by a different LLM action alone | **0 / 8** |
| Requiring new scientific instrument | **0 / 8** |
| Requiring validator or representation change | **8 / 8** |
| Qwen vs Sol different investigation path | **8 / 8** |
| Different final endpoint | **0 / 8** |

---

## Case-level (from `POSTHOC_ERROR_CASES.csv`)

| Pos | Target | Stratum | Truth | Pred | Primary rule | Different LLM action could fix? | Minimal conceptual rescue |
|---:|---|---|---|---|---|---|---|
| 13 | tetA | routine | POS | NEG | refine_weak: `target_family_supported`→`ambiguous_family`; family_detects_orthologue veto | NO | VALIDATOR_RULE_CHANGE_REQUIRED |
| 14 | tetA | routine | POS | NEG | same | NO | VALIDATOR_RULE_CHANGE_REQUIRED |
| 19 | tetA | routine | POS | NEG | same | NO | VALIDATOR_RULE_CHANGE_REQUIRED |
| 36 | tetA | routine | POS | NEG | same | NO | VALIDATOR_RULE_CHANGE_REQUIRED |
| 37 | tetA | routine | POS | NEG | same; extra Sol/Exhaustive protein searches increased n_loci, endpoint unchanged | NO | VALIDATOR_RULE_CHANGE_REQUIRED |
| 41 | tetA | challenge | POS | NEG | same | NO | VALIDATOR_RULE_CHANGE_REQUIRED |
| 44 | tetA | challenge | POS | NEG | same | NO | VALIDATOR_RULE_CHANGE_REQUIRED |
| 48 | rpoB | routine | POS | NEG | `architecture=domain_only` (recon hmm_cov≈0.40) despite best_hmm mcov≈0.88 score 1610.5 | NO | VALIDATOR_RULE_CHANGE_REQUIRED |

Authors’ confidence column: HIGH for all eight.

These **are** the seven resolved tetA positives plus the single rpoB GS miss. tetA sensitivity 0/7 is this residual.

---

## Authors’ post-hoc causal sentence

From `POSTHOC_MANUSCRIPT_INTERPRETATION.md`:

> In the shared errors examined here, prediction failure arose primarily from limitations in frozen family-state decision rules rather than from the choice of LLM-directed follow-up analysis.

Supporting observations they record:

- Frozen initial core reconstructed a locus overlapping the independent-truth candidate
- Family measurements (HMM, members, tetA competitive scores favouring tetA) were stored
- `discriminate_family` reported `target_family_supported` on all seven tetA errors **before** refine_weak
- Sol/Exhaustive added hits but did not change architecture, competitive classification after relabel, or polarity
- Exhaustive executed every eligible registered follow-up and remained wrong on the same eight
- Sol chose different first actions on all eight and remained wrong

**Claude must verify this case by case against `_extracted/` JSON and frozen `family_evidence` blobs. Do not assume it is true merely because Sol did not change endpoints.**

Alternative explanations to consider:

- Endpoint/truth-definition mismatch (truth POSITIVE using sequence/HMM routes; GS requires decisive identity-product / non-domain_only architecture)
- Evidence-state compression (numeric support exists but is stored as `ambiguous_family`)
- Reconstruction coverage using a different HMM-coverage field than `best_hmm.model_coverage` (rpoB)
- Independent truth too liberal on divergent tetA (identity as low as ~0.25 in the case table)

The analysis **does not** recalculate accuracy under a hypothetical rescue and **must not** be used to retune V4.1.

---

## Files

| File | Role |
|---|---|
| `POSTHOC_ERROR_CASES.csv` | Case-level forensic table |
| `POSTHOC_ERROR_DETAILED.md` | Narrative forensics |
| `POSTHOC_ROOT_CAUSE_SUMMARY.csv` | Category counts |
| `POSTHOC_MODEL_INVARIANCE.md` | Policy divergence vs endpoint invariance |
| `POSTHOC_MANUSCRIPT_INTERPRETATION.md` | Conservative wording |
| `POSTHOC_ERROR_ANALYSIS_MANIFEST.json` | Manifest + hashes |
| `_extracted/*.json` | Read-only extracts from frozen runs (not new predictions) |
