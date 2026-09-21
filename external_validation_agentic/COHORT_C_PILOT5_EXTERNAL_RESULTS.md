# PRELIMINARY EXTERNAL PILOT — Cohort C, 5 cases

**PRELIMINARY EXTERNAL PILOT**  
n = 5 genome-target cases  
2 genomes  
**not a definitive external benchmark**

Do not treat these counts as sensitivity, specificity, F1, MCC, or a superiority result.

Agentic V1, deterministic V5, the conventional baseline, predictions, thresholds, target definitions, and the 5-case pilot manifest were not modified after unblinding.

---

## 1. Lock verification (before unblinding)

Recomputed SHA256 after the locked files were already written.

| File | Locked SHA256 | Recomputed | Result |
|---|---|---|---|
| `cohort_C_pilot5_manifest.json` | `9107b54b5afdba8dd77088a07206fcc566f0632e2d97b88d8ac891f3943ae7ee` | `9107b54b5afdba8dd77088a07206fcc566f0632e2d97b88d8ac891f3943ae7ee` | MATCH |
| `cohort_C_pilot5_predictions_locked.jsonl` | `aac2a69ec747474c33d1d710e4d9a9389f8f5809832a3fb2cf33e97572869648` | `aac2a69ec747474c33d1d710e4d9a9389f8f5809832a3fb2cf33e97572869648` | MATCH |

Verification recorded. Unblinding proceeded only because both hashes matched.

---

## 2. External labels (locked before comparison)

File: `external_validation_agentic/cohort_C_pilot5_external_labels_locked.jsonl`

**External-label SHA256:** `8ba687f0b976c54e7de28a5d8eb26b76467445888ffb977607076e816ef4ec7a`

Hashed before prediction comparison. Only positions 1–5 were labelled. No other Cohort C case was opened.

Procedure (frozen):

- rpoB / tuf / lacZ: NCBI Gene Orthologs ± eggNOG 5; PGAP corroboration only.
- tetA: AMRFinderPlus external call as published on the RefSeq assembly. Positive family = tet(A) OR tet(B). tet(C) and other tetracycline-efflux genes are not positives.

NCBI Gene Orthologs does not index taxid 1261393 or 393030. eggNOG 5 precomputed bacterial members also lack those taxids. Orthology labels therefore used independent post-lock phmmer of the frozen/NCBI seed protein (whose UniProt record carries the eggNOG 5 NOG) against **all proteins of that assembly**, with PGAP symbols only as corroboration.

| Pos | Assembly | Target | Truth |
|---:|---|---|---|
| 1 | GCF_055394735.1 | rpoB_RNAP_beta | **POSITIVE** |
| 2 | GCF_055394735.1 | tuf_EF_Tu | **POSITIVE** |
| 3 | GCF_055394735.1 | lacZ_beta_galactosidase | **NEGATIVE** |
| 4 | GCF_055394735.1 | tetA_tetracycline_efflux | **NEGATIVE** |
| 5 | GCF_055378285.1 | rpoB_RNAP_beta | **POSITIVE** |

Short rationales:

1. Complete non-pseudo WP_464229829.1 hit to frozen rpoB seed NP_418414.1 / COG0085 (E=0, seed coverage 8–1340/1342). PGAP `rpoB` corroborates.
2. Complete non-pseudo WP_464229820.1 hit to authentic tufA NP_417798.1 / gene_id 947838 / eggNOG 5 COG0050 (E=7.5e-208, seed coverage 1–393/394). PGAP has two `tuf` loci with that protein. The written V5 protocol listed NP_418240.1 as the tuf seed; the current NCBI record for NP_418240.1 is not EF-Tu, so this label follows the named target `tuf_EF_Tu`.
3. phmmer of frozen lacZ seed NP_414878.1 / COG3250 against all proteins at E≤1e-5 returned no hits. PGAP has no lacZ / beta-galactosidase product.
4. No tet(A), tet(B), tetracycline, or AMRFinderPlus string on this assembly. Competing RND/MATE/CDF efflux proteins without tet(A)/tet(B) are negatives for this frozen family.
5. Complete non-pseudo WP_464280409.1 hit to frozen rpoB seed (E=0, score 1585, length 1347). PGAP `rpoB` corroborates.

---

## 3. Five-case comparison

Presence/absence scoring uses the locked claim type:

- `target_gene_detected` vs POSITIVE = correct; vs NEGATIVE = incorrect
- `target_gene_not_detected` vs NEGATIVE = correct; vs POSITIVE = incorrect
- Agentic position 2 is **execution failure**, not a biological prediction

| Pos | Truth | Agentic V1 | V5 | Conventional | Agentic score | V5 score | Conventional score |
|---:|---|---|---|---|---|---|---|
| 1 | POSITIVE | detected (weakened, 0.55) | detected (weakened, 0.55) | not detected (0.70) | correct | correct | incorrect |
| 2 | POSITIVE | **AGENT_EXECUTION_FAILURE** | not detected (supported, 0.54) | not detected (0.70) | execution failure | incorrect | incorrect |
| 3 | NEGATIVE | detected (weakened, 0.55) | detected (weakened, 0.55) | not detected (0.70) | incorrect | incorrect | correct |
| 4 | NEGATIVE | detected (weakened, 0.38) | detected (weakened, 0.38) | not detected (0.70) | incorrect | incorrect | correct |
| 5 | POSITIVE | detected (weakened, 0.55) | detected (weakened, 0.55) | not detected (0.70) | correct | correct | incorrect |

