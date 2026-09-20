#!/usr/bin/env python3
"""One D12 development replay for GENOME_SKEPTIC_V4_1_DEV.

TUF positions 6 and 9, LacZ positions 5, 7, 8, and tetA routing
confirmation for 1, 3, 11. Development only. Do not retune after this run.
Does not modify frozen V5/V3, D8/D12 locks, D20, or previous manifests.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / "scripts"))

from d12_common import (  # noqa: E402
    AGENTIC_YAML,
    D20_DIR,
    OUT,
    assert_d20_untouched,
    fix_llm_host,
    load_json,
    write_one_target,
    write_targets,
)
from genome_skeptic.agents.action_catalog_v4_1_dev import rank_candidate_actions  # noqa: E402
from genome_skeptic.agents.assembly_loop import collect_assembly_target_measurements  # noqa: E402
from genome_skeptic.agents.assembly_loop_v2 import BASELINE_WORK, _LoopState, capabilities_for  # noqa: E402
from genome_skeptic.agents.assembly_loop_v4_1_dev import (  # noqa: E402
    capabilities_for_v4_1,
    persist_repaired_measurements,
    run_skeptic_agentic_v4_1_dev,
)
from genome_skeptic.agents.diagnostic_needs_v4_1_dev import derive_diagnostic_needs_v4_1_dev  # noqa: E402
from genome_skeptic.agents.providers import reset_call_log  # noqa: E402
from genome_skeptic.config import load_settings  # noqa: E402
from genome_skeptic.validators.locus_stages_v4_1_dev import repair_loci_v4_1  # noqa: E402

TUF_POSITIONS = (6, 9)
LACZ_POSITIONS = (5, 7, 8)
TETA_POSITIONS = (1, 3, 11)
DEV_OUT = ROOT / "dev_work" / "agentic_v4_1_dev" / "d12_replay"
TRUTH = {
    1: {"kind": "family", "truth": "NEGATIVE"},
    3: {"kind": "family", "truth": "NEGATIVE"},
    5: {"kind": "lacz", "truth": "POSITIVE"},
    6: {"kind": "multiplicity", "truth": 1},
    7: {"kind": "lacz", "truth": "NEGATIVE"},
    8: {"kind": "lacz", "truth": "POSITIVE"},
    9: {"kind": "multiplicity", "truth": 2},
    11: {"kind": "family", "truth": "NEGATIVE"},
}


def _sha256_dir_listing(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())


def _v3_row(lock: dict, acc: str, target: str) -> dict:
    for row in lock.get("predictions") or []:
        if row.get("assembly_accession") == acc and row.get("target") == target:
            return row
    return {}


def _endpoint(claim) -> str:
    return claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)


def _confirm_teta_routing(cases: dict, settings, targets_fa: Path) -> list[dict]:
    rows = []
    for pos in TETA_POSITIONS:
        case = cases[pos]
        acc = case["assembly_accession"]
        target = case["target"]
        fasta = ROOT / case["solver_fasta"]
        one = DEV_OUT / "targets" / f"{acc}_{target}.fa"
        write_one_target(targets_fa, one, target)
        run_dir = DEV_OUT / "teta_routing" / acc / target
        run_dir.mkdir(parents=True, exist_ok=True)
        state = _LoopState(
            settings=settings,
            assembly=fasta,
            targets=one,
            out_dir=run_dir,
            declared_organism=None,
            mapping_sam=None,
            depth_tsv=None,
            assembly_gff=None,
            proteins_path=None,
            references_yaml=None,
        )
        measurements, _loci_ev = collect_assembly_target_measurements(state, query_ids=[target])
        repair_loci_v4_1(measurements, settings)
        caps = capabilities_for_v4_1(state, measurements)
        needs = derive_diagnostic_needs_v4_1_dev(measurements, caps, settings=settings)
        ranked = rank_candidate_actions(needs, caps, BASELINE_WORK, measurements, limit=3)
        ids = [row["action_id"] for row in ranked]
        rows.append(
            {
                "position": pos,
                "assembly_accession": acc,
                "target": target,
                "diagnostic_needs": needs,
                "ranked_actions": ids,
                "routes_to_competitive_family": bool(ids) and ids[0] == "competitive_family",
            }
        )
    return rows


def _replay_case(pos: int, case: dict, settings, targets_fa: Path, v3_lock: dict) -> dict:
    acc = case["assembly_accession"]
    target = case["target"]
    fasta = ROOT / case["solver_fasta"]
    one = DEV_OUT / "targets" / f"{acc}_{target}.fa"
    write_one_target(targets_fa, one, target)
    run_dir = DEV_OUT / "runs" / acc / target
    if run_dir.exists():
        import shutil

        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    reset_call_log()
    claims, _loci_ev, prov = run_skeptic_agentic_v4_1_dev(fasta, one, run_dir, settings, query_ids=[target])
    claim = claims[0]
    v3 = _v3_row(v3_lock, acc, target)
    fam = load_json(run_dir / "family" / target / "family_evidence.json") or {}
    recon = fam.get("reconstruction") or {}
    multi = recon.get("multiplicity") or {}
    competitive = recon.get("competitive_family") or {}
    ortholog = recon.get("ortholog_reference_discrimination") or {}
    stages = prov.get("locus_stages_m_final") or load_json(run_dir / "locus_stages.json") or {}
    executed = []
    for row in prov.get("actions_executed") or []:
        if isinstance(row, dict):
            executed.append(row.get("action_id") or (row.get("result") or {}).get("action_id"))
        else:
            executed.append(str(row))
    offered = [row.get("action_id") if isinstance(row, dict) else row for row in (prov.get("ranked_candidate_actions") or [])]
    return {
        "position": pos,
        "assembly_accession": acc,
        "target": target,
        "v3_original_endpoint": v3.get("final_result"),
        "v4_1_dev_endpoint": _endpoint(claim),
        "truth": TRUTH[pos]["truth"],
        "diagnostic_needs": prov.get("diagnostic_needs_m0"),
        "candidate_actions": offered,
        "action_chosen": prov.get("selected_action"),
        "critic_action": prov.get("critic_second_action"),
        "actions_executed": executed,
        "raw_hits": (stages.get("stages") or stages).get("n_source_hits") if isinstance(stages, dict) else None,
        "accepted_biological_candidates": (stages.get("stages") or stages).get("n_accepted") if isinstance(stages, dict) else None,
        "reconstructed_loci": multi.get("number_of_candidate_loci"),
        "locus_coordinates": multi.get("coordinates"),
        "multiplicity": multi.get("classification"),
        "locus_stages": stages,
        "family_classification": competitive.get("classification"),
        "ortholog_classification": ortholog.get("classification"),
        "claim_class": claim.status.value if hasattr(claim.status, "value") else claim.status,
        "architecture": claim.architecture_state,
        "competitive_family_offered": "competitive_family" in offered,
        "competitive_family_executed": "competitive_family" in executed,
        "ortholog_action_offered": "competitive_ortholog_references" in offered,
        "ortholog_action_executed": "competitive_ortholog_references" in executed,
    }


def main() -> int:
    d20_before = _sha256_dir_listing(D20_DIR)
    assert_d20_untouched("v4_1_dev_replay_start")
    manifest = json.loads((OUT / "D12_MANIFEST.json").read_text(encoding="utf-8"))
    v3_lock = json.loads((OUT / "D12_AGENTIC_V3_LOCKED.json").read_text(encoding="utf-8"))
    cases = {int(c["execution_position"]): c for c in manifest["cases"]}
    settings = load_settings(AGENTIC_YAML)
    fix_llm_host(settings)
    targets_fa = OUT / "inputs" / "targets.fa"
    write_targets(targets_fa)
    DEV_OUT.mkdir(parents=True, exist_ok=True)
    teta_rows = _confirm_teta_routing(cases, settings, targets_fa)
    reports = []
    for pos in TUF_POSITIONS + LACZ_POSITIONS:
        reports.append(_replay_case(pos, cases[pos], settings, targets_fa, v3_lock))
    d20_after = _sha256_dir_listing(D20_DIR)
    assert_d20_untouched("v4_1_dev_replay_end")
    if d20_after != d20_before:
        raise SystemExit("D20 was touched during V4.1-dev replay")
    payload = {
        "kind": "GENOME_SKEPTIC_V4_1_DEV_D12_REPLAY",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "tuf_positions": list(TUF_POSITIONS),
        "lacz_positions": list(LACZ_POSITIONS),
        "teta_routing": teta_rows,
        "d20_touched": False,
        "m80_cases_selected": False,
        "reports": reports,
    }
    (DEV_OUT / "D12_V4_1_DEV_REPLAY.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
