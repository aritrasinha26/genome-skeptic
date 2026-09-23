# M60 REANALYSIS R1

Locked predictions re-scored against locked truth. No arm was re-executed.

## Control totals (41 locked-evaluable cases)

| system | correct/n |
| --- | --- |
| Conventional | 20/41 |
| Specialist comparator | 34/41 |
| GS-Deterministic V4.1 | 33/41 |
| GS-Agentic V4.1 | 33/41 |
| GS-Exhaustive V4.1 | 33/41 |

## A. Class-decomposed performance

### tetA_tetracycline_efflux

| system | correct/n | accuracy Wilson 95% | n_pos | sensitivity | sens. Wilson 95% | n_neg | specificity | spec. Wilson 95% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Conventional | 20/26 | 0.579–0.890 | 7 | 0.142857 | 0.026–0.513 | 19 | 1.000000 | 0.832–1.000 |
| Specialist comparator | 19/26 | 0.539–0.863 | 7 | 0.000000 | 0.000–0.354 | 19 | 1.000000 | 0.832–1.000 |
| GS-Deterministic V4.1 | 19/26 | 0.539–0.863 | 7 | 0.000000 | 0.000–0.354 | 19 | 1.000000 | 0.832–1.000 |
| GS-Agentic V4.1 | 19/26 | 0.539–0.863 | 7 | 0.000000 | 0.000–0.354 | 19 | 1.000000 | 0.832–1.000 |
| GS-Exhaustive V4.1 | 19/26 | 0.539–0.863 | 7 | 0.000000 | 0.000–0.354 | 19 | 1.000000 | 0.832–1.000 |

### rpoB_RNAP_beta

| system | correct/n | accuracy Wilson 95% | n_pos | sensitivity | sens. Wilson 95% | n_neg | specificity | spec. Wilson 95% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Conventional | 0/15 | 0.000–0.204 | 15 | 0.000000 | 0.000–0.204 | 0 | n/a (no negatives) | n/a (no negatives) |
| Specialist comparator | 15/15 | 0.796–1.000 | 15 | 1.000000 | 0.796–1.000 | 0 | n/a (no negatives) | n/a (no negatives) |
| GS-Deterministic V4.1 | 14/15 | 0.702–0.988 | 15 | 0.933333 | 0.702–0.988 | 0 | n/a (no negatives) | n/a (no negatives) |
| GS-Agentic V4.1 | 14/15 | 0.702–0.988 | 15 | 0.933333 | 0.702–0.988 | 0 | n/a (no negatives) | n/a (no negatives) |
| GS-Exhaustive V4.1 | 14/15 | 0.702–0.988 | 15 | 0.933333 | 0.702–0.988 | 0 | n/a (no negatives) | n/a (no negatives) |

## B. Constant-baseline comparison

| baseline | correct/n | accuracy Wilson 95% |
| --- | --- | --- |
| CONSTANT_PER_TARGET | 34/41 | 0.687–0.915 |
| CONSTANT_ALL_NEGATIVE | 19/41 | 0.321–0.613 |
| CONSTANT_ALL_POSITIVE | 22/41 | 0.387–0.679 |

Paired 2x2 of each GS arm versus CONSTANT_PER_TARGET on the 41 evaluable cases.
b = CONSTANT_PER_TARGET correct and GS incorrect; c = CONSTANT_PER_TARGET incorrect and GS correct; net = c − b.

| GS arm | b | c | net | McNemar |
| --- | --- | --- | --- | --- |
| GS-Deterministic V4.1 | 1 | 0 | -1 | exact two-sided McNemar / binomial P=1 on B+C=1 |
| GS-Agentic V4.1 | 1 | 0 | -1 | exact two-sided McNemar / binomial P=1 on B+C=1 |
| GS-Exhaustive V4.1 | 1 | 0 | -1 | exact two-sided McNemar / binomial P=1 on B+C=1 |

## C. Prediction-degeneracy audit (all 60 cases)

| system | target | n | POSITIVE | NEGATIVE | UNRESOLVED | n distinct labels | labels |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Conventional | tetA_tetracycline_efflux | 30 | 1 | 29 | 0 | 2 | NEGATIVE;POSITIVE |
| Conventional | rpoB_RNAP_beta | 30 | 0 | 30 | 0 | 1 | NEGATIVE |
| Specialist comparator | tetA_tetracycline_efflux | 30 | 0 | 30 | 0 | 1 | NEGATIVE |
| Specialist comparator | rpoB_RNAP_beta | 30 | 29 | 1 | 0 | 2 | NEGATIVE;POSITIVE |
| GS-Deterministic V4.1 | tetA_tetracycline_efflux | 30 | 0 | 30 | 0 | 1 | NEGATIVE |
| GS-Deterministic V4.1 | rpoB_RNAP_beta | 30 | 29 | 1 | 0 | 2 | NEGATIVE;POSITIVE |
| GS-Agentic V4.1 | tetA_tetracycline_efflux | 30 | 0 | 30 | 0 | 1 | NEGATIVE |
| GS-Agentic V4.1 | rpoB_RNAP_beta | 30 | 29 | 1 | 0 | 2 | NEGATIVE;POSITIVE |
| GS-Exhaustive V4.1 | tetA_tetracycline_efflux | 30 | 0 | 30 | 0 | 1 | NEGATIVE |
| GS-Exhaustive V4.1 | rpoB_RNAP_beta | 30 | 29 | 1 | 0 | 2 | NEGATIVE;POSITIVE |

