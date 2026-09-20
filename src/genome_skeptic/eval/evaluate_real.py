"""Evaluate real-genome cases with production assembly and isolated analysis."""
from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from pathlib import Path

import yaml

from genome_skeptic.config import Settings, is_fast_pilot
from genome_skeptic.eval.baselines import followups_for, run_conventional, run_dummy_cautious, run_naive_confident, run_skeptic
from genome_skeptic.eval.pipeline import run_production_sequence
from genome_skeptic.eval.production import production_inventory
from genome_skeptic.eval.stack import write_environment_manifest, write_production_stack
from genome_skeptic.eval.sandbox import make_sandbox, sandbox_env
from genome_skeptic.eval.scoring import (
    CaseTruth,
    HiddenTruth,
    MetricCount,
    group_scores,
    merge_totals,
    overall_score,
    scientifically_correct,
    score_actions,
    score_case,
)
from genome_skeptic.isolation import assert_agent_accessible, hidden_roots
from genome_skeptic.models import Claim, ClaimStatus

SYSTEMS = (
    "dummy_cautious",
    "naive_confident",
    "conventional",
    "skeptic_no_falsification",
    "genome_skeptic",
)

ABLATIONS = {
    "no_synteny": {"enable_synteny": False},
    "no_mapping_breaks": {"enable_mapping_breaks": False},
    "no_orthology": {"enable_orthology": False},
    "no_phylogeny": {"enable_phylogeny": False},
    "no_critic": {"enable_critic": False},
    "no_completeness_in_confidence": {"apply_completeness_to_confidence": False},
}

ABLATION_NOTES = {
    "no_synteny": "Reference-aware synteny disabled; remaining architecture intact.",
    "no_mapping_breaks": "Read-supported break analysis disabled; geometric fallback only if mapping is absent.",
    "no_orthology": "RBH/paralogy classification disabled.",
    "no_phylogeny": "Placement among homologues disabled; RBH remains if orthology is on.",
    "no_critic": "Independent critic skipped. Claims remain deterministic; critic cannot be removed from the architecture without losing adversarial review.",
    "no_completeness_in_confidence": "Completeness is still recorded; it is not applied to confidence.",
}


def _best_hit(hits: list[dict], kinds: set[str]) -> dict | None:
    subset = [h for h in hits if h.get("search_kind") in kinds]
    if not subset:
        return None
    return max(subset, key=lambda h: (h.get("identity") or 0) * (h.get("query_coverage") or 0))


def build_prescore_table(predictions: dict, hidden: HiddenTruth, out_dir: Path | None = None) -> list[dict]:
    """Print one row per case/target/system before scoring. Does not compute overall scores."""
    rows = []
    for case_id, pred in predictions.items():
        truth = hidden.cases.get(case_id)
        if truth is None:
            continue
        for sys_name, payload in (pred.get("systems") or {}).items():
            if sys_name not in SYSTEMS:
                continue
            hits_path = out_dir / case_id / sys_name / "search" / "gene_search_hits.json" if out_dir else None
            hits = []
            if hits_path and hits_path.exists():
                try:
                    hits = json.loads(hits_path.read_text())
                except Exception:
                    hits = []
            claims = {c.claim_id.replace("C_target_", ""): c for c in (payload.get("claims") or [])}
            for target, expected in truth.targets.items():
                claim = claims.get(target)
                qhits = [h for h in hits if h.get("query_id") == target]
                nt = _best_hit(qhits, {"nucleotide"})
                prot = _best_hit(qhits, {"translated", "protein"})
                cov = None
                if nt:
                    cov = nt.get("query_coverage")
                elif prot:
                    cov = prot.get("query_coverage")
                row = {
                    "case_id": case_id,
                    "system": sys_name,
                    "target": target,
                    "target_type": expected.target_type,
                    "hidden_true_state": (
                        "unresolved" if expected.truth_state == "unresolved" or expected.present is None
                        else ("present" if expected.present else "absent")
                    ),
                    "target_provenance": expected.provenance,
                    "best_nucleotide_identity": None if nt is None else nt.get("identity"),
                    "best_nucleotide_coverage": None if nt is None else nt.get("query_coverage"),
                    "best_protein_identity": None if prot is None else prot.get("identity"),
                    "best_protein_coverage": None if prot is None else prot.get("query_coverage"),
                    "coverage": cov,
                    "claim": None if claim is None else claim.claim_type.value,
                    "status": None if claim is None else claim.status.value,
                    "confidence": None if claim is None else claim.confidence,
                    "evidence_completeness": None if claim is None else claim.evidence_completeness,
                    "homology_support": None if claim is None else claim.homology_support,
                }
                rows.append(row)
    header = (
        f"{'case':<22} {'sys':<24} {'target':<22} {'type':<16} {'truth':<10} "
        f"{'nt_id':>6} {'nt_cov':>6} {'aa_id':>6} {'aa_cov':>6} "
        f"{'claim':<26} {'status':<12} {'conf':>6} {'comp':>6}"
    )
    def fmt(val, width=6):
        if val is None:
            return f"{'':>{width}}"
        if isinstance(val, float):
            return f"{val:>{width}.3f}"
        return f"{str(val):<{width}}"

    print("\nPRE-SCORE TABLE (before scoring)\n" + header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['case_id']:<22} {row['system']:<24} {row['target']:<22} {str(row['target_type'] or ''):<16} "
            f"{row['hidden_true_state']:<10} "
            f"{fmt(row['best_nucleotide_identity'])} {fmt(row['best_nucleotide_coverage'])} "
            f"{fmt(row['best_protein_identity'])} {fmt(row['best_protein_coverage'])} "
            f"{str(row['claim'] or ''):<26} {str(row['status'] or ''):<12} "
            f"{fmt(row['confidence'])} {fmt(row['evidence_completeness'])}"
        )
    print()
    return rows


def _load_visible(case_dir: Path, *, require_reads: bool = True) -> dict:
    meta = yaml.safe_load((case_dir / "case.yaml").read_text()) or {}
    meta.setdefault("id", case_dir.name)
    for key in ("r1", "r2", "targets", "references"):
        if meta.get(key):
            p = Path(meta[key])
            meta[key] = str(p if p.is_absolute() else case_dir / p)
    meta.setdefault("r1", str(case_dir / "reads_R1.fastq"))
    meta.setdefault("r2", str(case_dir / "reads_R2.fastq"))
    meta.setdefault("targets", str(case_dir / "targets.fa"))
    if meta.get("assembly"):
        p = Path(meta["assembly"])
        meta["assembly"] = str(p if p.is_absolute() else case_dir / p)
    elif (case_dir / "contigs.fa").exists():
        meta["assembly"] = str(case_dir / "contigs.fa")
    if require_reads:
        assert_agent_accessible(meta["r1"])
        assert_agent_accessible(meta.get("r2"))
    assert_agent_accessible(meta["targets"])
    return meta


