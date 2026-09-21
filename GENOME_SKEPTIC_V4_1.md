# GENOME SKEPTIC V4.1 + EXTERNAL VALIDATION

SPAdes was not rerun. V3 and V4 reports were not modified. The family HMM gate remains 0.20. No species-specific rules were added. External benchmark prompts and scorers were not rewritten. Thresholds were not retuned after viewing external held-out answers.

## Acceptance gates (not a single composite)

- V4.1 paralogue/divergence controls GS overall: 1.0
- Conventional on the same controls: 0.5806451612903226
- Genome Skeptic without falsification: 0.967741935483871
- Dummy / naive: 0.8387096774193549 / 0.3064516129032258
- New families loaded: 4 / 4
- Multifamily calibration Brier: 0.0556
- Multifamily calibration ECE: 0.1326
- Overconfidence / underconfidence: 0.037 / 0.0
- Model dry-run available names: []
- External supported tasks with local inputs: 0

## Paralogues and divergence

- `ctrl_para_contaminant` architecture=close_paralogue kind=contaminant_copy query_identity=1.0 divergent=False
- `ctrl_para_fragments` architecture=assembly_fragmented kind=assembly_fragments_of_one_gene query_identity=1.0 divergent=False
- `ctrl_para_plasmid` architecture=close_paralogue kind=plasmid_copy query_identity=1.0 divergent=False
- `ctrl_para_recent` architecture=close_paralogue kind=recent_gene_duplication query_identity=1.0 divergent=False
- `ctrl_para_true` architecture=close_paralogue kind=true_duplicated_paralogue query_identity=1.0 divergent=False
- `ctrl_canonical_query_like` architecture=canonical_full_length kind=None query_identity=1.0 divergent=False
- `ctrl_divergent_family` architecture=divergent_full_length kind=None query_identity=0.5501 divergent=True

### Control claim comparison

- `ctrl_canonical_query_like` `rpoB`: GS target_gene_detected/supported arch=canonical_full_length vs conventional target_gene_detected
- `ctrl_divergent_family` `rpoB`: GS target_gene_detected/weakened arch=divergent_full_length vs conventional target_gene_not_detected
- `ctrl_para_contaminant` `rpoB`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `ctrl_para_fragments` `rpoB`: GS target_gene_not_detected/weakened arch=assembly_fragmented vs conventional target_gene_not_detected
- `ctrl_para_plasmid` `rpoB`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `ctrl_para_recent` `rpoB`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `ctrl_para_true` `rpoB`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected

## Gene-family generalization

- `recA_recombinase` (RecA recombinase (single-copy housekeeping)): loaded=True n_members=4
- `tuf_EF_Tu` (elongation factor Tu (multi-copy paralogues tufA/tufB)): loaded=True n_members=4
- `lacZ_beta_galactosidase` (beta-galactosidase LacZ (accessory, absent from many strains)): loaded=True n_members=3
- `tetA_tetracycline_efflux` (tetracycline efflux TetA (mobile/plasmid-associated)): loaded=True n_members=3
- `dev_01_lacZ` `lacZ`: GS target_gene_detected/supported arch=close_paralogue vs conventional target_gene_detected
- `dev_01_recA` `recA`: GS target_gene_detected/supported arch=canonical_full_length vs conventional target_gene_detected
- `dev_01_tetA` `tetA`: GS target_gene_detected/weakened arch=divergent_full_length vs conventional target_gene_not_detected
- `dev_01_tuf` `tuf`: GS target_gene_detected/supported arch=canonical_full_length vs conventional target_gene_detected

## Calibration (leave-one-genome-out, development only)

- Held-out genomes used to fit: False
- External benchmark answers used to fit: False
- n=27 Brier=0.0556 ECE=0.1326
- overconfidence=0.037 underconfidence=0.0
- Reliability bins:
  - [0.0, 0.1): n=0 mean_pred=None empirical=None
  - [0.1, 0.2): n=5 mean_pred=0.1667 empirical=0.0
  - [0.2, 0.3): n=0 mean_pred=None empirical=None
  - [0.3, 0.4): n=0 mean_pred=None empirical=None
  - [0.4, 0.5): n=0 mean_pred=None empirical=None
  - [0.5, 0.6): n=0 mean_pred=None empirical=None
  - [0.6, 0.7): n=0 mean_pred=None empirical=None
  - [0.7, 0.8): n=0 mean_pred=None empirical=None
  - [0.8, 0.9): n=22 mean_pred=0.8296 empirical=0.9545
  - [0.9, 1.0): n=0 mean_pred=None empirical=None
