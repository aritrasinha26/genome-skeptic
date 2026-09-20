#!/usr/bin/env python3
"""Frozen deterministic V5 prescreen on the locked 24-case D12 pool.

Does not run Agentic V3, planner, critic, or conventional.
Does not access external truth. Does not modify D20 or frozen scientific source.
"""
from __future__ import annotations

import faulthandler
import json
import shutil
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

faulthandler.enable()

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / "scripts"))

from d12_common import (  # noqa: E402
    FREEZE_ID,
    LINUX_WORK,
    OUT,
    V5_YAML,
    assert_d20_untouched,
    load_json,
    sha256_file,
    sha256_text,
    verify_v3_freeze,
    write_one_target,
    write_sha256_sidecar,
    write_targets,
)
from genome_skeptic.config import load_settings  # noqa: E402
from genome_skeptic.eval.evaluate_real import _run_system  # noqa: E402

POOL = OUT / "D12_CANDIDATE_POOL.json"
POOL_LOCK = OUT / "D12_CANDIDATE_POOL.json.sha256.json"
RUNS = OUT / "v5_prescreen"
TARGETS_FA = OUT / "inputs" / "targets.fa"
EMPTY_REFS = OUT / "inputs" / "references.yaml"


def stage_fasta(src: Path, acc: str, expected: str) -> Path:
    if not Path("/home/aritr").exists():
        return src
    dest_root = LINUX_WORK / "fasta"
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / f"{acc}.fna"
    if dest.exists() and sha256_file(dest) == expected:
        return dest
    shutil.copyfile(src, dest)
    got = sha256_file(dest)
    if got != expected:
        raise SystemExit(f"staged FASTA hash mismatch {acc}: {got}")
    return dest


def snapshot_case(sys_dir: Path, target: str, seconds: float, reused: bool) -> dict:
    claims = load_json(sys_dir / "claims.json") or []
    claim = next(
        (c for c in claims if c.get("claim_id", "").endswith(target) or target in str(c.get("claim_id"))),
        None,
    )
    if claim is None and claims:
        claim = claims[0]
    fam = load_json(sys_dir / "family" / target / "family_evidence.json") or {}
    recon = fam.get("reconstruction") or {}
    multi = recon.get("multiplicity") or fam.get("multiplicity") or {}
    hits = load_json(sys_dir / "search" / "gene_search_hits.json") or []
    if isinstance(hits, dict):
        hits = hits.get("hits") or hits.get("records") or []
    locus = load_json(sys_dir / "locus_evidence.json") or []
    m0_blob = {
        "target": target,
        "hits": hits,
        "family_evidence": fam,
        "locus_evidence_n": len(locus) if isinstance(locus, list) else None,
    }
    tests = []
    for t in (claim or {}).get("falsification_tests") or []:
        tests.append({"test_id": t.get("test_id"), "status": t.get("status"), "result": t.get("result")})
    recon_multi = recon.get("multiplicity") or {}
    if isinstance(recon_multi, dict) and recon_multi:
        multi = recon_multi
    elif isinstance(fam.get("multiplicity"), dict) and fam.get("multiplicity"):
        multi = fam.get("multiplicity")
    competitive = recon.get("competitive_family") or fam.get("competitive_family") or {}
    return {
        "target": target,
        "final_result": (claim or {}).get("claim_type"),
        "claim_class": (claim or {}).get("status"),
        "confidence": (claim or {}).get("confidence"),
        "architecture": fam.get("architecture") or (claim or {}).get("architecture_state"),
        "homology_support": (claim or {}).get("homology_support"),
        "orthology_class": (claim or {}).get("orthology_class"),
        "supports_orthologue": fam.get("supports_orthologue"),
        "statement": (claim or {}).get("statement"),
        "hits": hits,
        "family_evidence": fam,
        "locus_evidence": locus,
        "multiplicity": multi,
        "competitive_family": competitive,
        "falsification_tests": tests,
        "m0_hash": sha256_text(json.dumps(m0_blob, sort_keys=True, default=str)),
        "runtime_seconds": seconds,
        "reused": reused,
    }


