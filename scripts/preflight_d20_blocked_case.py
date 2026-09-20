#!/usr/bin/env python3
"""Infrastructure preflight: one frozen-V5 case with extra memory/swap.

Does not modify scientific source, thresholds, BLAST policy, or the candidate pool.
Does not run Agentic V2, planner, critic, or the other 39 candidates.
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
PRE = OUT / "preflight_GCF_048282645.1_lacZ"
FREEZE = ROOT / "agentic_freeze" / "GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json"
V5_FREEZE = ROOT / "v5_freeze_manifest.json"
POOL = OUT / "candidate_pool_manifest.json"
V5_YAML = ROOT / "config" / "qwen_external_v5.yaml"
EMPTY_REFS = OUT / "inputs" / "references.yaml"
TARGETS_FA = OUT / "inputs" / "targets.fa"
ACC = "GCF_048282645.1"
TARGET = "lacZ_beta_galactosidase"
EXPECTED_FREEZE = "736bd2bdc34b1967a429602903f26ebfa5cdb031c6787a7f0ebf77926517c696"
EXPECTED_POOL = "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c"
EXPECTED_CSV = "3b3660668aacddf85e613c70983cb0f94ed58d5c53e630f008f8798f27c8e4e6"
LINUX_WORK = Path("/home/aritr/d20_v5_preflight")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_freeze() -> dict:
    freeze_sha = sha256_file(FREEZE)
    pool_sha = sha256_file(POOL)
    csv_sha = sha256_file(OUT / "candidate_pool_manifest.csv")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    mismatches = []
    for row in freeze.get("files") or []:
        path = ROOT / row["path"]
        if not path.exists():
            mismatches.append({"path": row["path"], "error": "missing"})
            continue
        got = sha256_file(path)
        if got != row["sha256"]:
            mismatches.append({"path": row["path"], "expected": row["sha256"], "got": got})
    v5_freeze_sha = sha256_file(V5_FREEZE) if V5_FREEZE.exists() else None
    expected_v5 = (freeze.get("deterministic_v5_identity") or {}).get("v5_freeze_manifest_sha256")
    yaml_sha = sha256_file(V5_YAML)
    yaml_expected = next((r["sha256"] for r in freeze.get("files") or [] if r["path"] == "config/qwen_external_v5.yaml"), None)
    gene_sha = sha256_file(ROOT / "src/genome_skeptic/tools/gene_search.py")
    gene_expected = next((r["sha256"] for r in freeze.get("files") or [] if r["path"] == "src/genome_skeptic/tools/gene_search.py"), None)
    return {
        "freeze_manifest_sha256": freeze_sha,
        "freeze_manifest_match": freeze_sha == EXPECTED_FREEZE,
        "n_freeze_files": len(freeze.get("files") or []),
        "freeze_file_mismatches": mismatches,
        "scientific_source_match": not mismatches,
        "v5_freeze_manifest_sha256": v5_freeze_sha,
        "v5_freeze_manifest_match": v5_freeze_sha == expected_v5,
        "qwen_external_v5_yaml_sha256": yaml_sha,
        "qwen_external_v5_yaml_match": yaml_sha == yaml_expected,
        "gene_search_py_sha256": gene_sha,
        "gene_search_py_match": gene_sha == gene_expected,
        "candidate_pool_sha256": pool_sha,
        "candidate_pool_match": pool_sha == EXPECTED_POOL,
        "candidate_csv_sha256": csv_sha,
        "candidate_csv_match": csv_sha == EXPECTED_CSV,
    }


def env_record() -> dict:
    import platform
    mem = Path("/proc/meminfo").read_text(encoding="utf-8") if Path("/proc/meminfo").exists() else ""
    parsed = {}
    for line in mem.splitlines():
        k, _, rest = line.partition(":")
        parsed[k] = rest.strip()
    py = subprocess.check_output([sys.executable, "--version"], text=True).strip()
    blast = subprocess.check_output(["tblastn", "-version"], text=True).strip()
    pkgs = {}
    for name in ("pydantic", "numpy"):
        try:
            pkgs[name] = subprocess.check_output(
                [sys.executable, "-c", f"import {name}; print(getattr({name}, '__version__', 'unknown'))"],
                text=True,
            ).strip()
        except Exception as exc:
            pkgs[name] = f"unavailable:{exc}"
    return {
        "python": py,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "kernel": platform.release(),
        "blast": blast,
        "packages": pkgs,
        "meminfo": parsed,
        "wsl_memory_limit_note": "from /proc/meminfo MemTotal after .wslconfig apply",
        "cwd": str(Path.cwd()),
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
    }


def write_one_target(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    chosen = [(header, seq) for seq_id, header, seq in iter_fasta_records(TARGETS_FA) if seq_id == TARGET]
    if not chosen:
        fam = load_family(TARGET)
        member = max(fam.members, key=lambda m: len(m.sequence or ""))
        dest.write_text(
            f">{TARGET} target_type=gene_orthologue family={TARGET} length_aa={len(member.sequence)}\n{member.sequence}\n",
            encoding="utf-8",
        )
        return
    header, seq = chosen[0]
    dest.write_text(f">{header}\n{seq}\n", encoding="utf-8")


def run_tblastn(query: Path, subject: Path, out_tsv: Path) -> dict:
    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    fmt = "6 qseqid sseqid pident length qlen slen qstart qend sstart send evalue bitscore"
    cmd = [
        "tblastn",
        "-query", str(query),
        "-subject", str(subject),
        "-evalue", "1e-3",
        "-outfmt", fmt,
        "-max_hsps", "20",
        "-max_target_seqs", "20",
        "-out", str(out_tsv),
    ]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0
    text = out_tsv.read_text(encoding="utf-8") if out_tsv.exists() else ""
    n = len([ln for ln in text.splitlines() if ln.strip()])
    return {
        "command": cmd,
        "returncode": p.returncode,
        "n_hit_rows": n,
        "seconds": elapsed,
        "stdout": p.stdout[-2000:],
        "stderr": p.stderr[-2000:],
        "out_tsv": str(out_tsv),
    }


class RssMonitor:
    def __init__(self, pid: int, dest: Path) -> None:
        self.pid = pid
        self.dest = dest
        self.peak_rss_kb = 0
        self.peak_swap_kb = 0
        self.peak_vm_kb = 0
        self.samples = 0
        self.stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _read(self) -> tuple[int, int, int]:
        status = Path(f"/proc/{self.pid}/status")
        rss = swap = vm = 0
        try:
            for line in status.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1])
                elif line.startswith("VmSwap:"):
                    swap = int(line.split()[1])
                elif line.startswith("VmPeak:"):
                    vm = int(line.split()[1])
        except Exception:
            return self.peak_rss_kb, self.peak_swap_kb, self.peak_vm_kb
        return rss, swap, vm

    def _run(self) -> None:
        lines = []
        while not self.stop:
            rss, swap, vm = self._read()
            self.peak_rss_kb = max(self.peak_rss_kb, rss)
            self.peak_swap_kb = max(self.peak_swap_kb, swap)
            self.peak_vm_kb = max(self.peak_vm_kb, vm)
            self.samples += 1
            if self.samples % 5 == 0:
                lines.append(f"{time.time():.0f} rss_kb={rss} swap_kb={swap} vmpeak_kb={vm}\n")
                print(f"mem rss_kb={rss} swap_kb={swap} peak_rss_kb={self.peak_rss_kb}", flush=True)
            time.sleep(2)
        self.dest.write_text("".join(lines[-200:]), encoding="utf-8")

    def finish(self) -> dict:
        self.stop = True
        self.thread.join(timeout=5)
        ru = resource.getrusage(resource.RUSAGE_SELF)
        return {
            "peak_rss_kb": self.peak_rss_kb,
            "peak_swap_kb": self.peak_swap_kb,
            "peak_vm_kb": self.peak_vm_kb,
            "samples": self.samples,
            "rusage_maxrss_kb": int(ru.ru_maxrss),
        }


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def snapshot(sys_dir: Path) -> dict:
    claims = load_json(sys_dir / "claims.json") or []
    claim = next((c for c in claims if TARGET in str(c.get("claim_id"))), None)
    if claim is None and claims:
        claim = claims[0]
    fam = load_json(sys_dir / "family" / TARGET / "family_evidence.json") or {}
    hits = load_json(sys_dir / "search" / "gene_search_hits.json") or []
    if isinstance(hits, dict):
        hits = hits.get("hits") or []
    locus = load_json(sys_dir / "locus_evidence.json") or []
    m0_blob = {"target": TARGET, "hits": hits, "family_evidence": fam, "locus_evidence_n": len(locus) if isinstance(locus, list) else None}
    tools = sorted({h.get("tool") for h in hits if isinstance(h, dict) and h.get("tool")})
    return {
        "final_result": (claim or {}).get("claim_type"),
        "claim_class": (claim or {}).get("status"),
        "confidence": (claim or {}).get("confidence"),
        "architecture": fam.get("architecture") or (claim or {}).get("architecture_state"),
        "homology_support": (claim or {}).get("homology_support"),
        "orthology_class": (claim or {}).get("orthology_class"),
        "n_hits": len(hits) if isinstance(hits, list) else None,
        "hit_tools": tools,
        "m0_hash": sha256_text(json.dumps(m0_blob, sort_keys=True, default=str)),
        "claims_exists": (sys_dir / "claims.json").exists(),
        "family_evidence_exists": (sys_dir / "family" / TARGET / "family_evidence.json").exists(),
        "hits_exists": (sys_dir / "search" / "gene_search_hits.json").exists(),
    }


def main() -> int:
    PRE.mkdir(parents=True, exist_ok=True)
    print("PREFLIGHT_START", flush=True)
    ver = verify_freeze()
    (PRE / "freeze_verification.json").write_text(json.dumps(ver, indent=2) + "\n", encoding="utf-8")
    if not ver["freeze_manifest_match"] or not ver["candidate_pool_match"] or not ver["scientific_source_match"]:
        print(json.dumps(ver, indent=2), flush=True)
        raise SystemExit("frozen state mismatch; abort")
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    rec = next(c for c in pool["candidates"] if c["assembly_accession"] == ACC and c["target"] == TARGET)
    src_fa = ROOT / rec["solver_fasta"]
    fasta_sha = sha256_file(src_fa)
    if fasta_sha != rec["fasta_sha256"]:
        raise SystemExit(f"blocked FASTA hash mismatch: {fasta_sha}")
    env = env_record()
    (PRE / "environment.json").write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8")
    print("ENV", env["python"], env["blast"].splitlines()[0], "MemTotal", env["meminfo"].get("MemTotal"), "SwapTotal", env["meminfo"].get("SwapTotal"), flush=True)

    LINUX_WORK.mkdir(parents=True, exist_ok=True)
    assembly = LINUX_WORK / f"{ACC}.fna"
    if not assembly.exists() or sha256_file(assembly) != rec["fasta_sha256"]:
        shutil.copyfile(src_fa, assembly)
        if sha256_file(assembly) != rec["fasta_sha256"]:
            raise SystemExit("staged FASTA hash mismatch")
    target_fa = LINUX_WORK / "target.fa"
    if not TARGETS_FA.exists():
        fam = load_family(TARGET)
        member = max(fam.members, key=lambda m: len(m.sequence or ""))
        TARGETS_FA.parent.mkdir(parents=True, exist_ok=True)
        TARGETS_FA.write_text(
            f">{TARGET} target_type=gene_orthologue family={TARGET} length_aa={len(member.sequence)}\n{member.sequence}\n",
            encoding="utf-8",
        )
    write_one_target(target_fa)
    if not EMPTY_REFS.exists():
        EMPTY_REFS.write_text("references: []\n", encoding="utf-8")

    tblast = run_tblastn(target_fa, assembly, PRE / "tblastn.tsv")
    (PRE / "tblastn.json").write_text(json.dumps(tblast, indent=2) + "\n", encoding="utf-8")
    print("TBLASTN_HITS", tblast["n_hit_rows"], "seconds", round(tblast["seconds"], 3), flush=True)
    fallback_expected = tblast["n_hit_rows"] == 0

    work_dir = LINUX_WORK / "genome_skeptic"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    settings = load_settings(V5_YAML)
    monitor = RssMonitor(os.getpid(), PRE / "memory_samples.txt")
    monitor.start()
    t0 = time.perf_counter()
    payload = None
    err = None
    try:
        print("V5_START frozen_fallback_expected", fallback_expected, flush=True)
        payload = _run_system(
            "genome_skeptic",
            assembly,
            target_fa,
            work_dir,
            settings,
            EMPTY_REFS,
            rec.get("organism"),
            None,
            None,
        )
        print("V5_RETURNED", flush=True)
    except Exception as exc:
        err = {"error": str(exc), "traceback": traceback.format_exc()}
        print(err["traceback"], file=sys.stderr, flush=True)
    elapsed = time.perf_counter() - t0
    mem = monitor.finish()
    snap = snapshot(work_dir)
    dest = PRE / "genome_skeptic"
    if dest.exists():
        shutil.rmtree(dest)
    if work_dir.exists():
        shutil.copytree(work_dir, dest)
    hashes = {}
    for rel in (
        "genome_skeptic/claims.json",
        "genome_skeptic/search/gene_search_hits.json",
        f"genome_skeptic/family/{TARGET}/family_evidence.json",
        "genome_skeptic/locus_evidence.json",
    ):
        p = PRE / rel
        hashes[rel] = sha256_file(p) if p.exists() else None
    fallback_entered = fallback_expected or "internal_gene_search" in (snap.get("hit_tools") or [])
    fallback_completed = snap.get("claims_exists") is True and err is None
    report = {
        "kind": "D20_GATE1_INFRASTRUCTURE_PREFLIGHT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_code_changed": False,
        "external_labels_opened": False,
        "agentic_v2_executed": False,
        "planner_called": False,
        "critic_called": False,
        "other_39_candidates_run": False,
        "blocked_case": {"assembly_accession": ACC, "target": TARGET, "fasta_sha256": fasta_sha},
        "verification": ver,
        "environment": {
            "python": env["python"],
            "blast": env["blast"],
            "platform": env["platform"],
            "MemTotal": env["meminfo"].get("MemTotal"),
            "SwapTotal": env["meminfo"].get("SwapTotal"),
            "MemAvailable": env["meminfo"].get("MemAvailable"),
        },
        "tblastn": {"n_hit_rows": tblast["n_hit_rows"], "returncode": tblast["returncode"], "seconds": tblast["seconds"]},
        "frozen_fallback_entered": bool(fallback_entered),
        "fallback_completed": bool(fallback_completed),
        "exit_status": 0 if err is None and fallback_completed else 1,
        "runtime_seconds": elapsed,
        "peak_memory": mem,
        "v5_seconds_reported": None if payload is None else payload.get("seconds"),
        "v5_reused": None if payload is None else payload.get("reused"),
        "v5_result": snap,
        "output_hashes": hashes,
        "error": err,
    }
    (PRE / "PREFLIGHT_REPORT.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print("PREFLIGHT_DONE", json.dumps({
        "fallback_entered": fallback_entered,
        "fallback_completed": fallback_completed,
        "peak_rss_kb": mem["peak_rss_kb"],
        "peak_swap_kb": mem["peak_swap_kb"],
        "runtime_seconds": elapsed,
        "claim_class": snap.get("claim_class"),
        "m0_hash": snap.get("m0_hash"),
        "exit_status": report["exit_status"],
    }), flush=True)
    return report["exit_status"]


if __name__ == "__main__":
    raise SystemExit(main())
