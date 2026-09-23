# PHASE 0 — TARGET AUDIT (ROLE-SWAP CROSS-TASK STUDY)

Status: **STOP 1 — fewer than three mature tasks**

Date: 2026-09-22

Audit basis: on-disk families under `data/target_families/`, validators under
`src/genome_skeptic/validators/`, action catalogs under
`src/genome_skeptic/agents/`, M60 / D8 / D12 / V5 / decision-authority /
known-failure artifacts. `manuscript_benchmark/TARGET_READINESS.md` is treated
as **stale** (pre-M60) and is not authoritative for this audit.

Registry inventory: 8 families. No separate `tetB` target (`tet(B)` exists only
as member P02980 inside `tetA_tetracycline_efflux`).

---

## TARGET: tetA_tetracycline_efflux

SCIENTIFIC CORE COMPLETE: **YES**

- Deterministic measurement: family orthology, competitive family, falsification,
  locus path (`validators/family_orthology.py`, `competitive_family.py`, …)
- Explicit target: `family.yaml` members P02980 (Tn10 TetA class B), P02982
- Explicit competitors: `mfs_multidrug_efflux`, `rnd_efflux`
- Registered follow-ups: shared action catalog; `competitive_family` active when
  competing families are defined
- Deterministic validator: functioning (M60 / DA / known-failure artifacts)
- Independent truth: M60 two-route protocol (`TRUTH_M60`, EXTERNAL_REVIEW docs)

REAL POSITIVES AVAILABLE: **YES** (M60: 7 resolved POSITIVE; additional
historical D8/D12/D20 pool — all DEVELOPMENT/HISTORICAL for fresh selection)

REAL NEGATIVES AVAILABLE: **YES** (M60: 19 resolved NEGATIVE)

INDEPENDENT TRUTH POSSIBLE: **YES**

KNOWN DEVELOPMENT DEFECTS UNRESOLVED: **YES**

- Frozen V4.1 GS tetA sensitivity historically **0/7** on M60 evaluable positives
- V5 repair recovers some; **five residual errors** intentionally frozen
  (positions 14, 19, 37, 41, 44) — `V5_DEVELOPMENT_BOUNDARY.md`,
  `known_failure_rescue_v5/`
- Residual bias must be disclosed; not a reason to invent new scientific rules
  for this experiment

SUITABLE FOR ROLE-SWAP STUDY: **YES** (only mature balanced presence/absence
task; disclose residual FN set; cases must be fresh vs M60/dev/DA/known-failure)

---

## TARGET: rpoB_RNAP_beta

SCIENTIFIC CORE COMPLETE: **YES** (measurement + validator path exist)

REAL POSITIVES AVAILABLE: **YES** (M60: 15 evaluable POSITIVE)

REAL NEGATIVES AVAILABLE: **NO**

- M60: **0** independently resolved negatives; specificity `NA_no_negative_truth`
- Near-universal housekeeping gene → no biologically meaningful natural absence
  class in locked cohorts
- Protocol and EXTERNAL_REVIEW explicitly forbid manufacturing negatives

INDEPENDENT TRUTH POSSIBLE: **YES** for presence; **NO** for balanced
presence/absence

KNOWN DEVELOPMENT DEFECTS UNRESOLVED: **YES** (no negative class; 15/30 M60
truth-uncertain)

SUITABLE FOR ROLE-SWAP STUDY: **NO** as genome-level presence/absence

Locus-level rpoB vs rpoC option:

- Partner/fusion architecture for rpoB queries: supported
- Truth Route 2 may use RpoB vs RpoC profiles: supported for adjudication
- Frozen primary competitive endpoint “classify locus as genuine rpoB orthologue
  vs rpoC / related non-target”: **NOT** registered (`competing_families: []`;
  `competitive_family` inert for rpoB)
- Inventing that task would write new scientific rules → forbidden for this study

---

## TARGET: rpoC_RNAP_beta_prime

SCIENTIFIC CORE COMPLETE: **PARTIAL** (packaged partner family only)

REAL POSITIVES AVAILABLE: **NO** (no primary cohort)

REAL NEGATIVES AVAILABLE: **NO**

INDEPENDENT TRUTH POSSIBLE: **NO** as primary target

KNOWN DEVELOPMENT DEFECTS UNRESOLVED: **YES** (partner-only by design)

SUITABLE FOR ROLE-SWAP STUDY: **NO**

---

## TARGET: tuf_EF_Tu

SCIENTIFIC CORE COMPLETE: **NO** (multiplicity endpoint unreliable; seed issues)

REAL POSITIVES AVAILABLE: **YES** (D8/D12 / Cohort C)

REAL NEGATIVES AVAILABLE: **YES** (D12 multiplicity 0 / absence cases)

INDEPENDENT TRUTH POSSIBLE: **WEAK** (not M60-grade two-route freeze)

