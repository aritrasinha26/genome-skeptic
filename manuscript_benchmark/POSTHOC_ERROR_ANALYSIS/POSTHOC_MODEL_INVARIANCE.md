# POST-HOC MODEL-INVARIANCE ANALYSIS

Observation from locked runs, not a new experiment.

## Observed facts

| Arm | Follow-up actions | Truth-evaluable exact-endpoint accuracy |
|---|---:|---|
| Qwen Agentic (qwen3:4b) | 61 | 33 / 41 |
| Sol Agentic (gpt-5.6-sol, reasoning=high) | 120 | 33 / 41 |
| GS-Exhaustive | 189 | 33 / 41 |
| GS-Deterministic | policy-fixed follow-up, not LLM | 33 / 41 |

Sol vs Qwen, all 60 cases (locked Sol summary):

- Planner changed: 54 / 60
- Critic changed: 60 / 60
- Final endpoint changed: 0 / 60
- Extra Sol follow-up actions with DECISION_CHANGE: 0
- Extra Sol follow-up actions with NO_DECISION_CHANGE: 59

Accuracy identity is therefore not an artefact of identical investigation policy.

## Quantities restricted to the eight shared errors

| Quantity | n / 8 |
|---|---|
| Different Qwen vs Sol investigation paths (planner action changed) | 8 / 8 |
| Critic behaviour changed vs Qwen | 8 / 8 |
| Additional Sol evidence fields recorded | 8 / 8 |
| Additional Exhaustive follow-up relative to Qwen | 8 / 8 |
| Architecture different Qwen vs Sol | 0 / 8 |
| homology_support different Qwen vs Sol | 0 / 8 |
| competitive_family final classification different across GS arms | 0 / 8 |
| Final endpoint different | 0 / 8 |

Per-error path (locked Sol case-level file):

| Pos | Qwen first action | Sol first action | Sol second action | Extra Sol fields | Exhaustive n | Endpoint |
|---:|---|---|---|---|---:|---|
| 13 | competitive_family | search_target_domains_hmmer | competitive_family | family_evidence;hits;tools_run | 4 | NEGATIVE |
| 14 | competitive_family | search_target_domains_hmmer | competitive_family | hits;tools_run | 4 | NEGATIVE |
| 19 | competitive_family | search_target_domains_hmmer | competitive_family | hits;tools_run | 4 | NEGATIVE |
| 36 | competitive_family | search_target_domains_hmmer | competitive_family | hits;tools_run | 4 | NEGATIVE |
| 37 | competitive_family | search_target_domains_hmmer | competitive_family | family_evidence;hits;tools_run | 6 | NEGATIVE |
| 41 | competitive_family | search_target_domains_hmmer | competitive_family | hits;tools_run | 4 | NEGATIVE |
| 44 | competitive_family | search_target_domains_hmmer | competitive_family | hits;tools_run | 4 | NEGATIVE |
| 48 | inspect_contig_edges_for_target | search_target_domains_hmmer | inspect_contig_edges_for_target | hits;tools_run;hit_edge_flags | 2 | NEGATIVE |

Case 37 is the only error in which Exhaustive also ran protein-level ORF searches (`diamond`, `mmseqs`). Those instruments increased `n_loci` (Qwen 3, Exhaustive 7) without changing competitive classification, architecture, or endpoint.

Case 48 is the only error in which Sol’s extra HMM search was a first action that Qwen never chose. Frozen architecture remained `domain_only` and homology_support remained 0.35.

## What kind of invariance is this?

The eight errors do **not** support a single global label, but they do not support “the models found the same evidence by chance” either.

### A. Evidence convergence — supported, incomplete

All four GS arms reconstructed the same truth-overlapping locus and stored the same `best_hmm` / member-hit numbers. Additional Sol/Exhaustive hits were mostly extra HSPs on that locus or extra weak MFS-like loci, not a different biological candidate.

### B. Evidence-state compression — supported for tetA

On every tetA error, `discriminate_family` returned `target_family_supported` with large score margins. After `refine_weak_family_classification`, the stored decision-relevant classification was `ambiguous_family` in every arm. Numeric competitive scores remained in TargetMeasurements; the state machine compressed them to one veto label. Qwen, Sol, and Exhaustive therefore presented the validator with the same family-state even when hit lists differed.

### C. Validator saturation — supported for all eight

Once `ambiguous_family` (tetA) or `domain_only` (rpoB) is set, `family_detects_orthologue` returns False and `classify_polarity` forbids pairwise rescue. Extra hits, extra HMM ORFs, and extra copy-number loci cannot change the endpoint. That is saturation of a frozen rule, not saturation of biological information.

### D. Insufficient registered scientific instruments — not supported as the primary invariance mechanism

The instruments *did* recover the truth locus and family scores. Exhaustive’s unused-or-extra instruments (HMM search, diamond, mmseqs, edges, contamination) did not supply a missing family discriminator; the discriminator had already run. rpoB has no competing-family action, but the rpoB miss is a domain_only short-circuit on an already-supported HMM, not an absent competitive panel.

## Conclusion for the eight errors

Model-invariant endpoints on the shared errors arise from **evidence-state compression plus validator saturation** acting on **convergent recovered candidates**. They do not arise from identical LLM action selection, and they are not explained by a missing registered follow-up that Exhaustive failed to run while an LLM might have chosen it.

This statement is restricted to these eight locked false negatives. It is not a claim about all bioinformatics tasks or all possible future instruments.
