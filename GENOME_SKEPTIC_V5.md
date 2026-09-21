# GENOME SKEPTIC V5: FAILURE-MODE REPAIR, MODEL INDEPENDENCE, AND EXTERNAL VALIDATION

SPAdes was not rerun except if an official external benchmark had required raw-read assembly (it did not). V3, V4, and V4.1 reports were not modified. Thresholds were not retuned after external answers. No species- or gene-specific rescue rules were added. The family HMM gate remains 0.20.

On the reused FAST_PILOT *E. coli* K-12 assembly, tetA is **not detected** (domain-only MFS similarity, HMM model coverage 0.31). Genuine recA, tuf, lacZ, mdfA, and rpoB are detected. Conventional pairwise search misses rpoB at identity 0.458 while the family HMM still supports a divergent full-length locus. A near-identical tufA/tufB pair is recovered on a synthetic two-locus control (`recent_duplication`) but remains a single reconstructed interval on the SPAdes assembly, which collapsed the copies.

Official BioAgent Bench, PromptBio-Bench, and BixBench repositories were cloned. No original task was scored: either the task is outside bacterial gene-orthologue scope, or the clone lacks the original inputs and scorer. Qwen3, DeepSeek-R1-Distill, and GPT were unavailable and were not substituted.

## Internal validation

- V5 competitive/multiplicity controls GS overall: 0.9583333333333334
- Conventional: 0.8055555555555556
- Without falsification / dummy / naive: 0.9027777777777778 / 0.7777777777777778 / 0.4305555555555556
- `ctrl_comp_broad_membrane` `tetA`: GS target_gene_not_detected/weakened arch=true_no_candidate vs conventional target_gene_not_detected
- `ctrl_comp_divergent_genuine` `tetA`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `ctrl_comp_paralogous_member` `tetA`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `ctrl_comp_related_transporter` `tetA`: GS target_gene_not_detected/weakened arch=true_no_candidate vs conventional target_gene_not_detected
- `ctrl_comp_shared_domain` `tetA`: GS target_gene_not_detected/weakened arch=true_no_candidate vs conventional target_gene_not_detected
- `ctrl_comp_true_target` `tetA`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `ctrl_multi_near_identical` `tuf`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `ctrl_multi_single` `recA`: GS target_gene_detected/weakened arch=canonical_full_length vs conventional target_gene_detected
- competitive `ctrl_comp_broad_membrane` architecture=true_no_candidate classification=unresolved_candidate competitor=None
- competitive `ctrl_comp_divergent_genuine` architecture=close_paralogue classification=target_family_supported competitor=None
- competitive `ctrl_comp_paralogous_member` architecture=close_paralogue classification=target_family_supported competitor=None
- competitive `ctrl_comp_related_transporter` architecture=true_no_candidate classification=unresolved_candidate competitor=None
- competitive `ctrl_comp_shared_domain` architecture=true_no_candidate classification=domain_only competitor=mfs_multidrug_efflux
- competitive `ctrl_comp_true_target` architecture=close_paralogue classification=target_family_supported competitor=None
- competitive `dev_01_tetA` architecture=domain_only classification=target_family_supported competitor=None
- multiplicity `ctrl_multi_near_identical` architecture=close_paralogue class=recent_duplication n=4
- multiplicity `ctrl_multi_single` architecture=canonical_full_length class=single_locus n=1
- multiplicity `dev_01_tuf` architecture=canonical_full_length class=single_locus n=1

## Generalization

- `recA_recombinase` (highly_conserved_single_copy_housekeeping): loaded=True n_members=4
- `tuf_EF_Tu` (multi_copy_near_identical): loaded=True n_members=4
- `lacZ_beta_galactosidase` (accessory_metabolic): loaded=True n_members=3
- `tetA_tetracycline_efflux` (mobile_resistance_transporter): loaded=True n_members=2
- `mfs_multidrug_efflux` (membrane_transporter_with_competitors): loaded=True n_members=3
- `rpoB_RNAP_beta` (fusion_split_prone_housekeeping): loaded=True n_members=7
- `dev_01_lacZ` `lacZ`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `dev_01_mdfA` `mdfA`: GS target_gene_detected/weakened arch=close_paralogue vs conventional target_gene_detected
- `dev_01_recA` `recA`: GS target_gene_detected/supported arch=canonical_full_length vs conventional target_gene_detected
- `dev_01_rpoB` `rpoB`: GS target_gene_detected/supported arch=divergent_full_length vs conventional target_gene_not_detected
- `dev_01_tetA` `tetA`: GS target_gene_not_detected/weakened arch=domain_only vs conventional target_gene_not_detected
- `dev_01_tuf` `tuf`: GS target_gene_detected/supported arch=canonical_full_length vs conventional target_gene_detected

## Calibration

