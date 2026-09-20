"""Shared scientific-core hashes for the three manuscript V4.1 arms.

The arms differ only in follow-up test policy. This module hashes the shared
instruments so tests can prove equivalence before freeze.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from genome_skeptic.agents.action_catalog import ACTION_IDS
from genome_skeptic.agents.action_catalog_v4_1_dev import (
    DECISION_NEED_RANK,
    NEED_PRIMARY_ACTIONS,
    V41_EXTRA_ACTION_IDS,
)
from genome_skeptic.agents.assembly_loop_v4_1_dev import (
    AGENTIC_CRITIC_SYSTEM,
    AGENTIC_REASONER_SYSTEM,
    POLICY_AGENTIC,
    POLICY_DETERMINISTIC,
    POLICY_EXHAUSTIVE,
)
from genome_skeptic.claims.attack_plan import DETECTED_ATTACKS, NOT_DETECTED_ATTACKS
from genome_skeptic.config import Settings
from genome_skeptic.families import family_root
from genome_skeptic.validators.falsification import TargetMeasurements
from genome_skeptic.validators.ortholog_references import default_orthology_ref_root

REPO_ROOT = Path(__file__).resolve().parents[3]

SHARED_SOURCE = (
    "src/genome_skeptic/agents/assembly_loop.py",
    "src/genome_skeptic/agents/action_catalog.py",
    "src/genome_skeptic/agents/action_catalog_v4_1_dev.py",
    "src/genome_skeptic/agents/action_contract.py",
    "src/genome_skeptic/agents/diagnostic_needs_v4_1_dev.py",
    "src/genome_skeptic/config.py",
    "src/genome_skeptic/models.py",
    "src/genome_skeptic/families.py",
    "src/genome_skeptic/validators/falsification.py",
    "src/genome_skeptic/validators/family_orthology.py",
    "src/genome_skeptic/validators/competitive_family.py",
    "src/genome_skeptic/validators/ortholog_references.py",
    "src/genome_skeptic/validators/locus_stages_v4_1_dev.py",
    "src/genome_skeptic/validators/locus_reconstruction.py",
    "src/genome_skeptic/validators/locus_multiplicity.py",
    "src/genome_skeptic/validators/homology.py",
    "src/genome_skeptic/claims/attack_plan.py",
    "src/genome_skeptic/claims/action_policy.py",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_obj(obj: Any) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")))


def _hash_tree(root: Path | None, patterns: tuple[str, ...] = ("**/*",)) -> str:
    if root is None or not root.exists():
        return sha256_text("missing")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(p for p in root.glob(pattern) if p.is_file())
    files = sorted({p.resolve() for p in files}, key=lambda p: str(p).replace("\\", "/"))
    payload = []
    for path in files:
        rel = path.relative_to(root.resolve()).as_posix()
        payload.append({"path": rel, "sha256": sha256_file(path)})
    return sha256_obj(payload)


def _hash_listed_sources() -> dict[str, str]:
    out = {}
    for rel in SHARED_SOURCE:
        path = REPO_ROOT / rel
        out[rel] = sha256_file(path) if path.is_file() else "missing"
    return out


def scientific_core_hashes() -> dict[str, Any]:
    """Hashes that MUST be identical for GS-Deterministic, GS-Agentic, and GS-Exhaustive."""
    settings = Settings()
    family_dir = family_root()
    ortholog_dir = default_orthology_ref_root()
    source_hashes = _hash_listed_sources()
    payload = {
        "initial_measurement_code_hash": source_hashes["src/genome_skeptic/agents/assembly_loop.py"],
        "reference_assets_hash": _hash_tree(ortholog_dir),
        "family_definitions_hash": _hash_tree(family_dir),
        "target_measurements_schema_hash": sha256_obj([f.name for f in fields(TargetMeasurements)]),
        "validator_hash": sha256_obj(
            {
                "falsification": source_hashes["src/genome_skeptic/validators/falsification.py"],
                "family_orthology": source_hashes["src/genome_skeptic/validators/family_orthology.py"],
                "competitive_family": source_hashes["src/genome_skeptic/validators/competitive_family.py"],
                "ortholog_references": source_hashes["src/genome_skeptic/validators/ortholog_references.py"],
                "locus_stages": source_hashes["src/genome_skeptic/validators/locus_stages_v4_1_dev.py"],
            }
        ),
        "biological_thresholds_hash": sha256_obj(settings.thresholds.model_dump()),
        "action_registry_hash": sha256_obj(
            {
                "action_ids": list(ACTION_IDS),
                "v41_extra": sorted(V41_EXTRA_ACTION_IDS),
                "need_primary_actions": {k: list(v) for k, v in NEED_PRIMARY_ACTIONS.items()},
                "decision_need_rank": dict(DECISION_NEED_RANK),
            }
        ),
        "endpoint_contracts_hash": sha256_obj(
            {
                "detected_attacks": DETECTED_ATTACKS,
                "not_detected_attacks": NOT_DETECTED_ATTACKS,
            }
        ),
        "planner_prompt_hash": sha256_text(AGENTIC_REASONER_SYSTEM),
        "critic_prompt_hash": sha256_text(AGENTIC_CRITIC_SYSTEM),
        "source_file_hashes": source_hashes,
        "family_dir": None if family_dir is None else str(family_dir),
        "ortholog_dir": str(ortholog_dir),
    }
    payload["scientific_core_hash"] = sha256_obj(
        {k: payload[k] for k in (
            "initial_measurement_code_hash",
            "reference_assets_hash",
            "family_definitions_hash",
            "target_measurements_schema_hash",
            "validator_hash",
            "biological_thresholds_hash",
            "action_registry_hash",
            "endpoint_contracts_hash",
        )}
    )
    payload["follow_up_policy_hashes"] = {
        POLICY_DETERMINISTIC: sha256_obj({"policy": POLICY_DETERMINISTIC, "need_primary_actions": NEED_PRIMARY_ACTIONS}),
        POLICY_AGENTIC: sha256_obj({"policy": POLICY_AGENTIC, "planner": AGENTIC_REASONER_SYSTEM, "critic": AGENTIC_CRITIC_SYSTEM}),
        POLICY_EXHAUSTIVE: sha256_obj({"policy": POLICY_EXHAUSTIVE, "eligible": "all_registered_followups"}),
    }
    return payload


def assert_shared_scientific_core() -> dict[str, Any]:
    hashes = scientific_core_hashes()
    policy_hashes = hashes["follow_up_policy_hashes"]
    if len(set(policy_hashes.values())) != 3:
        raise AssertionError("follow-up policies must hash differently")
    return hashes
