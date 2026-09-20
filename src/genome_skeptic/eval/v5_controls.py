"""V5 competitive-family and multiplicity controls. Does not rewrite V3/V4/V4.1 reports."""
from __future__ import annotations

from pathlib import Path
import shutil

from genome_skeptic.eval.orthology_controls import _write_control, reverse_translate, ROOT
from genome_skeptic.families import load_family


def write_v5_controls(root: Path | None = None) -> Path:
    root = root or ROOT
    out = root / "benchmarks" / "v5" / "controls"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    tet = load_family("tetA_tetracycline_efflux")
    mfs = load_family("mfs_multidrug_efflux")
    rnd = load_family("rnd_efflux")
    tuf = load_family("tuf_EF_Tu")
    reca = load_family("recA_recombinase")
    filler = "A" * 900
    if not tet or not tet.members:
        return out
    tet_aa = max(tet.members, key=lambda m: len(m.sequence or "")).sequence
    tet_nt = reverse_translate(tet_aa)
    tet_q = ("tetA", f"tetA target_type=gene_orthologue family=tetA_tetracycline_efflux length_aa={len(tet_aa)}", tet_aa)
    mfs_aa = (mfs.members[0].sequence if mfs and mfs.members else tet_aa[:200])
    rnd_aa = (rnd.members[0].sequence if rnd and rnd.members else tet_aa[:180])
    domain = tet_aa[40:90]
    _write_control(out, "ctrl_comp_true_target", {"c1": filler + tet_nt + filler}, [tet_q], {
        "tetA": {"present": True, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "genuine_target_family_present"}},
    })
    _write_control(out, "ctrl_comp_related_transporter", {"c1": filler + reverse_translate(mfs_aa) + filler}, [tet_q], {
        "tetA": {"present": False, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "closely_related_transporter_family_not_tetA"}},
    })
    _write_control(out, "ctrl_comp_shared_domain", {"c1": filler + reverse_translate(domain) + filler}, [tet_q], {
        "tetA": {"present": False, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "shared_domain_only"}},
    })
    _write_control(out, "ctrl_comp_broad_membrane", {"c1": filler + reverse_translate(rnd_aa) + filler}, [tet_q], {
        "tetA": {"present": False, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "broad_membrane_protein_not_tetA"}},
    })
    divergent = list(tet_aa)
    for i in range(0, len(divergent), 6):
        table = {"A": "V", "V": "I", "I": "L", "L": "M", "M": "K", "K": "R", "R": "H", "H": "Q", "Q": "N", "N": "D", "D": "E", "E": "S", "S": "T", "T": "A"}
        divergent[i] = table.get(divergent[i], divergent[i])
    _write_control(out, "ctrl_comp_divergent_genuine", {"c1": filler + reverse_translate("".join(divergent)) + filler}, [tet_q], {
        "tetA": {"present": True, "clean": False, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "divergent_genuine_target_must_not_be_lost"}},
    })
    mutated = list(tet_nt)
    for i in range(0, len(mutated), 9):
        mutated[i] = {"A": "C", "C": "G", "G": "T", "T": "A"}.get(mutated[i], "A")
    _write_control(out, "ctrl_comp_paralogous_member", {"chr": filler + tet_nt + filler, "c2": filler + "".join(mutated) + filler}, [tet_q], {
        "tetA": {"present": True, "clean": False, "paralogue": True, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "paralogous_family_member"}},
    })
    if tuf and tuf.members:
        tuf_aa = tuf.members[0].sequence
        tuf_nt = reverse_translate(tuf_aa)
        tuf_q = ("tuf", f"tuf target_type=gene_orthologue family=tuf_EF_Tu length_aa={len(tuf_aa)}", tuf_aa)
        _write_control(out, "ctrl_multi_near_identical", {"chr": filler + tuf_nt + filler + "C" * 400 + filler + tuf_nt + filler}, [tuf_q], {
            "tuf": {"present": True, "clean": False, "paralogue": True, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                    "provenance": {"rule": "two_near_identical_loci_must_not_collapse"}},
        })
    if reca and reca.members:
        rec_aa = reca.members[0].sequence
        rec_q = ("recA", f"recA target_type=gene_orthologue family=recA_recombinase length_aa={len(rec_aa)}", rec_aa)
        _write_control(out, "ctrl_multi_single", {"c1": filler + reverse_translate(rec_aa) + filler}, [rec_q], {
            "recA": {"present": True, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                     "provenance": {"rule": "single_copy_housekeeping"}},
        })
    return out
