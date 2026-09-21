# M60 PROTOCOL V1.1 — PRE-SELECTION CLARIFICATION

Status: clarification of `M60_PROTOCOL.md` issued **before cohort sampling**.
This file does not replace the original protocol. The original file and its
SHA256 are preserved unchanged.

Original protocol path: `manuscript_benchmark/M60_PROTOCOL.md`
Original protocol SHA256 (frozen, must remain):
`30de5efc92d1b2b0db9de0db6f8f98b965397b6adac17052603b3ab44b74df4f`

This V1.1 document does **not** change:

- biological logic
- thresholds
- prompts
- action routing
- validator behavior
- manuscript arms
- exclusion-manifest contents
- the original protocol text

It records executable interpretation, frozen comparators, and truth-assignment
rules so that sampling cannot be informed by later analysis choices.

Seed: `20260920`
Freeze: `GENOME_SKEPTIC_V4_1_MANUSCRIPT`

---

## PRIMARY TARGETS

- `tetA_tetracycline_efflux`
- `rpoB_RNAP_beta`

Limitation targets `tuf_EF_Tu` and `lacZ_beta_galactosidase` remain excluded
from this primary study.

## PRIMARY COHORT

60 fresh genome-target cases.

| Stratum | n |
|---|---|
| tetA routine | 15 |
| tetA challenge | 15 |
| rpoB routine | 15 |
| rpoB challenge | 15 |
| **TOTAL** | **60** |

Report each target separately as well as pooled.

---

## TARGET-SPECIFIC INTERPRETATION

### tetA_tetracycline_efflux

Tests **exact tet(A)/tet(B) family discrimination**, not generic tetracycline
resistance and not any MFS transporter.

Both POSITIVE and NEGATIVE truth states are biologically meaningful.
Routine and challenge sampling may therefore include genomes that later
adjudicate as either state. Sampling itself does not inspect truth.

Exact endpoint: identity with the frozen tetA family members (UniProt P02980
class B / P02982 class A) versus competing packaged families
`mfs_multidrug_efflux` and `rnd_efflux`.

### rpoB_RNAP_beta

Tests **recovery of the true rpoB orthologue**, particularly under
divergence and assembly difficulty.

Do **not** manufacture negative genomes merely for class balance.
Absence, domain-only hits, rpoC confusion, fusion, and split remain
admissible truth outcomes if they arise naturally in sampled assemblies.
They are not a sampling target.

Exact endpoint: RNA polymerase subunit beta orthologue, not a domain-only
hit and not a different polymerase subunit (`rpoC_RNAP_beta_prime`).

---

## EXTERNAL COMPARATORS (FROZEN BEFORE COHORT SELECTION)

Comparators are not truth. Comparator identity, software/database versions,
and binary-endpoint conversion rules are frozen here. They must not be
changed after seeing results.

### tetA comparators

1. **AMRFinderPlus**
2. **Conventional** (Genome Skeptic `run_conventional`: nucleotide
   identity/coverage homology call without falsification)
3. **GS-Deterministic V4.1**
4. **GS-Agentic V4.1**
5. **GS-Exhaustive V4.1**

### rpoB comparators

1. **NCBI RefSeq/PGAP annotation** on the same genome inputs (frozen
   established orthology/annotation comparator)
2. **Conventional** (same `run_conventional` as tetA)
3. **GS-Deterministic V4.1**
4. **GS-Agentic V4.1**
5. **GS-Exhaustive V4.1**

eggNOG-mapper is **not** a frozen M60 comparator. It is not installed in the
production environment and will not be added after selection.

### AMRFinderPlus (tetA only)

| Field | Frozen value |
|---|---|
| Name | NCBI AMRFinderPlus |
| Software | 4.2.7 (production executable `amrfinder`) |
| Database | the AMRFinderPlus database version recorded in `manuscript_benchmark/M60_ENVIRONMENT.json` before the first comparator execution; that database version is immutable thereafter |
| Input | the same selected assembly nucleotide FASTA used by Genome Skeptic |
| Command class | protein-and-nucleotide AMRFinderPlus search on the assembly; no organism-specific rescue after seeing results |
| Binary tetA endpoint | POSITIVE if any reported gene symbol normalizes to exactly `teta`, `tet(a)`, `tetb`, or `tet(b)` after lowercasing and stripping non-alphanumeric characters except parentheses. Other tet classes (`tet(c)`, `tetA(P)`, `tet(M)`, etc.) are NEGATIVE for this endpoint. |
| Missing/failed run | record as comparator failure, not as truth, and not as NEGATIVE |

