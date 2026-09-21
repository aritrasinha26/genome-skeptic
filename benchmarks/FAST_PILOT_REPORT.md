# FAST PILOT - NOT FINAL BENCHMARK

Interpretable reduced-assembly pilot. **Not** the full production benchmark. Do not mix these scores with a future full benchmark.

- Split in this file: development
- Cases assembled: 3
- Assembly unavailable: 0

| Split | Case | Hidden scenario | Runtime (assembly s / GS s) | Assembly | Conventional | Genome Skeptic | GS confidence | Evidence completeness | Falsification changed conclusion | Overclaim | False absence | Useful next actions |
|---|---|---|---|---|---|---|---:|---:|---|---|---|---|
| development | `dev_01` | none | 986.243 / 16.3 | success | supported (target_gene_not_detected) | weakened (target_gene_not_detected) | 0.46 | 0.63 | yes | no | yes | none |
| development | `dev_02` | none | 1947.643 / 28.6 | success | supported (target_gene_not_detected) | weakened (target_gene_not_detected) | 0.46 | 0.63 | yes | no | no | none |
| development | `dev_03` | none | 399.554 / 9.8 | success | supported (target_gene_not_detected) | weakened (target_gene_not_detected) | 0.46 | 0.63 | yes | no | no | none |
| held_out | `hel_01` | none | 1621.991 / 20.5 | success | supported (target_gene_not_detected) | weakened (target_gene_not_detected) | 0.46 | 0.63 | yes | no | no | inspect_read_supported_breaks; repeat_assembly_after_diagnosing_fragmentation; inspect_contig_edges_for_target |
| held_out | `hel_02` | none | 2585.331 / 36.7 | success | supported (target_gene_not_detected) | weakened (target_gene_not_detected) | 0.46 | 0.63 | yes | no | no | none |
| held_out | `hel_03` | none | 635.412 / 13.1 | success | supported (target_gene_not_detected) | weakened (target_gene_not_detected) | 0.46 | 0.63 | yes | no | no | none |

## Missing dimensions / databases
- kraken2/sourmash taxonomy database (explicitly unavailable; not simulated)
- Bakta database (explicitly unavailable; not simulated)
- CheckM2 database (explicitly unavailable; not simulated)
- CheckM2 executable (not installed) (explicitly unavailable; not simulated)
- checkm2: executable or database missing; completeness not treated as measured.
- bakta: executable or database missing; annotation not treated as measured.

## System overall (pilot only)
- skeptic_no_falsification: 0.9375
- genome_skeptic: 0.9375
- conventional: 0.875