## D. Uncertain-truth bounds

| system | scenario | k/n | Wilson 95% | assumption |
| --- | --- | --- | --- | --- |
| Conventional | best_uncertain_counted_correct | 39/60 | 0.524–0.758 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted correct |
| Conventional | worst_uncertain_counted_incorrect | 20/60 | 0.227–0.459 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted incorrect |
| Conventional | rpob_uncertain_assumed_POSITIVE | 20/56 | 0.245–0.488 | ASSUMPTION (not a truth-file change): 15 rpoB TRUTH_UNCERTAIN scored as if truth=POSITIVE; 4 tetA TRUTH_UNCERTAIN remain excluded; denominator 56 = 41 locked-evaluable + 15 |
| Specialist comparator | best_uncertain_counted_correct | 53/60 | 0.778–0.942 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted correct |
| Specialist comparator | worst_uncertain_counted_incorrect | 34/60 | 0.441–0.684 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted incorrect |
| Specialist comparator | rpob_uncertain_assumed_POSITIVE | 48/56 | 0.743–0.926 | ASSUMPTION (not a truth-file change): 15 rpoB TRUTH_UNCERTAIN scored as if truth=POSITIVE; 4 tetA TRUTH_UNCERTAIN remain excluded; denominator 56 = 41 locked-evaluable + 15 |
| GS-Deterministic V4.1 | best_uncertain_counted_correct | 52/60 | 0.758–0.931 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted correct |
| GS-Deterministic V4.1 | worst_uncertain_counted_incorrect | 33/60 | 0.425–0.669 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted incorrect |
| GS-Deterministic V4.1 | rpob_uncertain_assumed_POSITIVE | 48/56 | 0.743–0.926 | ASSUMPTION (not a truth-file change): 15 rpoB TRUTH_UNCERTAIN scored as if truth=POSITIVE; 4 tetA TRUTH_UNCERTAIN remain excluded; denominator 56 = 41 locked-evaluable + 15 |
| GS-Agentic V4.1 | best_uncertain_counted_correct | 52/60 | 0.758–0.931 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted correct |
| GS-Agentic V4.1 | worst_uncertain_counted_incorrect | 33/60 | 0.425–0.669 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted incorrect |
| GS-Agentic V4.1 | rpob_uncertain_assumed_POSITIVE | 48/56 | 0.743–0.926 | ASSUMPTION (not a truth-file change): 15 rpoB TRUTH_UNCERTAIN scored as if truth=POSITIVE; 4 tetA TRUTH_UNCERTAIN remain excluded; denominator 56 = 41 locked-evaluable + 15 |
| GS-Exhaustive V4.1 | best_uncertain_counted_correct | 52/60 | 0.758–0.931 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted correct |
| GS-Exhaustive V4.1 | worst_uncertain_counted_incorrect | 33/60 | 0.425–0.669 | 41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted incorrect |
| GS-Exhaustive V4.1 | rpob_uncertain_assumed_POSITIVE | 48/56 | 0.743–0.926 | ASSUMPTION (not a truth-file change): 15 rpoB TRUTH_UNCERTAIN scored as if truth=POSITIVE; 4 tetA TRUTH_UNCERTAIN remain excluded; denominator 56 = 41 locked-evaluable + 15 |

## E. Leave-position-34-out (40 evaluable cases)

Position 34 = tetA GCF_054953385.1, locked truth NEGATIVE.

| system | correct/n | accuracy Wilson 95% |
| --- | --- | --- |
| Conventional | 19/40 | 0.329–0.625 |
| Specialist comparator | 33/40 | 0.681–0.913 |
| GS-Deterministic V4.1 | 32/40 | 0.652–0.895 |
| GS-Agentic V4.1 | 32/40 | 0.652–0.895 |
| GS-Exhaustive V4.1 | 32/40 | 0.652–0.895 |

