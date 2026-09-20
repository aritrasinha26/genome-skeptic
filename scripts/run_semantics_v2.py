#!/usr/bin/env python3
"""Analysis-only semantics v2 run. Does not rerun SPAdes, fastp, or wgsim."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from genome_skeptic.config import load_settings
from genome_skeptic.eval.evaluate_real import evaluate_real_genomes
from genome_skeptic.eval.semantics_overlay import overlay_fast_pilot, write_synthetic_controls


def _label_old_reports() -> None:
    notice = (
        "INVALID FOR PERFORMANCE COMPARISON.\n"
        "This FAST_PILOT report is preserved unchanged. Its scores used PUBLIC_RPOB_SEED "
        "(not authentic MG1655 rpoB), identity>=0.5 truth with no coverage floor, "
        "held-out cases labeled absent only, and a dummy cautious baseline that could tie "
        "Genome Skeptic. See BENCHMARK_SEMANTICS_V2.md.\n"
    )
    for split in ("dev", "held"):
        d = ROOT / f"benchmarks/real_genomes_fast_pilot_{split}_eval"
        (d / "FAST_PILOT_INVALID_FOR_PERFORMANCE.txt").write_text(notice)


def _write_reports(dev, held, controls) -> None:
    out = ROOT / "benchmarks" / "semantics_v2"
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": "benchmark_semantics_v2",
        "old_fast_pilot_invalid_for_performance": True,
        "old_fast_pilot_reason": [
            "PUBLIC_RPOB_SEED is not authentic MG1655 rpoB",
            "hidden truth used identity >= 0.5 with no coverage floor",
            "dummy cautious baseline could tie Genome Skeptic",
            "held-out cases were all labeled target absent",
            "confidence and evidence completeness were nearly constant",
        ],
        "development": {
            "systems": {k: {"overall": v.get("overall"), "groups": v.get("groups")} for k, v in (dev.get("systems") or {}).items()},
            "full_vs_baselines": dev.get("full_vs_baselines"),
            "prescore_table": dev.get("prescore_table"),
        },
        "held_out": {
            "systems": {k: {"overall": v.get("overall"), "groups": v.get("groups")} for k, v in (held.get("systems") or {}).items()},
            "full_vs_baselines": held.get("full_vs_baselines"),
            "prescore_table": held.get("prescore_table"),
        },
        "controls": {
            "systems": {k: {"overall": v.get("overall"), "groups": v.get("groups")} for k, v in (controls.get("systems") or {}).items()},
            "full_vs_baselines": controls.get("full_vs_baselines"),
            "prescore_table": controls.get("prescore_table"),
        },
    }
    combined_groups = {}
    for split_name, blob in (("development", dev), ("held_out", held), ("controls", controls)):
        for sys_name, sys_blob in (blob.get("systems") or {}).items():
            combined_groups.setdefault(sys_name, {})[split_name] = {
                "overall": sys_blob.get("overall"),
                "groups": sys_blob.get("groups"),
            }
    payload["systems_by_split"] = combined_groups
    gs_beats = []
    for blob in (dev, held, controls):
        cmp_ = blob.get("full_vs_baselines") or {}
        gs_beats.append(cmp_.get("full_beats_both_trivial_baselines"))
    payload["full_genome_skeptic_beats_both_trivial_baselines_on_every_split"] = all(gs_beats)
    payload["full_genome_skeptic_beats_both_trivial_baselines_on_any_split"] = any(gs_beats)
    (out / "benchmark_semantics_v2.json").write_text(json.dumps(payload, indent=2, default=str))
    (ROOT / "benchmark_semantics_v2.json").write_text(json.dumps(payload, indent=2, default=str))

    audit_src = out / "authentic_rpob.json"
    audit = json.loads(audit_src.read_text()) if audit_src.exists() else {}
    audit["prescore_development"] = dev.get("prescore_table")
    audit["prescore_held_out"] = held.get("prescore_table")
    audit["prescore_controls"] = controls.get("prescore_table")
    (out / "target_truth_audit.json").write_text(json.dumps(audit, indent=2, default=str))
    (ROOT / "target_truth_audit.json").write_text(json.dumps(audit, indent=2, default=str))

    conf_rows = []
    for split_name, blob in (("development", dev), ("held_out", held), ("controls", controls)):
        for row in blob.get("prescore_table") or []:
            if row.get("system") != "genome_skeptic":
                continue
            conf_rows.append({
                "split": split_name,
                "case_id": row.get("case_id"),
                "target": row.get("target"),
                "target_type": row.get("target_type"),
                "hidden_true_state": row.get("hidden_true_state"),
                "best_nucleotide_identity": row.get("best_nucleotide_identity"),
                "best_nucleotide_coverage": row.get("best_nucleotide_coverage"),
                "best_protein_identity": row.get("best_protein_identity"),
                "best_protein_coverage": row.get("best_protein_coverage"),
                "claim": row.get("claim"),
                "status": row.get("status"),
                "confidence": row.get("confidence"),
                "evidence_completeness": row.get("evidence_completeness"),
                "homology_support": row.get("homology_support"),
            })
    confidences = [r["confidence"] for r in conf_rows if r.get("confidence") is not None]
    completeness = [r["evidence_completeness"] for r in conf_rows if r.get("evidence_completeness") is not None]
    homology = [r["homology_support"] for r in conf_rows if r.get("homology_support") is not None]

    def _span(vals):
        if not vals:
            return None
        return {"min": min(vals), "max": max(vals), "n": len(vals), "unique_rounded_2dp": sorted(set(round(v, 2) for v in vals))}

    calib = {
        "llm_did_not_choose_confidence": True,
        "held_out_not_used_to_tune_confidence": True,
        "rows": conf_rows,
        "confidence_span": _span(confidences),
        "evidence_completeness_span": _span(completeness),
        "homology_support_span": _span(homology),
        "confidence_and_completeness_are_separate": True,
        "note": "Passing tests is not a claim of scientific improvement.",
    }
    (out / "confidence_calibration_v2.json").write_text(json.dumps(calib, indent=2, default=str))
    (ROOT / "confidence_calibration_v2.json").write_text(json.dumps(calib, indent=2, default=str))

    def _ov(blob, name):
        return ((blob.get("systems") or {}).get(name) or {}).get("overall")

    md = []
    md.append("# BENCHMARK SEMANTICS V2")
    md.append("")
    md.append("FAST PILOT v1 scores are **invalid for performance comparison**. The preserved `FAST_PILOT_REPORT.md` files were not rewritten.")
    md.append("")
    md.append("## Why v1 was invalid")
    md.append("")
    md.append("1. `PUBLIC_RPOB_SEED` is a 122-nt fragment, not the authentic MG1655 rpoB CDS.")
    md.append("2. Hidden truth used locate_target identity ≥ 0.5 with no coverage floor (52/122 bp could count as present).")
    md.append("3. A dummy cautious baseline could tie Genome Skeptic.")
    md.append("4. Held-out cases were all labeled target-absent.")
    md.append("5. Confidence and evidence completeness were nearly constant across biologically different cases.")
    md.append("")
    md.append("This run does **not** rerun SPAdes, fastp, or sequencing simulation. Production assemblies were reused.")
    md.append("Revised tests passing is **not** a claim of scientific improvement.")
    md.append("")
    md.append("## Target semantics")
    md.append("")
    md.append("| target_type | query | truth |")
    md.append("|---|---|---|")
    md.append("| exact_allele | authentic MG1655 rpoB CDS (4029 nt) | exact strain-level sequence relationship |")
    md.append("| gene_orthologue | authentic MG1655 RpoB protein | source-annotation rpoB / documented fusion |")
    md.append("| protein_family | full RpoB protein on synthetic controls | homolog/profile presence; domain-only is not full-gene detection |")
    md.append("")
    md.append("Nucleotide identity alone does not define cross-species orthologue truth. Domain-only evidence does not become full-gene detection.")
    md.append("If independent orthology cannot be assigned, the case is labeled unresolved rather than given a manufactured binary label.")
    md.append("")
    md.append("## Pre-score tables")
    md.append("")
    md.append("Printed to stdout during the run and stored in `benchmark_semantics_v2.json` / `target_truth_audit.json`.")
    md.append("")
    md.append("## Split scores (group metrics, not one overall)")
    md.append("")
    for split_name, blob in (("development", dev), ("held_out", held), ("controls", controls)):
        md.append(f"### {split_name}")
        md.append("")
        md.append("| System | Overall | detection | scope | status | calibration | completeness | overclaim | underclaim | abstention | next-action |")
        md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for name in ("naive_confident", "dummy_cautious", "conventional", "skeptic_no_falsification", "genome_skeptic"):
            sysb = (blob.get("systems") or {}).get(name) or {}
            g = sysb.get("groups") or {}
            def r(key):
                val = (g.get(key) or {}).get("rate")
                return "n/a" if val is None else f"{val:.3f}"
            ov = sysb.get("overall")
            ov_s = "n/a" if ov is None else f"{ov:.3f}"
            md.append(
                f"| {name} | {ov_s} | {r('detection_correctness')} | {r('claim_scope_correctness')} | "
                f"{r('status_appropriateness')} | {r('confidence_calibration')} | {r('evidence_completeness_consistency')} | "
                f"{r('overclaiming')} | {r('underclaiming')} | {r('appropriate_abstention')} | {r('next_action_usefulness')} |"
            )
        cmp_ = blob.get("full_vs_baselines") or {}
        md.append("")
        md.append(f"- Full Genome Skeptic beats dummy cautious: {cmp_.get('full_beats_dummy')}")
        md.append(f"- Full Genome Skeptic beats naive confident: {cmp_.get('full_beats_naive')}")
        md.append(f"- Full Genome Skeptic beats both trivial baselines: {cmp_.get('full_beats_both_trivial_baselines')}")
        md.append("")
    beats = payload["full_genome_skeptic_beats_both_trivial_baselines_on_every_split"]
    md.append("## Interpretation")
    md.append("")
    if beats:
        md.append("Full Genome Skeptic outperformed both trivial baselines on development, held-out, and synthetic-control mixtures of positive and negative cases.")
    else:
        md.append(
            "Full Genome Skeptic did **not** outperform both trivial baselines on every mixed positive/negative split. "
            "That is reported directly. It is not hidden behind a single overall score, and it is not described as improvement because tests passed."
        )
    md.append("")
    md.append("Held-out now contains both true presence (rpoB gene_orthologue) and true absence (MG1655 exact_allele).")
    md.append("A system that always says `not detected in this assembly, weakened` must fail clean positives.")
    md.append("A system that always converts homology into organism-level present/absent must fail claim-scope scoring.")
    md.append("")
    md.append("## Confidence")
    md.append("")
    md.append("Confidence is computed from measured homology (identity, coverage, search mode, truncation, paralogue loci, local depth).")
    md.append("Evidence completeness remains a separate score. Missing Bakta/taxonomy/HMMER/synteny may lower completeness without flattening distinct homology into identical confidence.")
    md.append("The LLM does not choose confidence numerically. Held-out cases were not used to tune confidence.")
    md.append("")
    span = calib.get("confidence_span") or {}
    md.append(f"- Genome Skeptic confidence span: {span}")
    md.append(f"- Evidence completeness span: {calib.get('evidence_completeness_span')}")
    md.append(f"- Homology support span: {calib.get('homology_support_span')}")
    md.append("")
    md.append("## Files")
    md.append("")
    md.append("- `benchmark_semantics_v2.json`")
    md.append("- `target_truth_audit.json`")
    md.append("- `confidence_calibration_v2.json`")
    md.append("- archived v1 targets/truth under `archived_fast_pilot_v1/`")
    md.append("")
    (out / "BENCHMARK_SEMANTICS_V2.md").write_text("\n".join(md) + "\n")
    (ROOT / "BENCHMARK_SEMANTICS_V2.md").write_text("\n".join(md) + "\n")


def main() -> None:
    _label_old_reports()
    print("overlay authentic rpoB targets/truth", flush=True)
    overlay_fast_pilot(ROOT)
    print("write synthetic controls", flush=True)
    controls_root = write_synthetic_controls(ROOT)
    settings = load_settings(ROOT / "config" / "fast_pilot.yaml")
    common = dict(
        settings=settings,
        run_ablations=False,
        reuse_assembly=True,
        write_fast_pilot_report=False,
        print_prescore_table=True,
    )
    print("evaluate development (reuse assemblies)", flush=True)
    dev = evaluate_real_genomes(
        ROOT / "benchmarks/real_genomes_fast_pilot_dev/agent_visible",
        ROOT / "benchmarks/real_genomes_fast_pilot_dev/hidden/truth.yaml",
        ROOT / "benchmarks/semantics_v2/analysis_dev",
        split="development",
        reuse_assembly_from=ROOT / "benchmarks/real_genomes_fast_pilot_dev_eval",
        **common,
    )
    print("evaluate held-out (reuse assemblies)", flush=True)
    held = evaluate_real_genomes(
        ROOT / "benchmarks/real_genomes_fast_pilot_held/agent_visible",
        ROOT / "benchmarks/real_genomes_fast_pilot_held/hidden/truth.yaml",
        ROOT / "benchmarks/semantics_v2/analysis_held",
        split="held_out",
        reuse_assembly_from=ROOT / "benchmarks/real_genomes_fast_pilot_held_eval",
        **common,
    )
    print("evaluate synthetic controls (no SPAdes)", flush=True)
    controls = evaluate_real_genomes(
        controls_root / "agent_visible",
        controls_root / "hidden" / "truth.yaml",
        ROOT / "benchmarks/semantics_v2/analysis_controls",
        split="controls",
        assembly_only=True,
        **common,
    )
    _write_reports(dev, held, controls)
    print("wrote BENCHMARK_SEMANTICS_V2.md", flush=True)
    print("dev GS vs baselines", json.dumps(dev.get("full_vs_baselines"), indent=2, default=str), flush=True)
    print("held GS vs baselines", json.dumps(held.get("full_vs_baselines"), indent=2, default=str), flush=True)
    print("controls GS vs baselines", json.dumps(controls.get("full_vs_baselines"), indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
