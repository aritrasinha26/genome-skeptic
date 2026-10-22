"""Validation of user-supplied nucleotide assemblies for live analysis.

Original FASTA headers are discarded and replaced with opaque ``contig_N``
identifiers before anything reaches the pipeline, mirroring
``scripts/select_and_download_d20.py:sanitize_fasta``. This keeps free text in
headers (product names, organism labels, or instructions) away from any
language-model planner.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_RECORDS = 5000
MIN_TOTAL_BP = 500
MAX_TOTAL_BP = 15_000_000
ALLOWED_EXTENSIONS = (".fa", ".fasta", ".fna", ".fas", ".txt")

_NUCLEOTIDE = set("ACGTUNRYKMSWBDHV")
_CORE = set("ACGTUN")
_PROTEIN_ONLY = set("EFILPQ")
_WS = re.compile(r"\s+")


@dataclass
class FastaValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    n_records: int = 0
    total_bp: int = 0
    max_contig_bp: int = 0
    gc_fraction: float | None = None
    n_fraction: float | None = None
    sha256_sanitized: str | None = None
    sanitized_fasta: str = ""


def check_filename(name: str | None) -> str | None:
    if not name:
        return None
    if not name.lower().endswith(ALLOWED_EXTENSIONS):
        return f"Unsupported file type. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}."
    return None


def decode_upload(data: bytes) -> tuple[str | None, str | None]:
    if len(data) > MAX_UPLOAD_BYTES:
        return None, f"File is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit for the public demo."
    if data[:2] == b"\x1f\x8b":
        return None, "Compressed (gzip) files are not accepted. Upload plain-text FASTA."
    if b"\x00" in data[:4096]:
        return None, "File looks binary, not plain-text FASTA."
    try:
        return data.decode("ascii"), None
    except UnicodeDecodeError:
        return None, "FASTA must be plain ASCII text."


def validate_assembly_fasta(text: str) -> FastaValidation:
    """Validate a nucleotide (DNA) assembly. Protein FASTA is rejected."""
    res = FastaValidation(ok=False)
    if not text or not text.strip():
        res.errors.append("No sequence was provided.")
        return res
    if len(text.encode("ascii", "ignore")) > MAX_UPLOAD_BYTES:
        res.errors.append("Input exceeds the size limit for the public demo.")
        return res
    if not text.lstrip().startswith(">"):
        res.errors.append("FASTA must start with a '>' header line.")
        return res

    seqs: list[str] = []
    current: list[str] | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if current is not None:
                seqs.append("".join(current))
            current = []
            if len(seqs) + 1 > MAX_RECORDS:
                res.errors.append(f"More than {MAX_RECORDS} records; the public demo accepts small assemblies only.")
                return res
            continue
        if line.startswith(";"):
            continue
        body = _WS.sub("", line).upper()
        bad = set(body) - _NUCLEOTIDE
        if bad:
            if bad & _PROTEIN_ONLY:
                res.errors.append(
                    f"Line {lineno} contains amino-acid letters ({''.join(sorted(bad))[:10]}). "
                    "Live analysis expects a nucleotide genome assembly, not a protein sequence."
                )
            else:
                res.errors.append(f"Line {lineno} contains characters that are not IUPAC nucleotides: "
                                  f"{''.join(sorted(bad))[:10]!r}.")
            return res
        assert current is not None
        current.append(body.replace("U", "T"))
    if current is not None:
        seqs.append("".join(current))

    empty = sum(1 for s in seqs if not s)
    if empty:
        res.errors.append(f"{empty} record(s) have a header but no sequence.")
        return res
    total = sum(len(s) for s in seqs)
    if total < MIN_TOTAL_BP:
        res.errors.append(f"Total sequence length {total} bp is below the {MIN_TOTAL_BP} bp minimum.")
        return res
    if total > MAX_TOTAL_BP:
        res.errors.append(f"Total sequence length {total:,} bp exceeds the {MAX_TOTAL_BP:,} bp public-demo limit.")
        return res

    joined = "".join(seqs)
    core = sum(1 for ch in joined if ch in _CORE)
    if core / total < 0.9:
        res.errors.append("Less than 90% of positions are A/C/G/T/N; this does not look like a nucleotide assembly.")
        return res
    n_count = joined.count("N")
    gc = (joined.count("G") + joined.count("C")) / max(1, total - n_count)
    res.n_fraction = round(n_count / total, 4)
    res.gc_fraction = round(gc, 4)
    if res.n_fraction > 0.2:
        res.warnings.append(f"{res.n_fraction:.0%} of positions are N.")
    if len(seqs) > 500:
        res.warnings.append(f"{len(seqs)} contigs: a highly fragmented assembly increases contig-edge effects.")

    lines: list[str] = []
    for i, s in enumerate(seqs, start=1):
        lines.append(f">contig_{i}")
        lines.extend(s[j : j + 80] for j in range(0, len(s), 80))
    sanitized = "\n".join(lines) + "\n"
    res.sanitized_fasta = sanitized
    res.sha256_sanitized = hashlib.sha256(sanitized.encode("ascii")).hexdigest()
    res.n_records = len(seqs)
    res.total_bp = total
    res.max_contig_bp = max(len(s) for s in seqs)
    res.ok = True
    return res
