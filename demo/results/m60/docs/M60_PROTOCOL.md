# M60 PROTOCOL — PRIMARY MANUSCRIPT STUDY

Frozen before case selection. Seed: `20260920`.
Do not modify analysis definitions after truth is opened.
Do not select M60 genomes in this freeze step.

These readiness decisions were made before selection of the manuscript
validation cohort.

## 1. Primary cohort

60 completely fresh genome-target cases.

| Stratum | n |
|---|---|
| tetA routine | 15 |
| tetA challenge | 15 |
| rpoB routine | 15 |
| rpoB challenge | 15 |
| **TOTAL** | **60** |

Primary targets only: `tetA_tetracycline_efflux` and `rpoB_RNAP_beta`.
Limitation targets `tuf_EF_Tu` and `lacZ_beta_galactosidase` are excluded
from this primary study.

## 2. Selection rules (not executed at freeze)

### ROUTINE (15 per target)

Sample prospectively from eligible fresh RefSeq genomes using metadata
only.

Do not inspect target truth or system predictions for routine selection.

Eligible metadata fields may include: assembly accession, organism,
genus, species, taxid, assembly level, release date, RefSeq category,
and geographic/host metadata if present. Gene-content, annotation
products, AMRFinderPlus calls, Genome Skeptic predictions, and hidden
truth are forbidden for routine selection.

### CHALLENGE (15 per target)

Select prospectively using frozen solver-derived ambiguity criteria only.
Do not use external truth.

Frozen ambiguity rules (copied from the locked D12 protocol; thresholds
are not modified):

| points | rule |
|---|---|
| 2 | candidate hit exists but no hit satisfies the frozen strong-hit gate |
| 2 | best relevant identity within ±0.10 of frozen orthologue identity threshold |
| 2 | best relevant query coverage within ±0.15 of frozen coverage threshold |
| 2 | architecture in close_paralogue/divergent_full_length/domain_only/fusion/biological_split/assembly_fragmented |
| 2 | candidate vs family/orthology disagreement or competing-family interpretation |
| 1 | more than one candidate locus or multiplicity/copy-number ambiguous |
| 1 | relevant hit near contig edge or possible_edge_truncation |
| +1 per missing/incomplete falsification category, max +2 | incomplete attack-plan coverage |
| 1 | V5/V4.1 solver claim class weakened or unresolved |

Identity threshold: 0.6. Coverage threshold: 0.8.

Tie-break after higher ambiguity:
`SHA256("M60|20260920|<target>|<assembly_accession>")` ascending.

Execution order:
`SHA256("M60_EXECUTION|20260920|<target>|<assembly_accession>")` ascending.

Solver-derived scores may use only the frozen V4.1 deterministic
instruments on the candidate assembly. They are a selection device, not
truth, and not a comparator output used as a label.

## 3. Exclusion

Every accession in `manuscript_benchmark/M60_EXCLUSION_MANIFEST.json` is
ineligible. That manifest is SHA256-hashed before case selection.

Excluded sources:

- controlled capability tests
- D8
- D12 (selected cases and D12 candidate pool)
- entire D20 candidate pool (accession list only; D20 results/truth not opened)
- previous external/development cohorts
- reference/source genomes used by Genome Skeptic
- sequences used to construct family/competitor reference assets

## 4. Manuscript arms (shared scientific core)

All three arms share:

- same initial measurement code (`collect_assembly_target_measurements`)
- same reference assets
- same family definitions
- same TargetMeasurements schema
- same validator (`build_target_gene_claim`)
- same biological thresholds
- same registered deterministic actions
- same endpoint contracts

The only intended difference is FOLLOW-UP TEST POLICY.

| Arm | Policy |
|---|---|
| GS_DETERMINISTIC_V4_1 | predefined fixed-path: one primary registered instrument per open m0 diagnostic need, ordered by DECISION_NEED_RANK / NEED_PRIMARY_ACTIONS. No LLM. |
| GS_AGENTIC_V4_1 | Planner/Critic select eligible follow-up tests from the ranked V4.1 candidate set. |
| GS_EXHAUSTIVE_V4_1 | execute every eligible registered follow-up analysis before validation. No LLM. |

## 5. Comparators

Comparators are not truth.

### tetA

