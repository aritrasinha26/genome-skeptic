#!/usr/bin/env python3
"""Shared helpers for M60 independent truth construction.

Never opens prediction payloads. Aborts if a forbidden predictor path is requested.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUTH_ROOT = ROOT / "manuscript_benchmark" / "TRUTH_M60"
SOURCE = TRUTH_ROOT / "SOURCE_FREEZE"
EVIDENCE = TRUTH_ROOT / "EVIDENCE"
CASE_RECORDS = TRUTH_ROOT / "CASE_RECORDS"
REVIEW = TRUTH_ROOT / "REVIEW"
FINAL = TRUTH_ROOT / "FINAL"

EXPECTED_GIT = "8f66868850a98494778966bd729b88a6fc2952eb"
EXPECTED_CORE = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"
EXPECTED_MANIFEST = "97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b"
EXPECTED_PROTOCOL_V11 = "73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660"
EXPECTED_M60 = "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655"
EXPECTED_LOCK = "5317b33fa554f81855fa6c68854ad732c5f5127fc0ad41f224fede9159a90791"

# Frozen protocol gates (M60_PROTOCOL_V1_1.md). Not modified.
GENE_AA_MIN_IDENTITY = 0.60
GENE_AA_MIN_QUERY_COVERAGE = 0.80
GENE_LENGTH_RATIO_MIN = 0.80
GENE_LENGTH_RATIO_MAX = 1.20
FAMILY_COMPETITIVE_MARGIN = 0.10
FAMILY_COMPETITIVE_AMBIGUOUS_BAND = 0.05
HMM_MIN_GATE_MODEL_COVERAGE = 0.20
HMM_DOMAIN_ONLY_MAX_MODEL_COVERAGE = 0.45
SEQ_DECISIVE_PRODUCT = 0.70
SEQ_DECISIVE_DELTA = 0.20
NEAR_IDENTITY_BAND = 0.10
NEAR_COVERAGE_BAND = 0.15

FORBIDDEN_PATH_PARTS = (
    "GS_AGENTIC",
    "GS_DETERMINISTIC",
    "GS_EXHAUSTIVE",
    "AMRFINDERPLUS",
    "NCBI_REFSEQ_PGAP",
    "M60_GS_AGENTIC_LOCKED",
    "M60_GS_DETERMINISTIC_LOCKED",
    "M60_GS_EXHAUSTIVE_LOCKED",
    "M60_CONVENTIONAL_LOCKED",
    "M60_SPECIALIST_COMPARATORS_LOCKED",
    "M60_BLINDED_EFFICIENCY",
    "manuscript_benchmark/RUNS",
    "manuscript_benchmark\\RUNS",
    "manuscript_benchmark/POSITION_LOCKS",
    "manuscript_benchmark\\POSITION_LOCKS",
    "external_validation_agentic_d20",
    "D8_EXTERNAL_TRUTH",
    "D12_EXTERNAL_TRUTH",
    "claims.json",
    "/CONVENTIONAL/",
    "\\CONVENTIONAL\\",
    "/CONVENTIONAL\\",
    "\\CONVENTIONAL/",
)

ALLOWED_ROOTS = (
    TRUTH_ROOT,
    ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json",
    ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.csv",
    ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json.sha256.json",
    ROOT / "manuscript_benchmark" / "M60_PREDICTION_LOCK_MANIFEST.json",
    ROOT / "manuscript_benchmark" / "M60_PREDICTION_LOCK_MANIFEST.json.sha256.json",
    ROOT / "manuscript_benchmark" / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json",
    ROOT / "manuscript_benchmark" / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.sha256.json",
    ROOT / "manuscript_benchmark" / "M60_PROTOCOL_V1_1.md",
    ROOT / "manuscript_benchmark" / "M60_PROTOCOL.md",
    ROOT / "manuscript_benchmark" / "M60_SELECTION_AUDIT.md",
    ROOT / "src" / "genome_skeptic" / "data" / "target_families",
    Path("/home/aritr/m60_work/fasta"),
    Path("/tmp"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _norm(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def assert_path_allowed(path: Path, *, hash_only: bool = False) -> Path:
    """Abort if a truth script tries to open predictor/comparator/D20/D8/D12 paths."""
    raw = _norm(path)
    upper = raw.upper()
    if hash_only:
        # Hash-verify locked prediction files without parsing payloads.
        return path
    for part in FORBIDDEN_PATH_PARTS:
        if part.upper() in upper.replace("\\", "/").upper() or part in raw:
            raise SystemExit(f"TRUTH PATH GUARD ABORT: forbidden path {path}")
    return path


def safe_read_bytes(path: Path) -> bytes:
    assert_path_allowed(path)
    return path.read_bytes()


def safe_read_text(path: Path) -> str:
    assert_path_allowed(path)
    return path.read_text(encoding="utf-8", errors="replace")


def safe_load_json(path: Path):
    return json.loads(safe_read_text(path))


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def write_sha256_sidecar(path: Path, extra: dict | None = None) -> str:
    digest = sha256_file(path)
    try:
        rel = str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        rel = str(path)
    payload = {
        "path": rel,
        "sha256": digest,
        "hashed_utc": utc_now(),
        "accuracy_scored": False,
        "prediction_payloads_opened": False,
        "d20_touched": False,
    }
    if extra:
        payload.update(extra)
    (path.parent / f"{path.name}.sha256.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return digest


def hash_file_lf(path: Path) -> str:
    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def verify_pre_truth_chain() -> dict:
    """Hash-verify freeze artifacts. Do not parse prediction payloads."""
    files = {
        ROOT / "manuscript_benchmark" / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json": EXPECTED_MANIFEST,
        ROOT / "manuscript_benchmark" / "M60_PROTOCOL_V1_1.md": EXPECTED_PROTOCOL_V11,
        ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json": EXPECTED_M60,
        ROOT / "manuscript_benchmark" / "M60_PREDICTION_LOCK_MANIFEST.json": EXPECTED_LOCK,
    }
    rows = {}
    for path, expected in files.items():
        raw = sha256_file(path)
        lf = hash_file_lf(path)
        ok = raw == expected or lf == expected
        rows[path.name] = {"raw": raw, "lf": lf, "expected": expected, "ok": ok}
        if not ok:
            raise SystemExit(f"PRE-TRUTH HASH MISMATCH {path.name}: raw={raw} lf={lf} expected={expected}")

    lock_path = ROOT / "manuscript_benchmark" / "M60_PREDICTION_LOCK_MANIFEST.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("n_cases") != 60:
        raise SystemExit(f"lock n_cases={lock.get('n_cases')}")
    if lock.get("truth_opened") is not False:
        raise SystemExit("truth_opened is not false on prediction-lock manifest")
    if lock.get("accuracy_scored") is not False:
        raise SystemExit("accuracy_scored is not false on prediction-lock manifest")
    counts = lock.get("counts") or {}
    for key in ("conventional", "specialist", "gs_deterministic", "gs_agentic", "gs_exhaustive"):
        if counts.get(key) != 60:
            raise SystemExit(f"incomplete arm {key}={counts.get(key)}")
    for key in ("agent_failures", "exhaustive_failures", "comparator_failures", "conventional_failures"):
        if lock.get(key) not in (0, None):
            raise SystemExit(f"{key}={lock.get(key)}")

    file_sha = lock.get("file_sha256") or {}
    for name, expected in file_sha.items():
        path = ROOT / "manuscript_benchmark" / name
        got = sha256_file(path)  # hash-only; do not JSON-load prediction payloads
        if got != expected:
            raise SystemExit(f"locked file hash mismatch {name}")

    pos_root = ROOT / "manuscript_benchmark" / "POSITION_LOCKS"
    missing = []
    for pos in range(1, 61):
        p = pos_root / f"position_{pos:02d}" / "POSITION_LOCK.json"
        if not p.exists():
            missing.append(pos)
    if missing:
        raise SystemExit(f"missing position locks {missing}")

    src = ROOT / "src"
    if str(src) not in os.sys.path:
        os.sys.path.insert(0, str(src))
    from genome_skeptic.manuscript.scientific_core import scientific_core_hashes

    core = scientific_core_hashes()["scientific_core_hash"]
    if core != EXPECTED_CORE:
        raise SystemExit(f"scientific_core_hash mismatch {core}")

    return {
        "verified_utc": utc_now(),
        "files": rows,
        "scientific_core_hash": core,
        "n_position_locks": 60,
        "truth_opened": False,
        "accuracy_scored": False,
        "PREDICTIONS_LOCKED_BEFORE_TRUTH": "YES",
        "prediction_payloads_opened": False,
    }


def load_cohort_metadata() -> list[dict]:
    path = ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for rec in data["cases"]:
        cases.append(
            {
                "case_id": rec["case_id"],
                "position": int(rec["execution_position"]),
                "accession": rec["accession"],
                "target": rec["target"],
                "stratum": rec["stratum"],
                "organism": rec.get("organism"),
                "ftp_path": rec.get("ftp_path"),
            }
        )
    cases.sort(key=lambda r: r["position"])
    if len(cases) != 60:
        raise SystemExit(f"cohort n={len(cases)}")
    return cases


CODONS = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}
_COMPLEMENT = str.maketrans("ACGTUNacgtun", "TGCAANtgcaan")


def reverse_complement(seq: str) -> str:
    return seq.translate(_COMPLEMENT)[::-1]


def translate_frame(seq: str, frame: int = 0) -> str:
    seq = seq.upper().replace("U", "T")
    aa = []
    for i in range(frame, len(seq) - 2, 3):
        aa.append(CODONS.get(seq[i:i + 3], "X"))
    return "".join(aa)


def read_fasta(path: Path) -> list[tuple[str, str]]:
    assert_path_allowed(path)
    recs: list[tuple[str, str]] = []
    header = None
    chunks: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(">"):
            if header is not None:
                recs.append((header, "".join(chunks)))
            header = line[1:].strip().split()[0]
            chunks = []
        else:
            chunks.append(line.strip())
    if header is not None:
        recs.append((header, "".join(chunks)))
    return recs


def write_fasta(path: Path, recs: list[tuple[str, str]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for name, seq in recs:
        lines.append(f">{name}")
        s = "".join(c for c in seq if not c.isspace())
        for i in range(0, len(s), 80):
            lines.append(s[i:i + 80])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sha256_file(path)
