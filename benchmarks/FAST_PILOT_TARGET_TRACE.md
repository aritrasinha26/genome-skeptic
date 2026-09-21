# FAST PILOT target-detection failure analysis

**FAST PILOT — NOT FINAL BENCHMARK.** Diagnostic only. Scientific thresholds, claim rules, falsification logic, evidence-completeness weights, and scoring were not modified. Existing FAST_PILOT assemblies and evidence were reused; SPAdes was not rerun.

All measurements below were produced by exact string search, SHA256, BLAST+/minimap2 if present, or the existing deterministic internal gene search. None were inferred by an LLM.

## Findings (measured)

1. **dev_01 is not a biological false absence of rpoB in the assembly.** The 122-nt query `rpoB` (`PUBLIC_RPOB_SEED`) is **not present as an exact string in the hidden E. coli K-12 source** and BLASTN/TBLASTN do not recover a gene-length homolog of Q in that source. The target was already absent before SPAdes.
2. Hidden truth still marks `present: true` because `locate_target` accepts any internal hit with **identity ≥ 0.5 and no coverage requirement**. The accepted hit is identity 0.654, query coverage **0.426**, 52 bp on `replicon_1:124319-124371`.
3. Genome Skeptic's `not_detected` polarity matches the unchanged 80/80 rule and independent BLASTN (best HSP identity 0.778, query coverage 0.295). The assembly did not destroy a present Q; Q was never in the source.
4. Completeness 0.63 and confidence 0.46 are the same arithmetic on every FAST_PILOT case (missing Bakta proteins + unwired `depth.tsv` + weakened-not-detected cap).
5. A dummy that always says `not_detected / weakened / 0.46 / 0.63` scores **0.9375 development and 1.000 held-out** — identical to Genome Skeptic. The held-out 1.000 is not discriminative.
6. Four tiny diagnostic controls **do** separate: exact-nt and protein orthologue → `detected/supported`; empty family → `not_detected/supported`; domain paralogue → `not_detected/weakened`. The FAST_PILOT genomes never reach those states because Q is not a recoverable gene in any of them.

## 1. Target representation (dev_01 query)

- FASTA identifier: `rpoB`
- Nucleotide length: `122`
- SHA256 of nucleotide sequence: `2713eb80b5e6a38e58d316616b67014dcf6373a297008caf91881cec67eafc0a`
- Nucleotide sequence: `GTGCAGATCCCGCGTGAAGGTCTGATCGCGCGTACCGGTGAAACCGTAGCTGAAGCTCTGAAAGGTCTGCGTGAACTGCCGGGTATCAACCTGCCGGAAGGTGTTGAAGTTGAAACCGAAGT`
- Representation: 122-nt public seed labelled `rpoB` (`PUBLIC_RPOB_SEED`). Independent BLASTN/TBLASTN against hidden MG1655 show it is **not** an authentic full-window E. coli rpoB allele.
- Chosen translated protein (longest ungapped prefix among frames 0–2): `VQIPREGLIARTGETVAEALKGLRELPGINLPEGVEVETE`
- Protein length: `40`
- SHA256 of chosen protein: `8e996def7688509f188d1091f1ce3a6ee79c175e0105b43b03a034c72a8aeafc`

Translated frames:

- frame 0: length_aa=40 `VQIPREGLIARTGETVAEALKGLRELPGINLPEGVEVETE`
- frame 1: length_aa=7 `CRSRVKV`
- frame 2: length_aa=4 `ADPA`

## 2. Hidden source locus (scorer-side only)

- Source FASTA: `/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev/hidden/genomes/ecoli_k12/sim_source.fa`
- Source file SHA256: `635d5790b0a3a2fe838ce3ea76369444676842a8393701eac312f94346400679`
- Exact complete target present in hidden source: **False**
- `locate_target` (truth rule: identity ≥ 0.5): `{"contig": "replicon_1", "start": 124319, "end": 124371, "identity": 0.6538461538461539, "coverage": 0.4262295081967213}`

## 3. SPAdes assembly

