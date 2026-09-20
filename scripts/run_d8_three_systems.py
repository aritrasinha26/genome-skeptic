#!/usr/bin/env python3
"""D8 mini: sequential conventional → frozen V5 → frozen Agentic V2.

Does not modify D20. Does not unblind. Does not change frozen scientific source.
"""
from __future__ import annotations

import faulthandler
import hashlib
import json
import os
import shutil
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

faulthandler.enable()

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.assembly_loop_v2 import SYSTEM_NAME, run_skeptic_agentic_v2
from genome_skeptic.agents.providers import CALL_LOG, extract_json_text, reset_call_log
from genome_skeptic.config import load_settings
from genome_skeptic.eval.evaluate_real import _run_system
from genome_skeptic.families import load_family
from genome_skeptic.io_utils import iter_fasta_records
from genome_skeptic.orchestrator import REGISTERED_ACTIONS

OUT = ROOT / "external_validation_agentic_d8"
MANIFEST = OUT / "D8_MANIFEST.json"
RUNS = OUT / "runs"
LINUX = Path("/home/aritr/d8_work")
EMPTY_REFS = OUT / "inputs" / "references.yaml"
TARGETS_FA = OUT / "inputs" / "targets.fa"
EXPECTED_FREEZE = "736bd2bdc34b1967a429602903f26ebfa5cdb031c6787a7f0ebf77926517c696"
MODEL_DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"
WSL_OLLAMA = "http://172.17.32.1:11434/v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _llm_reachable(url: str) -> bool:
    root = (url or "").rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    try:
        urllib.request.urlopen(root + "/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _fix_llm_host(settings) -> str | None:
    url = settings.llm.base_url or ""
    if "localhost" not in url and "127.0.0.1" not in url:
        return None
    if _llm_reachable(url):
        return None
    settings.llm.base_url = WSL_OLLAMA
    if settings.llm.planner is not None:
        settings.llm.planner.base_url = WSL_OLLAMA
    if settings.llm.critic is not None:
        settings.llm.critic.base_url = WSL_OLLAMA
    return WSL_OLLAMA


def write_targets() -> None:
    chunks = []
    for fid in ("rpoB_RNAP_beta", "tuf_EF_Tu", "lacZ_beta_galactosidase", "tetA_tetracycline_efflux"):
        fam = load_family(fid)
        member = max(fam.members, key=lambda m: len(m.sequence or ""))
        chunks.append(f">{fid} target_type=gene_orthologue family={fid} length_aa={len(member.sequence)}\n{member.sequence}\n")
    TARGETS_FA.parent.mkdir(parents=True, exist_ok=True)
    TARGETS_FA.write_text("".join(chunks), encoding="utf-8")
    if not EMPTY_REFS.exists():
        EMPTY_REFS.write_text("references: []\n", encoding="utf-8")


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


def load_family_blob(sys_dir: Path, qid: str) -> dict | None:
    return load_json(sys_dir / "family" / qid / "family_evidence.json")


def stage_fasta(src: Path, acc: str, expected: str) -> Path:
    if not Path("/home/aritr").exists():
        return src
    LINUX.mkdir(parents=True, exist_ok=True)
    dest = LINUX / f"{acc}.fna"
    if dest.exists() and sha256_file(dest) == expected:
        return dest
    shutil.copyfile(src, dest)
    if sha256_file(dest) != expected:
        raise SystemExit(f"staged FASTA hash mismatch {acc}")
    return dest


def sys_paths(acc: str, target: str, system: str) -> tuple[Path, Path]:
    published = RUNS / acc / target / system
    work = LINUX / "runs" / acc / target / system if Path("/home/aritr").exists() else published
    return published, work


def sync_work_to_published(work: Path, published: Path) -> None:
    if work.resolve() == published.resolve():
        return
    published.mkdir(parents=True, exist_ok=True)
    for src in work.rglob("*"):
        if not src.is_file():
            continue
        dest = published / src.relative_to(work)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


class _RssHeartbeat:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _read(self) -> tuple[int, int]:
        rss = swap = 0
        try:
            for line in Path(f"/proc/{self.pid}/status").read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1])
                elif line.startswith("VmSwap:"):
                    swap = int(line.split()[1])
        except Exception:
            pass
        return rss, swap

    def _run(self) -> None:
        while not self.stop:
            rss, swap = self._read()
            print(f"mem rss_kb={rss} swap_kb={swap}", flush=True)
            time.sleep(15)

    def finish(self) -> None:
        self.stop = True
        self.thread.join(timeout=2)


