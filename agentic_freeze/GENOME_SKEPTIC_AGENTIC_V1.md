# GENOME_SKEPTIC_AGENTIC_V1

Read-only freeze of the first agentic Genome Skeptic version.

This freeze is **separate from frozen deterministic V5**. It does not replace V5,
does not modify V5, and does not authorize Cohort A or any external genome run.

## Architecture

Genome Skeptic Agentic V1 consists of:

deterministic measurements
→ Evidence ledger
→ Qwen planner
→ registered deterministic action
→ additional Evidence
→ Qwen critic
→ deterministic final validator

The live implementation of this loop is `src/genome_skeptic/agents/assembly_loop.py`
(`SYSTEM_NAME = genome_skeptic_agentic`), configured by `config/qwen_agentic_dev.yaml`.

## Constraints (enforced)

- Qwen cannot supply measured biological quantities
- evidence-ID validation is enforced
- action registration is enforced
- malformed structured output fails closed
- maximum one repair
- no silent deterministic-success fallback after agent failure
- deterministic validator is final scientific authority

Qwen is not permitted to calculate or invent identity, coverage, E-values, HMM
scores, coordinates, copy number, gene order, taxonomy, read depth, or other
measured quantities. Those values come only from deterministic tools.

Structured planner/critic output uses Ollama native schema
(`format = json_schema`) with `thinking = false` and `temperature = 0`.
Invalid evidence IDs, unregistered actions, or schema-invalid JSON fail closed.
The deterministic validator (`build_target_gene_claim`) remains the final
scientific authority for claim type, architecture class, and status
(supported / weakened / unresolved / rejected).

## Frozen runtime identity

- model = qwen3:4b
- model digest = 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7
- thinking = false
- temperature = 0
- structured output = Ollama native schema
- repair policy = maximum one repair
- final authority = deterministic validator

## Internal gate (hashed before execution)

- internal gate manifest hash = 5715d3d1f9ce8edd00af249411da58d4cbc13cd407ca936cd472b2822779bb99
- internal gate result = 6/6 PASS
- 14 model calls
- 4029.5 s total runtime
- no LLM-generated measurements entered claims
- planner/critic invoked in all six cases
- final validator invoked in all six cases
- only one distinct action was selected: `inspect_contig_edges_for_target`

## Current limitation

The six-case internal gate demonstrated correct end-to-end agent execution
and biological no-regression, but all six planner decisions selected the
same registered action. Adaptive action-selection diversity has therefore
not yet been demonstrated externally.

This limitation is recorded, not hidden. Agentic V1 is frozen with that
bound: execution, evidence discipline, and V5 biological class agreement
are demonstrated; adaptive choice among registered actions is not.

## Out of scope for this freeze

- No modification of the agent after the 6/6 gate
- No modification of frozen deterministic V5
- Cohort A untouched
- External labels not opened
- No external genome selected or run
