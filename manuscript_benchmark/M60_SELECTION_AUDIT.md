# M60 SELECTION AUDIT

Created: 2026-09-20T03:07:15.711023+00:00
Freeze: GENOME_SKEPTIC_V4_1_MANUSCRIPT
Seed: 20260920

## Counts

- tetA routine: 15
- tetA challenge: 15
- rpoB routine: 15
- rpoB challenge: 15
- unique accessions: 60
- unique genera: 60

## Sampling algorithm

- Exclusion manifest applied first.
- Eligible pool: current RefSeq bacteria, GCF latest Full, named genus, seq_rel_date >= 2025-01-01.
- Routine: metadata only. Hash SHA256("M60_ROUTINE|20260920|<target>|<acc>"). 8 complete + 7 draft/target. Unique genus.
- Challenge candidate pool: SHA256("M60_CHALLENGE_POOL|20260920|<target>|<acc>"). 12 complete + 12 draft/target.
- Challenge score: frozen V4.1 deterministic instruments + unmodified score_case. No D20 results opened.
- Challenge lock: higher ambiguity, then SHA256("M60|20260920|<target>|<acc>"). Unique genus. Not selected because Agentic is expected to fix them.

## Integrity

- exclusion overlap: 0
- D8 overlap: 0
- D12 overlap: 0
- D20 overlap: 0
- D20 touched: NO
- truth opened: NO
- predictions run (manuscript arms / comparators): NO
- challenge prescreen failures skipped: 0

## Diversity (phylum)

- Pseudomonadota: 33
- Bacillota: 10
- Actinomycetota: 9
- unknown: 2
- Bacteroidota: 2
- Spirochaetota: 1
- Mycoplasmatota: 1
- Fusobacteriota: 1
- Campylobacterota: 1

## Diversity (family, top 20)

- Enterobacteriaceae: 6
- Rhizobiaceae: 5
- Staphylococcaceae: 2
- unknown: 2
- Lactobacillaceae: 2
- Moraxellaceae: 2
- Pasteurellaceae: 2
- Listeriaceae: 1
- Anaplasmataceae: 1
- Pseudomonadaceae: 1
- Legionellaceae: 1
- Erwiniaceae: 1
- Bifidobacteriaceae: 1
- Thalassospiraceae: 1
- Borreliaceae: 1
- Nitrobacteraceae: 1
- Aeromonadaceae: 1
- Clostridiaceae: 1
- Streptococcaceae: 1
- Mycobacteriaceae: 1

## Eligible pool

- n_eligible: 104291
- eligible pool SHA256: 3d1f95e3c8613a5c7848758d02433518b319b9096103fbfde1a9fcfcd3600d02

STOP. Do not run Conventional, AMRFinderPlus, PGAP comparator, or manuscript GS arms yet.
