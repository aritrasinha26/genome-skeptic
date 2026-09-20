"""Paired-end Illumina-like simulation with recorded parameters.

Prefers wgsim, ART, or InSilicoSeq when installed. Falls back to a
documented internal simulator so tests do not require those binaries.
"""
from __future__ import annotations

import gzip
import random
from pathlib import Path

from genome_skeptic.io_utils import read_fasta
from genome_skeptic.tools.base import available, run_command


ADAPTER = "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA"


def _open_fq(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz" or path.name.endswith(".fastq.gz"):
        return gzip.open(path, "wt")
    return path.open("w")


def _phred(q: int) -> str:
    return chr(33 + max(0, min(40, q)))


def simulate_paired_internal(
    fasta: Path,
    r1: Path,
    r2: Path,
    *,
    coverage: float,
    read_len: int,
    insert: int,
    error_rate: float,
    seed: int,
    quality: int = 35,
    adapter_rate: float = 0.0,
    coverage_profile: str = "uniform",
    drop_windows: list[tuple[str, int, int]] | None = None,
    end_quality_drop: bool = False,
) -> dict:
    rng = random.Random(seed)
    records = read_fasta(fasta)
    n_written = 0
    with _open_fq(r1) as f1, _open_fq(r2) as f2:
        for chrom, seq in records:
            seq = seq.upper()
            if "N" in seq:
                seq = "".join(b if b in "ACGT" else rng.choice("ACGT") for b in seq)
            if len(seq) < insert + 1:
                continue
            mean_cov = coverage
            n_frags = max(1, int(len(seq) * mean_cov / (2 * read_len)))
            for i in range(n_frags):
                if coverage_profile == "uneven":
                    pos = int((rng.random() ** 2) * max(1, len(seq) - insert))
                else:
                    pos = rng.randrange(0, max(1, len(seq) - insert))
                if drop_windows:
                    skip = False
                    for cid, a, b in drop_windows:
                        if cid == chrom and a <= pos < b:
                            skip = rng.random() < 0.92
                    if skip:
                        continue
                frag = seq[pos:pos + insert]
                if len(frag) < read_len * 2:
                    continue
                left = list(frag[:read_len])
                right = list(frag[-read_len:])
                right = list(reversed([{"A": "T", "T": "A", "C": "G", "G": "C"}.get(b, "A") for b in right]))
                for bases in (left, right):
                    for j, b in enumerate(bases):
                        if rng.random() < error_rate:
                            bases[j] = rng.choice([x for x in "ACGT" if x != b])
                if adapter_rate and rng.random() < adapter_rate:
                    clip = rng.randint(8, min(20, read_len // 3))
                    left = list(ADAPTER[:clip]) + left[clip:]
                    q_left = _phred(8) * clip + _phred(quality) * (read_len - clip)
                else:
                    if end_quality_drop:
                        q_left = "".join(_phred(max(8, quality - int(20 * j / read_len))) for j in range(read_len))
                    else:
                        q_left = _phred(quality) * read_len
                if end_quality_drop:
                    q_right = "".join(_phred(max(8, quality - int(20 * j / read_len))) for j in range(read_len))
                else:
                    q_right = _phred(quality) * read_len
                if adapter_rate and rng.random() < adapter_rate / 2:
                    q_right = _phred(10) * read_len
                name = f"{chrom}_{i}_{pos}"
                f1.write(f"@{name}/1\n{''.join(left)}\n+\n{q_left}\n")
                f2.write(f"@{name}/2\n{''.join(right)}\n+\n{q_right}\n")
                n_written += 1
    return {
        "simulator": "internal_illumina_pe",
        "coverage": coverage,
        "read_len": read_len,
        "insert": insert,
        "error_rate": error_rate,
        "seed": seed,
        "quality": quality,
        "adapter_rate": adapter_rate,
        "coverage_profile": coverage_profile,
        "n_fragments": n_written,
        "drop_windows": drop_windows or [],
        "end_quality_drop": end_quality_drop,
    }


def simulate_paired_reads(
    fasta: Path,
    out_dir: Path,
    *,
    coverage: float = 20.0,
    read_len: int = 100,
    insert: int = 250,
    error_rate: float = 0.01,
    seed: int = 7,
    quality: int = 35,
    adapter_rate: float = 0.0,
    coverage_profile: str = "uniform",
    drop_windows: list[tuple[str, int, int]] | None = None,
    end_quality_drop: bool = False,
    require_production_simulator: bool = False,
) -> tuple[Path, Path, dict]:
    """Use wgsim when practical; otherwise the internal simulator.

    Production real-genome cases must set require_production_simulator=True so a
    missing/failed wgsim is reported instead of silently using the internal toy.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    r1 = out_dir / "reads_R1.fastq"
    r2 = out_dir / "reads_R2.fastq"
    params = {
        "coverage": coverage,
        "read_len": read_len,
        "insert": insert,
        "error_rate": error_rate,
        "seed": seed,
        "quality": quality,
        "adapter_rate": adapter_rate,
        "coverage_profile": coverage_profile,
        "drop_windows": drop_windows or [],
        "end_quality_drop": end_quality_drop,
    }
    can_wgsim = (
        adapter_rate == 0 and coverage_profile == "uniform"
        and not drop_windows and not end_quality_drop
    )
    if require_production_simulator:
        if not available("wgsim"):
            raise RuntimeError(
                "wgsim is required for production real-genome simulation; "
                "the internal Illumina simulator was not used."
            )
        if not can_wgsim:
            raise RuntimeError(
                "production real-genome simulation requested parameters that wgsim cannot express; "
                "the internal simulator was not substituted."
            )
    if available("wgsim") and can_wgsim:
        total = sum(len(s) for _, s in read_fasta(fasta))
        n_pairs = max(100, int(total * coverage / (2 * read_len)))
        cmd = [
            "wgsim", "-e", str(error_rate), "-d", str(insert), "-1", str(read_len),
            "-2", str(read_len), "-N", str(n_pairs), "-S", str(seed),
            str(fasta), str(r1), str(r2),
        ]
        result = run_command("wgsim", "simulate", cmd, out_dir)
        if result.ok and r1.exists() and r1.stat().st_size > 0:
            params["simulator"] = "wgsim"
            params["command"] = cmd
            params["n_fragments"] = n_pairs
            return r1, r2, params
        if require_production_simulator:
            raise RuntimeError(f"wgsim failed; internal simulator was not used: {result.error}")
    params.update(simulate_paired_internal(
        fasta, r1, r2, coverage=coverage, read_len=read_len, insert=insert,
        error_rate=error_rate, seed=seed, quality=quality, adapter_rate=adapter_rate,
        coverage_profile=coverage_profile, drop_windows=drop_windows,
        end_quality_drop=end_quality_drop,
    ))
    return r1, r2, params