- Assembly path: `/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades/contigs.fasta`
- Assembly SHA256: `5006cf1945e78747c9f60e201e25a61965e364703ad7b2220e52b82d3e69a83f`
- Contigs: 208; total bp: 4575432
- Complete exact target present in assembly: **False**
- SPAdes command: `Command line: /home/aritr/micromamba/envs/genome-skeptic-prod/bin/spades.py	-1	/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/fastp/clean_R1.fastq.gz	-2	/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/fastp/clean_R2.fastq.gz	-o	/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades	-t	4	-m	3	--only-assembler	-k	21,33,55	`
- Mapping command: `[M::main] CMD: minimap2 -ax sr -t 4 /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades/contigs.fasta /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/fastp/clean_R1.fastq.gz /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/fastp/clean_R2.fastq.gz`

No exact complete copy of Q was found in `contigs.fasta` (forward or reverse complement).

## 4. Independent alignment of Q versus the assembly

### BLASTN (preferred independent check)

- Program exited successfully: **True**
- Command: `/home/aritr/micromamba/envs/genome-skeptic-prod/bin/blastn -query /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/fast_pilot_target_diagnostics/query_rpoB.fa -subject /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades/contigs.fasta -task blastn -evalue 10 -word_size 7 -outfmt 6 qseqid sseqid pident length qlen slen qstart qend sstart send qcovs evalue bitscore -max_hsps 20 -max_target_seqs 20`
- n_hits: 41

1. sseqid=`NODE_5_length_203134_cov_10.871784` pident=77.778% identity_frac=0.7778 query_coverage=0.2951 qcovs=72.0 length=36 q=74-109 s=103775-103810 evalue=0.39 bitscore=30.1
2. sseqid=`NODE_8_length_174202_cov_10.736200` pident=80.0% identity_frac=0.8000 query_coverage=0.2705 qcovs=64.0 length=35 q=11-43 s=62539-62573 evalue=0.39 bitscore=30.1
3. sseqid=`NODE_4_length_209738_cov_10.647215` pident=76.471% identity_frac=0.7647 query_coverage=0.2787 qcovs=48.0 length=34 q=6-39 s=100161-100128 evalue=4.7 bitscore=26.5
4. sseqid=`NODE_16_length_95454_cov_10.618770` pident=85.714% identity_frac=0.8571 query_coverage=0.2213 qcovs=29.0 length=28 q=21-47 s=6766-6793 evalue=0.39 bitscore=30.1
5. sseqid=`NODE_42_length_31580_cov_10.902427` pident=82.143% identity_frac=0.8214 query_coverage=0.2295 qcovs=23.0 length=28 q=83-110 s=28423-28399 evalue=4.7 bitscore=27.4

### TBLASTN (protein query vs assembly nucleotides)

- Program exited successfully: **True**
- Command: `/home/aritr/micromamba/envs/genome-skeptic-prod/bin/tblastn -query /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/fast_pilot_target_diagnostics/query_rpoB.faa -subject /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades/contigs.fasta -evalue 10 -word_size 2 -outfmt 6 qseqid sseqid pident length qlen slen qstart qend sstart send qcovs evalue bitscore -max_hsps 20 -max_target_seqs 20`
- n_hits: 26

1. sseqid=`NODE_12_length_132884_cov_10.556768` pident=41.379% identity_frac=0.4138 query_coverage=0.7000 q=8-35 s=79146-79060 evalue=3.6
2. sseqid=`NODE_2_length_268099_cov_10.821809` pident=50.0% identity_frac=0.5000 query_coverage=0.5750 q=12-34 s=57940-57869 evalue=5.0
3. sseqid=`NODE_19_length_87014_cov_10.647110` pident=42.857% identity_frac=0.4286 query_coverage=0.6500 q=13-38 s=65911-65828 evalue=2.0
4. sseqid=`NODE_10_length_133235_cov_11.098198` pident=31.429% identity_frac=0.3143 query_coverage=0.8750 q=3-37 s=2751-2647 evalue=3.9
5. sseqid=`NODE_15_length_105636_cov_10.789650` pident=39.286% identity_frac=0.3929 query_coverage=0.7000 q=13-40 s=63843-63760 evalue=2.8

### minimap2

- Program exited successfully: **True**
- Command: `/home/aritr/micromamba/envs/genome-skeptic-prod/bin/minimap2 -c -x sr /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades/contigs.fasta /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/fast_pilot_target_diagnostics/query_rpoB.fa`
- n_hits: 0


### Existing deterministic internal gene search (labelled)

