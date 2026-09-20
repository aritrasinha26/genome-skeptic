from genome_skeptic.config import Settings
from genome_skeptic.locus.phylo import place_query
from genome_skeptic.tools.taxonomy import parse_kraken2_output


def test_kraken2_parser_does_not_invent(tmp_path):
    tsv = tmp_path / "k.tsv"
    tsv.write_text("C\tc1\tEscherichia coli\t100\nU\tc2\tunclassified\t100\n")
    parsed = parse_kraken2_output(tsv)
    assert parsed["c1"]["taxonomy"] == "Escherichia coli"
    assert parsed["c2"]["taxonomy"] is None


def test_placement_among_labeled_homologues():
    settings = Settings()
    query = "MRSRSRSRSRSRSRSRSRSRSRSRSRSRSRSRS"
    ortho = query
    para = "MLGLGLGLGLGLGLGLGLGLGLGLGLGLGLGLG"
    rec = place_query(
        "rpoB",
        query,
        [
            {"id": "rpoB_ref", "sequence": ortho, "clade": "ortholog"},
            {"id": "rpoB2", "sequence": para, "clade": "paralog"},
        ],
        settings,
    )
    assert rec["status"] == "completed"
    assert rec["clade"] in {"ortholog", "paralog", "unresolved"}
    assert rec["provenance"]["created_by"] == "deterministic_phylogenetic_placement"


def test_placement_skips_without_homologues():
    rec = place_query("rpoB", "MRS", [], Settings())
    assert rec["status"] == "not_run"
    assert rec["clade"] is None