AMRFinderPlus **must not** define tetA truth.

If the database is not yet present at preflight, cohort selection may
proceed because AMRFinderPlus is a later comparator, not a sampling input.
The first AMRFinderPlus run on M60 genomes is forbidden until the database
version is written into `M60_ENVIRONMENT.json`.

### Conventional (both targets)

| Field | Frozen value |
|---|---|
| Name | Genome Skeptic Conventional |
| Code path | `genome_skeptic.eval.evaluate_real._run_system(name="conventional")` → `run_conventional` |
| Scientific core | not used; no falsification, no family classifier, no V4.1 follow-up policy |
| Binary endpoint | POSITIVE if the conventional claim for that target is a detected/present homology call; otherwise NEGATIVE. Unresolved conventional output is COMPARATOR_UNRESOLVED, not truth. |

### GS manuscript arms (both targets)

| Arm | Policy | Code |
|---|---|---|
| GS-Deterministic V4.1 | `GS_DETERMINISTIC_V4_1` | `run_gs_deterministic_v4_1` |
| GS-Agentic V4.1 | `GS_AGENTIC_V4_1` | `run_gs_agentic_v4_1` |
| GS-Exhaustive V4.1 | `GS_EXHAUSTIVE_V4_1` | `run_gs_exhaustive_v4_1` |

Shared scientific core hash:
`22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0`

Binary endpoint for each arm: POSITIVE if the frozen validator claim_type is
`target_gene_detected`; NEGATIVE if `target_gene_not_detected`; otherwise
unresolved/failed-closed. Unresolved/failed-closed counts as incorrect in
the primary accuracy denominator when truth is POSITIVE or NEGATIVE
(original protocol §7). These arms are **not** run in Phase 0/1.

### NCBI RefSeq/PGAP annotation (rpoB established comparator)

This is the frozen established annotation/orthology comparator for rpoB.
It can be run reproducibly on the same genome inputs because the annotation
travels with the RefSeq assembly.

| Field | Frozen value |
|---|---|
| Name | NCBI RefSeq PGAP CDS annotation |
| Software | NCBI Datasets / RefSeq annotated assembly distribution (no local PGAP re-run) |
| Database / annotation version | the `*_genomic.gff.gz` (fallback `*_feature_table.txt.gz`) from the same assembly `ftp_path` as the selected GCF accession. The assembly version (GCF_*.version) **is** the annotation version. Later reannotations of the same organism must not be substituted. |
| Input | the selected GCF accession; GFF/feature-table files from that accession's RefSeq FTP directory |
| Conversion to binary rpoB endpoint | apply the rules below, in order |

**rpoB PGAP conversion rules (frozen):**

Let `gene` be the GFF `gene=` attribute or feature-table gene symbol.
Let `product` be the GFF `product=` attribute or feature-table product name.
Compare case-insensitively.

1. Ignore non-CDS features.
2. A CDS is an **rpoB hit** if:
   - `gene` is exactly `rpoB`, OR
   - `product` matches RNA polymerase subunit beta / rpoB naming
     (`rna polymerase` AND `beta` AND NOT `beta prime` AND NOT `beta'` AND
     NOT `rpoC` AND NOT `beta-prime`).
3. A CDS is an **rpoC / other-subunit hit** if `gene` is `rpoC` or the
   product is RNA polymerase beta-prime / rpoC. These do **not** count as
   rpoB POSITIVE.
4. Comparator POSITIVE if ≥1 rpoB hit exists.
5. Comparator NEGATIVE if the annotation file is present and parseable and
   zero rpoB hits exist.
6. Comparator UNCERTAIN if the GFF/feature table is missing, unreadable, or
   has no CDS features.

PGAP/RefSeq annotation is hidden from truth adjudicators.

---

## TRUTH (EXECUTABLE DECISION RULES, FROZEN BEFORE SAMPLING)

Truth is adjudicated independently from all prediction arms and from all
comparators.

Prediction outputs must never be consulted during truth assignment.
If AMRFinderPlus is a comparator, AMRFinderPlus cannot define tetA truth.
PGAP/eggNOG/GS arm outputs cannot define rpoB truth.

Allowed truth states: `POSITIVE`, `NEGATIVE`, `TRUTH_UNCERTAIN`.

### Required fields for every truth record

- `case_id`
- `target`
- `truth_value` (`POSITIVE` / `NEGATIVE` / `TRUTH_UNCERTAIN`)
- `truth_status` (`ADJUDICATED` / `PENDING` / `DISAGREEMENT_UNRESOLVED`)
- `primary_evidence`
- `secondary_corroboration`
- `reference_accession_evidence`
- `curator`
- `adjudication_note`

