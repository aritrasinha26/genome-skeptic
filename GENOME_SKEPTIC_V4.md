# GENOME SKEPTIC V4

SPAdes was not rerun. FAST_PILOT sequencing data were not regenerated. Truth labels were not edited. Held-out cases were not used to tune thresholds or calibration. V3 reports were left in place.

## Acceptance gates (not a single composite)

- Clean development overall (GS): 0.9629629629629629
- Conventional on the same development cases: 0.8518518518518519
- Dummy / naive on development: 0.6666666666666666 / 0.4444444444444444
- S. aureus held-out (hel_03 only): GS 0.9444444444444444 vs conventional 0.7222222222222222
- Controls overall GS: 0.9577464788732394
- Calibration Brier / ECE: 0.1197 / 0.2356
- Robustness fail-closed cases: 14 / 18
- Model ablation available models: []

## Unique vs conventional (same assemblies, no new SPAdes)

- H. pylori `rpoB`: Genome Skeptic `fusion` / detected; conventional not detected. Partner was required inside the same reconstructed ORF, not merely on the contig.
- PAO1 `rpoB`: Genome Skeptic `canonical_full_length` (not fusion). Adjacent rpoC did not count as a fusion partner.
- S. aureus `rpoB`: Genome Skeptic `canonical_full_length` / detected (status still weakened); conventional not detected.
- Divergent Thermotoga-style control: Genome Skeptic detected; conventional not detected. Architecture was `canonical_full_length` rather than `divergent_full_length` because family-member identity was scored high.

## Key case architectures

- `dev_01` `rpoB_MG1655_allele`: GS target_gene_detected/supported arch=None vs conventional target_gene_detected
- `dev_01` `rpoB`: GS target_gene_detected/supported arch=canonical_full_length vs conventional target_gene_detected
- `dev_02` `rpoB_MG1655_allele`: GS target_gene_not_detected/weakened arch=None vs conventional target_gene_not_detected
- `dev_02` `rpoB`: GS target_gene_detected/supported arch=canonical_full_length vs conventional target_gene_detected
- `dev_03` `rpoB_MG1655_allele`: GS target_gene_not_detected/weakened arch=None vs conventional target_gene_not_detected
- `dev_03` `rpoB`: GS target_gene_detected/weakened arch=fusion vs conventional target_gene_not_detected
- `hel_03` `rpoB_MG1655_allele`: GS target_gene_not_detected/weakened arch=None vs conventional target_gene_not_detected
- `hel_03` `rpoB`: GS target_gene_detected/weakened arch=canonical_full_length vs conventional target_gene_not_detected
- `ctrl_absence` `rpoB`: GS target_gene_not_detected/weakened arch=true_no_candidate vs conventional target_gene_not_detected
- `ctrl_divergent` `rpoB`: GS target_gene_detected/weakened arch=canonical_full_length vs conventional target_gene_not_detected
- `ctrl_domain_only` `rpoB`: GS target_gene_not_detected/weakened arch=true_no_candidate vs conventional target_gene_not_detected
- `ctrl_fragmented` `rpoB`: GS target_gene_not_detected/weakened arch=assembly_fragmented vs conventional target_gene_not_detected
- `ctrl_full_length` `rpoB`: GS target_gene_detected/supported arch=canonical_full_length vs conventional target_gene_detected
- `ctrl_fusion` `rpoB`: GS target_gene_detected/weakened arch=fusion vs conventional target_gene_detected
- `ctrl_paralogue` `rpoB`: GS target_gene_detected/weakened arch=canonical_full_length vs conventional target_gene_detected
- `ctrl_split` `rpoB`: GS target_gene_detected/supported arch=biological_split vs conventional target_gene_detected

## Remaining failures

- Divergent control architecture is `canonical_full_length` rather than `divergent_full_length` (family-member identity was high).
- Domain-only control architecture is `true_no_candidate` (HMM coverage 0.195 just below the 0.20 family gate). Polarity was still non-detection.
- Paralogue control architecture is `canonical_full_length`; `close_paralogue` is never assigned.
- Qwen3 and DeepSeek-R1-Distill were unavailable locally; planner/critic combinations were not silently substituted.
- S. aureus `rpoB` is detected as `canonical_full_length` but the claim status is still weakened.
- Leave-one-genome-out calibration ECE is 0.24 / Brier 0.12 on 15 development+synthetic locus perturbations. Held-out genomes were not used to fit.

Robustness 14/18 fail-closed is not a miss: the other four probes (`ok_fastq`, parseable `truncated_fastq`, `ok_gzip`, `wrong_organism_metadata`) are structurally valid and correctly stayed open.

## Smallest next change

Assign `close_paralogue` when a second high-identity locus exists. Do not lower the family-evidence gate to relabel domain-only, and do not add species rules.

## Files

- GENOME_SKEPTIC_V4.md
- locus_reconstruction_v4.json
- hypothesis_graph_v4.json
- action_policy_v4.json
- calibration_v4.json
- model_ablation_v4.json
- robustness_v4.json
- v3_vs_v4.json