- Conventional baseline (Genome Skeptic `run_conventional`: nucleotide identity/coverage homology call without falsification)
- AMRFinderPlus
- GS-Deterministic V4.1
- GS-Agentic V4.1
- GS-Exhaustive V4.1

### rpoB

- Conventional baseline (same `run_conventional`)
- Established orthology/annotation comparator: NCBI PGAP/RefSeq CDS product and gene-symbol assignment for rpoB on the published assembly annotation. Optional frozen eggNOG-mapper run may be recorded as a second annotation comparator. Neither defines truth.
- GS-Deterministic V4.1
- GS-Agentic V4.1
- GS-Exhaustive V4.1

Exact software/database versions MUST be recorded in the environment
manifest before cohort execution. Freeze-time versions are captured in
the manuscript freeze manifest; if a comparator is installed later, its
version is recorded before first M60 prediction and is not changed
afterward.

AMRFinderPlus must NOT define truth because it is a comparator.

## 6. Truth protocol

Truth MUST be independent of prediction arms.

Possible states: `POSITIVE`, `NEGATIVE`, `TRUTH_UNCERTAIN`.

No prediction may be consulted to resolve uncertain truth.

Where feasible use two blinded adjudicators. Disagreement that cannot be
resolved by the predefined evidence rules is `TRUTH_UNCERTAIN`.

### tetA truth

Independent family adjudication for the exact tet(A)/tet(B) endpoint
using curated references/competitors and predefined evidence rules.

Predefined evidence (in order):

1. Sequence-decisive identity × coverage against the frozen tetA family
   members and competing MFS/RND families.
2. Independent curated competitor references packaged with Genome Skeptic.
3. Exact-endpoint rule: POSITIVE only if the candidate is sequence-decisive
   for tet(A)/tet(B) versus competing efflux families under the frozen
   family-identity gate. NEGATIVE if a competing family is preferred or no
   family-supported locus exists. TRUTH_UNCERTAIN if the margin is inside
   the frozen ambiguous band or evidence is incomplete.

AMRFinderPlus output is hidden from adjudicators.

### rpoB truth

Independent orthology adjudication using predefined curated/reference
evidence.

Predefined evidence (in order):

1. Reciprocal or sequence-decisive match to the frozen rpoB family members.
2. Domain architecture consistent with RNAP beta (documented Pfam set).
3. POSITIVE if the locus is a full-length rpoB orthologue under those
   rules. NEGATIVE if the best explanation is a different polymerase
   subunit, a domain fragment, or absence. TRUTH_UNCERTAIN if fusion/split
   or divergence cannot be resolved from the predefined evidence.

PGAP/eggNOG comparator outputs are hidden from adjudicators.

## 7. Pre-registered primary analysis

PRIMARY QUESTION:

Does GS-Agentic V4.1 improve exact endpoint correctness relative to
GS-Deterministic V4.1?

Exact endpoint correctness: prediction matches independent truth
POSITIVE/NEGATIVE. `TRUTH_UNCERTAIN` cases are excluded from the primary
accuracy denominator and reported separately. Unresolved/failed-closed
predictions count as incorrect when truth is POSITIVE or NEGATIVE.

Primary outputs:

- Agent correct / N
- Deterministic correct / N
- absolute accuracy difference
- Wilson 95% CI
- paired bootstrap CI, 10,000 resamples
- exact McNemar test
- Deterministic wrong -> Agent correct
- Deterministic correct -> Agent wrong
- net corrections

Seed for bootstrap resampling: `20260920`.

SECONDARY:

Does GS-Agentic approach GS-Exhaustive accuracy with fewer analyses?

Record for every arm and case:

- deterministic actions per case
- LLM calls
- wall-clock runtime
- peak memory
- completion rate
- routine vs challenge performance
- per-target performance

Do not modify analysis definitions after truth is opened.

## 8. Endpoints

tetA exact endpoint: tet(A)/tet(B) family identity, not generic tetracycline
resistance or any MFS transporter.

rpoB exact endpoint: RNA polymerase beta orthologue, not a domain-only hit
or a different polymerase subunit.

## 9. Stop rule

This protocol is frozen before M60 case selection.
M60 CASES SELECTED: NO
D20 TOUCHED: NO