Truth files are not created in Phase 0/1. These rules exist so sampling
cannot be tuned to a later private labelling scheme.

### Shared frozen gates (not modified)

From frozen `Settings.thresholds` / original protocol:

- identity threshold: `gene_aa_min_identity = 0.60`
- coverage threshold: `gene_aa_min_query_coverage = 0.80`
- length-ratio window: `gene_length_ratio_min = 0.80`, `gene_length_ratio_max = 1.20`
- family competitive margin: `family_competitive_margin = 0.10`
- family competitive ambiguous band: `family_competitive_ambiguous_band = 0.05`
- HMM gate coverage: `hmm_min_gate_model_coverage = 0.20`
- HMM domain-only max coverage: `hmm_domain_only_max_model_coverage = 0.45`
- sequence-decisive identity product used by the frozen competitive-family
  classifier: identity×coverage ≥ 0.70 with competing-family delta ≥ 0.20

Evidence generators permitted for later truth work: frozen family member
FASTA, frozen competing-family FASTA, independent BLASTP/HMMER/DIAMOND
against those packaged sequences, and the frozen functions in
`genome_skeptic.validators.competitive_family` /
`genome_skeptic.validators.family_orthology` used as **measurement
instruments**, not as manuscript-arm claim JSON.

Forbidden during truth assignment: any `claims.json` from GS-Deterministic /
GS-Agentic / GS-Exhaustive / Conventional; any AMRFinderPlus output; any
PGAP comparator table built for the study; D8/D12/D20 labels.

### tetA truth rule (executable)

For assembly `A` and target `tetA_tetracycline_efflux`:

1. Translate candidate loci by independent search against frozen tetA
   members P02980 and P02982. If no candidate protein is recovered,
   `truth_value = NEGATIVE`.
   `primary_evidence = "no_tetA_family_candidate_locus"`.
2. Score the best candidate against frozen tetA members and competing
   families `mfs_multidrug_efflux` and `rnd_efflux` using the frozen
   competitive-family classifier.
3. Let `cls` be that classification and `margin` the frozen score_margin.
4. Decision:
   - `POSITIVE` if `cls == target_family_supported` **and** the candidate
     is sequence-decisive for tet(A)/tet(B) versus competing efflux
     families under the frozen family-identity gate (identity×coverage
     ≥ 0.70 versus tetA members with delta ≥ 0.20 versus the best
     competitor, **or** `margin >= 0.10` and not inside the 0.05
     ambiguous band).
   - `NEGATIVE` if `cls == competing_family_preferred`, **or** the best
     competitor identity product is ≥ 0.70 with delta ≥ 0.20 versus tetA,
     **or** step 1 found no locus.
   - `TRUTH_UNCERTAIN` if `cls == ambiguous_family`, **or** `cls` is
     `domain_only` / `unresolved_candidate` with residual hits, **or**
     `|identity - 0.60| <= 0.10` or `|coverage - 0.80| <= 0.15` and no
     sequence-decisive margin exists, **or** two blinded curators disagree
     and the evidence rules do not resolve it.
5. Secondary corroboration may include independent accession-linked
   literature or RefSeq protein records for the **same locus**, recorded
   by the curator. It may not include comparator or GS predictions.
6. `reference_accession_evidence` records the frozen member protein IDs
   and any independent accession used. Never AMRFinderPlus.

### rpoB truth rule (executable)

For assembly `A` and target `rpoB_RNAP_beta`:

1. Search independently against frozen rpoB family members. Do not invent
   negatives to balance classes.
2. `POSITIVE` if a locus is a full-length rpoB orthologue:
   - relevant identity ≥ 0.60 and query coverage ≥ 0.80 versus a frozen
     rpoB member, **and**
   - length ratio in [0.80, 1.20] versus the matched member, **and**
   - architecture is not `domain_only`, **and**
   - the frozen partner-family comparison does not prefer
     `rpoC_RNAP_beta_prime` as the identity of that locus.
3. `NEGATIVE` if:
   - no candidate locus exists, **or**
   - the best explanation is a different polymerase subunit (rpoC or
     documented non-beta RNAP subunit), **or**
   - the only hit is a domain fragment (`domain_only` / coverage below
     the orthologue coverage gate without a resolvable split).
4. `TRUTH_UNCERTAIN` if fusion with rpoC, biological split, or assembly
   fragmentation cannot be resolved from the predefined evidence, **or**
   identity/coverage sit inside the frozen near-threshold bands without a
   decisive architecture, **or** curators disagree.