- Held-out used to fit: False
- External used to fit: False
- n=42 Brier=0.0199 ECE=0.1231
- overconfidence=0.0 underconfidence=0.0
- Reliability bins:
  - [0.0, 0.1): n=0 mean_pred=None empirical=None
  - [0.1, 0.2): n=0 mean_pred=None empirical=None
  - [0.2, 0.3): n=0 mean_pred=None empirical=None
  - [0.3, 0.4): n=4 mean_pred=0.3333 empirical=0.0
  - [0.4, 0.5): n=0 mean_pred=None empirical=None
  - [0.5, 0.6): n=0 mean_pred=None empirical=None
  - [0.6, 0.7): n=0 mean_pred=None empirical=None
  - [0.7, 0.8): n=0 mean_pred=None empirical=None
  - [0.8, 0.9): n=10 mean_pred=0.8861 empirical=1.0
  - [0.9, 1.0): n=28 mean_pred=0.9036 empirical=1.0
- family `rpoB_RNAP_beta`: n=18 Brier=0.1145 ECE=0.2722 over=0.0 under=0.0
- family `recA_recombinase`: n=6 Brier=0.1806 ECE=0.2068 over=0.0 under=0.0
- family `tuf_EF_Tu`: n=5 Brier=0.1176 ECE=0.3273 over=0.0 under=0.0
- family `lacZ_beta_galactosidase`: n=5 Brier=0.107 ECE=0.3122 over=0.0 under=0.0
- family `tetA_tetracycline_efflux`: n=8 Brier=0.0829 ECE=0.266 over=0.0 under=0.0
- target_type `gene_orthologue`: n=39 Brier=0.1072 ECE=0.3074
- target_type `exact_allele`: n=2 Brier=0.36 ECE=0.6
- target_type `protein_family`: n=1 Brier=0.0324 ECE=0.18

## Model independence

- Deterministic evidence package is identical across adapters. Missing models are not substituted.
- Setup: {'openai_compatible': 'Serve an OpenAI-compatible /v1/chat/completions endpoint (vLLM, llama.cpp server, Ollama with OpenAI API).', 'ollama': 'Install Ollama and pull models, e.g. `ollama pull qwen3:8b` and `ollama pull deepseek-r1:8b`.', 'gpt': 'Set OPENAI_API_KEY. GPT is optional and is never used as a substitute for missing Qwen/DeepSeek weights.', 'expected_model_names': {'qwen3': ['qwen3:8b', 'qwen3:14b', 'qwen3:32b', 'qwen2.5:7b', 'qwen2.5:14b'], 'deepseek-r1-distill': ['deepseek-r1:8b', 'deepseek-r1:7b', 'deepseek-r1-distill-qwen-7b', 'deepseek-r1-distill-llama-8b', 'deepseek-r1-distill-qwen-14b'], 'gpt': ['gpt-4o', 'gpt-4.1', 'gpt-4o-mini', 'gpt-5'], 'local': []}, 'available_now': [], 'no_silent_substitution': True}
- dry-run `qwen3` resolved=None invented_output=False
- dry-run `deepseek-r1-distill` resolved=None invented_output=False
- dry-run `gpt` resolved=None invented_output=False
- dry-run `local` resolved=None invented_output=False
- qwen3 / qwen3: unavailable=True reason=requested model was not exposed locally/configured and was not substituted
- deepseek-r1-distill / deepseek-r1-distill: unavailable=True reason=requested model was not exposed locally/configured and was not substituted
- qwen3 / deepseek-r1-distill: unavailable=True reason=requested model was not exposed locally/configured and was not substituted
- deepseek-r1-distill / qwen3: unavailable=True reason=requested model was not exposed locally/configured and was not substituted
- gpt / qwen3: unavailable=True reason=requested model was not exposed locally/configured and was not substituted
- gpt / deepseek-r1-distill: unavailable=True reason=requested model was not exposed locally/configured and was not substituted

## Robustness

- counts: {'correct_continuation': 10, 'correct_rejection': 27, 'incorrect_continuation': 0, 'incorrect_rejection': 0}
- Failed-closed is not counted as success unless the input was actually invalid.

## External validation

- freeze aggregate sha256: 0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b
- Official repositories were contacted; missing inputs were not fabricated.
- `bioagent_bench` ok=True commit=6d098b602b8a8fdc33a9d25e410a502be7ed9ce0 error=None
- `promptbio_bench` ok=True commit=e2a1947894eac530900247f00c0b726363b540ed error=None
- `bixbench` ok=True commit=49311180bdacb324c596f2e07596c126f2004008 error=None
- scored original tasks: 0

## Baseline comparisons

On V5 controls the same five systems were run: dummy-cautious, naive-confident, conventional, Genome Skeptic without falsification, and full Genome Skeptic.

## Ablation

No supported external task had local original inputs and scorer; ablations were not invented.

## Failures

- tuf on the reused SPAdes assembly has a single reconstructed locus; near-identical second copy was not present as a distinct BLAST interval
- Qwen3 / DeepSeek-R1-Distill were unavailable locally and were not substituted
- no original external benchmark task was scored; Genome Skeptic is not credited on rewritten proxies

## Scientific limitations

- Competitive family discrimination requires packaged competitor HMMs; families without competitors keep the V4.1 positive gate.
- Near-identical copies that the assembler collapsed to one contig interval cannot be recovered from protein identity alone.
- External transcriptomic and single-cell tasks remain unsupported and are not rewritten.
- Model-independence comparisons were not executed where weights/credentials were absent.

## Label

**internally validated agent**

This label follows the V5 definitions. Internal control scores alone cannot produce 'externally superior'.