- Label: existing deterministic ungapped k-mer search (not BLAST)
- Command: `internal_gene_search --targets /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev/agent_visible/dev_01/targets.fa --contigs /mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades/contigs.fasta`
- k_nt=8 k_aa=3 max_mismatch_rate_nt=0.35 max_mismatch_rate_aa=0.6000000000000001
- Detection rule (unchanged): nucleotide identity≥0.8 and query_coverage≥0.8; translated identity≥0.6 and query_coverage≥0.8
- n nucleotide hits: 3; n translated hits: 17; n strong: 0; n partial: 17
- Predicted proteins exist: False; best predicted-protein hit: None
- Gene split across multiple contigs: **false**. BLASTN reported short HSPs on many contigs (best query coverage 0.295). These are scattered low-quality matches, not complementary fragments of one split gene. Combined they do not reconstruct Q.
- Partial hits exist: **yes** (17 internal translated/partial hits; 0 strong hits).
- Search programs: BLASTN exited 0; TBLASTN exited 0; minimap2 `-x sr` exited 0 with 0 PAF hits (preset is a poor match for a 122-nt query); internal ungapped search completed (no subprocess, tool=`internal_gene_search`).

Best nucleotide hit:

contig `NODE_5_length_203134_cov_10.871784`  
identity=0.6538461538461539  query_coverage=0.4262295081967213  alignment_length=52  coords query 70-122 subject 103771-103823  strand=+ edge_distance=99311 contig_length=203134

Best translated hit:

contig `NODE_1_length_269802_cov_10.770971`  
identity=0.4074074074074074  query_coverage=0.675  alignment_length=81  coords query 1-28 subject 205864-205945  strand=+ edge_distance=63857 contig_length=269802

## 5. Read coverage at the locus

- depth.tsv exists: True
- mapped.sam exists: True
- Eval pipeline sets `depth_available`: False
- Claim limitation for `local_read_coverage`: read-back depth was unavailable
- Locus used for this diagnostic depth window: `{"contig": "NODE_5_length_203134_cov_10.871784", "start": 103774, "end": 103810}`
- Depth at that window: `{"local_mean_depth": 24.055555555555557, "genome_mean_depth": 25.404068786887212, "relative_depth": 0.9469174311152978, "positions_counted": 36, "zero_positions": 0}`

Mapping exists on disk. The FAST_PILOT eval path never loads `depth.tsv` into `TargetMeasurements.depth_available`, so `local_read_coverage` is skipped even though a depth file is present. That is a wiring gap, not absent data.

## 6. Where the known-positive E. coli target was lost

Loss point: **target definition / truth assignment, before assembly.**

- Exact nucleotide string Q is **absent** from hidden `ecoli_k12` source (`sim_source.fa` SHA256 `635d5790b0a3a2fe838ce3ea76369444676842a8393701eac312f94346400679`). Forward and reverse-complement exact search returned zero hits.
- Independent BLASTN versus that source: best HSP identity 0.778, query coverage 0.295, length 36 bp, evalue 0.39, bitscore 30.1, `replicon_1:124323-124358`. That is a short spurious HSP, not a 122-nt gene alignment. Combined `qcovs` of 84% concatenates unrelated short HSPs and is not a single locus.
- Independent TBLASTN of the 40-aa translation versus the same source: best HSP identity 0.414, query coverage 0.70, length 29 aa, evalue 3.6. The peptide is not recovered as a high-identity protein in MG1655.
- Hidden truth nevertheless sets `present: true` because `locate_target` keeps a 52-bp internal hit at identity 0.654 (coverage 0.426) and the truth rule is identity ≥ 0.5 **with no coverage floor**. Scorer-side locus recorded: `replicon_1` start 124319 end 124371 (as returned by `locate_target`; not an NCBI gene annotation).
- SPAdes therefore could not emit Q. Assembly SHA256 `5006cf1945e78747c9f60e201e25a61965e364703ad7b2220e52b82d3e69a83f`, 208 contigs, 4,575,432 bp. Exact Q absent from `contigs.fasta`. BLASTN versus assembly: best HSP identity 0.778, query coverage 0.295, `NODE_5_length_203134_cov_10.871784:103775-103810`, distance to contig edge 99,311 bp, contig length 203,134. This is the same class of short match as in the source, not a lost intact gene.
- Read coverage at that 36-bp window: local mean depth 24.06, genome mean 25.40, relative 0.947, zero-depth positions 0. The locus is well covered; coverage collapse is not the failure mode.
- Genome Skeptic internal search: best nucleotide identity 0.654, query coverage 0.426, alignment 52 bp on the same NODE_5 window; 0 strong hits; 17 partial translated hits. Search completed. Thresholds were not changed: nucleotide 0.80/0.80, amino-acid 0.60/0.80, k_nt=8, k_aa=3, mismatch rates 0.35 / 0.60.
- **Homology search vs assembly:** the assembly did not cause the miss. Independent BLASTN agrees with internal search that Q fails 80/80. The false-absence label is a **truth-rule error** (identity≥0.5, no coverage) plus a **query that is not an authentic MG1655 rpoB window**, not an assembler or search-program crash.

