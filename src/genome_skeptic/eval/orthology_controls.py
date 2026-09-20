"""Synthetic architecture controls for family-aware orthology.

No species-name special cases. Sequences are built from the curated public
family members and the agent-visible MG1655 query, not from hidden genomes
as extra references.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from genome_skeptic.eval.annotation import ALLELE_SOURCE_GENOME, load_all_rpob
from genome_skeptic.families import load_family
from genome_skeptic.io_utils import read_fasta

ROOT = Path(__file__).resolve().parents[3]

_CODON = {
    "A": "GCT", "C": "TGT", "D": "GAT", "E": "GAA", "F": "TTT",
    "G": "GGT", "H": "CAT", "I": "ATT", "K": "AAA", "L": "TTA",
    "M": "ATG", "N": "AAT", "P": "CCT", "Q": "CAA", "R": "CGT",
    "S": "TCT", "T": "ACT", "V": "GTT", "W": "TGG", "Y": "TAT",
}


def reverse_translate(aa: str) -> str:
    return "".join(_CODON.get(c, "GCT") for c in aa.upper() if c.isalpha())


def _fasta(records: list[tuple[str, str, str]]) -> str:
    return "".join(f">{header}\n{seq}\n" for _qid, header, seq in records)


def _write_control(out: Path, case_id: str, contigs: dict[str, str], queries: list[tuple[str, str, str]], targets_truth: dict) -> None:
    vis = out / "agent_visible" / case_id
    vis.mkdir(parents=True, exist_ok=True)
    (vis / "contigs.fa").write_text("".join(f">{cid}\n{seq}\n" for cid, seq in contigs.items()), encoding="utf-8")
    (vis / "targets.fa").write_text(_fasta(queries), encoding="utf-8")
    (vis / "case.yaml").write_text(
        yaml.safe_dump(
            {
                "id": case_id,
                "targets": "targets.fa",
                "assembly": "contigs.fa",
                "declared_organism": "synthetic_control",
                "references": "references.yaml",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (vis / "references.yaml").write_text("references: []\n", encoding="utf-8")
    (vis / "reads_R1.fastq").write_text("@r1\nACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIII\n", encoding="utf-8")
    (vis / "reads_R2.fastq").write_text("@r2\nACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIII\n", encoding="utf-8")
    hidden = out / "hidden"
    hidden.mkdir(parents=True, exist_ok=True)
    truth_path = hidden / "truth.yaml"
    blob = yaml.safe_load(truth_path.read_text()) if truth_path.exists() else {"cases": {}}
    blob.setdefault("cases", {})[case_id] = {
        "genome_id": case_id,
        "true_organism": "synthetic_control",
        "split": "controls",
        "corruption": case_id,
        "label": case_id,
        "targets": targets_truth,
        "acceptable_action_classes": ["continue"],
    }
    truth_path.write_text(yaml.safe_dump(blob, sort_keys=False), encoding="utf-8")


def write_orthology_v3_controls(root: Path | None = None) -> Path:
    root = root or ROOT
    out = root / "benchmarks" / "orthology_v3" / "controls"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    loci = load_all_rpob(root)
    mg = loci[ALLELE_SOURCE_GENOME]
    allele = mg["nucleotide"]
    protein = mg["protein"]
    family = load_family("rpoB_RNAP_beta")
    rpoc = load_family("rpoC_RNAP_beta_prime")
    thermo = next(m.sequence for m in family.members if m.protein_id == "WP_004081508.1")
    rpoc_aa = rpoc.members[0].sequence if rpoc and rpoc.members else protein[:400]
    filler = "A" * 900
    ortho_h = f"rpoB target_type=gene_orthologue family=rpoB_RNAP_beta length_aa={len(protein)}"
    ortho = ("rpoB", ortho_h, protein)

    _write_control(out, "ctrl_full_length", { "c1": filler + allele + filler }, [ortho], {
        "rpoB": {"present": True, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "canonical_full_length_mg1655_rpoB_inserted"}},
    })
    _write_control(out, "ctrl_divergent", { "c1": filler + reverse_translate(thermo) + filler }, [ortho], {
        "rpoB": {"present": True, "clean": False, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "public_divergent_family_member_not_mg1655", "protein_id": "WP_004081508.1",
                                "note": "Thermotoga is not a FAST_PILOT hidden genome; used as a divergent family member in a synthetic contig."}},
    })
    cds = allele[:-3] if allele[-3:] in {"TAA", "TAG", "TGA"} else allele
    fusion_nt = cds + reverse_translate(rpoc_aa)
    _write_control(out, "ctrl_fusion", { "c1": filler + fusion_nt + filler }, [ortho], {
        "rpoB": {"present": True, "clean": False, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "synthetic_rpoB_rpoC_fusion_orf", "fusion": True,
                                "note": "Concatenated RpoB CDS and reverse-translated RpoC. Not a species-specific exception."}},
    })
    mid = (len(allele) // 2 // 3) * 3
    split_nt = allele[:mid] + "TAA" + "C" * 30 + "ATG" + allele[mid:]
    _write_control(out, "ctrl_split", { "c1": filler + split_nt + filler }, [ortho], {
        "rpoB": {"present": True, "clean": False, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "biological_split_two_adjacent_orfs_same_contig"}},
    })
    half = (len(allele) // 6) * 3
    _write_control(out, "ctrl_fragmented", { "c1": filler + allele[:half], "c2": allele[half:] + filler }, [ortho], {
        "rpoB": {"present": True, "clean": False, "fragmented": True, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "assembly_fragmented_across_two_contigs"}},
    })
    mutated = list(allele)
    for i in range(0, len(mutated), 9):
        mutated[i] = {"A": "C", "C": "G", "G": "T", "T": "A"}.get(mutated[i], "A")
    para = "".join(mutated)
    _write_control(out, "ctrl_paralogue", { "c1": filler + allele + filler, "c2": filler + para + filler }, [ortho], {
        "rpoB": {"present": True, "clean": False, "paralogue": True, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "two_related_full_length_copies"}},
    })
    domain_nt = allele[540:780]
    _write_control(out, "ctrl_domain_only", { "c1": filler + domain_nt + filler }, [ortho], {
        "rpoB": {"present": False, "clean": False, "uncertainty_required": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "single_conserved_domain_is_not_gene_orthologue"}},
    })
    _write_control(out, "ctrl_absence", { "c1": filler + "C" * 1800 + filler }, [ortho], {
        "rpoB": {"present": False, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                 "provenance": {"rule": "true_absence_unrelated_sequence"}},
    })

    (out / "hidden" / "truth.yaml").exists()
    return out
