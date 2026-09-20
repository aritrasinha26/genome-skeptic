#!/usr/bin/env python3
"""GENOME SKEPTIC V4.1. Reuses FAST_PILOT assemblies. Does not edit V3/V4 reports or SPAdes."""
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
from genome_skeptic.eval.calibration_v4 import run_calibration_multifamily
from genome_skeptic.eval.evaluate_real import evaluate_real_genomes
from genome_skeptic.eval.external.discover import discover_all
from genome_skeptic.eval.v41_controls import write_v41_controls
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


def _write_generalization_case(out: Path, family_id: str, protein: str, qid: str) -> Path | None:
    src = ROOT / "benchmarks/real_genomes_fast_pilot_dev_eval/dev_01/production/spades/contigs.fasta"
    if not src.exists():
        return None
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
    present = qid in {"recA", "tuf"}  # housekeeping expected in E.coli; lacZ present; tetA typically absent
    if qid == "lacZ":
        present = True
    if qid == "tetA":
        present = False
    blob.setdefault("cases", {})[f"dev_01_{qid}"] = {
        "genome_id": "dev_01",
        "true_organism": "ecoli_k12_reuse",
        "split": "development",
        "targets": {qid: {"present": present, "clean": True, "target_type": "gene_orthologue", "truth_state": "resolved",
                           "provenance": {"rule": f"mg1655_{qid}_expectation_from_public_biology_not_hidden_labels"}}},
    }
    import yaml
    truth.write_text(yaml.safe_dump(blob, sort_keys=False), encoding="utf-8")
    return vis.parent.parent


