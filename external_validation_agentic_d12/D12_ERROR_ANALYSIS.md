# D12 error analysis

Cases where **both** deterministic V5 and Agentic V3 are wrong on the frozen external endpoint.
No code, thresholds, or predictions were changed. This is diagnosis only.

Shared pattern: Agentic V3 never flipped a V5 scored endpoint (12/12 identical). Dual errors are therefore V5 decision-path errors that adaptive actions did not correct.

## Position 1: `GCF_060416925.1` / `tetA_tetracycline_efflux`

- Class: **VALIDATOR_DECISION_LIMIT**
- Truth: **NEGATIVE** (no AMRFinder/PGAP tet(A) or tet(B))
- Locked V5 endpoint: `DETECTED` (divergent_full_length, conf=0.4316)
- Locked Agentic endpoint: `DETECTED` (same call)
- Additional actions Agentic executed: `search_target_domains_hmmer`
- New evidence produced: **yes** (HMMER status INFORMATIVE)
- Why that new evidence still failed to reach the truth: Frozen FAMILY truth is complete tet(A) or tet(B) only. V5 already treated remote homology / family-profile support as presence. Extra HMMER hits measure more remote homologs; they do not implement AMRFinder class identity, so they cannot convert a non-tet(A)/tet(B) transporter into a FAMILY negative.

## Position 3: `GCF_053795755.1` / `tetA_tetracycline_efflux`

- Class: **VALIDATOR_DECISION_LIMIT**
- Truth: **NEGATIVE**
- Locked V5 endpoint: `DETECTED`
- Locked Agentic endpoint: `DETECTED`
- Additional actions Agentic executed: `search_target_domains_hmmer`
- New evidence produced: **yes** (HMMER INFORMATIVE)
- Why that new evidence still failed to reach the truth: Same as position 1. Adaptive domain search added measurements but left the homology-as-FAMILY-positive decision unchanged.

## Position 6: `GCF_059683705.1` / `tuf_EF_Tu`

- Class: **VALIDATOR_DECISION_LIMIT**
- Truth: **1** distinct genuine EF-Tu locus
- Locked V5 endpoint: `MULTIPLICITY=0` (20 search hits, 0 candidate loci, claim not_detected)
- Locked Agentic endpoint: `MULTIPLICITY=0` (lock omitted multiplicity; inferred from not_detected)
- Additional actions Agentic executed: `search_target_domains_hmmer`, `inspect_hit_contig_contamination`
- New evidence produced: **partial** — HMMER `NO_NEW_INFORMATION`; contamination GC `INFORMATIVE`
- Why that new evidence still failed to reach the truth: Independent phmmer of authentic tufA mapped one complete EF-Tu locus. V5 already had many hits but reconstruction counted zero genuine loci and emitted absence. Planner HMMER did not change that state. Critic contamination inspection does not count distinct EF-Tu genomic intervals.

## Position 7: `GCF_048585425.2` / `lacZ_beta_galactosidase`

- Class: **MISSING_SCIENTIFIC_INSTRUMENT**
- Truth: **NEGATIVE** (no genuine LacZ orthologue under frozen seed completeness; NCBI Gene Orthologs does not reliably index this taxid)
- Locked V5 endpoint: `DETECTED`
- Locked Agentic endpoint: `DETECTED`
- Additional actions Agentic executed: `search_target_domains_hmmer`
- New evidence produced: **yes** (HMMER INFORMATIVE)
- Why that new evidence still failed to reach the truth: No frozen deterministic instrument currently distinguishes true LacZ orthology from competing beta-galactosidase families when reference/GFF/orthology resources are absent. Independent truth did not count generic beta-galactosidase homology as lacZ. Extra HMMER domain hits cannot supply that missing orthology/competitor test.

## Position 9: `GCF_052955985.1` / `tuf_EF_Tu`

- Class: **VALIDATOR_DECISION_LIMIT**
- Truth: **2** distinct genuine EF-Tu loci
- Locked V5 endpoint: `MULTIPLICITY=0` (20 search hits, 0 candidate loci)
- Locked Agentic endpoint: `MULTIPLICITY=0`
- Additional actions Agentic executed: `search_target_domains_hmmer`, `inspect_hit_contig_contamination`
- New evidence produced: **partial** — HMMER `NO_NEW_INFORMATION`; contamination `INFORMATIVE`
- Why that new evidence still failed to reach the truth: Independent mapping found two complete EF-Tu loci. V5 hits were not converted into counted loci. HMMER added no new copy-number information. Contamination GC does not recover multiplicity.

## Position 11: `GCF_054055795.1` / `tetA_tetracycline_efflux`

- Class: **VALIDATOR_DECISION_LIMIT**
- Truth: **NEGATIVE**
- Locked V5 endpoint: `DETECTED` (close_paralogue, 4 candidate loci, conf=0.3774)
- Locked Agentic endpoint: `DETECTED` (conf=0.4091)
- Additional actions Agentic executed: `search_target_domains_hmmer`, `inspect_hit_contig_contamination`
- New evidence produced: **yes** (both INFORMATIVE)
- Why that new evidence still failed to reach the truth: Same FAMILY-contract mismatch as positions 1 and 3. HMMER and contig-GC contamination tests are not tet(A)/tet(B) class calls. Confidence moved slightly; the scored FAMILY endpoint did not.

## Classification summary

| Pos | Target | Class |
|---:|---|---|
| 1 | tetA | VALIDATOR_DECISION_LIMIT |
| 3 | tetA | VALIDATOR_DECISION_LIMIT |
| 6 | tuf | VALIDATOR_DECISION_LIMIT |
| 7 | lacZ | MISSING_SCIENTIFIC_INSTRUMENT |
| 9 | tuf | VALIDATOR_DECISION_LIMIT |
| 11 | tetA | VALIDATOR_DECISION_LIMIT |

No dual-error case was classified as ACTION_SELECTION_FAILURE, INSUFFICIENT_SIGNAL, or OTHER.
Agentic actions ran and often produced measurements; they were the wrong kind of evidence for the frozen scored endpoints, and they did not override the V5 validator decision.