def claim_fields(claim) -> dict:
    if claim is None:
        return {}
    ctype = claim.claim_type.value if hasattr(claim.claim_type, "value") else claim.claim_type
    status = claim.status.value if hasattr(claim.status, "value") else claim.status
    return {
        "final_result": ctype,
        "claim_class": status,
        "confidence": claim.confidence,
        "architecture": claim.architecture_state,
        "homology_support": claim.homology_support,
        "orthology_class": claim.orthology_class,
        "statement": claim.statement,
    }


def snapshot_deterministic(sys_dir: Path, target: str, claim, seconds: float, reused: bool) -> dict:
    fam = load_family_blob(sys_dir, target) or {}
    recon = fam.get("reconstruction") or {}
    multi = fam.get("multiplicity") or recon.get("multiplicity") or {}
    hits = load_json(sys_dir / "search" / "gene_search_hits.json") or []
    if isinstance(hits, dict):
        hits = hits.get("hits") or []
    locus = load_json(sys_dir / "locus_evidence.json") or []
    m0 = hashlib.sha256(json.dumps({"target": target, "hits": hits, "family_evidence": fam}, sort_keys=True, default=str).encode()).hexdigest()
    row = {
        "ok": claim is not None,
        "runtime_seconds": seconds,
        "reused": reused,
        "architecture": fam.get("architecture") or (claim.architecture_state if claim else None),
        "multiplicity": {
            "number_of_candidate_loci": multi.get("number_of_candidate_loci") if isinstance(multi, dict) else None,
            "classification": multi.get("classification") if isinstance(multi, dict) else None,
        },
        "n_hits": len(hits) if isinstance(hits, list) else None,
        "m0_hash": m0,
        **claim_fields(claim),
        "external_labels_opened": False,
    }
    if claim is None:
        row["ok"] = False
    return row


def _parse_excerpt(raw: str) -> dict:
    text = extract_json_text(raw or "") or (raw or "")
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def extract_agentic(provenance: dict, claim, case_dir: Path) -> dict:
    graph = provenance.get("call_graph") or []
    planner = load_json(case_dir / "planner_decision.json") or {}
    critic = load_json(case_dir / "critic_review.json") or {}
    challenge = provenance.get("critic_challenge") or {}
    actions = provenance.get("actions_executed") or []
    statuses = []
    for a in actions:
        if isinstance(a, dict):
            statuses.append({"action_id": a.get("action_id"), "status": a.get("status"), "requested_by": a.get("requested_by")})
    m0 = ((provenance.get("measurement_state") or {}).get("m0") or {})
    m_final = ((provenance.get("measurement_state") or {}).get("m_final") or {})
    return {
        "planner_decision": planner.get("decision") or provenance.get("control_decision"),
        "planner_action": provenance.get("selected_action") or planner.get("requested_action") or (planner.get("requested_actions") or [None])[0],
        "planner_control_decision": provenance.get("control_decision"),
        "critic_verdict": challenge.get("verdict") or critic.get("verdict"),
        "critic_action": provenance.get("critic_second_action"),
        "actions_executed": [a.get("action_id") if isinstance(a, dict) else a for a in actions],
        "action_result_status": statuses or provenance.get("action_status_counts"),
        "m0_hash": m0.get("hash"),
        "m_final_hash": m_final.get("hash"),
        "measurements_changed_before_validation": provenance.get("measurements_changed_before_validation"),
        "validator_consumed_m0": provenance.get("validator_consumed_m0"),
        "model_call_count": provenance.get("model_call_count"),
        "planner_call_count": provenance.get("planner_model_call_count"),
        "critic_call_count": provenance.get("critic_model_call_count"),
        "repair_count": provenance.get("repair_count"),
        "agent_failure": provenance.get("agent_failure"),
        "final_validator_ran": provenance.get("final_validator_ran"),
        "call_graph": graph,
        "silent_deterministic_fallback": False,
        **claim_fields(claim),
    }


