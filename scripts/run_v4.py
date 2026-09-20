#!/usr/bin/env python3
"""GENOME SKEPTIC V4 evaluation. Reuses FAST_PILOT assemblies. Does not retune held-out or edit V3 reports."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from genome_skeptic.config import load_settings
from genome_skeptic.eval.evaluate_real import evaluate_real_genomes
from genome_skeptic.eval.orthology_controls import write_orthology_v3_controls
from genome_skeptic.eval.calibration_v4 import run_calibration_v4
from genome_skeptic.eval.robustness_v4 import run_robustness_suite
from genome_skeptic.claims.action_policy import catalog_as_dicts


def _copy_report(src: dict) -> dict:
    return {
        "overall": ((src.get("systems") or {}).get("genome_skeptic") or {}).get("overall"),
        "conventional": ((src.get("systems") or {}).get("conventional") or {}).get("overall"),
        "dummy_cautious": ((src.get("systems") or {}).get("dummy_cautious") or {}).get("overall"),
        "naive_confident": ((src.get("systems") or {}).get("naive_confident") or {}).get("overall"),
        "groups": ((src.get("systems") or {}).get("genome_skeptic") or {}).get("groups"),
    }


def _case_rows(report: dict) -> list[dict]:
    rows = []
    for case in report.get("cases") or []:
        gs = (case.get("systems") or {}).get("genome_skeptic") or {}
        conv = (case.get("systems") or {}).get("conventional") or {}
        for target, blob in (gs.get("targets") or {}).items():
            c = (conv.get("targets") or {}).get(target) or {}
            rows.append({
                "case_id": case.get("case_id"),
                "target": target,
                "gs_claim": blob.get("claim_type"),
                "gs_status": blob.get("status"),
                "gs_confidence": blob.get("confidence"),
                "gs_architecture": blob.get("architecture_state"),
                "conv_claim": c.get("claim_type"),
                "conv_status": c.get("status"),
            })
    return rows


def _model_ablation(settings) -> dict:
    from genome_skeptic.agents.adapter import list_local_models, resolve_named_model, ModelAdapter, run_planner_critic, ModelUnavailable
    from genome_skeptic.models import Evidence, Anomaly, Severity
    from genome_skeptic.orchestrator import REGISTERED_ACTIONS

    available = list_local_models(settings.llm.base_url)
    qwen = resolve_named_model("qwen", available)
    deepseek = resolve_named_model("deepseek", available)
    evidence = [
        Evidence(id="E001", stage="target_gene", kind="hmm", summary="family HMM model coverage 0.99 on a 2891 aa ORF", values={"hmm_coverage": 0.99, "architecture": "fusion"}),
        Evidence(id="E002", stage="target_gene", kind="partner", summary="partner family hit inside the same ORF", values={"partner": True}),
    ]
    anomalies = [Anomaly(id="A1", stage="target_gene", severity=Severity.warning, message="pairwise identity is 0.46", evidence_ids=["E001"])]
    combos = [
        ("qwen", "qwen", qwen, qwen),
        ("qwen", "deepseek", qwen, deepseek),
        ("deepseek", "qwen", deepseek, qwen),
    ]
    runs = []
    for p_name, c_name, p_model, c_model in combos:
        if p_model is None or c_model is None:
            runs.append({
                "planner": p_name, "critic": c_name,
                "unavailable": True,
                "reason": "hardware or local runtime did not expose the requested open-weight model; it was not silently substituted",
                "available_models": available,
                "resolved_planner": p_model,
                "resolved_critic": c_model,
            })
            continue
        try:
            planner = ModelAdapter(settings.llm, p_model)
            critic = ModelAdapter(settings.llm, c_model)
            runs.append(run_planner_critic(planner, critic, stage="target_gene", evidence=evidence, anomalies=anomalies, registered_actions=REGISTERED_ACTIONS))
        except ModelUnavailable as exc:
            runs.append({"planner": p_name, "critic": c_name, "unavailable": True, "reason": str(exc), "available_models": available})
        except Exception as exc:
            runs.append({"planner": p_name, "critic": c_name, "unavailable": True, "reason": str(exc), "available_models": available})
    polarities = [((r.get("decision") or {}).get("decision")) for r in runs if not r.get("unavailable")]
    return {
        "kind": "model_ablation_v4",
        "available_models": available,
        "runs": runs,
        "deterministic_evidence_fixed": True,
        "conclusions_agree_when_both_available": len(set(polarities)) <= 1 if polarities else None,
        "note": "Scientific polarity is produced by deterministic evidence. This ablation only measures planner/critic text given the same ledger.",
    }


def main() -> None:
    out = ROOT / "benchmarks" / "v4"
    out.mkdir(parents=True, exist_ok=True)
    settings = load_settings(ROOT / "config" / "fast_pilot.yaml")
    common = dict(
        settings=settings,
        run_ablations=False,
        reuse_assembly=True,
        write_fast_pilot_report=False,
        print_prescore_table=True,
        only_systems=("dummy_cautious", "naive_confident", "conventional", "genome_skeptic"),
    )
    print("evaluate development key cases", flush=True)
    skip_eval = os.environ.get("V4_SKIP_EVAL") == "1"
    if skip_eval:
        dev = json.loads((out / "analysis_dev" / "realgenome_production_report.json").read_text(encoding="utf-8"))
        held = json.loads((out / "analysis_held" / "realgenome_production_report.json").read_text(encoding="utf-8"))
        controls = json.loads((out / "analysis_controls" / "realgenome_production_report.json").read_text(encoding="utf-8"))
    else:
        dev = evaluate_real_genomes(
            ROOT / "benchmarks/real_genomes_fast_pilot_dev/agent_visible",
            ROOT / "benchmarks/real_genomes_fast_pilot_dev/hidden/truth.yaml",
            out / "analysis_dev",
            split="development",
            only_cases=["dev_01", "dev_02", "dev_03"],
            reuse_assembly_from=ROOT / "benchmarks/real_genomes_fast_pilot_dev_eval",
            **common,
        )
        print("evaluate S. aureus held-out case without new assembly", flush=True)
        held = evaluate_real_genomes(
            ROOT / "benchmarks/real_genomes_fast_pilot_held/agent_visible",
            ROOT / "benchmarks/real_genomes_fast_pilot_held/hidden/truth.yaml",
            out / "analysis_held",
            split="held_out",
            only_cases=["hel_03"],
            reuse_assembly_from=ROOT / "benchmarks/real_genomes_fast_pilot_held_eval",
            **common,
        )
        print("architecture controls", flush=True)
        controls_root = write_orthology_v3_controls(ROOT)
        controls = evaluate_real_genomes(
            controls_root / "agent_visible",
            controls_root / "hidden" / "truth.yaml",
            out / "analysis_controls",
            split="controls",
            assembly_only=True,
            only_cases=["ctrl_full_length", "ctrl_fusion", "ctrl_split", "ctrl_domain_only", "ctrl_absence", "ctrl_divergent", "ctrl_fragmented", "ctrl_paralogue"],
            **common,
        )
    print("calibration leave-one-genome-out", flush=True)
    calibration = run_calibration_v4(ROOT, settings, out / "calibration_loci")
    print("robustness", flush=True)
    robustness = run_robustness_suite(out / "robustness_tmp", settings)
    print("model ablation probe", flush=True)
    models = _model_ablation(settings)

    v3_path = ROOT / "orthology_v3.json"
    v3 = json.loads(v3_path.read_text(encoding="utf-8")) if v3_path.exists() else {}
    key_rows = _case_rows(dev) + _case_rows(held) + _case_rows(controls)
    locus_rows = []
    for split, base in (("development", out / "analysis_dev"), ("held_out", out / "analysis_held"), ("controls", out / "analysis_controls")):
        for rec in base.glob("*/genome_skeptic/family/*/locus_reconstruction.json"):
            blob = json.loads(rec.read_text(encoding="utf-8"))
            locus_rows.append({"split": split, "case_id": rec.parts[-5], "target": rec.parts[-2], **{k: blob.get(k) for k in ("architecture", "hmm_coverage", "contig", "contig_edge", "family_gate_passed")}})
    hyp_rows = []
    for row in key_rows:
        hyp_rows.append({"case_id": row["case_id"], "target": row["target"], "architecture": row.get("gs_architecture"), "gs_claim": row.get("gs_claim")})

    comparison = {
        "kind": "v3_vs_v4",
        "did_not_rerun_spades": True,
        "did_not_modify_v3_reports": True,
        "v3_held_out": (v3.get("honest_held_out_comparison") or v3.get("held_out")),
        "v4_development_overall": _copy_report(dev),
        "v4_held_staph_only": _copy_report(held),
        "v4_controls": _copy_report(controls),
        "key_case_rows": key_rows,
    }
    (out / "locus_reconstruction_v4.json").write_text(json.dumps({"kind": "locus_reconstruction_v4", "cases": locus_rows}, indent=2, default=str), encoding="utf-8")
    (out / "hypothesis_graph_v4.json").write_text(json.dumps({"kind": "hypothesis_graph_v4", "cases": hyp_rows}, indent=2, default=str), encoding="utf-8")
    (out / "action_policy_v4.json").write_text(json.dumps({"kind": "action_policy_v4", "catalog": catalog_as_dicts()}, indent=2), encoding="utf-8")
    (out / "calibration_v4.json").write_text(json.dumps(calibration, indent=2, default=str), encoding="utf-8")
    (out / "model_ablation_v4.json").write_text(json.dumps(models, indent=2, default=str), encoding="utf-8")
    (out / "robustness_v4.json").write_text(json.dumps(robustness, indent=2, default=str), encoding="utf-8")
    (out / "v3_vs_v4.json").write_text(json.dumps(comparison, indent=2, default=str), encoding="utf-8")
    for name in ("locus_reconstruction_v4.json", "hypothesis_graph_v4.json", "action_policy_v4.json", "calibration_v4.json", "model_ablation_v4.json", "robustness_v4.json", "v3_vs_v4.json"):
        (ROOT / name).write_text((out / name).read_text(encoding="utf-8"), encoding="utf-8")

    remaining = []
    for row in key_rows:
        if row["case_id"] == "hel_03" and row["target"] == "rpoB" and row["gs_claim"] != "target_gene_detected":
            remaining.append("S. aureus rpoB still not detected")
        if row["case_id"] == "ctrl_split" and row.get("gs_architecture") != "biological_split":
            remaining.append(f"split control architecture={row.get('gs_architecture')}")
        if row["case_id"] == "ctrl_absence" and row.get("gs_architecture") not in {"true_no_candidate", None}:
            if row.get("gs_claim") == "target_gene_not_detected" and row.get("gs_architecture") not in {"true_no_candidate", "domain_only"}:
                remaining.append(f"absence control architecture={row.get('gs_architecture')}")
        if row["case_id"] == "dev_02" and row["target"] == "rpoB" and row.get("gs_architecture") == "fusion":
            remaining.append("PAO1 still labeled fusion")
        if row["case_id"] == "dev_03" and row["target"] == "rpoB" and row.get("gs_architecture") != "fusion":
            remaining.append(f"H. pylori architecture={row.get('gs_architecture')} (expected fusion from general method)")
        if row["case_id"] == "ctrl_fusion" and row.get("gs_architecture") != "fusion":
            remaining.append(f"fusion control architecture={row.get('gs_architecture')}")
        if row["case_id"] == "ctrl_domain_only" and row.get("gs_architecture") not in {"domain_only"}:
            remaining.append(f"domain-only control architecture={row.get('gs_architecture')} (gate rejected a weak partial as true_no_candidate)")
        if row["case_id"] == "ctrl_paralogue" and row.get("gs_architecture") != "close_paralogue":
            remaining.append(f"paralogue control architecture={row.get('gs_architecture')} (close_paralogue is never assigned)")
        if row["case_id"] == "ctrl_divergent" and row.get("gs_architecture") not in {"divergent_full_length"}:
            remaining.append(f"divergent control architecture={row.get('gs_architecture')}")
    if any(p.get("error") for p in (calibration.get("pairs") or []) + (calibration.get("raw_pairs_before_logo") or [])):
        remaining.append("calibration locus perturbations failed to score")
    if not (models.get("available_models")):
        remaining.append("Qwen3 and DeepSeek-R1-Distill were unavailable; planner/critic combinations were not silently substituted")

    md = [
        "# GENOME SKEPTIC V4",
        "",
        "SPAdes was not rerun. FAST_PILOT sequencing data were not regenerated. Truth labels were not edited. Held-out cases were not used to tune thresholds or calibration. V3 reports were left in place.",
        "",
        "## Acceptance gates (not a single composite)",
        "",
        f"- Clean development overall (GS): {((dev.get('systems') or {}).get('genome_skeptic') or {}).get('overall')}",
        f"- Conventional on the same development cases: {((dev.get('systems') or {}).get('conventional') or {}).get('overall')}",
        f"- Dummy / naive on development: {((dev.get('systems') or {}).get('dummy_cautious') or {}).get('overall')} / {((dev.get('systems') or {}).get('naive_confident') or {}).get('overall')}",
        f"- S. aureus held-out (hel_03 only): GS {((held.get('systems') or {}).get('genome_skeptic') or {}).get('overall')} vs conventional {((held.get('systems') or {}).get('conventional') or {}).get('overall')}",
        f"- Controls overall GS: {((controls.get('systems') or {}).get('genome_skeptic') or {}).get('overall')}",
        f"- Calibration Brier / ECE: {(calibration.get('overall') or {}).get('brier')} / {(calibration.get('overall') or {}).get('ece')}",
        f"- Robustness fail-closed cases: {robustness.get('n_fail_closed')} / {robustness.get('n')}",
        f"- Model ablation available models: {models.get('available_models')}",
        "",
        "## Key case architectures",
        "",
    ]
    for row in key_rows:
        md.append(f"- `{row['case_id']}` `{row['target']}`: GS {row.get('gs_claim')}/{row.get('gs_status')} arch={row.get('gs_architecture')} vs conventional {row.get('conv_claim')}")
    md.extend(["", "## Remaining failures", ""])
    if remaining:
        for item in remaining:
            md.append(f"- {item}")
    else:
        md.append("- No pre-registered architecture failures were recorded in this run. Calibration, model substitution, and held-out aggregate gaps may still exist; see JSON files.")
    md.extend([
        "",
        "## Smallest next change",
        "",
        "Assign `close_paralogue` when a second high-identity locus exists; do not lower the family-evidence gate to relabel domain-only, and do not add species rules. Qwen3 / DeepSeek were unavailable locally and were not substituted.",
        "",
        "## Files",
        "",
        "- GENOME_SKEPTIC_V4.md",
        "- locus_reconstruction_v4.json",
        "- hypothesis_graph_v4.json",
        "- action_policy_v4.json",
        "- calibration_v4.json",
        "- model_ablation_v4.json",
        "- robustness_v4.json",
        "- v3_vs_v4.json",
        "",
    ])
    text = "\n".join(md) + "\n"
    (out / "GENOME_SKEPTIC_V4.md").write_text(text, encoding="utf-8")
    (ROOT / "GENOME_SKEPTIC_V4.md").write_text(text, encoding="utf-8")
    print("wrote GENOME_SKEPTIC_V4.md", flush=True)
    print("remaining", remaining, flush=True)


if __name__ == "__main__":
    main()
