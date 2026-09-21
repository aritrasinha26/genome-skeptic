#!/usr/bin/env python3
"""Second-pass review and lock of M60 independent truth.

Does not open prediction payloads. Does not score accuracy.
Automated second pass is NOT a second human curator.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from m60_truth_common import (  # noqa: E402
    CASE_RECORDS,
    FINAL,
    REVIEW,
    SEQ_DECISIVE_DELTA,
    SEQ_DECISIVE_PRODUCT,
    TRUTH_ROOT,
    load_cohort_metadata,
    sha256_file,
    utc_now,
    write_json,
    write_sha256_sidecar,
)


def load_pass1() -> list[dict]:
    rows = []
    for pos in range(1, 61):
        p = CASE_RECORDS / f"position_{pos:02d}.json"
        if not p.exists():
            raise SystemExit(f"missing pass1 record {p}")
        rec = json.loads(p.read_text(encoding="utf-8"))
        for banned in ("final_result", "claim_type", "binary_call", "amrfinder", "pgap", "prediction"):
            blob = json.dumps(rec).lower()
            if banned == "prediction" and "prediction_values_included" in blob:
                continue
            if banned in rec:
                raise SystemExit(f"prediction leak key {banned} in {p}")
        rows.append(rec)
    return rows


def needs_review(rec: dict) -> list[str]:
    reasons = []
    if rec.get("truth_value") == "TRUTH_UNCERTAIN" or rec.get("pass1_truth") == "TRUTH_UNCERTAIN":
        reasons.append("TRUTH_UNCERTAIN")
    if rec.get("evidence_route_concordance") == "DISCORDANT":
        reasons.append("evidence_route_discordance")
    if rec.get("evidence_route_concordance") == "INSUFFICIENT":
        reasons.append("insufficient_evidence_routes")
    ts = rec.get("sequence_similarity")
    cov = rec.get("sequence_coverage")
    if rec.get("target") == "tetA_tetracycline_efflux":
        ident = ts or 0
        coverage = cov or 0
        prod = ident * coverage
        if 0.40 <= prod < SEQ_DECISIVE_PRODUCT:
            reasons.append("borderline_tetA_target_vs_competitor")
        fam = rec.get("family_or_profile_result") or {}
        t = fam.get("target_hmm_model_coverage") or 0
        c = fam.get("competitor_hmm_model_coverage") or 0
        if abs(t - c) < 0.10 and max(t, c) >= 0.20:
            reasons.append("borderline_tetA_profile_margin")
    if rec.get("stratum") == "challenge":
        if rec.get("n_orfs_scored", 0) == 0:
            reasons.append("challenge_incomplete_evidence")
        if rec.get("sequence_similarity") is None and rec.get("truth_value") != "NEGATIVE":
            reasons.append("challenge_incomplete_evidence")
    if rec.get("target") == "rpoB_RNAP_beta":
        why = (rec.get("primary_evidence_summary") or "") + " " + (rec.get("secondary_evidence_summary") or "")
        if "partial" in why or "fragment" in why or "split" in why or "near_threshold" in why:
            reasons.append("rpoB_partial_or_fragmented_candidate")
        phy = rec.get("orthology_or_phylogeny_result") or {}
        if rec.get("truth_value") != "NEGATIVE" and rec.get("n_orfs_scored", 0) > 0:
            ratio_note = rec.get("adjudication_rationale") or ""
            if "fragment" in ratio_note or "partial" in why:
                reasons.append("rpoB_partial_or_fragmented_candidate")
    return sorted(set(reasons))


def resolve_pass2(rec: dict, reasons: list[str]) -> dict:
    """Independent second look at the same evidence record. No prediction access."""
    p1 = rec.get("pass1_truth") or rec.get("truth_value")
    r1 = (rec.get("evidence_route_1") or {}).get("value")
    r2 = (rec.get("evidence_route_2") or {}).get("value")
    conc = rec.get("evidence_route_concordance")
    ts = rec.get("sequence_similarity") or 0.0
    cov = rec.get("sequence_coverage") or 0.0
    prod = ts * cov
    fam = rec.get("family_or_profile_result") or {}
    t_hmm = fam.get("target_hmm_model_coverage") or 0.0
    c_hmm = fam.get("competitor_hmm_model_coverage") or 0.0

    p2 = p1
    note = "second_pass_confirmed_pass1"
    if not reasons:
        return {
            "pass2_truth": p2,
            "agreement": True,
            "review_reason": [],
            "final_truth": p1,
            "resolution_note": "no automatic review flag; pass1 retained",
            "human_review_required": False,
            "truth_status": "ADJUDICATED" if p1 != "TRUTH_UNCERTAIN" else "DISAGREEMENT_UNRESOLVED",
        }

    # Sequence-decisive tetA/rpoB can confirm POSITIVE/NEGATIVE even if profile is weaker.
    if rec.get("target") == "tetA_tetracycline_efflux":
        if p1 == "POSITIVE" and prod < 0.40:
            p2 = "TRUTH_UNCERTAIN"
            note = "pass2_blocked_tetA_positive_without_sequence_support"
        elif prod >= SEQ_DECISIVE_PRODUCT and (p1 == "POSITIVE" or r1 == "POSITIVE"):
            p2 = "POSITIVE"
            note = "pass2_sequence_decisive_tetA_family_match"
        elif p1 == "NEGATIVE" and rec.get("n_orfs_scored", 0) == 0:
            p2 = "NEGATIVE"
            note = "pass2_confirmed_no_tetA_candidate"
        elif conc == "DISCORDANT" and abs(t_hmm - c_hmm) < 0.10 and prod < SEQ_DECISIVE_PRODUCT:
            p2 = "TRUTH_UNCERTAIN"
            note = "pass2_unresolved_target_vs_competitor"

    if rec.get("target") == "rpoB_RNAP_beta":
        if p1 == "POSITIVE" and ts >= 0.60 and cov >= 0.80:
            p2 = "POSITIVE"
            note = "pass2_confirmed_full_length_rpoB"
        elif p1 == "NEGATIVE" and rec.get("n_orfs_scored", 0) == 0:
            p2 = "NEGATIVE"
            note = "pass2_confirmed_no_rpoB_candidate"
        elif conc == "DISCORDANT":
            p2 = "TRUTH_UNCERTAIN"
            note = "pass2_discordant_rpoB_routes_unresolved"

    if p1 == "TRUTH_UNCERTAIN":
        # Do not force uncertainty into NEGATIVE.
        p2 = "TRUTH_UNCERTAIN"
        note = "pass2_retained_uncertainty"

    human = p2 == "TRUTH_UNCERTAIN" or conc == "DISCORDANT"
    final = p2
    if p1 != p2 and not (p1 == "TRUTH_UNCERTAIN" or p2 == "TRUTH_UNCERTAIN"):
        # unresolved disagreement between passes
        final = "TRUTH_UNCERTAIN"
        note = "pass1_pass2_disagreement_unresolved"
        human = True
    return {
        "pass2_truth": p2,
        "agreement": p1 == p2,
        "review_reason": reasons,
        "final_truth": final,
        "resolution_note": note,
        "human_review_required": human,
        "truth_status": "DISAGREEMENT_UNRESOLVED" if final == "TRUTH_UNCERTAIN" and human else "ADJUDICATED",
    }


def main() -> int:
    records = load_pass1()
    if len(records) != 60:
        raise SystemExit(f"expected 60 records, got {len(records)}")
    cohort = {c["case_id"]: c for c in load_cohort_metadata()}

    review_rows = []
    human_rows = []
    locked = []
    for rec in records:
        cid = rec["case_id"]
        if cid not in cohort:
            raise SystemExit(f"case not in frozen cohort {cid}")
        reasons = needs_review(rec)
        res = resolve_pass2(rec, reasons)
        rec2 = dict(rec)
        rec2.update(
            {
                "pass1_truth": rec.get("pass1_truth") or rec.get("truth_value"),
                "pass2_truth": res["pass2_truth"],
                "agreement": res["agreement"],
                "review_reason": res["review_reason"],
                "final_truth": res["final_truth"],
                "truth_value": res["final_truth"],
                "resolution_note": res["resolution_note"],
                "truth_status": res["truth_status"],
                "human_review_required": res["human_review_required"],
                "second_pass_is_not_a_second_human_curator": True,
                "reviewed_utc": utc_now(),
            }
        )
        locked.append(rec2)
        review_rows.append(
            {
                "case_id": cid,
                "position": rec["position"],
                "accession": rec["accession"],
                "target": rec["target"],
                "stratum": rec["stratum"],
                "pass1_truth": rec2["pass1_truth"],
                "pass2_truth": rec2["pass2_truth"],
                "agreement": rec2["agreement"],
                "review_reason": ";".join(reasons),
                "final_truth": rec2["final_truth"],
                "resolution_note": rec2["resolution_note"],
                "human_review_required": rec2["human_review_required"],
            }
        )
        if rec2["human_review_required"] or rec2["final_truth"] == "TRUTH_UNCERTAIN" or rec.get("evidence_route_concordance") == "DISCORDANT":
            human_rows.append(
                {
                    "case_id": cid,
                    "position": rec["position"],
                    "accession": rec["accession"],
                    "target": rec["target"],
                    "reason_for_review": ";".join(reasons) or rec.get("evidence_route_concordance"),
                    "independent_evidence_summary": rec.get("adjudication_rationale"),
                    "reference_accessions": ";".join(rec.get("primary_reference_accessions") or []),
                    "evidence_artifact_paths": f"manuscript_benchmark/TRUTH_M60/EVIDENCE/position_{rec['position']:02d}_{rec['accession']}_{rec['target']}",
                    "marked_for_human_adjudication": True,
                    "automated_review_is_not_a_second_human_curator": True,
                }
            )

    # Blinded counts — truth only
    def count(rows, pred):
        return sum(1 for r in rows if pred(r))

    summary = {
        "kind": "M60_BLINDED_TRUTH_SET_SUMMARY",
        "total": 60,
        "tetA": 30,
        "rpoB": 30,
        "routine": 30,
        "challenge": 30,
        "POSITIVE": count(locked, lambda r: r["final_truth"] == "POSITIVE"),
        "NEGATIVE": count(locked, lambda r: r["final_truth"] == "NEGATIVE"),
        "TRUTH_UNCERTAIN": count(locked, lambda r: r["final_truth"] == "TRUTH_UNCERTAIN"),
        "tetA_POSITIVE": count(locked, lambda r: r["target"].startswith("tetA") and r["final_truth"] == "POSITIVE"),
        "tetA_NEGATIVE": count(locked, lambda r: r["target"].startswith("tetA") and r["final_truth"] == "NEGATIVE"),
        "tetA_TRUTH_UNCERTAIN": count(locked, lambda r: r["target"].startswith("tetA") and r["final_truth"] == "TRUTH_UNCERTAIN"),
        "rpoB_POSITIVE": count(locked, lambda r: r["target"].startswith("rpoB") and r["final_truth"] == "POSITIVE"),
        "rpoB_NEGATIVE": count(locked, lambda r: r["target"].startswith("rpoB") and r["final_truth"] == "NEGATIVE"),
        "rpoB_TRUTH_UNCERTAIN": count(locked, lambda r: r["target"].startswith("rpoB") and r["final_truth"] == "TRUTH_UNCERTAIN"),
        "routine_POSITIVE": count(locked, lambda r: r["stratum"] == "routine" and r["final_truth"] == "POSITIVE"),
        "routine_NEGATIVE": count(locked, lambda r: r["stratum"] == "routine" and r["final_truth"] == "NEGATIVE"),
        "routine_TRUTH_UNCERTAIN": count(locked, lambda r: r["stratum"] == "routine" and r["final_truth"] == "TRUTH_UNCERTAIN"),
        "challenge_POSITIVE": count(locked, lambda r: r["stratum"] == "challenge" and r["final_truth"] == "POSITIVE"),
        "challenge_NEGATIVE": count(locked, lambda r: r["stratum"] == "challenge" and r["final_truth"] == "NEGATIVE"),
        "challenge_TRUTH_UNCERTAIN": count(locked, lambda r: r["stratum"] == "challenge" and r["final_truth"] == "TRUTH_UNCERTAIN"),
        "evidence_routes_concordant": count(locked, lambda r: r.get("evidence_route_concordance") == "CONCORDANT"),
        "second_pass_reviewed": count(review_rows, lambda r: bool(r["review_reason"])),
        "human_review_required": len(human_rows),
        "accuracy_scored": False,
        "prediction_payloads_opened": False,
    }

    methods = """# M60 independent truth methods

