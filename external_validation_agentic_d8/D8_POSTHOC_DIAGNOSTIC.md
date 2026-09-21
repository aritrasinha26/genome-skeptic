# D8 post-hoc diagnostic audit

Diagnosis only. Locked D8 predictions, truth, Agentic provenance, evidence, and the frozen V2 action catalogue were used. No code, prompts, thresholds, Qwen, or bioinformatics tools were rerun. D20 was not accessed.

## Per-case table

| Pos | Accession | Target | Truth | Conv | Conv OK | V5 | V5 OK | Agentic | Ag OK | Done | Planner decision | Planner action | Critic verdict | Critic action | Executed | ActionResult | m0 | m_final | Measurements changed | Agentic ≠ V5 | agent_failure |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | GCF_054792365.1 | rpoB_RNAP_beta | POSITIVE | not_detected | no | detected | yes | detected | yes | yes | continue | search_target_proteins_mmseqs | accept | — | search_target_proteins_mmseqs | INFORMATIVE | dc8e9438… | cc2ad5cd… | yes | no | — |
| 2 | GCF_049373995.1 | rpoB_RNAP_beta | POSITIVE | not_detected | no | detected | yes | detected | yes | yes | continue | inspect_contig_edges_for_target | accept | — | inspect_contig_edges_for_target | INFORMATIVE | 7dfe0585… | 99fbcba9… | yes | no | — |
| 3 | GCF_048851505.1 | tuf_EF_Tu | 1 | not_detected (mult=0) | no | detected (mult=0) | no | EXECUTION_FAILURE | no | **no** | continue | inspect_contig_edges_for_target | — | — | none | none | 98dd8e71… | 98dd8e71… | no | **yes** | planner cited no evidence IDs |
| 4 | GCF_056483745.1 | lacZ_beta_galactosidase | NEGATIVE | not_detected | yes | detected | no | detected | no | yes | continue | search_target_proteins_mmseqs | accept | — | search_target_proteins_mmseqs | INFORMATIVE | a81d31b0… | 194367f2… | yes | no | — |
| 5 | GCF_046846385.1 | tuf_EF_Tu | 1 | not_detected (mult=0) | no | not_detected (mult=0) | no | not_detected (mult=0) | no | yes | continue | inspect_hit_contig_contamination | accept | — | inspect_hit_contig_contamination | INFORMATIVE | bd72fe3f… | 48a6be9f… | yes | no | — |
| 6 | GCF_056267885.1 | lacZ_beta_galactosidase | NEGATIVE | not_detected | yes | detected | no | detected | no | yes | continue | search_target_proteins_mmseqs | accept | — | search_target_proteins_mmseqs | INFORMATIVE | 11b74111… | ce3c130f… | yes | no | — |
| 7 | GCF_053618555.1 | tetA_tetracycline_efflux | NEGATIVE | not_detected | yes | detected | no | EXECUTION_FAILURE | no | **no** | continue | inspect_contig_edges_for_target | — | — | none | none | 8b9c9afc… | 8b9c9afc… | no | **yes** | planner cited no evidence IDs |
| 8 | GCF_050310035.1 | tetA_tetracycline_efflux | POSITIVE | not_detected | no | detected | yes | detected | yes | yes | continue | inspect_contig_edges_for_target | accept | — | inspect_contig_edges_for_target | INFORMATIVE | 5d087a04… | 0f5996e1… | yes | no | — |

No ActionResult was `NO_NEW_INFORMATION`, `UNAVAILABLE`, or `FAILED`. The six completed cases each executed one action that returned `INFORMATIVE`. The two non-completions executed nothing.

## V5-incorrect case audits (positions 3, 4, 5, 6, 7)

Runtime-available actions on every D8 case were nucleotide/translated search (inert: already in baseline), `inspect_contig_edges_for_target` (sometimes inert), `search_target_proteins_mmseqs` / `diamond` / `search_target_domains_hmmer`, `inspect_paralogue_copies` (always inert: updates no measurement), and `inspect_hit_contig_contamination`. `competitive_family` appeared only for tetA. GFF, depth, mapping, references, and taxonomy DB were not supplied, so synteny, coverage, RBH, reference comparison, breaks, and taxonomy were not in `available_actions`.

### Position 3 — tuf, truth multiplicity 1, V5 detected with recorded multiplicity 0

A. **YES**  
B. `search_target_proteins_mmseqs` (also `inspect_contig_edges_for_target`, which the planner named)  
C. Offered (in `state_changing_actions`). Not executed: planner JSON had `evidence_ids=[]`; controller rejected it.  
D. **EXECUTION_FAILURE**  
Planner asked for a live action but cited no evidence IDs; repair did not fill them; loop failed closed. `inspect_paralogue_copies` exists but is catalog-inert and cannot change scored multiplicity.