KNOWN DEVELOPMENT DEFECTS UNRESOLVED: **YES**

- Exact multiplicity not recovered (D8/D12)
- TARGET_READINESS: NOT READY FOR PRIMARY VALIDATION
- Excluded from M60

SUITABLE FOR ROLE-SWAP STUDY: **NO**

---

## TARGET: lacZ_beta_galactosidase

SCIENTIFIC CORE COMPLETE: **NO** (discriminator power not demonstrated)

REAL POSITIVES AVAILABLE: **YES** (D12 / accessory biology)

REAL NEGATIVES AVAILABLE: **YES** (biological absence common)

INDEPENDENT TRUTH POSSIBLE: **PARTIAL** (ortholog refs exist; weaker than M60)

KNOWN DEVELOPMENT DEFECTS UNRESOLVED: **YES**

- `competitive_ortholog_references` exists but D12 remains unresolved / FP
- TARGET_READINESS: NOT READY FOR PRIMARY VALIDATION
- Excluded from M60

SUITABLE FOR ROLE-SWAP STUDY: **NO**

---

## TARGET: recA_recombinase

SCIENTIFIC CORE COMPLETE: **PARTIAL** (packaged; unvalidated as primary)

REAL POSITIVES AVAILABLE: **NO** (no study cohort)

REAL NEGATIVES AVAILABLE: **NO** (housekeeping; no locked absences)

INDEPENDENT TRUTH POSSIBLE: **NO**

KNOWN DEVELOPMENT DEFECTS UNRESOLVED: **YES** (inventory-only)

SUITABLE FOR ROLE-SWAP STUDY: **NO**

---

## TARGET: mfs_multidrug_efflux

SCIENTIFIC CORE COMPLETE: **YES** as competitor packaging; **NO** as primary
validated endpoint

REAL POSITIVES AVAILABLE: **NO** as primary

REAL NEGATIVES AVAILABLE: **NO** as primary

INDEPENDENT TRUTH POSSIBLE: **PARTIAL** (used in tetA truth panels)

KNOWN DEVELOPMENT DEFECTS UNRESOLVED: **YES** (never primary)

SUITABLE FOR ROLE-SWAP STUDY: **NO** as primary task

---

## TARGET: rnd_efflux

Same pattern as mfs: competitor-only packaging.

SUITABLE FOR ROLE-SWAP STUDY: **NO** as primary task

---

## TARGET: tet(B) as separate task

Does not exist. Member of `tetA_tetracycline_efflux` only.

SUITABLE FOR ROLE-SWAP STUDY: **NO**

---

## STOP 1 VERDICT

**ONLY 1 TASK IS SCIENTIFICALLY READY.**

Mature balanced task count: **1** (`tetA_tetracycline_efflux`).

Do **not** fabricate additional tasks. Do **not** invent rpoB-vs-rpoC locus
classification solely to reach three tasks. Do **not** promote tuf/lacZ without
a new scientific version and fresh instrument demonstration.

---

## STRONGEST DESIGN RECOMMENDATION (AWAITING CONFIRMATION)

### Preferred under current freeze: 1-task role-swap (tetA only)

| Element | Proposal |
|---------|----------|
| Task | `tetA_tetracycline_efflux` only |
| Design | Same five arms (A–E) + optional Jev controller (F) |
| Cases | 20 total: 10 POSITIVE + 10 NEGATIVE, **fresh** vs M60, D8/D12/D20, DA PoC, known-failure rescue, development seeds, reference-source genomes |
| Truth | Lock independent two-route / curated AMR-family truth **before** scoring |
| Defects | Disclose residual V5 FN mechanism as known bias; no post-selection tuning |
| Claim scope | Within-task architecture role-swap; **no** cross-task replication claim |

This preserves the critical comparison (identical evidence; Det judge vs Sol judge)
without false cross-task generality.

### What is *not* recommended as a “2-task” stretch

1. **tetA + rpoB presence-only** — violates IMPORTANT TARGET RULE (no meaningful
   negative class; specificity undefined).
2. **tetA + invented rpoB/rpoC locus task** — requires new scientific rules.
3. **tetA + lacZ or tuf** — instruments not mature; would bake known failures into
   the role-swap.

### Path to a true ≥2-task study (out of scope for this freeze)

Complete a **new scientific version** that repairs at least one additional
balanced endpoint (most natural candidate: lacZ accessory presence/absence),
freeze hashes, then select a fresh multi-task cohort. That is a different
experiment, not a continuation of this Phase 0 freeze.

---

## NEXT STEP

Await explicit confirmation before Phase 1 freeze / case selection.

Options for confirmation:

1. Proceed with **tetA-only 20-case** role-swap under frozen V5 scientific core.
2. Abort role-swap until a second mature task exists.
3. Specify a different frozen task set (must already satisfy Phase 0 criteria).