def run_conventional(acc: str, target: str, assembly: Path, settings, organism: str | None) -> dict:
    published, sys_dir = sys_paths(acc, target, "conventional")
    dest = published / "case_locked.json"
    if dest.exists() and dest.stat().st_size > 50:
        print(f"reuse conventional {acc} {target}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    sys_dir.mkdir(parents=True, exist_ok=True)
    one = sys_dir / "target.fa"
    write_one_target(one, target)
    print(f"CONVENTIONAL {acc} {target}", flush=True)
    t0 = time.perf_counter()
    try:
        payload = _run_system("conventional", assembly, one, sys_dir, settings, EMPTY_REFS, organism, None, None)
        claims = payload.get("claims") or []
        claim = claims[0] if claims else None
        if claim and hasattr(claim, "claim_id") is False:
            pass
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": "conventional",
            "ok": True,
            "runtime_seconds": float(payload.get("seconds") or (time.perf_counter() - t0)),
            "reused": bool(payload.get("reused")),
            **claim_fields(claim),
            "external_labels_opened": False,
        }
    except Exception as exc:
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": "conventional",
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "runtime_seconds": time.perf_counter() - t0,
            "external_labels_opened": False,
        }
        print(f"FAIL conventional {acc}: {exc}", flush=True)
    sync_work_to_published(sys_dir, published)
    dest.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    return row


def run_v5(acc: str, target: str, assembly: Path, settings, organism: str | None) -> dict:
    published, sys_dir = sys_paths(acc, target, "genome_skeptic")
    dest = published / "case_locked.json"
    if dest.exists() and dest.stat().st_size > 50:
        print(f"reuse V5 {acc} {target}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    sys_dir.mkdir(parents=True, exist_ok=True)
    one = sys_dir / "target.fa"
    write_one_target(one, target)
    print(f"V5 {acc} {target}", flush=True)
    t0 = time.perf_counter()
    try:
        payload = _run_system("genome_skeptic", assembly, one, sys_dir, settings, EMPTY_REFS, organism, None, None)
        claims = payload.get("claims") or []
        claim = claims[0] if claims else None
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": "genome_skeptic_v5",
            **snapshot_deterministic(sys_dir, target, claim, float(payload.get("seconds") or (time.perf_counter() - t0)), bool(payload.get("reused"))),
        }
    except Exception as exc:
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": "genome_skeptic_v5",
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "runtime_seconds": time.perf_counter() - t0,
            "external_labels_opened": False,
        }
        print(f"FAIL V5 {acc}: {exc}", flush=True)
    sync_work_to_published(sys_dir, published)
    dest.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"V5 DONE {acc} ok={row.get('ok')} class={row.get('claim_class')} s={row.get('runtime_seconds')}", flush=True)
    return row


def run_agentic(acc: str, target: str, assembly: Path, settings, organism: str | None) -> dict:
    published, case_dir = sys_paths(acc, target, SYSTEM_NAME)
    dest = published / "case_locked.json"
    if dest.exists() and dest.stat().st_size > 50:
        print(f"reuse agentic {acc} {target}", flush=True)
        return json.loads(dest.read_text(encoding="utf-8"))
    case_dir.mkdir(parents=True, exist_ok=True)
    one = case_dir / "target.fa"
    write_one_target(one, target)
    print(f"AGENTIC V2 {acc} {target}", flush=True)
    reset_call_log()
    t0 = time.perf_counter()
    try:
        claims, loci, provenance = run_skeptic_agentic_v2(
            assembly, one, case_dir, settings, query_ids=[target], declared_organism=organism, references=EMPTY_REFS
        )
        claim = claims[0] if claims else None
        extra = extract_agentic(provenance, claim, case_dir)
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": SYSTEM_NAME,
            "ok": extra.get("agent_failure") is None and extra.get("final_validator_ran") is True,
            "runtime_seconds": provenance.get("seconds") or round(time.perf_counter() - t0, 3),
            "model": provenance.get("model_name") or "qwen3:4b",
            "model_digest": MODEL_DIGEST,
            "external_labels_opened": False,
            **extra,
        }
    except Exception as exc:
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": SYSTEM_NAME,
            "ok": False,
            "agent_failure": f"planner/critic could not complete under frozen policy: {exc}",
            "agent_execution_failure_recorded": True,
            "silent_deterministic_fallback": False,
            "runtime_seconds": round(time.perf_counter() - t0, 3),
            "traceback": traceback.format_exc(limit=8),
            "external_labels_opened": False,
        }
        print(f"AGENT_FAILURE {acc} {target}: {exc}", flush=True)
    sync_work_to_published(case_dir, published)
    dest.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        f"AGENTIC DONE {acc} ok={row.get('ok')} action={row.get('planner_action')} fail={row.get('agent_failure')}",
        flush=True,
    )
    return row


