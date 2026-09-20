from pathlib import Path

from genome_skeptic.io_utils import detect_sequence_format, fasta_stats, sample_fastq_stats


def test_fastq_stats(tmp_path: Path):
    p = tmp_path / "x.fastq"
    p.write_text("@r1\nACGTN\n+\nIIIII\n@r2\nACGTA\n+\nIIIII\n")
    assert detect_sequence_format(p) == "fastq"
    s = sample_fastq_stats(p)
    assert s["sampled_reads"] == 2
    assert s["mean_read_length"] == 5
    assert s["n_fraction"] == 0.1


def test_fasta_stats(tmp_path: Path):
    p = tmp_path / "x.fa"
    p.write_text(">a\nAAAA\n>b\nGGGGGG\n")
    s = fasta_stats(p)
    assert s["contigs"] == 2
    assert s["total_bp"] == 10
    assert s["largest_contig_bp"] == 6
    assert s["n50_bp"] == 6


def test_wrapped_fasta_is_joined(tmp_path: Path):
    from genome_skeptic.io_utils import read_fasta
    p = tmp_path / "wrap.fa"
    p.write_text(">a desc\nAA\nAA\n>b\nGGGGGG\n")
    records = read_fasta(p)
    assert records == [("a", "AAAA"), ("b", "GGGGGG")]
