# ROLE-SWAP ARMS — FROZEN AT STOP 2

Target: `tetA_tetracycline_efflux` only.  
Scientific measurements: frozen V5 deterministic instruments only.  
No V5 biology changes.

---

## SHARED CONSTRAINTS

1. All arms start from the same per-case `INITIAL_EVIDENCE_STATE` (frozen
   deterministic initial measurement stage, run once).
2. Follow-up scientific tools remain deterministic.
3. No model may invent evidence IDs; Sol-judge must cite existing evidence IDs
   from the packet (max 3).
4. Models never receive truth.
5. Arm D must **not** re-run tools; it consumes Arm B’s final evidence state.

Follow-up limits (frozen V5):

| Limit | Value |
|-------|------:|
| Planner max actions | 1 |
| Critic max additional actions | 1 |
| Max exhaustive actions | 32 |

---

## ARM A — DETERMINISTIC CONTROL

| Role | Actor |
|------|-------|
| Controller | Fixed deterministic follow-up policy (`POLICY_DETERMINISTIC` / GS_DETERMINISTIC_V5 path) |
| Planner / Critic | None |
| Measurements | Deterministic tools |
| Final decision | Deterministic validator |

Purpose: non-agentic reference.

---

## ARM B — SOL AS CONTROLLER (PRIMARY CONTROLLER ARM)

| Role | Actor |
|------|-------|
| Planner | `gpt-5.6-sol`, reasoning=`high` |
| Critic | `gpt-5.6-sol`, reasoning=`high` |
| Measurements | Deterministic tools |
| Final decision | **Deterministic validator** |

Model may choose evidence acquisition. Model may **not** make the final
biological call.

Config file: `config/sol56_high_posthoc.yaml`  
Harness adapter: `scripts/model_poc_v5/sol_adapter.py` (`SOL_REASONING_EFFORT=high`)  
Planner/critic system prompts: frozen `AGENTIC_REASONER_SYSTEM` /
`AGENTIC_CRITIC_SYSTEM` (hashes in freeze manifest).

---

## ARM C — EXHAUSTIVE + DETERMINISTIC JUDGE

| Role | Actor |
|------|-------|
| Controller | Exhaustive eligible registered actions (`POLICY_EXHAUSTIVE`) |
| Planner / Critic | None |
| Measurements | Deterministic tools |
| Final decision | Deterministic validator |

Purpose: performance ceiling of the current deterministic toolbox without
model routing.

---

## ARM D — SOL AS FINAL BIOLOGICAL JUDGE (CRITICAL ROLE-SWAP)

| Role | Actor |
|------|-------|
| Evidence | **Exact** final evidence state from Arm B |
| Tools | Do **not** re-run |
| Final decision | `gpt-5.6-sol`, reasoning=`high` |

Allowed answers only: `PRESENT` | `ABSENT` | `UNRESOLVED`.

Required structured fields (Phase 11 grounding):

- `endpoint`
- `target_support_state`
- `competitor_support_state`
- `evidence_sufficient` (YES/NO)
- up to 3 existing `evidence_ids` from the packet

Reject invented evidence IDs. Record invalid references and internally
inconsistent judgments.

Therefore Arms B and D share: same case, same model controller history, same
planner/critic decisions, same follow-ups, same final evidence, same scientific
measurements — **only final decision authority differs**.

---

## ARM E — SOL CONTROLLER + SOL JUDGE (FULL AUTHORITY)

Derived from Arm D when Arm D already uses Arm B evidence.

Do not duplicate Sol controller calls. Label conceptually:

`SOL_FULL_AUTHORITY`

Purpose: compare end-to-end agent architecture vs hybrid controller +
deterministic judge (Arm B).

Numerically, Arm E decision ≡ Arm D decision for this design.

---

## ARM F — OPTIONAL — JEV AS CONTROLLER

| Role | Actor |
|------|-------|
| Planner / critic / second-action | Jev (TypeSafe) via native Choice / Noul |
| Measurements | Deterministic tools |
| Final decision | **Deterministic validator** |

Jev does **not** receive final biological authority in the primary comparison.

Purpose: test whether an inexpensive typed decision model can replace a large
LLM for constrained workflow control.

If Arm F is not run, report `JEV_CONTROLLER: NOT_RUN` in results; do not invent
numbers.

---

## SCORING COMPARISONS (POST STOP 4)

### Primary (final-authority isolation)

Arm B vs Arm D: corrections, degradations, McNemar, paired bootstrap.

### Controller value

Arm A vs Arm B vs Arm C: decision quality, follow-up counts, efficiency.

### Within-task only

All headline metrics are for `tetA_tetracycline_efflux`. No pooled multi-task
claim. `TASK_ROLE_SUMMARY` / per-task tables contain a single task row.
