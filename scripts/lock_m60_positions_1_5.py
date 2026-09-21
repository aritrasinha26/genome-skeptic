#!/usr/bin/env python3
"""Build positions 1-5 efficiency table and combined lock. Does not rerun arms."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_ROOT = ROOT / "manuscript_benchmark" / "POSITION_LOCKS"
OUT_TABLE = ROOT / "manuscript_benchmark" / "M60_POSITIONS_1_5_EFFICIENCY.json"
OUT_LOCK = ROOT / "manuscript_benchmark" / "M60_POSITIONS_1_5_LOCK.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def followups(row: dict) -> int:
    integ = row.get("integrity") or {}
    if integ.get("n_deterministic_followup_analyses") is not None:
        return int(integ["n_deterministic_followup_analyses"])
    acts = row.get("actions_executed") or []
    if isinstance(acts, list):
        return len(acts)
    return 0


def main() -> int:
    rows = []
    position_locks = {}
    for pos in range(1, 6):
        pdir = LOCK_ROOT / f"position_{pos:02d}"
        lock = load(pdir / "POSITION_LOCK.json")
        agent = load(pdir / "GS_AGENTIC_V4_1.json")
        exh = load(pdir / "GS_EXHAUSTIVE_V4_1.json")
        rows.append(
            {
                "position": pos,
                "target": lock["target"],
                "stratum": lock["stratum"],
                "accession": lock["accession"],
                "case_id": lock["case_id"],
                "agent_followup_actions": followups(agent),
                "exhaustive_followup_actions": followups(exh),
                "agent_runtime_seconds": agent.get("runtime_seconds"),
                "exhaustive_runtime_seconds": exh.get("runtime_seconds"),
                "agent_peak_memory": agent.get("peak_memory"),
                "exhaustive_peak_memory": exh.get("peak_memory"),
                "agent_llm_calls": agent.get("model_call_count")
                or ((agent.get("planner_calls") or 0) + (agent.get("critic_calls") or 0) + (agent.get("repair_calls") or 0)),
                "accuracy_scored": False,
            }
        )
        position_locks[str(pos)] = {
            "position_lock_sha256": sha256_file(pdir / "POSITION_LOCK.json"),
            "outputs": lock.get("output_sha256"),
            "case_id": lock["case_id"],
            "accession": lock["accession"],
            "target": lock["target"],
            "stratum": lock["stratum"],
        }
    table = {
        "kind": "M60_POSITIONS_1_5_EFFICIENCY",
        "n_positions": 5,
        "accuracy_scored": False,
        "truth_opened": False,
        "d20_touched": False,
        "note": "Prospective efficiency only. Cases with equal agent/exhaustive action counts are retained.",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }
    OUT_TABLE.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    table_sha = sha256_file(OUT_TABLE)
    (OUT_TABLE.with_name(OUT_TABLE.name + ".sha256.json")).write_text(
        json.dumps({"path": str(OUT_TABLE.relative_to(ROOT)).replace("\\", "/"), "sha256": table_sha}, indent=2) + "\n",
        encoding="utf-8",
    )
    lock_blob = {
        "kind": "M60_POSITIONS_1_5_LOCK",
        "immutable": True,
        "n_positions": 5,
        "positions_complete": "5 / 60",
        "truth_opened": False,
        "d20_touched": False,
        "accuracy_scored": False,
        "scientific_core_hash": "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0",
        "m60_manifest_sha256": "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655",
        "amrfinder_database_freeze_sha256": "d7ae98063c3b7795fa443f90f51a267e5b28002e1e5d59f364f403dde8a188be",
        "efficiency_table_sha256": table_sha,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "positions": position_locks,
    }
    OUT_LOCK.write_text(json.dumps(lock_blob, indent=2) + "\n", encoding="utf-8")
    lock_sha = sha256_file(OUT_LOCK)
    (OUT_LOCK.with_name(OUT_LOCK.name + ".sha256.json")).write_text(
        json.dumps({"path": str(OUT_LOCK.relative_to(ROOT)).replace("\\", "/"), "sha256": lock_sha}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"efficiency_sha256": table_sha, "lock_sha256": lock_sha, "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
