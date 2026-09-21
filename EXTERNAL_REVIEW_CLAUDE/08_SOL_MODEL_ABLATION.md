# GPT-5.6 Sol post-hoc model ablation

```
POST-HOC
NOT PRIMARY VALIDATION
POST_HOC_MODEL_ABLATION = TRUE
MANUSCRIPT_PRIMARY_VALIDATION = FALSE
```

Only the LLM backend was changed:

`qwen3:4b` → `gpt-5.6-sol` with `reasoning=high`

Same (claimed and to be verified from code): prompts, schemas, actions, measurements, validator, thresholds, cases, scientific core.

Config: `config/sol56_high_posthoc.yaml` (also copied under `EXTERNAL_REVIEW_CLAUDE/posthoc_code/config/`). YAML sets `thinking: false`; runtime constant `SOL_REASONING_EFFORT = "high"` in the post-hoc `providers.py`.

Adapter code for review: `EXTERNAL_REVIEW_CLAUDE/posthoc_code/src/genome_skeptic/agents/providers.py`  
**Do not treat this as frozen V4.1 production code.** Production M60 Agentic used Ollama Qwen (`src/genome_skeptic/agents/providers.py` in the repository root).

Scripts: `EXTERNAL_REVIEW_CLAUDE/posthoc_code/scripts/run_sol56_*.py`.

---

## Verified full-cohort result

Source: `manuscript_benchmark/SOL56_FULL_ABLATION/SOL56_M60_RESULTS.md`  
Manifest SHA256: `2a9f86956ca12026b4ff39fc7bcaf297db992ba4db53421a9482683ae1885a39` **MATCH**.

Truth-evaluable N = 41. Same final truth SHA256 `a64dea4f…`.

| System | Exact endpoint |
|---|---|
| Sol | **33 / 41** |
| Qwen Agentic | **33 / 41** |
| GS-Deterministic | **33 / 41** |
| GS-Exhaustive | **33 / 41** |

Sol vs Qwen:

- 0 corrections
- 0 degradations
- 0 endpoint changes
- accuracy difference +0.0 pp
- paired bootstrap 95% CI 0.000–0.000 (10,000; seed 20260920)
- McNemar P: NA

tetA Sol 19 / 26; rpoB Sol 14 / 15; routine 15 / 21; challenge 18 / 20 (identical to Qwen).

---

## Investigation policy changed; endpoints did not

All 60 cases (Phase 1 blinded model comparison in the Sol results file):

| Quantity | Count |
|---|---|
| Planner action changed vs Qwen | **54 / 60** |
| Critic behaviour changed vs Qwen | **60 / 60** |
| Follow-up action count changed | 59 / 60 |
| Final endpoint changed vs Qwen | **0 / 60** |
| Final endpoint changed vs GS-Det | **0 / 60** |
| Final endpoint differs from Exhaustive | **0 / 60** |

Follow-up totals:

| Arm | Follow-ups |
|---|---:|
| Qwen | **61** |
| Sol | **120** |
| Exhaustive | **189** |

Sol critic challenges: 60 / 60 (Qwen: 1 / 60).  
Extra Sol actions → DECISION_CHANGE: **0**; NO_DECISION_CHANGE: 59.

---

## Cost and latency

From `SOL56_M60_RESULTS.md`:

| Quantity | Value |
|---|---|
| Total input tokens | 178526 |
| Total output tokens | 21855 |
| Total reasoning tokens | 11504 |
| API cost | **$1.151204** |
| Median Planner latency | **5.209 s** |
| Median Critic latency | **5.577 s** |
| Median Sol total case runtime | **32.559 s** |
| Median Qwen case runtime | 206.6875 s |
| Median Exhaustive runtime | 19.4455 s |

Sol was **faster wall-clock** than local Qwen while using **more** follow-up analyses (120 vs 61), still far from Exhaustive’s 19.4 s deterministic-only runtime.

5-case preflight manifest SHA256 `7b8ef9e2…` MATCH; that preflight did not open truth / score accuracy.

---

## Permissible vs impermissible interpretation

**Do NOT state** that this proves stronger LLMs can never improve this task.

**Do NOT state** “LLM intelligence is irrelevant.”

**Permissible narrower interpretation** (still for the reviewer to accept or reject):

> Within the frozen Genome Skeptic V4.1 architecture and registered toolbox, replacing the local 4B model with GPT-5.6 Sol substantially changed evidence-acquisition behaviour but did not change any final endpoint.

Even narrower, and still not a universal claim:

> Reasoning-model capability alone was insufficient to alter endpoint classification within the frozen V4.1 evidence and validator architecture.

Artifacts:

- `manuscript_benchmark/SOL56_FULL_ABLATION/SOL56_M60_CASE_LEVEL.csv`
- `SOL56_M60_MODEL_BEHAVIOUR.csv`
- `SOL56_M60_SCORING.csv`
- `SOL56_M60_SUMMARY.json`
- `SOL56_M60_PREDICTION_LOCK.json`
- `SOL56_M60_CALL_LOG.jsonl`
- `locks/` (per-case Sol lock JSON, copied for review)
