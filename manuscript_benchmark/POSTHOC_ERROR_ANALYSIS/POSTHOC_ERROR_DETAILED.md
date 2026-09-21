# POST-HOC MECHANISTIC ERROR ANALYSIS

Frozen prospective M60 (GENOME_SKEPTIC_V4_1_MANUSCRIPT) plus the Sol post-hoc model ablation.

This document reconstructs locked decision paths. It does not retune thresholds, regenerate predictions, replace cases, access D20, or reinterpret TRUTH_UNCERTAIN.

## 0. Source-artifact verification

Locked inputs were hashed, not regenerated.

| Artifact | SHA256 | Status |
|---|---|---|
| `TRUTH_M60/M60_EXTERNAL_TRUTH_FINAL_LOCKED.json` | `a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9` | matches frozen final truth |
| Sol ablation manifest file | `2a9f86956ca12026b4ff39fc7bcaf297db992ba4db53421a9482683ae1885a39` | matches stated Sol ablation manifest |
| M60 case-level results | `RESULTS_M60/M60_FINAL_CASE_LEVEL_RESULTS.csv` | read only |
| GS-Det / Qwen Agentic / Exhaustive | `POSITION_LOCKS/position_*/GS_*_V4_1.json` plus `RUNS/` family_evidence, claims, evidence, provenance | read only |
| Sol ablation | `SOL56_FULL_ABLATION/locks/position_*.json` plus Sol `family_evidence.json` | read only |

D20 was not opened.

## 1. Identity of the eight shared errors

Truth-evaluable N = 41. GS-Det final endpoint ≠ truth on exactly eight evaluable cases. The same eight are wrong for Qwen Agentic, GS-Exhaustive, and Sol Agentic. No discrepancy.

| Pos | Case | Target | Stratum | Truth | All GS endpoints |
|---:|---|---|---|---|---|
| 13 | `M60_tetA_tetracycline_efflux_GCF_056269845.1` | tetA | routine | POSITIVE | NEGATIVE |
| 14 | `M60_tetA_tetracycline_efflux_GCF_060343445.1` | tetA | routine | POSITIVE | NEGATIVE |
| 19 | `M60_tetA_tetracycline_efflux_GCF_054552735.1` | tetA | routine | POSITIVE | NEGATIVE |
| 36 | `M60_tetA_tetracycline_efflux_GCF_058409085.1` | tetA | routine | POSITIVE | NEGATIVE |
| 37 | `M60_tetA_tetracycline_efflux_GCF_059878295.1` | tetA | routine | POSITIVE | NEGATIVE |
| 41 | `M60_tetA_tetracycline_efflux_GCF_056613625.1` | tetA | challenge | POSITIVE | NEGATIVE |
| 44 | `M60_tetA_tetracycline_efflux_GCF_056539405.1` | tetA | challenge | POSITIVE | NEGATIVE |
| 48 | `M60_rpoB_RNAP_beta_GCF_055389225.1` | rpoB | routine | POSITIVE | NEGATIVE |

These are 7/7 tetA false negatives among evaluable POSITIVE tetA cases and 1/15 rpoB false negatives.

## Frozen validator rules used below (quoted, not changed)

Polarity after family analysis (`src/genome_skeptic/validators/falsification.py`):

```71:86:src/genome_skeptic/validators/falsification.py
def classify_polarity(hits: list[GeneSearchHit], settings: Settings, target_type=None, family_evidence=None) -> ClaimType:
    ...
    if family_evidence is not None and tt in {TargetType.gene_orthologue, TargetType.protein_family, None}:
        ...
        if family_detects_orthologue(profile, hits, settings, family_evidence):
            return ClaimType.target_gene_detected
        # Family analysis already ran. Pairwise similarity cannot restore family identity
        # after a competitive-family or domain-only veto.
        return ClaimType.target_gene_not_detected
```

Orthologue gate (`src/genome_skeptic/validators/family_orthology.py`):

```759:777:src/genome_skeptic/validators/family_orthology.py
def family_detects_orthologue(...):
    ...
    if family_evidence and family_evidence.domain_only:
        return False
    comp = ((family_evidence.reconstruction or {}).get("competitive_family") if family_evidence else None) or {}
    cls = comp.get("classification")
    if cls in {"competing_family_preferred", "ambiguous_family"}:
        return False
    if family_evidence and family_evidence.supports_orthologue:
        return True
```

