"""Real-world evaluation: three systems, hidden truth loaded after claims."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from genome_skeptic.config import Settings
from genome_skeptic.eval.baselines import assemble_case, followups_for, maybe_map_reads, run_conventional, run_skeptic
from genome_skeptic.eval.scoring import CaseTruth, HiddenTruth, MetricCount, merge_totals, overall_score, score_actions, score_case
from genome_skeptic.isolation import assert_agent_accessible


SYSTEMS = ("conventional", "skeptic_no_falsification", "genome_skeptic")


def _load_visible(case_dir: Path) -> dict:
    meta = yaml.safe_load((case_dir / "case.yaml").read_text()) or {}
    meta.setdefault("id", case_dir.name)
    for key in ("r1", "r2", "targets", "references", "gff", "proteins"):
        if meta.get(key):
            p = Path(meta[key])
            meta[key] = str(p if p.is_absolute() else case_dir / p)
    meta.setdefault("r1", str(case_dir / "reads_R1.fastq"))
    meta.setdefault("r2", str(case_dir / "reads_R2.fastq"))
    meta.setdefault("targets", str(case_dir / "targets.fa"))
    assert_agent_accessible(meta["r1"])
    assert_agent_accessible(meta.get("r2"))
    assert_agent_accessible(meta["targets"])
    if meta.get("references"):
        assert_agent_accessible(meta["references"])
    return meta


def evaluate_realworld(
    visible_dir: Path,
    truth_path: Path,
    out_dir: Path,
    settings: Settings,
) -> dict:
    """Assemble once per case, run three systems, then score with hidden truth."""
    out_dir.mkdir(parents=True, exist_ok=True)
    case_dirs = sorted(p for p in Path(visible_dir).iterdir() if p.is_dir())
    predictions: dict[str, dict] = {}
    for case_dir in case_dirs:
        meta = _load_visible(case_dir)
        case_out = out_dir / case_dir.name
        r1 = Path(meta["r1"])
        r2 = Path(meta["r2"]) if meta.get("r2") else None
        assembly = assemble_case(r1, r2, case_out / "assembly")
        mapping_sam = maybe_map_reads(assembly, r1, r2, case_out / "mapping")
        refs = Path(meta["references"]) if meta.get("references") else None
        targets = Path(meta["targets"])
        declared = meta.get("declared_organism")
        conv = run_conventional(assembly, targets, case_out / "conventional", settings)
        no_f, no_loci = run_skeptic(
            assembly, targets, case_out / "no_falsification", settings,
            references=refs, enable_falsification=False, declared_organism=declared, mapping_sam=mapping_sam,
        )
        full, loci = run_skeptic(
            assembly, targets, case_out / "genome_skeptic", settings,
            references=refs, enable_falsification=True, declared_organism=declared, mapping_sam=mapping_sam,
        )
        predictions[case_dir.name] = {
            "conventional": {"claims": conv, "loci": [], "followups": []},
            "skeptic_no_falsification": {"claims": no_f, "loci": no_loci, "followups": followups_for(no_f)},
            "genome_skeptic": {"claims": full, "loci": loci, "followups": followups_for(full)},
            "assembly": str(assembly),
        }

    hidden = HiddenTruth.model_validate(yaml.safe_load(Path(truth_path).read_text()) or {})
    by_system: dict[str, dict] = {s: {"parts": [], "rows": []} for s in SYSTEMS}
    highlights = []
    case_rows = []
    for case_id, pred in predictions.items():
        truth = hidden.cases.get(case_id)
        if truth is None:
            continue
        row = {"case_id": case_id, "label": truth.label or case_id, "corruption": truth.corruption, "systems": {}}
        for system in SYSTEMS:
            claims = pred[system]["claims"]
            loci = pred[system]["loci"]
            part, rows = score_case(case_id, claims, loci, truth)
            score_actions(part, pred[system]["followups"], truth)
            by_system[system]["parts"].append(part)
            by_system[system]["rows"].extend(rows)
            claim = claims[0] if claims else None
            row["systems"][system] = {
                "claim_type": claim.claim_type.value if claim else None,
                "status": claim.status.value if claim else None,
                "confidence": claim.confidence if claim else None,
                "statement": claim.statement if claim else None,
                "followups": pred[system]["followups"],
            }
        conv_s = row["systems"]["conventional"]
        gs = row["systems"]["genome_skeptic"]
        if conv_s.get("confidence") and conv_s["confidence"] >= 0.95:
            if gs.get("status") in {"weakened", "rejected", "unresolved"} or (gs.get("confidence") or 1) < 0.9:
                highlights.append({
                    "case_id": case_id,
                    "corruption": truth.corruption,
                    "conventional_statement": conv_s.get("statement"),
                    "skeptic_status": gs.get("status"),
                    "skeptic_statement": gs.get("statement"),
                    "note": "Conventional homology succeeded as a threshold call but the claim language or certainty is scientifically unsupported; Genome Skeptic recorded uncertainty or a challenge.",
                })
        case_rows.append(row)

    report = {
        "systems": {},
        "cases": case_rows,
        "highlights": highlights,
        "limitations": [
            "Cases use miniature complete-genome analogues (chromosome + plasmid), not downloaded NCBI genomes.",
            "This miniature suite is a synthetic regression test. Do not mix its scores with production real-genome results.",
            "eval assembler is a toy de Bruijn graph; homopolymer/N pads are randomized at simulation time, but it is not SPAdes and often fragments miniature genomes.",
            "Kraken2/sourmash contig taxonomy runs only when a database is configured; otherwise taxonomy is recorded as missing, not inferred.",
            "Read simulators prefer wgsim; tests fall back to a documented internal Illumina-like simulator.",
            "Thresholds were not tuned to force perfect scores, including not on held-out genomes.",
            "Scientific overall now scores calibration rather than generic caution: unresolved on a clean locus is penalized.",
            "Falsification-disabled Skeptic is unresolved on every claim; that is indiscriminate caution, not measured doubt.",
            "Next-action scoring uses scientific action classes. Extra useful diagnostics are not automatically penalized; repeats are.",
        ],
    }
    for system in SYSTEMS:
        totals = merge_totals(by_system[system]["parts"])
        report["systems"][system] = {
            "totals": {k: {**v.model_dump(), "rate": v.rate} for k, v in totals.items()},
            "overall": overall_score(totals),
            "targets": [r.model_dump() for r in by_system[system]["rows"]],
        }
    (out_dir / "realworld_evaluation.json").write_text(json.dumps(report, indent=2))
    (out_dir / "realworld_report.md").write_text(_markdown(report))
    return report


def _markdown(report: dict) -> str:
    lines = ["# Synthetic miniature adversarial validation", ""]
    lines.append("**Kind:** synthetic miniature genomes. Do not combine these numbers with production real-genome results.")
    lines.append("Ground-truth genomes and the truth manifest were loaded only after claims were produced.")
    lines.append("")
    lines.append("## System totals")
    lines.append("")
    lines.append("| System | Overall | Organism-level avoided | Overconfidence avoided | Underconfidence avoided | Overclaiming avoided | Next action |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for system, payload in report["systems"].items():
        tot = payload["totals"]
        ov = payload["overall"]
        ov_s = f"{ov:.3f}" if isinstance(ov, float) else "n/a"

        def frac(key):
            row = tot.get(key) or {"correct": 0, "n": 0}
            return f"{row.get('correct', 0)}/{row.get('n', 0)}"

        lines.append(
            f"| {system} | {ov_s} | {frac('unsupported_organism_level_claims')} | "
            f"{frac('overconfidence_on_ambiguous')} | {frac('underconfidence_on_clean')} | "
            f"{frac('unsupported_overclaiming')} | {frac('correct_next_action')} |"
        )
    lines.append("")
    lines.append("## Case by case")
    lines.append("")
    lines.append("| Case | Scenario | Conventional | No falsification | Genome Skeptic |")
    lines.append("|---|---|---|---|---|")
    for row in report["cases"]:
        cells = [row.get("label") or row["case_id"], row.get("corruption") or ""]
        for system in SYSTEMS:
            s = row["systems"][system]
            cells.append(f"{s.get('claim_type')}/{s.get('status')} ({s.get('confidence')})")
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    lines.append("")
    lines.append("## Highlights: conventional threshold success vs unsupported conclusions")
    if not report["highlights"]:
        lines.append("No cases in this run combined a high-confidence conventional call with a Skeptic challenge.")
    for h in report["highlights"]:
        lines.append(f"### {h['case_id']} ({h.get('corruption')})")
        lines.append(f"- Conventional: {h['conventional_statement']}")
        lines.append(f"- Genome Skeptic: {h['skeptic_status']} — {h['skeptic_statement']}")
        lines.append(f"- {h['note']}")
        lines.append("")
    lines.append("## Limitations")
    for lim in report["limitations"]:
        lines.append(f"- {lim}")
    return "\n".join(lines) + "\n"
