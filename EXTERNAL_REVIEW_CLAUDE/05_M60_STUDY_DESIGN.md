# M60 study design

60 completely fresh genome-target cases.

| Stratum | n |
|---|---|
| tetA routine | 15 |
| tetA challenge | 15 |
| rpoB routine | 15 |
| rpoB challenge | 15 |
| **TOTAL** | **60** |

Verified from `manuscript_benchmark/M60_COHORT_MANIFEST.json`:

- 60 unique accessions
- 60 unique genera
- 60 unique species
- SHA256 `014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655`
- Created `2026-09-20T03:07:15.598486+00:00`
- Seed `20260920`
- Freeze ID `GENOME_SKEPTIC_V4_1_MANUSCRIPT`

CSV: `manuscript_benchmark/M60_COHORT_MANIFEST.csv` (sidecar `8756823e…`).

---

## Eligible pool

- Path: `manuscript_benchmark/M60_ELIGIBLE_POOL.json`
- SHA256: `3d1f95e3c8613a5c7848758d02433518b319b9096103fbfde1a9fcfcd3600d02`
- n_eligible: **104,291** RefSeq bacteria, GCF latest Full, named genus, `seq_rel_date >= 2025-01-01`
- **Gitignored** (large). Hash is recorded in the selection audit and provenance JSON.

---

## Exclusion manifest

- Path: `manuscript_benchmark/M60_EXCLUSION_MANIFEST.json`
- Created: `2026-09-20T01:52:36Z` (**before** cohort selection)
- n_excluded: **183** identifiers
- Script: `scripts/build_m60_exclusion_manifest.py`
- Includes: D8×8, D12×12, D12 candidate pool, D20 candidate pool×40, prior cohorts A/C, family source organisms, internal gate manifests
- Flags: `d20_touched: false`, `d20_results_opened: false`, `m60_cases_selected: false`

D20 contributed **candidate-pool accessions only**. No D20 predictions or labels were read for exclusion construction (stated in the JSON note).

---

## Sampling algorithm (registered prospective procedure)

From `M60_SELECTION_AUDIT.md` / cohort manifest / `scripts/select_m60_cohort.py`:

**Routine** (metadata only; no gene-content / V4.1 score):

- Hash `SHA256("M60_ROUTINE|20260920|<target>|<acc>")`
- 8 complete + 7 draft per target
- Unique accession / genus / species

**Challenge candidate pool:**

- Hash `SHA256("M60_CHALLENGE_POOL|20260920|<target>|<acc>")`
- 12 complete + 12 draft per target
- Disjoint from routine
- Pool file: `M60_CHALLENGE_CANDIDATE_POOL.json` (n=48, `2026-09-20T02:11:59Z`)

**Challenge selection (frozen deterministic ambiguity / prescreen BEFORE predictions):**

- Frozen V4.1 deterministic instruments + unmodified `lock_cohort_d20_final.py:score_case`
- Rank by **higher ambiguity**, tie-break `SHA256("M60|20260920|<target>|<acc>")`
- Fill 8 complete + 7 draft
- `d20_results_opened: false`
- Ambiguity file: `M60_CHALLENGE_AMBIGUITY_SCORES.json` (n_ok=48, n_fail=0)
- Audit: “Not selected because Agentic is expected to fix them.”

**Execution hash:** `SHA256("M60_EXECUTION|20260920|<target>|<acc>")`

Scripts: `scripts/select_m60_cohort.py` (Linux/WSL; `SEED = "20260920"`), `scripts/build_m60_exclusion_manifest.py`, `scripts/m60_env_preflight.py`, `scripts/lock_cohort_d20_final.py` (`score_case` only).

---

## Challenge-selection bias (reviewer issue)

Challenge cases were chosen using **the same frozen V4.1 deterministic core** that later serves as GS-Deterministic. That can enrich for assemblies where Det is already in an ambiguous measurement regime. It is **not** outcome-dependent on Agentic predictions or truth (those did not exist yet). It **is** dependent on Det instruments.

Whether that is “hard cases for the scientific question” or “hidden selection on the Det state” is for the reviewer.

---

## Overlap with D8 / D12 / D20 (recomputed from manifests)

Accession sets loaded from D8_MANIFEST, D12_MANIFEST, D20 `candidate_pool_manifest.json`, and M60_COHORT_MANIFEST.

| Comparison | Accession overlap | (accession, target) overlap |
|---|---:|---:|
| M60 vs D8 | **0** | **0** |
| M60 vs D12 | **0** | **0** |
| M60 vs D20 pool (40) | **0** | **0** |

Matches declared fields `d8_overlap: 0`, `d12_overlap: 0`, `d20_overlap: 0`, `exclusion_overlap: 0`.

Same genus can appear across cohorts on **different targets / different accessions**. Genus+target pairs still did not overlap M60 vs D8/D12 in the audit recompute.

---

## Relationship to D8, D12, D20

| Cohort | Role relative to M60 |
|---|---|
| D8 | Development mini-benchmark; accessions excluded; **not rerun** after freeze |
| D12 | Development / V4.1 replay + external V3 benchmark; accessions excluded; **not rerun** after freeze; informed TARGET_READINESS |
| D20 | **Never locked as a 20-case cohort.** 40-accession candidate pool used for exclusion. Partial V5 prescreen blocked at 1/40. M60 artifacts: `d20_touched: false` |

### D20 filesystem (disclose; do not reuse for this audit)

`external_validation_agentic_d20/`:

- `candidate_pool_manifest.json` — 40 candidates (10 per target including tuf/lacZ)
- SHA256 cited everywhere: `61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c`
- `GATE1_V5_EXECUTION_BLOCK.json` — blocked 2026-09-20T11:35:00Z after SIGKILL on `GCF_048282645.1`
- `v5_prescreen/` — partial run artifacts (**gitignored**)
- **No `D20_MANIFEST.json`**

`d20_touched: false` means: M60 did not open D20 **prediction results or labels**. It does **not** mean the D20 directory was absent or unused for accession exclusion / shared download helpers (`scripts/select_and_download_d20.py`).

Timestamp tension: pool `created_utc` 11:23 UTC is after M60 selection 03:07 UTC, but the **same pool SHA256** is in the 01:52 exclusion manifest. Reviewer should not assume “untouched filesystem”; assume “accession list frozen for exclusion; later download/prescreen timestamps exist.”

---

## Protocol documents

| File | Role |
|---|---|
| `manuscript_benchmark/M60_PROTOCOL.md` | Original protocol (SHA256 `30de5efc…` LF) |
| `manuscript_benchmark/M60_PROTOCOL_V1_1.md` | Pre-selection clarification (SHA256 `73aebeba…` LF); does not replace original |
| `manuscript_benchmark/M60_COMPARATORS_FROZEN.json` | Comparator freeze |
| `manuscript_benchmark/TARGET_READINESS.md` | Endpoint inclusion/exclusion |

V1.1 records executable interpretation, frozen comparators, and truth-assignment rules so sampling cannot be informed by later analysis choices. It states it does **not** change biological logic, thresholds, prompts, routing, validator, arms, or original protocol text.
