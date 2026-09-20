"""Deterministic synthetic bacterial loci used by unit tests and benchmark cases.

Sequences are miniature operon analogues, not downloaded genomes. Measurements
still come from FASTA/GFF parsing and homology search.
"""
from __future__ import annotations

from pathlib import Path

from genome_skeptic.tools.gene_search import translate_frame


def _gene(repeat: str, n: int) -> str:
    return "ATG" + (repeat * n) + "TAA"


# Codon pairs are chosen so rpoB's RS repeat does not appear in other genes
# in any frame or on the reverse strand.
DNAA = _gene("TTCAAA", 18)
RPOB = _gene("CGTAGC", 20)
RPOC = _gene("GACCCT", 18)
RPLK = _gene("ATCGAG", 16)
GYRA = _gene("TGGGCA", 22)
SPACER = "N" * 30
PAD = "N" * 400


def translate(seq: str) -> str:
    return translate_frame(seq.upper(), 0).split("*")[0]


def _fa(records: dict[str, str]) -> str:
    return "".join(f">{name}\n{seq}\n" for name, seq in records.items())


def _gff(seqid: str, genes: list[tuple[str, int, int, str]]) -> str:
    lines = ["##gff-version 3"]
    for gid, start0, end0, strand in genes:
        start, end = start0 + 1, end0
        lines.append(f"{seqid}\tsynthetic\tCDS\t{start}\t{end}\t.\t{strand}\t0\tID={gid};product={gid}")
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _operon(order: list[tuple[str, str]], spacer: str = SPACER) -> tuple[str, list[tuple[str, int, int, str]]]:
    parts: list[str] = []
    genes: list[tuple[str, int, int, str]] = []
    pos = 0
    for i, (gid, seq) in enumerate(order):
        if i:
            parts.append(spacer)
            pos += len(spacer)
        parts.append(seq)
        genes.append((gid, pos, pos + len(seq), "+"))
        pos += len(seq)
    seq = PAD + "".join(parts) + PAD
    genes = [(gid, start + len(PAD), end + len(PAD), strand) for gid, start, end, strand in genes]
    return seq, genes


def _proteins(names: dict[str, str]) -> dict[str, str]:
    return {name: translate(seq) for name, seq in names.items()}


def _case_yaml(case_id: str) -> str:
    return (
        f"id: {case_id}\n"
        "assembly: assembly.fa\n"
        "targets: targets.fa\n"
        "gff: assembly.gff\n"
        "proteins: assembly.faa\n"
        "references: references.yaml\n"
    )


def _references_yaml(taxonomy: str = "Escherichia coli") -> str:
    return (
        "references:\n"
        "  - id: trusted_reference\n"
        "    fasta: ref.fa\n"
        "    gff: ref.gff\n"
        "    proteins: ref.faa\n"
        f"    taxonomy: {taxonomy}\n"
    )


def _write_reference(base: Path, taxonomy: str = "Escherichia coli") -> None:
    seq, genes = _operon([("dnaA", DNAA), ("rpoB", RPOB), ("rpoC", RPOC)])
    _write(base / "ref.fa", _fa({"ref": seq}))
    _write(base / "ref.gff", _gff("ref", genes))
    _write(base / "ref.faa", _fa(_proteins({"dnaA": DNAA, "rpoB": RPOB, "rpoC": RPOC})))
    _write(base / "references.yaml", _references_yaml(taxonomy))


def _write_query(base: Path, seq: str, genes: list[tuple[str, int, int, str]], seqid: str = "c1", extra_fa: dict[str, str] | None = None, extra_gff: str = "", extra_faa: dict[str, str] | None = None) -> None:
    records = {seqid: seq}
    if extra_fa:
        records.update(extra_fa)
    _write(base / "assembly.fa", _fa(records))
    gff = _gff(seqid, genes) + extra_gff
    _write(base / "assembly.gff", gff)
    prots = _proteins({gid: seq[start:end] if strand == "+" else seq[start:end] for gid, start, end, strand in genes})
    if extra_faa:
        prots.update(extra_faa)
    _write(base / "assembly.faa", _fa(prots))
    _write(base / "targets.fa", f">rpoB neighbors=dnaA,rpoC taxonomy=Escherichia\n{RPOB}\n")
    _write(base / "case.yaml", _case_yaml(base.name))


