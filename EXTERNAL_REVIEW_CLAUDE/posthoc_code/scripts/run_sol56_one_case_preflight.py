#!/usr/bin/env python3
"""One-case post-hoc Sol ablation preflight.

Calls the real production GS_AGENTIC_V4_1 path (run_gs_agentic_v4_1).
Does not modify the frozen manuscript lock, truth, prompts, or validator.
Does not score accuracy.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from genome_skeptic.agents.providers import (  # noqa: E402
    CALL_LOG,
    SOL_ABLATION_ID,
    SOL_MODEL,
    SOL_PROVIDER,
    SOL_REASONING_EFFORT,
    reset_call_log,
    sol_ablation_overlay,
)
from genome_skeptic.config import load_settings  # noqa: E402
from genome_skeptic.families import load_family  # noqa: E402
from genome_skeptic.manuscript.arms import run_gs_agentic_v4_1  # noqa: E402
from genome_skeptic.manuscript.scientific_core import scientific_core_hashes  # noqa: E402

ABLATION_YAML = ROOT / "config" / "sol56_high_posthoc.yaml"
OUT_ROOT = ROOT / "manuscript_benchmark" / "ABLATION_SOL56_HIGH_POSTHOC" / "preflight"
EXPECTED_CORE = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"
EXPECTED_INVARIANT_HASHES = {
    "target_measurements_schema_hash": "ef902b8b968fb5b78f183d2ffe8b1681f98e9799645fb0e598225bbdd6f62487",
    "biological_thresholds_hash": "c4ef9a307df7e5493eddfa308ce1d497636ddadb2e4b4604061ea68979d97df4",
    "action_registry_hash": "185390460dd990516b89eab036b5c5da11e2d28ef3371c5e4917a4e2fd6ac899",
    "endpoint_contracts_hash": "00d5d9618414e16ca69a1d9ec1ff3178c6a980c76e5d8dab455e78064c98aa44",
    "planner_prompt_hash": "fcffbc11cf6afbe84731c15854d37e85d929b966318acc45567f5332819d0f63",
    "critic_prompt_hash": "8b04802de10aea03d24b26633a17d68415db74db3ba82034b6b8d1cf75f2b60e",
}
PREFLIGHT_POSITION = 1


def manuscript_root() -> Path:
    env = os.environ.get("GENOME_SKEPTIC_M60_ROOT")
    if env:
        return Path(env)
    candidates = [
        ROOT.parent / "GenomeSkeptic_Cursor",
        Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"),
        Path(r"C:\Users\aritr\Downloads\GenomeSkeptic_Cursor\GenomeSkeptic_Cursor"),
    ]
    for cand in candidates:
        if (cand / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json").exists():
            return cand
    raise SystemExit("frozen M60 cohort manifest not found; set GENOME_SKEPTIC_M60_ROOT")


def load_case(position: int) -> dict:
    manifest = manuscript_root() / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for rec in data["cases"]:
        if int(rec["execution_position"]) == int(position):
            return rec
    raise SystemExit(f"no M60 case at position {position}")


def solver_fasta(rec: dict) -> Path:
    acc = rec["accession"]
    names = [f"{acc}.fna", f"{acc}.fasta", f"{acc}.fa"]
    roots = [
        Path("/home/aritr/m60_work/fasta/solver"),
        manuscript_root() / "manuscript_benchmark" / "m60_work" / "fasta" / "solver",
        ROOT / "manuscript_benchmark" / "m60_work" / "fasta" / "solver",
    ]
    for root in roots:
        for name in names:
            path = root / name
            if path.exists() and path.stat().st_size > 1000:
                return path
    raise SystemExit(
        f"frozen solver FASTA for {acc} not found; reuse the existing M60 solver fasta, do not invent sequences"
    )


def write_target_fa(dest: Path, target: str) -> None:
    fam = load_family(target)
    if fam is None or not fam.members:
        raise SystemExit(f"missing frozen family {target}")
    member = max(fam.members, key=lambda m: len(m.sequence or ""))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        f">{target} target_type=gene_orthologue family={target} length_aa={len(member.sequence or '')}\n{member.sequence}\n",
        encoding="utf-8",
    )


def sol_confirmed(call_log: list[dict], role: str) -> bool:
    rows = [r for r in call_log if r.get("role") == role]
    if not rows:
        return False
    return all(
        r.get("provider") == SOL_PROVIDER
        and r.get("model") == SOL_MODEL
        and r.get("reasoning_effort") == SOL_REASONING_EFFORT
        for r in rows
    )


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise SystemExit("OPENAI_API_KEY is not set")
    hashes = scientific_core_hashes()
    for key, expected in EXPECTED_INVARIANT_HASHES.items():
        got = hashes[key]
        if got != expected:
            raise SystemExit(f"scientific invariant {key} changed: {got} != {expected}")
    rec = load_case(PREFLIGHT_POSITION)
    assembly = solver_fasta(rec)
    settings = load_settings(ABLATION_YAML)
    if settings.llm.model != SOL_MODEL or settings.llm.provider != "openai_api":
        raise SystemExit("ablation yaml does not select gpt-5.6-sol / openai_api")
    out_dir = OUT_ROOT / rec["case_id"] / "GS_AGENTIC_V4_1_SOL56_HIGH_POSTHOC"
    if out_dir.exists():
        raise SystemExit(f"preflight output already exists: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    target_fa = out_dir / "target.fa"
    write_target_fa(target_fa, rec["target"])
    reset_call_log()
    started = time.perf_counter()
    start_iso = datetime.now(timezone.utc).isoformat()
    claims, _loci, provenance = run_gs_agentic_v4_1(
        assembly,
        target_fa,
        out_dir,
        settings,
        declared_organism=rec.get("organism"),
        query_ids=[rec["target"]],
    )
    elapsed = round(time.perf_counter() - started, 3)
    overlay = sol_ablation_overlay(CALL_LOG)
    provenance.update(overlay)
    provenance["scientific_invariant_hashes"] = {k: hashes[k] for k in EXPECTED_INVARIANT_HASHES}
    provenance["scientific_core_hash_computed"] = hashes["scientific_core_hash"]
    provenance["scientific_core_hash_manuscript"] = EXPECTED_CORE
    provenance["preflight_case_id"] = rec["case_id"]
    provenance["preflight_target"] = rec["target"]
    provenance["preflight_accession"] = rec["accession"]
    provenance["preflight_position"] = rec["execution_position"]
    provenance["preflight_start_time"] = start_iso
    provenance["preflight_total_runtime_seconds"] = elapsed
    provenance["truth_opened"] = False
    provenance["accuracy_scored"] = False
    (out_dir / "agentic_provenance.json").write_text(
        json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (out_dir / "call_log.json").write_text(json.dumps(CALL_LOG, indent=2, default=str) + "\n", encoding="utf-8")
    claim = claims[0] if claims else None
    endpoint = None
    if claim is not None:
        endpoint = claim.claim_type.value if hasattr(claim.claim_type, "value") else claim.claim_type
    planner_ok = sol_confirmed(CALL_LOG, "planner") and bool(provenance.get("planner_invoked"))
    critic_ok = sol_confirmed(CALL_LOG, "critic") and bool(provenance.get("critic_invoked"))
    followups = list(provenance.get("actions_executed") or [])
    summary = {
        "POST_HOC_MODEL_ABLATION": True,
        "MANUSCRIPT_PRIMARY_SYSTEM": False,
        "ablation_config": SOL_ABLATION_ID,
        "case_id": rec["case_id"],
        "target": rec["target"],
        "planner_action": provenance.get("selected_action") or provenance.get("control_decision"),
        "critic_result_or_action": provenance.get("critic_second_action")
        or ((provenance.get("critic_challenge") or {}).get("verdict")),
        "deterministic_follow_up_count": len(followups),
        "final_endpoint": endpoint,
        "planner_latency": provenance.get("planner_seconds"),
        "critic_latency": provenance.get("critic_seconds"),
        "total_runtime": elapsed,
        "input_tokens": overlay.get("sol_input_tokens"),
        "output_tokens": overlay.get("sol_output_tokens"),
        "reasoning_tokens": overlay.get("sol_reasoning_tokens"),
        "total_sol_tokens": overlay.get("sol_total_tokens"),
        "estimated_api_cost_usd": overlay.get("estimated_api_cost_usd"),
        "planner_sol_call_confirmed": planner_ok,
        "critic_sol_call_confirmed": critic_ok,
        "agent_failure": provenance.get("agent_failure"),
        "final_validator_ran": provenance.get("final_validator_ran"),
        "model_name": provenance.get("model_name"),
        "truth_opened": False,
        "accuracy_scored": False,
        "output_dir": str(out_dir),
    }
    (out_dir / "preflight_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    if not planner_ok or not critic_ok or provenance.get("agent_failure") or not provenance.get("final_validator_ran"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
