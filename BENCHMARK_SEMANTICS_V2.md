# BENCHMARK SEMANTICS V2

FAST PILOT v1 scores are **invalid for performance comparison**. The preserved `FAST_PILOT_REPORT.md` files were not rewritten.

## Why v1 was invalid

1. `PUBLIC_RPOB_SEED` is a 122-nt fragment, not the authentic MG1655 rpoB CDS.
2. Hidden truth used locate_target identity ≥ 0.5 with no coverage floor (52/122 bp could count as present).
3. A dummy cautious baseline could tie Genome Skeptic.
4. Held-out cases were all labeled target-absent.
5. Confidence and evidence completeness were nearly constant across biologically different cases.

This run does **not** rerun SPAdes, fastp, or sequencing simulation. Production assemblies were reused.
Revised tests passing is **not** a claim of scientific improvement.

## Target semantics

| target_type | query | truth |
|---|---|---|
| exact_allele | authentic MG1655 rpoB CDS (4029 nt) | exact strain-level sequence relationship |
| gene_orthologue | authentic MG1655 RpoB protein | source-annotation rpoB / documented fusion |
| protein_family | full RpoB protein on synthetic controls | homolog/profile presence; domain-only is not full-gene detection |

Nucleotide identity alone does not define cross-species orthologue truth. Domain-only evidence does not become full-gene detection.
If independent orthology cannot be assigned, the case is labeled unresolved rather than given a manufactured binary label.

## Authentic MG1655 rpoB (replaces PUBLIC_RPOB_SEED)

| field | value |
|---|---|
| accession | NC_000913.3 |
| gene | rpoB |
| locus_tag | b3987 |
| GeneID | 948488 |
| protein_id | NP_418414.1 |
| coordinates | 4181245–4185273 (+) |
| nucleotide length | 4029 |
| protein length | 1342 |
| nucleotide sha256 | 12c5d038046237f76f5d0777bd0d9c2debde53af75cf40c52e32311f1642f2f3 |
| protein sha256 | c33ef6acd9bbcfc005a1c510c5d60b886546d1c6f7ce155daf6989314c1f08af |
| provenance | NCBI RefSeq feature table + hidden source genome |

Cross-species orthologue testing uses this protein, not the MG1655 nucleotide fragment. Ground truth is source annotation / documented fusion, not a locate_target identity threshold.

## Pre-score tables

Printed to stdout during the run and stored in `benchmark_semantics_v2.json` / `target_truth_audit.json`.

## Split scores (group metrics, not one overall)

### development

| System | Overall | detection | scope | status | calibration | completeness | overclaim | underclaim | abstention | next-action |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| naive_confident | 0.444 | 0.833 | 0.000 | 0.429 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0.500 |
| dummy_cautious | 0.667 | 0.417 | 1.000 | 0.286 | 0.143 | 1.000 | 1.000 | 0.455 | 1.000 | 0.500 |
| conventional | 0.852 | 0.833 | 1.000 | 0.714 | 0.714 | 0.500 | 0.833 | 1.000 | 0.000 | 0.500 |
| skeptic_no_falsification | 0.833 | 0.917 | 1.000 | 0.286 | 0.286 | 1.000 | 1.000 | 0.727 | 1.000 | 0.500 |
| genome_skeptic | 0.944 | 0.917 | 1.000 | 0.714 | 0.286 | 1.000 | 1.000 | 1.000 | 1.000 | 0.833 |

- Full Genome Skeptic beats dummy cautious: True
- Full Genome Skeptic beats naive confident: True
- Full Genome Skeptic beats both trivial baselines: True

### held_out

| System | Overall | detection | scope | status | calibration | completeness | overclaim | underclaim | abstention | next-action |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| naive_confident | 0.407 | 0.833 | 0.000 | 0.333 | 0.000 | 0.000 | 0.000 | 0.833 | n/a | 0.500 |
| dummy_cautious | 0.667 | 0.500 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 0.500 | n/a | 0.500 |
| conventional | 0.870 | 0.833 | 1.000 | 0.833 | 0.833 | 0.667 | 1.000 | 0.833 | n/a | 0.500 |
| skeptic_no_falsification | 0.778 | 0.833 | 1.000 | 0.000 | 0.167 | 1.000 | 1.000 | 0.667 | n/a | 0.500 |
| genome_skeptic | 0.852 | 0.833 | 1.000 | 0.333 | 0.167 | 1.000 | 1.000 | 0.833 | n/a | 1.000 |

