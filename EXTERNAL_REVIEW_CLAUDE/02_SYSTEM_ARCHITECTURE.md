# System architecture

## Design rule

LLMs do not generate sequence measurements. Identity, coverage, HMM scores, coordinates, loci, and taxonomy come from deterministic tools. The LLM selects registered analyses and reasons over existing evidence. The deterministic validator has final authority.

Production M60 Agentic uses `config/qwen_agentic_dev.yaml`:

- model `qwen3:4b`
- provider `openai_compatible` (Ollama at `http://localhost:11434/v1`)
- temperature `0.0`
- thinking `false`

Integrity check in `scripts/run_m60_position.py`: `EXPECTED_MODEL = "qwen3:4b"`.

Position locks record Ollama digest  
`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`.

The same digest appears in `agentic_freeze/GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json` with **quantization `Q4_K_M`**. M60_ENVIRONMENT.json does not itself store the quantization string.

---

## Production call graph (M60)

Entry: `scripts/run_m60_position.py`

1. `verify_freeze()` — protocol / cohort / scientific-core hashes
2. `case_by_position()` — `manuscript_benchmark/M60_COHORT_MANIFEST.json`
3. `ensure_solver_fasta()` — NCBI Datasets / FTP; sanitized headers
4. Per-arm `run_one_system()` / `run_specialist()`
5. `lock_position()` — `manuscript_benchmark/POSITION_LOCKS/position_XX/`

Required systems per position:

- `CONVENTIONAL`
- `AMRFINDERPLUS` (tetA only) **or** `NCBI_REFSEQ_PGAP` (rpoB only)
- `GS_DETERMINISTIC_V4_1`
- `GS_AGENTIC_V4_1`
- `GS_EXHAUSTIVE_V4_1`

---

## The three Genome Skeptic arms (independently verifiable)

Single loop: `src/genome_skeptic/agents/assembly_loop_v4_1_dev.py`  
`run_skeptic_agentic_v4_1_dev(follow_up_policy=...)`

Wrappers (`run_gs_deterministic_v4_1`, `run_gs_agentic_v4_1`, `run_gs_exhaustive_v4_1`) only set policy.

Quoted contract in that module:

> follow_up_policy selects only which eligible registered follow-ups run after the shared initial measurement. Scientific instruments, thresholds, and the validator are identical across arms.

Shared m0:

- `collect_assembly_target_measurements()` — `src/genome_skeptic/agents/assembly_loop.py`
- `repair_loci_v4_1`
- `measurements_to_evidence` (Evidence Ledger IDs)
- `derive_diagnostic_needs_v4_1_dev`
- `rank_candidate_actions`

Follow-up policies (only divergence):

| Policy | Function | LLM? | Behaviour |
|---|---|---|---|
| `POLICY_DETERMINISTIC` | `apply_deterministic_followups()` | No | One primary action per open need |
| `POLICY_EXHAUSTIVE` | `apply_exhaustive_followups()` | No | All eligible actions, cheapest first, max 32 |
| `POLICY_AGENTIC` | Planner + optional Critic | Yes | ≤1 planner action + ≤1 critic action |

All arms end at `build_target_gene_claim()` in `src/genome_skeptic/validators/falsification.py`.

Scientific-core hashing: `src/genome_skeptic/manuscript/scientific_core.py`.  
Freeze follow-up-policy hashes differ; shared `scientific_core_hash` is identical.

M60 runner exhaustive integrity check asserts `same_scientific_core`, `same_validator`, `same_endpoint_contract`.

**Observed M60:** all three GS arms produced identical endpoints on all 60 cases (33/41 evaluable; 8 shared errors).

---

## Evidence Ledger and TargetMeasurements

Not a separate database class. `_LoopState.evidence` is populated by `state.add_evidence()` and `measurements_to_evidence()`. Persisted as `{case_dir}/evidence.json`. Claims link `provenance.evidence_ledger_ids`.

`TargetMeasurements` dataclass: `src/genome_skeptic/validators/falsification.py`.

Family evidence: `collect_family_evidence()` in `src/genome_skeptic/validators/family_orthology.py`.

Operational run metadata (not biological evidence): `manuscript_benchmark/RUN_LOGS/M60_EXECUTION_LEDGER.jsonl` (gitignored run tree).

---

## Planner / Critic / providers

