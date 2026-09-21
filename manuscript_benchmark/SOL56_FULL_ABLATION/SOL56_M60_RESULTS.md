# SOL56 full M60 post-hoc model ablation

POST_HOC_MODEL_ABLATION = TRUE. MANUSCRIPT_PRIMARY_VALIDATION = FALSE.

The only variable relative to original Agentic M60 is qwen3:4b → gpt-5.6-sol, reasoning=high.

## Phase 1 — blinded model comparison

- Planner action changed vs Qwen: 54 / 60
- Critic behaviour changed vs Qwen: 60 / 60
- Follow-up action count changed: 59 / 60
- Final endpoint changed vs Qwen: 0 / 60
- Final endpoint changed vs GS-Det: 0 / 60
- Final endpoint differs from GS-Exhaustive: 0 / 60

## Phase 2 — post-hoc truth join

Truth SHA256: `a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9`
Truth-evaluable N = 41. TRUTH_UNCERTAIN n = 19 remain descriptive only.

- Sol: 33 / 41 accuracy 0.805 Wilson 95% CI 0.660–0.898
- Qwen Agentic: 33 / 41
- GS-Deterministic: 33 / 41
- GS-Exhaustive: 33 / 41
- tetA Sol: 19 / 26
- rpoB Sol: 14 / 15
- routine Sol: 15 / 21
- challenge Sol: 18 / 20

## Sol vs Qwen Agentic

- Qwen wrong → Sol correct: 0
- Qwen correct → Sol wrong: 0
- Net corrections: 0
- Accuracy difference: +0.0 pp
- Paired bootstrap 95% CI (10,000; seed 20260920): 0.000–0.000
- Exact McNemar P: NA

## Sol vs GS-Deterministic

- Det wrong → Sol correct: 0
- Det correct → Sol wrong: 0
- Net: 0

## Sol vs GS-Exhaustive

- Exhaustive wrong → Sol correct: 0
- Exhaustive correct → Sol wrong: 0
- Net: 0

## Model behaviour

- Qwen follow-up actions mean/median/total: 1.016667 / 1.0 / 61
- Sol follow-up actions mean/median/total: 2.0 / 2.0 / 120
- Exhaustive follow-up actions mean/median/total: 3.15 / 3.0 / 189
- Qwen critic challenges: 1 / 60
- Sol critic challenges: 60 / 60
- Extra Sol actions → DECISION_CHANGE: 0
- Extra Sol actions → NO_DECISION_CHANGE: 59

No Sol endpoint differed from locked Qwen Agentic on the 60-case cohort.


## Cost and latency

- Total input tokens: 178526
- Total output tokens: 21855
- Total reasoning tokens: 11504
- Total API cost: $1.151204
- Median Planner latency: 5.209
- Median Critic latency: 5.577
- Median Sol case runtime: 32.559
- Median Qwen Agentic case runtime: 206.6875
- Median GS-Exhaustive case runtime: 19.4455
LLM latency and deterministic-analysis count are separate efficiency concepts.

PROMPTS MODIFIED: NO
SCIENTIFIC CORE MODIFIED: NO
VALIDATOR MODIFIED: NO
