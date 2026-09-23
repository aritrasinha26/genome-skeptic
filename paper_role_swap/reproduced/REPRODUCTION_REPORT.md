# Reproduction report

Status: **ALL_REPORTED_RESULTS_REPRODUCED**

Primary path uses only files under `paper_role_swap/`. No Sol/Jev API calls.

## Dependency paths (current generation)

| Output | Locked inputs inside paper_role_swap |
| --- | --- |
| Statistics / McNemar / bootstrap CI | `data/prospective_truth.csv`, `data/locked_predictions/{A,B,C,D,F}/*`, `results/preunblind_behaviour.csv` |
| Follow-up counts | sum of `followup_count` in locked predictions |
| Latency / API cost | `results/preunblind_behaviour.csv` (locked pre-unblind) |
| B↔D evidence identity | `data/arm_b_vs_d_evidence_hashes.csv` + D `identical_evidence_assert` |
| Table 1 | `protocol/ARM_DEFINITIONS.md` roles + regenerated arm scores |
| Figure 2 (precursor) | `results/precursor/M60_AGENT_VS_DETERMINISTIC.csv`, `M60_EFFICIENCY_RESULTS.csv` |
| Figure 3 (efficiency) | regenerated follow-ups + preunblind latency/cost |
| Figure 4 (role swap) | regenerated B vs D correction/degradation counts |

## Numerical comparison vs locked results

| claim | regenerated | locked | status |
| --- | --- | --- | --- |
| Arm A correct/20 | 18 | 18 | MATCH |
| Arm B correct/20 | 18 | 18 | MATCH |
| Arm C correct/20 | 18 | 18 | MATCH |
| Arm F correct/20 | 18 | 18 | MATCH |
| Arm D correct/20 | 11 | 11 | MATCH |
| sensitivity B | 0.8 | 0.8 | MATCH |
| specificity B | 1.0 | 1.0 | MATCH |
| sensitivity D | 0.8 | 0.8 | MATCH |
| specificity D | 0.3 | 0.3 | MATCH |
| unresolved D | 9 | 9 | MATCH |
| B correct / D wrong | 7 | 7 | MATCH |
| B wrong / D correct | 0 | 0 | MATCH |
| sol_corrections | 0 | 0 | MATCH |
| sol_degradations | 7 | 7 | MATCH |
| ABSENT->UNRESOLVED | 9 | 9 | MATCH |
| McNemar P | 0.015625 | 0.015625 | MATCH |
| paired_diff D-B | -0.35 | -0.35 | MATCH |
| paired_CI_low | -0.55 | -0.55 | MATCH |
| paired_CI_high | -0.15000000000000002 | -0.15000000000000002 | MATCH |
| followups fixed (A) | 57 | 57 | MATCH |
| followups Sol (B) | 39 | 39 | MATCH |
| followups exhaustive (C) | 74 | 74 | MATCH |
| followups Jev (F) | 39 | 39 | MATCH |
| Sol median latency | 10.2845 | 10.2845 | MATCH |
| Jev median latency | 2.2165 | 2.2165 | MATCH |
| Sol API cost | 0.374832 | 0.374832 | MATCH |
| Jev API cost | 0.0033142 | 0.0033142 | MATCH |
| B/D evidence identity 20/20 | 20 | 20 | MATCH |
| identical_evidence_assert from preds | 20 | 20 | MATCH |
| Table1 Arm A correct | 18 | 18 | MATCH |
| Table1 Arm B correct | 18 | 18 | MATCH |
| Table1 Arm C correct | 18 | 18 | MATCH |
| Table1 Arm D correct | 11 | 11 | MATCH |
| Table1 Arm F correct | 18 | 18 | MATCH |
| Fig3 source followups A | 57 | 57 | MATCH |
| Fig3 source followups B | 39 | 39 | MATCH |
| Fig3 source followups C | 74 | 74 | MATCH |
| Fig3 source followups F | 39 | 39 | MATCH |
| Fig4 source corrections | 0 | 0 | MATCH |
| Fig4 source degradations | 7 | 7 | MATCH |
| Fig2 precursor agent_vs_det source present | True | True | MATCH |
| Fig2 precursor efficiency source present | True | True | MATCH |

MATCH count: 42 / 42

All reported numerical claims MATCH locked manuscript source data.

