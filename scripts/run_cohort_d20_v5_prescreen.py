#!/usr/bin/env python3
"""Gate 1 Step 2: frozen deterministic V5 prescreen on the locked 40-case D20 pool.

Does not run Agentic V2, planner, critic, or conventional.
Does not access external truth. Does not modify frozen scientific source.
"""
from __future__ import annotations

import faulthandler
import hashlib
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

from genome_skeptic.config import load_settings
from genome_skeptic.eval.evaluate_real import _run_system
from genome_skeptic.families import load_family
from genome_skeptic.io_utils import iter_fasta_records

OUT = ROOT / "external_validation_agentic_d20"
POOL = OUT / "candidate_pool_manifest.json"
POOL_LOCK = OUT / "candidate_pool_manifest.json.sha256.json"
RUNS = OUT / "v5_prescreen"
TARGETS_FA = OUT / "inputs" / "targets.fa"
EMPTY_REFS = OUT / "inputs" / "references.yaml"
EXPECTED_POOL = "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c"
EXPECTED_FREEZE = "736bd2bdc34b1967a429602903f26ebfa5cdb031c6787a7f0ebf77926517c696"
V5_YAML = ROOT / "config" / "qwen_external_v5.yaml"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_targets() -> None:
    chunks = []
    for fid in (
        "rpoB_RNAP_beta",
        "tuf_EF_Tu",
        "lacZ_beta_galactosidase",
        "tetA_tetracycline_efflux",
    ):
        fam = load_family(fid)
        if not fam or not fam.members:
            raise SystemExit(f"frozen family missing: {fid}")
        member = max(fam.members, key=lambda m: len(m.sequence or ""))
        seq = member.sequence
        chunks.append(f">{fid} target_type=gene_orthologue family={fid} length_aa={len(seq)}\n{seq}\n")
    TARGETS_FA.parent.mkdir(parents=True, exist_ok=True)
    TARGETS_FA.write_text("".join(chunks), encoding="utf-8")
    if not EMPTY_REFS.exists():
        EMPTY_REFS.write_text("references: []\n", encoding="utf-8")


def stage_fasta(src: Path, acc: str, expected: str) -> Path:
    """Copy solver FASTA onto a Linux filesystem when WSL 9p is unreliable."""
    linux_root = Path("/home/aritr/d20_v5_work/fasta")
    if not Path("/home/aritr").exists():
        return src
    linux_root.mkdir(parents=True, exist_ok=True)
    dest = linux_root / f"{acc}.fna"
    if dest.exists() and sha256_file(dest) == expected:
        return dest
    shutil.copyfile(src, dest)
    got = sha256_file(dest)
    if got != expected:
        raise SystemExit(f"staged FASTA hash mismatch {acc}: {got}")
    return dest


def start_heartbeat() -> None:
    def _beat() -> None:
        n = 0
        while True:
            n += 1
            print(f"heartbeat {n}", flush=True)
            time.sleep(10)
    threading.Thread(target=_beat, daemon=True).start()


def write_one_target(dest: Path, query_id: str) -> None:
    chosen = [(header, seq) for seq_id, header, seq in iter_fasta_records(TARGETS_FA) if seq_id == query_id]
    if not chosen:
        raise SystemExit(f"missing target {query_id}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    header, seq = chosen[0]
    dest.write_text(f">{header}\n{seq}\n", encoding="utf-8")


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def snapshot_case(sys_dir: Path, target: str, seconds: float, reused: bool) -> dict:
    claims = load_json(sys_dir / "claims.json") or []
    claim = next((c for c in claims if c.get("claim_id", "").endswith(target) or target in str(c.get("claim_id"))), None)
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
    m0_hash = sha256_text(json.dumps(m0_blob, sort_keys=True, default=str))
    tests = []
    for t in (claim or {}).get("falsification_tests") or []:
        tests.append(
            {
                "test_id": t.get("test_id"),
                "status": t.get("status"),
                "result": t.get("result"),
            }
        )
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
        "m0_hash": m0_hash,
        "runtime_seconds": seconds,
        "reused": reused,
        "family_evidence_path": str((sys_dir / "family" / target / "family_evidence.json").relative_to(ROOT)).replace("\\", "/"),
        "claims_path": str((sys_dir / "claims.json").relative_to(ROOT)).replace("\\", "/"),
        "hits_path": str((sys_dir / "search" / "gene_search_hits.json").relative_to(ROOT)).replace("\\", "/"),
    }


def main() -> int:
    freeze = ROOT / "agentic_freeze" / "GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json"
    if sha256_file(freeze) != EXPECTED_FREEZE:
        raise SystemExit("freeze hash mismatch; abort")
    lock = json.loads(POOL_LOCK.read_text(encoding="utf-8"))
    actual = sha256_file(POOL)
    if actual != lock.get("sha256") or actual != EXPECTED_POOL:
        raise SystemExit(f"candidate pool hash mismatch: {actual}")
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    write_targets()
    settings = load_settings(V5_YAML)
    RUNS.mkdir(parents=True, exist_ok=True)
    start_heartbeat()
    rows = []
    for rec in pool["candidates"]:
        acc = rec["assembly_accession"]
        target = rec["target"]
        assembly = stage_fasta(ROOT / rec["solver_fasta"], acc, rec["fasta_sha256"])
        case_dir = RUNS / acc / target
        sys_dir = case_dir / "genome_skeptic"
        locked = case_dir / "v5_case.json"
        print(f"V5 {acc} {target}", flush=True)
        if locked.exists():
            snap = json.loads(locked.read_text(encoding="utf-8"))
            rows.append(snap)
            print("reuse", acc, target, flush=True)
            continue
        one = case_dir / "target.fa"
        write_one_target(one, target)
        work_dir = sys_dir
        work_target = one
        linux_out = Path(f"/home/aritr/d20_v5_work/runs/{acc}/{target}/genome_skeptic")
        if Path("/home/aritr").exists():
            linux_out.mkdir(parents=True, exist_ok=True)
            work_dir = linux_out
            work_target = linux_out.parent / "target.fa"
            shutil.copyfile(one, work_target)
        print(f"run {acc} {target} fasta={assembly} out={work_dir}", flush=True)
        t0 = time.perf_counter()
        try:
            payload = _run_system(
                "genome_skeptic",
                assembly,
                work_target,
                work_dir,
                settings,
                EMPTY_REFS if EMPTY_REFS.exists() else None,
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
            print(tb, file=sys.stderr, flush=True)
            fail = case_dir / "v5_failure.json"
            fail.write_text(
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
            "agentic_v2_executed": False,
            "planner_called": False,
            "critic_called": False,
            **snapshot_case(sys_dir, target, seconds, bool(payload.get("reused"))),
        }
        locked.write_text(json.dumps(snap, indent=2, default=str) + "\n", encoding="utf-8")
        rows.append(snap)
        print(f"done {acc} {target} class={snap.get('claim_class')} {seconds:.1f}s", flush=True)
    summary = {
        "kind": "d20_v5_prescreen_summary",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(rows),
        "candidate_pool_sha256": actual,
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V2_D20",
        "agentic_v2_executed": False,
        "planner_called": False,
        "critic_called": False,
        "external_labels_opened": False,
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
    dest = OUT / "v5_prescreen_summary.json"
    dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("V5_PRESCREEN_DONE", len(rows), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
