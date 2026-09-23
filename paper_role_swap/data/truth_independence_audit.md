# ROLE_SWAP TRUTH INDEPENDENCE AUDIT

Truth uses M60-aligned Routes 1–2 (sequence panel + HMM/profile), implemented via
`scripts/adjudicate_m60_truth.py` helpers, **not** Genome Skeptic validator polarity,
Sol, Jev, Qwen, or study arms.

| resource | used by GS scientific core | used by truth protocol | reference overlap | independence adequate | limitations |
|---|---|---|---|---|---|
| UniProt P02980/P02982 + packaged tetA members.faa | YES (family panel) | YES (Route 1 target) | sequence panel overlap with GS family members | YES with disclosed circularity | shared panel sequences; different code path / no GS claim polarity |
| MFS/RND competitor panels | YES (competitor families) | YES (Route 1 competitors) | yes | YES with disclosed circularity | same biological competitor definition |
| tetA/MFS/RND HMMs (M60 truth SOURCE_FREEZE) | GS builds runtime HMMs from same MSAs | YES (Route 2) | model family overlap | YES with disclosed circularity | thresholds numerically overlap GS gates by protocol design |
| NCBI IPG P02980/P02982 | NO | enrichment shortlist only | n/a | YES | not used as final truth label |
| GS deterministic/agentic/exhaustive endpoints | YES | NO | none | YES | path forbidden for truth |
| Sol / Jev / Qwen | n/a | NO | none | YES | not called |
| AMRFinderPlus / PGAP symbols | comparator only | NO as truth | none | YES | enrichment not used as label |

## Circularity disclosure

Numeric gates and packaged family sequences overlap GS endpoint definition
(acknowledged in ROLE_SWAP_TRUTH_PROTOCOL.md). Independence requirement is:
do not copy GS/Sol/Jev validator outputs into truth. That requirement is met.

STOP condition (exact same classifier + exact same evidence gates as the live GS
validator polarity function): **NOT TRIGGERED** — truth polarity comes from
`tet_call` / route concordance in the independent adjudication script, not from
`classify_polarity` / `family_detects_orthologue` in the GS validator.
