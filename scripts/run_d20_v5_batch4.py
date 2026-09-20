#!/usr/bin/env python3
"""Gate 1 small batch: exactly 4 frozen V5 cases after the completed preflight case.

Does not modify scientific source. Does not rerun GCF_048282645.1.
Does not run Agentic V2, planner, critic, conventional, or the remaining 35.
"""
from __future__ import annotations

import faulthandler
import hashlib
import json
import os
import resource
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

faulthandler.enable()

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
if not ROOT.exists():
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
FREEZE = ROOT / "agentic_freeze" / "GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json"
V5_YAML = ROOT / "config" / "qwen_external_v5.yaml"
EMPTY_REFS = OUT / "inputs" / "references.yaml"
TARGETS_FA = OUT / "inputs" / "targets.fa"
LINUX = Path("/home/aritr/d20_v5_batch4")
EXPECTED_FREEZE = "736bd2bdc34b1967a429602903f26ebfa5cdb031c6787a7f0ebf77926517c696"
EXPECTED_POOL = "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c"
SKIP = ("GCF_048282645.1", "lacZ_beta_galactosidase")
PREFLIGHT_M0 = "ae9f161ccfedad485178c7eaea2da771f0c2c0babfe3af54d827acfece8581b8"
N_NEW = 4


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class RssMonitor:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.peak_rss_kb = 0
        self.peak_swap_kb = 0
        self.peak_vm_kb = 0
        self.stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        while not self.stop:
            try:
                rss = swap = vm = 0
                for line in Path(f"/proc/{self.pid}/status").read_text(encoding="utf-8").splitlines():
                    if line.startswith("VmRSS:"):
                        rss = int(line.split()[1])
                    elif line.startswith("VmSwap:"):
                        swap = int(line.split()[1])
                    elif line.startswith("VmPeak:"):
                        vm = int(line.split()[1])
                self.peak_rss_kb = max(self.peak_rss_kb, rss)
                self.peak_swap_kb = max(self.peak_swap_kb, swap)
                self.peak_vm_kb = max(self.peak_vm_kb, vm)
            except Exception:
                pass
            time.sleep(2)

    def finish(self) -> dict:
        self.stop = True
        self.thread.join(timeout=5)
        return {
            "peak_rss_kb": self.peak_rss_kb,
            "peak_swap_kb": self.peak_swap_kb,
            "peak_vm_kb": self.peak_vm_kb,
            "rusage_maxrss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        }


def write_one_target(dest: Path, target: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    chosen = [(header, seq) for seq_id, header, seq in iter_fasta_records(TARGETS_FA) if seq_id == target]
    if chosen:
        header, seq = chosen[0]
        dest.write_text(f">{header}\n{seq}\n", encoding="utf-8")
        return
    fam = load_family(target)
    member = max(fam.members, key=lambda m: len(m.sequence or ""))
    dest.write_text(
        f">{target} target_type=gene_orthologue family={target} length_aa={len(member.sequence)}\n{member.sequence}\n",
        encoding="utf-8",
    )


def run_tblastn(query: Path, subject: Path, out_tsv: Path) -> dict:
    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    fmt = "6 qseqid sseqid pident length qlen slen qstart qend sstart send evalue bitscore"
    cmd = [
        "tblastn", "-query", str(query), "-subject", str(subject),
        "-evalue", "1e-3", "-outfmt", fmt, "-max_hsps", "20", "-max_target_seqs", "20",
        "-out", str(out_tsv),
    ]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True)
    n = 0
    if out_tsv.exists():
        n = len([ln for ln in out_tsv.read_text(encoding="utf-8").splitlines() if ln.strip()])
    return {"n_hit_rows": n, "returncode": p.returncode, "seconds": time.perf_counter() - t0}


def snapshot(sys_dir: Path, target: str) -> dict:
    claims = load_json(sys_dir / "claims.json") or []
    claim = next((c for c in claims if target in str(c.get("claim_id"))), None) or (claims[0] if claims else {})
    fam = load_json(sys_dir / "family" / target / "family_evidence.json") or {}
    hits = load_json(sys_dir / "search" / "gene_search_hits.json") or []
    if isinstance(hits, dict):
        hits = hits.get("hits") or []
    locus = load_json(sys_dir / "locus_evidence.json") or []
    tests = []
    for t in (claim or {}).get("falsification_tests") or []:
        tests.append({"test_id": t.get("test_id"), "status": t.get("status"), "result": t.get("result")})
    m0_blob = {"target": target, "hits": hits, "family_evidence": fam, "locus_evidence_n": len(locus) if isinstance(locus, list) else None}
    tools = sorted({h.get("tool") for h in hits if isinstance(h, dict) and h.get("tool")})
    return {
        "final_result": (claim or {}).get("claim_type"),
        "claim_class": (claim or {}).get("status"),
        "confidence": (claim or {}).get("confidence"),
        "architecture": fam.get("architecture") or (claim or {}).get("architecture_state"),
        "homology_support": (claim or {}).get("homology_support"),
        "n_hits": len(hits) if isinstance(hits, list) else None,
        "hit_tools": tools,
        "falsification_summary": tests,
        "m0_hash": sha256_text(json.dumps(m0_blob, sort_keys=True, default=str)),
        "claims_exists": (sys_dir / "claims.json").exists(),
    }


def main() -> int:
    freeze_sha = sha256_file(FREEZE)
    pool_sha = sha256_file(POOL)
    if freeze_sha != EXPECTED_FREEZE:
        raise SystemExit(f"freeze mismatch {freeze_sha}")
    if pool_sha != EXPECTED_POOL:
        raise SystemExit(f"pool mismatch {pool_sha}")
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    selected = []
    for rec in pool["candidates"]:
        key = (rec["assembly_accession"], rec["target"])
        if key == SKIP:
            continue
        selected.append(rec)
        if len(selected) == N_NEW:
            break
    if len(selected) != N_NEW:
        raise SystemExit(f"could not select {N_NEW} remaining candidates")
    print("BATCH4_SELECTED", [(r["assembly_accession"], r["target"]) for r in selected], flush=True)
    if not TARGETS_FA.exists():
        chunks = []
        for fid in ("rpoB_RNAP_beta", "tuf_EF_Tu", "lacZ_beta_galactosidase", "tetA_tetracycline_efflux"):
            fam = load_family(fid)
            member = max(fam.members, key=lambda m: len(m.sequence or ""))
            chunks.append(f">{fid} target_type=gene_orthologue family={fid} length_aa={len(member.sequence)}\n{member.sequence}\n")
        TARGETS_FA.parent.mkdir(parents=True, exist_ok=True)
        TARGETS_FA.write_text("".join(chunks), encoding="utf-8")
    if not EMPTY_REFS.exists():
        EMPTY_REFS.write_text("references: []\n", encoding="utf-8")
    settings = load_settings(V5_YAML)
    LINUX.mkdir(parents=True, exist_ok=True)
    rows = []
    for rec in selected:
        acc = rec["assembly_accession"]
        target = rec["target"]
        print(f"V5_BATCH {acc} {target}", flush=True)
        src_fa = ROOT / rec["solver_fasta"]
        fasta_sha = sha256_file(src_fa)
        if fasta_sha != rec["fasta_sha256"]:
            raise SystemExit(f"FASTA hash mismatch {acc}")
        assembly = LINUX / f"{acc}.fna"
        if not assembly.exists() or sha256_file(assembly) != fasta_sha:
            shutil.copyfile(src_fa, assembly)
        work = LINUX / acc / target
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True, exist_ok=True)
        target_fa = work / "target.fa"
        write_one_target(target_fa, target)
        sys_dir = work / "genome_skeptic"
        sys_dir.mkdir(parents=True, exist_ok=True)
        tblast = run_tblastn(target_fa, assembly, work / "tblastn.tsv")
        print(f"TBLASTN {acc} hits={tblast['n_hit_rows']}", flush=True)
        monitor = RssMonitor(os.getpid())
        monitor.start()
        t0 = time.perf_counter()
        err = None
        payload = None
        try:
            payload = _run_system(
                "genome_skeptic",
                assembly,
                target_fa,
                sys_dir,
                settings,
                EMPTY_REFS,
                rec.get("organism"),
                None,
                None,
            )
        except Exception as exc:
            err = {"error": str(exc), "traceback": traceback.format_exc()}
            print(err["traceback"], file=sys.stderr, flush=True)
        elapsed = time.perf_counter() - t0
        mem = monitor.finish()
        snap = snapshot(sys_dir, target)
        fallback_used = tblast["n_hit_rows"] == 0 or "internal_gene_search" in (snap.get("hit_tools") or [])
        ok = err is None and snap.get("claims_exists") is True
        dest = OUT / "v5_prescreen" / acc / target / "genome_skeptic"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        if sys_dir.exists():
            shutil.copytree(sys_dir, dest)
        case_row = {
            "assembly_accession": acc,
            "organism": rec.get("organism"),
            "genus": rec.get("genus"),
            "target": target,
            "assembly_level": rec.get("assembly_level"),
            "fasta_sha256": fasta_sha,
            "blast_returned_hits": tblast["n_hit_rows"] > 0,
            "tblastn_n_hit_rows": tblast["n_hit_rows"],
            "internal_fallback_executed": bool(fallback_used),
            "final_result": snap.get("final_result"),
            "claim_class": snap.get("claim_class"),
            "confidence": snap.get("confidence"),
            "architecture": snap.get("architecture"),
            "homology_support": snap.get("homology_support"),
            "n_hits": snap.get("n_hits"),
            "hit_tools": snap.get("hit_tools"),
            "falsification_summary": snap.get("falsification_summary"),
            "m0_sha256": snap.get("m0_hash"),
            "runtime_seconds": elapsed,
            "v5_seconds_reported": None if payload is None else payload.get("seconds"),
            "peak_memory": mem,
            "exit_status": 0 if ok else 1,
            "error": err,
            "external_labels_opened": False,
            "agentic_v2_executed": False,
            "planner_called": False,
            "critic_called": False,
        }
        locked = OUT / "v5_prescreen" / acc / target / "v5_case.json"
        locked.write_text(json.dumps({**case_row, **snap}, indent=2, default=str) + "\n", encoding="utf-8")
        rows.append(case_row)
        print(
            f"DONE {acc} ok={ok} class={snap.get('claim_class')} rss_kb={mem['peak_rss_kb']} s={elapsed:.1f}",
            flush=True,
        )
        if not ok:
            blob = {
                "kind": "GATE1_V5_BATCH4_RESULTS",
                "stopped_on_failure": True,
                "cases": rows,
            }
            (OUT / "GATE1_V5_BATCH4_RESULTS.json").write_text(json.dumps(blob, indent=2, default=str) + "\n", encoding="utf-8")
            raise SystemExit(f"STOP: frozen V5 failed on {acc} {target}")
    report = {
        "kind": "GATE1_V5_BATCH4_RESULTS",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V2_D20",
        "agentic_freeze_manifest_sha256": freeze_sha,
        "candidate_pool_manifest_sha256": pool_sha,
        "scientific_code_changed": False,
        "external_labels_opened": False,
        "agentic_v2_executed": False,
        "planner_called": False,
        "critic_called": False,
        "preflight_reference_not_rerun": {
            "assembly_accession": "GCF_048282645.1",
            "target": "lacZ_beta_galactosidase",
            "status": "COMPLETE",
            "rerun": False,
            "m0_sha256": PREFLIGHT_M0,
            "v5_result": "target_gene_detected / weakened / confidence 0.55",
        },
        "selection_rule": "first four remaining candidate_pool_manifest.json records after excluding GCF_048282645.1 / lacZ_beta_galactosidase",
        "n_new_attempted": len(rows),
        "n_new_completed": sum(1 for r in rows if r["exit_status"] == 0),
        "n_frozen_v5_complete_including_preflight": 1 + sum(1 for r in rows if r["exit_status"] == 0),
        "n_required": 40,
        "cases": rows,
    }
    dest = OUT / "GATE1_V5_BATCH4_RESULTS.json"
    dest.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print("BATCH4_DONE", dest, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
