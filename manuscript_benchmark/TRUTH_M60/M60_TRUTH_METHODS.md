# M60 independent truth methods

This document describes how M60 ground truth was constructed.

It does **not** report system accuracy.

## Independence

Truth was assigned after all M60 predictions were locked.

Prediction payloads were not opened.

AMRFinderPlus was not used as tetA truth.

NCBI RefSeq/PGAP annotation was not used as rpoB truth.

Genome Skeptic Deterministic, Agentic, Exhaustive, and Conventional outputs were not used as truth.

D20 was not accessed.

D8/D12 outcome labels were not used.

M60 assemblies were used only as query genomes. They were not added to the reference panel.

## Two independent evidence routes

This is **not** two independent human reviewers. One automated adjudication
pipeline applied two distinct evidence routes, then a separate automated
second pass over the same evidence records.

### tetA

Endpoint: presence of a genuine tet(A)/tet(B) family member.

Route 1: sequence comparison of recovered candidate ORFs against a frozen
tet(A)/tet(B) panel (UniProt P02982 / P02980 and packaged family members)
versus competing MFS/RND/non-target tet-class references.

Route 2: HMMER profile placement on frozen tetA versus competitor family
HMMs, with FastTree placement for borderline cases when hmmalign succeeded.

A generic MFS transporter match is not sufficient.

### rpoB

Endpoint: presence of a genuine bacterial rpoB orthologue.

Route 1: full/near-full-length similarity and length-ratio support versus
independently verified RpoB references.

Route 2: RpoB versus RpoC profile placement, with phylogenetic placement
when borderline.

PGAP gene-name equality was not used.

Negative rpoB labels were not manufactured for class balance.

Uncertainty was not forced into NEGATIVE.

## Decision gates

Frozen protocol gates from M60_PROTOCOL_V1_1.md:

- identity 0.60, coverage 0.80, length ratio 0.80–1.20
- competitive margin 0.10 / ambiguous band 0.05
- HMM gate coverage 0.20 / domain-only max 0.45
- sequence-decisive identity×coverage ≥ 0.70 with competitor delta ≥ 0.20

## Human review

Cases remaining TRUTH_UNCERTAIN, discordant, or otherwise unresolved are
listed in `M60_HUMAN_REVIEW_REQUIRED.csv` and are marked for human
adjudication. Automated review is not a second human curator.
