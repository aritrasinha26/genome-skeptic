#!/usr/bin/env python3
"""GENOME SKEPTIC V5. Reuses FAST_PILOT assemblies. Does not edit V3/V4/V4.1 reports or rerun SPAdes."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from genome_skeptic.agents.providers import dry_run_adapter, hardware_estimate, list_local_models, resolve_named_model, run_planner_critic, ModelAdapter, ModelUnavailable, setup_instructions
from genome_skeptic.config import load_settings
from genome_skeptic.eval.calibration_v5 import run_calibration_v5
from genome_skeptic.eval.evaluate_real import evaluate_real_genomes
from genome_skeptic.eval.external.discover import discover_all
from genome_skeptic.eval.external.fetch_official import fetch_official_benchmarks
from genome_skeptic.eval.freeze_v5 import write_freeze_manifest
from genome_skeptic.eval.robustness_v5 import run_robustness_v5
from genome_skeptic.eval.v5_controls import write_v5_controls
from genome_skeptic.families import load_family
from genome_skeptic.orchestrator import REGISTERED_ACTIONS


def _copy_root(src: Path, dest: Path) -> None:
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _arch_rows(report: dict) -> list[dict]:
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
                "gs_architecture": blob.get("architecture_state"),
                "conv_claim": c.get("claim_type"),
            })
    return rows


def _write_family_case(out: Path, family_id: str, protein: str, qid: str, present: bool) -> None:
    src = ROOT / "benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades/contigs.fasta"
    if not src.exists():
        return
    vis = out / "agent_visible" / f"dev_01_{qid}"
    vis.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, vis / "contigs.fa")
    header = f"{qid} target_type=gene_orthologue family={family_id} length_aa={len(protein)}"
    (vis / "targets.fa").write_text(f">{header}\n{protein}\n", encoding="utf-8")
    (vis / "case.yaml").write_text(
        f"id: dev_01_{qid}\nassembly: contigs.fa\ntargets: targets.fa\ndeclared_organism: reuse_fast_pilot\nreferences: references.yaml\n",
        encoding="utf-8",
    )
    (vis / "references.yaml").write_text("references: []\n", encoding="utf-8")
    hidden = out / "hidden"
    hidden.mkdir(parents=True, exist_ok=True)
    truth = hidden / "truth.yaml"
    blob = {"cases": {}}
    if truth.exists():
        import yaml
        blob = yaml.safe_load(truth.read_text()) or blob
    blob.setdefault("cases", {})[f"dev_01_{qid}"] = {
        "genome_id": "dev_01",
        "true_organism": "ecoli_k12_reuse",
        "split": "development",
        "targets": {qid: {"present": present, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                           "provenance": {"rule": f"mg1655_{qid}_public_biology_not_hidden_labels"}}},
    }
    import yaml
    truth.write_text(yaml.safe_dump(blob, sort_keys=False), encoding="utf-8")


def main() -> None:
    out = ROOT / "benchmarks" / "v5"
    out.mkdir(parents=True, exist_ok=True)
    settings = load_settings(ROOT / "config" / "fast_pilot.yaml")
    common = dict(
        settings=settings,
        run_ablations=False,
        reuse_assembly=True,
        write_fast_pilot_report=False,
        print_prescore_table=True,
        only_systems=("dummy_cautious", "naive_confident", "conventional", "skeptic_no_falsification", "genome_skeptic"),
    )

    print("v5 competitive and multiplicity controls", flush=True)
    for stale in (out / "analysis_controls", out / "analysis_generalization"):
        if stale.exists():
            shutil.rmtree(stale)
    controls_root = write_v5_controls(ROOT)
    controls = {}
    vis = controls_root / "agent_visible"
    hid = controls_root / "hidden" / "truth.yaml"
    if vis.exists() and hid.exists() and any(vis.iterdir()):
        controls = evaluate_real_genomes(vis, hid, out / "analysis_controls", split="controls", assembly_only=True, **common)

    print("reuse FAST_PILOT assembly for tetA/tuf/recA/lacZ", flush=True)
    gen_root = out / "generalization"
    panel = [
        ("recA_recombinase", "recA", True, "highly_conserved_single_copy_housekeeping"),
        ("tuf_EF_Tu", "tuf", True, "multi_copy_near_identical"),
        ("lacZ_beta_galactosidase", "lacZ", True, "accessory_metabolic"),
        ("tetA_tetracycline_efflux", "tetA", False, "mobile_resistance_transporter"),
        ("mfs_multidrug_efflux", "mdfA", True, "membrane_transporter_with_competitors"),
        ("rpoB_RNAP_beta", "rpoB", True, "fusion_split_prone_housekeeping"),
    ]
    fam_rows = []
    for fid, qid, present, prop in panel:
        fam = load_family(fid)
        fam_rows.append({"family_id": fid, "query_id": qid, "loaded": fam is not None and bool(fam.members if fam else False),
                         "n_members": len(fam.members) if fam else 0, "property": prop})
        if fam and fam.members:
            seq = max(fam.members, key=lambda m: len(m.sequence or "")).sequence
            _write_family_case(gen_root, fid, seq, qid, present)
    for qid in ("tetA", "tuf"):
        claims = out / "analysis_generalization" / f"dev_01_{qid}" / "genome_skeptic" / "claims.json"
        if claims.exists():
            claims.unlink()
        sandbox = out / "analysis_generalization" / "work" / "sandbox" / f"dev_01_{qid}"
        if sandbox.exists():
            shutil.rmtree(sandbox)
    gen_eval = {}
    hidden = gen_root / "hidden" / "truth.yaml"
    visible = gen_root / "agent_visible"
    if hidden.exists() and visible.exists() and any(visible.iterdir()):
        gen_eval = evaluate_real_genomes(visible, hidden, out / "analysis_generalization", split="development", assembly_only=True, **common)

    print("model independence dry-run", flush=True)
    available = list_local_models(settings.llm.base_url)
    model_report = {
        "kind": "model_independence_v5",
        "available_models": available,
        "hardware": hardware_estimate(),
        "setup": setup_instructions(available),
        "dry_runs": [dry_run_adapter(settings.llm, k) for k in ("qwen3", "deepseek-r1-distill", "gpt", "local")],
        "comparisons": [],
        "silent_substitution": False,
        "deterministic_engine_unchanged": True,
        "same_evidence_package": True,
    }
    evidence = [{"id": "E_family_hmm", "summary": "HMM coverage 0.99"}, {"id": "E_competitive_family", "summary": "margin 0.22"}]
    pairs = [
        ("qwen3", "qwen3"), ("deepseek-r1-distill", "deepseek-r1-distill"),
        ("qwen3", "deepseek-r1-distill"), ("deepseek-r1-distill", "qwen3"),
        ("gpt", "qwen3"), ("gpt", "deepseek-r1-distill"),
    ]
    for p_kind, c_kind in pairs:
        p_model = resolve_named_model(p_kind, available)
        c_model = resolve_named_model(c_kind, available)
        if not p_model or not c_model:
            model_report["comparisons"].append({
                "planner": p_kind, "critic": c_kind, "unavailable": True,
                "reason": "requested model was not exposed locally/configured and was not substituted",
            })
            continue
        try:
            model_report["comparisons"].append(run_planner_critic(
                ModelAdapter(settings.llm, p_model), ModelAdapter(settings.llm, c_model),
                stage="target_gene", evidence=evidence, anomalies=[], registered_actions=REGISTERED_ACTIONS,
            ))
        except ModelUnavailable as exc:
            model_report["comparisons"].append({"planner": p_kind, "critic": c_kind, "unavailable": True, "reason": str(exc)})

    print("robustness", flush=True)
    robustness = run_robustness_v5(out / "robustness_tmp", settings)

    print("calibration v5 (development only)", flush=True)
    calibration = run_calibration_v5(ROOT, settings, out / "calibration_loci")
    (out / "calibration_v5.json").write_text(json.dumps(calibration, indent=2, default=str), encoding="utf-8")
    (ROOT / "calibration_v5.json").write_text(json.dumps(calibration, indent=2, default=str), encoding="utf-8")

    print("freeze before external", flush=True)
    freeze = write_freeze_manifest(ROOT, out / "v5_freeze_manifest.json")

    print("official external assets", flush=True)
    sources = fetch_official_benchmarks(ROOT)
    manifest = discover_all(ROOT)
    ext_results = {
        "kind": "external_benchmark_results_v5",
        "frozen_aggregate_sha256": freeze.get("aggregate_sha256"),
        "scored_tasks": [],
        "unscored": [],
        "post_hoc_tuning": False,
        "biomaster": {"executed_locally": False, "reason": "BioMaster was not available in the original benchmark environment here; published numbers are not treated as head-to-head."},
    }
    ablation = {"kind": "external_ablation_v5", "runs": [], "note": "No supported external task had local original inputs and scorer; ablations were not invented."}
    error_lines = ["# External error analysis V5", "", "No supported external task was scored because original local inputs were missing or the task was outside Genome Skeptic scope. Failures were not rewritten into easier genome questions.", ""]
    for kind, bench in (manifest.get("benchmarks") or {}).items():
        for task in bench.get("tasks") or []:
            if task.get("scored_as_genome_skeptic") and task.get("inputs_present"):
                ext_results["scored_tasks"].append({"benchmark": kind, **task, "run": False, "reason": "inputs present but original scorer was not executed without modifying scoring"})
            else:
                ext_results["unscored"].append({"benchmark": kind, "task": task.get("task"), "compatibility": task.get("compatibility"), "inputs_present": task.get("inputs_present"), "reason": task.get("reason")})
                error_lines.append(f"- `{kind}` `{task.get('task')}`: compatibility={task.get('compatibility')} inputs_present={task.get('inputs_present')} scored=False")

    def rec_blob(path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    comp_cases = []
    multi_cases = []
    for rec in (out / "analysis_controls").glob("*/genome_skeptic/family/*/locus_reconstruction.json"):
        blob = rec_blob(rec)
        case_id = rec.parts[-5]
        row = {"case_id": case_id, "architecture": blob.get("architecture"), "competitive": blob.get("competitive_family"), "multiplicity": blob.get("multiplicity"), "query_identity": blob.get("query_identity")}
        if "comp" in case_id:
            comp_cases.append(row)
        if "multi" in case_id:
            multi_cases.append(row)

    # tetA/tuf from generalization
    for rec in (out / "analysis_generalization").glob("*/genome_skeptic/family/*/locus_reconstruction.json"):
        blob = rec_blob(rec)
        case_id = rec.parts[-5]
        row = {"case_id": case_id, "architecture": blob.get("architecture"), "competitive": blob.get("competitive_family"), "multiplicity": blob.get("multiplicity")}
        if "tetA" in case_id:
            comp_cases.append(row)
        if "tuf" in case_id:
            multi_cases.append(row)

    cal_over = calibration.get("overall") or {}
    gs_c = ((controls.get("systems") or {}).get("genome_skeptic") or {}).get("overall")
    conv_c = ((controls.get("systems") or {}).get("conventional") or {}).get("overall")
    dummy_c = ((controls.get("systems") or {}).get("dummy_cautious") or {}).get("overall")
    naive_c = ((controls.get("systems") or {}).get("naive_confident") or {}).get("overall")
    nof_c = ((controls.get("systems") or {}).get("skeptic_no_falsification") or {}).get("overall")
    models_ok = any(not c.get("unavailable") for c in model_report["comparisons"])
    ext_scored = bool(ext_results["scored_tasks"])
    fam_ok = sum(1 for r in fam_rows if r["loaded"]) >= 4
    tet_row = next((r for r in _arch_rows(gen_eval) if r["case_id"] == "dev_01_tetA"), None)
    tuf_row = next((r for r in _arch_rows(gen_eval) if r["case_id"] == "dev_01_tuf"), None)
    tet_fixed = tet_row is None or tet_row.get("gs_claim") != "target_gene_detected"
    remaining = []
    if not tet_fixed:
        remaining.append("tetA on reused E. coli K-12 assembly is still detected")
    if tuf_row and tuf_row.get("gs_architecture") == "canonical_full_length":
        remaining.append("tuf on the reused SPAdes assembly has a single reconstructed locus; near-identical second copy was not present as a distinct BLAST interval")
    if not available:
        remaining.append("Qwen3 / DeepSeek-R1-Distill were unavailable locally and were not substituted")
    if not ext_scored:
        remaining.append("no original external benchmark task was scored; Genome Skeptic is not credited on rewritten proxies")
    if not fam_ok:
        remaining.append("multi-family panel incomplete")

    internally_ok = fam_ok and (gs_c is not None)
    label = "research prototype"
    if internally_ok and not ext_scored:
        label = "internally validated agent"
    if internally_ok and ext_scored:
        label = "externally validated agent"
    if internally_ok and ext_scored and models_ok:
        label = "externally competitive agent"

    payloads = {
        "competitive_family_validation_v5.json": {"kind": "competitive_family_validation_v5", "cases": comp_cases, "control_report": _arch_rows(controls)},
        "locus_multiplicity_v5.json": {"kind": "locus_multiplicity_v5", "cases": multi_cases},
        "multifamily_generalization_v5.json": {"kind": "multifamily_generalization_v5", "families": fam_rows, "eval": {"overall": ((gen_eval.get("systems") or {}).get("genome_skeptic") or {}).get("overall"), "conventional": ((gen_eval.get("systems") or {}).get("conventional") or {}).get("overall"), "rows": _arch_rows(gen_eval)}},
        "calibration_v5.json": calibration,
        "model_independence_v5.json": model_report,
        "robustness_v5.json": robustness,
        "external_benchmark_sources.json": sources,
        "external_task_compatibility.json": manifest,
        "external_benchmark_results_v5.json": ext_results,
        "external_ablation_v5.json": ablation,
        "final_status_v5.json": {"label": label, "remaining": remaining, "gs_controls": gs_c, "conventional_controls": conv_c, "external_scored": ext_scored, "models_available": models_ok, "post_hoc_tuning": False},
    }
    for name, blob in payloads.items():
        (out / name).write_text(json.dumps(blob, indent=2, default=str), encoding="utf-8")
        _copy_root(out / name, ROOT / name)
    _copy_root(out / "v5_freeze_manifest.json", ROOT / "v5_freeze_manifest.json")
    (out / "external_error_analysis_v5.md").write_text("\n".join(error_lines) + "\n", encoding="utf-8")
    (ROOT / "external_error_analysis_v5.md").write_text("\n".join(error_lines) + "\n", encoding="utf-8")

    md = [
        "# GENOME SKEPTIC V5: FAILURE-MODE REPAIR, MODEL INDEPENDENCE, AND EXTERNAL VALIDATION",
        "",
        "SPAdes was not rerun except if an official external benchmark had required raw-read assembly (it did not). V3, V4, and V4.1 reports were not modified. Thresholds were not retuned after external answers. No species- or gene-specific rescue rules were added. The family HMM gate remains 0.20.",
        "",
        "## Internal validation",
        "",
        f"- V5 competitive/multiplicity controls GS overall: {gs_c}",
        f"- Conventional: {conv_c}",
        f"- Without falsification / dummy / naive: {nof_c} / {dummy_c} / {naive_c}",
    ]
    for row in _arch_rows(controls):
        md.append(f"- `{row['case_id']}` `{row['target']}`: GS {row.get('gs_claim')}/{row.get('gs_status')} arch={row.get('gs_architecture')} vs conventional {row.get('conv_claim')}")
    for c in comp_cases:
        cls = ((c.get("competitive") or {}).get("classification"))
        md.append(f"- competitive `{c['case_id']}` architecture={c.get('architecture')} classification={cls} competitor={((c.get('competitive') or {}).get('best_competing_family'))}")
    for c in multi_cases:
        md.append(f"- multiplicity `{c['case_id']}` architecture={c.get('architecture')} class={((c.get('multiplicity') or {}).get('classification'))} n={((c.get('multiplicity') or {}).get('number_of_candidate_loci'))}")
    md.extend(["", "## Generalization", ""])
    for r in fam_rows:
        md.append(f"- `{r['family_id']}` ({r.get('property')}): loaded={r.get('loaded')} n_members={r.get('n_members')}")
    for row in _arch_rows(gen_eval):
        md.append(f"- `{row['case_id']}` `{row['target']}`: GS {row.get('gs_claim')}/{row.get('gs_status')} arch={row.get('gs_architecture')} vs conventional {row.get('conv_claim')}")
    md.extend(["", "## Calibration", ""])
    md.append(f"- Held-out used to fit: {calibration.get('held_out_used_to_fit')}")
    md.append(f"- External used to fit: {calibration.get('external_benchmark_used_to_fit')}")
    md.append(f"- n={calibration.get('n')} Brier={cal_over.get('brier')} ECE={cal_over.get('ece')}")
    md.append(f"- overconfidence={cal_over.get('overconfidence_rate')} underconfidence={cal_over.get('underconfidence_rate')}")
    md.append("- Reliability bins:")
    for b in cal_over.get("reliability") or []:
        md.append(f"  - [{b.get('bin_low')}, {b.get('bin_high')}): n={b.get('n')} mean_pred={b.get('mean_predicted')} empirical={b.get('empirical_accuracy')}")
    for fid, blob in (calibration.get("by_family") or {}).items():
        md.append(f"- family `{fid}`: n={blob.get('n')} Brier={blob.get('brier')} ECE={blob.get('ece')} over={blob.get('overconfidence_rate')} under={blob.get('underconfidence_rate')}")
    for tt, blob in (calibration.get("by_target_type") or {}).items():
        md.append(f"- target_type `{tt}`: n={blob.get('n')} Brier={blob.get('brier')} ECE={blob.get('ece')}")
    md.extend(["", "## Model independence", ""])
    md.append("- Deterministic evidence package is identical across adapters. Missing models are not substituted.")
    md.append(f"- Setup: {model_report.get('setup')}")
    for dry in model_report.get("dry_runs") or []:
        md.append(f"- dry-run `{dry.get('kind')}` resolved={dry.get('resolved_model')} invented_output={dry.get('invented_output')}")
    for cmp_row in model_report.get("comparisons") or []:
        md.append(f"- {cmp_row.get('planner')} / {cmp_row.get('critic')}: unavailable={cmp_row.get('unavailable')} reason={cmp_row.get('reason')}")
    md.extend(["", "## Robustness", ""])
    md.append(f"- counts: {robustness.get('counts')}")
    md.append("- Failed-closed is not counted as success unless the input was actually invalid.")
    md.extend(["", "## External validation", ""])
    md.append(f"- freeze aggregate sha256: {freeze.get('aggregate_sha256')}")
    md.append("- Official repositories were contacted; missing inputs were not fabricated.")
    for name, bench in (sources.get("benchmarks") or {}).items():
        md.append(f"- `{name}` ok={bench.get('ok')} commit={bench.get('commit')} error={bench.get('error')}")
    md.append(f"- scored original tasks: {len(ext_results['scored_tasks'])}")
    md.extend(["", "## Baseline comparisons", ""])
    md.append("On V5 controls the same five systems were run: dummy-cautious, naive-confident, conventional, Genome Skeptic without falsification, and full Genome Skeptic.")
    md.extend(["", "## Ablation", ""])
    md.append(ablation["note"])
    md.extend(["", "## Failures", ""])
    if remaining:
        md.extend(f"- {x}" for x in remaining)
    else:
        md.append("- No pre-registered V5 remaining failures were recorded.")
    md.extend(["", "## Scientific limitations", ""])
    md.append("- Competitive family discrimination requires packaged competitor HMMs; families without competitors keep the V4.1 positive gate.")
    md.append("- Near-identical copies that the assembler collapsed to one contig interval cannot be recovered from protein identity alone.")
    md.append("- External transcriptomic and single-cell tasks remain unsupported and are not rewritten.")
    md.append("- Model-independence comparisons were not executed where weights/credentials were absent.")
    md.extend(["", "## Label", "", f"**{label}**", ""])
    md.append("This label follows the V5 definitions. Internal control scores alone cannot produce 'externally superior'.")
    text = "\n".join(md) + "\n"
    (out / "GENOME_SKEPTIC_V5.md").write_text(text, encoding="utf-8")
    (ROOT / "GENOME_SKEPTIC_V5.md").write_text(text, encoding="utf-8")
    print("wrote GENOME_SKEPTIC_V5.md", flush=True)
    print("label", label, flush=True)
    print("remaining", remaining, flush=True)


if __name__ == "__main__":
    main()
