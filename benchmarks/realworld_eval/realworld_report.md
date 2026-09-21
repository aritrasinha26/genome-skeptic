# Real-world adversarial validation

Ground-truth genomes and the truth manifest were loaded only after claims were produced.

## System totals

| System | Overall | Correct detection | False detection | Overclaiming avoided | Next action |
|---|---:|---:|---:|---:|---:|
| conventional | 0.376 | 9/9 | 1/1 | 0/14 | 2/14 |
| skeptic_no_falsification | 0.683 | 9/9 | 1/1 | 14/14 | 2/14 |
| genome_skeptic | 0.644 | 9/9 | 1/1 | 13/14 | 3/14 |

## Case by case

| Case | Scenario | Conventional | No falsification | Genome Skeptic |
|---|---|---|---|---|
| clean_short_read | none | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| low_coverage | low_coverage | target_gene_not_detected/supported (0.99) | target_gene_not_detected/unresolved (0.4) | target_gene_not_detected/weakened (0.5) |
| uneven_coverage | uneven_coverage | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| adapter_quality_degradation | adapter_quality | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| cross_species_contamination | cross_species_contamination | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| closely_related_strain_contamination | related_strain_contamination | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| high_copy_plasmid | high_copy_plasmid | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| target_paralogues | paralogues | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| target_near_repeat | target_near_repeat | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| target_fragmented | fragmented_target | target_gene_not_detected/supported (0.99) | target_gene_not_detected/unresolved (0.4) | target_gene_not_detected/weakened (0.5) |
| target_contig_break | contig_break | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/supported (0.37) |
| divergent_homologue | divergent_homologue | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |
| genuine_absence | genuine_absence | target_gene_not_detected/supported (0.99) | target_gene_not_detected/unresolved (0.4) | target_gene_not_detected/weakened (0.5) |
| incorrect_organism_identity | incorrect_organism_identity | target_gene_detected/supported (0.99) | target_gene_detected/unresolved (0.4) | target_gene_detected/weakened (0.5) |

## Highlights: conventional threshold success vs unsupported conclusions
### case_01 (none)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_02 (low_coverage)
- Conventional: Target gene 'rpoB' is absent from the organism.
- Genome Skeptic: weakened � Target gene 'rpoB' was not detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_03 (uneven_coverage)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_04 (adapter_quality)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_05 (cross_species_contamination)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_06 (related_strain_contamination)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_07 (high_copy_plasmid)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_08 (paralogues)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_09 (target_near_repeat)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_10 (fragmented_target)
- Conventional: Target gene 'rpoB' is absent from the organism.
- Genome Skeptic: weakened � Target gene 'rpoB' was not detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_11 (contig_break)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: supported � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_12 (divergent_homologue)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_13 (genuine_absence)
- Conventional: Target gene 'rpoB' is absent from the organism.
- Genome Skeptic: weakened � Target gene 'rpoB' was not detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

### case_14 (incorrect_organism_identity)
- Conventional: Target gene 'rpoB' is present in the isolate.
- Genome Skeptic: weakened � Target gene 'rpoB' is detected in the current assembly.
- Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.

## Limitations
- Cases use miniature complete-genome analogues (chromosome + plasmid), not downloaded NCBI genomes.
- eval assembler is a toy de Bruijn graph; homopolymer/N pads are randomized at simulation time, but it is not SPAdes and often fragments miniature genomes.
- Kraken2/sourmash contig taxonomy runs only when a database is configured; otherwise taxonomy is recorded as missing, not inferred.
- Read simulators prefer wgsim; tests fall back to a documented internal Illumina-like simulator.
- Thresholds were not tuned to force perfect scores.
- Falsification-disabled Skeptic scores well on uncertainty because every claim is unresolved; that is not the same as measured doubt.
- Contamination recognition currently credits weakened/unresolved status when no classifier database is present, so it overstates taxonomic awareness in CI.
- Next-action scoring is strict against a hidden expected list; useful extra diagnostics can look like unnecessary analyses.
