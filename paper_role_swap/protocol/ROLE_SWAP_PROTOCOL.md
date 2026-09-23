# ROLE-SWAP STUDY PROTOCOL — tetA-ONLY (WITHIN-TASK)

**Study ID:** `ROLE_SWAP_TETA_V5_WITHIN_TASK`  
**Phase:** 1 FREEZE (STOP 2 — cases not yet selected)  
**Date locked:** 2026-09-22  
**Parent scientific freeze:** `GENOME_SKEPTIC_V5_VALIDATOR_REPAIR`

---

## CLAIM SCOPE (BINDING)

This study is a **within-task** architecture role-swap confirmation on a single
biological endpoint:

> `tetA_tetracycline_efflux` — presence/absence of genuine frozen tet(A)/tet(B)
> family membership.

It does **not** claim cross-task replication. It does **not** add a second
biological target. It does **not** modify V5 biology, thresholds, validators,
reference panels, action registry, or planner/critic prompts.

Manuscript-facing interpretation, if results support the pattern, must remain
conditional and architectural for this task only. Do not generalise to “all
biological decision tasks.”

---

## HYPOTHESES (DO NOT ASSUME TRUE)

**H1:** LLM-guided evidence acquisition with a deterministic final decision
layer will be at least as reliable as fixed deterministic control while
permitting adaptive evidence acquisition.

**H2:** Giving the same LLM final biological decision authority over the same
scientific evidence will introduce more degradations, unresolved calls, or
FP/FN decisions than keeping the final decision explicit and deterministic.

Primary comparison: **same model, different roles** (controller vs final judge),
not Sol vs Jev vs Qwen.

---

## BIOLOGICAL ENDPOINT (FROZEN)

| Field | Value |
|-------|-------|
| Target ID | `tetA_tetracycline_efflux` |
| Display | tet(A)/tet(B) family membership |
| Family definition | `data/target_families/tetA_tetracycline_efflux/family.yaml` |
| Members | UniProt P02980 (class B), P02982 (class A) |
| Competitors | `mfs_multidrug_efflux`, `rnd_efflux` |
| POSITIVE | Genuine frozen tet(A)/tet(B) family membership |
| NEGATIVE | No such membership (competitor-only, other tet classes, absent, ambiguous-as-absent under truth rules — see truth protocol) |
| Not POSITIVE | Generic MFS/RND; other tet classes; domain-only; remote HMM alone |

Scoring map for deterministic arms:

- GS `target_gene_detected` → PRESENT / POSITIVE
- GS `target_gene_not_detected` → ABSENT / NEGATIVE
- Failed / incomplete run → scored incorrect against resolved truth (same as M60)

Sol-as-judge outputs: `PRESENT` | `ABSENT` | `UNRESOLVED` only.

---

## DESIGN SUMMARY

| Item | Value |
|------|-------|
| Tasks | 1 (`tetA_tetracycline_efflux`) |
| Cases | 20 (10 POSITIVE + 10 NEGATIVE), after truth lock |
| Freshness | Required vs development / M60 / DA / known-failure / D20 pool / reference sources |
| Scientific core | Frozen V5 — no modification |
| Primary model | `gpt-5.6-sol`, `reasoning=high` |
| Optional controller | Jev / TypeSafe (Arm F) — planner/critic only |
| Tuning after case selection | **FORBIDDEN** |

---

## PHASE ORDER AND STOP RULES

| Stop | After | Gate |
|------|-------|------|
| STOP 1 | Target audit | Passed: only 1 mature task; tetA-only confirmed |
| **STOP 2 (this document)** | Protocol, truth rules, arms, case-selection procedure, scientific freeze hashes | **Halt before selecting cases or running tools** |
| STOP 3 | 20 cases selected + truth locked | Halt before arm execution |
| STOP 4 | All predictions locked | Halt before scoring / unblinding |

No scientific component may change after STOP 2. Any change → new version + new cases.

---

## ARMS (SEE ALSO ROLE_SWAP_ARMS.md)

| Arm | Controller | Measurements | Final decision |
|-----|------------|--------------|----------------|
| A | Fixed deterministic follow-up policy | Deterministic tools | Deterministic validator |
| B | Sol planner + Sol critic | Deterministic tools | Deterministic validator |
| C | Exhaustive eligible registered actions | Deterministic tools | Deterministic validator |
| D | *(none — reuse Arm B final evidence)* | Identical to B | Sol judge |
| E | Sol full authority (same as D when D uses B evidence) | Identical to B | Sol judge |
| F (optional) | Jev planner/critic | Deterministic tools | Deterministic validator |

**Critical role-swap:** Arm B vs Arm D share identical final evidence; only final
decision authority differs.

---

## COMMON INITIAL EVIDENCE

For every case, run the frozen deterministic **initial measurement stage once**
to produce `INITIAL_EVIDENCE_STATE`. That state is shared by all arms as the
pre-follow-up baseline. No model sees truth.

---

## INTEGRITY CONSTRAINTS

1. Truth independent of Genome Skeptic endpoint, Sol, Jev, and the deterministic
   validator under evaluation.
2. Models never receive truth labels.
3. No post-selection scientific tuning.
4. Prospective cases previously used in development / M60 / DA / known-failure /
   D8 / D12 / D20 pool / reference-source genomes: **0**.
5. Predictions locked before scoring.
6. Within-task claim only.

---

## OUTPUTS (AFTER EXECUTION — NOT YET CREATED)

Required after full run (Phases 3–20): case-level, headline, task summary,
authority discordance, controller efficiency CSVs; figures 1–4; results and
integrity markdown; manifest with SHA256.

At STOP 2 these result artifacts must not exist yet.

---

## FREEZE POINTERS

- Scientific hashes: `../01_FREEZE/ROLE_SWAP_FREEZE_MANIFEST.json`
- Truth rules: `ROLE_SWAP_TRUTH_PROTOCOL.md`
- Arms: `ROLE_SWAP_ARMS.md`
- Case selection procedure (no cases): `ROLE_SWAP_CASE_SELECTION.md`
- STOP 2 notice: `../01_FREEZE/ROLE_SWAP_STOP2.md`
