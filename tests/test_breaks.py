from genome_skeptic.tools.breaks import analyze_locus_breaks, parse_alignment_records


def test_break_analysis_requires_mapping_records():
    rec = analyze_locus_breaks([], contig_id="c1", start=0, end=50, contig_length=80)
    assert rec["status"] == "not_run"
    assert rec["read_supported_break"] is None
    assert "not invented" in rec["limitation"]


def test_clipped_reads_support_a_break(tmp_path):
    sam = tmp_path / "edge.sam"
    # 1-based POS=1 at contig start, left soft-clip 12, mate unmapped (flag 8+1+2=11)
    lines = []
    for i in range(10):
        lines.append(f"r{i}\t11\tc1\t1\t60\t12S60M\t*\t0\t0\tACGT\tIIII")
    sam.write_text("\n".join(lines) + "\n")
    records = parse_alignment_records(sam)
    rec = analyze_locus_breaks(records, contig_id="c1", start=0, end=70, contig_length=80)
    assert rec["status"] == "completed"
    assert rec["read_supported_break"] is True
    assert rec["n_clipped"] >= 1


def test_interior_locus_is_not_a_break():
    records = [{"flag": 2, "rname": "c1", "pos": 400, "cigar": "100M", "rnext": "="}]
    rec = analyze_locus_breaks(records, contig_id="c1", start=350, end=500, contig_length=2000)
    assert rec["read_supported_break"] is False