---

## 4. Headline counts (n = 5 only)

- Agentic execution completion: **4 / 5**
- Agentic biological accuracy among successfully completed cases: **2 / 4**
- Agentic end-to-end successful correct answers: **2 / 5**
- V5: **2 / 5**
- Conventional: **2 / 5**

No sensitivity, specificity, F1, MCC, significance test, or superiority claim is reported.

---

## 5. Agentic vs V5 (successful Agentic cases only)

Final presence/absence class and confidence for the four completed Agentic cases were identical to deterministic V5.

| Pos | Category | Planner action | Critic | New evidence changed final claim? | Notes |
|---:|---|---|---|---|---|
| 1 | **A. SAME_FINAL_RESULT** | `inspect_contig_edges_for_target` | accept | no | Both correct detections. E005 added contig-edge inspection; class unchanged. |
| 3 | **A. SAME_FINAL_RESULT** | `inspect_local_coverage_for_target` | challenge | no | Both false detections. Critic challenged low identity/coverage; validator kept V5 detection. |
| 4 | **A. SAME_FINAL_RESULT** | `inspect_contig_edges_for_target` | challenge | no | Both false detections. Critic challenged edge/truncation; validator kept V5 detection. |
| 5 | **A. SAME_FINAL_RESULT** | `inspect_contig_edges_for_target` | challenge | no | Both correct detections. Critic challenged edge truncation on a complete chromosome; validator kept V5 detection. |

No completed case is B (agent corrected V5) or C (agent degraded a correct V5 result).

Planner/critic added a new evidence item (E005) in all four completed cases. That evidence did not change the deterministic final claim relative to V5. Benefit is not inferred merely because the LLM ran.

Position 2 is not given an A–E category.

---

## 6. Position 2 execution failure (not a biological result)

Pre-existing execution facts only. Not rerun after truth was known.

- Planner returned no registered action (`requested_actions: []` after one repair).
- System failed closed (`ok: false`, `classification: unresolved`, confidence 0.0).
- Statement: no LLM-free scientific success claim is issued.
- Silent deterministic fallback did not occur (`silent_deterministic_fallback: false`).
- Critic was not invoked. Final validator did not issue a scientific success claim.

This is a failure mode of the frozen planner policy (it discussed synteny/fragmentation but emitted no registered action). It is not an opportunity to repair this pilot.

Independently, deterministic V5 also called `target_gene_not_detected` on this POSITIVE tuf case. That V5 error is consistent with the frozen tuf family seed `NP_418240.1` not being current EF-Tu. That is a frozen-V5 limitation, not a post-hoc agent patch.

---

## 7. Actions and critic outcomes (completed Agentic cases)

Action frequency among completed cases:

- `inspect_contig_edges_for_target`: 3
- `inspect_local_coverage_for_target`: 1

Critic verdicts among completed cases:

- accept: 1 (position 1)
- challenge: 3 (positions 3, 4, 5)

Challenges did not flip the deterministic validator’s final class.

---

## 8. Runtime

| Pos | Case | Agentic (s) | V5 (s) | Conventional (s) |
|---:|---|---:|---:|---:|
| 1 | GCF_055394735.1 × rpoB | 745.6 | 95.6 | 5.9 |
| 2 | GCF_055394735.1 × tuf | 406.3 | 95.6 | 5.9 |
| 3 | GCF_055394735.1 × lacZ | 1498.3 | 95.6 | 5.9 |
| 4 | GCF_055394735.1 × tetA | 978.9 | 95.6 | 5.9 |
| 5 | GCF_055378285.1 × rpoB | 620.0 | 20.4 | 0.8 |

Positions 1–4 share one V5 genome-level run and one conventional genome-level run.

Unique compute ≈ 72.9 min (Agentic 4249 s + V5 116.0 s + conventional 6.7 s).

---

## 9. Limitations

- n = 5, two genomes, one complete-genome lineage pair. Not a benchmark.
- NCBI Gene Orthologs and eggNOG 5 precomputed members do not cover these taxa; orthology used independent seed-to-proteome phmmer plus PGAP corroboration.
- The frozen V5 tuf family seed `NP_418240.1` is not current EF-Tu. External tuf labels used NCBI tufA `NP_417798.1` / gene_id 947838.
- tetA labels are the published RefSeq/AMRFinderPlus call on these assemblies, not a local AMRFinderPlus rerun.
- Conventional absence on distant rpoB is expected if the baseline is strict BLAST-to-reference rather than family orthology.
- Agentic and V5 both false-detected lacZ and tetA; the planner/critic loop did not correct those V5 errors.
- Agentic failed closed on the one tuf case that is biologically present.
- No other Cohort C genomes or remaining 35 cases were unblinded.

---

STOP. Agentic V1 was not modified after seeing results.
