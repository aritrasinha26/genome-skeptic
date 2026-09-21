# FAST PILOT - NOT FINAL BENCHMARK

Reduced-assembly real-genome pilot. Not the full production benchmark.
Do not mix these scores with `benchmarks/real_genomes_dev_eval` or a future full benchmark.

- 3 development genomes + 3 held-out genomes
- Ordinary clean coverage 25x
- SPAdes `--only-assembler -k 21,33,55` (no `--careful`; no K77/K99/K127)
- fastp once; FastQC skipped
- No component ablations
- Missing large databases remain unavailable
