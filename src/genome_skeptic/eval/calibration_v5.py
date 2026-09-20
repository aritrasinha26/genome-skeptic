"""V5 calibration: development genomes and synthetic loci only. Never fit on held-out or external answers."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.eval.calibration import brier_score, expected_calibration_error, over_under_rates, reliability_table
from genome_skeptic.eval.calibration_v4 import generate_locus_perturbations, generate_multifamily_perturbations, _score_row, leave_one_genome_out
from genome_skeptic.eval.orthology_controls import reverse_translate
from genome_skeptic.families import load_family


def generate_v5_extra_perturbations() -> list[dict]:
    filler = "A" * 600
    rows = []
    tet = load_family("tetA_tetracycline_efflux")
    mfs = load_family("mfs_multidrug_efflux")
    tuf = load_family("tuf_EF_Tu")
    rec = load_family("recA_recombinase")
    rpo = load_family("rpoB_RNAP_beta")
    lac = load_family("lacZ_beta_galactosidase")

    def add(genome_id, name, contig, present, family, qid, extra=None, target_type="gene_orthologue"):
        protein = family.members[0].sequence
        rows.append({
            "genome_id": genome_id,
            "case_id": f"cal5_{genome_id}_{name}",
            "perturbation": name,
            "contig": contig,
            "present": present,
            "target_type": target_type,
            "query_aa": protein,
            "family_id": family.family_id,
            "query_id": qid,
            **(extra or {}),
        })

    if rec:
        aa = rec.members[0].sequence
        add("cal_recA", "clean_positive", filler + reverse_translate(aa) + filler, True, rec, "recA")
        add("cal_recA", "clean_negative", filler + "C" * 2000 + filler, False, rec, "recA")
        add("cal_recA", "exact_allele", filler + reverse_translate(aa) + filler, True, rec, "recA", target_type="exact_allele")
    if tuf:
        aa = tuf.members[0].sequence
        nt = reverse_translate(aa)
        add("cal_tuf", "duplication", filler + nt + filler + "C" * 300 + nt + filler, True, tuf, "tuf")
        add("cal_tuf", "partial", filler + nt[: len(nt) // 3], True, tuf, "tuf", extra={"fragmented": True})
    if tet:
        aa = max(tet.members, key=lambda m: len(m.sequence or "")).sequence
        add("cal_tetA", "clean_positive", filler + reverse_translate(aa) + filler, True, tet, "tetA")
        add("cal_tetA", "clean_negative", filler + "G" * 1800 + filler, False, tet, "tetA")
        if mfs and mfs.members:
            add("cal_tetA", "competing_family_false_positive", filler + reverse_translate(mfs.members[0].sequence) + filler, False, tet, "tetA")
        add("cal_tetA", "domain_only", filler + reverse_translate(aa[40:90]) + filler, False, tet, "tetA")
        add("cal_tetA", "protein_family", filler + reverse_translate(aa) + filler, True, tet, "tetA", target_type="protein_family")
    if rpo:
        aa = rpo.members[0].sequence
        nt = reverse_translate(aa)
        fs = nt[:90] + "A" + nt[90:]
        add("cal_rpoB", "frameshift", filler + fs + filler, True, rpo, "rpoB")
        add("cal_rpoB", "wrong_metadata", filler + nt + filler, True, rpo, "rpoB", extra={"declared_organism": "incorrect_label"})
        add("cal_rpoB", "contamination_span", filler + nt + filler, True, rpo, "rpoB")
    if lac:
        aa = lac.members[0].sequence
        add("cal_lacZ", "accessory_present", filler + reverse_translate(aa) + filler, True, lac, "lacZ")
        add("cal_lacZ", "accessory_absent", filler + "C" * 1600 + filler, False, lac, "lacZ")
    return rows


def run_calibration_v5(root: Path, settings: Settings, tmp: Path) -> dict:
    tmp.mkdir(parents=True, exist_ok=True)
    rows = generate_locus_perturbations(root, settings) + generate_multifamily_perturbations(settings) + generate_v5_extra_perturbations()
    pairs = []
    for row in rows:
        try:
            pairs.append(_score_row(row, settings, tmp))
        except Exception as exc:
            pairs.append({
                "case_id": row["case_id"],
                "genome_id": row["genome_id"],
                "perturbation": row.get("perturbation"),
                "target_type": row.get("target_type"),
                "family_id": row.get("family_id"),
                "confidence": 0.5,
                "correct": 0,
                "error": str(exc),
            })
    payload = leave_one_genome_out(pairs)
    payload["kind"] = "calibration_v5"
    payload["held_out_used_to_fit"] = False
    payload["external_benchmark_used_to_fit"] = False
    payload["frozen_before_external"] = True
    payload["n"] = len(pairs)
    payload["raw_pairs_before_logo"] = pairs
    by_family = defaultdict(list)
    by_type = defaultdict(list)
    for p in pairs:
        by_family[p.get("family_id") or "rpoB_RNAP_beta"].append(p)
        by_type[p.get("target_type") or "gene_orthologue"].append(p)
    payload["by_family"] = {
        fid: {
            "n": len(blob),
            "brier": brier_score(blob),
            "ece": expected_calibration_error(reliability_table(blob), len(blob)),
            **over_under_rates(blob),
        }
        for fid, blob in by_family.items()
    }
    payload["by_target_type"] = {
        tt: {
            "n": len(blob),
            "brier": brier_score(blob),
            "ece": expected_calibration_error(reliability_table(blob), len(blob)),
            **over_under_rates(blob),
        }
        for tt, blob in by_type.items()
    }
    payload["confidence_versus_completeness"] = {
        "note": "Numeric confidence is assigned by the deterministic validator. Evidence completeness is recorded separately and is not chosen by the LLM.",
        "n": len(pairs),
    }
    return payload
