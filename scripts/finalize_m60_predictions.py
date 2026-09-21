#!/usr/bin/env python3
"""Lock M60 prediction files and blinded efficiency after all 60 positions.

Does not open truth. Does not score accuracy. Does not read D20.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_ROOT = ROOT / "manuscript_benchmark" / "POSITION_LOCKS"
OUT = ROOT / "manuscript_benchmark"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj) -> str:
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")
    digest = sha256_file(path)
    (path.parent / f"{path.name}.sha256.json").write_text(
        json.dumps(
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": digest,
                "hashed_utc": datetime.now(timezone.utc).isoformat(),
                "truth_opened": False,
                "accuracy_scored": False,
                "d20_touched": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return digest


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def followups(row: dict) -> int:
    integ = row.get("integrity") or {}
    if integ.get("n_deterministic_followup_analyses") is not None:
        return int(integ["n_deterministic_followup_analyses"])
    acts = row.get("actions_executed") or []
    return len(acts) if isinstance(acts, list) else 0


def complete(row: dict) -> bool:
    return row.get("completion_status") == "complete"


def metrics(rows: list[dict], action_fn) -> dict:
    actions = [action_fn(r) for r in rows]
    runtimes = [float(r.get("runtime_seconds") or 0) for r in rows]
    n_ok = sum(1 for r in rows if complete(r))
    n = len(rows)
    return {
        "n": n,
        "complete": n_ok,
        "completion_rate": (n_ok / n) if n else 0,
        "total_followup_analyses": sum(actions),
        "median_followup_analyses_per_case": statistics.median(actions) if actions else None,
        "mean_followup_analyses_per_case": (sum(actions) / n) if n else None,
        "total_runtime_seconds": round(sum(runtimes), 3),
        "median_runtime_seconds_per_case": statistics.median(runtimes) if runtimes else None,
    }


def reduction(agent: dict, exh: dict) -> float | None:
    den = exh["total_followup_analyses"]
    if not den:
        return None
    return 100.0 * (den - agent["total_followup_analyses"]) / den


def main() -> int:
    conventional, specialist, det, agent, exh = [], [], [], [], []
    missing = []
    for pos in range(1, 61):
        pdir = LOCK_ROOT / f"position_{pos:02d}"
        lock_path = pdir / "POSITION_LOCK.json"
        if not lock_path.exists():
            missing.append(pos)
            continue
        lock = load(lock_path)
        target = lock["target"]
        spec_name = "AMRFINDERPLUS" if target == "tetA_tetracycline_efflux" else "NCBI_REFSEQ_PGAP"
        needed = {
            "CONVENTIONAL": conventional,
            spec_name: specialist,
            "GS_DETERMINISTIC_V4_1": det,
            "GS_AGENTIC_V4_1": agent,
            "GS_EXHAUSTIVE_V4_1": exh,
        }
        for name, bucket in needed.items():
            path = pdir / f"{name}.json"
            if not path.exists():
                missing.append(f"{pos}:{name}")
                continue
            bucket.append(load(path))
    if missing:
        raise SystemExit(f"cannot finalize; missing {missing}")
    if not (len(conventional) == len(specialist) == len(det) == len(agent) == len(exh) == 60):
        raise SystemExit(
            f"counts conv={len(conventional)} spec={len(specialist)} det={len(det)} agent={len(agent)} exh={len(exh)}"
        )

    stamp = datetime.now(timezone.utc).isoformat()
    common = {
        "freeze_id": "GENOME_SKEPTIC_V4_1_MANUSCRIPT",
        "git_commit": "8f66868850a98494778966bd729b88a6fc2952eb",
        "scientific_core_hash": "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0",
        "n_cases": 60,
        "do_not_regenerate": True,
        "truth_opened": False,
        "accuracy_scored": False,
        "d20_touched": False,
        "created_utc": stamp,
    }
    files = {
        "M60_CONVENTIONAL_LOCKED.json": {"kind": "M60_CONVENTIONAL_LOCKED", **common, "predictions": conventional},
        "M60_SPECIALIST_COMPARATORS_LOCKED.json": {
            "kind": "M60_SPECIALIST_COMPARATORS_LOCKED",
            **common,
            "predictions": specialist,
        },
        "M60_GS_DETERMINISTIC_LOCKED.json": {"kind": "M60_GS_DETERMINISTIC_LOCKED", **common, "predictions": det},
        "M60_GS_AGENTIC_LOCKED.json": {"kind": "M60_GS_AGENTIC_LOCKED", **common, "predictions": agent},
        "M60_GS_EXHAUSTIVE_LOCKED.json": {"kind": "M60_GS_EXHAUSTIVE_LOCKED", **common, "predictions": exh},
    }
    hashes = {}
    for name, payload in files.items():
        hashes[name] = write_json(OUT / name, payload)

    strata = {
        "all": agent,
        "tetA": [r for r in agent if r.get("target") == "tetA_tetracycline_efflux"],
        "rpoB": [r for r in agent if r.get("target") == "rpoB_RNAP_beta"],
        "routine": [r for r in agent if r.get("stratum") == "routine"],
        "challenge": [r for r in agent if r.get("stratum") == "challenge"],
    }
    exh_by_id = {(r.get("position"), r.get("accession"), r.get("target")): r for r in exh}

    def paired(subset):
        return [exh_by_id[(r.get("position"), r.get("accession"), r.get("target"))] for r in subset]

    efficiency = {
        "kind": "M60_BLINDED_EFFICIENCY",
        "truth_opened": False,
        "accuracy_scored": False,
        "d20_touched": False,
        "created_utc": stamp,
        "strata": {},
    }
    for label, subset in strata.items():
        a = metrics(subset, followups)
        e = metrics(paired(subset), followups)
        efficiency["strata"][label] = {
            "agentic": a,
            "exhaustive": e,
            "followup_action_reduction_percent": reduction(a, e),
        }
    hashes["M60_BLINDED_EFFICIENCY.json"] = write_json(OUT / "M60_BLINDED_EFFICIENCY.json", efficiency)

    manifest = {
        "kind": "M60_PREDICTION_LOCK_MANIFEST",
        "immutable": True,
        "n_cases": 60,
        "truth_opened": False,
        "accuracy_scored": False,
        "d20_touched": False,
        "created_utc": stamp,
        "file_sha256": hashes,
        "counts": {
            "conventional": len(conventional),
            "specialist": len(specialist),
            "gs_deterministic": len(det),
            "gs_agentic": len(agent),
            "gs_exhaustive": len(exh),
        },
        "agent_failures": sum(1 for r in agent if not complete(r)),
        "exhaustive_failures": sum(1 for r in exh if not complete(r)),
        "comparator_failures": sum(1 for r in specialist if not complete(r)),
        "conventional_failures": sum(1 for r in conventional if not complete(r)),
    }
    man_sha = write_json(OUT / "M60_PREDICTION_LOCK_MANIFEST.json", manifest)
    print(json.dumps({"manifest_sha256": man_sha, "file_sha256": hashes, "efficiency": efficiency["strata"]["all"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
