# Project chronology

Clocks used here:

- **JSON `created_utc` / `hashed_utc`**: operational scientific timestamps recorded in artifacts
- **Git author dates**: repository packaging times (see provenance flag in `PROVENANCE_VERIFICATION.md`)

All dates below are UTC unless marked otherwise. Seed used across D8/D12/M60 sampling: `20260920`.

**Never mix post-hoc analyses into the prospective primary study.**

---

## A. DEVELOPMENT (before M60 predictions)

These events informed system design, endpoint choice, and freeze. Results of D8/D12 **were visible** to developers. That is expected for development and is a researcher-degrees-of-freedom issue for M60 (see `04_DEVELOPMENT_HISTORY.md`).

| When (UTC, 2026-09-20 unless noted) | Event | Results visible? |
|---|---|---|
| Earlier (pre-tag) | Internal V3/V4/V4.1 development; family instruments; D8/D12 case selection; V4.1 D12 replay scripts exist in freeze tree (`scripts/run_d12_v4_1_dev_replay.py`) | YES (development) |
| 01:52:36 | `M60_EXCLUSION_MANIFEST.json` written. `m60_cases_selected: false`. Includes D8×8, D12×12, D12 pool, D20 pool×40, prior cohorts, family reference organisms. SHA256 `7fe225d0…` (CRLF working-tree / sidecar convention) | Exclusion lists visible; no M60 cases yet |
| 01:52:49 | Freeze manifest `GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json`. `development_closed: true`, `m60_cases_selected: false`, `d20_touched: false`. Scientific-core hash `22ff045c…` | Freeze identity visible; no M60 predictions |
| 01:52:50 | Freeze manifest sidecar hashed | |
| ~01:52 | `TARGET_READINESS.md` records tetA/rpoB **READY**, tuf/lacZ **NOT READY**, citing D12 development positions. States M60 not yet selected | Development outcomes visible; used to drop tuf/lacZ from M60 |
| 02:01:32 | Git commit `8f66868850a98494778966bd729b88a6fc2952eb` + annotated tag `GENOME_SKEPTIC_V4_1_MANUSCRIPT` (author date). Freeze tree includes D8_MANIFEST, D12_MANIFEST, TARGET_READINESS, V4.1 source, M60_PROTOCOL.md, exclusion | Packaging |
| 02:06:42 | `M60_ENVIRONMENT.json` WSL production snapshot. Python 3.11.16; BLAST+ 2.16.0+; HMMER 3.4; MMseqs 18.8cc5c; DIAMOND 2.2.6; AMRFinder 4.2.7 / DB 2026-08-07.1. `m60_cases_selected: false` | Environment only |
| 02:11:01 | `M60_ELIGIBLE_POOL.json` n=104,291 | Metadata pool; no case outcomes |
| 02:11:59 | `M60_CHALLENGE_CANDIDATE_POOL.json` n=48 | Challenge *candidates*, not final 30 |
| 11:14:11 | Agentic V2 freeze `GENOME_SKEPTIC_AGENTIC_V2_D20` (qwen3:4b digest `359d7dd4…`, Q4_K_M) — D8 used this agentic freeze | Development freeze |
| 11:23:18 | D20 `candidate_pool_manifest.json` `created_utc` (40 candidates). Same SHA256 already cited in 01:52 exclusion | Pool accessions for exclusion only |
| 11:35:00 | D20 Gate 1 V5 prescreen **BLOCKED** after 1/40. Final D20 cohort **never locked** | Partial D20 V5 prescreen exists on disk; M60 artifacts say `d20_touched: false` / `d20_results_opened: false` |
| 12:43:42 | D8_MANIFEST `created_utc` (8 cases). File already present in freeze commit — **timestamp vs git-author-date disagreement** | D8 selection |
| 15:33:24 | Agentic V3 freeze `GENOME_SKEPTIC_AGENTIC_V3_EXTERNAL` | Development freeze |
| 16:58:41 | D12_MANIFEST `created_utc` (12 cases). SHA256 identical in freeze commit and working tree — **same timestamp disagreement** | D12 selection |

**D8 results** (after D8 predictions + truth; files published in later git commit `e92e59d`): Conventional 3/8, V5 3/8, Agentic V2 3/8. Failures visible: tetA family FP, tuf multiplicity 0, lacZ FP, 2 agentic execution failures. **Results were visible during development of later versions.**

**D12 results**: Conventional 5/12, V5 6/12, Agentic V3 6/12; endpoints identical V5 vs Agentic 12/12. Dual errors: tetA validator/FAMILY contract, tuf multiplicity, lacZ missing instrument. **Used for V4.1 tetA readiness and for excluding tuf/lacZ from M60.**

