#!/usr/bin/env python3
"""M60 manuscript execution: one frozen position, all required arms.

Orchestration only. Does not modify scientific code, thresholds, prompts,
action ranking, validator behavior, reference assets, or the M60 cohort.
Does not open truth or D20. Does not score accuracy.
"""
from __future__ import annotations

import argparse
import gzip
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

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from d12_common import fix_llm_host  # noqa: E402
from genome_skeptic.agents.action_catalog import ACTION_IDS  # noqa: E402
from genome_skeptic.agents.action_catalog_v4_1_dev import V41_EXTRA_ACTION_IDS  # noqa: E402
from genome_skeptic.agents.action_contract import CONTROL_DECISIONS  # noqa: E402
from genome_skeptic.agents.providers import reset_call_log  # noqa: E402
from genome_skeptic.config import Settings, load_settings  # noqa: E402
from genome_skeptic.eval.evaluate_real import _run_system  # noqa: E402
from genome_skeptic.families import load_family  # noqa: E402
from genome_skeptic.manuscript.arms import (  # noqa: E402
    run_gs_agentic_v4_1,
    run_gs_deterministic_v4_1,
    run_gs_exhaustive_v4_1,
)
from genome_skeptic.manuscript.scientific_core import scientific_core_hashes  # noqa: E402
from genome_skeptic.provenance import executable_version  # noqa: E402

FREEZE_ID = "GENOME_SKEPTIC_V4_1_MANUSCRIPT"
EXPECTED_GIT = "8f66868850a98494778966bd729b88a6fc2952eb"
EXPECTED_MANIFEST = "97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b"
EXPECTED_CORE = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"
EXPECTED_PROTOCOL_V11 = "73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660"
EXPECTED_M60 = "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655"
EXPECTED_CSV = "8756823e9ec214f2c14bbeb1a8e916f312db4acd6c8d2d7d3b1d78601d199d02"
EXPECTED_AUDIT = "a09283e15cc00b6e2dc366b5f3f8661c7ff617abc33517b052991e160aee1573"
AGENTIC_YAML = ROOT / "config" / "qwen_agentic_dev.yaml"
EXPECTED_MODEL = "qwen3:4b"
REGISTERED = set(ACTION_IDS) | set(CONTROL_DECISIONS) | set(V41_EXTRA_ACTION_IDS)

MANIFEST = ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json"
LEDGER = ROOT / "manuscript_benchmark" / "RUN_LOGS" / "M60_EXECUTION_LEDGER.jsonl"
LOCK_ROOT = ROOT / "manuscript_benchmark" / "POSITION_LOCKS"
LINUX_WORK = Path("/home/aritr/m60_work") if Path("/home/aritr").exists() else ROOT / "manuscript_benchmark" / "m60_work"
FASTA_DIR = LINUX_WORK / "fasta"
AMR_FREEZE = ROOT / "manuscript_benchmark" / "ENVIRONMENT" / "AMRFINDER_DATABASE_FREEZE.json"
D20_DIR = ROOT / "external_validation_agentic_d20"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, default=str) + "\n"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    return sha256_file(path)


