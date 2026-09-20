"""Genome-level deterministic preprocessing cache.

ORF prediction, protein FASTA, and (when built) MMseqs target databases are
properties of the assembly, not of a target investigation. Four targets on the
same genome should reuse one preprocessing pass.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from genome_skeptic.tools.gene_search import extract_orfs


@dataclass
class GenomeWorkspace:
    key: str
    orfs: list[dict]
    orf_fasta: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


_WORKSPACES: dict[str, GenomeWorkspace] = {}


def assembly_prep_key(contig_seqs: dict[str, str], *, min_aa: int, edge_bp: int) -> str:
    h = hashlib.sha256()
    h.update(f"{int(min_aa)}:{int(edge_bp)}:{len(contig_seqs)}".encode())
    for cid, seq in sorted((contig_seqs or {}).items()):
        h.update(cid.encode("utf-8", "ignore"))
        h.update(b"\0")
        h.update(str(len(seq)).encode())
        h.update(b"\0")
        if seq:
            h.update(seq[:128].encode("ascii", "ignore"))
            h.update(seq[-128:].encode("ascii", "ignore"))
            h.update(str(hash(seq)).encode())
    return h.hexdigest()


def get_workspace(contig_seqs: dict[str, str], *, min_aa: int, edge_bp: int) -> GenomeWorkspace:
    key = assembly_prep_key(contig_seqs, min_aa=min_aa, edge_bp=edge_bp)
    cached = _WORKSPACES.get(key)
    if cached is not None:
        return cached
    orfs = extract_orfs(list((contig_seqs or {}).items()), min_aa=min_aa, edge_bp=edge_bp)
    ws = GenomeWorkspace(key=key, orfs=orfs)
    _WORKSPACES[key] = ws
    return ws


def orf_fasta_path(workspace: GenomeWorkspace, dest: Path) -> Path:
    """Write assembly ORFs once; reuse the FASTA for later target searches."""
    if workspace.orf_fasta is not None and Path(workspace.orf_fasta).exists():
        return Path(workspace.orf_fasta)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    records = [(o["orf_id"], o.get("sequence") or "") for o in workspace.orfs if o.get("sequence")]
    dest.write_text("".join(f">{name}\n{seq}\n" for name, seq in records), encoding="utf-8")
    workspace.orf_fasta = dest
    return dest


def clear_workspaces() -> None:
    _WORKSPACES.clear()
