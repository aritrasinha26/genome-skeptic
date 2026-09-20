#!/usr/bin/env python3
"""Shared constants and freeze/exclusion helpers for V3_D12_EXTERNAL.

Does not read D20 truth or write into external_validation_agentic_d20/.
Does not open D8 external truth.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "external_validation_agentic_d12"
D20_DIR = ROOT / "external_validation_agentic_d20"
D20_POOL = D20_DIR / "candidate_pool_manifest.json"
D8_MANIFEST = ROOT / "external_validation_agentic_d8" / "D8_MANIFEST.json"
COHORT_A_PATH = ROOT / "external_validation" / "cohort_A_naturalistic_manifest.json"
COHORT_C_PATH = ROOT / "external_validation_agentic" / "cohort_C_manifest.json"
COHORT_C_PILOT5 = ROOT / "external_validation_agentic" / "cohort_C_pilot5_manifest.json"
EXCL_PATH = ROOT / "external_validation" / "v5_reference_provenance_exclusions.json"
V3_FREEZE = ROOT / "agentic_freeze" / "GENOME_SKEPTIC_AGENTIC_V3_EXTERNAL_manifest.json"
V5_YAML = ROOT / "config" / "qwen_external_v5.yaml"
AGENTIC_YAML = ROOT / "config" / "qwen_agentic_dev.yaml"
LACZ_LIMITATION_PATH = ROOT / "agentic_freeze" / "CURRENT_LACZ_LIMITATION.md"

EXPECTED_V3_FREEZE = "4941a5197ea1a78a358070009e7df963fcdc67e651ba293015903ed6f5b76237"
EXPECTED_D20_POOL = "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c"
EXPECTED_DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"
FREEZE_ID = "GENOME_SKEPTIC_AGENTIC_V3_EXTERNAL"
SEED = "20260920"
WSL_OLLAMA = "http://172.17.32.1:11434/v1"
LINUX_WORK = Path("/home/aritr/d12_work")

TARGETS = [
    "rpoB_RNAP_beta",
    "tuf_EF_Tu",
    "lacZ_beta_galactosidase",
    "tetA_tetracycline_efflux",
]
N_POOL_COMPLETE = 4
N_POOL_DRAFT = 2
N_POOL_PER_TARGET = 6
N_FINAL_PER_TARGET = 3

CURRENT_LACZ_LIMITATION = (
    "No frozen deterministic instrument currently distinguishes true LacZ "
    "orthology from relevant competing beta-galactosidase families when "
    "reference/GFF/orthology resources are absent."
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_sha256_sidecar(path: Path, extra: dict | None = None) -> str:
    digest = sha256_file(path)
    payload = {
        "file": path.name,
        "sha256": digest,
        "hashed_utc": datetime.now(timezone.utc).isoformat(),
        "external_labels_opened": False,
        "d20_touched": False,
    }
    if extra:
        payload.update(extra)
    (path.parent / f"{path.name}.sha256.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return digest


def pool_sampling_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"V3_D12_POOL|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def selection_tie_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"V3_D12_EXTERNAL|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def execution_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"V3_D12_EXECUTION|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def verify_v3_freeze() -> dict:
    digest = sha256_file(V3_FREEZE)
    if digest != EXPECTED_V3_FREEZE:
        raise SystemExit(f"V3 freeze SHA256 mismatch: {digest} != {EXPECTED_V3_FREEZE}")
    payload = json.loads(V3_FREEZE.read_text(encoding="utf-8"))
    if payload.get("freeze_id") != FREEZE_ID:
        raise SystemExit(f"freeze_id mismatch: {payload.get('freeze_id')}")
    mismatches = []
    for row in payload.get("files") or []:
        path = ROOT / row["path"]
        if not path.is_file():
            mismatches.append(f"missing:{row['path']}")
            continue
        if sha256_file(path) != row["sha256"]:
            mismatches.append(f"changed:{row['path']}")
    if mismatches:
        raise SystemExit("frozen V3 files changed:\n" + "\n".join(mismatches[:30]))
    return {
        "freeze_id": FREEZE_ID,
        "manifest_sha256": digest,
        "n_files": payload.get("n_files"),
        "verified": True,
    }


def assert_d20_untouched(when: str) -> str:
    if not D20_POOL.exists():
        raise SystemExit(f"D20 candidate pool missing at {when}; exclusion cannot be verified")
    digest = sha256_file(D20_POOL)
    if digest != EXPECTED_D20_POOL:
        raise SystemExit(f"D20 pool hash changed at {when}: {digest}")
    print(f"D20_UNTOUCHED {when} {digest}", flush=True)
    return digest


def _collect_accessions(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in {"assembly_accession", "accession"} and isinstance(val, str) and val:
                out.add(val)
                if "." in val:
                    out.add(val.split(".")[0])
            elif key in {"extra_accessions", "excluded_nucleotide_accessions"}:
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, str) and item:
                            out.add(item)
                            out.add(item.split(".")[0])
            else:
                _collect_accessions(val, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_accessions(item, out)


def load_accessions_from(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    _collect_accessions(payload, out)
    return out


def load_d20_pool_accessions() -> tuple[set[str], set[str]]:
    digest = assert_d20_untouched("exclusion_load")
    payload = json.loads(D20_POOL.read_text(encoding="utf-8"))
    accs: set[str] = set()
    genera: set[str] = set()
    for rec in payload.get("candidates") or []:
        acc = rec.get("assembly_accession")
        if acc:
            accs.add(acc)
            accs.add(acc.split(".")[0])
        genus = rec.get("genus")
        if genus:
            genera.add(genus)
    if digest != EXPECTED_D20_POOL:
        raise SystemExit("D20 pool hash changed during accession load")
    return accs, genera


def load_genera(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for rec in payload.get("assemblies") or payload.get("cases") or payload.get("candidates") or []:
        genus = rec.get("genus")
        if genus:
            out.add(genus)
    sampling = payload.get("sampling") or {}
    for rec in sampling.get("per_genus") or []:
        genus = rec.get("genus")
        if genus:
            out.add(genus)
    for g in payload.get("genera") or []:
        if g:
            out.add(str(g))
    return out


def catalog_accessions() -> set[str]:
    from genome_skeptic.eval.catalog import GENOMES

    out: set[str] = set()
    for spec in GENOMES:
        out.add(spec.accession)
        out.add(spec.accession.split(".")[0])
        for extra in spec.extra_accessions or ():
            out.add(extra)
            out.add(str(extra).split(".")[0])
    return out


def blocked_accessions_and_genera() -> tuple[set[str], set[str], dict]:
    d20_acc, d20_genera = load_d20_pool_accessions()
    d8_acc = load_accessions_from(D8_MANIFEST)
    cohort_a = load_accessions_from(COHORT_A_PATH)
    cohort_c = load_accessions_from(COHORT_C_PATH)
    pilot5 = load_accessions_from(COHORT_C_PILOT5)
    excl = load_accessions_from(EXCL_PATH)
    catalog = catalog_accessions()
    blocked = set()
    for group in (d20_acc, d8_acc, cohort_a, cohort_c, pilot5, excl, catalog):
        blocked |= group
    genera = (
        d20_genera
        | load_genera(D8_MANIFEST)
        | load_genera(COHORT_A_PATH)
        | load_genera(COHORT_C_PATH)
        | load_genera(COHORT_C_PILOT5)
    )
    provenance = {
        "d20_candidate_pool_n": len({a for a in d20_acc if a.startswith("GCF_") or a.startswith("GCA_")}),
        "d8_n": len({a for a in d8_acc if a.startswith("GCF_") or a.startswith("GCA_")}),
        "cohort_a_n": len({a for a in cohort_a if a.startswith("GCF_") or a.startswith("GCA_")}),
        "cohort_c_n": len({a for a in cohort_c if a.startswith("GCF_") or a.startswith("GCA_")}),
        "d20_pool_sha256": EXPECTED_D20_POOL,
        "d20_directory_modified": False,
        "external_labels_opened": False,
        "d8_truth_opened": False,
    }
    return blocked, genera, provenance


def _llm_reachable(url: str) -> bool:
    root = (url or "").rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    try:
        urllib.request.urlopen(root + "/api/tags", timeout=2)
        return True
    except Exception:
        return False


def fix_llm_host(settings) -> str | None:
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


def write_targets(dest: Path) -> None:
    from genome_skeptic.families import load_family

    chunks = []
    for fid in TARGETS:
        fam = load_family(fid)
        member = max(fam.members, key=lambda m: len(m.sequence or ""))
        chunks.append(
            f">{fid} target_type=gene_orthologue family={fid} length_aa={len(member.sequence)}\n{member.sequence}\n"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(chunks), encoding="utf-8")


def write_one_target(targets_fa: Path, dest: Path, query_id: str) -> None:
    from genome_skeptic.io_utils import iter_fasta_records

    chosen = [(header, seq) for seq_id, header, seq in iter_fasta_records(targets_fa) if seq_id == query_id]
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
