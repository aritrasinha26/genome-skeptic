# Current claims to audit

Present in tiers. Ask whether each is **exactly supported**. Do not upgrade wording.

The audit package does **not** present the paper as proving LLM accuracy gains, specialist superiority/equivalence, formal Agentic=Exhaustive equivalence, “stronger LLMs never matter,” or general annotation performance from two endpoints.

---

## CLAIM 1 — PRIMARY PROSPECTIVE FINDING

> In the prospective M60 benchmark, adaptive LLM-guided follow-up analysis did not improve exact endpoint accuracy over the identical deterministic scientific core: both GS-Agentic and GS-Deterministic classified 33 of 41 independently truth-evaluable cases correctly.

**Ask:** Is this exactly supported?

Source to verify: `RESULTS_M60/M60_PHASE4_STOP.json`, `M60_AGENT_VS_DETERMINISTIC.csv`.

---

## CLAIM 2 — SELECTIVE EVIDENCE ACQUISITION

> Using the local Qwen reasoner, GS-Agentic used 61 follow-up analyses versus 189 under exhaustive follow-up, a 67.7% reduction, while yielding the same observed endpoint accuracy in this benchmark.

**CRITICAL:** Do **not** call the accuracies statistically equivalent. Use **same observed accuracy**.

**Ask:** Is this framing statistically and scientifically defensible?

No equivalence margin was preregistered (`M60_FINAL_RESULTS.md`).

---

## CLAIM 3 — WALL-CLOCK TRADEOFF

> Reduced deterministic follow-up analyses did not translate into reduced wall-clock time with the local Qwen implementation because LLM inference dominated runtime.

**Ask:** Verify against `M60_EFFICIENCY_RESULTS.csv` (median 206.7 s vs 19.4 s; ratio 10.63).

Note: Sol post-hoc median runtime was 32.6 s — **do not** fold that into Claim 3 (different model, post-hoc).

---

## CLAIM 4 — MODEL-STRENGTH ABLATION (POST-HOC)

> Replacing Qwen with GPT-5.6 Sol substantially changed investigation behaviour but changed no final endpoint across the 60 M60 cases.

**Ask** whether it supports the narrower inference:

> Reasoning-model capability alone was insufficient to alter endpoint classification within the frozen V4.1 evidence and validator architecture.

**Do NOT claim:** “LLM intelligence is irrelevant.”

Source: `SOL56_FULL_ABLATION/SOL56_M60_RESULTS.md` (54/60 planner, 60/60 critic, 0/60 endpoint).

---

## CLAIM 5 — MECHANISTIC INTERPRETATION (POST-HOC; only if forensics support it)

Completed 8-case analysis **does** propose:

> In the shared errors examined post hoc, failures were attributable primarily to limitations in evidence discrimination, evidence-state representation, or deterministic decision rules rather than to selection of a different LLM-directed follow-up analysis.

Authors’ tighter sentence (`POSTHOC_MANUSCRIPT_INTERPRETATION.md`) attributes failure **primarily to frozen family-state decision rules**.

**Ask:** Verify **case by case**. Do not assume this is true merely because Sol did not change endpoints.

If you reject any case’s assigned root cause, this claim must be dropped or scoped.

---

## CLAIM 6 — RELATION TO SPECIALIST TOOLS

Observed: specialist comparator **34 / 41**; Genome Skeptic **33 / 41**.

**Do NOT claim** superiority, equivalence, non-inferiority, or parity unless statistically justified.

**Ask:** What wording is defensible?

Disaggregated facts that constrain wording:

- tetA: specialist 19/26, GS 19/26, conventional 20/26; tetA sensitivity 0/7 (specialist and GS)
- rpoB: specialist 15/15, GS 14/15, conventional 0/15; no rpoB negatives
- Two different specialist tools

---

## Additional statements that are facts, not claims of advantage

- 41/60 truth-evaluable; 19 uncertain
- tetA Agent 19/26; rpoB Agent 14/15
- Routine 15/21; challenge 18/20
- Qwen follow-ups 61; Exhaustive 189; reduction 67.7%
- Median Qwen runtime 206.7 s; Exhaustive 19.4 s

---

## What must NOT be claimed (checklist)

- [ ] LLM agents improve accuracy
- [ ] Genome Skeptic beats specialist tools
- [ ] Genome Skeptic is equivalent / non-inferior to specialist tools
- [ ] Agentic equals Exhaustive as a statistical equivalence result
- [ ] Stronger LLMs never matter
- [ ] Exhaustive testing is unnecessary in general
- [ ] Validator limitations are causal **unless** you accept the 8-case forensics
- [ ] General genome annotation performance from two endpoints
- [ ] rpoB specificity
- [ ] tetA sensitivity is adequate