V4.1 manuscript freeze claims `d8_rerun: false`, `d12_rerun: false` (no post-freeze re-execution of those campaigns as manuscript tuning).

---

## B. PROSPECTIVE PRIMARY VALIDATION (M60)

M60 cases were **not** selected at freeze-manifest time (`m60_cases_selected: false` at 01:52). Cohort lock is **03:07:15 UTC**.

| When (UTC) | Event | Results visible? |
|---|---|---|
| 2026-09-20 03:07:15 | `M60_COHORT_MANIFEST.json` lock. 60 cases, seed `20260920`. SHA256 `014950b8…` | Cohort membership visible; **no endpoint predictions** |
| 2026-09-20 03:07:15 | `M60_SELECTION_AUDIT.md`; challenge ambiguity scores n_ok=48 | Prescreen scores visible (deterministic instruments, not Agentic/truth) |
| 2026-09-20 03:08:45 | `MANUSCRIPT_PROVENANCE.json` phase_0_1: `m60_cases_selected: true`, manuscript arms not yet run | |
| 2026-09-20 03:54:40 | AMRFinder DB freeze recorded (`2026-08-07.1`) | Comparator DB frozen before first M60 AMRFinder run (per environment JSON) |
| 2026-09-20 20:40:00 | `MANUSCRIPT_PROVENANCE.json` records git SHA/tag **externally** (freeze JSON not rewritten) | |
| 2026-09-21 (per position locks) | M60 predictions: Conventional, specialist, GS-Det, GS-Agentic Qwen, GS-Exhaustive | **Predictions visible to operators as each position locked**; protocol forbids truth until all 60 locked |
| 2026-09-21 07:34:59 | `M60_PREDICTION_LOCK_MANIFEST.json` SHA256 `5317b33f…` | **Prediction lock. Accuracy not scored.** |
| 2026-09-21 09:23:04 | `PRE_TRUTH_CHAIN.json` verifies freeze/protocol/cohort/prediction-lock hashes. `prediction_payloads_opened: false`, `accuracy_scored: false` | Chain only |
| 2026-09-21 09:23:43 | Truth-source freeze (UniProt/HMM/panels). SHA256 `640138da…` | Reference panels; not labels |
| 2026-09-21 10:01:42 | Original independent truth lock. SHA256 `bb375390…`. tetA 7/18/5; rpoB 15/0/15 | **Truth labels visible; still pre-unblind of system accuracy** if scoring not yet run |
| 2026-09-21 10:10:55–10:10:56 | Human review applied. Position 34 tetA UNCERTAIN→NEGATIVE. Final truth SHA256 `a64dea4f…` | One label change visible |
| 2026-09-21 10:17:58 | Phase 4 one-shot unblind `M60_PHASE4_STOP.json` | **Primary results visible for the first time as a scored table** |

`PREDICTIONS_LOCKED_BEFORE_TRUTH.txt` contains `YES`.

---

## C. POST-HOC ANALYSES (after unblind)

Label these **POST-HOC** in any manuscript.

| When (UTC) | Event | Results visible? |
|---|---|---|
| 2026-09-21 11:00:22 | Sol 5-case preflight manifest SHA256 `7b8ef9e2…`. `truth_opened: false`, `accuracy_scored: false` for that preflight | Behaviour only (5 cases) |
| 2026-09-21 11:39:59 | Full Sol ablation manifest SHA256 `2a9f8695…`. **POST_HOC_MODEL_ABLATION = true** | Sol endpoints/behaviour visible |
| 2026-09-21 12:18:50 | Mechanistic error-analysis manifest. 8 shared errors. **POST_HOC_ONLY** | Forensic interpretation visible |

---

## Explicit: when results were visible

| Class of result | First visibility |
|---|---|
| D8/D12 development outcomes | During development, **before** M60 sampling (TARGET_READINESS cites D12 positions) |
| M60 challenge ambiguity scores | At selection (03:07), **before** manuscript-arm predictions |
| M60 system predictions | During position runs, **before** truth |
| Independent truth labels | After prediction lock |
| Primary accuracy 33/41 | Phase 4 unblind 10:17:58 UTC 2026-09-21 |
| Sol 33/41, 0 endpoint changes | Post-hoc, after unblind |
| Validator-as-root-cause narrative | Post-hoc forensics, after unblind |

If a claim depends on Sol or the 8-case forensics, it is **not** a prospective M60 finding.
