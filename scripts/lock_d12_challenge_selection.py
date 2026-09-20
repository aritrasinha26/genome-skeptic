#!/usr/bin/env python3
"""Score the 24-case D12 V5 prescreen with the frozen generic ambiguity score.

Select top 3 per target. Tie-break:
  SHA256("V3_D12_EXTERNAL|20260920|<target>|<assembly_accession>")
Do not modify thresholds. Do not downweight lacZ for the known competing-family gap.
Freeze the 12-case manifest before Agentic V3. Do not open labels. Do not touch D20.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / "scripts"))

from d12_common import (  # noqa: E402
    CURRENT_LACZ_LIMITATION,
    EXPECTED_D20_POOL,
    EXPECTED_DIGEST,
    FREEZE_ID,
    N_FINAL_PER_TARGET,
    OUT,
    SEED,
    TARGETS,
    assert_d20_untouched,
    execution_hash,
    selection_tie_hash,
    sha256_file,
    verify_v3_freeze,
    write_sha256_sidecar,
)
from genome_skeptic.config import load_settings  # noqa: E402
from lock_cohort_d20_final import score_case  # noqa: E402

POOL = OUT / "D12_CANDIDATE_POOL.json"
POOL_LOCK = OUT / "D12_CANDIDATE_POOL.json.sha256.json"
RUNS = OUT / "v5_prescreen"
V5_YAML = ROOT / "config" / "qwen_external_v5.yaml"


def main() -> None:
    freeze = verify_v3_freeze()
    print("V3_FREEZE_OK", freeze["manifest_sha256"], flush=True)
    assert_d20_untouched("selection_start")
    lock = json.loads(POOL_LOCK.read_text(encoding="utf-8"))
    pool_sha = sha256_file(POOL)
    if pool_sha != lock.get("sha256"):
        raise SystemExit(f"D12 candidate pool hash mismatch: {pool_sha}")
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    settings = load_settings(V5_YAML)
    cases = []
    for rec in pool["candidates"]:
        acc = rec["assembly_accession"]
        target = rec["target"]
        snap_path = RUNS / acc / target / "v5_case.json"
        if not snap_path.exists():
            raise SystemExit(f"missing V5 snapshot {acc} {target}")
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        scored = score_case(snap, settings)
        cases.append({**rec, **snap, **scored, "selection_tie_hash": selection_tie_hash(target, acc)})

    amb_path = OUT / "D12_CANDIDATE_AMBIGUITY_SCORES.json"
    amb_blob = {
        "kind": "d12_candidate_ambiguity_scores",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(cases),
        "score_source": "scripts/lock_cohort_d20_final.py:score_case",
        "score_modified_after_inspection": False,
        "thresholds_modified": False,
        "external_labels_opened": False,
        "lacz_not_downweighted_for_missing_competing_family_instrument": True,
        "current_lacz_limitation": CURRENT_LACZ_LIMITATION,
        "cases": [
            {
                "assembly_accession": c["assembly_accession"],
                "target": c["target"],
                "genus": c.get("genus"),
                "species": c.get("species"),
                "assembly_quality": c.get("assembly_quality"),
                "sampling_hash": c["sampling_hash"],
                "selection_tie_hash": c["selection_tie_hash"],
                "ambiguity_score": c["ambiguity_score"],
                "components": c["components"],
                "m0_hash": c.get("m0_hash"),
                "v5_claim_class": c.get("claim_class"),
                "v5_architecture": c.get("architecture"),
            }
            for c in cases
        ],
    }
    amb_path.write_text(json.dumps(amb_blob, indent=2) + "\n", encoding="utf-8")

    protocol = {
        "kind": "D12_SELECTION_PROTOCOL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": FREEZE_ID,
        "agentic_freeze_manifest_sha256": freeze["manifest_sha256"],
        "candidate_pool_sha256": pool_sha,
        "seed": SEED,
        "ambiguity_score_preregistered": True,
        "score_source": "scripts/lock_cohort_d20_final.py:score_case",
        "thresholds_modified": False,
        "ambiguity_rules": [
            {"points": 2, "rule": "candidate hit exists but no hit satisfies the frozen strong-hit gate"},
            {"points": 2, "rule": "best relevant identity within ±0.10 of frozen orthologue identity threshold"},
            {"points": 2, "rule": "best relevant query coverage within ±0.15 of frozen coverage threshold"},
            {"points": 2, "rule": "architecture in close_paralogue/divergent_full_length/domain_only/fusion/biological_split/assembly_fragmented"},
            {"points": 2, "rule": "candidate vs family/orthology disagreement or competing-family interpretation"},
            {"points": 1, "rule": "more than one candidate locus or multiplicity/copy-number ambiguous"},
            {"points": 1, "rule": "relevant hit near contig edge or possible_edge_truncation"},
            {"points": "+1 per missing/incomplete falsification category, max +2"},
            {"points": 1, "rule": "V5 final claim class weakened or unresolved"},
        ],
        "identity_threshold": settings.thresholds.gene_aa_min_identity,
        "coverage_threshold": settings.thresholds.gene_aa_min_query_coverage,
        "final_n_per_target": N_FINAL_PER_TARGET,
        "tie_break": 'SHA256("V3_D12_EXTERNAL|20260920|<target>|<assembly_accession>") ascending after higher ambiguity',
        "execution_order": 'SHA256("V3_D12_EXECUTION|20260920|<target>|<assembly_accession>") ascending',
        "lacz_not_downweighted_for_missing_competing_family_instrument": True,
        "current_lacz_limitation": CURRENT_LACZ_LIMITATION,
        "score_modified_after_inspection": False,
        "external_labels_opened": False,
        "d20_touched": False,
        "d20_candidate_pool_sha256": EXPECTED_D20_POOL,
    }

    by_target: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        by_target[case["target"]].append(case)

    def ranked(pool_cases: list[dict]) -> list[dict]:
        return sorted(
            pool_cases,
            key=lambda c: (-int(c["ambiguity_score"]), c["selection_tie_hash"], c["assembly_accession"]),
        )

    selected: list[dict] = []
    for target in TARGETS:
        pool_cases = by_target[target]
        if len(pool_cases) < N_FINAL_PER_TARGET:
            raise SystemExit(f"underfilled {target}: {len(pool_cases)}")
        picked = ranked(pool_cases)[:N_FINAL_PER_TARGET]
        for i, cand in enumerate(picked, start=1):
            cand["selection_rank"] = i
        selected.extend(picked)

    selected.sort(key=lambda c: (execution_hash(c["target"], c["assembly_accession"]), c["assembly_accession"]))
    for i, rec in enumerate(selected, start=1):
        rec["execution_position"] = i
        rec["execution_hash"] = execution_hash(rec["target"], rec["assembly_accession"])

    proto_path = OUT / "D12_SELECTION_PROTOCOL.json"
    proto_path.write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")

    final_rows = []
    for rec in selected:
        final_rows.append(
            {
                "execution_position": rec["execution_position"],
                "assembly_accession": rec["assembly_accession"],
                "organism": rec.get("organism"),
                "genus": rec.get("genus"),
                "species": rec.get("species"),
                "target": rec["target"],
                "release_date": rec.get("release_date"),
                "assembly_level": rec.get("assembly_level"),
                "assembly_quality": rec.get("assembly_quality"),
                "solver_fasta": rec.get("solver_fasta"),
                "fasta_sha256": rec.get("fasta_sha256"),
                "sampling_hash": rec.get("sampling_hash"),
                "selection_tie_hash": rec["selection_tie_hash"],
                "execution_hash": rec["execution_hash"],
                "ambiguity_score": rec["ambiguity_score"],
                "ambiguity_score_components": rec["components"],
                "selection_rank": rec["selection_rank"],
                "pool_stratum": rec.get("pool_stratum"),
                "prescreen_v5_reference": str(
                    (RUNS / rec["assembly_accession"] / rec["target"] / "v5_case.json").relative_to(ROOT)
                ).replace("\\", "/"),
                "frozen_m0_hash": rec.get("m0_hash"),
                "prescreen_v5_final_result": rec.get("final_result"),
                "prescreen_v5_claim_class": rec.get("claim_class"),
                "prescreen_v5_architecture": rec.get("architecture"),
                "external_labels_opened": False,
            }
        )

    lacz_selected = [r for r in final_rows if r["target"] == "lacZ_beta_galactosidase"]
    final_manifest = {
        "kind": "D12_MANIFEST",
        "name": "V3_D12_EXTERNAL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": FREEZE_ID,
        "agentic_freeze_manifest_sha256": freeze["manifest_sha256"],
        "candidate_pool_sha256": pool_sha,
        "model": "qwen3:4b",
        "model_digest": EXPECTED_DIGEST,
        "seed": SEED,
        "sampling_hash_formula": 'SHA256("V3_D12_POOL|20260920|<target>|<assembly_accession>")',
        "selection_tie_break_formula": 'SHA256("V3_D12_EXTERNAL|20260920|<target>|<assembly_accession>")',
        "execution_hash_formula": 'SHA256("V3_D12_EXECUTION|20260920|<target>|<assembly_accession>")',
        "n_cases": len(final_rows),
        "target_counts": {t: sum(1 for r in final_rows if r["target"] == t) for t in TARGETS},
        "assembly_quality_counts": {
            "complete_or_chromosome": sum(1 for r in final_rows if r["assembly_quality"] == "complete_or_chromosome"),
            "scaffold_or_contig": sum(1 for r in final_rows if r["assembly_quality"] == "scaffold_or_contig"),
        },
        "n_unique_genomes": len({r["assembly_accession"] for r in final_rows}),
        "n_unique_species": len({r["species"] for r in final_rows}),
        "n_unique_genera": len({r["genus"] for r in final_rows}),
        "d8_excluded": True,
        "d20_pool_excluded": True,
        "d20_candidate_pool_sha256": EXPECTED_D20_POOL,
        "d20_directory_modified": False,
        "external_labels_opened": False,
        "gene_content_used_for_selection": False,
        "challenge_enriched": True,
        "v5_used_for_selection": True,
        "ambiguity_score_used": True,
        "agentic_v3_executed": False,
        "conventional_executed": False,
        "frozen_before_agentic_v3": True,
        "current_lacz_limitation": CURRENT_LACZ_LIMITATION,
        "lacz_not_downweighted_for_missing_competing_family_instrument": True,
        "n_lacz_selected": len(lacz_selected),
        "cases": final_rows,
    }
    if any(v != N_FINAL_PER_TARGET for v in final_manifest["target_counts"].values()):
        raise SystemExit(f"target counts not 3 each: {final_manifest['target_counts']}")
    if len(final_rows) != 12:
        raise SystemExit(f"expected 12 cases, got {len(final_rows)}")

    final_json = OUT / "D12_MANIFEST.json"
    final_json.write_text(json.dumps(final_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    final_csv = OUT / "D12_MANIFEST.csv"
    fields = [
        "execution_position",
        "assembly_accession",
        "organism",
        "genus",
        "species",
        "target",
        "release_date",
        "assembly_level",
        "assembly_quality",
        "fasta_sha256",
        "sampling_hash",
        "selection_tie_hash",
        "execution_hash",
        "ambiguity_score",
        "selection_rank",
        "solver_fasta",
    ]
    with final_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in final_rows:
            w.writerow(row)

    hashes = {}
    for path in (amb_path, proto_path, final_json, final_csv):
        digest = write_sha256_sidecar(path, {"frozen_before_agentic_v3": path.name.startswith("D12_MANIFEST")})
        hashes[path.name] = digest
        print(path.name, digest, flush=True)
    assert_d20_untouched("selection_end")
    print(
        json.dumps(
            {
                "n_final": len(final_rows),
                "targets": final_manifest["target_counts"],
                "quality": final_manifest["assembly_quality_counts"],
                "hashes": hashes,
                "UNBLIND": "NO",
                "D20_TOUCHED": "NO",
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
