"""Target-type-specific deterministic confidence. The LLM does not assign these values."""
from __future__ import annotations

from genome_skeptic.models import ClaimStatus, FalsificationResult, FalsificationTest, TargetType
from genome_skeptic.claims.state_machine import confidence_for as confidence_legacy


def _status_scale(status: ClaimStatus) -> float:
    if status == ClaimStatus.rejected:
        return 0.35
    if status == ClaimStatus.unresolved:
        return 0.70
    if status == ClaimStatus.weakened:
        return 0.88
    return 1.0


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, round(value, 4)))


def _test_flag(tests: list[FalsificationTest], prefix: str, result: FalsificationResult) -> bool:
    for test in tests:
        if test.test_id.split(":")[0] == prefix and test.status == "completed" and test.result == result:
            return True
    return False


def confidence_exact_allele(
    status: ClaimStatus,
    tests: list[FalsificationTest],
    *,
    homology_support: float,
    not_detected: bool,
    max_supported: float,
    identity: float | None = None,
    coverage: float | None = None,
) -> float:
    ident = identity if identity is not None else homology_support
    cov = coverage if coverage is not None else homology_support
    if not_detected:
        raw = 0.38 + 0.22 * (1.0 - homology_support)
        cap = min(max_supported - 0.15, 0.65)
        return _clip(raw * _status_scale(status), 0.12, cap)
    raw = 0.42 + 0.40 * (ident * cov) + 0.08 * homology_support
    if ident is not None and ident < 0.99:
        raw *= 0.72
    if cov is not None and cov < 0.95:
        raw *= 0.85
    return _clip(raw * _status_scale(status), 0.12, min(max_supported, 0.85))


def confidence_gene_orthologue(
    status: ClaimStatus,
    tests: list[FalsificationTest],
    *,
    homology_support: float,
    not_detected: bool,
    max_supported: float,
    family_metrics: dict | None = None,
) -> float:
    m = family_metrics or {}
    ident = float(m.get("best_member_identity") or 0.0)
    cov = float(m.get("best_member_coverage") or 0.0)
    hmm_cov = float(m.get("hmm_model_coverage") or 0.0)
    hmm_ev = m.get("hmm_full_evalue")
    hmm_ok = 1.0 if (hmm_ev is not None and hmm_ev <= 1e-10 and hmm_cov >= 0.70) else (0.5 * hmm_cov if hmm_cov else 0.0)
    if m.get("domain_only"):
        hmm_ok = min(hmm_ok, 0.25)
    ref_agree = float(m.get("reference_set_agreement") or 0.0)
    rbh = 1.0 if "reciprocal_best_hit" in (m.get("hierarchy") or []) else (0.4 if m.get("rbh_unknown", True) else 0.0)
    synteny = 1.0 if "synteny" in (m.get("hierarchy") or []) else 0.45
    fusion_split = 1.0 if m.get("architecture") in {"fusion", "biological_split"} else (0.55 if m.get("architecture") == "assembly_fragmented" else 0.35)
    depth = float(m.get("depth_ok", 0.55))
    edge_ok = 0.0 if m.get("contig_edge") else 1.0
    para_ok = 0.0 if m.get("paralogue") else 1.0
    tax_ok = 0.0 if m.get("contradictory_taxonomy") else 1.0
    phylo = 1.0 if "phylogenetic_placement" in (m.get("hierarchy") or []) else 0.5

    if not_detected:
        family_signal = max(ident * cov, hmm_ok, ref_agree)
        raw = 0.40 + 0.22 * (1.0 - family_signal) + 0.08 * (1.0 - homology_support)
        if m.get("architecture") == "domain_only":
            raw = min(raw, 0.48)
        cap = min(max_supported - 0.12, 0.65)
        return _clip(raw * _status_scale(status), 0.10, cap)

    raw = (
        0.16
        + 0.14 * min(1.0, ident * cov if ident and cov else homology_support)
        + 0.16 * hmm_ok
        + 0.10 * min(1.0, float(m.get("domain_completeness_score") or hmm_cov))
        + 0.12 * ref_agree
        + 0.07 * rbh
        + 0.05 * synteny
        + 0.06 * fusion_split
        + 0.04 * depth
        + 0.03 * edge_ok
        + 0.04 * para_ok
        + 0.03 * tax_ok
        + 0.02 * phylo
    )
    if _test_flag(tests, "wrong_paralogue", FalsificationResult.weakens_claim):
        raw -= 0.08
    if _test_flag(tests, "taxonomic_inconsistency", FalsificationResult.weakens_claim):
        raw -= 0.06
    if m.get("architecture") == "fusion" and hmm_ok >= 0.7:
        raw = max(raw, 0.58)
    if m.get("architecture") == "divergent_full_length" and hmm_ok >= 0.7:
        raw = max(raw, 0.55)
    return _clip(raw * _status_scale(status), 0.12, min(max_supported, 0.85))


def confidence_protein_family(
    status: ClaimStatus,
    tests: list[FalsificationTest],
    *,
    homology_support: float,
    not_detected: bool,
    max_supported: float,
    family_metrics: dict | None = None,
) -> float:
    m = family_metrics or {}
    hmm_cov = float(m.get("hmm_model_coverage") or 0.0)
    hmm_ev = m.get("hmm_full_evalue")
    hmm = 0.0
    if hmm_ev is not None and hmm_ev <= 1e-5:
        hmm = min(1.0, 0.4 + 0.6 * hmm_cov)
    if not_detected:
        raw = 0.36 + 0.24 * (1.0 - max(homology_support, hmm))
        return _clip(raw * _status_scale(status), 0.10, min(max_supported - 0.15, 0.62))
    raw = 0.22 + 0.38 * hmm + 0.22 * homology_support + 0.08 * min(1.0, float(m.get("hmm_n_domains") or 0) / 3.0)
    return _clip(raw * _status_scale(status), 0.12, min(max_supported, 0.82))


def confidence_for_target_type(
    status: ClaimStatus,
    tests: list[FalsificationTest],
    *,
    target_type: TargetType | None,
    homology_support: float,
    not_detected: bool,
    max_supported: float,
    family_metrics: dict | None = None,
    identity: float | None = None,
    coverage: float | None = None,
) -> float:
    if target_type == TargetType.exact_allele:
        return confidence_exact_allele(
            status, tests, homology_support=homology_support, not_detected=not_detected,
            max_supported=max_supported, identity=identity, coverage=coverage,
        )
    if target_type == TargetType.gene_orthologue:
        return confidence_gene_orthologue(
            status, tests, homology_support=homology_support, not_detected=not_detected,
            max_supported=max_supported, family_metrics=family_metrics,
        )
    if target_type == TargetType.protein_family:
        return confidence_protein_family(
            status, tests, homology_support=homology_support, not_detected=not_detected,
            max_supported=max_supported, family_metrics=family_metrics,
        )
    return confidence_legacy(
        status, tests, base=0.55 if not_detected else 0.70, max_supported=max_supported,
        not_detected=not_detected, homology_support=homology_support,
    )
