from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from genome_skeptic.io_utils import read_fasta
from genome_skeptic.tools.gene_search import parse_gff_features


class HomologueSpec(BaseModel):
    id: str
    clade: str
    sequence: str | None = None


class ReferenceGenome(BaseModel):
    id: str
    fasta: str
    gff: str | None = None
    proteins: str | None = None
    taxonomy: str | None = None
    homologues: list[HomologueSpec] = Field(default_factory=list)


class ReferenceSet(BaseModel):
    references: list[ReferenceGenome] = Field(default_factory=list)


def load_reference_set(path: str | Path) -> list[dict]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    cfg = ReferenceSet.model_validate(raw)
    base = Path(path).parent
    loaded = []
    for ref in cfg.references:
        fasta = (base / ref.fasta).resolve() if not Path(ref.fasta).is_absolute() else Path(ref.fasta)
        gff = None
        proteins = None
        if ref.gff:
            gff = (base / ref.gff).resolve() if not Path(ref.gff).is_absolute() else Path(ref.gff)
        if ref.proteins:
            proteins = (base / ref.proteins).resolve() if not Path(ref.proteins).is_absolute() else Path(ref.proteins)
        seqs = dict(read_fasta(fasta)) if fasta.exists() else {}
        feats = parse_gff_features(gff) if gff and gff.exists() else []
        prot = dict(read_fasta(proteins)) if proteins and proteins.exists() else {}
        homologues = []
        for item in ref.homologues:
            dump = item.model_dump()
            if not dump.get("sequence"):
                dump["sequence"] = prot.get(item.id)
            homologues.append(dump)
        loaded.append({
            "id": ref.id,
            "fasta": str(fasta) if fasta.exists() else None,
            "gff": str(gff) if gff and gff.exists() else None,
            "proteins": str(proteins) if proteins and proteins.exists() else None,
            "taxonomy": ref.taxonomy,
            "sequences": seqs,
            "features": feats,
            "protein_sequences": prot,
            "homologues": homologues,
        })
    return loaded
