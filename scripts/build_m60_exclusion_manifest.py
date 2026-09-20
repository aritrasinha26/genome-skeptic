#!/usr/bin/env python3
"""Build M60_EXCLUSION_MANIFEST.json from frozen accession lists only.

Does not select M60 cases. Does not open D20 results or any truth labels.
D20 is represented only by the candidate-pool accession list.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.eval.catalog import GENOMES  # noqa: E402
from genome_skeptic.families import family_root  # noqa: E402
from genome_skeptic.validators.ortholog_references import default_orthology_ref_root  # noqa: E402

OUT = ROOT / "manuscript_benchmark" / "M60_EXCLUSION_MANIFEST.json"
OUT_SHA = ROOT / "manuscript_benchmark" / "M60_EXCLUSION_MANIFEST.json.sha256.json"

ACC_RE = re.compile(r"\b((?:GCF|GCA)_\d+(?:\.\d+)?|(?:NC|NZ|NM|NP|WP|YP)_\d+(?:\.\d+)?)\b")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add(rows: list[dict], accession: str, source: str, reason: str) -> None:
    acc = (accession or "").strip()
    if not acc:
        return
    rows.append({"accession": acc, "source": source, "reason": reason})


def from_json_accessions(path: Path, source: str, reason: str) -> list[dict]:
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"assembly_accession", "accession", "genome_accession"} and isinstance(value, str):
                    add(found, value, source, reason)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(raw)
    return found


def from_family_assets() -> list[dict]:
    found: list[dict] = []
    root = family_root()
    if root is None:
        return found
    for yaml_path in sorted(root.glob("*/family.yaml")):
        text = yaml_path.read_text(encoding="utf-8")
        family_id = yaml_path.parent.name
        for match in ACC_RE.findall(text):
            add(found, match, f"family:{family_id}", "family_or_competitor_reference_asset")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("species:"):
                species = line.split(":", 1)[1].strip()
                add(found, species, f"family:{family_id}", "family_source_organism")
    return found


def from_ortholog_assets() -> list[dict]:
    found: list[dict] = []
    root = default_orthology_ref_root()
    if not root.exists():
        return found
    for yaml_path in sorted(root.glob("*/index.yaml")):
        text = yaml_path.read_text(encoding="utf-8")
        family_id = yaml_path.parent.name
        for match in ACC_RE.findall(text):
            add(found, match, f"ortholog_ref:{family_id}", "orthology_reference_asset")
        raw = json.loads(json.dumps(__import__("yaml").safe_load(text) or {}))
        for member in raw.get("members") or []:
            if member.get("organism"):
                add(found, str(member["organism"]), f"ortholog_ref:{family_id}", "orthology_reference_source_organism")
            if member.get("protein_id"):
                add(found, str(member["protein_id"]), f"ortholog_ref:{family_id}", "orthology_reference_protein")
    return found


def from_catalog() -> list[dict]:
    found: list[dict] = []
    for spec in GENOMES:
        add(found, spec.accession, "eval_catalog", f"catalog_{spec.split}_{spec.genome_id}")
        for extra in spec.extra_accessions:
            add(found, extra, "eval_catalog", f"catalog_{spec.split}_{spec.genome_id}_extra")
        add(found, spec.genome_id, "eval_catalog", f"catalog_genome_id_{spec.split}")
    return found


MODEL_SOURCE_GENOMES = [
    ("NC_000913.3", "Escherichia coli K-12 MG1655", "family/query source genome"),
    ("NC_000962.3", "Mycobacterium tuberculosis H37Rv", "rpoB/tuf family source genome"),
    ("NC_002516.2", "Pseudomonas aeruginosa PAO1", "development catalog / forbidden family member host"),
    ("NC_000964.3", "Bacillus subtilis 168", "development catalog"),
    ("NC_000915.1", "Helicobacter pylori 26695", "development catalog"),
]


def main() -> dict:
    rows: list[dict] = []
    sources = [
        (ROOT / "external_validation_agentic_d8" / "D8_MANIFEST.json", "D8", "D8_selected_case"),
        (ROOT / "external_validation_agentic_d12" / "D12_MANIFEST.json", "D12", "D12_selected_case"),
        (ROOT / "external_validation_agentic_d12" / "D12_CANDIDATE_POOL.json", "D12_candidate_pool", "D12_candidate_pool"),
        (
            ROOT / "external_validation_agentic_d20" / "candidate_pool_manifest.json",
            "D20_candidate_pool",
            "D20_candidate_pool_accession_only",
        ),
        (ROOT / "external_validation" / "cohort_A_naturalistic_manifest.json", "cohort_A", "previous_external_cohort"),
        (ROOT / "external_validation_agentic" / "cohort_C_manifest.json", "cohort_C", "previous_external_cohort"),
        (ROOT / "external_validation_agentic" / "cohort_C_pilot5_manifest.json", "cohort_C_pilot5", "previous_external_cohort"),
        (ROOT / "dev_work" / "agentic_gate" / "agentic_internal_gate_manifest.json", "agentic_internal_gate", "controlled_capability_test"),
    ]
    used_files = []
    for path, source, reason in sources:
        extracted = from_json_accessions(path, source, reason)
        rows.extend(extracted)
        used_files.append(
            {
                "path": path.relative_to(ROOT).as_posix() if path.exists() else path.as_posix(),
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
                "n_records": len(extracted),
                "d20_results_opened": False,
            }
        )
    rows.extend(from_catalog())
    rows.extend(from_family_assets())
    rows.extend(from_ortholog_assets())
    for acc, name, reason in MODEL_SOURCE_GENOMES:
        add(rows, acc, "reference_source_genome", reason)
        add(rows, name, "reference_source_genome", reason)

    # Deduplicate while preserving first source/reason.
    seen: dict[str, dict] = {}
    for row in rows:
        key = row["accession"]
        if key not in seen:
            seen[key] = {
                "accession": key,
                "sources": [row["source"]],
                "reasons": [row["reason"]],
            }
        else:
            if row["source"] not in seen[key]["sources"]:
                seen[key]["sources"].append(row["source"])
            if row["reason"] not in seen[key]["reasons"]:
                seen[key]["reasons"].append(row["reason"])
    excluded = [seen[k] for k in sorted(seen)]
    payload = {
        "kind": "M60_EXCLUSION_MANIFEST",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seed": "20260920",
        "m60_cases_selected": False,
        "d8_rerun": False,
        "d12_rerun": False,
        "d20_touched": False,
        "d20_results_opened": False,
        "external_truth_opened": False,
        "note": (
            "Accession/identifier exclusion set frozen before M60 case selection. "
            "D20 contributed only candidate-pool accessions. No D20 predictions or labels were read."
        ),
        "source_files": used_files,
        "n_excluded": len(excluded),
        "excluded": excluded,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    digest = sha256_file(OUT)
    sidecar = {
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "hashed_utc": datetime.now(timezone.utc).isoformat(),
        "n_excluded": len(excluded),
        "m60_cases_selected": False,
        "d20_touched": False,
    }
    OUT_SHA.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    print(f"EXCLUSION {OUT}")
    print(f"SHA256 {digest}")
    print(f"N {len(excluded)}")
    return {"path": str(OUT), "sha256": digest, "n_excluded": len(excluded)}


if __name__ == "__main__":
    main()
