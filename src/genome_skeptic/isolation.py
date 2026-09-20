"""Prevent the analysis agent from reading scorer-only ground truth.

Path-part checks are kept, but they are not the only protection. Resolved
paths, symlinks, parent traversal, configured hidden roots, environment
variables, and registered-action parameters are also blocked.
"""
from __future__ import annotations

import os
from pathlib import Path

HIDDEN_PATH_PARTS = frozenset({"hidden", "ground_truth", "scorer_only"})
HIDDEN_FILENAMES = frozenset({
    "truth.yaml",
    "simulation_provenance.yaml",
    "source_genome.fa",
    "genome_catalog.yaml",
    "held_out_accessions.yaml",
})
HIDDEN_ENV_VARS = (
    "GENOME_SKEPTIC_HIDDEN_ROOTS",
    "GENOME_SKEPTIC_TRUTH",
    "GENOME_SKEPTIC_SOURCE_GENOME",
    "GENOME_SKEPTIC_TRUTH_MANIFEST",
)


def hidden_roots() -> list[Path]:
    raw = os.environ.get("GENOME_SKEPTIC_HIDDEN_ROOTS", "")
    roots = []
    for part in raw.split(os.pathsep):
        if part.strip():
            roots.append(Path(part).expanduser().resolve())
    return roots


def _looks_hidden(p: Path) -> bool:
    parts = {part.lower() for part in p.parts}
    if parts & {x.lower() for x in HIDDEN_PATH_PARTS}:
        if "agent_visible" not in parts:
            return True
    if p.name.lower() in {n.lower() for n in HIDDEN_FILENAMES} and "agent_visible" not in parts:
        return True
    return False


def assert_agent_accessible(path: str | Path | None, *, role: str = "analysis") -> Path | None:
    """Raise if a path is in the hidden/scorer tree after resolution."""
    if path is None:
        return None
    raw = str(path)
    if any(marker in raw.replace("\\", "/").lower() for marker in ("/hidden/", "\\hidden\\", "/ground_truth/", "/scorer_only/")):
        # Still allow agent_visible copies that happen to mention the word later.
        if "agent_visible" not in raw.replace("\\", "/").lower():
            raise PermissionError(f"{role} cannot read hidden ground-truth path: {path}")
    p = Path(path)
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p
    for candidate in (p, resolved):
        if _looks_hidden(candidate):
            raise PermissionError(f"{role} cannot read hidden ground-truth path: {candidate}")
    for root in hidden_roots():
        for candidate in (p, resolved):
            try:
                cand = candidate if candidate.is_absolute() else candidate.resolve()
            except OSError:
                cand = candidate
            try:
                cand.relative_to(root)
            except ValueError:
                continue
            raise PermissionError(f"{role} cannot read path under hidden root {root}: {cand}")
    return p


def assert_action_args_accessible(arguments: dict | None, *, role: str = "registered_action") -> None:
    """Reject registered-action parameters that point at hidden truth."""
    if not arguments:
        return
    for key, value in arguments.items():
        if isinstance(value, (str, Path)):
            text = str(value)
            if any(tok in text.lower() for tok in ("truth.yaml", "source_genome", "simulation_provenance", "held_out")):
                assert_agent_accessible(text, role=f"{role}:{key}")
            elif Path(text).suffix in {".fa", ".fasta", ".fna", ".yaml", ".yml", ".fastq", ".fq", ".gff", ".gbk"} or "\\" in text or "/" in text:
                assert_agent_accessible(text, role=f"{role}:{key}")
        elif isinstance(value, dict):
            assert_action_args_accessible(value, role=role)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, (str, Path)):
                    assert_action_args_accessible({key: item}, role=role)


def reject_hidden_environment(*, role: str = "analysis") -> None:
    """Block using env vars as a side channel to hidden truth files."""
    for name in HIDDEN_ENV_VARS:
        if name == "GENOME_SKEPTIC_HIDDEN_ROOTS":
            continue
        value = os.environ.get(name)
        if value:
            assert_agent_accessible(value, role=f"{role}:env:{name}")
