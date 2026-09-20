# GENOME_SKEPTIC_AGENTIC_V2_D20

Read-only freeze of Agentic V2 after Gate 0 readiness, taken as the locked
starting state for Cohort D20.

This freeze is **separate from frozen deterministic V5** and **separate from
GENOME_SKEPTIC_AGENTIC_V1**. It does not replace either.

No scientific or agentic source was modified to create this freeze.
D20 candidate discovery has **not** started. External genomes were not run.
External truth was not accessed.

After this freeze, no scientific code, prompts, thresholds, actions, or
validators may change until D20 is completely scored.

## Architecture

deterministic measurements (m0)
→ Evidence ledger
→ compact Qwen planner (`PlannerDecision`)
→ registered deterministic action or explicit control decision
→ validated measurement patch
→ compact Qwen critic (`CriticDecision`)
→ at most one further named action
→ deterministic final validator (`build_target_gene_claim`)

Live loop: `src/genome_skeptic/agents/assembly_loop_v2.py`
(`SYSTEM_NAME = genome_skeptic_agentic_v2`), configured by
`config/qwen_agentic_dev.yaml`.

## Frozen runtime identity

- model = qwen3:4b
- model digest = 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7
- think = false
- temperature = 0.0
- context length = 262144 (Ollama `qwen3.context_length`; request does not set `num_ctx`)
- planner max output tokens = 320
- critic max output tokens = 320
- repair limit = 1
- keep_alive = 30m

## Readiness evidence (recorded)

- full regression status = 67/67 PASS
- ask_human → ABSTAIN_UNRESOLVED mapping regression = PASS
- planner valid one-call JSON = yes
- planner warm time = 88.2 s
- planner repairs = 0
- planner truncation = no
- critic valid one-call JSON = yes
- critic repairs = 0
- think = false
- unavailable actions filtered
- redundant/inert actions filtered
- deterministic state recomputation enabled
- tuf multiplicity consistency invariant enabled

Gate 0 live corroboration (internal Test A fixture, not a scientific rerun):
planner 91.664 s / 0 repairs / no truncation; critic 60.39 s / 0 repairs.

## Integrity references

- V5 freeze-manifest SHA256 = 5c36a0dbd0e1ab17ef7c0c598fd209bcbb77edf596286bf05ff165a08d04e7a3
- V5 aggregate SHA256 = 0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b
- scoring contract SHA256 = d224b8b829b3a46c03e42aae324062b7ff72c75d2b6906a0cab45618818f9cb9
- provenance/exclusion contract SHA256 = 205d468d98090bca51099785407d8df004cb97f04603bd93f5521e63484ddf80
- input-policy SHA256 = 6d99f26208175a5f7a77017d3d99461ed4c75d333930622059ed01c9b18d0978

## Freeze inventory

- freeze name = GENOME_SKEPTIC_AGENTIC_V2_D20
- frozen files = 112
- freeze-manifest SHA256 = 736bd2bdc34b1967a429602903f26ebfa5cdb031c6787a7f0ebf77926517c696
- created_utc = 2026-09-20T11:14:11.988331+00:00

## Out of scope

- D20 candidate discovery started = NO
- External truth accessed = NO
- External genomes run = NO
