# ROLE-SWAP CASE SELECTION PROCEDURE — FROZEN AT STOP 2

**Status:** Procedure locked. **Cases not selected.**  
**Target:** `tetA_tetracycline_efflux` only.  
**Target N:** 20 resolved cases = 10 POSITIVE + 10 NEGATIVE after truth lock.

Do not execute this procedure until STOP 2 is cleared and Phase 2 is
explicitly authorised. Selecting cases now would violate the freeze order.

---

## PRINCIPLES

1. Cases must be **fresh** relative to all development and prior evaluation
   cohorts listed below.
2. Do **not** select cases using Genome Skeptic arm outputs, Sol, Jev, or the
   deterministic validator polarity as the selection label.
3. Truth is assigned only under `ROLE_SWAP_TRUTH_PROTOCOL.md`, after candidates
   are chosen.
4. Uncertain truth → exclude from the 10+10 resolved set; draw replacements
   under this same frozen procedure.
5. No scientific tuning after case selection.

---

## HARD EXCLUSION SET (BUILD AND HASH BEFORE SAMPLING)

Exclude any assembly accession (and any case previously binding that accession
to tetA) that appears in:

| Source | What to exclude |
|--------|-----------------|
| M60 | All 30 tetA positions / accessions |
| D8 / D12 | All tetA cases |
| D20 | Entire D20 **candidate pool** accession list (results/labels not opened) |
| Cohort C / early external pilots | All tetA-labeled cases |
| decision_authority_poc_v5 | All DA01–DA10 accessions |
| known_failure_rescue_v5 | All rescue / control accessions |
| model_poc / single_rescue / other V5 PoCs | All tetA accessions used |
| Family reference sources | Genomes/proteins used as packaged family members or truth-source references for tetA / mfs / rnd panels where identifiable |
| Duplicate accessions | Already selected into this study |

Write `02_CASES/ROLE_SWAP_EXCLUSION_MANIFEST.json` with SHA256 **before** any
candidate is accepted. Selection aborts if an accession is later found in the
exclusion set.

---

## ELIGIBLE POOL (METADATA ONLY)

1. Source: current RefSeq bacterial `assembly_summary.txt`.
2. Apply exclusion manifest first.
3. Keep GCF latest Full assemblies at Complete Genome, Chromosome, Scaffold,
   or Contig level; not excluded from RefSeq; named genus.
4. Freshness cutoff: `seq_rel_date >= 2025-01-01` (metadata filter only;
   identical calendar rule to M60 — not a biological-threshold change).
5. While building the pool: no gene-content lookup that opens GS predictions;
   no opening of prior study truth labels for excluded cohorts beyond the
   accession exclusion list.

---

## BALANCED CLASS CONSTRUCTION

Goal: 10 independently established POSITIVE + 10 NEGATIVE.

### Allowed enrichment (non-GS)

To achieve class balance for a sparse mobile gene, candidate enrichment may use
**independent** specialist resources, for example:

- CARD / ResFinder / NCBI AMRFinder **reference annotations for enrichment
  shortlists only**
- Literature / curated strain lists with known tet(A)/tet(B) presence or
  documented absence

Enrichment shortlists are **not** final truth. Every accepted case must still
pass Routes 1–2 under the frozen truth protocol.

### Forbidden enrichment

- Ranking or accepting cases because GS / Sol / Jev predicted POSITIVE or
  NEGATIVE
- Preferring genomes known to be residual V5 failures (those accessions are
  already excluded via M60 / known-failure lists)
- Manufacturing synthetic genomes or editing assemblies for class balance

### Diversity preferences

- Prefer unique genus across the 20 cases when feasible
- Prefer mix of Complete/Chromosome and Scaffold/Contig
- Prefer taxonomic spread (family/order) when filling

### Deterministic ranking keys (when oversubscribed)

Within an enrichment stratum, rank by:

`SHA256("ROLE_SWAP_TETA|20260922|<stratum>|<assembly_accession>")`

ascending, accession as final tie-break. Stratum ∈
`{POS_ENRICH, NEG_ENRICH, OPEN_POOL}`.

---

## CHALLENGE / AMBIGUITY PRESREEN (OPTIONAL, DISCLOSED)

M60 used frozen deterministic instruments as a **selection device** for a
challenge stratum. For this study:

- Default: **do not** run GS instruments for selection.
- If, and only if, independent enrichment cannot fill 10+10 after a documented
  open-pool attempt, a single optional challenge fill may use frozen V5
  deterministic instruments solely to compute a pre-registered ambiguity score
  on a candidate pool that is still exclusion-clean.
- That prescreen is **not** an arm result, not truth, and not Sol/Jev.
- If used, record `challenge_prescreen_used: true` and the candidate-pool
  manifest hash in the caseset lock.

---

## ACCEPTANCE INTO CASESET

A candidate becomes a locked case only when:

1. Accession passes exclusion checks.
2. Assembly FASTA SHA256 recorded.
3. Truth Routes 1–2 resolve to POSITIVE or NEGATIVE (not UNCERTAIN).
4. Running totals do not exceed 10 POS / 10 NEG.
5. Diversity constraints satisfied or explicitly waived with reason in the lock.

Write:

- `02_CASES/ROLE_SWAP_CASESET.csv`
- `02_CASES/ROLE_SWAP_CASESET_LOCK.json`

Then STOP 3.

---

## CURRENT STATE

```
CASES SELECTED: NO
CASESET EXISTS: NO
TRUTH LOCKED: NO
EXCLUSION MANIFEST WRITTEN: NO
```

Procedure hash will be recorded in `01_FREEZE/ROLE_SWAP_FREEZE_MANIFEST.json`
after this file is frozen.
