# Real-world adversarial validation

Ground-truth genomes and the truth manifest were loaded only after claims were produced.

## System totals

| System | Overall | Organism-level avoided | Overconfidence avoided | Underconfidence avoided | Overclaiming avoided | Next action |
|---|---:|---:|---:|---:|---:|---:|
| conventional | 0.304 | 0/14 | 0/11 | 2/2 | 0/14 | 2/14 |
| skeptic_no_falsification | 0.975 | 14/14 | 11/11 | 0/2 | 14/14 | 2/14 |
| genome_skeptic | 0.975 | 14/14 | 10/11 | 2/2 | 13/14 | 13/14 |

## Case by case

| Case | Scenario | Conventional | No falsification | Genome Skeptic |
|---|---|---|---|---|
| clean_short_read | none | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| low_coverage | low_coverage | target_gene_not_detected/supported (0.99) | target_gene_not_detected/unresolved (0.4) | target_gene_not_detected/weakened (0.44) |
| uneven_coverage | uneven_coverage | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| adapter_quality_degradation | adapter_quality | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| cross_species_contamination | cross_species_contamination | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| closely_related_strain_contamination | related_strain_contamination | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| high_copy_plasmid | high_copy_plasmid | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| target_paralogues | paralogues | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| target_near_repeat | target_near_repeat | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| target_fragmented | fragmented_target | target_gene_not_detected/supported (0.99) | target_gene_not_detected/unresolved (0.4) | target_gene_not_detected/weakened (0.44) |
| target_contig_break | contig_break | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/supported (0.3256) |
| divergent_homologue | divergent_homologue | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |
| genuine_absence | genuine_absence | target_gene_not_detected/supported (0.99) | target_gene_not_detected/unresolved (0.4) | target_gene_not_detected/weakened (0.44) |
| incorrect_organism_identity | incorrect_organism_identity | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.44) |

## Highlights: conventional threshold success vs unsupported conclusions
### case_01 (none)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_02 (low_coverage)
- Conventional: Target gene 'rpoB' is absent from the organism.
- Genome Skeptic: weakened — Target gene 'rpoB' was not detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_03 (uneven_coverage)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_04 (adapter_quality)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_05 (cross_species_contamination)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_06 (related_strain_contamination)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_07 (high_copy_plasmid)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_08 (paralogues)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_09 (target_near_repeat)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_10 (fragmented_target)
- Conventional: Target gene 'rpoB' is absent from the organism.
- Genome Skeptic: weakened — Target gene 'rpoB' was not detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_11 (contig_break)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: supported — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_12 (divergent_homologue)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_13 (genuine_absence)
- Conventional: Target gene 'rpoB' is absent from the organism.
- Genome Skeptic: weakened — Target gene 'rpoB' was not detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_14 (incorrect_organism_identity)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened — Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

## Limitations
- Cases use miniature complete-genome analogues (chromosome + plasmid), not downloaded NCBI genomes.
- eval assembler is a toy de Bruijn graph; homopolymer/N pads are randomized at simulation time, but it is not SPAdes and often fragments miniature genomes.
- Kraken2/sourmash contig taxonomy runs only when a database is configured; otherwise taxonomy is recorded as missing, not inferred.
- Read simulators prefer wgsim; tests fall back to a documented internal Illumina-like simulator.
- Thresholds were not tuned to force perfect scores, including not on held-out genomes.
- Scientific overall now scores calibration rather than generic caution: unresolved on a clean locus is penalized.
- Falsification-disabled Skeptic is unresolved on every claim; that is indiscriminate caution, not measured doubt.
- Next-action scoring uses scientific action classes. Extra useful diagnostics are not automatically penalized; repeats are.