Post-action relabel (`src/genome_skeptic/validators/locus_v4_dev.py` and `diagnostic_needs_v4_1_dev.py`):

```239:266:src/genome_skeptic/validators/locus_v4_dev.py
def refine_weak_family_classification(m: TargetMeasurements) -> bool:
    """Reclassify a non-decisive target_family_supported call as ambiguous_family."""
    ...
    if competitive.get("classification") != "target_family_supported":
        return False
    if family_identity_is_decisive(competitive):
        return False
    competitive["classification"] = "ambiguous_family"
```

```41:54:src/genome_skeptic/agents/diagnostic_needs_v4_1_dev.py
def family_identity_is_decisive(competitive: dict[str, Any]) -> bool:
    ...
    coverage = float(competitive.get("target_family_sequence_coverage") or 0.0)
    if coverage < _DECISIVE_IDENTITY_PRODUCT:  # 0.70
        return False
    conflicts = [str(item).lower() for item in (competitive.get("conflicting_evidence") or [])]
    if any("did not pass the family gate" in item for item in conflicts):
        return False
    return True
```

The second clause is the tetA veto: `discriminate_family` writes `"best competing family did not pass the family gate..."` when MFS/RND fail the family gate (i.e. they are *not* alternative identities), then `family_identity_is_decisive` treats that same string as non-decisive, `refine_weak_family_classification` relabels `target_family_supported` → `ambiguous_family`, and `family_detects_orthologue` returns False.

---

## CASE 13 — tetA GCF_056269845.1 (routine)

### A. Independent truth

POSITIVE, ADJUDICATED, concordant.

- Route 1: `target_family_supported`
- Route 2: tetA HMM prefers target, model coverage 0.991, score 765.6, E 7.5e-235
- Candidate: `orf_06` on `NZ_CM149866.1` `+` 2644493–2646496
- Reference: P02980 (Tn10 TetA class B); identity 0.998; coverage 1.0
- Independent BLASTX of P02980 vs the locked assembly: 99.751% over 401 aa at 2644894–2646096, E=0
- Competitor BLASTX finds genuine MFS proteins (MdfA P0AEY8 100% at a *different* locus 2966858–2965629). Those are not the truth candidate.

Signal in assembly: **YES_CLEAR**.

### B–C. Frozen initial core

Candidate detected: **YES**. Frozen reconstruction:

- contig `contig_1` `+` 2644818–2646096 (same locus as truth BLASTX)
- architecture `close_paralogue` despite `multiplicity.n_loci=1`
- sequence identity 0.99751, protein coverage 1.0, HMM coverage 0.9929, score 766.5
- hierarchy: `exact_strong_homolog`, `multi_reference_protein_homolog`, `profile_hmm_family_match`
- two supporting members (P02980 0.99751/1.0; P02982 0.472/0.950)

### D. Follow-up actions

| Arm | Actions | Discriminating result |
|---|---|---|
| GS-Det | competitive_family; edges; contamination | competitive_family summary: `target_family_supported`, `supports_orthologue=True`; status NO_NEW_INFORMATION (already in m0) |
| Qwen | competitive_family | same |
| Sol | HMM search (22 new hits) then competitive_family | same classification; extra hits did not change architecture or endpoint |
| Exhaustive | competitive_family; edges; contamination; HMM search | same |

CORRECT_EVIDENCE_RECOVERED_BY_ANY_ACTION: **YES** (`competitive_family` / initial `discriminate_family`). Target combined_score 0.9839 vs MFS 0.0053 / RND 0.0039. Competitors failed the family gate.

### E. Propagation

FULLY_PROPAGATED as numeric scores into `family_evidence.reconstruction.competitive_family`. Then `refine_weak_family_classification` overwrote `classification` to `ambiguous_family` and appended “target family support is not sequence-decisive”. Final `supports_orthologue=False`.

### F. Validator rule

Branch taken: `family_identity_is_decisive` False (conflict string “did not pass the family gate”) → `ambiguous_family` → `family_detects_orthologue` False → `classify_polarity` `target_gene_not_detected`. Pairwise 99.8% identity cannot restore presence after that veto.