## 7. Is 80/80 conceptually appropriate for this target?

The query is a **122-nt E. coli rpoB fragment**, not a full-length gene and not an HMM profile. Hidden truth marks `present` when `locate_target` (internal search) reports identity ≥ 0.5. Detection polarity uses a different rule: nucleotide 80/80 or amino-acid 60/80.

| genome | exact nt Q in source | locate_target identity | BLASTN meets 80/80 | TBLASTN meets 60/80 | hidden truth present |
|---|---|---|---|---|---|
| `ecoli_k12` | False | 0.6538461538461539 | False | False | True |
| `pao1` | False | 0.4074074074074074 | False | False | False |
| `hpylori` | False | 0.4074074074074074 | False | False | False |
| `salmonella_lt2` | False | 0.4230769230769231 | False | False | False |
| `pputida_kt2440` | False | 0.4074074074074074 | False | False | False |
| `staph_8325` | False | 0.4 | False | False | False |

Interpretation of detection modes (definitions only; truth was not rewritten):

- **Exact strain-level allele:** requires the E. coli nucleotide string (or a near-identical allele). 80/80 nucleotide is a reasonable operationalisation of that question, but the truth rule (identity ≥ 0.5) is looser than detection (80/80).
- **Same-gene detection across species:** rpoB exists in all six FAST_PILOT organisms. Nucleotide 80/80 against an E. coli fragment will fail in distant taxa even when the orthologue is present. Protein/profile search is the matching reference strategy for that question.
- **Orthologue-family detection:** would use a protein or HMM reference. Current FASTA seed does not encode that question.
- **Domain-level detection:** a short conserved peptide would be expected to hit paralogues; that is a different claim from gene presence.

A nucleotide sequence from E. coli should not automatically be expected to meet the same nucleotide threshold in distantly related bacteria. The FAST_PILOT hidden truth currently answers a hybrid question: 'did the internal k-mer search find this 122-nt seed at ≥50% identity in the source genome, ignoring coverage?' That is neither exact-allele presence nor orthologue-family presence.

Measured consequence: **no FAST_PILOT source genome contains exact Q, and none meets nucleotide 80/80 or amino-acid 60/80 against Q**, including E. coli K-12. If the scientific question is 'is authentic rpoB present?', this seed is the wrong reference (TBLASTN does not recover a high-identity protein in MG1655). If the question is 'is this exact 122-nt allele present?', hidden truth should be `present: false` for all six genomes. Truth was not rewritten in this milestone. Scoring was not changed.

## 8. Diagnostic controls (independent of benchmark scoring)

Tiny synthetic assemblies. No SPAdes. Genome Skeptic was run with unchanged thresholds.

| control | intended biology | claim_type | status | confidence | completeness | n_strong | n_partial |
|---|---|---|---|---:|---:|---:|---:|
| `pos1_exact_nt` | exact nucleotide target inserted in a synthetic contig | target_gene_detected | supported | 0.1326 | 0.2182 | 2 | 0 |
| `pos2_protein_orthologue` | divergent amino-acid orthologue reverse-translated into a contig | target_gene_detected | supported | 0.1326 | 0.2182 | 1 | 1 |
| `neg1_no_family` | synthetic sequence with no planted rpoB family | target_gene_not_detected | supported | 0.484 | 0.5067 | 0 | 0 |
| `neg2_domain_paralogue` | chimeric protein sharing only a short conserved stretch | target_gene_not_detected | weakened | 0.44 | 0.5067 | 0 | 2 |

Controls collapsed to a single (claim_type, status, confidence≈) pattern: **False**.

Polarity and status differ as required:

- Positive control 1 (exact Q inserted): `target_gene_detected`, `supported`.
- Positive control 2 (30% amino-acid-divergent reverse-translated orthologue): `target_gene_detected`, `supported`.
- Negative control 1 (no planted family): `target_gene_not_detected`, `supported` (no partials, so the claim is not weakened).
- Negative control 2 (12-aa conserved stretch only): `target_gene_not_detected`, `weakened`.

