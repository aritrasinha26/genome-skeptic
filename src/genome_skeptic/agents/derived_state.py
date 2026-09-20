"""Hit-dependent derived measurements. The LLM never authors these values.

After an action changes ``TargetMeasurements.hits``, every deterministic field
that is a function of the hit set is regenerated from the new hits. Historical
evidence records are left untouched; only the current scientific state moves.
"""
from __future__ import annotations

from typing import Any

from genome_skeptic.agents.action_contract import FieldUpdate
from genome_skeptic.config import Settings
from genome_skeptic.models import GeneSearchHit
from genome_skeptic.validators.falsification import TargetMeasurements, _loci
from genome_skeptic.validators.locus_multiplicity import assess_multiplicity


class StaleDerivedState(RuntimeError):
    """Raised when a hits-dependent field disagrees with the current hit set."""


_STALE_LIMITATION_MARKERS = (
    "only one placed",
    "additional copies has not been run",
    "additional orfs were not searched",
    "cannot discover an unplaced second locus",
)


def candidate_loci(m: TargetMeasurements, settings: Settings) -> list[GeneSearchHit]:
    """Canonical distinct supported loci, the same clustering the validator uses."""
    return _loci(m.hits, settings)


def assert_hits_derived_consistent(m: TargetMeasurements, settings: Settings) -> None:
    """Hard guardrail: multiplicity representations must match ``_loci(hits)``."""
    n = len(candidate_loci(m, settings))
    fam = m.family_evidence
    if fam is None or not hasattr(fam, "reconstruction"):
        return
    recon = getattr(fam, "reconstruction", None) or {}
    multi = recon.get("multiplicity") or {}
    n_cand = multi.get("number_of_candidate_loci")
    if n_cand is None:
        return
    if int(n_cand) != n:
        raise StaleDerivedState(
            f"family_evidence.reconstruction.multiplicity.number_of_candidate_loci={n_cand} "
            f"but _loci(hits)={n}"
        )
    para = getattr(fam, "paralogue", None) or {}
    if n >= 2 and para.get("state") == "single_locus":
        raise StaleDerivedState(
            f"family_evidence.paralogue.state=single_locus but _loci(hits)={n}"
        )
    if n >= 2 and (multi.get("classification") or "") == "single_locus":
        raise StaleDerivedState(
            f"family_evidence.reconstruction.multiplicity.classification=single_locus "
            f"but _loci(hits)={n}"
        )


def recompute_derived_measurements(m: TargetMeasurements, settings: Settings) -> list[FieldUpdate]:
    """Regenerate copy number, paralogue, and family reconstruction summaries from hits.

    Does not rewrite the evidence ledger. Competitive-family scores already stored
    on the reconstruction are preserved; they are not LLM-authored and they are
    not a function of the extra hit coordinates.
    """
    fam = m.family_evidence
    if fam is None or not hasattr(fam, "reconstruction"):
        return []
    before = _family_blob(fam)
    _refresh_hit_dependent_family_state(m, settings)
    after = _family_blob(fam)
    if before == after:
        return []
    n = len(candidate_loci(m, settings))
    return [
        FieldUpdate(
            field="family_evidence",
            op="replace_family_evidence",
            origin="locus_multiplicity_clustering",
            n_new=1,
            detail={
                "reason": "recomputed hit-dependent derived fields after hits changed",
                "n_loci": n,
                "multiplicity": ((getattr(fam, "reconstruction", None) or {}).get("multiplicity") or {}).get(
                    "classification"
                ),
            },
        )
    ]


def _family_blob(fam: Any) -> str:
    if hasattr(fam, "as_dict"):
        import json

        return json.dumps(fam.as_dict(), sort_keys=True, default=str, separators=(",", ":"))
    return repr(fam)


def _locus_coord(hit: GeneSearchHit) -> dict[str, Any]:
    lo, hi = min(hit.tstart, hit.tend), max(hit.tstart, hit.tend)
    return {
        "contig": hit.contig_id,
        "contig_id": hit.contig_id,
        "start": lo,
        "end": hi,
        "genomic_start": lo,
        "genomic_end": hi,
        "strand": hit.strand or "+",
        "identity": hit.identity,
        "coverage": hit.query_coverage,
        "query_identity": hit.identity,
        "query_coverage": hit.query_coverage,
        "hmm_coverage": hit.query_coverage,
        "search_kind": hit.search_kind,
        "tool": hit.tool,
    }


def _refresh_hit_dependent_family_state(m: TargetMeasurements, settings: Settings) -> None:
    fam = m.family_evidence
    loci = candidate_loci(m, settings)
    n = len(loci)
    recon = dict(getattr(fam, "reconstruction", None) or {})
    competitive = recon.get("competitive_family")

    hmm_loci = [_locus_coord(h) for h in loci]
    multi = assess_multiplicity(
        family_id=getattr(fam, "family_id", None) or m.query_id,
        member_hits=list(getattr(fam, "member_hits", None) or []),
        query_hits=list(m.hits),
        hmm_loci=hmm_loci,
        contig_sequences=dict(m.contig_sequences or {}),
        settings=settings,
        paralogue_record=recon.get("paralogue_record"),
    )
    # Canonical count is _loci(hits), not a second clustering that can go stale.
    multi["number_of_candidate_loci"] = n
    if n <= 1:
        multi["classification"] = "single_locus"
    elif (multi.get("classification") or "single_locus") == "single_locus":
        n_contigs = len({h.contig_id for h in loci})
        multi["classification"] = "true_gene_duplication" if n_contigs >= 2 else "unresolved_multiple_hits"
    multi["coordinates"] = [
        {"contig": h.contig_id, "start": min(h.tstart, h.tend), "end": max(h.tstart, h.tend), "strand": h.strand or "+"}
        for h in loci
    ]
    multi["contigs"] = sorted({h.contig_id for h in loci})
    recon["multiplicity"] = multi
    recon["secondary_loci"] = hmm_loci[1:]
    if n >= 2:
        recon["paralogue_record"] = {
            "kind": "true_duplicated_paralogue",
            "classify_as": "close_paralogue",
            "state": "multiple_loci",
            "n_loci": n,
            "supported": True,
            "multiplicity_class": multi.get("classification"),
            "evidence_ids": ["E_multiplicity", "E_paralogy"],
            "provenance": {"created_by": "deterministic_locus_multiplicity", "collapsed_near_identical_copies": False},
        }
        fam.paralogue = {"state": "multiple_loci", "n_loci": n, "supported": True}
    else:
        existing_para = dict(getattr(fam, "paralogue", None) or {})
        if existing_para.get("state") == "multiple_loci":
            fam.paralogue = {"state": "single_locus", "n_loci": n, "supported": False}
        recon["paralogue_record"] = recon.get("paralogue_record") or {"state": "single_locus", "supported": False}

    if competitive is not None:
        recon["competitive_family"] = competitive
    fam.reconstruction = recon

    metrics = dict(getattr(fam, "metrics", None) or {})
    metrics["multiplicity_classification"] = multi.get("classification")
    metrics["n_loci"] = n
    fam.metrics = metrics

    limitations = [
        item
        for item in list(getattr(fam, "limitations", None) or [])
        if not any(marker in item.lower() for marker in _STALE_LIMITATION_MARKERS)
    ]
    fam.limitations = limitations
