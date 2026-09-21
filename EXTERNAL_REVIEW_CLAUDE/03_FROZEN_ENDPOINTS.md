# Frozen endpoints

Manuscript primary endpoints (freeze manifest):

- `tetA_tetracycline_efflux`
- `rpoB_RNAP_beta`

Limitation targets **excluded from M60**: `tuf_EF_Tu`, `lacZ_beta_galactosidase`.

Do not paraphrase away the vetoes. The eight shared M60 errors are produced by these rules.

---

## tetA — presence/absence of genuine frozen tet(A)/tet(B) family membership

Family definition: `data/target_families/tetA_tetracycline_efflux/family.yaml`  
(mirror under `src/genome_skeptic/data/target_families/`).

- Members: UniProt **P02980** (class B), **P02982** (class A)
- Competing packaged families: `mfs_multidrug_efflux`, `rnd_efflux`

**POSITIVE** means the frozen validator claims `target_gene_detected` for this family contract — genuine tet(A)/tet(B) family membership, not generic tetracycline resistance and not any MFS transporter.

**Does NOT count as POSITIVE:**

| Condition | Code |
|---|---|
| Generic MFS / RND competitor preferred | `family_detects_orthologue`: `classification == competing_family_preferred` → False |
| `ambiguous_family` (including after `refine_weak_family_classification`) | `cls in {competing_family_preferred, ambiguous_family}` → False |
| `domain_only` | `family_evidence.domain_only` → False |
| Pairwise identity/coverage after a family veto | `classify_polarity` returns `target_gene_not_detected` once family analysis ran |
| Other tet classes (tet(C), tetA(P), tet(M), …) | Protocol / AMRFinder converter; family members are P02980/P02982 only |
| Remote HMM without passing family-state rules | HMM can support `supports_orthologue` but refine_weak / ambiguous_family still veto |

Protocol v1.1: exact endpoint is identity with frozen tetA family members versus competing MFS/RND.

Independent truth uses the same biological question but **different evidence routes** (sequence panel + HMM/tree). Truth is not the GS validator output.

---

## rpoB — presence/absence of a genuine rpoB orthologue

Family definition: `data/target_families/rpoB_RNAP_beta/family.yaml`

- `competing_families: []` (no competitive-family panel)
- `partner_families: [rpoC_RNAP_beta_prime]`
- Members: frozen RefSeq proteins listed in `family.yaml`

**POSITIVE**: RNA polymerase subunit beta orthologue.

**Does NOT count as POSITIVE:**

| Condition | Notes |
|---|---|
| Domain-only hit | `reconstruction.architecture == domain_only` forces `supports_orthologue=False` |
| Different polymerase subunit (`rpoC`) | Partner/competitor conceptually; not a legal rpoB positive |
| Fusion/split without passing reconstruction rules | Family YAML notes known fusion/split; architecture rules apply |
| PGAP gene-name equality | Comparator only; not truth; not the GS validator |

Protocol: do not manufacture negative rpoB genomes for class balance.

---

## Validator rules (verbatim-level)

### `family_detects_orthologue`

`src/genome_skeptic/validators/family_orthology.py`

For `gene_orthologue` (tetA and rpoB):

1. If `family_evidence.domain_only`: **return False**
2. If competitive classification is `competing_family_preferred` or `ambiguous_family`: **return False**
3. If `family_evidence.supports_orthologue`: **return True**
4. Else fallback `any(strong_hit(...))`

### `classify_polarity`

`src/genome_skeptic/validators/falsification.py`

If family evidence exists for gene_orthologue / protein_family:

- if `family_detects_orthologue`: `target_gene_detected`
- else: `target_gene_not_detected`  
  Comment in source: *Family analysis already ran. Pairwise similarity cannot restore family identity after a competitive-family or domain-only veto.*

### `refine_weak_family_classification`

`src/genome_skeptic/validators/locus_v4_dev.py`

If stored competitive classification is `target_family_supported` **and** `family_identity_is_decisive` is False:

- rewrite classification to `ambiguous_family`
- append conflict string about non-decisive sequence support

This is the tetA M60 error mechanism: `discriminate_family` can return `target_family_supported` with large HMM margin, then refine_weak relabels `ambiguous_family` because competitors “did not pass the family gate” or identity-product is not decisive.

### `family_identity_is_decisive`

`src/genome_skeptic/agents/diagnostic_needs_v4_1_dev.py` (also imported from `diagnostic_needs_v4_dev`)

- `_DECISIVE_IDENTITY_PRODUCT = 0.70`
- `competing_family_preferred` → True
- `target_family_supported` only if coverage ≥ 0.70 **and** no conflict containing `"did not pass the family gate"`

### `domain_only` architecture

`src/genome_skeptic/validators/locus_reconstruction.py`:

If `0 < hmm_cov <= hmm_domain_only_max_model_coverage` (0.45) and not frameshift / multi-contig / edge: `architecture = "domain_only"`.

This uses **`reconstruction.hmm_coverage`**, which can be low (M60 position 48: ~0.40) even when `best_hmm.model_coverage` is high (~0.88).

Then `family_orthology.py` post-collection:

if architecture `domain_only`: `ev.domain_only = True`; `ev.supports_orthologue = False`.

That is the rpoB M60 error mechanism (position 48).

---

## Frozen biological thresholds

`src/genome_skeptic/config.py` (Defaults; freeze lists `biological_thresholds_hash` `c4ef9a30…`):

| Parameter | Value |
|---|---|
| `gene_aa_min_identity` | 0.60 |
| `gene_aa_min_query_coverage` | 0.80 |
| `gene_length_ratio_min` / `max` | 0.80 / 1.20 |
| `hmm_model_coverage_orthologue` | 0.70 |
| `hmm_domain_only_max_model_coverage` | **0.45** |
| `hmm_min_gate_model_coverage` | 0.20 |
| `hmm_full_evalue_max` | 1e-10 |
| `family_competitive_margin` | 0.10 |
| `family_competitive_ambiguous_band` | 0.05 |
| `family_member_min_identity` | 0.35 |
| `family_member_min_coverage` | 0.70 |
| `family_min_supporting_members` | 2 |
| Decisive identity-product (code constant) | **0.70** |

Competitive-family `discriminate_family()` (`competitive_family.py`): gate failures, margin ≥ 0.10 → `target_family_supported`, ≤ −0.10 → `competing_family_preferred`, `|margin|` in ambiguous band → `ambiguous_family`; TM-rich partial HMM can force `ambiguous_family`.

---

## Conventional and specialist converters (not the GS endpoint)

These are **comparators**, with their own binary rules (see `02_SYSTEM_ARCHITECTURE.md` and `M60_PROTOCOL_V1_1.md`). They are not the frozen GS validator contract.

GS binary for scoring: `target_gene_detected` → POSITIVE; `target_gene_not_detected` → NEGATIVE; unresolved/failed → incorrect against resolved truth (`scripts/score_m60_phase4.py`).