PRIMARY: **VALIDATOR_DECISION_LIMIT / FAMILY_STATE_SEMANTICS**

TETA mechanism: **B** (family distinguished; validator ignored/relabelled it).

COULD_A_DIFFERENT_LLM_ACTION_HAVE_FIXED_THIS_WITH_THE_EXISTING_TOOLBOX: **NO**. Exhaustive and Sol both acquired the target-supporting competitive scores and still produced NEGATIVE.

MINIMAL_CONCEPTUAL_RESCUE: **VALIDATOR_RULE_CHANGE_REQUIRED** — do not treat “competitors failed the family gate” as non-decisive, and/or do not let `ambiguous_family` override `exact_strong_homolog`. CONFIDENCE: HIGH.

---

## CASE 14 — tetA GCF_060343445.1 (routine)

### A. Truth

POSITIVE. P02982 identity 0.257, coverage 0.931; HMM coverage 0.834, score 121.7; competitor HMM coverage 0.0. Locus `NZ_CP160882.1` `+` 249659–251545. Signal: **YES_WEAK_OR_DIVERGENT**.

### B–C. Initial core

Candidate detected: **YES**. Reconstruction `contig_1` `+` 249960–251223; architecture `divergent_full_length`; HMM 122.7 / 0.860; best member identity 0.2465 coverage 0.893; family gate passed.

### D–F. Follow-up and validator

`discriminate_family`: target_family_supported, score 0.6348, HMM 122.7, competitors ≤0.0063 and failed the family gate. Then refine_weak → `ambiguous_family` (here `target_family_sequence_coverage=0.0998 < 0.70` *and* the gate-conflict string). Final supports_orthologue=False. All arms NEGATIVE.

CORRECT_EVIDENCE_RECOVERED: **YES** (HMM preference over MFS is present in locked competitive scores). The frozen measurements *did* distinguish target from the competing MFS panel; the sequence-decisive coverage gate then discarded that distinction.

TETA: **B**. LLM fix: **NO**. Rescue: **VALIDATOR_RULE_CHANGE_REQUIRED**. Confidence HIGH.

---

## CASE 19 — tetA GCF_054552735.1 (routine)

### A. Truth

POSITIVE. P02982 identity 0.449, coverage 0.99; HMM 0.739 / 280.6. Locus `NZ_JBTOKU010000021.1` `-` 28418–30147. Signal: **YES_WEAK_OR_DIVERGENT**.

### B–C. Initial core

Detected: **YES**. Reconstruction `contig_21` `-` 27100–29795; architecture `close_paralogue` with n_loci=1; HMM 280.3 / 0.739; two supporting members (P02980 0.387/0.758; P02982 0.452/0.777). Candidate protein length 858 aa (window longer than a canonical TetA ORF).

### D–F

competitive_family: target_family_supported, score 0.6919, competitors ≤0.0036. refine_weak → ambiguous_family (`tgt_scov=0.408 < 0.70` plus gate-conflict). All arms NEGATIVE.

TETA: **B**. LLM fix: **NO**. Primary: VALIDATOR_DECISION_LIMIT / FAMILY_STATE_SEMANTICS. Contributing: reconstructed window is long (858 aa), which depresses competitive sequence-coverage used by `family_identity_is_decisive`. Rescue still VALIDATOR_RULE_CHANGE_REQUIRED (do not require 0.70 candidate-as-query coverage after HMM 280 and failed competitors). HIGH.

---

## CASE 36 — tetA GCF_058409085.1 (routine)

### A. Truth

POSITIVE. P02982 identity 0.945, coverage 0.997; HMM 0.998 / 722.3. Locus `NZ_JBZGEN010000002.1` `+` 124729–126726. Signal: **YES_CLEAR**.

### B–C. Initial core

Detected: **YES**. Reconstruction `contig_2` `+` 125057–126326; identity 0.942, coverage 1.0, HMM 722.0 / 0.998; hierarchy includes `exact_strong_homolog`. Frozen homology_support=0.9298.

### D–F

Same tetA veto: target_family_supported (margin 0.9765 vs MFS 0.0063) relabelled ambiguous_family because competitors failed the family gate. Exact-strong homolog still cannot restore POSITIVE. All arms NEGATIVE.

