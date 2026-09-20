"""Freeze configuration before a held-out production run."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from genome_skeptic.claims.actions import ACTION_CLASS_BY_NAME
from genome_skeptic.claims.completeness import IMPORTANCE_WEIGHTS, TEST_IMPORTANCE
from genome_skeptic.config import Settings
from genome_skeptic.eval.catalog import FAST_PILOT_GENOME_IDS, GENOMES
from genome_skeptic.eval.scoring import METRIC_NAMES, SCIENTIFIC_METRICS


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_freeze_manifest(settings: Settings) -> dict:
    from genome_skeptic.config import is_fast_pilot

    fast_pilot = is_fast_pilot(settings)
    catalog = {
        "development": [g.genome_id for g in GENOMES if g.split == "development"],
        "held_out": [g.genome_id for g in GENOMES if g.split == "held_out"],
    }
    if fast_pilot:
        catalog = {
            "development": list(FAST_PILOT_GENOME_IDS["development"]),
            "held_out": list(FAST_PILOT_GENOME_IDS["held_out"]),
        }
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "FAST PILOT - NOT FINAL BENCHMARK. Frozen FAST_PILOT assembly/runtime settings only. "
            "Thresholds, claim rules, evidence rules, and scoring were not changed. "
            "Do not mix these scores with the full production benchmark."
            if fast_pilot
            else "Frozen before held-out evaluation. Do not edit thresholds, claim rules, labels, or tool parameters after this point."
        ),
        "fast_pilot": fast_pilot,
        "banner": settings.assembly.banner if fast_pilot else None,
        "thresholds": settings.thresholds.model_dump(),
        "execution": settings.execution.model_dump(),
        "assembly": settings.assembly.model_dump(),
        "paths": settings.paths.model_dump(),
        "project": settings.project.model_dump(),
        "catalog_genome_ids": catalog,
        "scoring_metrics": list(METRIC_NAMES),
        "scientific_metrics": list(SCIENTIFIC_METRICS),
        "action_classes": dict(ACTION_CLASS_BY_NAME),
        "test_importance": dict(TEST_IMPORTANCE),
        "importance_weights": dict(IMPORTANCE_WEIGHTS),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str)
    payload["sha256"] = _sha(encoded)
    payload["component_hashes"] = {
        "thresholds": _sha(json.dumps(payload["thresholds"], sort_keys=True)),
        "execution": _sha(json.dumps(payload["execution"], sort_keys=True)),
        "catalog": _sha(json.dumps(payload["catalog_genome_ids"], sort_keys=True)),
        "scoring": _sha(json.dumps(payload["scientific_metrics"])),
        "actions": _sha(json.dumps(payload["action_classes"], sort_keys=True)),
        "assembly": _sha(json.dumps(payload["assembly"], sort_keys=True)),
    }
    return payload


def write_freeze_manifest(path: Path, settings: Settings) -> dict:
    payload = build_freeze_manifest(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return payload