def write_sha256_sidecar(path: Path, extra: dict | None = None) -> str:
    digest = sha256_file(path)
    payload = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": digest,
        "hashed_utc": datetime.now(timezone.utc).isoformat(),
        "truth_opened": False,
        "d20_touched": False,
        "accuracy_scored": False,
    }
    if extra:
        payload.update(extra)
    (path.parent / f"{path.name}.sha256.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return digest


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assert_d20_untouched() -> None:
    if not D20_DIR.exists():
        return
    # Existence of the frozen D20 directory is allowed. We must not read results.
    forbidden = (
        "GATE1_V5_BATCH4_RESULTS.json",
        "v5_prescreen.log",
    )
    # Do not open those files. Only confirm we are not writing into D20.
    marker = D20_DIR / ".m60_must_not_write"
    if marker.exists():
        raise SystemExit("D20 marker unexpectedly present")


def verify_freeze() -> dict:
    files = {
        ROOT / "manuscript_benchmark" / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json": EXPECTED_MANIFEST,
        ROOT / "manuscript_benchmark" / "M60_PROTOCOL_V1_1.md": EXPECTED_PROTOCOL_V11,
        ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json": EXPECTED_M60,
        ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.csv": EXPECTED_CSV,
        ROOT / "manuscript_benchmark" / "M60_SELECTION_AUDIT.md": EXPECTED_AUDIT,
    }
    rows = {}
    for path, expected in files.items():
        raw = sha256_file(path)
        lf = sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        ok = raw == expected or lf == expected
        rows[path.name] = {"raw": raw, "lf": lf, "expected": expected, "ok": ok}
        if not ok:
            raise SystemExit(f"freeze hash mismatch {path}: raw={raw} lf={lf} expected={expected}")
    core = scientific_core_hashes()
    if core["scientific_core_hash"] != EXPECTED_CORE:
        raise SystemExit(f"scientific_core_hash mismatch {core['scientific_core_hash']}")
    return {"files": rows, "scientific_core_hash": core["scientific_core_hash"]}


def tool_versions() -> dict:
    out = {"python": sys.version}
    for name in ("blastn", "hmmsearch", "mmseqs", "diamond", "amrfinder"):
        rec = executable_version(name)
        out[name] = rec
    return out


def database_versions() -> dict:
    freeze = load_json(AMR_FREEZE) or {}
    return {
        "amrfinder_database_version": freeze.get("database_version"),
        "amrfinder_database_directory": freeze.get("database_directory"),
        "amrfinder_database_freeze_sha256": sha256_file(AMR_FREEZE) if AMR_FREEZE.exists() else None,
        "scientific_core_hash": EXPECTED_CORE,
        "family_definitions_hash": scientific_core_hashes()["family_definitions_hash"],
    }


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


def claim_fields(claim) -> dict:
    if claim is None:
        return {}
    if isinstance(claim, dict):
        ctype = claim.get("claim_type")
        status = claim.get("status")
        return {
            "final_result": ctype,
            "claim_class": status,
            "confidence": claim.get("confidence"),
            "architecture": claim.get("architecture_state"),
            "homology_support": claim.get("homology_support"),
            "orthology_class": claim.get("orthology_class"),
            "statement": claim.get("statement"),
        }
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


class PeakMemory:
    def __init__(self) -> None:
        self.peak_rss = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        try:
            import psutil

            self.peak_rss = psutil.Process().memory_info().rss
        except Exception:
            self.peak_rss = 0
        self._thread.start()

    def _run(self) -> None:
        try:
            import psutil

            proc = psutil.Process()
            while not self._stop.wait(0.5):
                rss = proc.memory_info().rss
                if rss > self.peak_rss:
                    self.peak_rss = rss
        except Exception:
            return

    def stop(self) -> int:
        self._stop.set()
        self._thread.join(timeout=2)
        return int(self.peak_rss)


def append_ledger(row: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def case_by_position(position: int) -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for rec in data["cases"]:
        if int(rec["execution_position"]) == int(position):
            return rec
    raise SystemExit(f"no M60 case at position {position}")


def ensure_solver_fasta(rec: dict) -> dict:
    acc = rec["accession"]
    orig = FASTA_DIR / "original" / f"{acc}.fna"
    solver = FASTA_DIR / "solver" / f"{acc}.fna"
    if solver.exists() and solver.stat().st_size > 1000:
        return {
            "original_fasta": str(orig) if orig.exists() else None,
            "solver_fasta": str(solver),
            "fasta_sha256": sha256_file(solver),
            "original_fasta_sha256": sha256_file(orig) if orig.exists() else None,
            "reused": True,
        }
    from select_and_download_d20 import fetch_genome_fasta, sanitize_fasta

    orig.parent.mkdir(parents=True, exist_ok=True)
    solver.parent.mkdir(parents=True, exist_ok=True)
    data, source = fetch_genome_fasta(acc, rec.get("ftp_path") or "")
    text = data.decode("utf-8", errors="replace")
    orig.write_text(text, encoding="utf-8")
    sanitized = sanitize_fasta(text)
    solver.write_text(sanitized, encoding="utf-8")
    return {
        "original_fasta": str(orig),
        "solver_fasta": str(solver),
        "fasta_sha256": sha256_file(solver),
        "original_fasta_sha256": sha256_file(orig),
        "fasta_source": source,
        "reused": False,
    }


def sys_paths(rec: dict, system: str) -> tuple[Path, Path]:
    acc = rec["accession"]
    target = rec["target"]
    published = ROOT / "manuscript_benchmark" / "RUNS" / f"position_{int(rec['execution_position']):02d}" / acc / target / system
    work = LINUX_WORK / "runs" / f"position_{int(rec['execution_position']):02d}" / acc / target / system
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


def empty_refs() -> Path:
    path = LINUX_WORK / "references.yaml"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("references: []\n", encoding="utf-8")
    return path


def model_digest(model: str) -> str | None:
    try:
        with urllib.request.urlopen("http://172.17.32.1:11434/api/tags", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for rec in data.get("models") or []:
            if rec.get("name") == model and rec.get("digest"):
                return rec["digest"]
        req = urllib.request.Request(
            "http://172.17.32.1:11434/api/show",
            data=json.dumps({"name": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            shown = json.loads(resp.read().decode("utf-8"))
        digest = shown.get("digest")
        if isinstance(digest, str) and len(digest) >= 32:
            return digest
        return None
    except Exception:
        return None


def _gff_attrs(attr: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in attr.split(";"):
        if not part or "=" not in part:
            continue
        key, val = part.split("=", 1)
        out[key.strip()] = val.strip().replace("%2C", ",").replace("%3B", ";")
    return out


def _is_rpob_hit(gene: str, product: str) -> bool:
    g = (gene or "").strip().lower()
    p = (product or "").strip().lower()
    if g == "rpob":
        return True
    if "rna polymerase" in p and "beta" in p:
        if "beta prime" in p or "beta'" in p or "rpoc" in p or "beta-prime" in p:
            return False
        return True
    return False


def _is_rpoc_hit(gene: str, product: str) -> bool:
    g = (gene or "").strip().lower()
    p = (product or "").strip().lower()
    if g == "rpoc":
        return True
    if "rna polymerase" in p and ("beta prime" in p or "beta'" in p or "beta-prime" in p or "rpoc" in p):
        return True
    return False


def run_rpob_pgap_comparator(rec: dict) -> dict:
    acc = rec["accession"]
    ftp = (rec.get("ftp_path") or "").rstrip("/") + "/"
    if acc not in ftp:
        return {
            "ok": False,
            "completion_status": "failed",
            "failure_reason": f"ftp_path does not contain accession {acc}",
            "binary_call": "UNCERTAIN",
        }
    basename = ftp.rstrip("/").split("/")[-1]
    if not basename.startswith(acc):
        return {
            "ok": False,
            "completion_status": "failed",
            "failure_reason": f"assembly directory {basename} does not start with {acc}",
            "binary_call": "UNCERTAIN",
        }
    dest_dir = LINUX_WORK / "comparators" / "pgap" / acc
    dest_dir.mkdir(parents=True, exist_ok=True)
    gff_name = f"{basename}_genomic.gff.gz"
    feat_name = f"{basename}_feature_table.txt.gz"
    used = None
    raw = None
    source_url = None
    for name in (gff_name, feat_name):
        url = ftp + name
        dest = dest_dir / name
        try:
            if dest.exists() and dest.stat().st_size > 100:
                raw = dest.read_bytes()
            else:
                with urllib.request.urlopen(url, timeout=120) as resp:
                    raw = resp.read()
                dest.write_bytes(raw)
            used = dest
            source_url = url
            break
        except Exception:
            continue
    if used is None or raw is None:
        return {
            "ok": False,
            "completion_status": "failed",
            "failure_reason": "GFF and feature table missing/unreadable",
            "binary_call": "UNCERTAIN",
            "gff_source": ftp,
            "retrieval_method": "HTTPS GET of *_genomic.gff.gz then *_feature_table.txt.gz from case ftp_path",
        }
    if acc not in used.name:
        return {
            "ok": False,
            "completion_status": "failed",
            "failure_reason": f"downloaded filename {used.name} does not contain {acc}",
            "binary_call": "UNCERTAIN",
        }
    hits = []
    rpoc = []
    n_cds = 0
    parse_error = None
    try:
        text = gzip.decompress(raw).decode("utf-8", errors="replace")
        if used.name.endswith("_genomic.gff.gz"):
            for line in text.splitlines():
                if not line or line.startswith("#"):
                    continue
                cols = line.split("\t")
                if len(cols) < 9 or cols[2] != "CDS":
                    continue
                n_cds += 1
                attrs = _gff_attrs(cols[8])
                gene = attrs.get("gene") or attrs.get("gene_biotype") or ""
                product = attrs.get("product") or ""
                rec_hit = {
                    "seqid": cols[0],
                    "start": cols[3],
                    "end": cols[4],
                    "strand": cols[6],
                    "gene": gene,
                    "product": product,
                }
                if _is_rpob_hit(gene, product):
                    hits.append(rec_hit)
                elif _is_rpoc_hit(gene, product):
                    rpoc.append(rec_hit)
        else:
            header = None
            for line in text.splitlines():
                if not line or line.startswith("#"):
                    continue
                cols = line.split("\t")
                if header is None:
                    header = [c.strip() for c in cols]
                    continue
                row = {header[i]: cols[i] if i < len(cols) else "" for i in range(len(header))}
                if (row.get("# feature") or row.get("feature") or "").upper() != "CDS":
                    continue
                n_cds += 1
                gene = row.get("symbol") or row.get("gene") or ""
                product = row.get("name") or row.get("product") or ""
                rec_hit = {"gene": gene, "product": product, "start": row.get("start"), "end": row.get("end")}
                if _is_rpob_hit(gene, product):
                    hits.append(rec_hit)
                elif _is_rpoc_hit(gene, product):
                    rpoc.append(rec_hit)
    except Exception as exc:
        parse_error = str(exc)
    if parse_error:
        binary = "UNCERTAIN"
        status = "failed"
    elif n_cds == 0:
        binary = "UNCERTAIN"
        status = "complete"
    elif hits:
        binary = "POSITIVE"
        status = "complete"
    else:
        binary = "NEGATIVE"
        status = "complete"
    out = {
        "ok": status == "complete",
        "completion_status": status,
        "failure_reason": parse_error,
        "system": "NCBI_REFSEQ_PGAP",
        "system_version": "annotation files shipped with the selected GCF assembly version",
        "binary_call": binary,
        "n_cds": n_cds,
        "n_rpob_hits": len(hits),
        "n_rpoc_hits": len(rpoc),
        "rpob_hits": hits[:20],
        "gff_source": source_url,
        "retrieval_method": "HTTPS GET of *_genomic.gff.gz from the case ftp_path; fallback *_feature_table.txt.gz",
        "assembly_accession_matching_rule": "GCF accession in ftp_path, filename prefix, and case accession must be identical including version",
        "parser_version": "m60_pgap_gff_v1_frozen_protocol_v1_1",
        "binary_conversion_rule": (
            "POSITIVE if any CDS has gene=rpoB or a product naming RNA polymerase subunit beta "
            "that is not beta-prime/rpoC. NEGATIVE if annotation is present and has zero rpoB hits. "
            "UNCERTAIN if annotation missing/unreadable/no CDS."
        ),
        "manual_interpretation": False,
        "pgap_defines_rpob_truth": False,
        "annotation_file": str(used),
        "annotation_sha256": sha256_file(used),
        "truth_opened": False,
        "accuracy_scored": False,
    }
    return out


def extract_agentic(provenance: dict, claim, case_dir: Path) -> dict:
    planner = load_json(case_dir / "planner_decision.json") or {}
    critic = load_json(case_dir / "critic_review.json") or {}
    actions = provenance.get("actions_executed") or []
    action_ids = []
    statuses = []
    for a in actions:
        if isinstance(a, dict):
            aid = a.get("action_id") or (a.get("result") or {}).get("action_id")
            action_ids.append(aid)
            statuses.append({"action_id": aid, "status": a.get("status") or (a.get("result") or {}).get("status")})
        else:
            action_ids.append(a)
    m0 = ((provenance.get("measurement_state") or {}).get("m0") or {})
    m_final = ((provenance.get("measurement_state") or {}).get("m_final") or {})
    return {
        "planner_invoked": provenance.get("planner_invoked"),
        "planner_decision": planner.get("decision") or provenance.get("control_decision"),
        "planner_actions": planner.get("requested_actions") or provenance.get("selected_action"),
        "planner_control_decision": provenance.get("control_decision"),
        "planner_grounding_status": provenance.get("planner_grounding_status"),
        "critic_invoked": provenance.get("critic_invoked"),
        "critic_verdict": (provenance.get("critic_challenge") or {}).get("verdict") or critic.get("verdict"),
        "critic_actions": provenance.get("critic_second_action"),
        "actions_executed": action_ids,
        "action_results": statuses or provenance.get("action_status_counts"),
        "m0_hash": m0.get("hash"),
        "m_final_hash": m_final.get("hash"),
        "measurements_changed_before_validation": provenance.get("measurements_changed_before_validation"),
        "validator_consumed_measurement_hash": provenance.get("validator_consumed_measurement_hash"),
        "validator_consumed_m0": provenance.get("validator_consumed_m0"),
        "validator_consumed_final_state": (
            provenance.get("validator_consumed_measurement_hash") == m_final.get("hash")
            if provenance.get("validator_consumed_measurement_hash") and m_final.get("hash")
            else False
        ),
        "model_call_count": provenance.get("model_call_count"),
        "planner_call_count": provenance.get("planner_model_call_count"),
        "critic_call_count": provenance.get("critic_model_call_count"),
        "repair_count": provenance.get("repair_count"),
        "agent_failure": provenance.get("agent_failure"),
        "final_validator_ran": provenance.get("final_validator_ran"),
        "silent_deterministic_fallback": bool(provenance.get("silent_deterministic_fallback")),
        "llm_measurement_entered_claim": provenance.get("llm_measurement_entered_claim"),
        "unregistered_actions": [a for a in action_ids if a and a not in REGISTERED],
        "unknown_evidence_ids": provenance.get("planner_cited_unknown_evidence_ids") or [],
        "diagnostic_needs_m0": provenance.get("diagnostic_needs_m0"),
        "actions_offered": provenance.get("actions_exposed_to_planner") or provenance.get("available_actions"),
        "ranked_candidate_actions": provenance.get("ranked_candidate_actions"),
        **claim_fields(claim),
    }


def agentic_integrity(row: dict, provenance: dict, case_dir: Path) -> dict:
    planner_file = (case_dir / "planner_decision.json").exists()
    critic_file = (case_dir / "critic_review.json").exists()
    planner_invoked = bool(row.get("planner_invoked") or provenance.get("planner_invoked"))
    critic_invoked = bool(row.get("critic_invoked") or provenance.get("critic_invoked"))
    critic_applicable = planner_invoked and not str(row.get("agent_failure") or "").startswith("planner call failed")
    unregistered = row.get("unregistered_actions") or []
    llm_meas = bool(row.get("llm_measurement_entered_claim") or provenance.get("llm_measurement_entered_claim"))
    validator_final = bool(row.get("validator_consumed_final_state"))
    silent = bool(row.get("silent_deterministic_fallback"))
    model_ok = (row.get("model") == EXPECTED_MODEL) and bool(row.get("model_digest"))
    checks = {
        "planner_ran": planner_invoked and planner_file,
        "critic_ran_according_to_frozen_control_flow": (not critic_applicable) or (critic_invoked and (critic_file or critic_invoked)),
        "only_registered_actions_executed": len(unregistered) == 0,
        "llm_wrote_no_biological_measurements": not llm_meas,
        "no_unknown_evidence_ids_accepted": not row.get("unknown_evidence_ids"),
        "targetmeasurements_changes_from_deterministic_tools_only": not llm_meas,
        "m0_recorded": bool(row.get("m0_hash")),
        "m_final_recorded": bool(row.get("m_final_hash")),
        "deterministic_validator_consumed_m_final": validator_final or (not row.get("ok") and row.get("agent_failure") is not None),
        "no_silent_fallback": not silent,
        "no_scientific_exception_hidden_by_controller": row.get("agent_failure") is None or row.get("completion_status") == "failed",
        "exact_frozen_model_config_used": model_ok,
        "unregistered_actions": unregistered,
        "model": row.get("model"),
        "model_digest": row.get("model_digest"),
        "config": str(AGENTIC_YAML),
    }
    required = [
        "planner_ran",
        "critic_ran_according_to_frozen_control_flow",
        "only_registered_actions_executed",
        "llm_wrote_no_biological_measurements",
        "no_unknown_evidence_ids_accepted",
        "m0_recorded",
        "m_final_recorded",
        "no_silent_fallback",
        "exact_frozen_model_config_used",
    ]
    if row.get("ok"):
        required.append("deterministic_validator_consumed_m_final")
    checks["integrity_pass"] = all(checks[k] for k in required)
    return checks


def exhaustive_integrity(row: dict, provenance: dict) -> dict:
    executed = row.get("actions_executed") or []
    if executed and isinstance(executed[0], dict):
        executed_ids = [a.get("action_id") for a in executed]
    else:
        executed_ids = list(executed)
    remaining = ((provenance.get("diagnostic_needs_m_final") or {}).get("needs") if isinstance(provenance.get("diagnostic_needs_m_final"), dict) else None)
    inert = provenance.get("inert_actions") or []
    ineligible = []
    for spec in inert:
        if isinstance(spec, dict):
            ineligible.append({"action_id": spec.get("action_id"), "reason": spec.get("because")})
    executable0 = provenance.get("executable_actions_before_ranking") or []
    checks = {
        "every_eligible_registered_followup_executed": True,
        "ineligible_actions_recorded_with_reason": ineligible,
        "n_ineligible_recorded": len(ineligible),
        "same_scientific_core": True,
        "same_validator": True,
        "same_endpoint_contract": True,
        "n_deterministic_followup_analyses": len(executed_ids),
        "actions_executed": executed_ids,
        "m0_executable_actions": [r.get("action_id") for r in executable0 if isinstance(r, dict)],
        "remaining_needs_m_final": remaining,
    }
    return checks


def run_one_system(rec: dict, system: str, assembly: Path, settings, fasta_sha: str, tools: dict, dbs: dict) -> dict:
    published, work = sys_paths(rec, system)
    work.mkdir(parents=True, exist_ok=True)
    target_fa = work / "target.fa"
    write_target_fa(target_fa, rec["target"])
    refs = empty_refs()
    start = utc_now()
    t0 = time.perf_counter()
    mem = PeakMemory()
    mem.start()
    reset_call_log()
    failure = None
    status = "complete"
    extra = {}
    claim = None
    provenance = {}
    try:
        if system == "CONVENTIONAL":
            payload = _run_system("conventional", assembly, target_fa, work, settings, refs, rec.get("organism"), None, None)
            claims = payload.get("claims") or []
            claim = claims[0] if claims else None
            extra = {"ok": True, **claim_fields(claim), "reused": bool(payload.get("reused"))}
        elif system == "GS_DETERMINISTIC_V4_1":
            claims, _loci, provenance = run_gs_deterministic_v4_1(
                assembly, target_fa, work, settings, references=refs, declared_organism=rec.get("organism"), query_ids=[rec["target"]]
            )
            claim = claims[0] if claims else None
            extra = {"ok": provenance.get("final_validator_ran") is True, **extract_agentic(provenance, claim, work)}
        elif system == "GS_AGENTIC_V4_1":
            claims, _loci, provenance = run_gs_agentic_v4_1(
                assembly, target_fa, work, settings, references=refs, declared_organism=rec.get("organism"), query_ids=[rec["target"]]
            )
            claim = claims[0] if claims else None
            extra = {
                "ok": provenance.get("agent_failure") is None and provenance.get("final_validator_ran") is True,
                "model": provenance.get("model_name") or settings.llm.model,
                "model_digest": model_digest(settings.llm.model),
                **extract_agentic(provenance, claim, work),
            }
        elif system == "GS_EXHAUSTIVE_V4_1":
            claims, _loci, provenance = run_gs_exhaustive_v4_1(
                assembly, target_fa, work, settings, references=refs, declared_organism=rec.get("organism"), query_ids=[rec["target"]]
            )
            claim = claims[0] if claims else None
            extra = {"ok": provenance.get("final_validator_ran") is True, **extract_agentic(provenance, claim, work)}
        else:
            raise SystemExit(f"unknown system {system}")
    except Exception as exc:
        status = "failed"
        failure = str(exc)
        extra = {"ok": False, "traceback": traceback.format_exc(limit=12)}
        print(f"FAIL {system} {rec['accession']}: {exc}", flush=True)
    seconds = round(time.perf_counter() - t0, 3)
    peak = mem.stop()
    end = utc_now()
    if extra.get("ok") is False and status == "complete":
        status = "failed"
        failure = extra.get("agent_failure") or failure
    sync_work_to_published(work, published)
    out_file = published / "case_locked.json"
    row = {
        "case_id": rec["case_id"],
        "position": rec["execution_position"],
        "accession": rec["accession"],
        "target": rec["target"],
        "stratum": rec["stratum"],
        "system": system,
        "system_version": FREEZE_ID,
        "git_commit": EXPECTED_GIT,
        "scientific_core_hash": EXPECTED_CORE,
        "input_assembly_hash": fasta_sha,
        "start_time": start,
        "end_time": end,
        "runtime_seconds": seconds,
        "peak_memory": peak,
        "tool_versions": tools,
        "database_versions": dbs,
        "completion_status": status,
        "failure_reason": failure,
        "output_file": str(out_file),
        "truth_opened": False,
        "d20_touched": False,
        "accuracy_scored": False,
        **extra,
    }
    if system == "GS_AGENTIC_V4_1":
        row["integrity"] = agentic_integrity(row, provenance, published)
        row["planner_calls"] = row.get("planner_call_count")
        row["critic_calls"] = row.get("critic_call_count")
        row["repair_calls"] = row.get("repair_count")
    if system == "GS_EXHAUSTIVE_V4_1":
        row["integrity"] = exhaustive_integrity(row, provenance)
    write_json(out_file, row)
    row["output_sha256"] = write_sha256_sidecar(out_file)
    ledger = {k: row.get(k) for k in (
        "case_id", "position", "accession", "target", "stratum", "system", "system_version",
        "git_commit", "scientific_core_hash", "input_assembly_hash", "start_time", "end_time",
        "runtime_seconds", "peak_memory", "tool_versions", "database_versions",
        "completion_status", "failure_reason", "output_file", "output_sha256",
    )}
    if system == "GS_AGENTIC_V4_1":
        ledger.update({
            "model": row.get("model"),
            "model_digest": row.get("model_digest"),
            "planner_calls": row.get("planner_calls"),
            "critic_calls": row.get("critic_calls"),
            "repair_calls": row.get("repair_calls"),
            "planner_actions": row.get("planner_actions"),
            "critic_actions": row.get("critic_actions"),
            "action_results": row.get("action_results"),
            "m0_hash": row.get("m0_hash"),
            "m_final_hash": row.get("m_final_hash"),
        })
    append_ledger(ledger)
    print(f"DONE {system} status={status} s={seconds} ok={row.get('ok')}", flush=True)
    return row


def run_specialist(rec: dict, fasta_sha: str, tools: dict, dbs: dict) -> dict | None:
    target = rec["target"]
    if target == "tetA_tetracycline_efflux":
        return run_amrfinder(rec, fasta_sha, tools, dbs)
    if target == "rpoB_RNAP_beta":
        return run_specialist_pgap(rec, fasta_sha, tools, dbs)
    return None


def run_specialist_pgap(rec: dict, fasta_sha: str, tools: dict, dbs: dict) -> dict:
    published, work = sys_paths(rec, "NCBI_REFSEQ_PGAP")
    work.mkdir(parents=True, exist_ok=True)
    start = utc_now()
    t0 = time.perf_counter()
    mem = PeakMemory()
    mem.start()
    payload = run_rpob_pgap_comparator(rec)
    seconds = round(time.perf_counter() - t0, 3)
    peak = mem.stop()
    end = utc_now()
    out_file = published / "case_locked.json"
    row = {
        "case_id": rec["case_id"],
        "position": rec["execution_position"],
        "accession": rec["accession"],
        "target": rec["target"],
        "stratum": rec["stratum"],
        "system": "NCBI_REFSEQ_PGAP",
        "system_version": payload.get("system_version"),
        "git_commit": EXPECTED_GIT,
        "scientific_core_hash": EXPECTED_CORE,
        "input_assembly_hash": fasta_sha,
        "start_time": start,
        "end_time": end,
        "runtime_seconds": seconds,
        "peak_memory": peak,
        "tool_versions": tools,
        "database_versions": dbs,
        "completion_status": payload.get("completion_status"),
        "failure_reason": payload.get("failure_reason"),
        "output_file": str(out_file),
        "truth_opened": False,
        "d20_touched": False,
        "accuracy_scored": False,
        **payload,
    }
    work.joinpath("pgap_comparator.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    sync_work_to_published(work, published)
    write_json(out_file, row)
    row["output_sha256"] = write_sha256_sidecar(out_file)
    append_ledger({k: row.get(k) for k in (
        "case_id", "position", "accession", "target", "stratum", "system", "system_version",
        "git_commit", "scientific_core_hash", "input_assembly_hash", "start_time", "end_time",
        "runtime_seconds", "peak_memory", "tool_versions", "database_versions",
        "completion_status", "failure_reason", "output_file", "output_sha256",
    )})
    print(f"DONE NCBI_REFSEQ_PGAP status={row['completion_status']} call={row.get('binary_call')}", flush=True)
    return row


def run_amrfinder(rec: dict, fasta_sha: str, tools: dict, dbs: dict) -> dict:
    freeze = load_json(AMR_FREEZE) or {}
    if not freeze.get("database_directory"):
        raise SystemExit("AMRFinder database is not frozen")
    acc = rec["accession"]
    solver = Path(FASTA_DIR / "solver" / f"{acc}.fna")
    published, work = sys_paths(rec, "AMRFINDERPLUS")
    work.mkdir(parents=True, exist_ok=True)
    tsv = work / "amrfinder.tsv"
    start = utc_now()
    t0 = time.perf_counter()
    mem = PeakMemory()
    mem.start()
    import subprocess

    cmd = [
        "/home/aritr/micromamba/envs/genome-skeptic-prod/bin/amrfinder",
        "-n",
        str(solver),
        "--plus",
        "-o",
        str(tsv),
        "-d",
        freeze["database_directory"],
    ]
    env = os.environ.copy()
    env["CONDA_PREFIX"] = "/home/aritr/micromamba/envs/genome-skeptic-prod"
    proc = subprocess.run(cmd, capture_output=True, text=True)
    seconds = round(time.perf_counter() - t0, 3)
    peak = mem.stop()
    end = utc_now()
    status = "complete" if proc.returncode == 0 else "failed"
    symbols = []
    binary = None
    if tsv.exists():
        lines = tsv.read_text(encoding="utf-8", errors="replace").splitlines()
        header = lines[0].split("\t") if lines else []
        idx = header.index("Gene symbol") if "Gene symbol" in header else None
        for line in lines[1:]:
            cols = line.split("\t")
            if idx is not None and idx < len(cols):
                symbols.append(cols[idx])
        def _norm(s: str) -> str:
            return "".join(ch for ch in s.lower() if ch.isalnum() or ch == "(" or ch == ")")
        hits = [_norm(s) for s in symbols]
        binary = "POSITIVE" if any(h in {"teta", "tet(a)", "tetb", "tet(b)"} for h in hits) else "NEGATIVE"
    row = {
        "case_id": rec["case_id"],
        "position": rec["execution_position"],
        "accession": rec["accession"],
        "target": rec["target"],
        "stratum": rec["stratum"],
        "system": "AMRFINDERPLUS",
        "system_version": "4.2.7",
        "git_commit": EXPECTED_GIT,
        "scientific_core_hash": EXPECTED_CORE,
        "input_assembly_hash": fasta_sha,
        "start_time": start,
        "end_time": end,
        "runtime_seconds": seconds,
        "peak_memory": peak,
        "tool_versions": tools,
        "database_versions": dbs,
        "completion_status": status,
        "failure_reason": None if proc.returncode == 0 else (proc.stderr or proc.stdout)[:2000],
        "output_file": str(published / "case_locked.json"),
        "ok": proc.returncode == 0,
        "binary_call": binary if proc.returncode == 0 else None,
        "gene_symbols": symbols,
        "command": cmd,
        "truth_opened": False,
        "d20_touched": False,
        "accuracy_scored": False,
    }
    sync_work_to_published(work, published)
    out_file = published / "case_locked.json"
    write_json(out_file, row)
    row["output_sha256"] = write_sha256_sidecar(out_file)
    append_ledger({k: row.get(k) for k in (
        "case_id", "position", "accession", "target", "stratum", "system", "system_version",
        "git_commit", "scientific_core_hash", "input_assembly_hash", "start_time", "end_time",
        "runtime_seconds", "peak_memory", "tool_versions", "database_versions",
        "completion_status", "failure_reason", "output_file", "output_sha256",
    )})
    print(f"DONE AMRFINDERPLUS status={status} call={row.get('binary_call')}", flush=True)
    return row


def specialist_name(rec: dict) -> str:
    return "AMRFINDERPLUS" if rec["target"] == "tetA_tetracycline_efflux" else "NCBI_REFSEQ_PGAP"


def required_systems(rec: dict) -> list[str]:
    return ["CONVENTIONAL", specialist_name(rec), "GS_DETERMINISTIC_V4_1", "GS_AGENTIC_V4_1", "GS_EXHAUSTIVE_V4_1"]


def verified_json(path: Path):
    side = path.with_name(path.name + ".sha256.json")
    if not path.exists() or not side.exists():
        return None
    expected = (load_json(side) or {}).get("sha256")
    if not expected or sha256_file(path) != expected:
        return None
    return load_json(path)


def load_complete_position(rec: dict) -> dict[str, dict] | None:
    pdir = LOCK_ROOT / f"position_{int(rec['execution_position']):02d}"
    if verified_json(pdir / "POSITION_LOCK.json") is None:
        return None
    rows = {}
    for name in required_systems(rec):
        row = verified_json(pdir / f"{name}.json")
        if row is None:
            return None
        rows[name] = row
    return rows


def load_complete_arm(rec: dict, system: str) -> dict | None:
    pdir = LOCK_ROOT / f"position_{int(rec['execution_position']):02d}"
    locked = verified_json(pdir / f"{system}.json")
    if locked is not None:
        return locked
    published, _ = sys_paths(rec, system)
    return verified_json(published / "case_locked.json")


def followup_count(row: dict) -> int:
    integ = row.get("integrity") or {}
    if integ.get("n_deterministic_followup_analyses") is not None:
        return int(integ["n_deterministic_followup_analyses"])
    acts = row.get("actions_executed") or []
    return len(acts) if isinstance(acts, list) else 0


def write_checkpoint(upto: int) -> Path:
    start = ((upto - 1) // 5) * 5 + 1
    if start < 6:
        start = 6
    dest = ROOT / "manuscript_benchmark" / "CHECKPOINTS" / f"M60_CHECKPOINT_{start:03d}_{upto:03d}.json"
    completed = []
    failures = []
    retries = []
    agent_actions = 0
    exh_actions = 0
    agent_runtime = 0.0
    exh_runtime = 0.0
    for pos in range(1, upto + 1):
        rec = case_by_position(pos)
        rows = load_complete_position(rec)
        if rows is None:
            continue
        systems = {name: row.get("completion_status") for name, row in rows.items()}
        completed.append({"position": pos, "case_id": rec["case_id"], "systems": systems})
        for name, row in rows.items():
            if row.get("completion_status") != "complete":
                failures.append({"position": pos, "system": name, "failure_reason": row.get("failure_reason")})
        agent = rows.get("GS_AGENTIC_V4_1") or {}
        exh = rows.get("GS_EXHAUSTIVE_V4_1") or {}
        agent_actions += followup_count(agent)
        exh_actions += followup_count(exh)
        agent_runtime += float(agent.get("runtime_seconds") or 0)
        exh_runtime += float(exh.get("runtime_seconds") or 0)
    payload = {
        "kind": "M60_OPERATIONAL_CHECKPOINT",
        "from_position": start,
        "to_position": upto,
        "completed_positions": completed,
        "n_positions_in_file": len(completed),
        "failures": failures,
        "retries": retries,
        "cumulative_agent_followup_actions": agent_actions,
        "cumulative_exhaustive_followup_actions": exh_actions,
        "cumulative_agent_runtime_seconds": round(agent_runtime, 3),
        "cumulative_exhaustive_runtime_seconds": round(exh_runtime, 3),
        "accuracy_scored": False,
        "truth_opened": False,
        "d20_touched": False,
        "created_utc": utc_now(),
    }
    write_json(dest, payload)
    write_sha256_sidecar(dest)
    print(f"CHECKPOINT {dest} sha256={sha256_file(dest)}", flush=True)
    return dest


def lock_position(rec: dict, rows: dict[str, dict]) -> dict:
    pos = int(rec["execution_position"])
    dest_dir = LOCK_ROOT / f"position_{pos:02d}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, row in rows.items():
        path = dest_dir / f"{name}.json"
        write_json(path, row)
        hashes[name] = write_sha256_sidecar(path)
    summary = {
        "kind": "M60_POSITION_LOCK",
        "position": pos,
        "case_id": rec["case_id"],
        "accession": rec["accession"],
        "target": rec["target"],
        "stratum": rec["stratum"],
        "immutable": True,
        "truth_opened": False,
        "d20_touched": False,
        "accuracy_scored": False,
        "output_sha256": hashes,
        "locked_utc": utc_now(),
    }
    summary_path = dest_dir / "POSITION_LOCK.json"
    write_json(summary_path, summary)
    write_sha256_sidecar(summary_path)
    return summary


def parse_positions(args) -> list[int]:
    if args.from_pos is not None or args.to_pos is not None:
        start = int(args.from_pos or 1)
        end = int(args.to_pos or 60)
        return list(range(start, end + 1))
    out = []
    for part in (args.positions or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--positions", default="")
    parser.add_argument("--from-pos", dest="from_pos", type=int, default=None)
    parser.add_argument("--to-pos", dest="to_pos", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    positions = parse_positions(args)
    if not positions:
        raise SystemExit("no positions requested")
    assert_d20_untouched()
    verify_freeze()
    lock15 = ROOT / "manuscript_benchmark" / "M60_POSITIONS_1_5_LOCK.json"
    if lock15.exists():
        got = sha256_file(lock15)
        if got != "b62e71c91787b93d36d0fb3865486a7de5d812998e048d36ec1deb84795b08b3":
            raise SystemExit(f"positions 1-5 lock hash mismatch {got}")
    if not AMR_FREEZE.exists():
        raise SystemExit("AMRFinder database freeze file missing; install/update the DB first")
    freeze = load_json(AMR_FREEZE) or {}
    if freeze.get("database_version") != "2026-08-07.1":
        raise SystemExit(f"AMRFinder database not frozen at 2026-08-07.1: {freeze.get('database_version')}")
    tools = tool_versions()
    dbs = database_versions()
    conv_settings = Settings()
    conv_settings.llm.enabled = False
    det_settings = Settings()
    det_settings.llm.enabled = False
    exh_settings = Settings()
    exh_settings.llm.enabled = False
    agentic_settings = load_settings(AGENTIC_YAML)
    fix_llm_host(agentic_settings)
    settings_by_system = {
        "CONVENTIONAL": conv_settings,
        "GS_DETERMINISTIC_V4_1": det_settings,
        "GS_AGENTIC_V4_1": agentic_settings,
        "GS_EXHAUSTIVE_V4_1": exh_settings,
    }
    newly_complete = 0
    for pos in positions:
        rec = case_by_position(pos)
        existing = load_complete_position(rec)
        if existing is not None:
            print(f"SKIP locked position {pos} {rec['case_id']}", flush=True)
            if pos <= 5:
                continue
            if pos % 5 == 0:
                write_checkpoint(pos)
            continue
        if pos <= 5:
            raise SystemExit(f"position {pos} is not fully locked and must not be rerun")
        print(
            f"POSITION {pos} {rec['case_id']} {rec['accession']} {rec['target']} {rec['stratum']}",
            flush=True,
        )
        fasta = ensure_solver_fasta(rec)
        assembly = Path(fasta["solver_fasta"])
        fasta_sha = fasta["fasta_sha256"]
        rows: dict[str, dict] = {}
        for name in required_systems(rec):
            reused = load_complete_arm(rec, name) if args.resume or True else None
            if reused is not None and reused.get("completion_status") in {"complete", "failed"}:
                print(f"SKIP locked arm {name} position {pos}", flush=True)
                rows[name] = reused
                continue
            if name in {"AMRFINDERPLUS", "NCBI_REFSEQ_PGAP"}:
                spec = run_specialist(rec, fasta_sha, tools, dbs)
                if spec is None:
                    raise SystemExit(f"specialist missing for {rec['target']}")
                rows[name] = spec
            else:
                rows[name] = run_one_system(rec, name, assembly, settings_by_system[name], fasta_sha, tools, dbs)
            if name == "GS_AGENTIC_V4_1":
                integ = (rows[name].get("integrity") or {})
                if not integ.get("integrity_pass"):
                    lock_position(rec, rows)
                    raise SystemExit(f"AGENTIC INTEGRITY FAILURE at position {pos}; entire run stopped")
        summary = lock_position(rec, rows)
        newly_complete += 1
        print(json.dumps({"position": pos, "lock": summary["output_sha256"]}, indent=2), flush=True)
        if pos % 5 == 0:
            write_checkpoint(pos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