def write_benchmark_tree(root: Path) -> None:
    cases = root / "cases"
    hidden = root / "hidden"

    syntenic = cases / "syntenic_ortholog"
    seq, genes = _operon([("dnaA", DNAA), ("rpoB", RPOB), ("rpoC", RPOC)])
    _write_query(syntenic, seq, genes)
    _write_reference(syntenic)

    para = cases / "paralogue_copy"
    seq, genes = _operon([("dnaA", DNAA), ("rpoB", RPOB), ("rpoC", RPOC)])
    extra = {"copy2": "C" * 400 + RPOB + "G" * 400}
    extra_gff = _gff("copy2", [("rpoB_para", 400, 400 + len(RPOB), "+")])
    _write_query(para, seq, genes, extra_fa=extra, extra_gff=extra_gff, extra_faa={"rpoB_para": translate(RPOB)})
    _write_reference(para)

    scrambled = cases / "scrambled_synteny"
    seq, genes = _operon([("rpoC", RPOC), ("rpoB", RPOB), ("dnaA", DNAA)])
    _write_query(scrambled, seq, genes)
    _write_reference(scrambled)

    edge = cases / "contig_edge"
    seq = RPOB[:48] + SPACER + RPOC
    genes = [("rpoB", 0, 48, "+"), ("rpoC", 48 + len(SPACER), len(seq), "+")]
    _write_query(edge, seq, genes)
    _write_reference(edge)

    frag = cases / "fragmentation"
    left, right = RPOB[:72], RPOB[72:]
    extra = {"c2": right + "C" * 40}
    seq = DNAA + SPACER + left
    genes = [("dnaA", 0, len(DNAA), "+"), ("rpoB_left", len(DNAA) + len(SPACER), len(seq), "+")]
    extra_gff = _gff("c2", [("rpoB_right", 0, len(right), "+")])
    _write_query(frag, seq, genes, extra_fa=extra, extra_gff=extra_gff, extra_faa={"rpoB_right": translate(right + "TAA")})
    _write_reference(frag)

    contaminant = cases / "contaminant_locus"
    seq, genes = _operon([("dnaA", DNAA), ("rpoB", RPOB), ("rpoC", RPOC)])
    _write_query(contaminant, seq, genes)
    _write_reference(contaminant, taxonomy="Bacillus cereus")

    absence = cases / "clean_absence"
    seq, genes = _operon([("dnaA", DNAA), ("rpoC", RPOC)])
    _write_query(absence, seq, genes)
    _write_reference(absence)

    realistic = cases / "realistic_rpo_operon"
    seq, genes = _operon([("dnaA", DNAA), ("gyrA", GYRA), ("rpoB", RPOB), ("rpoC", RPOC), ("rplK", RPLK)])
    _write_query(realistic, seq, genes)
    ref_seq, ref_genes = _operon([("dnaA", DNAA), ("gyrA", GYRA), ("rpoB", RPOB), ("rpoC", RPOC), ("rplK", RPLK)])
    _write(realistic / "ref.fa", _fa({"ref": ref_seq}))
    _write(realistic / "ref.gff", _gff("ref", ref_genes))
    _write(realistic / "ref.faa", _fa(_proteins({"dnaA": DNAA, "gyrA": GYRA, "rpoB": RPOB, "rpoC": RPOC, "rplK": RPLK})))
    _write(realistic / "references.yaml", _references_yaml("Escherichia coli"))

    _write(
        hidden / "truth.yaml",
        """# Scorer-only ground truth. Never pass this file to analyze_targets_on_assembly or the orchestrator.
cases:
  syntenic_ortholog:
    targets:
      rpoB:
        present: true
        paralogue: false
        contaminant: false
        fragmented: false
        uncertainty_required: false
        overclaim_forbidden: true
  paralogue_copy:
    targets:
      rpoB:
        present: true
        paralogue: true
        contaminant: false
        fragmented: false
        uncertainty_required: true
        overclaim_forbidden: true
  scrambled_synteny:
    targets:
      rpoB:
        present: true
        paralogue: false
        contaminant: false
        fragmented: false
        uncertainty_required: true
        overclaim_forbidden: true
  contig_edge:
    targets:
      rpoB:
        present: true
        paralogue: false
        contaminant: false
        fragmented: true
        uncertainty_required: true
        overclaim_forbidden: true
  fragmentation:
    targets:
      rpoB:
        present: true
        paralogue: false
        contaminant: false
        fragmented: true
        uncertainty_required: true
        overclaim_forbidden: true
  contaminant_locus:
    targets:
      rpoB:
        present: true
        paralogue: false
        contaminant: true
        fragmented: false
        uncertainty_required: true
        overclaim_forbidden: true
  clean_absence:
    targets:
      rpoB:
        present: false
        paralogue: false
        contaminant: false
        fragmented: false
        uncertainty_required: false
        overclaim_forbidden: true
  realistic_rpo_operon:
    targets:
      rpoB:
        present: true
        paralogue: false
        contaminant: false
        fragmented: false
        uncertainty_required: false
        overclaim_forbidden: true
""",
    )


if __name__ == "__main__":
    write_benchmark_tree(Path("benchmarks"))