def lock_predictions(conv: list[dict], v5: list[dict], agentic: list[dict]) -> dict:
    if len(conv) != 8 or len(v5) != 8 or len(agentic) != 8:
        raise SystemExit(f"lock aborted: counts conv={len(conv)} v5={len(v5)} agentic={len(agentic)}")
    blobs = {
        "D8_CONVENTIONAL_LOCKED.json": {
            "kind": "D8_CONVENTIONAL_LOCKED",
            "n_cases": len(conv),
            "do_not_regenerate": True,
            "external_labels_opened": False,
            "predictions": conv,
        },
        "D8_V5_LOCKED.json": {
            "kind": "D8_V5_LOCKED",
            "n_cases": len(v5),
            "do_not_regenerate": True,
            "external_labels_opened": False,
            "predictions": v5,
        },
        "D8_AGENTIC_V2_LOCKED.json": {
            "kind": "D8_AGENTIC_V2_LOCKED",
            "n_cases": len(agentic),
            "do_not_regenerate": True,
            "external_labels_opened": False,
            "predictions": agentic,
        },
    }
    hashes = {}
    stamp = datetime.now(timezone.utc).isoformat()
    for name, payload in blobs.items():
        payload["created_utc"] = stamp
        payload["frozen_agentic_version"] = "GENOME_SKEPTIC_AGENTIC_V2_D20"
        path = OUT / name
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        digest = sha256_file(path)
        hashes[name] = digest
        (OUT / f"{name}.sha256.json").write_text(
            json.dumps({"file": name, "sha256": digest, "hashed_utc": stamp}, indent=2) + "\n",
            encoding="utf-8",
        )
    return hashes


def main() -> int:
    freeze = ROOT / "agentic_freeze" / "GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json"
    if sha256_file(freeze) != EXPECTED_FREEZE:
        raise SystemExit("freeze hash mismatch")
    lock = json.loads((OUT / "D8_MANIFEST.json.sha256.json").read_text(encoding="utf-8"))
    actual = sha256_file(MANIFEST)
    if actual != lock.get("sha256"):
        raise SystemExit(f"D8 manifest hash mismatch {actual}")
    d20_pool = ROOT / "external_validation_agentic_d20" / "candidate_pool_manifest.json"
    if sha256_file(d20_pool) != "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c":
        raise SystemExit("D20 pool was modified; abort")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = sorted(manifest["cases"], key=lambda r: (r["execution_hash"], r["assembly_accession"]))
    write_targets()
    conv_settings = load_settings(ROOT / "config" / "qwen_external_v5.yaml")
    v5_settings = load_settings(ROOT / "config" / "qwen_external_v5.yaml")
    agentic_settings = load_settings(ROOT / "config" / "qwen_agentic_dev.yaml")
    remap = _fix_llm_host(agentic_settings)
    print("OLLAMA_REMAP", remap, flush=True)
    if Path("/home/aritr").exists():
        LINUX.mkdir(parents=True, exist_ok=True)
        tmp = LINUX / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        os.environ["TMPDIR"] = str(tmp)
        os.environ["TMP"] = str(tmp)
        os.environ["TEMP"] = str(tmp)
    RUNS.mkdir(parents=True, exist_ok=True)
    heartbeat = _RssHeartbeat(os.getpid())
    heartbeat.start()
    conv_rows = []
    v5_rows = []
    agentic_rows = []
    for rec in cases:
        acc = rec["assembly_accession"]
        target = rec["target"]
        src = ROOT / rec["solver_fasta"]
        if sha256_file(src) != rec["fasta_sha256"]:
            raise SystemExit(f"FASTA changed {acc}")
        assembly = stage_fasta(src, acc, rec["fasta_sha256"])
        print(f"CASE pos={rec['execution_position']} {acc} {target}", flush=True)
        conv_rows.append(run_conventional(acc, target, assembly, conv_settings, rec.get("organism")))
        v5_rows.append(run_v5(acc, target, assembly, v5_settings, rec.get("organism")))
        agentic_rows.append(run_agentic(acc, target, assembly, agentic_settings, rec.get("organism")))
    heartbeat.finish()
    hashes = lock_predictions(conv_rows, v5_rows, agentic_rows)
    print(json.dumps({"locked": hashes, "n_conv": len(conv_rows), "n_v5": len(v5_rows), "n_agentic": len(agentic_rows)}, indent=2), flush=True)
    print("UNBLIND: NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
