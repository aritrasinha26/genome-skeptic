# ROLE-SWAP FINAL RESULTS — tetA within-task

Single unblind. Predictions and truth unchanged. Scoring: UNRESOLVED vs resolved truth = incorrect.

## Headline

- **Arm A**: 18/20 correct; sens=0.80; spec=1.00; bal_acc=0.900; MCC=0.816; unresolved=0
- **Arm B**: 18/20 correct; sens=0.80; spec=1.00; bal_acc=0.900; MCC=0.816; unresolved=0
- **Arm C**: 18/20 correct; sens=0.80; spec=1.00; bal_acc=0.900; MCC=0.816; unresolved=0
- **Arm D**: 11/20 correct; sens=0.80; spec=0.30; bal_acc=0.550; MCC=0.115; unresolved=9
- **Arm F**: 18/20 correct; sens=0.80; spec=1.00; bal_acc=0.900; MCC=0.816; unresolved=0

A/B/C/F endpoints identical → accuracy metrics identical. Efficiency differs.

## Primary comparison (B vs D, identical evidence)

- Endpoint differences: **9/20**
- Both correct: 11
- Both wrong: 2
- B correct / D wrong (degradations): **7**
- B wrong / D correct (corrections): **0**
- Net Sol-judge effect (corrections−degradations): **-7**
- McNemar: exact two-sided McNemar / binomial P=0.015625 on B+C=7
- Paired accuracy difference D−B = -0.350 (bootstrap 95% CI -0.550–-0.150)

### Discordant transitions
- `ABSENT->UNRESOLVED`: 9

All 9 discordances convert deterministic ABSENT → Sol UNRESOLVED (uncertainty), not PRESENT↔ABSENT flips.

### Nine endpoint-discordant cases

| case_id | truth | B | D | B_ok | D_ok | family | competitor | sufficient | locus |
|---|---|---|---|---|---|---|---|---|---|
| RS06 | POSITIVE | ABSENT | UNRESOLVED | False | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |
| RS09 | POSITIVE | ABSENT | UNRESOLVED | False | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |
| RS11 | NEGATIVE | ABSENT | UNRESOLVED | True | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |
| RS13 | NEGATIVE | ABSENT | UNRESOLVED | True | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |
| RS15 | NEGATIVE | ABSENT | UNRESOLVED | True | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |
| RS16 | NEGATIVE | ABSENT | UNRESOLVED | True | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |
| RS17 | NEGATIVE | ABSENT | UNRESOLVED | True | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |
| RS19 | NEGATIVE | ABSENT | UNRESOLVED | True | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |
| RS20 | NEGATIVE | ABSENT | UNRESOLVED | True | False | UNCERTAIN | NOT_SUPPORTED | NO | INSUFFICIENT_EVIDENCE |

## Controller efficiency

- Follow-ups: A=57, B=39, C=74, F=39
- B reduction vs A: 31.6%
- B reduction vs C: 47.3%
- F reduction vs A: 31.6%
- F reduction vs C: 47.3%
- Sol/Jev median model latency ratio: 4.6400
- Sol/Jev API cost ratio: 113.0988
- Fewer analyses ≠ faster wall-clock (B median total runtime > A).

## Central questions

- A. Sol controller improve accuracy over det? **NO**
- B. Sol controller alter final biological decisions? **NO (0/20 endpoint differences vs A/C/F)**
- C. Sol controller reduce follow-ups? **YES**
- D. Jev reproduce Sol-controller endpoints? **YES (20/20)**
- E. Transferring final authority to Sol improve accuracy? **NO**
- F. Sol-judge corrections: **0**
- G. Sol-judge degradations: **7**
- H. Sol-judge mainly: **INCREASE_UNCERTAINTY**

## Interpretation (within-task only)

"Under identical scientific evidence, transferring final biological decision authority from the explicit deterministic validator to GPT-5.6 Sol did not improve classification and introduced additional degradations and/or unresolved calls."

"Model-guided control altered evidence acquisition and reduced analytical work without changing the final biological decisions in this cohort."

"A specialised typed decision model reproduced the same final endpoints as GPT-5.6 Sol while requiring substantially lower model latency and API cost."

Do not generalise beyond tet(A)/tet(B).
