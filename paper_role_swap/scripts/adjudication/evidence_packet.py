"""Build, sanitize, and ablate COMMON_EVIDENCE_STATE packets."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

try:
    from leakage import assert_no_forbidden_fields
except ImportError:  # pragma: no cover
    from model_poc_v5.leakage import assert_no_forbidden_fields

FORBIDDEN_EXTRA = (
    "amrfinder",
    "m60_position",
    "development_role",
    "development_truth",
    "false_positive",
    "false_negative",
    "rescued",
    "validator",
    "claim_type",
    "final_claim",
    "correctness",
)


_TOKEN_RE = re.compile(
    r"\b("
    r"truth|ground_truth|correct|incorrect|rescued|known_error|posthoc|post_hoc|"
    r"false\s*positive|false\s*negative|known_failure|amrfinder|validator\s*output|"
    r"development\s*role|m60\s*result|deterministic\s*endpoint|case-selection|"
    r"m60\s*position\s*interpretation"
    r")\b",
    re.IGNORECASE,
)


def _strip_forbidden_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            lowered = str(key).lower()
            if lowered in {
                "truth",
                "ground_truth",
                "correct",
                "incorrect",
                "rescued",
                "known_error",
                "posthoc",
                "post_hoc",
                "correctness",
                "development_truth",
                "development_role",
                "amrfinder",
                "amrfinder_result",
                "validator_output",
                "final_claim_state",
                "claims",
                "claim",
                "m60_position",
                "false_positive",
                "false_negative",
            }:
                continue
            if any(tok in lowered for tok in ("validator", "claim_type", "amrfinder")):
                continue
            out[key] = _strip_forbidden_keys(value)
        return out
    if isinstance(obj, list):
        return [_strip_forbidden_keys(x) for x in obj]
    return obj


def assert_clean_for_models(obj: Any, *, label: str) -> None:
    assert_no_forbidden_fields(obj, label=label)
    text = json.dumps(obj, default=str)
    hits = sorted({m.group(1).lower() for m in _TOKEN_RE.finditer(text)})
    if hits:
        raise SystemExit(f"STOP: leakage tokens in {label}: {hits}")


def _summarize_family(family: dict[str, Any] | None) -> dict[str, Any] | None:
    if not family:
        return None
    metrics = family.get("metrics") or {}
    competitive = family.get("competitive_family") or {}
    recon = family.get("reconstruction") or {}
    best_hmm = family.get("best_hmm")
    hmm_summary = None
    if isinstance(best_hmm, dict):
        hmm_summary = {
            "full_score": best_hmm.get("full_score"),
            "full_evalue": best_hmm.get("full_evalue"),
            "model_coverage": best_hmm.get("model_coverage"),
            "query_coverage": best_hmm.get("query_coverage"),
            "n_domains": best_hmm.get("n_domains"),
        }
    competitors = []
    for row in competitive.get("competitors_scored") or []:
        if isinstance(row, dict):
            competitors.append(
                {
                    "family_id": row.get("family_id") or row.get("competitor_family"),
                    "combined_score": row.get("combined_score"),
                    "hmm_score": row.get("hmm_score"),
                    "hmm_model_coverage": row.get("hmm_model_coverage"),
                }
            )
    return {
        "family_id": family.get("family_id"),
        "architecture": family.get("architecture"),
        "supports_orthologue": family.get("supports_orthologue"),
        "domain_only": family.get("domain_only"),
        "n_member_hits": family.get("n_member_hits"),
        "metrics": {
            "best_member_identity": metrics.get("best_member_identity"),
            "best_member_coverage": metrics.get("best_member_coverage"),
            "hmm_model_coverage": metrics.get("hmm_model_coverage"),
            "hmm_query_coverage": metrics.get("hmm_query_coverage"),
            "hmm_full_score": metrics.get("hmm_full_score"),
            "hmm_full_evalue": metrics.get("hmm_full_evalue"),
            "reference_set_agreement": metrics.get("reference_set_agreement"),
        },
        "hmm_profile": hmm_summary,
        "competitive_family": {
            "classification": competitive.get("classification"),
            "target_family_score": competitive.get("target_family_score"),
            "target_family_HMM_score": competitive.get("target_family_HMM_score"),
            "target_family_model_coverage": competitive.get("target_family_model_coverage"),
            "best_competitor": competitive.get("best_competitor"),
            "score_margin": competitive.get("score_margin"),
            "competitors_scored": competitors[:8],
        },
        "reconstruction": {
            "architecture": recon.get("architecture"),
            "sequence_identity": recon.get("sequence_identity") or recon.get("query_identity"),
            "protein_coverage": recon.get("protein_coverage"),
            "hmm_coverage": recon.get("hmm_coverage"),
            "evidence_ids": recon.get("evidence_ids") or [],
        },
        "paralogue": family.get("paralogue"),
        "tools_run": family.get("tools_run") or [],
    }


def _classify_evidence_id(ev: dict[str, Any]) -> set[str]:
    """Return ablation classes this evidence belongs to."""
    blob = json.dumps(ev, default=str).lower()
    classes: set[str] = set()
    if any(tok in blob for tok in ("competitor", "competitive_family", "competing_family")):
        classes.add("competitor")
    if any(tok in blob for tok in ("hmm", "profile", "hmmer", "domain")):
        classes.add("hmm")
    if any(
        tok in blob
        for tok in (
            "homology",
            "identity",
            "blast",
            "pairwise",
            "member_hit",
            "orf_protein_similarity",
            "translated",
            "nucleotide",
        )
    ):
        classes.add("homology")
    eid = str(ev.get("id") or "").lower()
    summary = str(ev.get("summary") or "").lower()
    if "competitive" in eid or "competitor" in eid or "competitive" in summary:
        classes.add("competitor")
    if "hmm" in eid or "family_hmm" in eid or "profile" in eid:
        classes.add("hmm")
    if "member" in eid or "homology" in eid or "blast" in eid or "similarity" in summary:
        classes.add("homology")
    return classes


def build_common_evidence_packet(
    *,
    target: str,
    evidence_rows: list[dict[str, Any]],
    locus_rows: list[dict[str, Any]],
    family: dict[str, Any] | None,
    measurement_summary: dict[str, Any] | None,
    executed_analyses: list[str],
    initial_measurement_hash: str | None,
    final_evidence_state_hash: str | None,
) -> dict[str, Any]:
    clean_evidence = []
    for ev in evidence_rows:
        row = {
            "id": ev.get("id"),
            "summary": ev.get("summary"),
            "values": _strip_forbidden_keys(ev.get("values") or {}),
        }
        clean_evidence.append(row)
    loci = []
    for locus in locus_rows or []:
        loci.append(
            {
                "contig_id": locus.get("contig_id") or locus.get("contig"),
                "start": locus.get("start") or locus.get("tstart") or locus.get("genomic_start"),
                "end": locus.get("end") or locus.get("tend") or locus.get("genomic_end"),
                "strand": locus.get("strand"),
                "architecture_state": locus.get("architecture_state") or locus.get("architecture"),
                "evidence_ids": locus.get("evidence_ids") or [],
            }
        )
    packet = {
        "target": target,
        "biological_endpoint_options": ["PRESENT", "ABSENT", "UNRESOLVED"],
        "structured_biological_measurements": _strip_forbidden_keys(measurement_summary or {}),
        "candidate_loci": loci,
        "sequence_evidence": {
            "n_evidence_items": len(clean_evidence),
            "evidence_ids": [e["id"] for e in clean_evidence if e.get("id")],
        },
        "family_competitor_profile_architecture_evidence": _summarize_family(family),
        "evidence": clean_evidence,
        "valid_evidence_ids": [e["id"] for e in clean_evidence if e.get("id")],
        "executed_analyses": list(executed_analyses or []),
        "initial_measurement_hash": initial_measurement_hash,
        "final_evidence_state_hash": final_evidence_state_hash,
        "constraints": [
            "Answer only from the supplied biological evidence.",
            "Do not request additional analyses, tools, BLAST, HMM, or follow-ups.",
            "Do not invent measurements or evidence IDs.",
            "Cite at most 3 evidence IDs, copied verbatim from valid_evidence_ids.",
        ],
    }
    packet = _strip_forbidden_keys(packet)
    assert_clean_for_models(packet, label="common_evidence_packet")
    return packet


def ablate_packet(packet: dict[str, Any], ablation: str) -> dict[str, Any]:
    """Remove one evidence class without altering remaining numeric values."""
    out = copy.deepcopy(packet)
    class_map = {
        "ABLATION_A_COMPETITOR": "competitor",
        "ABLATION_B_HMM": "hmm",
        "ABLATION_C_HOMOLOGY": "homology",
    }
    needed = class_map[ablation]
    kept = []
    removed_ids = []
    for ev in out.get("evidence") or []:
        classes = _classify_evidence_id(ev)
        if needed in classes:
            removed_ids.append(ev.get("id"))
            continue
        kept.append(ev)
    out["evidence"] = kept
    out["valid_evidence_ids"] = [e["id"] for e in kept if e.get("id")]
    out["sequence_evidence"] = {
        "n_evidence_items": len(kept),
        "evidence_ids": list(out["valid_evidence_ids"]),
    }
    fam = out.get("family_competitor_profile_architecture_evidence")
    if isinstance(fam, dict):
        if needed == "competitor":
            fam["competitive_family"] = {
                "classification": None,
                "note": "competitor-family evidence removed for ablation",
                "competitors_scored": [],
            }
        elif needed == "hmm":
            fam["hmm_profile"] = None
            metrics = fam.get("metrics") or {}
            for key in (
                "hmm_model_coverage",
                "hmm_query_coverage",
                "hmm_full_score",
                "hmm_full_evalue",
            ):
                metrics[key] = None
            fam["metrics"] = metrics
            recon = fam.get("reconstruction") or {}
            recon["hmm_coverage"] = None
            fam["reconstruction"] = recon
        elif needed == "homology":
            metrics = fam.get("metrics") or {}
            metrics["best_member_identity"] = None
            metrics["best_member_coverage"] = None
            fam["metrics"] = metrics
            recon = fam.get("reconstruction") or {}
            recon["sequence_identity"] = None
            recon["protein_coverage"] = None
            fam["reconstruction"] = recon
            meas = out.get("structured_biological_measurements") or {}
            best = meas.get("best_hit")
            if isinstance(best, dict):
                best["identity"] = None
                best["coverage"] = None
                meas["best_hit"] = best
            out["structured_biological_measurements"] = meas
    out["ablation"] = ablation
    out["ablated_evidence_ids"] = removed_ids
    out = _strip_forbidden_keys(out)
    assert_clean_for_models(out, label=f"ablated_packet:{ablation}")
    return out


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
