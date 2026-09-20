#!/usr/bin/env python3
"""One targeted D12 development replay for GENOME_SKEPTIC_V4_DEV.

Replays ONLY positions 1, 3, 6, 9, 11. Does not rerun all D12.
Does not modify D12 locks, D8 locks, frozen V5, V3 external freeze, or D20.
This is development, not validation. Do not tune after seeing the report.
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
from genome_skeptic.agents.assembly_loop_v4_dev import CURRENT_LACZ_LIMITATION, run_skeptic_agentic_v4_dev  # noqa: E402
from genome_skeptic.agents.providers import reset_call_log  # noqa: E402
from genome_skeptic.config import load_settings  # noqa: E402
from genome_skeptic.validators.locus_v4_dev import _loci  # noqa: E402

DEV_POSITIONS = (1, 3, 6, 9, 11)
DEV_OUT = ROOT / "dev_work" / "agentic_v4_dev" / "d12_replay"
TRUTH = {
    1: {"kind": "family", "truth": "NEGATIVE"},
    3: {"kind": "family", "truth": "NEGATIVE"},
    6: {"kind": "multiplicity", "truth": 1},
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
    ctype = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
    return ctype


def main() -> int:
    d20_before = _sha256_dir_listing(D20_DIR)
    assert_d20_untouched("v4_dev_replay_start")
    manifest = json.loads((OUT / "D12_MANIFEST.json").read_text(encoding="utf-8"))
    v3_lock = json.loads((OUT / "D12_AGENTIC_V3_LOCKED.json").read_text(encoding="utf-8"))
    cases = {int(c["execution_position"]): c for c in manifest["cases"]}
    settings = load_settings(AGENTIC_YAML)
    fix_llm_host(settings)
    targets_fa = OUT / "inputs" / "targets.fa"
    write_targets(targets_fa)
    DEV_OUT.mkdir(parents=True, exist_ok=True)
    reports = []
    for pos in DEV_POSITIONS:
        case = cases[pos]
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
        claims, _loci_ev, prov = run_skeptic_agentic_v4_dev(
            fasta, one, run_dir, settings, query_ids=[target]
        )
        claim = claims[0]
        v3 = _v3_row(v3_lock, acc, target)
        fam = load_json(run_dir / "family" / target / "family_evidence.json") or {}
        recon = (fam.get("reconstruction") or {})
        multi = recon.get("multiplicity") or {}
        competitive = recon.get("competitive_family") or fam.get("competitive_family") or {}
        hits = load_json(run_dir / "search" / "gene_search_hits.json") or []
        if not hits:
            hits = load_json(run_dir / "family" / target / "search" / "gene_search_hits.json") or []
        executed = []
        for row in prov.get("actions_executed") or []:
            if isinstance(row, dict):
                executed.append(row.get("action_id") or (row.get("result") or {}).get("action_id"))
            else:
                executed.append(str(row))
        offered = [row.get("action_id") if isinstance(row, dict) else row for row in (prov.get("ranked_candidate_actions") or [])]
        v4_endpoint = _endpoint(claim)
        changed = v4_endpoint != v3.get("final_result")
        if target == "tuf_EF_Tu":
            n_loci = int(multi.get("number_of_candidate_loci") or 0)
            changed = n_loci != 0 and n_loci != (0)
        rec = {
            "position": pos,
            "assembly_accession": acc,
            "target": target,
            "v3_original_endpoint": v3.get("final_result"),
            "v4_dev_endpoint": v4_endpoint,
            "truth": TRUTH[pos]["truth"],
            "diagnostic_needs": prov.get("diagnostic_needs_m0"),
            "candidate_actions": offered,
            "action_chosen": prov.get("selected_action"),
            "critic_action": prov.get("critic_second_action"),
            "action_result": prov.get("actions_executed"),
            "m0": (prov.get("measurement_state") or {}).get("m0"),
            "m_final": (prov.get("measurement_state") or {}).get("m_final"),
            "endpoint_changed": changed,
            "why": (
                f"needs={prov.get('diagnostic_needs_m0')} chose={prov.get('selected_action')} "
                f"critic={prov.get('critic_second_action')} architecture={claim.architecture_state}"
            ),
            "competitive_family_offered": "competitive_family" in offered,
            "competitive_family_executed": "competitive_family" in executed,
            "family_classification": competitive.get("classification"),
            "raw_candidate_hits": len(hits) if isinstance(hits, list) else hits,
            "distinct_reconstructed_loci": multi.get("number_of_candidate_loci"),
            "final_multiplicity": multi.get("classification"),
            "claim_class": claim.status.value if hasattr(claim.status, "value") else claim.status,
            "confidence": claim.confidence,
            "architecture": claim.architecture_state,
        }
        reports.append(rec)
        (run_dir / "v4_dev_case_report.json").write_text(json.dumps(rec, indent=2, default=str) + "\n", encoding="utf-8")

    d20_after = _sha256_dir_listing(D20_DIR)
    assert_d20_untouched("v4_dev_replay_end")
    if d20_after != d20_before:
        raise SystemExit("D20 was touched during V4-dev replay")
    payload = {
        "kind": "GENOME_SKEPTIC_V4_DEV_D12_REPLAY",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "positions": list(DEV_POSITIONS),
        "current_lacz_limitation": CURRENT_LACZ_LIMITATION,
        "d20_touched": False,
        "reports": reports,
    }
    (DEV_OUT / "D12_V4_DEV_REPLAY.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    lines = ["# V4-dev targeted D12 development replay", "", "Development only. Not a new benchmark.", ""]
    for rec in reports:
        lines.append(f"## Position {rec['position']}: {rec['assembly_accession']} / {rec['target']}")
        lines.append("")
        lines.append(f"- V3 original endpoint: {rec['v3_original_endpoint']}")
        lines.append(f"- V4-dev endpoint: {rec['v4_dev_endpoint']}")
        lines.append(f"- truth: {rec['truth']}")
        lines.append(f"- DiagnosticNeeds: {rec['diagnostic_needs']}")
        lines.append(f"- candidate actions: {rec['candidate_actions']}")
        lines.append(f"- action chosen: {rec['action_chosen']}")
        lines.append(f"- critic action: {rec['critic_action']}")
        lines.append(f"- endpoint changed: {rec['endpoint_changed']}")
        lines.append(f"- why: {rec['why']}")
        if rec["target"] == "tetA_tetracycline_efflux":
            lines.append(f"- COMPETITIVE_FAMILY OFFERED: {'YES' if rec['competitive_family_offered'] else 'NO'}")
            lines.append(f"- COMPETITIVE_FAMILY EXECUTED: {'YES' if rec['competitive_family_executed'] else 'NO'}")
            lines.append(f"- FAMILY CLASSIFICATION RESULT: {rec['family_classification']}")
        if rec["target"] == "tuf_EF_Tu":
            lines.append(f"- raw candidate hits: {rec['raw_candidate_hits']}")
            lines.append(f"- distinct reconstructed loci: {rec['distinct_reconstructed_loci']}")
            lines.append(f"- final multiplicity: {rec['final_multiplicity']}")
        lines.append("")
    (DEV_OUT / "D12_V4_DEV_REPLAY.md").write_text("\n".join(lines), encoding="utf-8")
    print((DEV_OUT / "D12_V4_DEV_REPLAY.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