Confidence on the two detected controls is low (0.13) because the **detected** attack plan expects taxonomy, synteny, reciprocal hits, and other validators that are unavailable without Bakta/references. That is a completeness cap on a correct polarity, not a collapse to `not_detected`. The FAST_PILOT six-genome run never produced these four patterns because Q is not recoverable in those assemblies.

## 9. Evidence completeness ≈ 0.63 on every FAST_PILOT case

Expected validators for `target_gene_not_detected` and their weights: nucleotide_homology 4, translated_homology 4, predicted_protein_homology 2, partial_domain_hits 2, contig_edge_truncation 2, assembly_fragmentation 2, local_read_coverage 2, divergent_homologues 2, read_supported_break 2, reference_neighbor_presence 1, expected_neighboring_genes 1. Denominator = 24 if all are applicable.

Completed contribution if the same six tests complete and the same four are skipped: (4+4+2+2+2+2+2)/24 = 18/24 = 0.75. Two missing high-value tests (`predicted_protein_homology`, `local_read_coverage`) apply multiplier max(0.55, 1−0.08×2) = 0.84. 0.75 × 0.84 = **0.63**. Bakta proteins are unavailable, so predicted-protein homology is always skipped. `depth.tsv` exists but is not wired, so local read coverage is always skipped. No reference neighbors are configured. This constant is a missing-dependency / wiring consequence, not six independent biological completeness values.

### dev_01 (development, genome `ecoli_k12`, hidden present=True)

- Recorded completeness 0.63; recomputed 0.63
- Weighted done 18.0 / 24.0
- Missing essential: []
- Missing high-value: ['predicted_protein_homology', 'local_read_coverage']
- Unavailable: ['predicted_protein_homology:rpoB', 'local_read_coverage:rpoB', 'reference_neighbor_presence:rpoB', 'expected_neighboring_genes:rpoB']

| prefix | importance | weight | status | result | limitation | weighted_done |
|---|---|---:|---|---|---|---:|
| nucleotide_homology | essential | 4.0 | completed | supports_claim |  | 4.0 |
| translated_homology | essential | 4.0 | completed | weakens_claim |  | 4.0 |
| predicted_protein_homology | high_value | 2.0 | skipped | not_run | predicted proteins were unavailable | 0.0 |
| partial_domain_hits | high_value | 2.0 | completed | weakens_claim |  | 2.0 |
| contig_edge_truncation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| assembly_fragmentation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| local_read_coverage | high_value | 2.0 | skipped | not_run | read-back depth was unavailable | 0.0 |
| divergent_homologues | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| read_supported_break | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| reference_neighbor_presence | supporting | 1.0 | skipped | not_run | no trusted reference genome was configured; orthologues and gene order were not invented | 0.0 |
| expected_neighboring_genes | supporting | 1.0 | skipped | not_run | no expected neighboring genes were specified | 0.0 |

Confidence path: polarity base 0.55 → status `weakened` → confidence_for 0.5 → after completeness 0.46 (recorded 0.46).

### dev_02 (development, genome `pao1`, hidden present=False)

- Recorded completeness 0.63; recomputed 0.63
- Weighted done 18.0 / 24.0
- Missing essential: []
- Missing high-value: ['predicted_protein_homology', 'local_read_coverage']
- Unavailable: ['predicted_protein_homology:rpoB', 'local_read_coverage:rpoB', 'reference_neighbor_presence:rpoB', 'expected_neighboring_genes:rpoB']

| prefix | importance | weight | status | result | limitation | weighted_done |
|---|---|---:|---|---|---|---:|
| nucleotide_homology | essential | 4.0 | completed | supports_claim |  | 4.0 |
| translated_homology | essential | 4.0 | completed | weakens_claim |  | 4.0 |
| predicted_protein_homology | high_value | 2.0 | skipped | not_run | predicted proteins were unavailable | 0.0 |
| partial_domain_hits | high_value | 2.0 | completed | weakens_claim |  | 2.0 |
| contig_edge_truncation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| assembly_fragmentation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| local_read_coverage | high_value | 2.0 | skipped | not_run | read-back depth was unavailable | 0.0 |
| divergent_homologues | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| read_supported_break | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| reference_neighbor_presence | supporting | 1.0 | skipped | not_run | no trusted reference genome was configured; orthologues and gene order were not invented | 0.0 |
| expected_neighboring_genes | supporting | 1.0 | skipped | not_run | no expected neighboring genes were specified | 0.0 |