### Position 4 — lacZ, truth NEGATIVE, V5/Agentic detected (`profile_hmm_family_match`)

A. **YES** (catalog)  
B. `competitive_family`; also `reciprocal_best_hit_search`, `compare_locus_to_reference`, `inspect_synteny_neighborhood_for_target`  
C. Excluded by prerequisites: `lacZ_beta_galactosidase/family.yaml` has no `competing_families`; D8 used empty `references.yaml` and no GFF. `competitive_family` was not in `available_actions`. Planner executed `search_target_proteins_mmseqs` (`INFORMATIVE`, hits 20→40). Critic accepted. Validator still detected.  
D. **TOOLBOX_GAP**  
No executable action on this run could test LacZ orthology versus a related beta-galactosidase. Extra protein hits cannot produce a true-negative.

### Position 5 — tuf, truth multiplicity 1, V5/Agentic not_detected (`true_no_candidate`, multiplicity 0) despite 20 baseline hits

A. **YES**  
B. `search_target_proteins_mmseqs` (also `search_target_domains_hmmer`, `search_target_proteins_diamond`)  
C. Offered; ignored by planner, which ran `inspect_hit_contig_contamination`. Critic accepted. Action was `INFORMATIVE` (GC only); `n_hits` stayed 20 and `n_loci` stayed 1 in measurements while the claim remained `true_no_candidate`.  
D. **ACTION_SELECTION_FAILURE**  
A live protein/HMM search could re-measure the missed EF-Tu; the planner chose a contamination GC test instead.

### Position 6 — lacZ, truth NEGATIVE, V5/Agentic detected (`profile_hmm_family_match`)

A. **YES** (catalog)  
B. Same as position 4: `competitive_family` / RBH / reference / synteny  
C. Excluded by prerequisites. Planner executed `search_target_proteins_mmseqs` (`INFORMATIVE`, hits 20→21). Critic accepted.  
D. **TOOLBOX_GAP**  
Same as position 4.

### Position 7 — tetA, truth NEGATIVE, V5 detected (`profile_hmm_family_match`, `close_paralogue`)

A. **YES**  
B. `competitive_family`  
C. Offered (`available_actions` and `state_changing_actions`). Planner requested `inspect_contig_edges_for_target` with empty `evidence_ids`; repair failed; nothing executed.  
D. **EXECUTION_FAILURE**  
The catalog action that discriminates `wrong_family` vs `true_presence` was live; the controller never reached it.

## Two Agentic non-completions

Both are **ENGINEERING / CONTROL FLOW**, not scientific/evidence failures of a tool.

| | Position 3 | Position 7 |
|---|---|---|
| Recorded reason | planner cited no evidence IDs | planner cited no evidence IDs |
| JSON/schema parse | no (PlannerDecision parsed; action named) | no |
| Missing evidence IDs | **yes** (`evidence_ids=[]` before and after repair) | **yes** |
| Invalid action | no | no |
| Unavailable action | no (`inspect_contig_edges_for_target` was available) | no |
| Model truncation | no (rationale and requested_action present) | no |
| Controller rejection | **yes** (`_validate_planner`) | **yes** |
| Deterministic tool failure | no (no action executed) | no |
| Critic | not invoked | not invoked |
| Repair | `AgentDecision_repair` in call graph; still empty IDs | same |

Position 2 had the same first-pass empty-`evidence_ids` defect but the repair filled IDs and the run completed. Positions 3 and 7 did not.

## Summary

| Failure category | Count |
|---|---:|
| ACTION_SELECTION_FAILURE | 1 |
| TOOLBOX_GAP | 2 |
| STATE_UPDATE_FAILURE | 0 |
| VALIDATOR_LIMITATION | 0 |
| EXECUTION_FAILURE | 2 |
| NO_RESOLVABLE_SIGNAL | 0 |
| OTHER | 0 |

V5 WRONG CASES:  
3, 4, 5, 6, 7

V5 WRONG CASES WITH A USEFUL EXISTING ACTION AVAILABLE:  
3, 4, 5, 6, 7

USEFUL ACTION AVAILABLE BUT NOT EXECUTED:  
3 (`search_target_proteins_mmseqs` offered; loop died), 5 (`search_target_proteins_mmseqs` offered; planner ignored), 7 (`competitive_family` offered; loop died)

INFORMATIVE ACTIONS EXECUTED:  
1, 2, 4, 5, 6, 8

CASES WHERE m_final != m0:  
1, 2, 4, 5, 6, 8

CASES WHERE AGENTIC FINAL RESULT != V5:  
3, 7

AGENTIC EXECUTION FAILURES:  
2 / 8

DIAGNOSTIC OUTCOME:  
MIXED

D20 TOUCHED:  
NO
