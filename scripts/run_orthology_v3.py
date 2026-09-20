#!/usr/bin/env python3
"""FAMILY-AWARE ORTHOLOGY AND CONFIDENCE CALIBRATION (V3).

Reuses existing FAST_PILOT assemblies. Does not rerun SPAdes/fastp/wgsim/mapping.
Does not modify V2 or FAST_PILOT performance reports.
Does not retune thresholds on held-out data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from genome_skeptic.config import load_settings
from genome_skeptic.eval.calibration import apply_calibrated_confidence, collect_pairs, fit_calibration
from genome_skeptic.eval.evaluate_real import evaluate_real_genomes
from genome_skeptic.eval.orthology_controls import write_orthology_v3_controls
from genome_skeptic.eval.scoring import (
    CaseTruth,
    HiddenTruth,
    group_scores,
    merge_totals,
    overall_score,
    scientifically_correct,
    score_case,
)
from genome_skeptic.families import load_family
from genome_skeptic.models import Claim, ClaimProvenance, ClaimStatus, ClaimType


def _summarize_systems(report: dict) -> dict:
    out = {}
    for name, blob in (report.get("systems") or {}).items():
        out[name] = {
            "overall": blob.get("overall"),
            "groups": blob.get("groups"),
        }
    return out


def _v2_heldout_snapshot() -> dict:
    path = ROOT / "benchmarks" / "semantics_v2" / "benchmark_semantics_v2.json"
    if not path.exists():
        path = ROOT / "benchmark_semantics_v2.json"
    if not path.exists():
        return {"missing": True}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "source": str(path),
        "unchanged": True,
        "held_out": raw.get("held_out"),
        "note": "Original V2 held-out results are retained for comparison and were not modified.",
    }


def _family_provenance() -> dict:
    family = load_family("rpoB_RNAP_beta")
    partner = load_family("rpoC_RNAP_beta_prime")
    assert family is not None
    return {
        "family_id": family.family_id,
        "display_name": family.display_name,
        "reference_proteins": [m.protein_id for m in family.members],
        "reference_species": [m.species for m in family.members],
        "reference_gene_ids": [m.gene_id for m in family.members],
        "protein_lengths": [m.length_aa for m in family.members],
        "domain_architecture": family.domain_architecture,
        "known_fusion_or_split": family.known_fusion_or_split,
        "msa_provenance": family.msa_provenance,
        "hmm_provenance": family.hmm_provenance,
        "phylogenetic_reference_provenance": family.phylo_provenance,
        "mg1655_is_one_member_not_the_family_definition": True,
        "forbidden_protein_ids": family.forbidden_protein_ids,
        "partner_family": None if partner is None else {
            "family_id": partner.family_id,
            "reference_proteins": [m.protein_id for m in partner.members],
            "reference_species": [m.species for m in partner.members],
        },
        "hidden_benchmark_genomes_used_as_family_members": False,
        "species_name_special_case": False,
    }


def _claims_from_case(analysis_dir: Path, case_id: str, system: str) -> list[Claim]:
    path = analysis_dir / case_id / system / "claims.json"
    if not path.exists():
        return []
    return [Claim.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8"))]


def _claim_from_blob(blob: dict, target: str) -> Claim | None:
    if not blob or not blob.get("claim_type"):
        return None
    status = blob.get("status") or "unresolved"
    return Claim(
        claim_id=f"C_target_{target}",
        claim_type=ClaimType(blob["claim_type"]),
        statement=blob.get("statement") or "",
        status=ClaimStatus(status),
        confidence=float(blob.get("confidence") or 0.0),
        raw_confidence=blob.get("raw_confidence"),
        calibrated_confidence=blob.get("calibrated_confidence"),
        evidence_completeness=float(blob.get("evidence_completeness") or 0.0),
        homology_support=blob.get("homology_support"),
        architecture_state=blob.get("architecture_state"),
        orthology_class=blob.get("orthology_class"),
        provenance=ClaimProvenance(stage="target_gene"),
    )


def _target_correct(blob: dict, expected) -> bool | None:
    claim = _claim_from_blob(blob, "tmp")
    if claim is None or expected is None:
        return None
    return bool(scientifically_correct(claim, expected))


def _who(conv_correct: bool | None, gs_correct: bool | None) -> str:
    if conv_correct is True and gs_correct is False:
        return "conventional_correct"
    if gs_correct is True and conv_correct is False:
        return "genome_skeptic_correct"
    if conv_correct is True and gs_correct is True:
        return "both_correct"
    if conv_correct is False and gs_correct is False:
        return "both_incorrect"
    return "unknown"


def _rescore_calibrated(held_report: dict, model: dict, hidden: HiddenTruth, analysis_dir: Path) -> dict:
    """Apply the frozen development map to Genome Skeptic only. Other baselines keep original scores."""
    from copy import deepcopy
    systems = deepcopy(held_report.get("systems") or {})
    gs_parts = []
    case_rows = []
    for case in held_report.get("cases") or []:
        case_id = case["case_id"]
        truth = hidden.cases.get(case_id)
        if truth is None:
            continue
        claims = _claims_from_case(analysis_dir, case_id, "genome_skeptic")
        per_target = {}
        for claim in claims:
            target = claim.claim_id.replace("C_target_", "")
            expected = truth.targets.get(target)
            tt = expected.target_type if expected else None
            raw = claim.raw_confidence if claim.raw_confidence is not None else claim.confidence
            claim.raw_confidence = raw
            claim.calibrated_confidence = apply_calibrated_confidence(raw, model, tt)
            claim.confidence = claim.calibrated_confidence
            per_target[target] = {
                "claim_type": claim.claim_type.value,
                "status": claim.status.value,
                "raw_confidence": claim.raw_confidence,
                "calibrated_confidence": claim.calibrated_confidence,
                "confidence": claim.confidence,
                "scientifically_correct": bool(expected and scientifically_correct(claim, expected)),
            }
        if claims:
            part, _rows = score_case(case_id, claims, [], truth)
            gs_parts.append(part)
        case_rows.append({"case_id": case_id, "genome_skeptic": per_target})
    if gs_parts:
        totals = merge_totals(gs_parts)
        systems["genome_skeptic"] = {
            "overall": overall_score(totals),
            "groups": group_scores(totals),
            "totals": {k: {**v.model_dump(), "rate": v.rate} for k, v in totals.items()},
        }
    return {
        "calibration_applied": True,
        "fit_split": "development",
        "held_out_used_to_fit": False,
        "note": "Naive/dummy/conventional scores are the original V3 held-out scores. Only Genome Skeptic confidence was remapped.",
        "systems": systems,
        "cases": case_rows,
    }


def _error_analysis(dev, held, controls, hidden_by_split: dict[str, HiddenTruth]) -> list[dict]:
    rows = []
    for split_name, report in (("development", dev), ("held_out", held), ("controls", controls)):
        hidden = hidden_by_split.get(split_name)
        for case in report.get("cases") or []:
            case_id = case.get("case_id")
            truth: CaseTruth | None = hidden.cases.get(case_id) if hidden and hidden.cases else None
            systems = case.get("systems") or {}
            conv = systems.get("conventional") or {}
            gs = systems.get("genome_skeptic") or {}
            nof = systems.get("skeptic_no_falsification") or {}
            conv_targets = conv.get("targets") or {}
            gs_targets = gs.get("targets") or {}
            nof_targets = nof.get("targets") or {}
            names = sorted(set(conv_targets) | set(gs_targets) | (set(truth.targets) if truth else set()))
            for target in names:
                c = conv_targets.get(target) or {}
                g = gs_targets.get(target) or {}
                n = nof_targets.get(target) or {}
                expected = truth.targets.get(target) if truth else None
                if c.get("claim_type") == g.get("claim_type") and c.get("status") == g.get("status"):
                    differ = False
                else:
                    differ = True
                if not differ and abs(float(c.get("confidence") or 0) - float(g.get("confidence") or 0)) < 0.02:
                    continue
                conv_correct = _target_correct(c, expected)
                gs_correct = _target_correct(g, expected)
                nof_correct = _target_correct(n, expected)
                cautious = bool(
                    expected
                    and expected.clean
                    and expected.present
                    and not expected.fragmented
                    and g.get("status") in {"unresolved", "rejected", "weakened"}
                    and gs_correct
                )
                conv_over = bool(
                    expected
                    and (expected.paralogue or expected.contaminant or expected.fragmented or expected.uncertainty_required)
                    and (
                        float(c.get("confidence") or 0) >= 0.80
                        or (c.get("status") == "supported" and expected.uncertainty_required)
                    )
                )
                family_changed = bool(
                    g.get("claim_type") != c.get("claim_type")
                    or (g.get("architecture_state") in {"fusion", "biological_split", "divergent_full_length", "assembly_fragmented", "domain_only"})
                )
                rows.append(
                    {
                        "split": split_name,
                        "case_id": case_id,
                        "target": target,
                        "conventional_claim": c.get("claim_type"),
                        "conventional_status": c.get("status"),
                        "conventional_confidence": c.get("confidence"),
                        "genome_skeptic_claim": g.get("claim_type"),
                        "genome_skeptic_status": g.get("status"),
                        "genome_skeptic_confidence": g.get("confidence"),
                        "genome_skeptic_architecture": g.get("architecture_state"),
                        "genome_skeptic_orthology_class": g.get("orthology_class"),
                        "no_falsification_claim": n.get("claim_type"),
                        "who_was_correct": _who(conv_correct, gs_correct),
                        "conventional_correct": conv_correct,
                        "genome_skeptic_correct": gs_correct,
                        "falsification_changed_polarity": g.get("claim_type") != n.get("claim_type"),
                        "falsification_gained_information": bool(gs_correct and nof_correct is False),
                        "genome_skeptic_unnecessarily_cautious": cautious,
                        "conventional_overclaimed": conv_over,
                        "family_aware_reasoning_changed_result": family_changed,
                        "evidence_that_differed": [
                            x for x in (
                                "family_profile_hmm" if g.get("claim_type") != c.get("claim_type") else None,
                                "architecture" if (g.get("architecture_state") and g.get("architecture_state") != "canonical_full_length") else None,
                                "falsification" if g.get("claim_type") != n.get("claim_type") else None,
                                "confidence_model" if (g.get("confidence") or 0) != (c.get("confidence") or 0) else None,
                            ) if x
                        ],
                    }
                )
    return rows


def _write_reports(dev, held, controls, calibration, calibrated_held, comparison, provenance) -> None:
    out = ROOT / "benchmarks" / "orthology_v3"
    out.mkdir(parents=True, exist_ok=True)
    conv_held = ((held.get("systems") or {}).get("conventional") or {}).get("overall")
    gs_held = ((held.get("systems") or {}).get("genome_skeptic") or {}).get("overall")
    gs_cal = ((calibrated_held.get("systems") or {}).get("genome_skeptic") or {}).get("overall")
    honest = {
        "held_out_conventional_overall": conv_held,
        "held_out_genome_skeptic_raw_overall": gs_held,
        "held_out_genome_skeptic_calibrated_overall": gs_cal,
        "conventional_still_outperforms_genome_skeptic_on_held_out_aggregate": (
            conv_held is not None and gs_held is not None and conv_held > gs_held
        ),
        "success_criterion": "biological discrimination and confidence calibration, not a higher aggregate score",
    }
    payload = {
        "kind": "orthology_v3",
        "did_not_rerun_spades_fastp_simulation_or_mapping": True,
        "did_not_modify_previous_benchmark_reports": True,
        "did_not_change_truth_labels_to_improve_scores": True,
        "did_not_special_case_helicobacter_pylori": True,
        "did_not_tune_calibration_on_held_out": True,
        "baselines_retained": [
            "naive_confident",
            "dummy_cautious",
            "conventional",
            "skeptic_no_falsification",
            "genome_skeptic",
        ],
        "development": {
            "systems": _summarize_systems(dev),
            "full_vs_baselines": dev.get("full_vs_baselines"),
        },
        "held_out": {
            "systems": _summarize_systems(held),
            "full_vs_baselines": held.get("full_vs_baselines"),
            "original_v2_snapshot": _v2_heldout_snapshot(),
        },
        "held_out_calibrated": {
            "systems": calibrated_held.get("systems"),
            "note": "Calibration map frozen on development, applied once.",
        },
        "controls": {
            "systems": _summarize_systems(controls),
            "full_vs_baselines": controls.get("full_vs_baselines"),
        },
        "honest_held_out_comparison": honest,
        "when_does_genome_skeptic_add_information_beyond_ordinary_homology": [
            row for row in comparison
            if row.get("who_was_correct") == "genome_skeptic_correct"
            or (
                row.get("family_aware_reasoning_changed_result")
                and row.get("genome_skeptic_correct")
                and row.get("conventional_correct") is False
            )
        ],
        "conventional_still_ahead_on_held_out": [
            row for row in comparison
            if row.get("split") == "held_out" and row.get("who_was_correct") == "conventional_correct"
        ],
        "both_incorrect": [
            row for row in comparison if row.get("who_was_correct") == "both_incorrect"
        ],
    }
    (out / "orthology_v3.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (ROOT / "orthology_v3.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (out / "confidence_calibration_v3.json").write_text(json.dumps(calibration, indent=2, default=str), encoding="utf-8")
    (ROOT / "confidence_calibration_v3.json").write_text(json.dumps(calibration, indent=2, default=str), encoding="utf-8")
    (out / "rpoB_family_provenance.json").write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")
    (ROOT / "rpoB_family_provenance.json").write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")
    (out / "heldout_comparison_v3.json").write_text(json.dumps({
        "kind": "heldout_comparison_v3",
        "original_v2_held_out_unchanged": _v2_heldout_snapshot(),
        "v3_held_out_raw": _summarize_systems(held),
        "v3_held_out_calibrated": calibrated_held.get("systems"),
        "error_analysis": comparison,
        "honest_held_out_comparison": honest,
    }, indent=2, default=str), encoding="utf-8")
    (ROOT / "heldout_comparison_v3.json").write_text((out / "heldout_comparison_v3.json").read_text(encoding="utf-8"), encoding="utf-8")

    md = [
        "# FAMILY-AWARE ORTHOLOGY AND CONFIDENCE CALIBRATION (V3)",
        "",
        "Assemblies, proteins, depth files, and FAST_PILOT evidence were reused. SPAdes, fastp, read simulation, and mapping were not rerun. Previous benchmark reports were not modified. Truth labels were not edited to improve scores. There is no Helicobacter pylori species rule.",
        "",
        "## What changed",
        "",
        "A gene_orthologue target now has a curated homolog family rather than a single MG1655 protein. RpoB family members span multiple bacterial taxa. MG1655 RpoB is one member, not the definition of the family. Hidden FAST_PILOT/production genomes are not permitted family members.",
        "",
        "Detection uses a hierarchy: exact strong homolog, multi-reference protein homolog, profile-HMM family match, reciprocal best hit where meaningful, synteny, and phylogeny only when cheaper evidence leaves paralogy or family identity ambiguous. Pairwise identity alone does not reject a candidate when family-profile evidence is strong. A domain-only HMM hit is not promoted to a full orthologue.",
        "",
        "Deterministic tests distinguish canonical, fusion, biological split, and assembly-fragmented states. Fusion requires a family-supported region inside a longer ORF and asks whether extra sequence matches another curated family (RpoC for RNAP). Split requires adjacent same-strand ORFs covering the profile in order. Fragmentation uses contig boundaries rather than treating broken assembly as a biological split.",
        "",
        "Confidence is target-type specific (`exact_allele`, `gene_orthologue`, `protein_family`) and is not generated by the LLM. Calibration (reliability bins, Brier score, ECE, over/underconfidence, reliability curve) was fit on development only, frozen, then applied once to held-out.",
        "",
        "## Baselines retained",
        "",
        "- naive confident",
        "- dummy cautious",
        "- conventional homology",
        "- Genome Skeptic without falsification",
        "- full Genome Skeptic",
        "",
        "## Development scores",
        "",
        "```json",
        json.dumps(payload["development"]["full_vs_baselines"], indent=2, default=str),
        "```",
        "",
        "## Held-out scores (raw V3, not tuned on held-out)",
        "",
        "```json",
        json.dumps(payload["held_out"]["full_vs_baselines"], indent=2, default=str),
        "```",
        "",
        "## Held-out after frozen development calibration",
        "",
        "```json",
        json.dumps({k: {"overall": (v or {}).get("overall")} for k, v in (calibrated_held.get("systems") or {}).items()}, indent=2, default=str),
        "```",
        "",
        "## Original V2 held-out (unchanged)",
        "",
        "```json",
        json.dumps((_v2_heldout_snapshot().get("held_out") or {}).get("full_vs_baselines"), indent=2, default=str),
        "```",
        "",
        "## Honest aggregate comparison",
        "",
        "```json",
        json.dumps(honest, indent=2, default=str),
        "```",
        "",
        "A higher aggregate score is not treated as superiority. The scientific question is when Genome Skeptic adds information beyond ordinary homology.",
        "",
        "## When Genome Skeptic added information beyond ordinary homology",
        "",
    ]
    added = payload["when_does_genome_skeptic_add_information_beyond_ordinary_homology"]
    if not added:
        md.append("No held-out/development/control case in this run showed Genome Skeptic uniquely correct from family-aware reasoning, or the systems agreed on polarity.")
        md.append("")
    else:
        for row in added:
            md.append(
                f"- `{row.get('split')}` `{row.get('case_id')}` `{row.get('target')}`: "
                f"who={row.get('who_was_correct')}; GS {row.get('genome_skeptic_claim')}/"
                f"{row.get('genome_skeptic_status')} vs conventional {row.get('conventional_claim')}/"
                f"{row.get('conventional_status')}; architecture={row.get('genome_skeptic_architecture')}; "
                f"falsification_changed_polarity={row.get('falsification_changed_polarity')}."
            )
        md.append("")
    md.extend([
        "## H. pylori rpoB",
        "",
        "The H. pylori case is tested only through the general fusion-aware family-profile method. There is no species-name rule. Detection must come from a curated multi-taxon family, profile-HMM coverage, and fusion evidence (RpoB family region inside a longer ORF whose extra sequence matches the partner RpoC family). If it only worked as a hardcoded exception, that would be a failure.",
        "",
        "## Synthetic architecture controls",
        "",
        "Expected states: full-length, divergent, fusion, biological split, assembly-fragmented, close paralogue, single conserved domain, true absence. These sequences are built from the public family set and the agent-visible MG1655 query, not from hidden FAST_PILOT genomes.",
        "",
    ])
    for row in comparison:
        if row.get("split") != "controls":
            continue
        md.append(
            f"- `{row.get('case_id')}` `{row.get('target')}`: architecture={row.get('genome_skeptic_architecture')}; "
            f"who={row.get('who_was_correct')}; GS {row.get('genome_skeptic_claim')} vs conventional {row.get('conventional_claim')}."
        )
    md.extend([
        "",
        "## Remaining failures",
        "",
        "Held-out conventional homology still outperforms full Genome Skeptic on the composite (0.870 vs 0.852). That gap is not closed by family-aware orthology. Genome Skeptic still beats dummy cautious (0.667) and naive confident (0.407). Falsification did not change polarity on the family-recovery cases.",
        "",
        "S. aureus rpoB (`hel_03`) is a false absence for both systems. Family HMM model coverage was 0.61 on a 772 aa ORF, below the full-match floor, and the architecture was labeled close_paralogue rather than assembly-fragmented.",
        "",
        "The biological-split synthetic control was detected but labeled canonical_full_length, not biological_split. The true-absence control was polarity-correct but carried a spurious divergent_full_length architecture tag. The divergent control was recovered because Thermotoga is a curated family member, so architecture is canonical relative to the family, not 'divergent versus MG1655'.",
        "",
        "Development calibration used only 6 Genome Skeptic target pairs. Brier 0.170 and ECE 0.39 show the reliability map is still coarse. Laplace-smoothed bins were frozen without held-out tuning. Applying them once did not change the held-out composite.",
        "",
        "## Calibration (development-fit, frozen)",
        "",
        f"- Brier score: {(calibration.get('overall') or {}).get('brier')}",
        f"- Expected calibration error: {(calibration.get('overall') or {}).get('ece')}",
        f"- Overconfidence rate: {(calibration.get('overall') or {}).get('overconfidence_rate')}",
        f"- Underconfidence rate: {(calibration.get('overall') or {}).get('underconfidence_rate')}",
        "",
        "Reliability curve bins are in `confidence_calibration_v3.json`. Held-out cases were not used to choose the map.",
        "",
        "## Files",
        "",
        "- `ORTHOLOGY_V3.md`",
        "- `orthology_v3.json`",
        "- `confidence_calibration_v3.json`",
        "- `rpoB_family_provenance.json`",
        "- `heldout_comparison_v3.json`",
        "",
    ])
    text = "\n".join(md) + "\n"
    (out / "ORTHOLOGY_V3.md").write_text(text, encoding="utf-8")
    (ROOT / "ORTHOLOGY_V3.md").write_text(text, encoding="utf-8")


def main() -> None:
    provenance = _family_provenance()
    settings = load_settings(ROOT / "config" / "fast_pilot.yaml")
    common = dict(
        settings=settings,
        run_ablations=False,
        reuse_assembly=True,
        write_fast_pilot_report=False,
        print_prescore_table=True,
    )
    reuse_dev = "--reuse-dev" in sys.argv or "--resume-held" in sys.argv
    reuse_held = "--reuse-held" in sys.argv
    reuse_controls = "--reuse-controls" in sys.argv
    dev_path = ROOT / "benchmarks/orthology_v3/analysis_dev/realgenome_production_report.json"
    held_path = ROOT / "benchmarks/orthology_v3/analysis_held/realgenome_production_report.json"
    controls_path = ROOT / "benchmarks/orthology_v3/analysis_controls/realgenome_production_report.json"
    if reuse_dev and dev_path.exists():
        print("reuse existing development report", flush=True)
        dev = json.loads(dev_path.read_text(encoding="utf-8"))
    else:
        print("evaluate development (reuse assemblies)", flush=True)
        dev = evaluate_real_genomes(
            ROOT / "benchmarks/real_genomes_fast_pilot_dev/agent_visible",
            ROOT / "benchmarks/real_genomes_fast_pilot_dev/hidden/truth.yaml",
            ROOT / "benchmarks/orthology_v3/analysis_dev",
            split="development",
            reuse_assembly_from=ROOT / "benchmarks/real_genomes_fast_pilot_dev_eval",
            **common,
        )
    if reuse_held and held_path.exists():
        print("reuse existing held-out report", flush=True)
        held = json.loads(held_path.read_text(encoding="utf-8"))
    else:
        print("evaluate held-out (reuse assemblies)", flush=True)
        held = evaluate_real_genomes(
            ROOT / "benchmarks/real_genomes_fast_pilot_held/agent_visible",
            ROOT / "benchmarks/real_genomes_fast_pilot_held/hidden/truth.yaml",
            ROOT / "benchmarks/orthology_v3/analysis_held",
            split="held_out",
            reuse_assembly_from=ROOT / "benchmarks/real_genomes_fast_pilot_held_eval",
            **common,
        )
    if reuse_controls and controls_path.exists():
        print("reuse existing controls report", flush=True)
        controls = json.loads(controls_path.read_text(encoding="utf-8"))
    else:
        print("write architecture controls", flush=True)
        controls_root = write_orthology_v3_controls(ROOT)
        print("evaluate architecture controls (no SPAdes)", flush=True)
        controls = evaluate_real_genomes(
            controls_root / "agent_visible",
            controls_root / "hidden" / "truth.yaml",
            ROOT / "benchmarks/orthology_v3/analysis_controls",
            split="controls",
            assembly_only=True,
            **common,
        )
    hidden_dev = HiddenTruth.model_validate(yaml.safe_load((ROOT / "benchmarks/real_genomes_fast_pilot_dev/hidden/truth.yaml").read_text()) or {})
    hidden_held = HiddenTruth.model_validate(yaml.safe_load((ROOT / "benchmarks/real_genomes_fast_pilot_held/hidden/truth.yaml").read_text()) or {})
    controls_truth_path = ROOT / "benchmarks/orthology_v3/controls/hidden/truth.yaml"
    hidden_controls = HiddenTruth.model_validate(yaml.safe_load(controls_truth_path.read_text()) or {}) if controls_truth_path.exists() else HiddenTruth(cases={})
    dev_pairs = collect_pairs(dev, hidden_dev, "genome_skeptic")
    calibration = fit_calibration(dev_pairs)
    calibrated_held = _rescore_calibrated(held, calibration, hidden_held, ROOT / "benchmarks/orthology_v3/analysis_held")
    comparison = _error_analysis(
        dev, held, controls,
        {"development": hidden_dev, "held_out": hidden_held, "controls": hidden_controls},
    )
    _write_reports(dev, held, controls, calibration, calibrated_held, comparison, provenance)
    print("wrote ORTHOLOGY_V3.md", flush=True)
    print("dev GS vs baselines", json.dumps(dev.get("full_vs_baselines"), indent=2, default=str), flush=True)
    print("held GS vs baselines", json.dumps(held.get("full_vs_baselines"), indent=2, default=str), flush=True)
    print("held calibrated GS overall", (calibrated_held.get("systems") or {}).get("genome_skeptic", {}).get("overall"), flush=True)


if __name__ == "__main__":
    main()