Confidence path: polarity base 0.55 → status `weakened` → confidence_for 0.5 → after completeness 0.46 (recorded 0.46).

### dev_03 (development, genome `hpylori`, hidden present=False)

- Recorded completeness 0.63; recomputed 0.63
- Weighted done 18.0 / 24.0
- Missing essential: []
- Missing high-value: ['predicted_protein_homology', 'local_read_coverage']
- Unavailable: ['predicted_protein_homology:rpoB', 'local_read_coverage:rpoB', 'reference_neighbor_presence:rpoB', 'expected_neighboring_genes:rpoB']

| prefix | importance | weight | status | result | limitation | weighted_done |
|---|---|---:|---|---|---|---:|
| nucleotide_homology | essential | 4.0 | completed | supports_claim |  | 4.0 |
| translated_homology | essential | 4.0 | completed | weakens_claim |  | 4.0 |
| predicted_protein_homology | high_value | 2.0 | skipped | not_run | predicted proteins were unavailable | 0.0 |
| partial_domain_hits | high_value | 2.0 | completed | weakens_claim |  | 2.0 |
| contig_edge_truncation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| assembly_fragmentation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| local_read_coverage | high_value | 2.0 | skipped | not_run | read-back depth was unavailable | 0.0 |
| divergent_homologues | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| read_supported_break | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| reference_neighbor_presence | supporting | 1.0 | skipped | not_run | no trusted reference genome was configured; orthologues and gene order were not invented | 0.0 |
| expected_neighboring_genes | supporting | 1.0 | skipped | not_run | no expected neighboring genes were specified | 0.0 |

Confidence path: polarity base 0.55 → status `weakened` → confidence_for 0.5 → after completeness 0.46 (recorded 0.46).

### hel_01 (held_out, genome `salmonella_lt2`, hidden present=False)

- Recorded completeness 0.63; recomputed 0.63
- Weighted done 18.0 / 24.0
- Missing essential: []
- Missing high-value: ['predicted_protein_homology', 'local_read_coverage']
- Unavailable: ['predicted_protein_homology:rpoB', 'local_read_coverage:rpoB', 'reference_neighbor_presence:rpoB', 'expected_neighboring_genes:rpoB']

| prefix | importance | weight | status | result | limitation | weighted_done |
|---|---|---:|---|---|---|---:|
| nucleotide_homology | essential | 4.0 | completed | supports_claim |  | 4.0 |
| translated_homology | essential | 4.0 | completed | weakens_claim |  | 4.0 |
| predicted_protein_homology | high_value | 2.0 | skipped | not_run | predicted proteins were unavailable | 0.0 |
| partial_domain_hits | high_value | 2.0 | completed | weakens_claim |  | 2.0 |
| contig_edge_truncation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| assembly_fragmentation | high_value | 2.0 | completed | weakens_claim |  | 2.0 |
| local_read_coverage | high_value | 2.0 | skipped | not_run | read-back depth was unavailable | 0.0 |
| divergent_homologues | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| read_supported_break | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| reference_neighbor_presence | supporting | 1.0 | skipped | not_run | no trusted reference genome was configured; orthologues and gene order were not invented | 0.0 |
| expected_neighboring_genes | supporting | 1.0 | skipped | not_run | no expected neighboring genes were specified | 0.0 |

Confidence path: polarity base 0.55 → status `weakened` → confidence_for 0.5 → after completeness 0.46 (recorded 0.46).

### hel_02 (held_out, genome `pputida_kt2440`, hidden present=False)

- Recorded completeness 0.63; recomputed 0.63
- Weighted done 18.0 / 24.0
- Missing essential: []
- Missing high-value: ['predicted_protein_homology', 'local_read_coverage']
- Unavailable: ['predicted_protein_homology:rpoB', 'local_read_coverage:rpoB', 'reference_neighbor_presence:rpoB', 'expected_neighboring_genes:rpoB']

