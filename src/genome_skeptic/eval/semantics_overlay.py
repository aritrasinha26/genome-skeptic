"""Overlay authentic FAST_PILOT targets/truth and write assembly-only controls.

Does not resimulate reads or rerun SPAdes. Agent-visible assemblies are unchanged.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from genome_skeptic.eval.annotation import ALLELE_SOURCE_GENOME, load_all_rpob, sha256_seq, write_json
from genome_skeptic.eval.catalog import PUBLIC_RPOB_SEED

ROOT = Path(__file__).resolve().parents[3]
CASE_GENOMES = {
    "dev_01": "ecoli_k12",
    "dev_02": "pao1",
    "dev_03": "hpylori",
    "hel_01": "salmonella_lt2",
    "hel_02": "pputida_kt2440",
    "hel_03": "staph_8325",
}
SPLIT_ROOTS = {
    "development": ROOT / "benchmarks" / "real_genomes_fast_pilot_dev",
    "held_out": ROOT / "benchmarks" / "real_genomes_fast_pilot_held",
}


def _fasta(records: list[tuple[str, str, str]]) -> str:
    chunks = []
    for qid, header, seq in records:
        chunks.append(f">{header}\n{seq}\n")
    return "".join(chunks)


def _archive(path: Path, dest_dir: Path) -> None:
    if not path.exists():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / path.name
    if not target.exists():
        shutil.copy2(path, target)


def allele_truth(genome_id: str, mg1655: dict) -> dict:
    present = genome_id == ALLELE_SOURCE_GENOME
    return {
        "present": present,
        "clean": True,
        "uncertainty_required": False,
        "target_type": "exact_allele",
        "truth_state": "resolved",
        "provenance": {
            "rule": "exact_MG1655_rpoB_CDS_from_source_annotation",
            "source_genome": ALLELE_SOURCE_GENOME,
            "accession": mg1655["accession"],
            "gene": mg1655["gene"],
            "locus_tag": mg1655["locus_tag"],
            "gene_id": mg1655["gene_id"],
            "coordinates": [mg1655["start"], mg1655["end"]],
            "strand": mg1655["strand"],
            "nucleotide_length": mg1655["nucleotide_length"],
            "nucleotide_sha256": mg1655["nucleotide_sha256"],
            "independent_of_locate_target": True,
        },
    }


def orthologue_truth(rec: dict) -> dict:
    fusion = bool(rec.get("fusion"))
    present = rec.get("orthology", {}).get("state") == "present"
    if rec.get("rpoB") is None and rec.get("orthology", {}).get("state") == "unresolved":
        return {
            "present": None,
            "clean": False,
            "uncertainty_required": True,
            "target_type": "gene_orthologue",
            "truth_state": "unresolved",
            "provenance": rec.get("orthology") or {"reason": "orthology could not be assigned from annotation"},
        }
    return {
        "present": present,
        "clean": bool(present) and not fusion,
        "uncertainty_required": fusion,
        "fragmented": False,
        "target_type": "gene_orthologue",
        "truth_state": "resolved",
        "fusion": fusion,
        "provenance": {
            "rule": "independent_source_annotation_orthology",
            "genome_id": rec["genome_id"],
            "accession": rec["accession"],
            "gene": rec.get("gene"),
            "locus_tag": rec.get("locus_tag"),
            "gene_id": rec.get("gene_id"),
            "protein_id": rec.get("protein_id"),
            "product": rec.get("product"),
            "coordinates": [rec.get("start"), rec.get("end")],
            "strand": rec.get("strand"),
            "nucleotide_length": rec.get("nucleotide_length"),
            "protein_length": rec.get("protein_length"),
            "protein_sha256": rec.get("protein_sha256"),
            "assignment": rec.get("orthology", {}).get("assignment"),
            "independent_of_locate_target": True,
        },
    }


def overlay_fast_pilot(root: Path | None = None) -> dict:
    root = root or ROOT
    loci = load_all_rpob(root)
    mg1655 = loci[ALLELE_SOURCE_GENOME]
    if not mg1655.get("nucleotide"):
        raise RuntimeError("authentic MG1655 rpoB CDS was not extracted")
    audit = {
        "PUBLIC_RPOB_SEED_invalid": {
            "length": len(PUBLIC_RPOB_SEED),
            "sha256": sha256_seq(PUBLIC_RPOB_SEED),
            "note": "Not an authentic MG1655 rpoB sequence. Replaced as a benchmark query.",
        },
        "mg1655_rpoB": {k: v for k, v in mg1655.items() if k not in {"nucleotide", "protein"}},
        "genomes": {gid: {k: v for k, v in rec.items() if k not in {"nucleotide", "protein"}} for gid, rec in loci.items()},
        "cases": {},
    }
    hidden_set = root / "benchmarks" / "semantics_v2" / "hidden_orthologue_set"
    hidden_set.mkdir(parents=True, exist_ok=True)
    faa = []
    for gid, rec in loci.items():
        if rec.get("protein"):
            faa.append(f">{gid}|{rec.get('protein_id')}|{rec.get('locus_tag')}\n{rec['protein']}\n")
    (hidden_set / "rpoB_proteins.faa").write_text("".join(faa))
    (hidden_set / "README.txt").write_text(
        "Hidden orthology reference set constructed from source annotations. Not agent-visible.\n"
    )
    allele_header = (
        f"rpoB_MG1655_allele target_type=exact_allele length_aa={mg1655['protein_length']} "
        f"taxonomy=Escherichia_coli"
    )
    ortho_header = (
        f"rpoB target_type=gene_orthologue length_aa={mg1655['protein_length']} "
        f"taxonomy=Escherichia_coli"
    )
    targets_text = _fasta([
        ("rpoB_MG1655_allele", allele_header, mg1655["nucleotide"]),
        ("rpoB", ortho_header, mg1655["protein"]),
    ])
    archive_root = root / "benchmarks" / "semantics_v2" / "archived_fast_pilot_v1"
    for split, split_root in SPLIT_ROOTS.items():
        visible = split_root / "agent_visible"
        hidden = split_root / "hidden"
        truth_path = hidden / "truth.yaml"
        _archive(truth_path, archive_root / split)
        truth = yaml.safe_load(truth_path.read_text()) or {}
        for case_id, spec in (truth.get("cases") or {}).items():
            gid = spec.get("genome_id") or CASE_GENOMES[case_id]
            rec = loci[gid]
            case_dir = visible / case_id
            _archive(case_dir / "targets.fa", archive_root / split / case_id)
            (case_dir / "targets.fa").write_text(targets_text)
            spec["targets"] = {
                "rpoB_MG1655_allele": allele_truth(gid, mg1655),
                "rpoB": orthologue_truth(rec),
            }
            audit["cases"][case_id] = {
                "genome_id": gid,
                "split": split,
                "targets": spec["targets"],
            }
        truth_path.write_text(yaml.safe_dump(truth, sort_keys=False))
    write_json(root / "benchmarks" / "semantics_v2" / "authentic_rpob.json", audit)
    return audit


def _write_control(root: Path, case_id: str, contigs: dict[str, str], targets: list[tuple[str, str, str]], truth_targets: dict) -> None:
    vis = root / "agent_visible" / case_id
    vis.mkdir(parents=True, exist_ok=True)
    (vis / "contigs.fa").write_text("".join(f">{k}\n{v}\n" for k, v in contigs.items()))
    (vis / "targets.fa").write_text(_fasta(targets))
    (vis / "case.yaml").write_text(
        f"id: {case_id}\n"
        "targets: targets.fa\n"
        "assembly: contigs.fa\n"
        "declared_organism: synthetic_control\n"
        "references: references.yaml\n"
    )
    (vis / "references.yaml").write_text("references: []\n")
    (vis / "reads_R1.fastq").write_text("@r1\nACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIII\n")
    (vis / "reads_R2.fastq").write_text("@r2\nACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIII\n")
    hidden = root / "hidden"
    hidden.mkdir(parents=True, exist_ok=True)
    truth_path = hidden / "truth.yaml"
    blob = yaml.safe_load(truth_path.read_text()) if truth_path.exists() else {"cases": {}}
    blob.setdefault("cases", {})[case_id] = {
        "genome_id": case_id,
        "true_organism": "synthetic_control",
        "split": "controls",
        "corruption": case_id.split("_", 1)[-1] if "_" in case_id else case_id,
        "label": case_id,
        "targets": truth_targets,
        "acceptable_action_classes": ["continue"],
    }
    truth_path.write_text(yaml.safe_dump(blob, sort_keys=False))


def write_synthetic_controls(root: Path | None = None, loci: dict | None = None) -> Path:
    root = root or ROOT
    loci = loci or load_all_rpob(root)
    mg = loci[ALLELE_SOURCE_GENOME]
    allele = mg["nucleotide"]
    protein = mg["protein"]
    staph = loci["staph_8325"]["nucleotide"]
    hp_nt = loci["hpylori"]["nucleotide"]
    domain_nt = allele[180 * 3:260 * 3]
    filler = "A" * 400
    out = root / "benchmarks" / "semantics_v2" / "controls"
    if out.exists():
        shutil.rmtree(out)
    allele_h = f"rpoB_MG1655_allele target_type=exact_allele length_aa={mg['protein_length']}"
    ortho_h = f"rpoB target_type=gene_orthologue length_aa={mg['protein_length']}"
    family_h = f"rpoB_family target_type=protein_family length_aa={len(protein)}"
    allele_rec = ( "rpoB_MG1655_allele", allele_h, allele)
    ortho_rec = ("rpoB", ortho_h, protein)
    family_rec = ("rpoB_family", family_h, protein)

    _write_control(out, "ctrl_clear_tp", {"c1": filler + allele + filler}, [allele_rec], {
        "rpoB_MG1655_allele": {"present": True, "clean": True, "target_type": "exact_allele", "truth_state": "resolved",
                               "provenance": {"rule": "exact_string_inserted_into_synthetic_contig"}},
    })
    _write_control(out, "ctrl_clear_tn", {"c1": filler + "C" * 1200 + filler}, [allele_rec], {
        "rpoB_MG1655_allele": {"present": False, "clean": True, "target_type": "exact_allele", "truth_state": "resolved",
                               "provenance": {"rule": "no_rpoB_sequence_in_synthetic_contig"}},
    })
    _write_control(out, "ctrl_ambig_pos_partial", {"c1": allele[:int(0.35 * len(allele))]}, [allele_rec], {
        "rpoB_MG1655_allele": {
            "present": True, "clean": False, "fragmented": True, "uncertainty_required": True,
            "target_type": "exact_allele", "truth_state": "resolved",
            "provenance": {"rule": "truncated_allele_at_contig_edge", "query_fraction": 0.35},
        },
    })
    _write_control(out, "ctrl_ambig_neg_domain", {"c1": filler + domain_nt + filler}, [allele_rec], {
        "rpoB_MG1655_allele": {
            "present": False, "clean": False, "uncertainty_required": True, "target_type": "exact_allele",
            "truth_state": "resolved",
            "provenance": {"rule": "protein_domain_only_must_not_be_strain_allele"},
        },
    })
    mutated = list(allele)
    for i in range(0, len(mutated), 7):
        mutated[i] = {"A": "C", "C": "G", "G": "T", "T": "A"}.get(mutated[i], "A")
    para_nt = "".join(mutated)
    _write_control(out, "ctrl_paralogue", {"c1": filler + allele + filler, "c2": filler + para_nt + filler}, [ortho_rec], {
        "rpoB": {
            "present": True, "clean": False, "paralogue": True, "uncertainty_required": True,
            "target_type": "gene_orthologue", "truth_state": "resolved",
            "provenance": {"rule": "two_related_copies_inserted"},
        },
    })
    mid = len(allele) // 2
    _write_control(out, "ctrl_fragmented", {"c1": filler + allele[:mid], "c2": allele[mid:] + filler}, [allele_rec], {
        "rpoB_MG1655_allele": {
            "present": True, "clean": False, "fragmented": True, "uncertainty_required": True,
            "target_type": "exact_allele", "truth_state": "resolved",
            "provenance": {"rule": "allele_split_across_two_contigs"},
        },
    })
    _write_control(out, "ctrl_contamination", {"host": filler + "G" * 800, "foreign": filler + staph + filler}, [ortho_rec], {
        "rpoB": {
            "present": True, "clean": False, "contaminant": True, "uncertainty_required": True,
            "target_type": "gene_orthologue", "truth_state": "resolved",
            "provenance": {"rule": "foreign_contig_carries_staph_rpoB"},
        },
    })
    _write_control(out, "ctrl_divergent_orthologue", {"c1": filler + hp_nt + filler}, [ortho_rec], {
        "rpoB": {
            "present": True, "clean": False, "uncertainty_required": True,
            "target_type": "gene_orthologue", "truth_state": "resolved",
            "provenance": {"rule": "H_pylori_rpoB_rpoC_fusion_protein_as_divergent_orthologue", "fusion": True},
        },
    })
    _write_control(out, "ctrl_family_domain_only", {"c1": filler + domain_nt + filler}, [family_rec], {
        "rpoB_family": {
            "present": False, "clean": False, "uncertainty_required": True,
            "target_type": "protein_family", "truth_state": "resolved",
            "provenance": {"rule": "domain_only_must_not_count_as_full_gene_or_full_family_detection", "query_coverage_expected": len(domain_nt) / 3 / len(protein)},
        },
    })
    _write_control(out, "ctrl_family_full", {"c1": filler + allele + filler}, [family_rec], {
        "rpoB_family": {
            "present": True, "clean": True, "target_type": "protein_family", "truth_state": "resolved",
            "provenance": {"rule": "full_length_protein_family_member_inserted"},
        },
    })
    return out
