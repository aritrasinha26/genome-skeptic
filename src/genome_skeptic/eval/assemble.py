"""Eval-only de Bruijn assembler used when SPAdes is unavailable.

This is not part of Genome Skeptic's measurement stack. It exists so the
three-system comparison can run on miniature complete-genome analogues in CI.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path


def _iter_fastq(path: Path):
    with path.open() as fh:
        while True:
            header = fh.readline()
            if not header:
                break
            seq = fh.readline().strip()
            fh.readline()
            fh.readline()
            if seq:
                yield seq.upper()


def assemble_reads(r1: Path, r2: Path | None, out_fa: Path, k: int = 21, min_contig: int = 120) -> Path:
    counts: dict[str, int] = defaultdict(int)
    files = [r1] + ([r2] if r2 and r2.exists() else [])
    for fq in files:
        for seq in _iter_fastq(fq):
            seq = "".join(c if c in "ACGT" else "" for c in seq)
            if len(seq) < k:
                continue
            for i in range(len(seq) - k + 1):
                counts[seq[i:i + k]] += 1
    if not counts:
        out_fa.parent.mkdir(parents=True, exist_ok=True)
        out_fa.write_text(">empty\nN\n")
        return out_fa
    peak = max(counts.values())
    thresh = 2 if peak >= 6 else 1
    kmers = {kmer for kmer, n in counts.items() if n >= thresh}
    prefixes: dict[str, list[str]] = defaultdict(list)
    for kmer in kmers:
        prefixes[kmer[:-1]].append(kmer[-1])
    used = set()
    contigs = []

    def extend(start: str) -> str:
        path = start
        used.add(start)
        while True:
            pref = path[-(k - 1):]
            nxt = [b for b in prefixes.get(pref, []) if (pref + b) in kmers and (pref + b) not in used]
            if len(nxt) != 1:
                break
            kmer = pref + nxt[0]
            used.add(kmer)
            path += nxt[0]
        while True:
            suf = path[: k - 1]
            prev = [kmer[0] for kmer in kmers if kmer[1:] == suf and kmer not in used]
            if len(prev) != 1:
                break
            kmer = prev[0] + suf
            used.add(kmer)
            path = prev[0] + path
        return path

    for kmer in sorted(kmers, key=lambda x: -counts[x]):
        if kmer in used:
            continue
        lefts = [p for p, outs in prefixes.items() if kmer[0] in outs and p + kmer[0] == kmer]
        # start at weakly incoming nodes
        contig = extend(kmer)
        if len(contig) >= min_contig:
            contigs.append(contig)
    if not contigs:
        contigs = [max(kmers, key=len)]
    out_fa.parent.mkdir(parents=True, exist_ok=True)
    out_fa.write_text("".join(f">c{i}\n{seq}\n" for i, seq in enumerate(contigs, start=1)))
    return out_fa