This case, with case 13, shows the failure is not remote-homology sensitivity. The scientific core already had a near-identity TetA call.

TETA: **B**. LLM fix: **NO**. VALIDATOR_DECISION_LIMIT / FAMILY_STATE_SEMANTICS. HIGH.

---

## CASE 37 — tetA GCF_059878295.1 (routine)

### A. Truth

POSITIVE. P02982 identity 0.286, coverage 0.889; HMM 0.865 / 150.2. Locus `NZ_CM187609.1` `+` 670760–672751. Signal: **YES_WEAK_OR_DIVERGENT**.

### B–C. Initial core

Detected: **YES**. Reconstruction `contig_1` `+` 671154–672354; HMM 150.6 / 0.855; architecture `close_paralogue`. Frozen multiplicity is *not* identical across arms: Qwen n_loci=3, Det/Exhaustive n_loci=7 after extra protein searches. The truth locus remains the leading reconstructed locus in every arm.

### D. Follow-up

Exhaustive uniquely ran `search_target_proteins_diamond` and `search_target_proteins_mmseqs` (INFORMATIVE). Those added extra MFS-like loci. Competitive scores on the reconstructed candidate still preferred tetA 0.670 vs 0.004. Sol added HMM hits; n_loci=3 like Qwen. Endpoint identical.

### E–F

Same refine_weak veto (`tgt_scov=0.1375 < 0.70`). Extra instruments changed copy-number state, not polarity.

TETA: **B**. LLM fix: **NO**. This is the strongest model-invariance counterexample among tetA errors: Exhaustive executed every eligible follow-up, increased n_loci, and still produced NEGATIVE. HIGH.

---

## CASE 41 — tetA GCF_056613625.1 (challenge)

### A. Truth

POSITIVE. P02980 identity 0.252, coverage 1.0; HMM 0.832 / 113.1. Locus `NZ_JBWRAH010000012.1` `-` 449763–451594. Signal: **YES_WEAK_OR_DIVERGENT**.

### B–F

Detected: **YES**. Reconstruction `contig_12` `-` 450084–451272; HMM 114.8 / 0.863; competitors 0.0032. target_family_supported → ambiguous_family. All arms NEGATIVE.

TETA: **B**. LLM fix: **NO**. VALIDATOR_DECISION_LIMIT / FAMILY_STATE_SEMANTICS. HIGH.

---

## CASE 44 — tetA GCF_056539405.1 (challenge)

### A. Truth

POSITIVE. P02982 identity 0.397, coverage 1.0; HMM 0.853 / 274.2. Locus `NZ_JBQFUX010000012.1` `+` 96750–98624. Signal: **YES_WEAK_OR_DIVERGENT**.

### B–F

Detected: **YES**. Reconstruction `contig_12` `+` 97075–98338; HMM 279.2 / 0.931; two supporting members; competitive score 0.7992 vs 0.004. Same refine_weak veto (`tgt_scov=0.444 < 0.70`). All arms NEGATIVE.

TETA: **B**. LLM fix: **NO**. HIGH.

---

## CASE 48 — rpoB GCF_055389225.1 (routine)

### A. Truth

POSITIVE. P37870 identity 0.837, coverage 1.0; HMM 0.885 / 1610.5; reason `full_length_rpoB_orthologue`. Locus `NZ_AP044037.1` `+` 2258450–2263777. Signal: **YES_CLEAR**.

### B. Assembly signal

Independent BLASTX of NP_418414.1 hits the same contig at 2260484–2262034 (partial HSP of a longer gene). Truth ORF spans 2258450–2263777. The frozen GS window 2259337–2262880 overlaps the truth locus and is shorter at both ends. This is truncation of an otherwise present gene, not missing sequence.

### C. Initial core

Candidate detected: **YES**.

Frozen measurements (identical across Det/Qwen/Exhaustive/Sol):

