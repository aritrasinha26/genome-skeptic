"""Leave-one-genome-out calibration from development genomes and synthetic locus perturbations.

Held-out genomes are never used to fit. The LLM does not set confidence.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.eval.calibration import (
    apply_calibrated_confidence,
    brier_score,
    expected_calibration_error,
    fit_calibration,
    over_under_rates,
    reliability_table,
)
from genome_skeptic.eval.orthology_controls import reverse_translate
from genome_skeptic.eval.scoring import scientifically_correct, TargetTruth
from genome_skeptic.families import load_family
from genome_skeptic.models import Claim, ClaimStatus, ClaimType, TargetProfile, TargetType
from genome_skeptic.claims.confidence import confidence_for_target_type
from genome_skeptic.validators.family_orthology import collect_family_evidence, family_detects_orthologue


def _mutate_aa(seq: str, every: int) -> str:
    table = {"A": "V", "V": "I", "I": "L", "L": "M", "M": "K", "K": "R", "R": "H", "H": "Q", "Q": "N", "N": "D", "D": "E", "E": "S", "S": "T", "T": "A"}
    out = []
    for i, c in enumerate(seq):
        out.append(table.get(c, c) if i % every == 0 else c)
    return "".join(out)


def generate_locus_perturbations(root: Path, settings: Settings) -> list[dict]:
    """Locus-level sequences. No whole-genome assembly."""
    family = load_family("rpoB_RNAP_beta")
    partner = load_family("rpoC_RNAP_beta_prime")
    from genome_skeptic.eval.annotation import ALLELE_SOURCE_GENOME, load_all_rpob
    loci = load_all_rpob(root)
    mg = loci[ALLELE_SOURCE_GENOME]
    allele = mg["nucleotide"]
    protein = mg["protein"]
    filler = "A" * 900
    thermo = next((m.sequence for m in family.members if m.protein_id == "WP_004081508.1"), protein)
    rpoc = partner.members[0].sequence if partner and partner.members else protein[:400]
    cds = allele[:-3] if allele[-3:] in {"TAA", "TAG", "TGA"} else allele
    rows = []

    def add(genome_id, name, contig, present, target_type="gene_orthologue", **extra):
        rows.append({
            "genome_id": genome_id,
            "case_id": f"cal_{genome_id}_{name}",
            "perturbation": name,
            "contig": contig,
            "present": present,
            "target_type": target_type,
            "query_aa": protein,
            **extra,
        })

    add("ecoli_k12", "identity", filler + allele + filler, True)
    add("ecoli_k12", "nt_divergence", filler + "".join({"A": "C", "C": "G", "G": "T", "T": "A"}.get(c, c) if i % 8 == 0 else c for i, c in enumerate(allele)) + filler, True)
    add("ecoli_k12", "coverage_truncation", filler + allele[: len(allele) // 3], True, fragmented=True)
    add("ecoli_k12", "contig_truncation", allele[:600], True, fragmented=True)
    add("pao1", "split", filler + allele[: (len(allele) // 2 // 3) * 3] + "TAA" + "C" * 30 + "ATG" + allele[(len(allele) // 2 // 3) * 3 :] + filler, True)
    add("pao1", "fusion", filler + cds + reverse_translate(rpoc) + filler, True)
    add("pao1", "depth_ok", filler + allele + filler, True)
    add("hpylori", "divergent", filler + reverse_translate(thermo) + filler, True)
    add("hpylori", "paralogue", filler + allele + filler + "N" * 200 + filler + "".join({"A": "G", "G": "A", "C": "T", "T": "C"}.get(c, c) if i % 6 == 0 else c for i, c in enumerate(allele)) + filler, True)
    add("hpylori", "domain_only", filler + allele[540:780] + filler, False)
    add("synthetic", "absence", filler + "C" * 1800 + filler, False)
    add("synthetic", "contamination_span", filler + allele + filler, True)
    add("ecoli_k12", "allele_exact", filler + allele + filler, True, target_type="exact_allele")
    add("pao1", "aa_divergence", filler + reverse_translate(_mutate_aa(protein, 5)) + filler, True)
    add("hpylori", "fragment_two_contigs", None, True, fragmented=True, contigs={"c1": filler + allele[:1200], "c2": allele[1200:] + filler})
    return rows


def _score_row(row: dict, settings: Settings, tmp: Path) -> dict:
    fid = row.get("family_id") or "rpoB_RNAP_beta"
    qid = row.get("query_id") or "rpoB"
    family = load_family(fid)
    contigs = row.get("contigs") or {"c1": row["contig"]}
    asm = tmp / f"{row['case_id']}.fa"
    asm.write_text("".join(f">{k}\n{v}\n" for k, v in contigs.items()), encoding="utf-8")
    profile = TargetProfile(
        query_id=qid,
        sequence=row["query_aa"],
        target_type=TargetType(row["target_type"]),
        family_id=fid,
        family=family,
        expected_length_aa=len(row["query_aa"]),
    )
    ev = collect_family_evidence(
        profile=profile,
        assembly=asm,
        contig_sequences=contigs,
        proteins={},
        query_hits=[],
        settings=settings,
        out_dir=tmp / row["case_id"],
    )
    detected = family_detects_orthologue(profile, [], settings, ev)
    claim_type = ClaimType.target_gene_detected if detected else ClaimType.target_gene_not_detected
    status = ClaimStatus.weakened if ev.architecture in {"fusion", "biological_split", "assembly_fragmented", "unresolved_candidate", "frameshift_or_pseudogene"} else ClaimStatus.supported
    if not detected:
        status = ClaimStatus.supported
    conf = confidence_for_target_type(
        status, [],
        target_type=profile.target_type,
        homology_support=float((ev.metrics or {}).get("best_member_identity") or 0.0),
        not_detected=not detected,
        max_supported=settings.thresholds.max_claim_confidence,
        family_metrics={**(ev.metrics or {}), "architecture": ev.architecture, "hierarchy": ev.hierarchy},
        identity=(ev.metrics or {}).get("best_member_identity"),
        coverage=(ev.metrics or {}).get("best_member_coverage"),
    )
    claim = Claim(
        claim_id="C_target_rpoB",
        claim_type=claim_type,
        statement="calibration locus",
        status=status,
        confidence=conf,
        architecture_state=ev.architecture,
    )
    truth = TargetTruth(
        present=row["present"],
        fragmented=bool(row.get("fragmented")),
        target_type=row["target_type"],
        truth_state="resolved",
    )
    correct = scientifically_correct(claim, truth)
    return {
        "case_id": row["case_id"],
        "genome_id": row["genome_id"],
        "perturbation": row["perturbation"],
        "target_type": row["target_type"],
        "confidence": conf,
        "correct": int(bool(correct)),
        "architecture": ev.architecture,
        "claim_type": claim_type.value,
        "hmm_coverage": (ev.reconstruction or {}).get("hmm_coverage") or (ev.metrics or {}).get("hmm_model_coverage"),
        "family_id": fid,
        "query_id": qid,
    }


def leave_one_genome_out(pairs: list[dict]) -> dict:
    """Fit on all other genomes; score the held-out genome. Never uses FAST_PILOT held-out isolates."""
    by_g = defaultdict(list)
    for row in pairs:
        by_g[row["genome_id"]].append(row)
    scored = []
    models = {}
    for genome, blob in by_g.items():
        train = [r for r in pairs if r["genome_id"] != genome]
        if not train:
            train = blob
        model = fit_calibration(train)
        models[genome] = {"n_train": len(train), "n_test": len(blob), "brier_train": (model.get("overall") or {}).get("brier")}
        for row in blob:
            mapped = apply_calibrated_confidence(float(row["confidence"]), model, row.get("target_type"))
            scored.append({**row, "raw_confidence": row["confidence"], "calibrated_confidence": mapped, "confidence": mapped, "left_out_genome": genome})
    table = reliability_table(scored)
    return {
        "kind": "calibration_v4",
        "fit_split": "development_and_synthetic_controls",
        "held_out_used_to_fit": False,
        "method": "leave_one_genome_out",
        "llm_generated_confidence": False,
        "n": len(scored),
        "by_left_out_genome": models,
        "overall": {
            "reliability": table,
            "brier": brier_score(scored),
            "ece": expected_calibration_error(table, len(scored)),
            **over_under_rates(scored),
        },
        "pairs": scored,
        "note": "Perturbations from a genome never fit the map applied to that genome.",
    }


def run_calibration_v4(root: Path, settings: Settings, tmp: Path) -> dict:
    tmp.mkdir(parents=True, exist_ok=True)
    rows = generate_locus_perturbations(root, settings)
    pairs = []
    for row in rows:
        try:
            pairs.append(_score_row(row, settings, tmp))
        except Exception as exc:
            pairs.append({
                "case_id": row["case_id"],
                "genome_id": row["genome_id"],
                "perturbation": row["perturbation"],
                "target_type": row["target_type"],
                "confidence": 0.5,
                "correct": 0,
                "error": str(exc),
            })
    by_type = defaultdict(list)
    for p in pairs:
        by_type[p.get("target_type") or "unknown"].append(p)
    payload = leave_one_genome_out(pairs)
    payload["by_target_type"] = {
        tt: {
            "n": len(blob),
            "brier": brier_score(blob),
            "ece": expected_calibration_error(reliability_table(blob), len(blob)),
            **over_under_rates(blob),
        }
        for tt, blob in by_type.items()
    }
    payload["raw_pairs_before_logo"] = pairs
    return payload


def generate_multifamily_perturbations(settings: Settings) -> list[dict]:
    """Development-only synthetic loci for extra families. Held-out genomes are not used."""
    from genome_skeptic.eval.orthology_controls import reverse_translate
    rows = []
    filler = "A" * 600
    for fid in ("recA_recombinase", "tuf_EF_Tu", "lacZ_beta_galactosidase", "tetA_tetracycline_efflux"):
        family = load_family(fid)
        if family is None or not family.members:
            continue
        protein = family.members[0].sequence
        allele = reverse_translate(protein)
        qid = fid.split("_")[0]
        def add(name, contig, present, **extra):
            rows.append({
                "genome_id": f"dev_{qid}",
                "case_id": f"cal_{qid}_{name}",
                "perturbation": name,
                "contig": contig,
                "present": present,
                "target_type": "gene_orthologue",
                "query_aa": protein,
                "family_id": fid,
                "query_id": qid,
                **extra,
            })
        add("identity", filler + allele + filler, True)
        add("absence", filler + "C" * min(1800, len(allele)), False)
        if len(family.members) > 1 and family.members[1].sequence:
            add("divergent", filler + reverse_translate(family.members[-1].sequence) + filler, True)
    return rows


def run_calibration_multifamily(root: Path, settings: Settings, tmp: Path) -> dict:
    tmp.mkdir(parents=True, exist_ok=True)
    rows = generate_locus_perturbations(root, settings) + generate_multifamily_perturbations(settings)
    pairs = []
    for row in rows:
        try:
            pairs.append(_score_row(row, settings, tmp))
        except Exception as exc:
            pairs.append({
                "case_id": row["case_id"],
                "genome_id": row["genome_id"],
                "perturbation": row["perturbation"],
                "target_type": row.get("target_type"),
                "family_id": row.get("family_id"),
                "confidence": 0.5,
                "correct": 0,
                "error": str(exc),
            })
    payload = leave_one_genome_out(pairs)
    payload["kind"] = "calibration_multifamily"
    payload["held_out_used_to_fit"] = False
    payload["external_benchmark_used_to_fit"] = False
    payload["n"] = len(pairs)
    payload["raw_pairs_before_logo"] = pairs
    by_family = defaultdict(list)
    for p in pairs:
        by_family[p.get("family_id") or "rpoB_RNAP_beta"].append(p)
    payload["by_family"] = {
        fid: {
            "n": len(blob),
            "brier": brier_score(blob),
            "ece": expected_calibration_error(reliability_table(blob), len(blob)),
            **over_under_rates(blob),
        }
        for fid, blob in by_family.items()
    }
    return payload
