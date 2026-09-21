#!/usr/bin/env python3
"""Build audit-package manifests. Does not modify frozen scientific artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(p.read_bytes())


def sha256_lf(p: Path) -> str:
    return sha256_bytes(p.read_bytes().replace(b"\r\n", b"\n"))


def rel(p: Path, base: Path = ROOT) -> str:
    return str(p.relative_to(base)).replace("\\", "/")


def write_environment() -> None:
    env = json.loads((ROOT / "manuscript_benchmark" / "M60_ENVIRONMENT.json").read_text(encoding="utf-8"))
    fm = json.loads(
        (ROOT / "manuscript_benchmark" / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json").read_text(encoding="utf-8")
    )
    lines = [
        "Genome Skeptic M60 environment manifest (audit extract)",
        "Source: manuscript_benchmark/M60_ENVIRONMENT.json",
        "created_utc: " + str(env.get("created_utc")),
        "",
        "PRODUCTION HOST (WSL) — use this for M60",
        "python_executable: " + str(env.get("python_executable")),
        "python_version: " + str(env.get("python_version")),
        "platform: " + str(env.get("platform")),
    ]
    for k in ["blast", "hmmer", "mmseqs", "diamond", "amrfinder"]:
        t = env.get(k, {})
        lines.append(f"{k}: version={t.get('version')} available={t.get('available')} path={t.get('path')}")
    lines += [
        "amrfinder_database_version: " + str(env.get("amrfinder_database_version")),
        "emapper available: " + str((env.get("emapper") or {}).get("available")),
        "",
        "Qwen: qwen3:4b",
        "Qwen digest: 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
        "Qwen quantization Q4_K_M: recorded in agentic_freeze/GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json (same digest)",
        "Sol post-hoc: gpt-5.6-sol reasoning=high",
        "",
        "WINDOWS FREEZE-MANIFEST SNAPSHOT (not M60 host)",
        "python_version: " + fm["environment"]["python_version"],
        "bioinformatics tools available on that snapshot: false",
        "",
        "environment.yml: python=3.11 + conda-forge/bioconda stack",
        "pyproject.toml requires-python >=3.11",
        "",
        "Seeds: sampling string 20260920; bootstrap integer 20260920; BOOTSTRAP_N=10000",
        "",
        "PIP_FREEZE (from M60_ENVIRONMENT.json)",
    ]
    for item in env.get("pip_freeze", []):
        lines.append(item)
    (OUT / "ENVIRONMENT_MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


CODE_ROWS = [
    ("scripts/run_m60_position.py", "M60 runner; freeze verify; arms; specialist; position lock", "prospective"),
    ("scripts/select_m60_cohort.py", "M60 cohort selection seed 20260920", "prospective"),
    ("scripts/build_m60_exclusion_manifest.py", "Exclusion set before sampling", "prospective"),
    ("scripts/finalize_m60_predictions.py", "Aggregate prediction lock", "prospective"),
    ("scripts/freeze_m60_truth_sources.py", "Truth source freeze", "prospective"),
    ("scripts/adjudicate_m60_truth.py", "Two-route automated truth", "prospective"),
    ("scripts/lock_m60_truth.py", "Phase 3 truth lock", "prospective"),
    ("scripts/lock_m60_phase3b.py", "Human review + final truth lock", "prospective"),
    ("scripts/m60_truth_common.py", "Truth gates and path guards", "prospective"),
    ("scripts/score_m60_phase4.py", "One-shot unblind statistics", "prospective"),
    ("scripts/freeze_manuscript_v4_1.py", "V4.1 freeze writer", "development/freeze"),
    ("src/genome_skeptic/manuscript/arms.py", "GS arm aliases", "frozen"),
    ("src/genome_skeptic/manuscript/scientific_core.py", "Shared-core hasher", "frozen"),
    ("src/genome_skeptic/agents/assembly_loop.py", "Initial measurement collection; evidence ledger helpers", "frozen"),
    ("src/genome_skeptic/agents/assembly_loop_v4_1_dev.py", "V4.1 loop; policies; planner/critic prompts", "frozen"),
    ("src/genome_skeptic/agents/assembly_loop_v2.py", "Registered action execution", "frozen"),
    ("src/genome_skeptic/agents/action_catalog.py", "Base action registry", "frozen"),
    ("src/genome_skeptic/agents/action_catalog_v4_1_dev.py", "V4.1 extra actions; ranking", "frozen"),
    ("src/genome_skeptic/agents/planner_views_v4_1_dev.py", "Planner/critic views", "frozen"),
    ("src/genome_skeptic/agents/diagnostic_needs_v4_1_dev.py", "Needs + family_identity_is_decisive", "frozen"),
    ("src/genome_skeptic/agents/ollama.py", "Ollama JSON client", "frozen"),
    ("src/genome_skeptic/agents/adapter.py", "OpenAI-compatible adapter", "frozen"),
    ("src/genome_skeptic/agents/providers.py", "Production M60 providers (Qwen/Ollama)", "frozen"),
    ("src/genome_skeptic/eval/baselines.py", "Conventional arm", "frozen"),
    ("src/genome_skeptic/eval/evaluate_real.py", "System dispatch including conventional", "frozen"),
    ("src/genome_skeptic/validators/falsification.py", "TargetMeasurements; classify_polarity; build_target_gene_claim", "frozen"),
    ("src/genome_skeptic/validators/family_orthology.py", "collect_family_evidence; family_detects_orthologue", "frozen"),
    ("src/genome_skeptic/validators/competitive_family.py", "discriminate_family", "frozen"),
    ("src/genome_skeptic/validators/locus_v4_dev.py", "refine_weak_family_classification", "frozen"),
    ("src/genome_skeptic/validators/locus_reconstruction.py", "domain_only architecture", "frozen"),
    ("src/genome_skeptic/validators/homology.py", "strong_hit thresholds", "frozen"),
    ("src/genome_skeptic/config.py", "Biological thresholds", "frozen"),
    ("src/genome_skeptic/families.py", "Family loader", "frozen"),
    ("config/qwen_agentic_dev.yaml", "M60 Agentic Qwen config", "frozen-config"),
    ("config/sol56_high_posthoc.yaml", "Sol post-hoc config", "post-hoc"),
    (
        "EXTERNAL_REVIEW_CLAUDE/posthoc_code/src/genome_skeptic/agents/providers.py",
        "Sol openai_api adapter (NOT frozen M60 src)",
        "post-hoc",
    ),
    (
        "EXTERNAL_REVIEW_CLAUDE/posthoc_code/scripts/run_sol56_full_ablation.py",
        "Sol full ablation runner",
        "post-hoc",
    ),
    (
        "manuscript_benchmark/POSTHOC_ERROR_ANALYSIS/_extract_frozen_error_artifacts.py",
        "Read-only forensic extract",
        "post-hoc",
    ),
]


def write_code_path() -> None:
    md = [
        "# Code path manifest",
        "",
        "Production call graph is described in `02_SYSTEM_ARCHITECTURE.md`.",
        "",
        "Hashes are SHA256 of working-tree bytes and LF-normalized bytes.",
        "On Windows, CRLF files may differ from git LF blobs; see `PROVENANCE_VERIFICATION.md`.",
        "",
        "| relative path | SHA256 (working tree) | SHA256 (LF-normalized) | purpose | status |",
        "|---|---|---|---|---|",
    ]
    for path, purpose, status in CODE_ROWS:
        p = ROOT / path
        if not p.exists():
            md.append(f"| `{path}` | MISSING | MISSING | {purpose} | {status} |")
            continue
        md.append(f"| `{path}` | `{sha256_file(p)}` | `{sha256_lf(p)}` | {purpose} | {status} |")
    (OUT / "CODE_PATH_MANIFEST.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")


KEY_REFS = [
    "manuscript_benchmark/GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json",
    "manuscript_benchmark/M60_PROTOCOL_V1_1.md",
    "manuscript_benchmark/M60_COHORT_MANIFEST.json",
    "manuscript_benchmark/M60_PREDICTION_LOCK_MANIFEST.json",
    "manuscript_benchmark/TRUTH_M60/M60_TRUTH_SOURCE_MANIFEST.json",
    "manuscript_benchmark/TRUTH_M60/M60_EXTERNAL_TRUTH_LOCKED.json",
    "manuscript_benchmark/TRUTH_M60/M60_TRUTH_LOCK_MANIFEST.json",
    "manuscript_benchmark/TRUTH_M60/M60_EXTERNAL_TRUTH_FINAL_LOCKED.json",
    "manuscript_benchmark/TRUTH_M60/M60_TRUTH_FINAL_LOCK_MANIFEST.json",
    "manuscript_benchmark/RESULTS_M60/M60_PHASE4_STOP.json",
    "manuscript_benchmark/RESULTS_M60/M60_FINAL_RESULTS.md",
    "manuscript_benchmark/SOL56_FULL_ABLATION/SOL56_M60_MANIFEST.json",
    "manuscript_benchmark/SOL56_SMALL_PREFLIGHT/SOL56_5CASE_MANIFEST.json",
    "manuscript_benchmark/POSTHOC_ERROR_ANALYSIS/POSTHOC_ERROR_ANALYSIS_MANIFEST.json",
]


def audit_files() -> list[Path]:
    skip_names = {"_build_audit_manifests.py"}
    files = []
    for p in OUT.rglob("*"):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts:
            continue
        if p.name in skip_names:
            continue
        files.append(p)
    return sorted(files)


def write_file_manifest() -> None:
    rows = []
    for p in audit_files():
        raw = p.read_bytes()
        rows.append(
            [
                "audit_package",
                rel(p),
                str(len(raw)),
                sha256_bytes(raw),
                sha256_bytes(raw.replace(b"\r\n", b"\n")),
                "yes",
            ]
        )
    for path in KEY_REFS:
        p = ROOT / path
        if not p.exists():
            rows.append(["scientific_pointer", path, "", "MISSING", "MISSING", "no"])
            continue
        raw = p.read_bytes()
        rows.append(
            [
                "scientific_pointer",
                path,
                str(len(raw)),
                sha256_bytes(raw),
                sha256_bytes(raw.replace(b"\r\n", b"\n")),
                "no",
            ]
        )
    with (OUT / "FILE_MANIFEST.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "kind",
                "relative_path",
                "bytes",
                "sha256_working_tree",
                "sha256_lf_normalized",
                "in_audit_package_dir",
            ]
        )
        w.writerows(rows)


def write_hash_manifest() -> None:
    """SHA256 of every audit-package file except this list file itself."""
    skip = {"HASH_MANIFEST.sha256"}
    lines = []
    for p in audit_files():
        if p.name in skip:
            continue
        lines.append(f"{sha256_file(p)}  {rel(p, OUT)}")
    (OUT / "HASH_MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_audit_package_manifest() -> None:
    files = []
    for p in audit_files():
        if p.name == "AUDIT_PACKAGE_MANIFEST.json":
            continue
        files.append({"path": rel(p, OUT), "sha256": sha256_file(p), "bytes": p.stat().st_size})
    files.sort(key=lambda x: x["path"])
    payload = {
        "kind": "AUDIT_PACKAGE_MANIFEST",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Independent pre-manuscript adversarial review package for Claude",
        "does_not_modify_frozen_science": True,
        "AUDIT_PACKAGE_READY_FOR_CLAUDE": "YES",
        "MECHANISTIC_ERROR_ANALYSIS_STATUS": "COMPLETE",
        "line_ending_note": "Protocol v1.1 advertised hash is LF-normalized; Windows working-tree SHA256 may differ by CRLF only.",
        "frozen_identifiers": {
            "git_commit": "8f66868850a98494778966bd729b88a6fc2952eb",
            "tag": "GENOME_SKEPTIC_V4_1_MANUSCRIPT",
            "scientific_core_hash": "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0",
            "system_manifest_sha256": "97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b",
            "protocol_v1_1_sha256_lf": "73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660",
            "cohort_sha256": "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655",
            "prediction_lock_sha256": "5317b33fa554f81855fa6c68854ad732c5f5127fc0ad41f224fede9159a90791",
            "final_truth_sha256": "a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9",
            "sol_preflight_sha256": "7b8ef9e24a5a6a395b6a685ef035f2671fff84bc75b7c3d9ab88553ef0bebc27",
            "sol_full_sha256": "2a9f86956ca12026b4ff39fc7bcaf297db992ba4db53421a9482683ae1885a39",
        },
        "n_files": len(files),
        "files": files,
    }
    text = json.dumps(payload, indent=2) + "\n"
    (OUT / "AUDIT_PACKAGE_MANIFEST.json").write_text(text, encoding="utf-8", newline="\n")
    print("AUDIT_PACKAGE_MANIFEST.json sha256", sha256_bytes(text.encode("utf-8")))


def main() -> None:
    write_environment()
    write_code_path()
    write_file_manifest()
    write_hash_manifest()
    write_audit_package_manifest()
    print("AUDIT_PACKAGE_MANIFEST.json sha256", sha256_file(OUT / "AUDIT_PACKAGE_MANIFEST.json"))
    print("audit manifests written")


if __name__ == "__main__":
    main()
