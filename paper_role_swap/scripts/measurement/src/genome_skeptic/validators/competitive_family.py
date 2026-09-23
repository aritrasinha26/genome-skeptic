"""Competitive family discrimination.

Positive similarity to the requested family is not family identity.
The LLM does not invent scores. No gene-specific rescue rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.families import families_sharing_class, load_family
from genome_skeptic.models import TargetFamily
from genome_skeptic.tools.gene_search import search_proteins
from genome_skeptic.tools.hmmer import hmmer_tools_available, run_hmmsearch


def _candidate_aa_from_reconstruction(reconstruction: dict, contig_sequences: dict[str, str]) -> tuple[str | None, dict]:
    contig = reconstruction.get("contig")
    start = reconstruction.get("genomic_start")
    end = reconstruction.get("genomic_end")
    strand = reconstruction.get("strand") or "+"
    if not contig or start is None or end is None:
        return None, {}
    seq = contig_sequences.get(contig) or ""
    window = seq[max(0, int(start)): min(len(seq), int(end))].upper()
    if not window:
        return None, {"contig": contig, "genomic_start": start, "genomic_end": end, "strand": strand}
    from genome_skeptic.tools.gene_search import reverse_complement, translate_frame
    if str(strand).startswith("-"):
        window = reverse_complement(window)
    aa = max((translate_frame(window, f).replace("*", "") for f in range(3)), key=len, default="")
    return (aa or None), {"contig": contig, "genomic_start": start, "genomic_end": end, "strand": strand, "protein_length": len(aa or "")}


def _hydrophobic_tm_windows(aa: str) -> int:
    if not aa:
        return 0
    hydro = set("AILMFWV")
    n = 0
    i = 0
    while i + 18 <= len(aa):
        window = aa[i:i + 19]
        if sum(1 for c in window if c in hydro) / 19 >= 0.60:
            n += 1
            i += 19
        else:
            i += 1
    return n


def score_family_on_protein(family: TargetFamily, aa: str, settings: Settings, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    fa = out_dir / "candidate.faa"
    fa.write_text(f">candidate\n{aa}\n", encoding="utf-8")
    hmm_score = None
    hmm_cov = 0.0
    hmm_evalue = None
    from genome_skeptic.validators.family_orthology import _ensure_family_hmm
    hmm_path = _ensure_family_hmm(family, out_dir)
    if hmm_path is not None and "hmmsearch" in hmmer_tools_available():
        result = run_hmmsearch(hmm_path, fa, out_dir / f"hmm_{family.family_id}", settings.project.threads)
        by = (result.metrics or {}).get("by_target") or {}
        hit = by.get("candidate") or (next(iter(by.values()), None) if by else None)
        if hit:
            hmm_score = hit.get("full_score")
            hmm_cov = float(hit.get("model_coverage") or 0.0)
            hmm_evalue = hit.get("full_evalue")
    ident = None
    cov = None
    members = [(m.protein_id, m.sequence) for m in family.members if m.sequence]
    if members:
        hits = search_proteins("candidate", aa, members, settings)
        if hits:
            ident = max(h.identity for h in hits)
            cov = max(h.query_coverage for h in hits)
    bits = 0.0 if hmm_score is None else min(1.0, max(0.0, float(hmm_score) / 200.0))
    seq_term = 0.0 if ident is None or cov is None else ident * cov
    combined = round(0.55 * hmm_cov + 0.25 * bits + 0.20 * seq_term, 4)
    return {
        "family_id": family.family_id,
        "hmm_score": hmm_score,
        "hmm_model_coverage": round(hmm_cov, 4),
        "hmm_evalue": hmm_evalue,
        "sequence_identity": ident,
        "sequence_coverage": cov,
        "combined_score": combined,
    }


@dataclass
class CompetitiveFamilyEvidence:
    target_family: str | None = None
    candidate_locus: dict = field(default_factory=dict)
    target_family_score: float | None = None
    target_family_HMM_score: float | None = None
    target_family_model_coverage: float | None = None
    target_family_sequence_coverage: float | None = None
    best_competing_family: str | None = None
    competing_family_score: float | None = None
    competing_family_HMM_score: float | None = None
    competing_family_model_coverage: float | None = None
    score_margin: float | None = None
    domain_architecture: list = field(default_factory=list)
    protein_length: int | None = None
    transmembrane_topology: dict | None = None
    conserved_motif_evidence: dict | None = None
    reciprocal_family_assignment: str | None = None
    reference_family_placement: dict | None = None
    conflicting_evidence: list = field(default_factory=list)
    classification: str = "unresolved_candidate"
    evidence_ids: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    competitors_scored: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "target_family": self.target_family,
            "candidate_locus": self.candidate_locus,
            "target_family_score": self.target_family_score,
            "target_family_HMM_score": self.target_family_HMM_score,
            "target_family_model_coverage": self.target_family_model_coverage,
            "target_family_sequence_coverage": self.target_family_sequence_coverage,
            "best_competing_family": self.best_competing_family,
            "competing_family_score": self.competing_family_score,
            "competing_family_HMM_score": self.competing_family_HMM_score,
            "competing_family_model_coverage": self.competing_family_model_coverage,
            "score_margin": self.score_margin,
            "domain_architecture": self.domain_architecture,
            "protein_length": self.protein_length,
            "transmembrane_topology": self.transmembrane_topology,
            "conserved_motif_evidence": self.conserved_motif_evidence,
            "reciprocal_family_assignment": self.reciprocal_family_assignment,
            "reference_family_placement": self.reference_family_placement,
            "conflicting_evidence": self.conflicting_evidence,
            "classification": self.classification,
            "evidence_ids": self.evidence_ids,
            "provenance": self.provenance,
            "competitors_scored": self.competitors_scored,
        }


def discriminate_family(
    *,
    family: TargetFamily,
    reconstruction: dict,
    contig_sequences: dict[str, str],
    settings: Settings,
    out_dir: Path,
    candidate_aa: str | None = None,
) -> CompetitiveFamilyEvidence:
    ev = CompetitiveFamilyEvidence(
        target_family=family.family_id,
        domain_architecture=list(family.domain_architecture or []),
        evidence_ids=["E_family_hmm", "E_competitive_family"],
        provenance={
            "created_by": "deterministic_competitive_family",
            "llm_invented_scores": False,
            "gene_specific_rules": False,
        },
    )
    aa, locus = _candidate_aa_from_reconstruction(reconstruction, contig_sequences)
    if candidate_aa:
        aa = candidate_aa
    ev.candidate_locus = locus
    if not aa:
        ev.classification = "unresolved_candidate"
        ev.conflicting_evidence.append("candidate protein could not be translated from the reconstructed locus")
        return ev
    ev.protein_length = len(aa)
    tm = _hydrophobic_tm_windows(aa)
    ev.transmembrane_topology = {"hydrophobic_windows_19aa": tm, "measured": True} if tm else {"hydrophobic_windows_19aa": 0, "measured": True}
    out_dir.mkdir(parents=True, exist_ok=True)
    target = score_family_on_protein(family, aa, settings, out_dir / "target")
    ev.target_family_score = target["combined_score"]
    ev.target_family_HMM_score = target["hmm_score"]
    ev.target_family_model_coverage = target["hmm_model_coverage"]
    ev.target_family_sequence_coverage = target["sequence_coverage"]

    competitor_ids = list(dict.fromkeys(list(family.competing_families or []) + families_sharing_class(family)))
    competitor_ids = [c for c in competitor_ids if c != family.family_id]
    scored = []
    for cid in competitor_ids:
        other = load_family(cid)
        if other is None:
            ev.conflicting_evidence.append(f"competing family {cid} was not packaged")
            continue
        row = score_family_on_protein(other, aa, settings, out_dir / cid)
        scored.append(row)
    ev.competitors_scored = scored
    best = max(scored, key=lambda r: r["combined_score"]) if scored else None
    if best:
        ev.best_competing_family = best["family_id"]
        ev.competing_family_score = best["combined_score"]
        ev.competing_family_HMM_score = best["hmm_score"]
        ev.competing_family_model_coverage = best["hmm_model_coverage"]
        ev.score_margin = round((ev.target_family_score or 0) - best["combined_score"], 4)
        ev.reciprocal_family_assignment = family.family_id if (ev.score_margin or 0) > 0 else best["family_id"]
        ev.reference_family_placement = {"winner": ev.reciprocal_family_assignment, "margin": ev.score_margin}

    t = settings.thresholds
    gate = (ev.target_family_model_coverage or 0) >= t.hmm_min_gate_model_coverage
    margin = ev.score_margin
    band = t.family_competitive_ambiguous_band
    need = t.family_competitive_margin
    if not gate:
        if (ev.target_family_model_coverage or 0) > 0 and (ev.target_family_model_coverage or 0) <= t.hmm_domain_only_max_model_coverage:
            ev.classification = "domain_only"
        else:
            ev.classification = "unresolved_candidate"
        return ev
    if best and (best.get("hmm_model_coverage") or 0) < t.hmm_min_gate_model_coverage and (best.get("combined_score") or 0) < 0.30:
        ev.conflicting_evidence.append("best competing family did not pass the family gate and is not treated as an alternative identity")
        best = None
        ev.best_competing_family = None
        ev.competing_family_score = None
        ev.score_margin = ev.target_family_score
        ev.reciprocal_family_assignment = family.family_id
    tgt_ident = 0.0 if target.get("sequence_identity") is None or target.get("sequence_coverage") is None else float(target["sequence_identity"]) * float(target["sequence_coverage"])
    cmp_ident = 0.0
    if best and best.get("sequence_identity") is not None and best.get("sequence_coverage") is not None:
        cmp_ident = float(best["sequence_identity"]) * float(best["sequence_coverage"])
    if best is None:
        if competitor_ids and not scored:
            ev.classification = "unresolved_candidate"
            ev.conflicting_evidence.append("declared competing families were not packaged; strong family identity is withheld")
            return ev
        ev.classification = "target_family_supported"
        return ev
    if tgt_ident >= 0.70 and (tgt_ident - cmp_ident) >= 0.20:
        ev.classification = "target_family_supported"
        ev.reciprocal_family_assignment = family.family_id
        ev.reference_family_placement = {"winner": family.family_id, "identity_product": tgt_ident, "competing_identity_product": cmp_ident}
        return ev
    if cmp_ident >= 0.70 and (cmp_ident - tgt_ident) >= 0.20:
        ev.classification = "competing_family_preferred"
        ev.reciprocal_family_assignment = best["family_id"]
        ev.conflicting_evidence.append("a competing family is a better reciprocal sequence match than the requested family")
        return ev
    if margin is not None and margin >= need:
        ev.classification = "target_family_supported"
    elif margin is not None and margin <= -need:
        ev.classification = "competing_family_preferred"
        ev.conflicting_evidence.append("a competing family explains the locus at least as well as the requested family")
    elif margin is not None and abs(margin) < max(band, need):
        ev.classification = "ambiguous_family"
        ev.conflicting_evidence.append("requested and competing families are not separated by the pre-registered margin")
    else:
        ev.classification = "unresolved_candidate"
    if ev.classification == "target_family_supported" and tm >= 4 and (ev.target_family_model_coverage or 0) < t.hmm_unresolved_model_coverage and (margin is None or margin < need):
        ev.classification = "ambiguous_family"
        ev.conflicting_evidence.append("transmembrane-rich sequence with only partial family HMM coverage is not specific family identity")
    return ev