| prefix | importance | weight | status | result | limitation | weighted_done |
|---|---|---:|---|---|---|---:|
| nucleotide_homology | essential | 4.0 | completed | supports_claim |  | 4.0 |
| translated_homology | essential | 4.0 | completed | weakens_claim |  | 4.0 |
| predicted_protein_homology | high_value | 2.0 | skipped | not_run | predicted proteins were unavailable | 0.0 |
| partial_domain_hits | high_value | 2.0 | completed | weakens_claim |  | 2.0 |
| contig_edge_truncation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| assembly_fragmentation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| local_read_coverage | high_value | 2.0 | skipped | not_run | read-back depth was unavailable | 0.0 |
| divergent_homologues | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| read_supported_break | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| reference_neighbor_presence | supporting | 1.0 | skipped | not_run | no trusted reference genome was configured; orthologues and gene order were not invented | 0.0 |
| expected_neighboring_genes | supporting | 1.0 | skipped | not_run | no expected neighboring genes were specified | 0.0 |

Confidence path: polarity base 0.55 → status `weakened` → confidence_for 0.5 → after completeness 0.46 (recorded 0.46).

### hel_03 (held_out, genome `staph_8325`, hidden present=False)

- Recorded completeness 0.63; recomputed 0.63
- Weighted done 18.0 / 24.0
- Missing essential: []
- Missing high-value: ['predicted_protein_homology', 'local_read_coverage']
- Unavailable: ['predicted_protein_homology:rpoB', 'local_read_coverage:rpoB', 'reference_neighbor_presence:rpoB', 'expected_neighboring_genes:rpoB']

| prefix | importance | weight | status | result | limitation | weighted_done |
|---|---|---:|---|---|---|---:|
| nucleotide_homology | essential | 4.0 | completed | supports_claim |  | 4.0 |
| translated_homology | essential | 4.0 | completed | weakens_claim |  | 4.0 |
| predicted_protein_homology | high_value | 2.0 | skipped | not_run | predicted proteins were unavailable | 0.0 |
| partial_domain_hits | high_value | 2.0 | completed | weakens_claim |  | 2.0 |
| contig_edge_truncation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| assembly_fragmentation | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| local_read_coverage | high_value | 2.0 | skipped | not_run | read-back depth was unavailable | 0.0 |
| divergent_homologues | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| read_supported_break | high_value | 2.0 | completed | supports_claim |  | 2.0 |
| reference_neighbor_presence | supporting | 1.0 | skipped | not_run | no trusted reference genome was configured; orthologues and gene order were not invented | 0.0 |
| expected_neighboring_genes | supporting | 1.0 | skipped | not_run | no expected neighboring genes were specified | 0.0 |

Confidence path: polarity base 0.55 → status `weakened` → confidence_for 0.5 → after completeness 0.46 (recorded 0.46).

## 10. Confidence ≈ 0.46

For `target_gene_not_detected` with falsification enabled, base confidence is 0.55. Status is `weakened` because translated homology and partial-domain hits weaken non-detection whenever the k=3 amino-acid search returns partials. `confidence_for(weakened)` caps at `max(0.15, min(0.50, base))` = 0.50. `max_not_detected_confidence` does not lower this further. Completeness then multiplies by max(0.78, 1−0.04×n_missing_high_value). With n=2: 0.50 × 0.92 = **0.46**. Completeness 0.63 ≥ 0.50, so the extra low-completeness cap is not applied. Final clamp is [0.05, 0.85].

Drivers, in order:

1. Claim polarity is uniformly `not_detected` (no 80/80 nucleotide or 60/80 protein hit).
2. Status is uniformly `weakened` (translated/partial hits), which imposes a 0.50 cap — a status cap, not a homology-quality score.
3. Missing Bakta proteins and unwired read-depth subtract the same two high-value validators on every case.
4. Falsification ran; the constant is not a 'falsification disabled' path.
5. There is no separate per-genome homology strength in the confidence number once polarity and status are fixed.

## 11. Dummy cautious baseline versus the same scorer

- Strategy: always target_gene_not_detected, weakened, confidence 0.46, completeness 0.63; no homology
- Dummy overall all six cases (scientific metrics): **0.967741935483871**
- Dummy development overall: **0.9375**
- Dummy held-out overall: **1.0**
- Genome Skeptic development overall: **0.9375**
- Genome Skeptic held-out overall: **1.0**
- Dummy development matches Genome Skeptic 0.9375 exactly: **True**
- Held-out 1.000 achievable by dummy (within 0.08): **True**

The dummy is scientifically wrong on dev_01 (`scientifically_correct=False`) but still scores the same as Genome Skeptic because `false_absence` ignores weakened non-detection and `underconfidence_on_clean` only applies when the gene is detected. Calibration error is 6/6 failed for the dummy (confidence 0.46 vs correctness 0 or 1) but **calibration_error is excluded from `SCIENTIFIC_METRICS`**, so it does not affect the published overall.

