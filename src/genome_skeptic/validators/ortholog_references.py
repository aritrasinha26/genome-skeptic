"""Generic sequence-decisive orthologue vs competing-family discriminator.

Uses an independent curated reference set. No accession-specific rules,
no D8/D12/D20/M80 sequences, and no annotation-name equality as truth.

Returns one of:
- TARGET_FAMILY_SUPPORTED
- COMPETING_FAMILY_PREFERRED
- UNRESOLVED_CANDIDATE
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from genome_skeptic.config import Settings
from genome_skeptic.tools.gene_search import search_proteins
from genome_skeptic.validators.competitive_family import _candidate_aa_from_reconstruction

TARGET_FAMILY_SUPPORTED = "TARGET_FAMILY_SUPPORTED"
COMPETING_FAMILY_PREFERRED = "COMPETING_FAMILY_PREFERRED"
UNRESOLVED_CANDIDATE = "UNRESOLVED_CANDIDATE"

TRUE_CATEGORIES = frozenset({"true_orthologue", "target_family", "true_ortholog"})
COMPETING_CATEGORIES = frozenset(
    {
        "competing_beta_galactosidase",
        "competing_family",
        "competing_paralogue",
        "competing_paralog",
    }
)

# Same identity-product gate already used by discriminate_family.
_DECISIVE_IDENTITY_PRODUCT = 0.70
_DECISIVE_MARGIN = 0.20


def default_orthology_ref_root() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "orthology_references"


def family_id_for_profile(profile: Any) -> str | None:
    return getattr(profile, "family_id", None) or getattr(profile, "query_id", None)


def reference_set_path(family_id: str | None, root: Path | None = None) -> Path | None:
    if not family_id:
        return None
    base = root or default_orthology_ref_root()
    index = base / family_id / "index.yaml"
    return index if index.is_file() else None


def has_ortholog_reference_set(family_id: str | None, root: Path | None = None) -> bool:
    return reference_set_path(family_id, root) is not None


def _read_fasta(path: Path) -> str:
    parts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            continue
        parts.append(line.strip())
    return "".join(parts).upper()


@dataclass(frozen=True)
class OrthologReference:
    protein_id: str
    category: str
    sequence: str
    sequence_sha256: str
    source: str
    accession: str
    provenance: str
    gene: str = ""
    organism: str = ""

    @property
    def is_true(self) -> bool:
        return self.category in TRUE_CATEGORIES

    @property
    def is_competing(self) -> bool:
        return self.category in COMPETING_CATEGORIES

    def as_record(self) -> dict[str, Any]:
        return {
            "protein_id": self.protein_id,
            "category": self.category,
            "source": self.source,
            "accession": self.accession,
            "sequence_sha256": self.sequence_sha256,
            "provenance": self.provenance,
            "gene": self.gene,
            "organism": self.organism,
            "length_aa": len(self.sequence),
        }


def load_ortholog_reference_set(family_id: str, root: Path | None = None) -> list[OrthologReference]:
    index_path = reference_set_path(family_id, root)
    if index_path is None:
        return []
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    members = []
    for row in payload.get("members") or []:
        fasta = index_path.parent / str(row["fasta"])
        seq = _read_fasta(fasta)
        digest = hashlib.sha256(seq.encode("ascii")).hexdigest()
        expected = str(row.get("sequence_sha256") or "")
        if expected and expected != digest:
            raise RuntimeError(f"orthology reference {row.get('protein_id')} hash mismatch")
        members.append(
            OrthologReference(
                protein_id=str(row["protein_id"]),
                category=str(row["category"]),
                sequence=seq,
                sequence_sha256=digest,
                source=str(row.get("source") or ""),
                accession=str(row.get("accession") or row["protein_id"]),
                provenance=str(row.get("provenance") or ""),
                gene=str(row.get("gene") or ""),
                organism=str(row.get("organism") or ""),
            )
        )
    return members


@dataclass
class OrthologReferenceEvidence:
    family_id: str | None = None
    classification: str = UNRESOLVED_CANDIDATE
    validator_classification: str = "unresolved_candidate"
    target_best_identity: float | None = None
    target_best_coverage: float | None = None
    target_identity_product: float = 0.0
    competing_best_identity: float | None = None
    competing_best_coverage: float | None = None
    competing_identity_product: float = 0.0
    score_margin: float = 0.0
    reciprocal_assignment: str | None = None
    best_true_reference: str | None = None
    best_competing_reference: str | None = None
    references_scored: list = field(default_factory=list)
    reference_records: list = field(default_factory=list)
    conflicting_evidence: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "classification": self.classification,
            "validator_classification": self.validator_classification,
            "target_best_identity": self.target_best_identity,
            "target_best_coverage": self.target_best_coverage,
            "target_identity_product": self.target_identity_product,
            "competing_best_identity": self.competing_best_identity,
            "competing_best_coverage": self.competing_best_coverage,
            "competing_identity_product": self.competing_identity_product,
            "score_margin": self.score_margin,
            "reciprocal_assignment": self.reciprocal_assignment,
            "best_true_reference": self.best_true_reference,
            "best_competing_reference": self.best_competing_reference,
            "references_scored": self.references_scored,
            "reference_records": self.reference_records,
            "conflicting_evidence": self.conflicting_evidence,
            "provenance": self.provenance,
        }


def _score_against(aa: str, refs: list[OrthologReference], settings: Settings) -> list[dict[str, Any]]:
    if not aa or not refs:
        return []
    proteins = [(ref.protein_id, ref.sequence) for ref in refs]
    hits = search_proteins("candidate", aa, proteins, settings)
    by_id: dict[str, dict[str, Any]] = {}
    for hit in hits:
        product = float(hit.identity) * float(hit.query_coverage)
        prev = by_id.get(hit.contig_id)
        if prev is None or product > prev["identity_product"]:
            by_id[hit.contig_id] = {
                "protein_id": hit.contig_id,
                "identity": hit.identity,
                "coverage": hit.query_coverage,
                "identity_product": round(product, 4),
            }
    return list(by_id.values())


def discriminate_ortholog_references(
    *,
    family_id: str,
    candidate_aa: str | None,
    settings: Settings,
    reconstruction: dict | None = None,
    contig_sequences: dict[str, str] | None = None,
    root: Path | None = None,
) -> OrthologReferenceEvidence:
    ev = OrthologReferenceEvidence(
        family_id=family_id,
        provenance={
            "created_by": "deterministic_ortholog_references",
            "llm_invented_scores": False,
            "accession_specific_rules": False,
            "annotation_name_equality": False,
            "d8_d12_d20_m80_used": False,
        },
    )
    refs = load_ortholog_reference_set(family_id, root)
    ev.reference_records = [ref.as_record() for ref in refs]
    aa = candidate_aa
    if not aa and reconstruction is not None:
        aa, _locus = _candidate_aa_from_reconstruction(reconstruction, contig_sequences or {})
    if not refs:
        ev.conflicting_evidence.append("no independent orthology reference set is packaged for this family")
        return ev
    if not aa:
        ev.conflicting_evidence.append("candidate protein could not be obtained for reference comparison")
        return ev

    true_refs = [ref for ref in refs if ref.is_true]
    comp_refs = [ref for ref in refs if ref.is_competing]
    true_scores = _score_against(aa, true_refs, settings)
    comp_scores = _score_against(aa, comp_refs, settings)
    ev.references_scored = [
        {**row, "category": "true_orthologue"} for row in true_scores
    ] + [{**row, "category": "competing_family"} for row in comp_scores]

    best_true = max(true_scores, key=lambda r: r["identity_product"]) if true_scores else None
    best_comp = max(comp_scores, key=lambda r: r["identity_product"]) if comp_scores else None
    tgt = float(best_true["identity_product"]) if best_true else 0.0
    cmp = float(best_comp["identity_product"]) if best_comp else 0.0
    ev.target_identity_product = tgt
    ev.competing_identity_product = cmp
    ev.score_margin = round(tgt - cmp, 4)
    if best_true:
        ev.best_true_reference = best_true["protein_id"]
        ev.target_best_identity = best_true["identity"]
        ev.target_best_coverage = best_true["coverage"]
    if best_comp:
        ev.best_competing_reference = best_comp["protein_id"]
        ev.competing_best_identity = best_comp["identity"]
        ev.competing_best_coverage = best_comp["coverage"]

    if tgt >= cmp:
        ev.reciprocal_assignment = ev.best_true_reference
    else:
        ev.reciprocal_assignment = ev.best_competing_reference

    if tgt >= _DECISIVE_IDENTITY_PRODUCT and (tgt - cmp) >= _DECISIVE_MARGIN:
        ev.classification = TARGET_FAMILY_SUPPORTED
        ev.validator_classification = "target_family_supported"
    elif cmp >= _DECISIVE_IDENTITY_PRODUCT and (cmp - tgt) >= _DECISIVE_MARGIN:
        ev.classification = COMPETING_FAMILY_PREFERRED
        ev.validator_classification = "competing_family_preferred"
        ev.conflicting_evidence.append("a competing reference is a better sequence match than the true-orthologue set")
    else:
        ev.classification = UNRESOLVED_CANDIDATE
        ev.validator_classification = "ambiguous_family"
        ev.conflicting_evidence.append("reference comparison is not sequence-decisive")
    return ev


def consume_ortholog_result_in_family_evidence(fam: Any, scored: OrthologReferenceEvidence) -> None:
    """Write the discriminator into family_evidence so the existing validator consumes it."""
    recon = dict(getattr(fam, "reconstruction", None) or {})
    recon["ortholog_reference_discrimination"] = scored.as_dict()
    competitive = dict(recon.get("competitive_family") or {})
    competitive.update(
        {
            "classification": scored.validator_classification,
            "target_family_sequence_coverage": scored.target_best_coverage,
            "target_family_score": scored.target_identity_product,
            "competing_family_score": scored.competing_identity_product,
            "score_margin": scored.score_margin,
            "reciprocal_family_assignment": scored.reciprocal_assignment,
            "conflicting_evidence": list(scored.conflicting_evidence),
            "competitors_scored": scored.references_scored,
            "provenance": {
                **dict(competitive.get("provenance") or {}),
                "consumed_ortholog_references": True,
                "created_by": "deterministic_ortholog_references",
                "llm_invented_scores": False,
            },
        }
    )
    recon["competitive_family"] = competitive
    fam.reconstruction = recon
    metrics = dict(getattr(fam, "metrics", None) or {})
    metrics["ortholog_reference_classification"] = scored.classification
    metrics["competitive_family_classification"] = scored.validator_classification
    fam.metrics = metrics
