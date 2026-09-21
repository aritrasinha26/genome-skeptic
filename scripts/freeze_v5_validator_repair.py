#!/usr/bin/env python3
"""Write the GENOME_SKEPTIC_V5_VALIDATOR_REPAIR scientific freeze.

Does not change scientific code. Does not select genomes. Does not rerun M60.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.action_catalog import ACTION_IDS  # noqa: E402
from genome_skeptic.agents.action_catalog_v4_1_dev import (  # noqa: E402
    DECISION_NEED_RANK,
    NEED_PRIMARY_ACTIONS,
    V41_EXTRA_ACTION_IDS,
)
from genome_skeptic.agents.assembly_loop_v4_1_dev import (  # noqa: E402
    AGENTIC_CRITIC_SYSTEM,
    AGENTIC_REASONER_SYSTEM,
    MAX_EXHAUSTIVE_ACTIONS,
)
from genome_skeptic.config import Settings  # noqa: E402
from genome_skeptic.families import family_root  # noqa: E402
from genome_skeptic.validators.falsification import TargetMeasurements  # noqa: E402
from genome_skeptic.validators.ortholog_references import default_orthology_ref_root  # noqa: E402

FREEZE_ID = "GENOME_SKEPTIC_V5_VALIDATOR_REPAIR"
OUT = ROOT / "prospective_v5" / "01_V5_FREEZE"
SKIP = {"__pycache__", ".pytest_cache", ".git"}

V5_SOURCE = (
    "src/genome_skeptic/agents/assembly_loop.py",
    "src/genome_skeptic/agents/assembly_loop_v4_1_dev.py",
    "src/genome_skeptic/agents/action_catalog.py",
    "src/genome_skeptic/agents/action_catalog_v4_1_dev.py",
    "src/genome_skeptic/agents/action_contract.py",
    "src/genome_skeptic/agents/diagnostic_needs.py",
    "src/genome_skeptic/agents/diagnostic_needs_v4_dev.py",
    "src/genome_skeptic/agents/diagnostic_needs_v4_1_dev.py",
    "src/genome_skeptic/agents/providers.py",
    "src/genome_skeptic/config.py",
    "src/genome_skeptic/models.py",
    "src/genome_skeptic/families.py",
    "src/genome_skeptic/validators/falsification.py",
    "src/genome_skeptic/validators/family_orthology.py",
    "src/genome_skeptic/validators/competitive_family.py",
    "src/genome_skeptic/validators/ortholog_references.py",
    "src/genome_skeptic/validators/locus_stages_v4_1_dev.py",
    "src/genome_skeptic/validators/locus_reconstruction.py",
    "src/genome_skeptic/validators/locus_v4_dev.py",
    "src/genome_skeptic/validators/locus_multiplicity.py",
    "src/genome_skeptic/validators/homology.py",
    "src/genome_skeptic/claims/attack_plan.py",
    "src/genome_skeptic/claims/action_policy.py",
    "tests/test_v5_validator_repair.py",
    "config/sol56_high_posthoc.yaml",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_obj(obj) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")))


def hash_tree(root: Path | None) -> tuple[str, list[dict]]:
    if root is None or not root.exists():
        return sha256_text("missing"), []
    files = sorted(
        (p for p in root.rglob("*") if p.is_file() and not any(part in SKIP for part in p.parts)),
        key=lambda p: str(p).replace("\\", "/"),
    )
    rows = []
    for path in files:
        rel = path.relative_to(root.resolve()).as_posix()
        rows.append({"path": rel, "sha256": sha256_file(path)})
    return sha256_obj(rows), rows


def git_value(*args: str) -> str | None:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")
    return sha256_file(path)


def main() -> int:
    settings = Settings()
    source_hashes = {}
    for rel in V5_SOURCE:
        path = ROOT / rel
        source_hashes[rel] = sha256_file(path) if path.is_file() else "missing"

    family_dir = family_root()
    ortholog_dir = default_orthology_ref_root()
    family_hash, family_files = hash_tree(family_dir)
    ortholog_hash, ortholog_files = hash_tree(ortholog_dir)

    validator_hash = sha256_obj(
        {
            "falsification": source_hashes["src/genome_skeptic/validators/falsification.py"],
            "family_orthology": source_hashes["src/genome_skeptic/validators/family_orthology.py"],
            "competitive_family": source_hashes["src/genome_skeptic/validators/competitive_family.py"],
            "ortholog_references": source_hashes["src/genome_skeptic/validators/ortholog_references.py"],
            "locus_stages": source_hashes["src/genome_skeptic/validators/locus_stages_v4_1_dev.py"],
            "locus_reconstruction": source_hashes["src/genome_skeptic/validators/locus_reconstruction.py"],
            "locus_v4_dev": source_hashes["src/genome_skeptic/validators/locus_v4_dev.py"],
            "diagnostic_needs_v4_dev": source_hashes["src/genome_skeptic/agents/diagnostic_needs_v4_dev.py"],
            "diagnostic_needs_v4_1_dev": source_hashes["src/genome_skeptic/agents/diagnostic_needs_v4_1_dev.py"],
        }
    )
    action_registry_hash = sha256_obj(
        {
            "action_ids": list(ACTION_IDS),
            "v41_extra": sorted(V41_EXTRA_ACTION_IDS),
            "need_primary_actions": {k: list(v) for k, v in NEED_PRIMARY_ACTIONS.items()},
            "decision_need_rank": dict(DECISION_NEED_RANK),
        }
    )
    planner_prompt_hash = sha256_text(AGENTIC_REASONER_SYSTEM)
    critic_prompt_hash = sha256_text(AGENTIC_CRITIC_SYSTEM)
    scientific_core_hash = sha256_obj(
        {
            "source_file_hashes": source_hashes,
            "family_definitions_hash": family_hash,
            "reference_assets_hash": ortholog_hash,
            "target_measurements_schema": [f.name for f in fields(TargetMeasurements)],
            "validator_hash": validator_hash,
            "thresholds": settings.thresholds.model_dump(),
            "action_registry_hash": action_registry_hash,
            "planner_prompt_hash": planner_prompt_hash,
            "critic_prompt_hash": critic_prompt_hash,
            "follow_up_limits": {
                "planner_max_actions": 1,
                "critic_max_additional_actions": 1,
                "max_exhaustive_actions": MAX_EXHAUSTIVE_ACTIONS,
            },
        }
    )

    amrfinder = ROOT / "manuscript_benchmark" / "ENVIRONMENT" / "AMRFINDER_DATABASE_FREEZE.json"
    model_config = {
        "prospective_agentic_model": "gpt-5.6-sol",
        "prospective_reasoning": "high",
        "provider": "openai_api",
        "temperature": 0.0,
        "sol56_yaml": "config/sol56_high_posthoc.yaml",
        "sol56_yaml_sha256": source_hashes.get("config/sol56_high_posthoc.yaml"),
        "providers_py_sha256": source_hashes.get("src/genome_skeptic/agents/providers.py"),
        "llm_defaults": settings.llm.model_dump(),
        "note": "V5 Agentic-Sol uses gpt-5.6-sol with reasoning=high. Thresholds remain Settings() defaults.",
    }
    comparator_config = {
        "amrfinder_database_freeze": str(amrfinder.relative_to(ROOT)).replace("\\", "/") if amrfinder.is_file() else None,
        "amrfinder_database_freeze_sha256": sha256_file(amrfinder) if amrfinder.is_file() else None,
        "parser_fail_closed_required": True,
        "note": "Comparator parsing must fail closed if expected columns are absent. No silent default-to-negative.",
    }

    test_report = (OUT / "V5_TEST_REPORT.txt").read_text(encoding="utf-8") if (OUT / "V5_TEST_REPORT.txt").is_file() else ""
    payload = {
        "freeze_id": FREEZE_ID,
        "kind": "v5_scientific_freeze",
        "immutable_after_tag": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "git_tag": FREEZE_ID,
        "further_m60_tuning_after_repair": False,
        "scientific_core_sha256": scientific_core_hash,
        "validator_sha256": validator_hash,
        "reference_panel_hashes": {
            "family_definitions_hash": family_hash,
            "ortholog_reference_hash": ortholog_hash,
            "family_dir": None if family_dir is None else str(family_dir),
            "ortholog_dir": str(ortholog_dir),
            "n_family_files": len(family_files),
            "n_ortholog_files": len(ortholog_files),
        },
        "action_registry_hash": action_registry_hash,
        "planner_prompt_hash": planner_prompt_hash,
        "critic_prompt_hash": critic_prompt_hash,
        "target_measurements_schema": [f.name for f in fields(TargetMeasurements)],
        "thresholds": settings.thresholds.model_dump(),
        "follow_up_limits": {
            "planner_max_actions": 1,
            "critic_max_additional_actions": 1,
            "max_exhaustive_actions": MAX_EXHAUSTIVE_ACTIONS,
        },
        "model_configuration": model_config,
        "specialist_comparator_configuration": comparator_config,
        "source_file_sha256": source_hashes,
        "environment": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        "test_report_present": bool(test_report),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_text(OUT / "V5_SCIENTIFIC_CORE_HASH.txt", scientific_core_hash)
    write_text(
        OUT / "V5_DEVELOPMENT_BOUNDARY.md",
        """# V5 development boundary