def main() -> int:
    freeze = verify_v3_freeze()
    print("V3_FREEZE_OK", freeze["manifest_sha256"], flush=True)
    assert_d20_untouched("v5_prescreen_start")
    lock = json.loads(POOL_LOCK.read_text(encoding="utf-8"))
    actual = sha256_file(POOL)
    if actual != lock.get("sha256"):
        raise SystemExit(f"D12 candidate pool hash mismatch: {actual}")
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    write_targets(TARGETS_FA)
    if not EMPTY_REFS.exists():
        EMPTY_REFS.write_text("references: []\n", encoding="utf-8")
    settings = load_settings(V5_YAML)
    RUNS.mkdir(parents=True, exist_ok=True)

    def beat() -> None:
        n = 0
        while True:
            n += 1
            print(f"heartbeat {n}", flush=True)
            time.sleep(15)

    threading.Thread(target=beat, daemon=True).start()
    rows = []
    for rec in pool["candidates"]:
        acc = rec["assembly_accession"]
        target = rec["target"]
        assembly = stage_fasta(ROOT / rec["solver_fasta"], acc, rec["fasta_sha256"])
        case_dir = RUNS / acc / target
        sys_dir = case_dir / "genome_skeptic"
        locked = case_dir / "v5_case.json"
        print(f"V5 {acc} {target}", flush=True)
        if locked.exists() and locked.stat().st_size > 50:
            snap = json.loads(locked.read_text(encoding="utf-8"))
            rows.append(snap)
            print("reuse", acc, target, flush=True)
            continue
        one = case_dir / "target.fa"
        write_one_target(TARGETS_FA, one, target)
        work_dir = sys_dir
        work_target = one
        if Path("/home/aritr").exists():
            linux_out = LINUX_WORK / "v5_prescreen" / acc / target / "genome_skeptic"
            linux_out.mkdir(parents=True, exist_ok=True)
            work_dir = linux_out
            work_target = linux_out.parent / "target.fa"
            shutil.copyfile(one, work_target)
        t0 = time.perf_counter()
        try:
            payload = _run_system(
                "genome_skeptic",
                assembly,
                work_target,
                work_dir,
                settings,
                EMPTY_REFS,
                rec.get("organism"),
                None,
                None,
            )
            if work_dir != sys_dir:
                if sys_dir.exists():
                    shutil.rmtree(sys_dir)
                shutil.copytree(work_dir, sys_dir)
        except Exception as exc:
            tb = traceback.format_exc()
            (case_dir / "v5_failure.json").write_text(
                json.dumps(
                    {
                        "assembly_accession": acc,
                        "target": target,
                        "error": str(exc),
                        "traceback": tb,
                        "seconds": time.perf_counter() - t0,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            raise SystemExit(f"V5 failed on frozen candidate {acc} {target}: {exc}") from exc
        seconds = float(payload.get("seconds") or (time.perf_counter() - t0))
        snap = {
            "assembly_accession": acc,
            "target": target,
            "organism": rec.get("organism"),
            "genus": rec.get("genus"),
            "species": rec.get("species"),
            "assembly_level": rec.get("assembly_level"),
            "assembly_quality": rec.get("assembly_quality"),
            "fasta_sha256": rec["fasta_sha256"],
            "sampling_hash": rec["sampling_hash"],
            "external_labels_opened": False,
            "agentic_v3_executed": False,
            "planner_called": False,
            "critic_called": False,
            **snapshot_case(sys_dir, target, seconds, bool(payload.get("reused"))),
        }
        locked.parent.mkdir(parents=True, exist_ok=True)
        locked.write_text(json.dumps(snap, indent=2, default=str) + "\n", encoding="utf-8")
        rows.append(snap)
        print(f"done {acc} {target} class={snap.get('claim_class')} {seconds:.1f}s", flush=True)
    summary = {
        "kind": "d12_v5_prescreen_summary",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(rows),
        "candidate_pool_sha256": actual,
        "frozen_agentic_version": FREEZE_ID,
        "agentic_v3_executed": False,
        "planner_called": False,
        "critic_called": False,
        "external_labels_opened": False,
        "d20_touched": False,
        "cases": [
            {
                "assembly_accession": r["assembly_accession"],
                "target": r["target"],
                "claim_class": r.get("claim_class"),
                "final_result": r.get("final_result"),
                "m0_hash": r.get("m0_hash"),
                "runtime_seconds": r.get("runtime_seconds"),
            }
            for r in rows
        ],
    }
    dest = OUT / "D12_V5_PRESCREEN_SUMMARY.json"
    dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_sha256_sidecar(dest)
    assert_d20_untouched("v5_prescreen_end")
    print("V5_PRESCREEN_DONE", len(rows), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
