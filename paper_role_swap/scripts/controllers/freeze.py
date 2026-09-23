"""Recompute frozen V5 hashes without rewriting freeze artifacts."""
from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from freeze_v5_validator_repair import (  # noqa: E402
    V5_SOURCE,
    hash_tree,
    sha256_file,
    sha256_obj,
    sha256_text,
)
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

EXPECTED = {
    "tag": "GENOME_SKEPTIC_V5_VALIDATOR_REPAIR",
    "commit": "92dfacad2b67aa53562f955c0a308eed5eaad6c4",
    "scientific_core": "86af163a1e427c83ed0010fbca69ba6a9f81b7a97ae1eda2f1be35179a8ea463",
    "validator": "cf6d6c5b26d74de9f475ba6d4d7de3ddef9b95d222c08efbbc202a2164d38672",
    "planner_prompt": "fcffbc11cf6afbe84731c15854d37e85d929b966318acc45567f5332819d0f63",
    "critic_prompt": "8b04802de10aea03d24b26633a17d68415db74db3ba82034b6b8d1cf75f2b60e",
    "action_registry": "185390460dd990516b89eab036b5c5da11e2d28ef3371c5e4917a4e2fd6ac899",
}


def compute_v5_hashes() -> dict:
    settings = Settings()
    source_hashes = {}
    for rel in V5_SOURCE:
        path = ROOT / rel
        source_hashes[rel] = sha256_file(path) if path.is_file() else "missing"
    family_hash, _family_files = hash_tree(family_root())
    ortholog_hash, _ortholog_files = hash_tree(default_orthology_ref_root())
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
    return {
        "scientific_core": scientific_core_hash,
        "validator": validator_hash,
        "planner_prompt": planner_prompt_hash,
        "critic_prompt": critic_prompt_hash,
        "action_registry": action_registry_hash,
        "source_file_hashes": source_hashes,
        "family_definitions_hash": family_hash,
        "reference_assets_hash": ortholog_hash,
        "follow_up_limits": {
            "planner_max_actions": 1,
            "critic_max_additional_actions": 1,
            "max_exhaustive_actions": MAX_EXHAUSTIVE_ACTIONS,
        },
    }


def verify_v5_freeze() -> dict:
    observed = compute_v5_hashes()
    rows = {}
    stop = False
    for key in ("scientific_core", "validator", "planner_prompt", "critic_prompt", "action_registry"):
        ok = observed[key] == EXPECTED[key]
        rows[key] = {"expected": EXPECTED[key], "observed": observed[key], "match": ok}
        if key in {"scientific_core", "validator"} and not ok:
            stop = True
    return {
        "expected": EXPECTED,
        "observed": {k: observed[k] for k in ("scientific_core", "validator", "planner_prompt", "critic_prompt", "action_registry")},
        "rows": rows,
        "scientific_core_or_validator_mismatch": stop,
        "all_match": all(row["match"] for row in rows.values()),
        "family_definitions_hash": observed["family_definitions_hash"],
        "reference_assets_hash": observed["reference_assets_hash"],
        "follow_up_limits": observed["follow_up_limits"],
    }


if __name__ == "__main__":
    payload = verify_v5_freeze()
    print(json.dumps(payload, indent=2))
    if payload["scientific_core_or_validator_mismatch"]:
        raise SystemExit("STOP: V5 scientific core or validator hash mismatch")