5. Domain architecture consistent with RNAP beta (documented Pfam set in
   frozen `rpoB_RNAP_beta/family.yaml`) is secondary corroboration, not a
   licence to override sequence-decisive identity when the two conflict
   unresolvedly — that conflict is `TRUTH_UNCERTAIN`.
6. PGAP gene symbols are hidden from adjudicators and are not primary
   evidence.

### Curator protocol

Where feasible use two blinded adjudicators. Disagreement that cannot be
resolved by the rules above is `TRUTH_UNCERTAIN` with
`truth_status = DISAGREEMENT_UNRESOLVED`.

---

## SAMPLING CLARIFICATIONS (METADATA / PRESCREEN ONLY)

Original protocol §2 is unchanged. The following makes the algorithm
executable without peeking at truth.

### Eligible pool

- Source: current RefSeq bacterial `assembly_summary.txt`.
- Apply `M60_EXCLUSION_MANIFEST.json` **first**.
- Keep GCF latest Full assemblies at Complete Genome, Chromosome,
  Scaffold, or Contig level, not excluded from RefSeq, with a named genus.
- Freshness cutoff: `seq_rel_date >= 2025-01-01` (same freshness rule as
  the prior external-cohort design; this is a metadata filter, not a
  biological-threshold change).
- No gene-content, annotation, AMRFinderPlus, orthology, Genome Skeptic,
  or truth lookup while building the pool.

### Routine stratum (15 tetA + 15 rpoB)

Metadata only.

- 8 Complete Genome/Chromosome + 7 Scaffold/Contig per target.
- Unique assembly accession across the whole M60 cohort.
- Unique species and unique genus within the 30-case routine set, then
  preferred unique versus later challenge.
- Rank key: `SHA256("M60_ROUTINE|20260920|<target>|<assembly_accession>")`
  ascending, accession as final tie-break.
- Do not inspect target annotations, AMRFinder, orthology, Genome Skeptic
  measurements, predictions, or truth.

### Challenge stratum (15 tetA + 15 rpoB)

Separate candidate pool, disjoint accessions from routine.

- Candidate-pool size frozen now: 12 Complete Genome/Chromosome + 12
  Scaffold/Contig per target (24 candidates/target; 48 total).
- Candidate-pool rank:
  `SHA256("M60_CHALLENGE_POOL|20260920|<target>|<assembly_accession>")`.
- Prefer genera unused by routine.
- Download nucleotide FASTA only for this candidate pool. Sanitize headers
  to opaque `contig_N` labels. Do not download GFF/GBFF/proteins for
  selection. Do not open annotations.
- Run **only** the frozen V4.1 deterministic instruments required for the
  pre-registered ambiguity score (`run_gs_deterministic_v4_1` / shared
  `collect_assembly_target_measurements` + deterministic follow-ups +
  frozen validator). This prescreen is a **selection device**, not a
  manuscript-arm result, not Conventional, not AMRFinderPlus, and not
  truth.
- Score with unmodified `scripts/lock_cohort_d20_final.py:score_case`
  (import the function; do not read D20 results or labels).
- Select top 15 per target by higher ambiguity, then
  `SHA256("M60|20260920|<target>|<assembly_accession>")` ascending.
- After ranking, fill 8 complete + 7 draft per target when those quality
  buckets exist in the ranked list; otherwise continue down the ranked
  list. Unique genus is required. Do not select because Agentic is
  expected to fix a case.
- Execution order after lock:
  `SHA256("M60_EXECUTION|20260920|<target>|<assembly_accession>")`.

### Diversity

Prefer taxonomic diversity. One genus may not contribute more than one
M60 case. Prefer unused families/orders/phyla when filling.

### Overlap checks required at lock

- no exclusion-manifest overlap
- no D8 overlap
- no D12 overlap
- no D20 candidate-pool overlap
- no reference-source overlap
- no duplicate accession unless explicitly preregistered (none are)
- 60 total, 30 tetA, 30 rpoB, 30 routine, 30 challenge

---

## PHASE 0/1 STOP RULE

Do not run Conventional, AMRFinderPlus, the rpoB PGAP comparator,
GS-Deterministic, GS-Agentic, or GS-Exhaustive as manuscript study arms.
Do not open truth.

Challenge-stratum deterministic prescreen on the **candidate pool only**
is permitted solely to compute the pre-registered ambiguity score.

M60 CASES SELECTED: recorded in the cohort manifest after Phase G.
D20 TOUCHED: NO
TRUTH OPENED: NO
PREDICTIONS RUN: NO
