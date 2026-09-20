"""Modest, diverse RefSeq complete genomes for isolated evaluation.

Held-out accessions are scorer-side only. The analysis agent never receives
this catalog unless a genome is explicitly configured as a permitted reference.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenomeSpec:
    genome_id: str
    accession: str
    species: str
    assembly_level: str
    split: str
    source: str
    url: str
    approx_mb: float
    gc: float
    notes: str
    plasmids: bool = False
    repeats: bool = False
    extra_accessions: tuple[str, ...] = ()


def _efetch(acc: str) -> str:
    return (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=nuccore&id={acc}&rettype=fasta&retmode=text"
    )


# Eight complete RefSeq genomes: two Pseudomonas, Gram-negative and Gram-positive,
# size/GC spread, one plasmid-containing isolate. Not chosen to flatter Genome Skeptic.
GENOMES: tuple[GenomeSpec, ...] = (
    GenomeSpec("ecoli_k12", "NC_000913.3", "Escherichia coli str. K-12 substr. MG1655", "complete", "development", "NCBI RefSeq", _efetch("NC_000913.3"), 4.64, 50.8, "model enterobacterium"),
    GenomeSpec("pao1", "NC_002516.2", "Pseudomonas aeruginosa PAO1", "complete", "development", "NCBI RefSeq", _efetch("NC_002516.2"), 6.26, 66.6, "high GC Pseudomonas; current use-case organism"),
    GenomeSpec("hpylori", "NC_000915.1", "Helicobacter pylori 26695", "complete", "development", "NCBI RefSeq", _efetch("NC_000915.1"), 1.67, 38.9, "small AT-rich Gram-negative"),
    GenomeSpec("bsubtilis", "NC_000964.3", "Bacillus subtilis subsp. subtilis str. 168", "complete", "development", "NCBI RefSeq", _efetch("NC_000964.3"), 4.22, 43.5, "Gram-positive model"),
    GenomeSpec("pputida_kt2440", "NC_002947.4", "Pseudomonas putida KT2440", "complete", "held_out", "NCBI RefSeq", _efetch("NC_002947.4"), 6.18, 61.5, "second Pseudomonas, held-out"),
    GenomeSpec("staph_8325", "NC_007795.1", "Staphylococcus aureus subsp. aureus NCTC 8325", "complete", "held_out", "NCBI RefSeq", _efetch("NC_007795.1"), 2.82, 32.9, "low-GC Gram-positive"),
    GenomeSpec(
        "salmonella_lt2", "NC_003197.2",
        "Salmonella enterica subsp. enterica serovar Typhimurium str. LT2",
        "complete", "held_out", "NCBI RefSeq", _efetch("NC_003197.2"), 4.86, 52.2,
        "enterobacterium with virulence plasmid pSLT",
        plasmids=True, extra_accessions=("NC_003277.2",),
    ),
    GenomeSpec("vcholerae_chr1", "NC_002505.1", "Vibrio cholerae O1 biovar El Tor str. N16961 chromosome I", "complete", "held_out", "NCBI RefSeq", _efetch("NC_002505.1"), 2.96, 47.7, "multipartite genome chromosome I"),
)


def genomes_for(split: str, *, profile: str | None = None) -> list[GenomeSpec]:
    rows = [g for g in GENOMES if g.split == split]
    if (profile or "").strip().lower() != "fast_pilot":
        return rows
    wanted = FAST_PILOT_GENOME_IDS.get(split) or ()
    by_id = {g.genome_id: g for g in rows}
    missing = [gid for gid in wanted if gid not in by_id]
    if missing:
        raise KeyError(f"FAST_PILOT genomes missing from catalog for split {split}: {missing}")
    return [by_id[gid] for gid in wanted]


# FAST_PILOT uses three development and three held-out genomes. Not the full catalog.
# Pseudomonas, Enterobacterales, and a smaller bacterium in each split.
FAST_PILOT_GENOME_IDS: dict[str, tuple[str, ...]] = {
    "development": ("ecoli_k12", "pao1", "hpylori"),
    "held_out": ("salmonella_lt2", "pputida_kt2440", "staph_8325"),
}


# Public 122-nt seed used by FAST_PILOT v1. Not an authentic MG1655 rpoB sequence.
# Semantics v2 replaces it with the annotated NC_000913.3 rpoB CDS/protein.
# Kept only so historical diagnostics and unit-test fixtures remain importable.
PUBLIC_RPOB_SEED = (
    "GTGCAGATCCCGCGTGAAGGTCTGATCGCGCGTACCGGTGAAACCGTAGCTGAAGCTCTGA"
    "AAGGTCTGCGTGAACTGCCGGGTATCAACCTGCCGGAAGGTGTTGAAGTTGAAACCGAAGT"
)
ABSENT_TARGET = (
    "ATGAAATTTGGTTGGTTCGGTTGGAAAGGTTGGAAACCGTGGAAAGGTATGCCGTGGTTC"
    "GGTAAAGGTTGGTTCAAAGGTTAA"
)
