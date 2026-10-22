"""Read-only access to the precomputed demo bundle under ``demo/results``.

The bundle is produced by ``demo/scripts/build_demo_bundle.py`` from locked
Genome Skeptic records. Nothing here computes or alters a biological result.
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = REPO_ROOT / "demo" / "results"


class BundleError(RuntimeError):
    """The precomputed bundle is missing or malformed."""


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise BundleError(f"missing bundle file: {path.relative_to(REPO_ROOT).as_posix()}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BundleError(f"malformed bundle file: {path.name}") from exc


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise BundleError(f"missing bundle file: {path.relative_to(REPO_ROOT).as_posix()}")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    return _read_json(RESULTS_DIR / "BUNDLE_MANIFEST.json")


@lru_cache(maxsize=1)
def load_case_index() -> list[dict[str, Any]]:
    rows = _read_json(RESULTS_DIR / "m60" / "case_index.json")
    if not isinstance(rows, list) or not rows:
        raise BundleError("case index is empty")
    return rows


def case_positions() -> list[int]:
    return [int(r["position"]) for r in load_case_index()]


@lru_cache(maxsize=64)
def load_case(position: int) -> dict[str, Any]:
    position = int(position)
    if position not in set(case_positions()):
        raise BundleError(f"no locked M60 case at position {position}")
    trace = _read_json(RESULTS_DIR / "m60" / "cases" / f"position_{position:02d}.json")
    if trace.get("case", {}).get("position") != position:
        raise BundleError(f"case file for position {position} is inconsistent")
    return trace


@lru_cache(maxsize=1)
def load_examples() -> list[dict[str, Any]]:
    return _read_json(RESULTS_DIR / "examples.json")


@lru_cache(maxsize=32)
def load_table(relpath: str) -> list[dict[str, str]]:
    """CSV table inside the bundle, e.g. ``m60/tables/system_summary.csv``."""
    return _read_csv(_safe(relpath))


@lru_cache(maxsize=32)
def load_bundle_json(relpath: str) -> Any:
    return _read_json(_safe(relpath))


@lru_cache(maxsize=32)
def load_doc(relpath: str) -> str:
    path = _safe(relpath)
    if not path.is_file():
        raise BundleError(f"missing bundle file: {relpath}")
    return path.read_text(encoding="utf-8")


def bundle_file_bytes(relpath: str) -> bytes:
    return _safe(relpath).read_bytes()


def _safe(relpath: str) -> Path:
    path = (RESULTS_DIR / relpath).resolve()
    if RESULTS_DIR.resolve() not in path.parents:
        raise BundleError("path escapes the results bundle")
    return path
