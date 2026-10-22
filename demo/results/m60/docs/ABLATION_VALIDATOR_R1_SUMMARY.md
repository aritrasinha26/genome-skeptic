POST_HOC_DIAGNOSTIC = TRUE ; NOT PROSPECTIVE PERFORMANCE

# VALIDATOR COUNTERFACTUAL R1

POST_HOC_DIAGNOSTIC = TRUE ; NOT PROSPECTIVE PERFORMANCE

This is a post-hoc diagnostic on frozen, locked TargetMeasurements. It is **not**
prospective performance and must not be scored as a primary system result.

Patch iteration: **1** (stop; do not retune (a) or (b)).
Search / HMM / LLM calls: **none**. POSITION_LOCKS writes: **none**.

## Answer

The two documented defects account for **3 of 8** shared errors
on the 41 truth-evaluable cases. **0 of 33** frozen-correct calls flip.

| quantity | value |
| --- | --- |
| shared errors recovered | 3/8 |
| recovered positions | 13:M60_tetA_tetracycline_efflux_GCF_056269845.1;36:M60_tetA_tetracycline_efflux_GCF_058409085.1;48:M60_rpoB_RNAP_beta_GCF_055389225.1 |
| shared errors remaining | 5/8 |
| remaining positions | 14:M60_tetA_tetracycline_efflux_GCF_060343445.1;19:M60_tetA_tetracycline_efflux_GCF_054552735.1;37:M60_tetA_tetracycline_efflux_GCF_059878295.1;41:M60_tetA_tetracycline_efflux_GCF_056613625.1;44:M60_tetA_tetracycline_efflux_GCF_056539405.1 |
| frozen-correct flips | 0/33 |
| flipped positions | (none) |
| recovered via (a) family_identity_is_decisive | 2 |
| recovered via (b) classify_architecture | 1 |
| frozen GS-Det correct/n | 33/41 |
| counterfactual correct/n | 36/41 |
| CONSTANT_PER_TARGET correct/n | 34/41 |

## Patches applied (one iteration)

(a) `family_identity_is_decisive`: drop the "did not pass the family gate" substring
test; compare `_DECISIVE_IDENTITY_PRODUCT` (0.70) against identity × coverage.
Replay undoes `refine_weak_family_classification` only where that post-action
relabel is already stored, then re-applies it with the patched test.

(b) `classify_architecture`: if `reconstruction.hmm_coverage` and
`best_hmm.model_coverage` disagree by more than 0.2 on the same ORF, use
`best_hmm.model_coverage`. Re-run only when that disagreement is present, so
frozen fusion/partner evidence is not reconstructed.

## Shared-error case table

*POST_HOC_DIAGNOSTIC = TRUE ; NOT PROSPECTIVE PERFORMANCE*

| pos | case | truth | frozen | patched | recovered | defect |
| --- | --- | --- | --- | --- | --- | --- |
| 13 | M60_tetA_tetracycline_efflux_GCF_056269845.1 | POSITIVE | NEGATIVE | POSITIVE | YES | a |
| 14 | M60_tetA_tetracycline_efflux_GCF_060343445.1 | POSITIVE | NEGATIVE | NEGATIVE | NO | neither |
| 19 | M60_tetA_tetracycline_efflux_GCF_054552735.1 | POSITIVE | NEGATIVE | NEGATIVE | NO | neither |
| 36 | M60_tetA_tetracycline_efflux_GCF_058409085.1 | POSITIVE | NEGATIVE | POSITIVE | YES | a |
| 37 | M60_tetA_tetracycline_efflux_GCF_059878295.1 | POSITIVE | NEGATIVE | NEGATIVE | NO | neither |
| 41 | M60_tetA_tetracycline_efflux_GCF_056613625.1 | POSITIVE | NEGATIVE | NEGATIVE | NO | neither |
| 44 | M60_tetA_tetracycline_efflux_GCF_056539405.1 | POSITIVE | NEGATIVE | NEGATIVE | NO | neither |
| 48 | M60_rpoB_RNAP_beta_GCF_055389225.1 | POSITIVE | NEGATIVE | POSITIVE | YES | b |

