"""Compare the installed scientific core with the frozen M60 core.

``scientific_core_hashes()`` hashes raw file bytes, so the same content checked
out with LF instead of CRLF line endings produces a different top-level hash.
This check compares each frozen component and file individually and treats a
text file as identical if its bytes match after line-ending normalisation.
Generated ``family.hmm`` caches (gitignored, rebuilt from the members) are
reported separately rather than counted as differences.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

FROZEN_REFERENCE = Path(__file__).resolve().parents[2] / "results" / "m60" / "frozen_core_reference.json"
GENERATED_CACHE_NAMES = {"family.hmm"}
CONTENT_COMPONENTS = (
    "target_measurements_schema_hash",
    "biological_thresholds_hash",
    "action_registry_hash",
    "endpoint_contracts_hash",
    "planner_prompt_hash",
    "critic_prompt_hash",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _variants(data: bytes) -> set[str]:
    out = {_sha(data)}
    if b"\0" not in data:
        lf = data.replace(b"\r\n", b"\n")
        out |= {_sha(lf), _sha(lf.replace(b"\n", b"\r\n"))}
    return out


def file_matches(path: Path, frozen_sha: str) -> bool:
    return path.is_file() and frozen_sha in _variants(path.read_bytes())


def _compare_tree(root: Path | None, frozen_files: dict[str, str], label: str) -> tuple[list[str], list[str]]:
    diffs: list[str] = []
    caches: list[str] = []
    if root is None or not root.exists():
        return [f"{label}: directory missing"], caches
    present = {p.relative_to(root).as_posix(): p for p in root.glob("**/*") if p.is_file()}
    for rel, sha in frozen_files.items():
        if rel not in present:
            diffs.append(f"{label}: missing {rel}")
        elif not file_matches(present[rel], sha):
            diffs.append(f"{label}: changed {rel}")
    for rel in sorted(set(present) - set(frozen_files)):
        if Path(rel).name in GENERATED_CACHE_NAMES:
            caches.append(f"{label}/{rel}")
        else:
            diffs.append(f"{label}: extra file {rel}")
    return diffs, caches


def compare_with_frozen(reference_path: Path = FROZEN_REFERENCE) -> dict[str, Any]:
    from genome_skeptic.families import family_root
    from genome_skeptic.manuscript.scientific_core import REPO_ROOT, scientific_core_hashes
    from genome_skeptic.validators.ortholog_references import default_orthology_ref_root

    ref = json.loads(reference_path.read_text(encoding="utf-8"))
    frozen = ref["components"]
    now = scientific_core_hashes()
    diffs: list[str] = []
    for key in CONTENT_COMPONENTS:
        if now.get(key) != frozen.get(key):
            diffs.append(f"component {key}")
    for rel, sha in frozen["source_file_hashes"].items():
        if not file_matches(REPO_ROOT / rel, sha):
            diffs.append(f"source {rel}")
    fam_diffs, fam_caches = _compare_tree(family_root(), ref["family_definition_files"], "target_families")
    orth_diffs, orth_caches = _compare_tree(
        default_orthology_ref_root(), ref["orthology_reference_files"], "orthology_references"
    )
    diffs += fam_diffs + orth_diffs
    return {
        "frozen_scientific_core_hash": ref["scientific_core_hash"],
        "frozen_git_commit": ref["git_commit"],
        "byte_level_scientific_core_hash": now["scientific_core_hash"],
        "byte_level_hash_matches": now["scientific_core_hash"] == ref["scientific_core_hash"],
        "content_identical_to_frozen": not diffs,
        "differences": diffs,
        "generated_caches_present": fam_caches + orth_caches,
    }