| Role | Location |
|---|---|
| Planner system prompt | `AGENTIC_REASONER_SYSTEM` in `assembly_loop_v4_1_dev.py` |
| Critic system prompt | `AGENTIC_CRITIC_SYSTEM` same file |
| Planner/critic views | `src/genome_skeptic/agents/planner_views_v4_1_dev.py` |
| LLM client | `src/genome_skeptic/agents/ollama.py` (`OllamaJSONClient`) |
| OpenAI-compatible adapter | `src/genome_skeptic/agents/adapter.py` |
| Provider routing | `src/genome_skeptic/agents/providers.py` (production M60: Ollama/Qwen) |

Frozen prompts hashes in freeze manifest:

- planner `fcffbc11cf6afbe84731c15854d37e85d929b966318acc45567f5332819d0f63`
- critic `8b04802de10aea03d24b26633a17d68415db74db3ba82034b6b8d1cf75f2b60e`

Sol ablation uses a **post-hoc** provider path (`openai_api`, `gpt-5.6-sol`, `reasoning=high`) copied for review under `EXTERNAL_REVIEW_CLAUDE/posthoc_code/`. That file is **not** the frozen M60 scientific core.

---

## Conventional arm

`run_m60_position.py` → `genome_skeptic.eval.evaluate_real._run_system("conventional")` → `src/genome_skeptic/eval/baselines.py` `run_conventional()`.

Uses `run_gene_search()` + `strong_hit()` (`src/genome_skeptic/validators/homology.py`):

- gene_orthologue: amino-acid/translated identity ≥ 0.60, coverage ≥ 0.80

No family orthology, competitive_family, falsification loop, or planner.

---

## Specialist comparators (not truth)

### tetA — AMRFinderPlus

- Software **4.2.7**
- Database **2026-08-07.1** (frozen `manuscript_benchmark/ENVIRONMENT/AMRFINDER_DATABASE_FREEZE.json`)
- Command class: `amrfinder -n <solver.fna> --plus -d <frozen_db>`
- Binary POSITIVE iff any gene symbol normalizes to exactly `teta`, `tet(a)`, `tetb`, or `tet(b)`
- Other tet classes are NEGATIVE for this endpoint
- **AMRFinder did not define tetA truth**

### rpoB — NCBI RefSeq/PGAP

- `run_rpob_pgap_comparator()` in `scripts/run_m60_position.py`
- POSITIVE if any CDS gene=`rpoB` or RNA polymerase beta (not beta-prime / rpoC)
- NEGATIVE if annotation present with zero rpoB hits
- UNCERTAIN if missing/unreadable/no CDS
- **PGAP did not define rpoB truth**

Pooled “specialist 34/41” is a **composite of two different tools**. Do not describe it as one biological method.

---

## Registered actions and validator

Registry: `ACTION_IDS` + `V41_EXTRA_ACTION_IDS` (`action_catalog.py`, `action_catalog_v4_1_dev.py`).

Handlers: `assembly_loop_v2.py` `run_action_and_update()`; V4.1 adds ortholog-reference handler.

After `competitive_family`, `refine_weak_family_classification()` may relabel `target_family_supported` → `ambiguous_family`.

Final polarity: `classify_polarity()` / `family_detects_orthologue()` — see `03_FROZEN_ENDPOINTS.md`.

GS binary scoring (`scripts/score_m60_phase4.py` `gs_binary()`):

- `target_gene_detected` → POSITIVE
- `target_gene_not_detected` → NEGATIVE
- failed/incomplete → UNRESOLVED (incorrect if truth is POSITIVE or NEGATIVE)

---

## Lock / truth / statistics / post-hoc scripts

| Stage | Script |
|---|---|
| Position lock | `scripts/run_m60_position.py` |
| Prediction aggregate lock | `scripts/finalize_m60_predictions.py` |
| Truth sources | `scripts/freeze_m60_truth_sources.py` |
| Adjudication | `scripts/adjudicate_m60_truth.py` |
| Truth lock | `scripts/lock_m60_truth.py` |
| Human review lock | `scripts/lock_m60_phase3b.py` |
| Statistics | `scripts/score_m60_phase4.py` |
| Sol ablation | `EXTERNAL_REVIEW_CLAUDE/posthoc_code/scripts/run_sol56_*.py` |
| Error forensics | `manuscript_benchmark/POSTHOC_ERROR_ANALYSIS/_extract_frozen_error_artifacts.py` |