This document describes how M60 ground truth was constructed.

It does **not** report system accuracy.

## Independence

Truth was assigned after all M60 predictions were locked.

Prediction payloads were not opened.

AMRFinderPlus was not used as tetA truth.

NCBI RefSeq/PGAP annotation was not used as rpoB truth.

Genome Skeptic Deterministic, Agentic, Exhaustive, and Conventional outputs were not used as truth.

D20 was not accessed.

D8/D12 outcome labels were not used.

M60 assemblies were used only as query genomes. They were not added to the reference panel.

## Two independent evidence routes

This is **not** two independent human reviewers. One automated adjudication
pipeline applied two distinct evidence routes, then a separate automated
second pass over the same evidence records.

### tetA

Endpoint: presence of a genuine tet(A)/tet(B) family member.

Route 1: sequence comparison of recovered candidate ORFs against a frozen
tet(A)/tet(B) panel (UniProt P02982 / P02980 and packaged family members)
versus competing MFS/RND/non-target tet-class references.

Route 2: HMMER profile placement on frozen tetA versus competitor family
HMMs, with FastTree placement for borderline cases when hmmalign succeeded.

A generic MFS transporter match is not sufficient.

### rpoB

Endpoint: presence of a genuine bacterial rpoB orthologue.

Route 1: full/near-full-length similarity and length-ratio support versus
independently verified RpoB references.