def _load_completed_system(out: Path) -> list[Claim] | None:
    path = out / "claims.json"
    if not path.exists() or path.stat().st_size <= 2:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, list) or not raw:
        return None
    return [Claim.model_validate(c) for c in raw]


def _run_system(name: str, assembly: Path, targets: Path, out: Path, settings: Settings, refs, declared, mapping, flags: dict | None = None, gff=None, proteins=None, depth_tsv=None):
    reused = _load_completed_system(out)
    if reused is not None:
        print(f"reuse completed system {out.parent.name}/{name}", flush=True)
        return {
            "claims": reused,
            "loci": [],
            "followups": followups_for(reused),
            "seconds": 0.0,
            "n_claims": len(reused),
            "reused": True,
        }
    cfg = deepcopy(settings)
    for k, v in (flags or {}).items():
        setattr(cfg.execution, k, v)
    t0 = time.perf_counter()
    if name == "dummy_cautious":
        claims = run_dummy_cautious(targets)
        loci = []
        followups = []
    elif name == "naive_confident":
        claims = run_naive_confident(assembly, targets, out, cfg)
        loci = []
        followups = []
    elif name == "conventional":
        claims = run_conventional(assembly, targets, out, cfg)
        loci = []
        followups = []
    elif name == "skeptic_no_falsification":
        claims, loci = run_skeptic(assembly, targets, out, cfg, references=refs, enable_falsification=False, declared_organism=declared, mapping_sam=mapping, gff=gff, proteins=proteins, depth_tsv=depth_tsv)
        followups = followups_for(claims)
    else:
        claims, loci = run_skeptic(assembly, targets, out, cfg, references=refs, enable_falsification=True, declared_organism=declared, mapping_sam=mapping, gff=gff, proteins=proteins, depth_tsv=depth_tsv)
        followups = followups_for(claims)
        for c in claims:
            if c.recommended_next_actions:
                followups = list(dict.fromkeys(list(c.recommended_next_actions) + followups))
    out.mkdir(parents=True, exist_ok=True)
    (out / "claims.json").write_text(json.dumps([c.model_dump(mode="json") for c in claims], indent=2), encoding="utf-8")
    return {
        "claims": claims,
        "loci": loci,
        "followups": followups,
        "seconds": time.perf_counter() - t0,
        "n_claims": len(claims),
    }


def _production_from_existing_assembly(prod_dir: Path, assembly: Path) -> dict:
    """Reuse a completed production assembly instead of re-running SPAdes."""
    mapping_sam = prod_dir / "mapping" / "mapped.sam"
    mapping_bam = prod_dir / "mapping" / "reads_to_assembly.bam"
    depth_tsv = prod_dir / "mapping" / "depth.tsv"
    clean_r1 = prod_dir / "fastp" / "clean_R1.fastq.gz"
    clean_r2 = prod_dir / "fastp" / "clean_R2.fastq.gz"
    return {
        "ok": True,
        "assembly": str(assembly),
        "mapping_sam": str(mapping_sam) if mapping_sam.exists() else None,
        "mapping_bam": str(mapping_bam) if mapping_bam.exists() else None,
        "depth_tsv": str(depth_tsv) if depth_tsv.exists() else None,
        "gff": None,
        "proteins": None,
        "clean_r1": str(clean_r1) if clean_r1.exists() else None,
        "clean_r2": str(clean_r2) if clean_r2.exists() else None,
        "stages": [{
            "stage": "spades",
            "tool": "spades.py",
            "ok": True,
            "parameters": {"reused_existing_assembly": True, "contigs": str(assembly), "regenerated_mapping": False},
        }],
        "missing": [],
        "failed": [],
        "reused_existing_assembly": True,
    }


