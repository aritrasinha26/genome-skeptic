# Manuscript interpretation (conservative, post-hoc)

Scope: the eight truth-evaluable M60 cases on which GS-Deterministic, GS-Agentic (Qwen), GS-Exhaustive, and the Sol post-hoc ablation all disagreed with independent truth. Not a development loop. Not a licence to change V4.1.

## Observed facts

**OBSERVED FACT.** On the locked 41-case truth-evaluable denominator, Qwen Agentic, Sol Agentic, and GS-Exhaustive produced identical exact-endpoint predictions (33 / 41). GS-Deterministic produced the same 33 / 41 and the same eight errors.

**OBSERVED FACT.** Sol substantially changed investigation policy relative to Qwen (planner action 54 / 60; critic 60 / 60; follow-up count 120 vs 61) without changing any endpoint (0 / 60). Among the eight errors specifically, Sol and Qwen used different first actions in 8 / 8 cases and still matched endpoints in 8 / 8.

**OBSERVED FACT.** Independent truth for all eight errors is POSITIVE. The locked assemblies contain a recoverable candidate: tetA identity 0.25–0.998 with target-preferring HMMs; rpoB identity 0.837 with HMM score 1610.5.

## Post-hoc mechanistic finding

In every shared error, the frozen initial scientific core reconstructed a locus overlapping the independent-truth candidate and stored family measurements (HMM scores, member hits, and, for tetA, competitive-family scores that favoured tetA over MFS/RND). `discriminate_family` reported `target_family_supported` on all seven tetA errors. The Sol and Exhaustive follow-ups added hits but did not change architecture, competitive classification after relabel, or polarity.

The wrong endpoint was then produced by frozen family-state rules:

- tetA (7/7): `refine_weak_family_classification` rewrote `target_family_supported` as `ambiguous_family`; `family_detects_orthologue` treats that label as a hard negative, and pairwise identity cannot restore presence.
- rpoB (1/1): reconstruction architecture `domain_only` (from reconstruction HMM coverage 0.40) short-circuits `family_detects_orthologue` despite `best_hmm` model coverage 0.88, score 1610.5, and an `exact_strong_homolog` hierarchy.

Action-selection failure is not supported. Exhaustive executed every eligible registered follow-up and remained wrong on the same eight cases. Sol chose different instruments on all eight and remained wrong on the same eight.

## Permissible conclusion

In the shared errors examined here, prediction failure arose primarily from limitations in frozen family-state decision rules rather than from the choice of LLM-directed follow-up analysis.

That sentence is limited to this locked eight-case residual. It does not imply that language models cannot improve bioinformatics, that additional scientific instruments are never useful, or that a different validator would have been accurate on M60. It does not re-estimate manuscript accuracy under any counterfactual rule.

## What this analysis does not do

- It does not change thresholds, prompts, target definitions, or scientific code.
- It does not recalculate accuracy under a hypothetical rescue.
- It does not treat TRUTH_UNCERTAIN cases as correct or incorrect.
- It does not use these errors to build a V4.2.

Descriptive counterfactual rescues (validator-rule or representation changes) are recorded in `POSTHOC_ERROR_CASES.csv` for diagnosis only.