Route 2: RpoB versus RpoC profile placement, with phylogenetic placement
when borderline.

PGAP gene-name equality was not used.

Negative rpoB labels were not manufactured for class balance.

Uncertainty was not forced into NEGATIVE.

## Decision gates

Frozen protocol gates from M60_PROTOCOL_V1_1.md:

- identity 0.60, coverage 0.80, length ratio 0.80–1.20
- competitive margin 0.10 / ambiguous band 0.05
- HMM gate coverage 0.20 / domain-only max 0.45
- sequence-decisive identity×coverage ≥ 0.70 with competitor delta ≥ 0.20

## Human review

Cases remaining TRUTH_UNCERTAIN, discordant, or otherwise unresolved are
listed in `M60_HUMAN_REVIEW_REQUIRED.csv` and are marked for human
adjudication. Automated review is not a second human curator.
"""

    FINAL.mkdir(parents=True, exist_ok=True)
    REVIEW.mkdir(parents=True, exist_ok=True)

    truth_json = {
        "kind": "M60_EXTERNAL_TRUTH_LOCKED",
        "freeze_id": "GENOME_SKEPTIC_V4_1_MANUSCRIPT",
        "n_cases": 60,
        "created_utc": utc_now(),
        "do_not_regenerate": True,
        "prediction_payloads_opened": False,
        "amrfinder_used_as_truth": False,
        "pgap_used_as_truth": False,
        "gs_predictions_used_as_truth": False,
        "d20_touched": False,
        "accuracy_scored": False,
        "two_independent_evidence_routes": True,
        "two_independent_reviewers": False,
        "cases": [
            {
                "case_id": r["case_id"],
                "position": r["position"],
                "accession": r["accession"],
                "target": r["target"],
                "stratum": r["stratum"],
                "truth_value": r["final_truth"],
                "truth_status": r["truth_status"],
                "evidence_route_1": r.get("evidence_route_1"),
                "evidence_route_2": r.get("evidence_route_2"),
                "evidence_route_concordance": r.get("evidence_route_concordance"),
                "candidate_sequence_ids": r.get("candidate_sequence_ids"),
                "candidate_coordinates": r.get("candidate_coordinates"),
                "primary_reference_accessions": r.get("primary_reference_accessions"),
                "competitor_reference_accessions": r.get("competitor_reference_accessions"),
                "sequence_coverage": r.get("sequence_coverage"),
                "sequence_similarity": r.get("sequence_similarity"),
                "family_or_profile_result": r.get("family_or_profile_result"),
                "orthology_or_phylogeny_result": r.get("orthology_or_phylogeny_result"),
                "primary_evidence_summary": r.get("primary_evidence_summary"),
                "secondary_evidence_summary": r.get("secondary_evidence_summary"),
                "truth_resource_manifest_sha256": r.get("truth_resource_manifest_sha256"),
                "software_versions": r.get("software_versions"),
                "evidence_artifact_hashes": r.get("evidence_artifact_hashes"),
                "adjudication_rationale": r.get("adjudication_rationale"),
                "pass1_truth": r.get("pass1_truth"),
                "pass2_truth": r.get("pass2_truth"),
                "agreement": r.get("agreement"),
                "review_reason": r.get("review_reason"),
                "final_truth": r.get("final_truth"),
                "resolution_note": r.get("resolution_note"),
                "human_review_required": r.get("human_review_required"),
            }
            for r in locked
        ],
        "blinded_summary": summary,
    }

    tpath = FINAL / "M60_EXTERNAL_TRUTH_LOCKED.json"
    write_json(tpath, truth_json)

    csv_path = FINAL / "M60_TRUTH_CASE_LEVEL.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "case_id", "position", "accession", "target", "stratum",
                "truth_value", "truth_status", "evidence_route_concordance",
                "sequence_similarity", "sequence_coverage",
                "primary_reference_accessions", "human_review_required",
            ],
        )
        w.writeheader()
        for r in locked:
            w.writerow(
                {
                    "case_id": r["case_id"],
                    "position": r["position"],
                    "accession": r["accession"],
                    "target": r["target"],
                    "stratum": r["stratum"],
                    "truth_value": r["final_truth"],
                    "truth_status": r["truth_status"],
                    "evidence_route_concordance": r.get("evidence_route_concordance"),
                    "sequence_similarity": r.get("sequence_similarity"),
                    "sequence_coverage": r.get("sequence_coverage"),
                    "primary_reference_accessions": ";".join(r.get("primary_reference_accessions") or []),
                    "human_review_required": r.get("human_review_required"),
                }
            )

    ev_manifest = {
        "kind": "M60_TRUTH_EVIDENCE_MANIFEST",
        "created_utc": utc_now(),
        "n_cases": 60,
        "source_manifest": "manuscript_benchmark/TRUTH_M60/M60_TRUTH_SOURCE_MANIFEST.json",
        "source_manifest_sha256": sha256_file(TRUTH_ROOT / "M60_TRUTH_SOURCE_MANIFEST.json"),
        "case_record_sha256": {
            f"position_{r['position']:02d}.json": sha256_file(CASE_RECORDS / f"position_{r['position']:02d}.json")
            for r in locked
        },
        "prediction_payloads_opened": False,
        "d20_touched": False,
    }
    epath = FINAL / "M60_TRUTH_EVIDENCE_MANIFEST.json"
    write_json(epath, ev_manifest)

    rev_csv = FINAL / "M60_TRUTH_REVIEW.csv"
    with rev_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(review_rows[0].keys()))
        w.writeheader()
        w.writerows(review_rows)

    human_csv = FINAL / "M60_HUMAN_REVIEW_REQUIRED.csv"
    fields = [
        "case_id", "position", "accession", "target", "reason_for_review",
        "independent_evidence_summary", "reference_accessions",
        "evidence_artifact_paths", "marked_for_human_adjudication",
        "automated_review_is_not_a_second_human_curator",
    ]
    with human_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(human_rows)

    mpath = FINAL / "M60_TRUTH_METHODS.md"
    mpath.write_text(methods, encoding="utf-8")

    hashes = {
        "M60_EXTERNAL_TRUTH_LOCKED.json": write_sha256_sidecar(tpath),
        "M60_TRUTH_CASE_LEVEL.csv": write_sha256_sidecar(csv_path),
        "M60_TRUTH_EVIDENCE_MANIFEST.json": write_sha256_sidecar(epath),
        "M60_TRUTH_REVIEW.csv": write_sha256_sidecar(rev_csv),
        "M60_TRUTH_METHODS.md": write_sha256_sidecar(mpath),
        "M60_HUMAN_REVIEW_REQUIRED.csv": write_sha256_sidecar(human_csv),
    }

    lock_manifest = {
        "kind": "M60_TRUTH_LOCK_MANIFEST",
        "immutable": True,
        "n_cases": 60,
        "created_utc": utc_now(),
        "file_sha256": hashes,
        "blinded_summary": summary,
        "prediction_payloads_opened": False,
        "amrfinder_used_as_truth": False,
        "pgap_used_as_truth": False,
        "gs_predictions_used_as_truth": False,
        "d20_touched": False,
        "accuracy_scored": False,
        "m60_cases_replaced": False,
        "scientific_code_changed": False,
        "prediction_reruns": False,
    }
    lpath = FINAL / "M60_TRUTH_LOCK_MANIFEST.json"
    write_json(lpath, lock_manifest)
    lock_sha = write_sha256_sidecar(lpath)

    # publish copies at TRUTH_M60 root for the required filenames
    for name in (
        "M60_EXTERNAL_TRUTH_LOCKED.json",
        "M60_TRUTH_CASE_LEVEL.csv",
        "M60_TRUTH_EVIDENCE_MANIFEST.json",
        "M60_TRUTH_REVIEW.csv",
        "M60_TRUTH_METHODS.md",
        "M60_HUMAN_REVIEW_REQUIRED.csv",
        "M60_TRUTH_LOCK_MANIFEST.json",
    ):
        src = FINAL / name
        dest = TRUTH_ROOT / name
        dest.write_bytes(src.read_bytes())
        write_sha256_sidecar(dest)

    write_json(TRUTH_ROOT / "BLINDED_TRUTH_SET_SUMMARY.json", summary)
    write_sha256_sidecar(TRUTH_ROOT / "BLINDED_TRUTH_SET_SUMMARY.json")

    print(json.dumps({"lock_sha256": lock_sha, "summary": summary, "file_sha256": hashes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