## Class-decomposed metrics (counterfactual, with constant baseline)

*POST_HOC_DIAGNOSTIC = TRUE ; NOT PROSPECTIVE PERFORMANCE*

| target | system | correct/n | accuracy Wilson 95% | n_pos | sensitivity | n_neg | specificity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tetA_tetracycline_efflux | GS-Deterministic V4.1 frozen | 19/26 | 0.539–0.863 | 7 | 0.000000 | 19 | 1.000000 |
| tetA_tetracycline_efflux | GS validator counterfactual (patched a+b) | 21/26 | 0.621–0.915 | 7 | 0.285714 | 19 | 1.000000 |
| tetA_tetracycline_efflux | CONSTANT_PER_TARGET | 19/26 | 0.539–0.863 | 7 | 0.000000 | 19 | 1.000000 |
| tetA_tetracycline_efflux | CONSTANT_ALL_NEGATIVE | 19/26 | 0.539–0.863 | 7 | 0.000000 | 19 | 1.000000 |
| tetA_tetracycline_efflux | CONSTANT_ALL_POSITIVE | 7/26 | 0.137–0.461 | 7 | 1.000000 | 19 | 0.000000 |
| rpoB_RNAP_beta | GS-Deterministic V4.1 frozen | 14/15 | 0.702–0.988 | 15 | 0.933333 | 0 | n/a (no negatives) |
| rpoB_RNAP_beta | GS validator counterfactual (patched a+b) | 15/15 | 0.796–1.000 | 15 | 1.000000 | 0 | n/a (no negatives) |
| rpoB_RNAP_beta | CONSTANT_PER_TARGET | 15/15 | 0.796–1.000 | 15 | 1.000000 | 0 | n/a (no negatives) |
| rpoB_RNAP_beta | CONSTANT_ALL_NEGATIVE | 0/15 | 0.000–0.204 | 15 | 0.000000 | 0 | n/a (no negatives) |
| rpoB_RNAP_beta | CONSTANT_ALL_POSITIVE | 15/15 | 0.796–1.000 | 15 | 1.000000 | 0 | n/a (no negatives) |

## Constant baseline (41 evaluable)

*POST_HOC_DIAGNOSTIC = TRUE ; NOT PROSPECTIVE PERFORMANCE*

| baseline / comparison | correct/n | b | c | net | McNemar |
| --- | --- | --- | --- | --- | --- |
| CONSTANT_PER_TARGET | 34/41 |  |  |  |  |
| CONSTANT_ALL_NEGATIVE | 19/41 |  |  |  |  |
| CONSTANT_ALL_POSITIVE | 22/41 |  |  |  |  |
| mcnemar_counterfactual_vs_CONSTANT_PER_TARGET | 36/41 | 0 | 2 | 2 | exact two-sided McNemar / binomial P=0.5 on B+C=2 |
| mcnemar_frozen_gs_det_vs_CONSTANT_PER_TARGET | 33/41 | 1 | 0 | -1 | exact two-sided McNemar / binomial P=1 on B+C=1 |

Frozen GS-Det vs CONSTANT_PER_TARGET uses the locked endpoints. The counterfactual
row is the patched validator replay and is not a new system arm.

## Inputs

Locked family_evidence JSON under `manuscript_benchmark/RUNS/position_*/**/family/TARGET/family_evidence.json`
for GS-Deterministic, GS-Agentic, and GS-Exhaustive (180 files). Truth from
`TRUTH_M60/M60_EXTERNAL_TRUTH_FINAL_LOCKED.json`. Locked endpoints from
`M60_GS_*_LOCKED.json`. Frozen validator source was not modified.
