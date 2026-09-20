from __future__ import annotations

import gzip
from pathlib import Path
from typing import Iterator, TextIO


def open_text(path: str | Path) -> TextIO:
    p = Path(path)
    if p.suffix == ".gz":
        return gzip.open(p, "rt")
    return p.open("rt")


def detect_sequence_format(path: str | Path) -> str:
    with open_text(path) as fh:
        first = fh.readline().strip()
    if first.startswith("@"):
        return "fastq"
    if first.startswith(">"):
        return "fasta"
    raise ValueError(f"Cannot detect FASTA/FASTQ format for {path}")


def iter_fastq(path: str | Path) -> Iterator[tuple[str, str, str]]:
    with open_text(path) as fh:
        while True:
            header = fh.readline()
            if not header:
                break
            seq = fh.readline().rstrip("\n")
            plus = fh.readline()
            qual = fh.readline().rstrip("\n")
            if not seq or not plus or not qual:
                raise ValueError(f"Truncated FASTQ record in {path}")
            if not header.startswith("@") or not plus.startswith("+"):
                raise ValueError(f"Malformed FASTQ record in {path}")
            if len(seq) != len(qual):
                raise ValueError(f"Sequence/quality length mismatch in {path}")
            yield header[1:].strip(), seq, qual


def sample_fastq_stats(path: str | Path, max_reads: int = 100_000) -> dict:
    reads = 0
    bases = 0
    ns = 0
    min_len = None
    max_len = 0
    for _, seq, _ in iter_fastq(path):
        reads += 1
        n = len(seq)
        bases += n
        ns += seq.upper().count("N")
        min_len = n if min_len is None else min(min_len, n)
        max_len = max(max_len, n)
        if reads >= max_reads:
            break
    if reads == 0:
        raise ValueError(f"No reads found in {path}")
    return {
        "sampled_reads": reads,
        "sampled_bases": bases,
        "mean_read_length": bases / reads,
        "min_read_length": min_len,
        "max_read_length": max_len,
        "n_fraction": ns / bases if bases else 0.0,
    }


def iter_fasta_records(path: str | Path) -> Iterator[tuple[str, str, str]]:
    header: str | None = None
    parts: list[str] = []
    with open_text(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    seq_id = header.split()[0]
                    yield seq_id, header, "".join(parts)
                header = line[1:]
                parts = []
            else:
                parts.append(line)
        if header is not None:
            seq_id = header.split()[0]
            yield seq_id, header, "".join(parts)


def iter_fasta(path: str | Path) -> Iterator[tuple[str, str]]:
    for seq_id, _header, seq in iter_fasta_records(path):
        yield seq_id, seq


def read_fasta(path: str | Path) -> list[tuple[str, str]]:
    records = list(iter_fasta(path))
    if not records:
        raise ValueError(f"No FASTA sequences found in {path}")
    return records


def fasta_stats(path: str | Path) -> dict:
    lengths: list[int] = []
    gc = 0
    bases = 0
    for _, seq in read_fasta(path):
        s = seq.upper()
        n = len(s)
        lengths.append(n)
        bases += n
        gc += s.count("G") + s.count("C")
    lengths.sort(reverse=True)
    half = sum(lengths) / 2
    acc = 0
    n50 = 0
    for n in lengths:
        acc += n
        if acc >= half:
            n50 = n
            break
    return {
        "contigs": len(lengths),
        "total_bp": sum(lengths),
        "largest_contig_bp": max(lengths),
        "n50_bp": n50,
        "gc_fraction": gc / bases if bases else 0.0,
    }