| target | system | correct/n | n_pos | sensitivity | n_neg | specificity |
| --- | --- | --- | --- | --- | --- | --- |
| tetA_tetracycline_efflux | Conventional | 19/25 | 7 | 0.14285714285714285 | 18 | 1.0 |
| tetA_tetracycline_efflux | Specialist comparator | 18/25 | 7 | 0.0 | 18 | 1.0 |
| tetA_tetracycline_efflux | GS-Deterministic V4.1 | 18/25 | 7 | 0.0 | 18 | 1.0 |
| tetA_tetracycline_efflux | GS-Agentic V4.1 | 18/25 | 7 | 0.0 | 18 | 1.0 |
| tetA_tetracycline_efflux | GS-Exhaustive V4.1 | 18/25 | 7 | 0.0 | 18 | 1.0 |
| rpoB_RNAP_beta | Conventional | 0/15 | 15 | 0.0 | 0 | n/a (no negatives) |
| rpoB_RNAP_beta | Specialist comparator | 15/15 | 15 | 1.0 | 0 | n/a (no negatives) |
| rpoB_RNAP_beta | GS-Deterministic V4.1 | 14/15 | 15 | 0.9333333333333333 | 0 | n/a (no negatives) |
| rpoB_RNAP_beta | GS-Agentic V4.1 | 14/15 | 15 | 0.9333333333333333 | 0 | n/a (no negatives) |
| rpoB_RNAP_beta | GS-Exhaustive V4.1 | 14/15 | 15 | 0.9333333333333333 | 0 | n/a (no negatives) |

| baseline | correct/n |
| --- | --- |
| CONSTANT_PER_TARGET | 33/40 |
| CONSTANT_ALL_NEGATIVE | 18/40 |
| CONSTANT_ALL_POSITIVE | 22/40 |

| GS arm | b | c | net | McNemar |
| --- | --- | --- | --- | --- |
| GS-Deterministic V4.1 | 1 | 0 | -1 | exact two-sided McNemar / binomial P=1 on B+C=1 |
| GS-Agentic V4.1 | 1 | 0 | -1 | exact two-sided McNemar / binomial P=1 on B+C=1 |
| GS-Exhaustive V4.1 | 1 | 0 | -1 | exact two-sided McNemar / binomial P=1 on B+C=1 |

## F. Follow-up action counts (len(actions_executed), all 60 cases)

| system | total | mean/case | median | IQR q1 | IQR q3 | reduction vs Deterministic % | reduction vs Exhaustive % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GS-Deterministic V4.1 | 149 | 2.483333 | 2.5 | 1.75 | 3.0 |  | 21.164021164021165 |
| GS-Agentic V4.1 | 61 | 1.016667 | 1.0 | 1.0 | 1.0 | 59.060402684563755 | 67.72486772486772 |
| GS-Exhaustive V4.1 | 189 | 3.150000 | 3.0 | 1.75 | 5.0 | -26.845637583892618 |  |

GS-Agentic per-case distribution of action counts:

| n actions | n cases |
| --- | --- |
| 1 | 59 |
| 2 | 1 |

## G. Measurement-state divergence

| metric | arm_or_pair | n | n_denom |
| --- | --- | --- | --- |
| m0_ne_m_final | gs_det | 60 | 60 |
| m0_ne_m_final | gs_agent | 60 | 60 |
| m0_ne_m_final | gs_exh | 60 | 60 |
| m_final_det_ne_agent | gs_det/gs_agent | 45 | 60 |
| m_final_det_ne_exh | gs_det/gs_exh | 30 | 60 |
| m_final_agent_ne_exh | gs_agent/gs_exh | 45 | 60 |
| endpoint_det_ne_agent | gs_det/gs_agent | 0 | 60 |
| endpoint_det_ne_exh | gs_det/gs_exh | 0 | 60 |
| endpoint_agent_ne_exh | gs_agent/gs_exh | 0 | 60 |
| endpoint_differs_any_gs_pair | gs_det/gs_agent/gs_exh | 0 | 60 |

## H. Planner policy

Counts are in M60_PLANNER_POLICY.csv (source × target × stratum × field × value).

GS_AGENTIC_V4_1 actions_executed (pooled):

| action_id | count |
| --- | --- |
| competitive_family | 30 |
| inspect_contig_edges_for_target | 15 |
| inspect_hit_contig_contamination | 15 |
| search_target_proteins_mmseqs | 1 |

GS_AGENTIC_V4_1 planner_decision (pooled):

| planner_decision | count |
| --- | --- |
| continue | 60 |

GS_AGENTIC_V4_1 critic_verdict (pooled):

| critic_verdict | count |
| --- | --- |
| accept | 59 |
| challenge | 1 |

GS_AGENTIC_V4_1 planner_grounding_status (pooled):

| planner_grounding_status | count |
| --- | --- |
| MISSING | 60 |

SOL56 sol_planner_action (pooled):

| sol_planner_action | count |
| --- | --- |
| competitive_family | 4 |
| inspect_contig_edges_for_target | 2 |
| search_target_domains_hmmer | 54 |

SOL56 sol_critic_disposition (pooled):

| sol_critic_disposition | count |
| --- | --- |
| challenge | 60 |

## Inputs

- created_utc: 2026-09-21T14:00:17.095057+00:00
- final_truth SHA256: `a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9`
- prediction_lock SHA256: `5317b33fa554f81855fa6c68854ad732c5f5127fc0ad41f224fede9159a90791`
- scientific_core SHA256: `22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0`