def evaluate_real_genomes(
    visible_dir: Path,
    truth_path: Path,
    out_dir: Path,
    settings: Settings,
    *,
    run_ablations: bool = True,
    split: str | None = None,
    only_cases: list[str] | None = None,
    merge_existing: bool = False,
    reuse_assembly: bool = False,
    reuse_assembly_from: Path | None = None,
    write_fast_pilot_report: bool = True,
    print_prescore_table: bool = False,
    assembly_only: bool = False,
    only_systems: tuple[str, ...] | list[str] | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    fast_pilot = is_fast_pilot(settings)
    if fast_pilot:
        run_ablations = False
    inventory = production_inventory()
    limitations = []
    if not inventory.get("spades.py"):
        limitations.append("SPAdes is unavailable. The toy assembler was not substituted. Assembly dimension is unavailable.")
    if not inventory.get("fastp"):
        limitations.append("fastp is unavailable. QC cleaning was not simulated.")
    if not inventory.get("minimap2"):
        limitations.append("minimap2 is unavailable. Read-back mapping dimension is unavailable.")
    if not inventory.get("fastqc"):
        limitations.append("FastQC is unavailable. QC summary dimension is unavailable.")
    for name in ("checkm2", "bakta", "mmseqs", "diamond", "hmmsearch", "kraken2", "sourmash", "FastTree", "quast.py", "samtools"):
        if not inventory.get(name):
            limitations.append(f"{name} is unavailable. That production dimension is reported missing rather than simulated.")
    hidden_root = Path(truth_path).resolve().parent
    env = sandbox_env(hidden_root)
    os.environ.update({k: v for k, v in env.items() if k.startswith("GENOME_SKEPTIC_") or k not in os.environ})
    os.environ["GENOME_SKEPTIC_HIDDEN_ROOTS"] = str(hidden_root)
    for key in ("GENOME_SKEPTIC_TRUTH", "GENOME_SKEPTIC_SOURCE_GENOME", "GENOME_SKEPTIC_TRUTH_MANIFEST"):
        os.environ.pop(key, None)
    if not settings.paths.taxonomy_db:
        limitations.append("No taxonomy database is configured. kraken2/sourmash cannot be treated as having run.")
    if not settings.paths.bakta_db:
        limitations.append("No Bakta database is configured.")
    if not settings.paths.checkm2_db:
        limitations.append("No CheckM2 database is configured.")
    case_dirs = sorted(p for p in Path(visible_dir).iterdir() if p.is_dir())
    wanted = {c.strip() for c in (only_cases or []) if c and c.strip()}
    previous = None
    prev_path = out_dir / "realgenome_production_report.json"
    if merge_existing and prev_path.exists():
        previous = json.loads(prev_path.read_text())
        if bool(previous.get("fast_pilot")) != bool(fast_pilot):
            limitations.append("Refused to merge FAST_PILOT results with a full-production report.")
            previous = None
    if wanted:
        found = {p.name for p in case_dirs}
        missing_cases = sorted(wanted - found)
        if missing_cases:
            limitations.append(f"Requested cases not found under visible dir: {missing_cases}")
        case_dirs = [p for p in case_dirs if p.name in wanted]
    predictions = {}
    stack_status = {"inventory": inventory, "assembled": 0, "assembly_unavailable": 0}
    for case_dir in case_dirs:
        print(f"case {case_dir.name} start", flush=True)
        skip_reads = bool(reuse_assembly or assembly_only)
        sandbox = make_sandbox(
            case_dir,
            out_dir / "work",
            hidden_root,
            skip_reads=skip_reads,
        )
        meta = _load_visible(sandbox, require_reads=not skip_reads)
        r1 = Path(meta["r1"])
        r2 = Path(meta["r2"]) if meta.get("r2") else None
        case_out = out_dir / case_dir.name
        prev = os.getcwd()
        try:
            os.chdir(sandbox)
            if assembly_only:
                local_asm = Path(meta.get("assembly") or (sandbox / "contigs.fa"))
                if not local_asm.is_absolute():
                    local_asm = sandbox / local_asm
                prod = {
                    "ok": True,
                    "assembly": str(local_asm),
                    "mapping_sam": None,
                    "depth_tsv": None,
                    "gff": None,
                    "proteins": None,
                    "stages": [{"stage": "spades", "ok": True, "parameters": {"assembly_only_control": True}}],
                    "missing": [],
                    "failed": [],
                    "reused_existing_assembly": True,
                }
            else:
                existing_contigs = case_out / "production" / "spades" / "contigs.fasta"
                src_prod = None
                if reuse_assembly_from:
                    alt = Path(reuse_assembly_from) / case_dir.name / "production" / "spades" / "contigs.fasta"
                    if alt.exists() and alt.stat().st_size > 0:
                        src_prod = alt.parent.parent
                        existing_contigs = alt
                if reuse_assembly and existing_contigs.exists() and existing_contigs.stat().st_size > 0:
                    prod = _production_from_existing_assembly(src_prod or (case_out / "production"), existing_contigs)
                else:
                    prod = run_production_sequence(r1, r2, case_out / "production", settings)
        finally:
            os.chdir(prev)
        limitations.extend(prod.get("missing") or [])
        assembly = Path(prod["assembly"]) if prod.get("assembly") else None
        if assembly is None:
            stack_status["assembly_unavailable"] += 1
            predictions[case_dir.name] = {"unavailable": prod, "systems": {}, "production": prod}
            continue
        stack_status["assembled"] += 1
        mapping = Path(prod["mapping_sam"]) if prod.get("mapping_sam") else None
        depth_tsv = Path(prod["depth_tsv"]) if prod.get("depth_tsv") else None
        if depth_tsv is None and mapping:
            cand = mapping.with_name("depth.tsv")
            if cand.exists():
                depth_tsv = cand
        gff = Path(prod["gff"]) if prod.get("gff") else None
        proteins = Path(prod["proteins"]) if prod.get("proteins") else None
        refs = Path(meta["references"]) if meta.get("references") else None
        declared = meta.get("declared_organism")
        sys_results = {}
        selected_systems = tuple(only_systems) if only_systems is not None else SYSTEMS
        for sys_name in selected_systems:
            print(f"case {case_dir.name} system {sys_name}", flush=True)
            flags = {"enable_falsification": sys_name != "skeptic_no_falsification"} if "skeptic" in sys_name else None
            sys_results[sys_name] = _run_system(
                sys_name, assembly, Path(meta["targets"]), case_out / sys_name, settings, refs, declared, mapping,
                flags if sys_name not in {"conventional", "dummy_cautious", "naive_confident"} else None,
                gff=gff, proteins=proteins, depth_tsv=depth_tsv,
            )
        if run_ablations:
            for ab_name, flags in ABLATIONS.items():
                sys_results[ab_name] = _run_system(
                    "genome_skeptic", assembly, Path(meta["targets"]), case_out / ab_name, settings, refs, declared, mapping, flags,
                    gff=gff, proteins=proteins, depth_tsv=depth_tsv,
                )
                sys_results[ab_name]["ablation_note"] = ABLATION_NOTES[ab_name]
        predictions[case_dir.name] = {"unavailable": None, "systems": sys_results, "assembly": str(assembly), "production": prod}

    hidden = HiddenTruth.model_validate(yaml.safe_load(Path(truth_path).read_text()) or {})
    prescore_rows = []
    if print_prescore_table:
        prescore_rows = build_prescore_table(predictions, hidden, out_dir)
    failed_tools: list[str] = []
    missing_dimensions: list[str] = []
    missing_databases: list[str] = []
    for pred in predictions.values():
        prod = pred.get("production") or {}
        failed_tools.extend(prod.get("failed") or [])
        missing_dimensions.extend(prod.get("missing") or [])
    if not settings.paths.taxonomy_db:
        missing_databases.append("kraken2/sourmash taxonomy database")
    if not settings.paths.bakta_db:
        missing_databases.append("Bakta database")
    if not settings.paths.checkm2_db:
        missing_databases.append("CheckM2 database")
    if not inventory.get("checkm2"):
        missing_databases.append("CheckM2 executable (not installed)")

    by_system: dict[str, dict] = {}
    case_rows = []
    error_rows = []
    for case_id, pred in predictions.items():
        truth = hidden.cases.get(case_id)
        if truth is None:
            continue
        if split and truth.split and truth.split != split:
            continue
        row = {"case_id": case_id, "label": truth.label, "corruption": truth.corruption, "split": truth.split, "systems": {}, "production": pred.get("production")}
        if pred.get("unavailable"):
            row["unavailable"] = pred["unavailable"]
            error_rows.append({
                "case_id": case_id,
                "hidden_scenario": truth.corruption or truth.label,
                "correct_or_incorrect": "unavailable",
                "note": pred["unavailable"],
            })
            case_rows.append(row)
            continue
        for sys_name, payload in pred["systems"].items():
            by_system.setdefault(sys_name, {"parts": [], "rows": []})
            claims = payload["claims"]
            loci = payload["loci"]
            part, rows = score_case(case_id, claims, loci, truth)
            score_actions(part, payload["followups"], truth)
            by_system[sys_name]["parts"].append(part)
            by_system[sys_name]["rows"].extend(rows)
            claim = claims[0] if claims else None
            expected = next(iter(truth.targets.values())) if truth.targets else None
            correct = bool(claim and expected and scientifically_correct(claim, expected))
            overconfident = bool(
                expected and claim
                and (expected.paralogue or expected.contaminant or expected.fragmented or expected.uncertainty_required)
                and (
                    (claim.confidence or 0) >= 0.80
                    or (claim.status == ClaimStatus.supported and expected.uncertainty_required)
                )
            )
            underconfident = bool(
                expected and claim and expected.clean
                and claim.status in {ClaimStatus.unresolved, ClaimStatus.rejected}
            )
            row["systems"][sys_name] = {
                "claim_type": claim.claim_type.value if claim else None,
                "status": claim.status.value if claim else None,
                "confidence": claim.confidence if claim else None,
                "evidence_completeness": claim.evidence_completeness if claim else None,
                "homology_support": claim.homology_support if claim else None,
                "statement": claim.statement if claim else None,
                "supporting_evidence_ids": claim.supporting_evidence_ids if claim else [],
                "contradicting_evidence_ids": claim.contradicting_evidence_ids if claim else [],
                "completed_tests": claim.completed_tests if claim else [],
                "unresolved_tests": claim.unresolved_tests if claim else [],
                "unavailable_tests": claim.unavailable_tests if claim else [],
                "recommended_next_actions": payload["followups"],
                "seconds": payload.get("seconds"),
                "n_tool_invocations": len(claim.completed_tests) if claim else 0,
                "scientifically_correct": correct,
                "overconfident": overconfident,
                "unnecessarily_cautious": underconfident,
                "targets": {
                    (c.claim_id.replace("C_target_", "")): {
                        "claim_type": c.claim_type.value,
                        "status": c.status.value,
                        "confidence": c.confidence,
                        "raw_confidence": c.raw_confidence,
                        "evidence_completeness": c.evidence_completeness,
                        "homology_support": c.homology_support,
                        "statement": c.statement,
                        "architecture_state": c.architecture_state,
                        "orthology_class": c.orthology_class,
                    }
                    for c in claims
                },
            }
            error_rows.append(_error_row(case_id, truth, sys_name, claim, payload, correct, overconfident, underconfident))
        row["components_that_changed_result"] = _component_deltas(row)
        case_rows.append(row)

    report = {
        "kind": "fast_pilot_real_genome" if fast_pilot else "production_real_genome",
        "label": (
            "FAST PILOT - NOT FINAL BENCHMARK. Genuine public complete bacterial genomes with a reduced assembly profile. "
            "Not the full production benchmark. Do not mix these scores with a future full benchmark or the synthetic miniature suite."
            if fast_pilot
            else "Genuine public complete bacterial genomes with the production tool stack. Not the synthetic miniature benchmark."
        ),
        "fast_pilot": fast_pilot,
        "banner": "FAST PILOT - NOT FINAL BENCHMARK" if fast_pilot else None,
        "do_not_mix_with_full_benchmark": bool(fast_pilot),
        "split": split,
        "production": stack_status,
        "limitations": list(dict.fromkeys(limitations)),
        "missing_dimensions": list(dict.fromkeys(missing_dimensions or limitations)),
        "failed_tools": list(dict.fromkeys(failed_tools)),
        "missing_databases": list(dict.fromkeys(missing_databases)),
        "hidden_roots": [str(p) for p in hidden_roots()],
        "systems": {},
        "cases": case_rows,
        "error_analysis": error_rows,
        "ablation_notes": ABLATION_NOTES,
        "highlights": _highlights(case_rows),
        "error_categories": _categories(error_rows),
        "prescore_table": prescore_rows,
        "synthetic_miniature_excluded": True,
        "note": (
            "FAST PILOT - NOT FINAL BENCHMARK. Do not combine these numbers with the full production benchmark or the synthetic miniature suite."
            if fast_pilot
            else "Do not combine these numbers with the synthetic miniature realworld benchmark."
        ),
    }
    for sys_name, blob in by_system.items():
        totals = merge_totals(blob["parts"])
        report["systems"][sys_name] = {
            "totals": {k: {**v.model_dump(), "rate": v.rate} for k, v in totals.items()},
            "groups": group_scores(totals),
            "overall": overall_score(totals),
            "mean_seconds": (
                sum((row.get("systems") or {}).get(sys_name, {}).get("seconds") or 0 for row in case_rows)
                / max(1, sum(1 for row in case_rows if (row.get("systems") or {}).get(sys_name)))
            ),
        }
    if previous and wanted:
        report = _merge_realgenome_reports(previous, report, rerun_ids=wanted)
    gs = (report.get("systems") or {}).get("genome_skeptic") or {}
    nof = (report.get("systems") or {}).get("skeptic_no_falsification") or {}
    dummy = (report.get("systems") or {}).get("dummy_cautious") or {}
    naive = (report.get("systems") or {}).get("naive_confident") or {}
    report["full_vs_no_falsification"] = {
        "genome_skeptic_overall": gs.get("overall"),
        "no_falsification_overall": nof.get("overall"),
        "full_beats_no_falsification": (
            gs.get("overall") is not None and nof.get("overall") is not None and gs["overall"] > nof["overall"]
        ),
        "note": "Comparison uses scientific overall (calibration), not generic caution.",
    }
    report["full_vs_baselines"] = {
        "genome_skeptic_overall": gs.get("overall"),
        "dummy_cautious_overall": dummy.get("overall"),
        "naive_confident_overall": naive.get("overall"),
        "no_falsification_overall": nof.get("overall"),
        "full_beats_dummy": (
            gs.get("overall") is not None and dummy.get("overall") is not None and gs["overall"] > dummy["overall"]
        ),
        "full_beats_naive": (
            gs.get("overall") is not None and naive.get("overall") is not None and gs["overall"] > naive["overall"]
        ),
        "full_beats_both_trivial_baselines": (
            gs.get("overall") is not None
            and dummy.get("overall") is not None
            and naive.get("overall") is not None
            and gs["overall"] > dummy["overall"]
            and gs["overall"] > naive["overall"]
        ),
        "groups": {
            "genome_skeptic": gs.get("groups"),
            "dummy_cautious": dummy.get("groups"),
            "naive_confident": naive.get("groups"),
            "skeptic_no_falsification": nof.get("groups"),
        },
    }
    inferred = {}
    for pred in predictions.values():
        for st in (pred.get("production") or {}).get("stages") or []:
            tool = st.get("tool")
            if tool and st.get("ok"):
                inferred[tool] = {"ran": True, "ok": True}
    (out_dir / "real_genome_evaluation.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / "real_genome_report.md").write_text(_markdown(report))
    (out_dir / "realgenome_production_report.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / "realgenome_production_report.md").write_text(_markdown(report))
    if fast_pilot and write_fast_pilot_report:
        fp = out_dir / "FAST_PILOT_REPORT.md"
        if fp.exists():
            limitations.append("Existing FAST_PILOT_REPORT.md was left unchanged; it is invalid for performance comparison.")
        else:
            write_fast_pilot_summary(fp, report)
    write_production_stack(out_dir / "production_stack.json", settings=settings, smoke=inferred or None)
    write_environment_manifest(out_dir / "environment_manifest.json")
    _maybe_plots(report, out_dir)
    return report


def _metric_totals_from_blob(blob: dict | None) -> dict[str, MetricCount]:
    from genome_skeptic.eval.scoring import METRIC_NAMES

    raw = (blob or {}).get("totals") or {}
    out = {name: MetricCount() for name in METRIC_NAMES}
    for name, row in raw.items():
        if isinstance(row, dict):
            out[name] = MetricCount(n=int(row.get("n") or 0), correct=int(row.get("correct") or 0))
    return out


def _merge_realgenome_reports(previous: dict, new: dict, *, rerun_ids: set[str]) -> dict:
    """Keep successful cases from a prior report and replace rerun case IDs."""
    old_cases = list(previous.get("cases") or [])
    new_by_id = {c["case_id"]: c for c in (new.get("cases") or []) if c.get("case_id")}
    merged_cases = []
    seen: set[str] = set()
    for row in old_cases:
        cid = row.get("case_id")
        if not cid:
            continue
        seen.add(cid)
        merged_cases.append(new_by_id[cid] if cid in new_by_id else row)
    for cid, row in new_by_id.items():
        if cid not in seen:
            merged_cases.append(row)

    error_rows = [e for e in (previous.get("error_analysis") or []) if e.get("case_id") not in rerun_ids]
    error_rows.extend(new.get("error_analysis") or [])

    assembled = 0
    unavailable = 0
    failed_tools: list[str] = []
    missing_dims: list[str] = []
    for row in merged_cases:
        prod = row.get("production") or {}
        if prod.get("ok") and prod.get("assembly"):
            assembled += 1
        else:
            unavailable += 1
        failed_tools.extend(prod.get("failed") or [])
        missing_dims.extend(prod.get("missing") or [])

    inventory = ((new.get("production") or {}).get("inventory")
                 or (previous.get("production") or {}).get("inventory") or {})
    systems = {}
    all_names = set((previous.get("systems") or {})) | set((new.get("systems") or {}))
    for name in all_names:
        previously_scored = any(((c.get("systems") or {}).get(name)) for c in old_cases if c.get("case_id") in rerun_ids)
        old_tot = _metric_totals_from_blob((previous.get("systems") or {}).get(name))
        new_tot = _metric_totals_from_blob((new.get("systems") or {}).get(name))
        combined = new_tot if previously_scored else merge_totals([old_tot, new_tot])
        n_sys = sum(1 for c in merged_cases if (c.get("systems") or {}).get(name))
        seconds = sum(((c.get("systems") or {}).get(name) or {}).get("seconds") or 0 for c in merged_cases)
        systems[name] = {
            "totals": {k: {**v.model_dump(), "rate": v.rate} for k, v in combined.items()},
            "overall": overall_score(combined),
            "mean_seconds": seconds / max(1, n_sys),
        }

    merged = dict(previous)
    merged.update({
        "kind": new.get("kind") or previous.get("kind"),
        "label": new.get("label") or previous.get("label"),
        "split": new.get("split") if new.get("split") is not None else previous.get("split"),
        "production": {
            "inventory": inventory,
            "assembled": assembled,
            "assembly_unavailable": unavailable,
        },
        "limitations": list(dict.fromkeys((previous.get("limitations") or []) + (new.get("limitations") or []))),
        "missing_dimensions": list(dict.fromkeys(missing_dims or (new.get("missing_dimensions") or []))),
        "failed_tools": list(dict.fromkeys(failed_tools)),
        "missing_databases": list(dict.fromkeys((new.get("missing_databases") or previous.get("missing_databases") or []))),
        "hidden_roots": new.get("hidden_roots") or previous.get("hidden_roots"),
        "systems": systems,
        "cases": merged_cases,
        "error_analysis": error_rows,
        "highlights": _highlights(merged_cases),
        "error_categories": _categories(error_rows),
        "resource_rerun_case_ids": sorted(rerun_ids),
    })
    return merged


def write_fast_pilot_summary(path: Path, report: dict, *, held: dict | None = None) -> None:
    """Concise FAST_PILOT table. Not a full-benchmark substitute."""
    blobs = [("development" if (report.get("split") == "development") else (report.get("split") or "run"), report)]
    if held:
        blobs.append(("held_out", held))
    lines = [
        "# FAST PILOT - NOT FINAL BENCHMARK",
        "",
        "Interpretable reduced-assembly pilot. **Not** the full production benchmark. Do not mix these scores with a future full benchmark.",
        "",
        f"- Split in this file: {report.get('split')}",
        f"- Cases assembled: {(report.get('production') or {}).get('assembled')}",
        f"- Assembly unavailable: {(report.get('production') or {}).get('assembly_unavailable')}",
        "",
        "| Split | Case | Hidden scenario | Runtime (assembly s / GS s) | Assembly | Conventional | Genome Skeptic | GS confidence | Evidence completeness | Falsification changed conclusion | Overclaim | False absence | Useful next actions |",
        "|---|---|---|---|---|---|---|---:|---:|---|---|---|---|",
    ]
    rows_out = []
    for split_name, blob in blobs:
        for row in blob.get("cases") or []:
            prod = row.get("production") or {}
            stages = {s.get("stage"): s for s in (prod.get("stages") or []) if s.get("stage")}
            asm_s = (stages.get("spades") or {}).get("runtime_seconds")
            gs = (row.get("systems") or {}).get("genome_skeptic") or {}
            conv = (row.get("systems") or {}).get("conventional") or {}
            nof = (row.get("systems") or {}).get("skeptic_no_falsification") or {}
            assembled = bool(prod.get("ok") and prod.get("assembly"))
            falsification_changed = (
                (gs.get("status") != nof.get("status"))
                or (gs.get("claim_type") != nof.get("claim_type"))
                or abs((gs.get("confidence") or 0) - (nof.get("confidence") or 0)) >= 0.05
            ) if gs and nof else False
            overclaim = bool(gs.get("overconfident"))
            false_abs = None
            if gs:
                false_abs = (gs.get("scientifically_correct") is False and gs.get("claim_type") == "target_gene_not_detected")
            next_actions = gs.get("recommended_next_actions") or []
            lines.append(
                "| {split} | `{cid}` | {scen} | {asm} / {gs_s} | {ok} | {conv} | {gss} | {conf} | {comp} | {fals} | {oc} | {fa} | {nxt} |".format(
                    split=split_name,
                    cid=row.get("case_id"),
                    scen=row.get("corruption") or row.get("label") or "",
                    asm=asm_s if asm_s is not None else "n/a",
                    gs_s=round(gs.get("seconds") or 0, 1) if gs else "n/a",
                    ok="success" if assembled else "failure",
                    conv=(conv.get("status") or "n/a") + (f" ({conv.get('claim_type')})" if conv.get("claim_type") else ""),
                    gss=(gs.get("status") or "n/a") + (f" ({gs.get('claim_type')})" if gs.get("claim_type") else ""),
                    conf=gs.get("confidence") if gs.get("confidence") is not None else "n/a",
                    comp=gs.get("evidence_completeness") if gs.get("evidence_completeness") is not None else "n/a",
                    fals="yes" if falsification_changed else "no",
                    oc="yes" if overclaim else "no",
                    fa="yes" if false_abs else "no",
                    nxt="; ".join(next_actions[:4]) if next_actions else "none",
                )
            )
            rows_out.append({
                "split": split_name,
                "case_id": row.get("case_id"),
                "scenario": row.get("corruption") or row.get("label"),
                "assembly_runtime_seconds": asm_s,
                "genome_skeptic_seconds": gs.get("seconds"),
                "assembly": "success" if assembled else "failure",
                "conventional_status": conv.get("status"),
                "conventional_claim_type": conv.get("claim_type"),
                "conventional_statement": conv.get("statement"),
                "genome_skeptic_status": gs.get("status"),
                "genome_skeptic_claim_type": gs.get("claim_type"),
                "genome_skeptic_statement": gs.get("statement"),
                "confidence": gs.get("confidence"),
                "evidence_completeness": gs.get("evidence_completeness"),
                "falsification_changed_conclusion": falsification_changed,
                "overclaiming_error": overclaim,
                "false_absence_error": false_abs,
                "useful_next_actions": next_actions,
            })
    lines.append("")
    lines.append("## Missing dimensions / databases")
    for item in report.get("missing_databases") or []:
        lines.append(f"- {item} (explicitly unavailable; not simulated)")
    for item in (report.get("missing_dimensions") or [])[:12]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## System overall (pilot only)")
    for name, payload in (report.get("systems") or {}).items():
        if name in SYSTEMS:
            lines.append(f"- {name}: {payload.get('overall')}")
    path.write_text("\n".join(lines) + "\n")
    path.with_suffix(".json").write_text(json.dumps({"banner": "FAST PILOT - NOT FINAL BENCHMARK", "rows": rows_out, "report_kind": report.get("kind")}, indent=2, default=str))


def _error_row(case_id, truth, sys_name, claim, payload, correct, overconfident, underconfident) -> dict:
    statement = claim.statement if claim else None
    return {
        "case_id": case_id,
        "system": sys_name,
        "hidden_biological_scenario": truth.corruption or truth.label,
        "system_conclusion": statement,
        "claim_scope": "assembly" if claim and "current assembly" in (claim.statement or "") else ("organism" if claim and ("organism" in (claim.statement or "").lower() or "isolate" in (claim.statement or "").lower()) else "unknown"),
        "claim_status": claim.status.value if claim else None,
        "confidence": claim.confidence if claim else None,
        "evidence_completeness": claim.evidence_completeness if claim else None,
        "supporting_evidence": claim.supporting_evidence_ids if claim else [],
        "contradicting_evidence": claim.contradicting_evidence_ids if claim else [],
        "missed_evidence": claim.unavailable_tests if claim else [],
        "correct_or_incorrect": "correct" if correct else "incorrect",
        "overconfident": overconfident,
        "unnecessarily_cautious": underconfident,
        "next_actions": payload.get("followups") or [],
        "seconds": payload.get("seconds"),
        "remaining_ambiguity": claim.unresolved_tests if claim else [],
    }


def _component_deltas(row: dict) -> list[str]:
    gs = (row.get("systems") or {}).get("genome_skeptic") or {}
    notes = []
    for name, payload in (row.get("systems") or {}).items():
        if name in SYSTEMS:
            continue
        if gs.get("status") != payload.get("status") or abs((gs.get("confidence") or 0) - (payload.get("confidence") or 0)) >= 0.08:
            notes.append(name)
    return notes


def _highlights(case_rows: list[dict]) -> list[dict]:
    out = []
    for row in case_rows:
        conv = (row.get("systems") or {}).get("conventional") or {}
        gs = (row.get("systems") or {}).get("genome_skeptic") or {}
        nof = (row.get("systems") or {}).get("skeptic_no_falsification") or {}
        if conv.get("confidence", 0) and conv["confidence"] >= 0.95:
            if gs.get("status") in {"weakened", "rejected", "unresolved"} or (gs.get("confidence") or 1) < 0.9:
                out.append({"kind": "conventional_unsupported_caught", "case_id": row["case_id"], "scenario": row.get("corruption"), "conventional": conv.get("statement"), "skeptic": gs.get("statement")})
        if gs.get("status") == "unresolved" and row.get("corruption") in {None, "none"}:
            out.append({"kind": "too_cautious_on_clean", "case_id": row["case_id"], "skeptic": gs.get("statement")})
        if gs.get("status") == "supported" and row.get("corruption") not in {None, "none"} and (gs.get("confidence") or 0) >= 0.7:
            out.append({"kind": "missed_anomaly", "case_id": row["case_id"], "scenario": row.get("corruption")})
        nof_correct = nof.get("scientifically_correct")
        gs_correct = gs.get("scientifically_correct")
        if nof_correct and gs_correct is False:
            out.append({"kind": "falsification_made_worse", "case_id": row["case_id"]})
        if len(gs.get("recommended_next_actions") or []) >= 4:
            out.append({"kind": "unnecessary_followups", "case_id": row["case_id"], "actions": gs.get("recommended_next_actions")})
    return out


def _categories(error_rows: list[dict]) -> dict:
    cats: dict[str, int] = {}
    for row in error_rows:
        key = f"{row.get('system')}:{row.get('hidden_biological_scenario')}:{row.get('claim_status')}"
        cats[key] = cats.get(key, 0) + 1
    return cats


def _markdown(report: dict) -> str:
    lines = []
    if report.get("fast_pilot"):
        lines.extend(["# FAST PILOT - NOT FINAL BENCHMARK", ""])
        lines.append("These scores are a reduced-assembly pilot. They are **not** the full production benchmark and must not be mixed with it.")
        lines.append("")
    lines.append("# Real-genome production report")
    lines.append("")
    split = report.get("split") or "unspecified"
    lines.append("**Kind:** genuine public complete bacterial genomes and production tools.")
    lines.append("**Not** the synthetic miniature benchmark. Those scores are not combined with these numbers.")
    lines.append(f"**Split:** {split}")
    lines.append("Held-out source genomes and the truth manifest were loaded only after claims were produced.")
    lines.append("Scientific overall excludes generic caution. Thresholds were not tuned on held-out genomes.")
    lines.append("")
    lines.append("## Production results")
    prod = report.get("production") or {}
    lines.append(f"- Cases assembled with SPAdes: {prod.get('assembled', 0)}")
    lines.append(f"- Cases where assembly was unavailable: {prod.get('assembly_unavailable', 0)}")
    lines.append("")
    lines.append("## Missing dimensions")
    dims = report.get("missing_dimensions") or report.get("limitations") or []
    if not dims:
        lines.append("No missing production dimensions were recorded.")
    for lim in dims:
        lines.append(f"- {lim}")
    lines.append("")
    lines.append("## Failed tools")
    failed = report.get("failed_tools") or []
    if not failed:
        lines.append("No production-stage tool failures were recorded.")
    for name in failed:
        lines.append(f"- {name}")
    lines.append("")
    lines.append("## Missing databases")
    dbs = report.get("missing_databases") or []
    if not dbs:
        lines.append("No required databases were reported missing.")
    for name in dbs:
        lines.append(f"- {name} — taxonomy/annotation/completeness is not treated as validated.")
    lines.append("")
    if split == "development":
        lines.append("## Development results")
        lines.append("This run used development genomes only. Configuration may be inspected here before freeze.")
        lines.append("")
    elif split == "held_out":
        lines.append("## Held-out results")
        lines.append("This run used held-out genomes after freeze. Thresholds and labels were not modified based on these results.")
        lines.append("")
    else:
        lines.append("## Split")
        lines.append("Split was not specified; treat results as mixed only if both development and held-out cases were present.")
        lines.append("")
    inv = prod.get("inventory") or {}
    if inv:
        lines.append("## Production-stack inventory (executable presence)")
        lines.append("")
        lines.append("| Tool | Executable on PATH |")
        lines.append("|---|---|")
        for name, ok in inv.items():
            lines.append(f"| {name} | {'yes' if ok else 'no'} |")
        lines.append("")
        lines.append("Executable presence is not operational status. See production_stack.json.")
        lines.append("")
    if not report.get("systems"):
        lines.append("No systems were scored because production assembly did not complete. This is not a scientific Genome Skeptic result.")
        lines.append("")
    lines.append("| System | Overall | Organism-level avoided | Overconfidence avoided | Underconfidence avoided | False detection avoided | False absence avoided | Completeness-confidence |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")

    def frac(tot, key):
        row = tot.get(key) or {}
        return f"{row.get('correct', 0)}/{row.get('n', 0)}"

    for name, payload in report.get("systems", {}).items():
        tot = payload["totals"]
        ov = payload["overall"]
        ov_s = f"{ov:.3f}" if isinstance(ov, float) else "n/a"
        lines.append(
            f"| {name} | {ov_s} | {frac(tot, 'unsupported_organism_level_claims')} | "
            f"{frac(tot, 'overconfidence_on_ambiguous')} | {frac(tot, 'underconfidence_on_clean')} | "
            f"{frac(tot, 'false_detection')} | {frac(tot, 'false_absence')} | {frac(tot, 'completeness_confidence_consistency')} |"
        )
    cmp_ = report.get("full_vs_no_falsification") or {}
    lines.append("")
    lines.append("## Full Genome Skeptic vs falsification-off")
    lines.append("")
    lines.append(f"- Full overall: {cmp_.get('genome_skeptic_overall')}")
    lines.append(f"- Falsification-off overall: {cmp_.get('no_falsification_overall')}")
    lines.append(f"- Full beats falsification-off: {cmp_.get('full_beats_no_falsification')}")
    lines.append("")
    lines.append("## Highlights")
    if not report.get("highlights"):
        lines.append("No highlight rules fired.")
    for h in report.get("highlights") or []:
        lines.append(f"- **{h['kind']}** `{h.get('case_id')}` {h.get('scenario') or ''}")
    lines.append("")
    lines.append("## Error analysis")
    for row in report.get("error_analysis") or []:
        if row.get("system") not in SYSTEMS:
            continue
        lines.append(f"### {row['case_id']} / {row['system']} ({row.get('hidden_biological_scenario')})")
        lines.append(f"- Conclusion: {row.get('system_conclusion')}")
        lines.append(f"- Scope {row.get('claim_scope')}; status {row.get('claim_status')}; confidence {row.get('confidence')}; completeness {row.get('evidence_completeness')}")
        lines.append(f"- Interpretation: {row.get('correct_or_incorrect')}; overconfident={row.get('overconfident')}; unnecessarily_cautious={row.get('unnecessarily_cautious')}")
        lines.append(f"- Supporting: {row.get('supporting_evidence')}")
        lines.append(f"- Contradicting: {row.get('contradicting_evidence')}")
        lines.append(f"- Missed/unavailable tests: {row.get('missed_evidence')}")
        lines.append(f"- Next actions: {row.get('next_actions')}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _maybe_plots(report: dict, out_dir: Path) -> None:
    points = []
    for row in report.get("cases") or []:
        for sys_name, payload in (row.get("systems") or {}).items():
            points.append({
                "case_id": row.get("case_id"),
                "system": sys_name,
                "corruption": row.get("corruption"),
                "confidence": payload.get("confidence"),
                "completeness": payload.get("evidence_completeness"),
                "correct": payload.get("scientifically_correct"),
                "overconfident": payload.get("overconfident"),
                "underconfident": payload.get("unnecessarily_cautious"),
            })
    series = {
        "overall": {k: v.get("overall") for k, v in report.get("systems", {}).items()},
        "organism_level_avoided": {k: (v["totals"].get("unsupported_organism_level_claims") or {}).get("rate") for k, v in report.get("systems", {}).items()},
        "overconfidence_avoided": {k: (v["totals"].get("overconfidence_on_ambiguous") or {}).get("rate") for k, v in report.get("systems", {}).items()},
        "underconfidence_avoided": {k: (v["totals"].get("underconfidence_on_clean") or {}).get("rate") for k, v in report.get("systems", {}).items()},
        "false_detection_avoided": {k: (v["totals"].get("false_detection") or {}).get("rate") for k, v in report.get("systems", {}).items()},
        "false_absence_avoided": {k: (v["totals"].get("false_absence") or {}).get("rate") for k, v in report.get("systems", {}).items()},
        "next_action_utility": {k: (v["totals"].get("useful_follow_up_analyses") or {}).get("rate") for k, v in report.get("systems", {}).items()},
        "points": points,
        "full_vs_no_falsification": report.get("full_vs_no_falsification"),
    }
    (out_dir / "calibration_series.json").write_text(json.dumps(series, indent=2))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    names = [k for k in report.get("systems", {}) if k in SYSTEMS] or list(report.get("systems", {}))[:8]
    xs = list(range(len(names)))

    def _bar(metric_key, ylabel, filename, title):
        fig, ax = plt.subplots(figsize=(8, 4))
        vals = []
        for n in names:
            tot = report["systems"][n]["totals"]
            if metric_key == "overall":
                vals.append(report["systems"][n]["overall"] or 0)
            else:
                vals.append((tot.get(metric_key) or {}).get("rate") or 0)
        ax.bar(xs, vals)
        ax.set_xticks(xs)
        ax.set_xticklabels(names, rotation=25, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        fig.tight_layout()
        fig.savefig(out_dir / filename)
        plt.close(fig)

    _bar("overall", "Scientific overall", "system_comparison.png", "System comparison (scientific overall)")
    _bar("unsupported_overclaiming", "Overclaim avoided (rate)", "overclaim_rate.png", "Overclaim avoidance by system")
    _bar("false_absence", "False-absence avoided (rate)", "false_absence_rate.png", "False-absence avoidance by system")
    _bar("false_detection", "False-detection avoided (rate)", "false_detection_rate.png", "False-detection avoidance by system")
    _bar("useful_follow_up_analyses", "Useful next-action rate", "next_action_utility.png", "Next-action utility by system")
    ab_names = [k for k in report.get("systems", {}) if k not in SYSTEMS]
    if ab_names:
        fig, ax = plt.subplots(figsize=(8, 4))
        labels = ["genome_skeptic"] + ab_names
        ax.bar(range(len(labels)), [report["systems"][n]["overall"] or 0 for n in labels])
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=25, ha="right")
        ax.set_ylabel("Scientific overall")
        ax.set_title("Ablation comparison")
        fig.tight_layout()
        fig.savefig(out_dir / "ablation_comparison.png")
        plt.close(fig)
    gs_pts = [p for p in points if p["system"] == "genome_skeptic" and p["confidence"] is not None]
    if gs_pts:
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.scatter([p["confidence"] for p in gs_pts], [1 if p["correct"] else 0 for p in gs_pts], alpha=0.7)
        ax.set_xlabel("Claim confidence")
        ax.set_ylabel("Empirical correctness (1 = scientifically correct)")
        ax.set_title("Genome Skeptic: confidence versus empirical correctness")
        fig.tight_layout()
        fig.savefig(out_dir / "confidence_vs_correctness.png")
        plt.close(fig)
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.scatter([p["completeness"] or 0 for p in gs_pts], [p["confidence"] for p in gs_pts], alpha=0.7)
        ax.set_xlabel("Evidence completeness")
        ax.set_ylabel("Confidence")
        ax.set_title("Genome Skeptic: evidence completeness versus confidence")
        fig.tight_layout()
        fig.savefig(out_dir / "completeness_vs_confidence.png")
        plt.close(fig)


def combine_production_reports(dev: dict | None, held: dict | None) -> dict:
    """Join development and held-out reports without mixing headline scores."""
    return {
        "kind": "production_real_genome_combined",
        "label": "Genuine public complete bacterial genomes. Development and held-out are reported separately. Synthetic miniature scores are excluded.",
        "development": dev,
        "held_out": held,
        "missing_dimensions": list(dict.fromkeys((dev or {}).get("missing_dimensions", []) + (held or {}).get("missing_dimensions", []))),
        "failed_tools": list(dict.fromkeys((dev or {}).get("failed_tools", []) + (held or {}).get("failed_tools", []))),
        "missing_databases": list(dict.fromkeys((dev or {}).get("missing_databases", []) + (held or {}).get("missing_databases", []))),
        "development_overall": ((dev or {}).get("systems") or {}).get("genome_skeptic", {}).get("overall"),
        "held_out_overall": ((held or {}).get("systems") or {}).get("genome_skeptic", {}).get("overall"),
        "conventional_held_out_overall": ((held or {}).get("systems") or {}).get("conventional", {}).get("overall"),
        "note": "Headline metrics are not averaged across development, held-out, or the synthetic miniature suite.",
    }


def write_combined_production_report(path: Path, combined: dict, *, freeze: dict | None = None, stack: dict | None = None) -> None:
    lines = ["# Real-genome production report", ""]
    lines.append("**Kind:** genuine public complete bacterial genomes and production tools.")
    lines.append("Development and held-out results are separate. Synthetic miniature scores are not included.")
    lines.append("")
    lines.append("## Production results")
    lines.append(f"- Development Genome Skeptic overall: {combined.get('development_overall')}")
    lines.append(f"- Held-out Genome Skeptic overall: {combined.get('held_out_overall')}")
    lines.append(f"- Held-out conventional overall: {combined.get('conventional_held_out_overall')}")
    for split_name, key in (("development", "development"), ("held-out", "held_out")):
        blob = combined.get(key) or {}
        prod = blob.get("production") or {}
        lines.append(f"- {split_name} SPAdes assemblies: {prod.get('assembled', 0)}; unavailable: {prod.get('assembly_unavailable', 0)}")
    lines.append("")
    lines.append("## Missing dimensions")
    for item in combined.get("missing_dimensions") or ["None recorded."]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Failed tools")
    for item in combined.get("failed_tools") or ["None recorded."]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Missing databases")
    for item in combined.get("missing_databases") or ["None recorded."]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Development results")
    dev = combined.get("development") or {}
    if not dev:
        lines.append("Development split was not run.")
    else:
        for name, payload in (dev.get("systems") or {}).items():
            if name in SYSTEMS:
                lines.append(f"- {name} overall: {payload.get('overall')}")
    lines.append("")
    lines.append("## Held-out results")
    held = combined.get("held_out") or {}
    if not held:
        lines.append("Held-out split was not run.")
    else:
        for name, payload in (held.get("systems") or {}).items():
            if name in SYSTEMS:
                lines.append(f"- {name} overall: {payload.get('overall')}")
    if freeze:
        lines.append("")
        lines.append("## Freeze")
        lines.append(f"- sha256: {freeze.get('sha256')}")
        lines.append(f"- created_at: {freeze.get('created_at')}")
    if stack:
        lines.append("")
        lines.append("## Production stack (operational count)")
        lines.append(f"- operational: {stack.get('operational_count')}")
        lines.append(f"- available: {stack.get('available_count')}")
    path.write_text("\n".join(lines) + "\n")
    path.with_suffix(".json").write_text(json.dumps(combined, indent=2, default=str))