- Full Genome Skeptic beats dummy cautious: True
- Full Genome Skeptic beats naive confident: True
- Full Genome Skeptic beats both trivial baselines: True

### controls

| System | Overall | detection | scope | status | calibration | completeness | overclaim | underclaim | abstention | next-action |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| naive_confident | 0.307 | 0.667 | 0.000 | 0.118 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0.500 |
| dummy_cautious | 0.841 | 0.611 | 1.000 | 0.824 | 0.412 | 1.000 | 1.000 | 0.692 | 1.000 | 0.500 |
| conventional | 0.682 | 0.667 | 1.000 | 0.294 | 0.471 | 0.700 | 0.300 | 1.000 | 0.000 | 0.500 |
| skeptic_no_falsification | 0.920 | 0.889 | 1.000 | 0.824 | 0.529 | 1.000 | 1.000 | 0.846 | 1.000 | 0.500 |
| genome_skeptic | 0.966 | 0.889 | 1.000 | 0.941 | 0.529 | 1.000 | 1.000 | 1.000 | 1.000 | 0.900 |

- Full Genome Skeptic beats dummy cautious: True
- Full Genome Skeptic beats naive confident: True
- Full Genome Skeptic beats both trivial baselines: True

## Interpretation

Full Genome Skeptic outperformed both trivial baselines (dummy cautious and naive confident) on development, held-out, and synthetic-control mixtures of positive and negative cases.

That is not a claim that Genome Skeptic is calibrated or that it beat ordinary homology calling. On held-out, conventional overall was 0.870 and Genome Skeptic was 0.852. Calibration remains weak (held-out confidence-calibration rate 0.167). Missing Bakta, taxonomy, HMMER, and synteny still lower evidence completeness; completeness and confidence are no longer identical, but confidence is still capped well below 0.85.

Remaining detection miss: *H. pylori* rpoB is a documented beta/beta' fusion (HP_RS05885). Independent annotation truth is present, but protein identity to MG1655 RpoB is 0.463 with query coverage 0.993, below the 0.60 amino-acid identity floor. Nucleotide identity alone was not used as cross-species truth. Domain-only synthetic controls were not promoted to full-gene detection.

Held-out contains both true presence (`rpoB` gene_orthologue) and true absence (`rpoB_MG1655_allele`). Dummy cautious always says `not detected, weakened` and now fails clean positives. Naive confident always converts homology into organism-level present/absent and fails claim-scope scoring.

Revised unit tests passing is **not** a claim of scientific improvement. The old FAST_PILOT scores remain invalid for performance comparison.

## Confidence

Confidence is computed from measured homology (identity, coverage, search mode, truncation, paralogue loci, local depth).
Evidence completeness remains a separate score. Missing Bakta/taxonomy/HMMER/synteny may lower completeness without flattening distinct homology into identical confidence.
The LLM does not choose confidence numerically. Held-out cases were not used to tune confidence.

- Genome Skeptic confidence span: {'min': 0.1388, 'max': 0.5134, 'n': 22, 'unique_rounded_2dp': [0.14, 0.15, 0.23, 0.25, 0.3, 0.31, 0.32, 0.33, 0.41, 0.45, 0.51]}
- Evidence completeness span: {'min': 0.2182, 'max': 0.7667, 'n': 22, 'unique_rounded_2dp': [0.22, 0.34, 0.51, 0.77]}
- Homology support span: {'min': 0.002, 'max': 0.9799, 'n': 22, 'unique_rounded_2dp': [0.0, 0.02, 0.09, 0.11, 0.14, 0.19, 0.3, 0.33, 0.47, 0.5, 0.53, 0.58, 0.95, 0.98]}

## Files

- `benchmark_semantics_v2.json`
- `target_truth_audit.json`
- `confidence_calibration_v2.json`
- archived v1 targets/truth under `archived_fast_pilot_v1/`

