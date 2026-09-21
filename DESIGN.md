# Design notes

The MVP is deliberately split into three layers.

The measurement layer contains deterministic bioinformatics tools. It owns facts such as Q30 rate, assembly size, N50, mapping rate, depth distribution, completeness, contamination, and predicted gene count. These values never come from the language model.

The scientific reasoning layer receives compact structured evidence and asks what the results mean, what else could explain them, and what should be tested next. The local model is replaceable. It is currently wired to Ollama.

## Coordinate convention

All in-memory genomic intervals are **0-based, half-open** `[start, end)` on the forward strand of the named contig (`genome_skeptic.coords`). GFF3/GTF files remain 1-based closed at parse/write boundaries. SAM/BAM POS is 1-based and is converted before comparison with hit coordinates. Homology hits, depth windows, synteny, and locus evidence use the internal convention only.

## Isolated evaluation

Real-world benchmark generation writes agent-visible FASTQ, targets, declared organism, and permitted references separately from a scorer-only tree. The analysis agent, conventional baseline, and locus pipeline refuse paths under `hidden` / `ground_truth` / `scorer_only` and refuse `truth.yaml`, `simulation_provenance.yaml`, and `source_genome.fa` unless they sit under `agent_visible`. Scoring loads the truth manifest only after claims exist.

## Contig taxonomy, breaks, and placement

Contig taxonomy is measured by kraken2 or sourmash when a database is configured. It is never inferred from reference-genome metadata or invented by the LLM. Contig-edge claims use paired-end clip / mate-unmapped / discordant evidence when mapping exists; geometric proximity is only a fallback when mapping is unavailable. Reciprocal best hit remains the fast orthology test. Ambiguous cases may add identity-based neighbor-joining (or FastTree when installed) among labeled homologues.

## Evidence completeness and calibrated uncertainty

Every claim records `evidence_completeness` from which expected validators completed, using documented importance classes (essential, high-value, supporting, optional). The LLM does not assign this number. Status stays independent: missing optional tests do not force `unresolved`. Missing essential/high-value tests lower completeness and may lower confidence.

Evaluation scores calibration, not generic caution. Clean unambiguous loci penalize unnecessary unresolved conclusions. Ambiguous loci penalize unjustified confidence and organism-level language.

The real-genome production benchmark simulates paired-end reads from complete hidden RefSeq genomes (anonymized headers), then runs FastQC → fastp → FastQC → SPAdes → QUAST → minimap2/samtools. CheckM2/Bakta/Kraken2 remain unavailable until their databases are configured. The toy assembler is never used. Docker (`environment.yml`) is the canonical production environment. The miniature synthetic benchmark is a regression suite only.

## Evidence graph

Every external tool result creates an evidence record. Claims cite evidence IDs. Model-generated decisions that cite nonexistent evidence are rejected. This is the beginning of a provenance graph that can later record explicit edges such as supports, contradicts, derived-from, and tested-by.

## Hard gates

A hard gate is deterministic and cannot be overridden by an LLM. Current examples are invalid input, missing required stage output, and very high estimated contamination. Thresholds are configuration, not universal truths.

## Falsification-first claims

The initial claims are intentionally modest. The pipeline can currently conclude that an assembly is sufficiently supported to proceed to annotation and that the annotation is internally plausible. It does not yet claim that a particular biological gene is truly absent.

The next module should implement target-gene reasoning. A negative search result should create a claim such as "target not detected in current assembly" rather than "target absent from organism". The system should then try direct nucleotide search, translated search, partial-domain search, contig-edge proximity, local read coverage, and conserved-neighborhood evidence before changing the claim status.

## Why the LLM is not used for everything

Using a language model to estimate sequence quality or assembly completeness would make the system less reliable. The goal is open local intelligence around open computational tools, not replacing validated algorithms with text generation. Models decide what evidence is needed and interpret measured evidence. They do not manufacture the evidence.