Dummy metric totals:

| metric | n | correct | rate |
|---|---:|---:|---:|
| correct_detection | 1 | 0 | 0.0 |
| false_detection | 5 | 5 | 1.0 |
| correct_non_detection | 5 | 5 | 1.0 |
| false_absence | 1 | 1 | 1.0 |
| unsupported_overclaiming | 6 | 6 | 1.0 |
| underconfidence_on_clean | 1 | 1 | 1.0 |
| calibration_error | 6 | 0 | 0.0 |
| unsupported_organism_level_claims | 6 | 6 | 1.0 |
| completeness_confidence_consistency | 6 | 6 | 1.0 |

Per-case dummy hits:

- `dev_01` split=development present=True scientifically_correct=False hits={'false_absence': True, 'unsupported_overclaiming': True, 'underconfidence_on_clean': True, 'calibration_error': False, 'unsupported_organism_level_claims': True, 'completeness_confidence_consistency': True}
- `dev_02` split=development present=False scientifically_correct=True hits={'false_detection': True, 'correct_non_detection': True, 'unsupported_overclaiming': True, 'calibration_error': False, 'unsupported_organism_level_claims': True, 'completeness_confidence_consistency': True}
- `dev_03` split=development present=False scientifically_correct=True hits={'false_detection': True, 'correct_non_detection': True, 'unsupported_overclaiming': True, 'calibration_error': False, 'unsupported_organism_level_claims': True, 'completeness_confidence_consistency': True}
- `hel_01` split=held_out present=False scientifically_correct=True hits={'false_detection': True, 'correct_non_detection': True, 'unsupported_overclaiming': True, 'calibration_error': False, 'unsupported_organism_level_claims': True, 'completeness_confidence_consistency': True}
- `hel_02` split=held_out present=False scientifically_correct=True hits={'false_detection': True, 'correct_non_detection': True, 'unsupported_overclaiming': True, 'calibration_error': False, 'unsupported_organism_level_claims': True, 'completeness_confidence_consistency': True}
- `hel_03` split=held_out present=False scientifically_correct=True hits={'false_detection': True, 'correct_non_detection': True, 'unsupported_overclaiming': True, 'calibration_error': False, 'unsupported_organism_level_claims': True, 'completeness_confidence_consistency': True}

`scientifically_correct` requires `target_gene_detected` when hidden present is true and the gene is not fragmented. The dummy therefore fails scientific correctness on dev_01. The scorer's `false_absence` metric nevertheless counts a *weakened* `not_detected` claim as avoiding false absence. Held-out FAST_PILOT truths are all `present: false`, so always saying 'not detected, weakened' scores a perfect scientific overall. If the dummy overall is at or near Genome Skeptic, the held-out 1.000 is not evidence of discriminative biological reasoning.

## 12. Smallest scientifically justified next changes (not applied)

Do not start another SPAdes run. Do not change scoring until these are decided explicitly:

1. Replace or re-define `PUBLIC_RPOB_SEED`. BLASTN/TBLASTN show this 122-nt string is not an authentic MG1655 rpoB window. If the question is exact-allele detection, use a real extracted MG1655 locus and mark only near-identical genomes present. If the question is orthologue-family detection, use a protein or HMM reference and score protein-level presence across species. Do not keep a nucleotide E. coli fragment as a universal bacterial rpoB probe.
2. Align truth assignment with detection: require identity **and** coverage (the 80/80 or 60/80 rule, or a documented equivalent). The current identity≥0.5 / no-coverage rule marked E. coli present on a 52-bp 65% hit.
3. Prefer BLAST+ for nucleotide/protein search when installed (it was available here and agreed with internal search on the miss). Keep k=3 translated search from being the sole reason every real genome is `weakened`.
4. Wire existing `depth.tsv` into `depth_available` so `local_read_coverage` is measured. Do not change completeness weights yet.
5. Count weakened `not_detected` on a clean present gene as a false absence (or as underconfidence). Until that changes, a dummy cautious baseline ties Genome Skeptic on FAST_PILOT.
6. Do not scale the benchmark or rerun SPAdes until the target definition and truth rule match the scientific question.

## Machine-readable measurements

Companion JSON: `benchmarks/FAST_PILOT_TARGET_TRACE.json`. Alignment tables: `benchmarks/fast_pilot_target_diagnostics/`.

