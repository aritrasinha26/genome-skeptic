from genome_skeptic.coords import (
    COORDINATE_CONVENTION,
    gff_to_internal,
    internal_to_gff,
    intervals_overlap,
    sam_pos_to_internal,
)
from genome_skeptic.tools.gene_search import parse_gff_features


def test_gff_round_trip():
    assert COORDINATE_CONVENTION == "0-based-half-open"
    assert gff_to_internal(1, 114) == (0, 114)
    assert internal_to_gff(0, 114) == (1, 114)
    assert gff_to_internal(145, 270) == (144, 270)
    assert internal_to_gff(144, 270) == (145, 270)


def test_gff_parser_stores_internal_coordinates(tmp_path):
    gff = tmp_path / "x.gff"
    gff.write_text("c1\tsrc\tCDS\t145\t270\t.\t+\t0\tID=rpoB;product=rpoB\n")
    feats = parse_gff_features(gff)
    assert feats[0]["start"] == 144
    assert feats[0]["end"] == 270
    assert feats[0]["gff_start"] == 145
    assert feats[0]["gff_end"] == 270
    assert feats[0]["coord_system"] == "0-based-half-open"
    assert intervals_overlap(144, 270, 144, 270)
    assert not intervals_overlap(0, 144, 144, 270)


def test_sam_pos_conversion():
    assert sam_pos_to_internal(1) == 0
    assert sam_pos_to_internal(145) == 144