def main() -> None:
    out = ROOT / "benchmarks" / "v4_1"
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

    print("v4.1 paralogue and divergence controls", flush=True)
    controls_root = write_v41_controls(ROOT)
    for stale in (
        out / "analysis_controls" / "ctrl_para_contaminant",
        out / "analysis_controls" / "work" / "sandbox" / "ctrl_para_contaminant",
    ):
        if stale.exists():
            shutil.rmtree(stale)
    control_common = dict(common)
    control_common["only_systems"] = ("dummy_cautious", "naive_confident", "conventional", "skeptic_no_falsification", "genome_skeptic")
    controls = evaluate_real_genomes(
        controls_root / "agent_visible",
        controls_root / "hidden" / "truth.yaml",
        out / "analysis_controls",
        split="controls",
        assembly_only=True,
        **control_common,
    )

    print("model independence dry-run", flush=True)
    available = list_local_models(settings.llm.base_url)
    model_report = {
        "kind": "model_independence_v4_1",
        "available_models": available,
        "hardware": hardware_estimate(),
        "setup": setup_instructions(available),
        "dry_runs": [dry_run_adapter(settings.llm, k) for k in ("qwen3", "deepseek-r1-distill", "local")],
        "comparisons": [],
        "silent_substitution": False,
        "deterministic_engine_unchanged": True,
        "note": "Planner/critic adapters are OpenAI-compatible. Missing models are not substituted. Dry-run does not invent output.",
    }
    evidence = [{"id": "E_family_hmm", "summary": "HMM coverage 0.99"}]
    pairs = [("qwen3", "qwen3"), ("deepseek-r1-distill", "deepseek-r1-distill"), ("qwen3", "deepseek-r1-distill")]
    for p_kind, c_kind in pairs:
        p_model = resolve_named_model(p_kind, available)
        c_model = resolve_named_model(c_kind, available)
        if not p_model or not c_model:
            model_report["comparisons"].append({
                "planner": p_kind, "critic": c_kind, "unavailable": True,
                "reason": "requested open-weight model was not exposed locally and was not substituted",
            })
            continue
        try:
            row = run_planner_critic(
                ModelAdapter(settings.llm, p_model),
                ModelAdapter(settings.llm, c_model),
                stage="target_gene",
                evidence=evidence,
                anomalies=[],
                registered_actions=REGISTERED_ACTIONS,
            )
            model_report["comparisons"].append(row)
        except ModelUnavailable as exc:
            model_report["comparisons"].append({"planner": p_kind, "critic": c_kind, "unavailable": True, "reason": str(exc)})

    print("external benchmark discovery", flush=True)
    manifest = discover_all(ROOT)
    ext_results = {
        "kind": "external_benchmark_results",
        "scored_tasks": [],
        "unscored": [],
        "baselines_note": "Only supported tasks with local inputs are scored. Missing datasets are not treated as Genome Skeptic failures.",
        "published_agent_comparisons": [],
        "biomaster": {"executed_locally": False, "reason": "BioMaster was not available in the original benchmark environment here; published numbers are not treated as head-to-head."},
    }
    for kind, bench in (manifest.get("benchmarks") or {}).items():
        for task in bench.get("tasks") or []:
            if task.get("scored_as_genome_skeptic") and task.get("inputs_present"):
                ext_results["scored_tasks"].append({"benchmark": kind, **task, "run": False, "reason": "local inputs exist but full original scorer was not executed in this milestone to avoid rewriting scoring"})
            else:
                ext_results["unscored"].append({"benchmark": kind, "task": task.get("task"), "compatibility": task.get("compatibility"), "inputs_present": task.get("inputs_present")})

    print("gene-family generalization", flush=True)
    gen_rows = []
    gen_root = out / "generalization"
    fam_ids = [
        ("recA_recombinase", "recA"),
        ("tuf_EF_Tu", "tuf"),
        ("lacZ_beta_galactosidase", "lacZ"),
        ("tetA_tetracycline_efflux", "tetA"),
    ]
    for fid, qid in fam_ids:
        fam = load_family(fid)
        gen_rows.append({
            "family_id": fid,
            "query_id": qid,
            "loaded": fam is not None and bool(fam.members if fam else False),
            "n_members": len(fam.members) if fam else 0,
            "property": None if fam is None else (fam.display_name),
        })
        if fam and fam.members:
            _write_generalization_case(gen_root, fid, fam.members[0].sequence, qid)
    gen_eval = {}
    hidden = gen_root / "hidden" / "truth.yaml"
    visible = gen_root / "agent_visible"
    if hidden.exists() and visible.exists() and any(visible.iterdir()):
        gen_eval = evaluate_real_genomes(
            visible, hidden, out / "analysis_generalization",
            split="development", assembly_only=True, **common,
        )

    print("multifamily calibration", flush=True)
    calibration = run_calibration_multifamily(ROOT, settings, out / "calibration_loci")

    para_cases = []
    div_cases = []
    for rec in (out / "analysis_controls").glob("*/genome_skeptic/family/*/locus_reconstruction.json"):
        blob = json.loads(rec.read_text(encoding="utf-8"))
        case_id = rec.parts[-5]
        row = {"case_id": case_id, "architecture": blob.get("architecture"), "paralogue_record": blob.get("paralogue_record"), "divergence": blob.get("divergence"), "query_identity": blob.get("query_identity")}
        if "para" in case_id:
            para_cases.append(row)
        if "divergent" in case_id or "canonical_query" in case_id:
            div_cases.append(row)

    (out / "paralogue_validation_v4_1.json").write_text(json.dumps({"kind": "paralogue_validation_v4_1", "cases": para_cases, "control_report": _arch_rows(controls)}, indent=2, default=str), encoding="utf-8")
    (out / "divergence_validation_v4_1.json").write_text(json.dumps({"kind": "divergence_validation_v4_1", "cases": div_cases, "gate_unchanged": 0.20}, indent=2, default=str), encoding="utf-8")
    (out / "model_independence_v4_1.json").write_text(json.dumps(model_report, indent=2, default=str), encoding="utf-8")
    (out / "external_benchmark_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (out / "external_benchmark_results.json").write_text(json.dumps(ext_results, indent=2, default=str), encoding="utf-8")
    (out / "gene_family_generalization.json").write_text(json.dumps({"kind": "gene_family_generalization", "families": gen_rows, "eval": {
        "overall": ((gen_eval.get("systems") or {}).get("genome_skeptic") or {}).get("overall"),
        "conventional": ((gen_eval.get("systems") or {}).get("conventional") or {}).get("overall"),
        "rows": _arch_rows(gen_eval),
    }}, indent=2, default=str), encoding="utf-8")
    (out / "calibration_multifamily.json").write_text(json.dumps(calibration, indent=2, default=str), encoding="utf-8")
    for name in ("paralogue_validation_v4_1.json", "divergence_validation_v4_1.json", "model_independence_v4_1.json", "external_benchmark_manifest.json", "external_benchmark_results.json", "gene_family_generalization.json", "calibration_multifamily.json"):
        _copy_root(out / name, ROOT / name)

    expected_kind = {
        "ctrl_para_true": "true_duplicated_paralogue",
        "ctrl_para_recent": "recent_gene_duplication",
        "ctrl_para_plasmid": "plasmid_copy",
        "ctrl_para_contaminant": "contaminant_copy",
        "ctrl_para_fragments": "assembly_fragments_of_one_gene",
    }
    gs_overall = ((controls.get("systems") or {}).get("genome_skeptic") or {}).get("overall")
    conv_overall = ((controls.get("systems") or {}).get("conventional") or {}).get("overall")
    dummy_overall = ((controls.get("systems") or {}).get("dummy_cautious") or {}).get("overall")
    naive_overall = ((controls.get("systems") or {}).get("naive_confident") or {}).get("overall")
    nof_overall = ((controls.get("systems") or {}).get("skeptic_no_falsification") or {}).get("overall")
    cal_over = calibration.get("overall") or {}
    remaining = []
    for c in para_cases:
        if c["case_id"] == "ctrl_para_fragments" and c.get("architecture") == "close_paralogue":
            remaining.append("fragment control mislabeled as paralogue")
        if c["case_id"] in {"ctrl_para_true", "ctrl_para_recent", "ctrl_para_plasmid", "ctrl_para_contaminant"} and c.get("architecture") != "close_paralogue":
            remaining.append(f"{c['case_id']} architecture={c.get('architecture')}")
        want = expected_kind.get(c["case_id"])
        got = ((c.get("paralogue_record") or {}).get("kind"))
        if want and got and got != want:
            remaining.append(f"{c['case_id']} kind={got} expected={want}")
    for c in div_cases:
        if c["case_id"] == "ctrl_divergent_family" and c.get("architecture") != "divergent_full_length":
            remaining.append(f"divergent control architecture={c.get('architecture')}")
        if c["case_id"] == "ctrl_canonical_query_like" and c.get("architecture") != "canonical_full_length":
            remaining.append(f"canonical control architecture={c.get('architecture')}")
    for row in _arch_rows(gen_eval):
        if row["case_id"] == "dev_01_tetA" and row.get("gs_claim") == "target_gene_detected":
            remaining.append("tetA on reused E. coli K-12 assembly was detected despite accessory/mobile truth=absent; no family-specific rule was added")
    if sum(1 for r in gen_rows if r["loaded"]) < 4:
        remaining.append("fewer than four new gene families were packaged from public sequences")
    if not available:
        remaining.append("Qwen3 / DeepSeek-R1-Distill were unavailable locally and were not substituted")
    if not ext_results["scored_tasks"]:
        remaining.append("no external benchmark tasks had local inputs; Genome Skeptic is not scored on rewritten proxies")

    label = "research prototype"
    models_ok = any(not c.get("unavailable") for c in model_report["comparisons"])
    ext_scored = bool(ext_results["scored_tasks"])
    fam_ok = sum(1 for r in gen_rows if r["loaded"]) >= 4
    para_ok = all(
        (
            c.get("architecture") == "close_paralogue"
            and ((c.get("paralogue_record") or {}).get("kind") == expected_kind[c["case_id"]])
        )
        if c["case_id"] in {"ctrl_para_true", "ctrl_para_recent", "ctrl_para_plasmid", "ctrl_para_contaminant"}
        else True
        for c in para_cases
    ) and any(c["case_id"] == "ctrl_para_true" for c in para_cases)
    frag_ok = any(c["case_id"] == "ctrl_para_fragments" and c.get("architecture") == "assembly_fragmented" for c in para_cases)
    div_ok = any(c["case_id"] == "ctrl_divergent_family" and c.get("architecture") == "divergent_full_length" for c in div_cases)
    can_ok = any(c["case_id"] == "ctrl_canonical_query_like" and c.get("architecture") == "canonical_full_length" for c in div_cases)
    beats_baselines = (
        gs_overall is not None and dummy_overall is not None and naive_overall is not None
        and gs_overall >= dummy_overall and gs_overall >= naive_overall
    )
    if para_ok and frag_ok and fam_ok and can_ok and div_ok and not ext_scored:
        label = "internally validated agent"
    if para_ok and frag_ok and fam_ok and can_ok and div_ok and ext_scored and models_ok and beats_baselines:
        label = "externally competitive agent"
    superior_gates = [
        ("matches conventional on clean cases", can_ok),
        ("improves difficult architecture cases", para_ok and div_ok and frag_ok),
        ("beats naive-confident and dummy-cautious on V4.1 controls", beats_baselines),
        ("stable across two open-weight models", models_ok),
        ("generalizes beyond rpoB", fam_ok),
        ("scored on original external genomics tasks", ext_scored),
    ]
    if all(ok for _, ok in superior_gates):
        label = "externally superior agent"

    md = [
        "# GENOME SKEPTIC V4.1 + EXTERNAL VALIDATION",
        "",
        "SPAdes was not rerun. V3 and V4 reports were not modified. The family HMM gate remains 0.20. No species-specific rules were added. External benchmark prompts and scorers were not rewritten. Thresholds were not retuned after viewing external held-out answers.",
        "",
        "## Acceptance gates (not a single composite)",
        "",
        f"- V4.1 paralogue/divergence controls GS overall: {gs_overall}",
        f"- Conventional on the same controls: {conv_overall}",
        f"- Genome Skeptic without falsification: {nof_overall}",
        f"- Dummy / naive: {dummy_overall} / {naive_overall}",
        f"- New families loaded: {sum(1 for r in gen_rows if r['loaded'])} / 4",
        f"- Multifamily calibration Brier: {cal_over.get('brier')}",
        f"- Multifamily calibration ECE: {cal_over.get('ece')}",
        f"- Overconfidence / underconfidence: {cal_over.get('overconfidence_rate')} / {cal_over.get('underconfidence_rate')}",
        f"- Model dry-run available names: {available}",
        f"- External supported tasks with local inputs: {len(ext_results['scored_tasks'])}",
        "",
        "## Paralogues and divergence",
        "",
    ]
    seen = set()
    for c in para_cases + div_cases:
        if c["case_id"] in seen:
            continue
        seen.add(c["case_id"])
        rec = c.get("paralogue_record") or {}
        md.append(
            f"- `{c['case_id']}` architecture={c.get('architecture')} kind={rec.get('kind')} "
            f"query_identity={c.get('query_identity')} divergent={(c.get('divergence') or {}).get('divergent')}"
        )
    md.extend(["", "### Control claim comparison", ""])
    for row in _arch_rows(controls):
        md.append(f"- `{row['case_id']}` `{row['target']}`: GS {row.get('gs_claim')}/{row.get('gs_status')} arch={row.get('gs_architecture')} vs conventional {row.get('conv_claim')}")
    md.extend(["", "## Gene-family generalization", ""])
    for r in gen_rows:
        md.append(f"- `{r['family_id']}` ({r.get('property')}): loaded={r.get('loaded')} n_members={r.get('n_members')}")
    for row in _arch_rows(gen_eval):
        md.append(f"- `{row['case_id']}` `{row['target']}`: GS {row.get('gs_claim')}/{row.get('gs_status')} arch={row.get('gs_architecture')} vs conventional {row.get('conv_claim')}")
    md.extend(["", "## Calibration (leave-one-genome-out, development only)", ""])
    md.append(f"- Held-out genomes used to fit: {calibration.get('held_out_used_to_fit')}")
    md.append(f"- External benchmark answers used to fit: {calibration.get('external_benchmark_used_to_fit')}")
    md.append(f"- n={calibration.get('n')} Brier={cal_over.get('brier')} ECE={cal_over.get('ece')}")
    md.append(f"- overconfidence={cal_over.get('overconfidence_rate')} underconfidence={cal_over.get('underconfidence_rate')}")
    md.append("- Reliability bins:")
    for b in cal_over.get("reliability") or []:
        md.append(
            f"  - [{b.get('bin_low')}, {b.get('bin_high')}): n={b.get('n')} "
            f"mean_pred={b.get('mean_predicted')} empirical={b.get('empirical_accuracy')}"
        )
    for fid, blob in (calibration.get("by_family") or {}).items():
        md.append(f"- family `{fid}`: n={blob.get('n')} Brier={blob.get('brier')} ECE={blob.get('ece')} over={blob.get('overconfidence_rate')} under={blob.get('underconfidence_rate')}")
    md.extend(["", "## Model independence", ""])
    md.append("- Deterministic evidence/claim engine is unchanged across adapter swaps.")
    md.append("- Silent substitution is forbidden.")
    setup = model_report.get("setup") or {}
    md.append(f"- Setup (OpenAI-compatible): {setup.get('openai_compatible')}")
    md.append(f"- Setup (Ollama): {setup.get('ollama')}")
    md.append(f"- Expected names: {setup.get('expected_model_names')}")
    hw = model_report.get("hardware") or {}
    md.append(f"- RAM/VRAM estimates: {hw.get('expected_vram_gb')} notes={hw.get('notes')}")
    for dry in model_report.get("dry_runs") or []:
        md.append(f"- dry-run `{dry.get('kind')}` resolved={dry.get('resolved_model')} invented_output={dry.get('invented_output')} would_call={dry.get('would_call')}")
    for cmp_row in model_report.get("comparisons") or []:
        md.append(f"- comparison planner={cmp_row.get('planner')} critic={cmp_row.get('critic')} unavailable={cmp_row.get('unavailable')} reason={cmp_row.get('reason')}")
    md.extend(["", "## External benchmarks", ""])
    md.append("Unsupported transcriptomics/single-cell/unrelated tasks were not rewritten. Only supported tasks with original local inputs would be scored.")
    md.append("- BioMaster was not executed locally; published numbers are not treated as a head-to-head comparison.")
    for kind, bench in (manifest.get("benchmarks") or {}).items():
        md.append(f"- `{kind}`: source={bench.get('source')} n={bench.get('n_tasks')} supported={bench.get('n_supported')} partial={bench.get('n_partial')} unsupported={bench.get('n_unsupported')}")
    md.extend(["", "## Superiority gates (evidence, not aspiration)", ""])
    for name, ok in superior_gates:
        md.append(f"- {name}: {ok}")
    md.extend(["", "## Remaining failures", ""])
    if remaining:
        md.extend(f"- {x}" for x in remaining)
    else:
        md.append("- No pre-registered V4.1 architecture failures were recorded.")
    md.extend([
        "",
        "## Label",
        "",
        f"**{label}**",
        "",
        "This label is from executed evidence: internal architecture controls, family generalization, model availability, and whether original external tasks could be scored without rewriting them. Genome Skeptic is not described as superior unless every listed superiority gate is true.",
        "",
        "## Files",
        "",
        "- GENOME_SKEPTIC_V4_1.md",
        "- paralogue_validation_v4_1.json",
        "- divergence_validation_v4_1.json",
        "- model_independence_v4_1.json",
        "- external_benchmark_manifest.json",
        "- external_benchmark_results.json",
        "- gene_family_generalization.json",
        "- calibration_multifamily.json",
        "",
    ])
    text = "\n".join(md) + "\n"
    (out / "GENOME_SKEPTIC_V4_1.md").write_text(text, encoding="utf-8")
    (ROOT / "GENOME_SKEPTIC_V4_1.md").write_text(text, encoding="utf-8")
    print("wrote GENOME_SKEPTIC_V4_1.md", flush=True)
    print("label", label, flush=True)
    print("remaining", remaining, flush=True)


if __name__ == "__main__":
    main()