M60, D8, D12, D20 and all associated known outcomes are DEVELOPMENT/HISTORICAL
and cannot be used for prospective V5 evaluation.

The V4.1 manuscript study remains frozen historical evidence. It must never be
rescored as prospective V5 confirmation.

Five remaining M60 tet(A) errors (positions 14, 19, 37, 41, 44) were
intentionally NOT used for further tuning. They were not inspected to derive
additional V5 rules.

After this freeze, no validator, threshold, reference panel, scientific
instrument, action, prompt, model configuration, or endpoint definition may
change. Any later change becomes V6 and requires another fresh cohort.
""",
    )
    man_sha = write_json(OUT / "V5_FREEZE_MANIFEST.json", payload)
    payload["freeze_manifest_sha256"] = man_sha
    write_json(OUT / "V5_FREEZE_MANIFEST.json", payload)
    print(f"V5_SCIENTIFIC_CORE_SHA256={scientific_core_hash}", flush=True)
    print(f"V5_VALIDATOR_SHA256={validator_hash}", flush=True)
    print(f"PLANNER_PROMPT_SHA256={planner_prompt_hash}", flush=True)
    print(f"CRITIC_PROMPT_SHA256={critic_prompt_hash}", flush=True)
    print(f"ACTION_REGISTRY_SHA256={action_registry_hash}", flush=True)
    print(f"OUTPUT {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