- reconstruction `contig_1` `+` 2259337–2262880, protein length 1181 aa, family gate passed, contig_edge False
- `best_hmm`: score 1610.5, E=0, model coverage 0.8845, query coverage 0.9365, four domains
- four supporting family members; best identity 0.67389 coverage 0.963 (S. pyogenes WP_506804874.1)
- hierarchy: `exact_strong_homolog`, `multi_reference_protein_homolog`, `profile_hmm_family_match`
- competitive_family: `target_family_supported` (no packaged rpoB competing families; score 0.8019, target HMM coverage 0.8845, sequence coverage 0.813)
- **architecture = `domain_only`**, `domain_only=True`, `supports_orthologue=False`
- reconstruction.hmm_coverage = **0.4038**, which is the value used by `classify_architecture` (`0 < hmm_cov ≤ 0.45` → domain_only)

The same ORF carries two HMM coverages in TargetMeasurements: `best_hmm.model_coverage=0.8845` and `reconstruction.hmm_coverage=0.4038`. Only the latter sets architecture.

### D. Follow-up

| Arm | Actions | Effect |
|---|---|---|
| Qwen | inspect_contig_edges_for_target | INFORMATIVE (edge flags); architecture unchanged |
| Sol | search_target_domains_hmmer (20 new hits) then inspect_contig_edges | extra hits; architecture still domain_only |
| Exhaustive | edges; contamination | no competitive_family (rpoB declares no competing families); architecture unchanged |
| Det | edges; contamination | same |

CORRECT_EVIDENCE_RECOVERED: **YES** (initial family HMM and member search). Additional Sol HMM search did not repair architecture.

No eligible frozen action recomputes reconstruction architecture from `best_hmm`.

### E. Propagation

HMM/member/competitive evidence FULLY entered TargetMeasurements. Architecture was labelled `domain_only` from reconstruction.hmm_coverage. `collect_family_evidence` then forces `domain_only=True` and `supports_orthologue=False` when reconstruction architecture is `domain_only` (`family_orthology.py` reconstruction override).

### F. Validator rule

`family_detects_orthologue` returns False immediately on `domain_only`, *before* inspecting `target_family_supported` or `supports_orthologue`. `classify_polarity` then has no pairwise-similarity rescue. There is **no legal route to POSITIVE** from this frozen state.

Identity 0.67 is above the AA strong-hit floor (0.60) and coverage 0.96 is above 0.80, but those hits cannot restore presence after the family veto.

PRIMARY: **VALIDATOR_DECISION_LIMIT / FAMILY_STATE_SEMANTICS**, with a contributing reconstruction-coverage mismatch (representation of HMM coverage in `reconstruction.hmm_coverage` versus `best_hmm`).

LLM fix: **NO**. Sol already ran the extra HMM instrument that Qwen omitted; endpoint unchanged.

Rescue: **VALIDATOR_RULE_CHANGE_REQUIRED** (do not call domain_only, and do not short-circuit, when `best_hmm.model_coverage` is 0.88 and exact_strong_homolog is already on the hierarchy). Secondary: **TARGETMEASUREMENT_REPRESENTATION_CHANGE_REQUIRED** to stop storing two conflicting HMM coverages. HIGH.

---

## Cross-error mechanism (tetA)

All seven tetA errors share one path:

1. Independent truth finds a TetA/TetB-class candidate in the assembly (identity 0.25–0.998).
2. Frozen family core reconstructs that locus; HMM prefers tetA; MFS/RND combined scores are ~0.004.
3. `discriminate_family` returns `target_family_supported` and the action observation records `supports_orthologue=True`.
4. `refine_weak_family_classification` relabels the stored classification `ambiguous_family`.
5. `family_detects_orthologue` treats `ambiguous_family` as a hard negative.
6. Extra LLM-chosen or Exhaustive instruments change hit counts, not polarity.

Generic MFS evidence was **not** treated as target evidence. The target family *was* distinguished. Remote HMM support did **not** override family identity; the opposite occurred: family identity was computed and then discarded.

Truncation: case 19 used an 858-aa window; others reconstructed ~396–426 aa, near the 399–401 aa references. Truncation is not the common cause.

---

## LLM-failure hypothesis

For every error, Exhaustive executed every eligible registered follow-up and produced the same wrong endpoint. Sol changed Planner action on all eight errors and Critic behaviour on all eight, added follow-up evidence on all eight, and changed endpoint on 0/8.

ACTION_SELECTION_FAILURE is therefore **not causal**.

COULD_A_DIFFERENT_LLM_ACTION_HAVE_FIXED_THIS_WITH_THE_EXISTING_TOOLBOX: **NO / 8**.
