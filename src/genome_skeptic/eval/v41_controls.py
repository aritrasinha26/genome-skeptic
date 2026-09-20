"""V4.1 architecture controls. Does not rewrite V3/V4 control reports."""
from __future__ import annotations

from pathlib import Path
import shutil

from genome_skeptic.eval.orthology_controls import _write_control, reverse_translate, ROOT
from genome_skeptic.eval.annotation import ALLELE_SOURCE_GENOME, load_all_rpob
from genome_skeptic.families import load_family


def write_v41_controls(root: Path | None = None) -> Path:
    root = root or ROOT
    out = root / "benchmarks" / "v4_1" / "controls"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    loci = load_all_rpob(root)
    mg = loci[ALLELE_SOURCE_GENOME]
    allele = mg["nucleotide"]
    protein = mg["protein"]
    family = load_family("rpoB_RNAP_beta")
    thermo = next((m.sequence for m in family.members if m.protein_id == "WP_004081508.1"), protein)
    filler = "A" * 900
    ortho_h = f"rpoB target_type=gene_orthologue family=rpoB_RNAP_beta length_aa={len(protein)}"
    ortho = ("rpoB", ortho_h, protein)

    mutated = list(allele)
    for i in range(0, len(mutated), 9):
        mutated[i] = {"A": "C", "C": "G", "G": "T", "T": "A"}.get(mutated[i], "A")
    para = "".join(mutated)
    _write_control(out, "ctrl_para_true", {"chr": filler + allele + filler, "c2": filler + para + filler}, [ortho], {
        "rpoB": {"present": True, "clean": False, "paralogue": True, "uncertainty_required": True,
                 "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "true_duplicated_paralogue_second_copy_diverged"}},
    })
    _write_control(out, "ctrl_para_recent", {"chr": filler + allele + filler, "c2": filler + allele + filler}, [ortho], {
        "rpoB": {"present": True, "clean": False, "paralogue": True, "uncertainty_required": True,
                 "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "recent_gene_duplication_near_identical_copies"}},
    })
    half = (len(allele) // 6) * 3
    _write_control(out, "ctrl_para_fragments", {"c1": filler + allele[:half], "c2": allele[half:] + filler}, [ortho], {
        "rpoB": {"present": True, "clean": False, "fragmented": True, "uncertainty_required": True,
                 "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "two_assembly_fragments_of_one_gene_not_paralogue"}},
    })
    plasmid = "C" * 200 + allele + "C" * 200
    _write_control(out, "ctrl_para_plasmid", {"chr": "A" * 80_000 + allele + "A" * 1000, "plasmid": plasmid}, [ortho], {
        "rpoB": {"present": True, "clean": False, "paralogue": True, "uncertainty_required": True,
                 "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "second_copy_on_short_contig_plasmid_like"}},
    })
    balanced = ("ACGT" * 1500)[:6000]
    at_flank = "A" * 6000
    _write_control(out, "ctrl_para_contaminant", {"chr": balanced + allele + balanced, "foreign": at_flank + allele + at_flank}, [ortho], {
        "rpoB": {"present": True, "clean": False, "paralogue": True, "contaminant": True, "uncertainty_required": True,
                 "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "second_copy_gc_outlier_contaminant_like"}},
    })
    _write_control(out, "ctrl_divergent_family", {"c1": filler + reverse_translate(thermo) + filler}, [ortho], {
        "rpoB": {"present": True, "clean": False, "uncertainty_required": True, "target_type": "gene_orthologue",
                 "truth_state": "resolved",
                 "provenance": {"rule": "public_divergent_family_member_vs_query_distribution", "protein_id": "WP_004081508.1"}},
    })
    _write_control(out, "ctrl_canonical_query_like", {"c1": filler + allele + filler}, [ortho], {
        "rpoB": {"present": True, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "query_identical_full_length"}},
    })
    return out