- family `rpoB_RNAP_beta`: n=15 Brier=0.1273 ECE=0.2828 over=0.0 under=0.0
- family `recA_recombinase`: n=3 Brier=0.1086 ECE=0.3193 over=0.0 under=0.0
- family `tuf_EF_Tu`: n=3 Brier=0.1131 ECE=0.325 over=0.0 under=0.0
- family `lacZ_beta_galactosidase`: n=3 Brier=0.1078 ECE=0.3174 over=0.0 under=0.0
- family `tetA_tetracycline_efflux`: n=3 Brier=0.1219 ECE=0.3462 over=0.0 under=0.0

## Model independence

- Deterministic evidence/claim engine is unchanged across adapter swaps.
- Silent substitution is forbidden.
- Setup (OpenAI-compatible): Serve an OpenAI-compatible /v1/chat/completions endpoint (vLLM, llama.cpp server, Ollama with OpenAI API).
- Setup (Ollama): Install Ollama and pull models, e.g. `ollama pull qwen3:8b` and `ollama pull deepseek-r1:8b`.
- Expected names: {'qwen3': ['qwen3:8b', 'qwen3:14b', 'qwen3:32b', 'qwen2.5:7b', 'qwen2.5:14b'], 'deepseek-r1-distill': ['deepseek-r1:8b', 'deepseek-r1:7b', 'deepseek-r1-distill-qwen-7b', 'deepseek-r1-distill-llama-8b', 'deepseek-r1-distill-qwen-14b'], 'local': []}
- RAM/VRAM estimates: {'qwen3:8b': '~8–12 GB', 'qwen3:14b': '~12–18 GB', 'deepseek-r1:8b': '~8–12 GB', 'deepseek-r1-distill-qwen-7b': '~8–12 GB'} notes=['nvidia-smi not on PATH; VRAM estimate unavailable', 'Ollama /api/ps not reachable']
- dry-run `qwen3` resolved=None invented_output=False would_call=False
- dry-run `deepseek-r1-distill` resolved=None invented_output=False would_call=False
- dry-run `local` resolved=None invented_output=False would_call=False
- comparison planner=qwen3 critic=qwen3 unavailable=True reason=requested open-weight model was not exposed locally and was not substituted
- comparison planner=deepseek-r1-distill critic=deepseek-r1-distill unavailable=True reason=requested open-weight model was not exposed locally and was not substituted
- comparison planner=qwen3 critic=deepseek-r1-distill unavailable=True reason=requested open-weight model was not exposed locally and was not substituted

## External benchmarks

Unsupported transcriptomics/single-cell/unrelated tasks were not rewritten. Only supported tasks with original local inputs would be scored.
- BioMaster was not executed locally; published numbers are not treated as a head-to-head comparison.
- `bioagent_bench`: source=catalog_fallback_no_inputs n=8 supported=2 partial=3 unsupported=3
- `promptbio_bench`: source=catalog_fallback_no_inputs n=6 supported=2 partial=1 unsupported=3
- `bixbench`: source=catalog_fallback_no_inputs n=4 supported=1 partial=1 unsupported=2

## Superiority gates (evidence, not aspiration)

- matches conventional on clean cases: True
- improves difficult architecture cases: True
- beats naive-confident and dummy-cautious on V4.1 controls: True
- stable across two open-weight models: False
- generalizes beyond rpoB: True
- scored on original external genomics tasks: False

## Remaining failures

- tetA on reused E. coli K-12 assembly was detected despite accessory/mobile truth=absent; no family-specific rule was added
- Qwen3 / DeepSeek-R1-Distill were unavailable locally and were not substituted
- no external benchmark tasks had local inputs; Genome Skeptic is not scored on rewritten proxies

## Label

**internally validated agent**

This label is from executed evidence: internal architecture controls, family generalization, model availability, and whether original external tasks could be scored without rewriting them. Genome Skeptic is not described as superior unless every listed superiority gate is true.

## Files

- GENOME_SKEPTIC_V4_1.md
- paralogue_validation_v4_1.json
- divergence_validation_v4_1.json
- model_independence_v4_1.json
- external_benchmark_manifest.json
- external_benchmark_results.json
- gene_family_generalization.json
- calibration_multifamily.json

