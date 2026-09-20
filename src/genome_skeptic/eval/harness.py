from __future__ import annotations

import json
from pathlib import Path

import yaml

from genome_skeptic.config import Settings
from genome_skeptic.eval.scoring import (
    CaseTruth,
    EvaluationReport,
    HiddenTruth,
    merge_totals,
    overall_score,
    score_case,
)
from genome_skeptic.locus.pipeline import analyze_targets_on_assembly
from genome_skeptic.models import Claim, LocusEvidence


def load_case_inputs(case_dir: Path) -> dict:
    meta_path = case_dir / "case.yaml"
    raw = yaml.safe_load(meta_path.read_text()) if meta_path.exists() else {}
    raw = raw or {}
    raw.setdefault("id", case_dir.name)
    for key in ("assembly", "targets", "gff", "proteins", "references"):
        value = raw.get(key)
        if value:
            p = Path(value)
            raw[key] = str(p if p.is_absolute() else (case_dir / p))
    raw.setdefault("assembly", str(case_dir / "assembly.fa"))
    raw.setdefault("targets", str(case_dir / "targets.fa"))
    return raw


def _run_case(case_dir: Path, out_dir: Path, settings: Settings) -> tuple[list[Claim], list[LocusEvidence]]:
    meta = load_case_inputs(case_dir)
    assembly = Path(meta["assembly"])
    targets = Path(meta["targets"])
    gff = Path(meta["gff"]) if meta.get("gff") else None
    proteins = Path(meta["proteins"]) if meta.get("proteins") else None
    references = Path(meta["references"]) if meta.get("references") else None
    claims, loci, _anoms = analyze_targets_on_assembly(
        targets=targets,
        assembly=assembly,
        settings=settings,
        assembly_gff=gff if gff and gff.exists() else None,
        proteins=proteins if proteins and proteins.exists() else None,
        references_yaml=references if references and references.exists() else None,
        out_dir=out_dir,
    )
    return claims, loci


def evaluate_benchmark(
    cases_dir: Path,
    truth_path: Path,
    out_dir: Path,
    settings: Settings,
) -> EvaluationReport:
    """Run each case without ground truth, then score against the hidden manifest."""
    case_dirs = sorted(p for p in Path(cases_dir).iterdir() if p.is_dir())
    predictions: dict[str, tuple[list[Claim], list[LocusEvidence]]] = {}
    for case_dir in case_dirs:
        case_out = Path(out_dir) / case_dir.name
        predictions[case_dir.name] = _run_case(case_dir, case_out, settings)

    hidden = HiddenTruth.model_validate(yaml.safe_load(Path(truth_path).read_text()) or {})
    totals_parts = []
    rows = []
    for case_id, (claims, loci) in predictions.items():
        case_truth = hidden.cases.get(case_id)
        if case_truth is None:
            continue
        part, part_rows = score_case(case_id, claims, loci, case_truth)
        totals_parts.append(part)
        rows.extend(part_rows)
    totals = merge_totals(totals_parts)
    report = EvaluationReport(totals=totals, targets=rows, overall=overall_score(totals))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "evaluation.json").write_text(json.dumps(report.as_json(), indent=2))
    return report
