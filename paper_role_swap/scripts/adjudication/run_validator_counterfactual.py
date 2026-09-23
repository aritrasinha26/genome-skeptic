#!/usr/bin/env python3
"""Replay locked M60 family_evidence through two patched validator behaviours.

POST_HOC_DIAGNOSTIC = TRUE ; NOT PROSPECTIVE PERFORMANCE

Reads FROZEN TargetMeasurements from RUNS/*/family_evidence.json.
Does not re-run search, HMM, or LLM. Does not write POSITION_LOCKS.
Stop after one patch iteration; do not retune (a) or (b) against recovery.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.config import Settings  # noqa: E402
from genome_skeptic.families import load_family  # noqa: E402
from genome_skeptic.models import (  # noqa: E402
    GeneSearchHit,
    LocusReconstruction,
    TargetFamily,
    TargetType,
)
from genome_skeptic.validators._counterfactual_r1 import (  # noqa: E402
    PATCH_ITERATION,
    POST_HOC_DIAGNOSTIC,
    best_hmm_overrides_reconstruction_coverage,
    classify_architecture as patched_classify_architecture,
    family_identity_is_decisive as patched_family_identity_is_decisive,
)
from genome_skeptic.validators.falsification import classify_polarity  # noqa: E402
from genome_skeptic.validators.family_orthology import (  # noqa: E402
    FamilyEvidence,
    classify_family_orthology,
)
from genome_skeptic.models import ClaimType  # noqa: E402

MB = ROOT / "manuscript_benchmark"
TRUTH_ROOT = MB / "TRUTH_M60"
RUNS = MB / "RUNS"
LOCK_ROOT = MB / "POSITION_LOCKS"
OUT = MB / "ABLATION_VALIDATOR_R1"

DIAGNOSTIC_HEADER = "POST_HOC_DIAGNOSTIC = TRUE ; NOT PROSPECTIVE PERFORMANCE"
REFINE_WEAK_NOTE = (
    "target family support is not sequence-decisive; competing-family comparison did not settle identity"
)
SHARED_ERROR_POSITIONS = (13, 14, 19, 36, 37, 41, 44, 48)
ARMS = (
    ("gs_det", "GS_DETERMINISTIC_V4_1", "GS-Deterministic V4.1"),
    ("gs_agent", "GS_AGENTIC_V4_1", "GS-Agentic V4.1"),
    ("gs_exh", "GS_EXHAUSTIVE_V4_1", "GS-Exhaustive V4.1"),
)
PRIMARY_ARM = "gs_det"
TARGETS = ("tetA_tetracycline_efflux", "rpoB_RNAP_beta")
NA_SPEC = "n/a (no negatives)"
CONSTANT_PER_TARGET_K = 34
N_EVALUABLE = 41
N_CORRECT_FROZEN = 33
N_SHARED_ERRORS = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def polarity_to_binary(polarity: ClaimType) -> str:
    if polarity == ClaimType.target_gene_detected:
        return "POSITIVE"
    if polarity == ClaimType.target_gene_not_detected:
        return "NEGATIVE"
    return "UNRESOLVED"


def gs_binary(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("completion_status") not in {None, "complete"}:
        if rec.get("completion_status") == "complete":
            pass
        elif rec.get("ok") is False or rec.get("completion_status") in {"failed", "error"}:
            return "UNRESOLVED"
    fr = rec.get("final_result") or rec.get("binary_call")
    if fr == "target_gene_detected" or fr == "POSITIVE":
        return "POSITIVE"
    if fr == "target_gene_not_detected" or fr == "NEGATIVE":
        return "NEGATIVE"
    return "UNRESOLVED"


def is_correct(truth: str, pred: str) -> bool | None:
    if truth == "TRUTH_UNCERTAIN":
        return None
    if truth in {"POSITIVE", "NEGATIVE"}:
        return pred == truth
    return None


def index_preds(payload: dict) -> dict:
    out = {}
    for rec in payload["predictions"]:
        out[rec["case_id"]] = rec
    if len(out) != 60:
        raise SystemExit(f"{payload.get('kind')} n={len(out)}")
    return out


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / den
    margin = (z / den) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def fmt_ci(ci: tuple[float, float]) -> str:
    if any(math.isnan(x) for x in ci):
        return "NA"
    return f"{ci[0]:.3f}–{ci[1]:.3f}"


def rate_block(k: int, n: int) -> tuple[object, object, object, str]:
    if n <= 0:
        return NA_SPEC, NA_SPEC, NA_SPEC, NA_SPEC
    acc = k / n
    ci = wilson_ci(k, n)
    return acc, ci[0], ci[1], fmt_ci(ci)


def constant_pred(row: dict, mode: str) -> str:
    if mode == "CONSTANT_PER_TARGET":
        return "NEGATIVE" if row["target"].startswith("tetA") else "POSITIVE"
    if mode == "CONSTANT_ALL_NEGATIVE":
        return "NEGATIVE"
    if mode == "CONSTANT_ALL_POSITIVE":
        return "POSITIVE"
    raise SystemExit(f"unknown constant mode {mode}")


def confusion(rows: list[dict], pred_key: str) -> dict:
    tp = tn = fp = fn = 0
    for r in rows:
        truth = r["truth"]
        pred = r[pred_key]
        if truth == "POSITIVE" and pred == "POSITIVE":
            tp += 1
        elif truth == "NEGATIVE" and pred == "NEGATIVE":
            tn += 1
        elif truth == "NEGATIVE" and pred != "NEGATIVE":
            fp += 1
        elif truth == "POSITIVE" and pred != "POSITIVE":
            fn += 1
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "n_pos": tp + fn, "n_neg": tn + fp}


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.startswith(DIAGNOSTIC_HEADER):
        text = DIAGNOSTIC_HEADER + "\n\n" + text
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(obj) if isinstance(obj, dict) else obj
    if isinstance(payload, dict):
        payload = {"POST_HOC_DIAGNOSTIC": DIAGNOSTIC_HEADER.split(" = ", 1)[-1], **payload}
    text = json.dumps(payload, indent=2, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if "POST_HOC_DIAGNOSTIC" not in fields:
        fields = ["POST_HOC_DIAGNOSTIC", *fields]
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"# {DIAGNOSTIC_HEADER}\n")
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            out = {k: row.get(k, "") for k in fields}
            out["POST_HOC_DIAGNOSTIC"] = DIAGNOSTIC_HEADER.split(" = ", 1)[-1]
            w.writerow(out)
    return sha256_file(path)


def md_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        f"*{DIAGNOSTIC_HEADER}*",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def hit_from_summary(s: dict) -> GeneSearchHit:
    tstart = int(s.get("tstart") or 0)
    tend = int(s.get("tend") or 0)
    ident = float(s.get("identity") or 0.0)
    qcov = float(s.get("query_coverage") or 0.0)
    aln = max(1, abs(tend - tstart))
    qlen = max(1, int(round(aln / max(qcov, 1e-9))))
    kind = s.get("search_kind") or "translated"
    if kind not in {"nucleotide", "translated", "protein", "domain"}:
        kind = "translated"
    strand = s.get("strand") or "+"
    if strand not in {"+", "-"}:
        strand = "+"
    return GeneSearchHit(
        query_id=str(s.get("query_id") or "member"),
        contig_id=str(s.get("contig_id") or ""),
        search_kind=kind,
        qstart=0,
        qend=max(1, int(round(qlen * qcov))),
        tstart=tstart,
        tend=tend,
        strand=strand,
        identity=ident,
        query_coverage=qcov,
        alignment_length=aln,
        query_length=qlen,
        contig_length=max(tend, tstart, 1),
        near_contig_edge=bool(s.get("near_contig_edge")),
        evalue=s.get("evalue"),
    )


def family_evidence_from_json(blob: dict) -> FamilyEvidence:
    recon = dict(blob.get("reconstruction") or {})
    hits = [hit_from_summary(s) for s in (blob.get("member_hit_summaries") or [])]
    return FamilyEvidence(
        family_id=blob.get("family_id"),
        member_hits=hits,
        architecture=blob.get("architecture") or "absent",
        hierarchy=list(blob.get("hierarchy") or []),
        supports_orthologue=bool(blob.get("supports_orthologue")),
        domain_only=bool(blob.get("domain_only")),
        fusion=dict(blob.get("fusion") or {}),
        split=dict(blob.get("split") or {}),
        fragmented=dict(blob.get("fragmented") or {}),
        paralogue=dict(blob.get("paralogue") or {}),
        reconstruction=recon,
        best_hmm=blob.get("best_hmm"),
        metrics=dict(blob.get("metrics") or {}),
        limitations=list(blob.get("limitations") or []),
        tools_run=list(blob.get("tools_run") or []),
        provenance=dict(blob.get("provenance") or {}),
    )


def frozen_identity(ev: FamilyEvidence, competitive: dict) -> float:
    recon = ev.reconstruction or {}
    metrics = ev.metrics or {}
    for value in (
        competitive.get("target_family_sequence_identity"),
        competitive.get("sequence_identity"),
        recon.get("sequence_identity"),
        recon.get("query_identity"),
        metrics.get("best_member_identity"),
    ):
        if value is not None:
            return float(value)
    return 0.0


def dummy_family(family_id: str | None) -> TargetFamily:
    return TargetFamily(
        family_id=family_id or "unknown",
        display_name=family_id or "unknown",
        members=[],
    )


def apply_reconstruction_override(ev: FamilyEvidence) -> None:
    if not ev.reconstruction:
        return
    rarch = ev.reconstruction.get("architecture")
    if rarch == "domain_only":
        ev.domain_only = True
        ev.supports_orthologue = False
    elif rarch in {
        "canonical_full_length",
        "divergent_full_length",
        "fusion",
        "biological_split",
        "close_paralogue",
    }:
        ev.domain_only = False
    elif rarch == "true_no_candidate":
        ev.domain_only = False
        ev.supports_orthologue = False


def endpoint_from_evidence(ev: FamilyEvidence, target: str, settings: Settings) -> str:
    polarity = classify_polarity(
        list(ev.member_hits or []),
        settings,
        TargetType.gene_orthologue,
        family_evidence=ev,
    )
    return polarity_to_binary(polarity)


def find_family_evidence(position: int, accession: str, target: str, arm_dir: str) -> Path:
    return (
        RUNS
        / f"position_{position:02d}"
        / accession
        / target
        / arm_dir
        / "family"
        / target
        / "family_evidence.json"
    )


def undo_refine_weak(competitive: dict) -> bool:
    cls = competitive.get("classification")
    conflicts = [str(x) for x in (competitive.get("conflicting_evidence") or [])]
    if cls != "ambiguous_family":
        return False
    if not any(REFINE_WEAK_NOTE in item for item in conflicts):
        return False
    competitive["classification"] = "target_family_supported"
    competitive["conflicting_evidence"] = [item for item in conflicts if REFINE_WEAK_NOTE not in item]
    return True


def apply_refine_weak_if_not_decisive(competitive: dict) -> bool:
    if competitive.get("classification") != "target_family_supported":
        return False
    if patched_family_identity_is_decisive(competitive):
        return False
    competitive["classification"] = "ambiguous_family"
    conflicts = list(competitive.get("conflicting_evidence") or [])
    conflicts.append(REFINE_WEAK_NOTE)
    competitive["conflicting_evidence"] = conflicts
    return True


def apply_architecture_patch(
    ev: FamilyEvidence,
    family: TargetFamily,
    settings: Settings,
) -> tuple[bool, str | None, str | None]:
    recon_raw = dict(ev.reconstruction or {})
    if not recon_raw:
        return False, None, ev.architecture
    rec = LocusReconstruction.model_validate(recon_raw)
    frozen_arch = rec.architecture
    if not best_hmm_overrides_reconstruction_coverage(rec, ev.best_hmm):
        return False, frozen_arch, frozen_arch
    patched = patched_classify_architecture(
        reconstruction=rec,
        family=family,
        member_hits=list(ev.member_hits or []),
        partner_hits=[],
        partner_hmm={},
        settings=settings,
        best_hmm=ev.best_hmm,
    )
    ev.architecture = patched.architecture
    dumped = patched.model_dump()
    recon_raw["architecture"] = patched.architecture
    recon_raw["hmm_coverage"] = dumped.get("hmm_coverage")
    recon_raw["family_gate_passed"] = dumped.get("family_gate_passed")
    ev.reconstruction = recon_raw
    ev.domain_only = patched.architecture == "domain_only"
    ev.fusion = {
        "state": patched.architecture if patched.architecture == "fusion" else "not_fusion",
        "supported": patched.architecture == "fusion",
        "hmm_coverage": dumped.get("hmm_coverage"),
        "contig": dumped.get("contig"),
        "genomic_start": dumped.get("genomic_start"),
        "genomic_end": dumped.get("genomic_end"),
    }
    ev.split = {
        "state": patched.architecture if patched.architecture == "biological_split" else "not_split",
        "supported": patched.architecture == "biological_split",
        "gaps": dumped.get("inter_segment_gaps"),
    }
    ev.fragmented = {
        "state": patched.architecture if patched.architecture == "assembly_fragmented" else "not_fragmented",
        "supported": patched.architecture == "assembly_fragmented",
        "contig_edge": dumped.get("contig_edge"),
        "combined_query_span": dumped.get("hmm_coverage"),
        "not_biological_split": patched.architecture == "assembly_fragmented",
    }
    return True, frozen_arch, patched.architecture


def replay_patched(
    blob: dict,
    target: str,
    settings: Settings,
    family_cache: dict[str, TargetFamily | None],
) -> dict:
    ev = family_evidence_from_json(deepcopy(blob))
    recon = dict(ev.reconstruction or {})
    competitive = dict(recon.get("competitive_family") or blob.get("competitive_family") or {})
    identity = frozen_identity(ev, competitive)
    coverage = float(competitive.get("target_family_sequence_coverage") or 0.0)
    competitive["target_family_sequence_identity"] = identity
    frozen_cls = competitive.get("classification")
    undid = undo_refine_weak(competitive)
    a_relabelled = apply_refine_weak_if_not_decisive(competitive) if undid else False
    a_recovered_cls = bool(undid and competitive.get("classification") == "target_family_supported")
    recon["competitive_family"] = competitive
    ev.reconstruction = recon

    family_id = ev.family_id or target
    if family_id not in family_cache:
        family_cache[family_id] = load_family(family_id) or dummy_family(family_id)
    family = family_cache[family_id] or dummy_family(family_id)
    b_applied, frozen_arch, patched_arch = apply_architecture_patch(ev, family, settings)

    classify_family_orthology(
        ev,
        family,
        settings,
        query_hits=list(ev.member_hits or []),
        locus_evidence=None,
    )
    apply_reconstruction_override(ev)

    pred = endpoint_from_evidence(ev, target, settings)
    return {
        "patched_pred": pred,
        "patched_classification": (ev.reconstruction or {}).get("competitive_family", {}).get("classification"),
        "patched_architecture": ev.architecture,
        "patched_domain_only": ev.domain_only,
        "patched_supports_orthologue": ev.supports_orthologue,
        "frozen_classification": frozen_cls,
        "identity": identity,
        "coverage": coverage,
        "identity_coverage_product": identity * coverage,
        "patch_a_undid_refine_weak": undid,
        "patch_a_still_relabelled": a_relabelled,
        "patch_a_kept_target_family_supported": a_recovered_cls,
        "patch_b_applied": b_applied,
        "frozen_architecture": frozen_arch if frozen_arch is not None else blob.get("architecture"),
        "patched_architecture_from_b": patched_arch,
        "decisive_under_patch": patched_family_identity_is_decisive(competitive),
    }


def class_row(target: str, system: str, system_id: str, subset: list[dict], pred_key: str, corr_key: str) -> dict:
    n = len(subset)
    k = sum(1 for r in subset if r[corr_key] is True)
    acc, acc_lo, acc_hi, acc_ci = rate_block(k, n)
    cm = confusion(subset, pred_key)
    n_pos, n_neg = cm["n_pos"], cm["n_neg"]
    sens, sens_lo, sens_hi, sens_ci = rate_block(cm["tp"], n_pos)
    if n_neg <= 0:
        spec = spec_lo = spec_hi = spec_ci = NA_SPEC
    else:
        spec, spec_lo, spec_hi, spec_ci = rate_block(cm["tn"], n_neg)
    return {
        "target": target,
        "system": system,
        "system_id": system_id,
        "n": n,
        "correct": k,
        "accuracy": acc,
        "accuracy_wilson_low": acc_lo,
        "accuracy_wilson_high": acc_hi,
        "accuracy_wilson": acc_ci,
        "n_pos": n_pos,
        "sensitivity": sens,
        "sensitivity_wilson_low": sens_lo,
        "sensitivity_wilson_high": sens_hi,
        "sensitivity_wilson": sens_ci,
        "n_neg": n_neg,
        "specificity": spec,
        "specificity_wilson_low": spec_lo,
        "specificity_wilson_high": spec_hi,
        "specificity_wilson": spec_ci,
        "correct_over_n": f"{k}/{n}",
    }


def score_constant(eval_rows: list[dict], mode: str) -> dict:
    k = 0
    for r in eval_rows:
        pred = constant_pred(r, mode)
        if is_correct(r["truth"], pred) is True:
            k += 1
    n = len(eval_rows)
    acc, lo, hi, ci = rate_block(k, n)
    return {
        "kind": "baseline",
        "baseline": mode,
        "system_id": "",
        "n": n,
        "correct": k,
        "accuracy": acc,
        "accuracy_wilson_low": lo,
        "accuracy_wilson_high": hi,
        "accuracy_wilson": ci,
        "correct_over_n": f"{k}/{n}",
        "b": "",
        "c": "",
        "net": "",
        "mcnemar_note": "",
    }


def mcnemar(gs_ok: list[bool], base_ok: list[bool]) -> dict:
    from scipy.stats import binomtest

    b = sum(1 for g, c in zip(gs_ok, base_ok) if c and not g)
    c = sum(1 for g, c in zip(gs_ok, base_ok) if (not c) and g)
    net = c - b
    if b + c == 0:
        return {
            "b": b,
            "c": c,
            "net": net,
            "mcnemar_note": "McNemar not applicable (B+C = 0)",
        }
    p = float(binomtest(c, n=b + c, p=0.5, alternative="two-sided").pvalue)
    return {
        "b": b,
        "c": c,
        "net": net,
        "mcnemar_note": f"exact two-sided McNemar / binomial P={p:.6g} on B+C={b + c}",
    }


def assert_no_lock_writes(before: dict[str, float]) -> None:
    after = {}
    for path in LOCK_ROOT.glob("position_*/POSITION_LOCK.json"):
        after[str(path)] = path.stat().st_mtime
    if after != before:
        raise SystemExit("POSITION_LOCKS were modified; aborting diagnostic")


def main() -> int:
    if PATCH_ITERATION != 1:
        raise SystemExit("this diagnostic is a single patch iteration")
    print(DIAGNOSTIC_HEADER, flush=True)
    print("NOT PROSPECTIVE PERFORMANCE", flush=True)

    lock_mtime = {str(p): p.stat().st_mtime for p in LOCK_ROOT.glob("position_*/POSITION_LOCK.json")}
    settings = Settings()
    truth_obj = load_json(TRUTH_ROOT / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json")
    truth_cases = {c["case_id"]: c for c in truth_obj["cases"]}
    if len(truth_cases) != 60:
        raise SystemExit("truth n != 60")

    locked = {
        "gs_det": index_preds(load_json(MB / "M60_GS_DETERMINISTIC_LOCKED.json")),
        "gs_agent": index_preds(load_json(MB / "M60_GS_AGENTIC_LOCKED.json")),
        "gs_exh": index_preds(load_json(MB / "M60_GS_EXHAUSTIVE_LOCKED.json")),
    }

    family_cache: dict[str, TargetFamily | None] = {}
    rows = []
    missing = []
    for cid, tcase in sorted(truth_cases.items(), key=lambda kv: int(kv[1]["position"])):
        position = int(tcase["position"])
        accession = tcase["accession"]
        target = tcase["target"]
        truth = tcase["truth_value"]
        row = {
            "case_id": cid,
            "position": position,
            "accession": accession,
            "target": target,
            "stratum": tcase.get("stratum"),
            "truth": truth,
            "evaluable": truth in {"POSITIVE", "NEGATIVE"},
            "shared_error": position in SHARED_ERROR_POSITIONS,
        }
        for arm_id, arm_dir, _label in ARMS:
            frozen_pred = gs_binary(locked[arm_id][cid])
            path = find_family_evidence(position, accession, target, arm_dir)
            if not path.is_file():
                missing.append(str(path))
                row[f"{arm_id}_family_evidence"] = ""
                row[f"{arm_id}_frozen_pred"] = frozen_pred
                row[f"{arm_id}_frozen_replay_pred"] = "MISSING"
                row[f"{arm_id}_patched_pred"] = "MISSING"
                continue
            blob = load_json(path)
            frozen_ev = family_evidence_from_json(blob)
            frozen_replay = endpoint_from_evidence(frozen_ev, target, settings)
            patched = replay_patched(blob, target, settings, family_cache)
            recon = blob.get("reconstruction") or {}
            cf = recon.get("competitive_family") or blob.get("competitive_family") or {}
            row[f"{arm_id}_family_evidence"] = str(path.relative_to(ROOT)).replace("\\", "/")
            row[f"{arm_id}_frozen_pred"] = frozen_pred
            row[f"{arm_id}_frozen_replay_pred"] = frozen_replay
            row[f"{arm_id}_patched_pred"] = patched["patched_pred"]
            row[f"{arm_id}_frozen_correct"] = is_correct(truth, frozen_pred)
            row[f"{arm_id}_patched_correct"] = is_correct(truth, patched["patched_pred"])
            row[f"{arm_id}_endpoint_changed"] = frozen_pred != patched["patched_pred"]
            row[f"{arm_id}_frozen_replay_matches_lock"] = frozen_replay == frozen_pred
            if arm_id == PRIMARY_ARM:
                row.update(
                    {
                        "frozen_architecture": blob.get("architecture"),
                        "patched_architecture": patched["patched_architecture"],
                        "frozen_classification": cf.get("classification"),
                        "patched_classification": patched["patched_classification"],
                        "frozen_domain_only": blob.get("domain_only"),
                        "patched_domain_only": patched["patched_domain_only"],
                        "frozen_supports_orthologue": blob.get("supports_orthologue"),
                        "patched_supports_orthologue": patched["patched_supports_orthologue"],
                        "identity": patched["identity"],
                        "target_family_sequence_coverage": patched["coverage"],
                        "identity_coverage_product": patched["identity_coverage_product"],
                        "reconstruction_hmm_coverage": recon.get("hmm_coverage"),
                        "best_hmm_model_coverage": (blob.get("best_hmm") or {}).get("model_coverage"),
                        "patch_a_undid_refine_weak": patched["patch_a_undid_refine_weak"],
                        "patch_a_still_relabelled": patched["patch_a_still_relabelled"],
                        "patch_a_kept_target_family_supported": patched["patch_a_kept_target_family_supported"],
                        "patch_b_applied": patched["patch_b_applied"],
                        "decisive_under_patch": patched["decisive_under_patch"],
                    }
                )
        rows.append(row)

    if missing:
        raise SystemExit(f"missing family_evidence.json n={len(missing)} first={missing[0]}")
    if len(rows) != 60:
        raise SystemExit(f"joined n={len(rows)}")

    eval_rows = [r for r in rows if r["evaluable"]]
    if len(eval_rows) != N_EVALUABLE:
        raise SystemExit(f"evaluable {len(eval_rows)} != {N_EVALUABLE}")

    mismatch = [
        r for r in rows if r.get(f"{PRIMARY_ARM}_frozen_replay_matches_lock") is False
    ]
    if mismatch:
        ids = ",".join(str(r["position"]) for r in mismatch)
        raise SystemExit(
            f"frozen replay of classify_polarity on locked family_evidence "
            f"does not match locked {PRIMARY_ARM} endpoints at positions {ids}"
        )

    shared = [r for r in eval_rows if r["shared_error"]]
    if len(shared) != N_SHARED_ERRORS:
        raise SystemExit(f"shared errors {len(shared)} != {N_SHARED_ERRORS}")
    correct33 = [r for r in eval_rows if r.get(f"{PRIMARY_ARM}_frozen_correct") is True]
    if len(correct33) != N_CORRECT_FROZEN:
        raise SystemExit(f"frozen correct {len(correct33)} != {N_CORRECT_FROZEN}")

    recovered = [r for r in shared if r.get(f"{PRIMARY_ARM}_patched_correct") is True]
    unrecovered = [r for r in shared if r.get(f"{PRIMARY_ARM}_patched_correct") is not True]
    flipped = [r for r in correct33 if r.get(f"{PRIMARY_ARM}_patched_correct") is not True]

    for arm_id, _arm_dir, _label in ARMS:
        recov_arm = [r for r in shared if r.get(f"{arm_id}_patched_correct") is True]
        flip_arm = [
            r
            for r in eval_rows
            if r.get(f"{arm_id}_frozen_correct") is True and r.get(f"{arm_id}_patched_correct") is not True
        ]
        if [r["position"] for r in recov_arm] != [r["position"] for r in recovered]:
            raise SystemExit(f"{arm_id} recovery set diverged from {PRIMARY_ARM}")
        if [r["position"] for r in flip_arm] != [r["position"] for r in flipped]:
            raise SystemExit(f"{arm_id} flip set diverged from {PRIMARY_ARM}")

    OUT.mkdir(parents=True, exist_ok=True)
    if OUT.resolve() == LOCK_ROOT.resolve() or LOCK_ROOT in OUT.resolve().parents:
        raise SystemExit("refusing to write diagnostic outputs under POSITION_LOCKS")

    case_fields = [
        "case_id",
        "position",
        "accession",
        "target",
        "stratum",
        "truth",
        "evaluable",
        "shared_error",
        "gs_det_frozen_pred",
        "gs_det_patched_pred",
        "gs_det_frozen_correct",
        "gs_det_patched_correct",
        "gs_det_endpoint_changed",
        "gs_agent_frozen_pred",
        "gs_agent_patched_pred",
        "gs_agent_frozen_correct",
        "gs_agent_patched_correct",
        "gs_agent_endpoint_changed",
        "gs_exh_frozen_pred",
        "gs_exh_patched_pred",
        "gs_exh_frozen_correct",
        "gs_exh_patched_correct",
        "gs_exh_endpoint_changed",
        "frozen_architecture",
        "patched_architecture",
        "frozen_classification",
        "patched_classification",
        "frozen_domain_only",
        "patched_domain_only",
        "frozen_supports_orthologue",
        "patched_supports_orthologue",
        "identity",
        "target_family_sequence_coverage",
        "identity_coverage_product",
        "reconstruction_hmm_coverage",
        "best_hmm_model_coverage",
        "patch_a_undid_refine_weak",
        "patch_a_still_relabelled",
        "patch_a_kept_target_family_supported",
        "patch_b_applied",
        "decisive_under_patch",
        "gs_det_family_evidence",
    ]
    case_sha = write_csv(OUT / "ABLATION_VALIDATOR_R1_CASE_LEVEL.csv", rows, case_fields)

    recovery_rows = []
    for r in shared:
        defect = []
        if r.get("patch_a_kept_target_family_supported") and r.get(f"{PRIMARY_ARM}_patched_correct") is True:
            defect.append("a_family_identity_is_decisive")
        if r.get("patch_b_applied") and r.get(f"{PRIMARY_ARM}_patched_correct") is True:
            defect.append("b_classify_architecture")
        recovery_rows.append(
            {
                "set": "shared_error",
                "position": r["position"],
                "case_id": r["case_id"],
                "target": r["target"],
                "truth": r["truth"],
                "frozen_pred": r[f"{PRIMARY_ARM}_frozen_pred"],
                "patched_pred": r[f"{PRIMARY_ARM}_patched_pred"],
                "recovered": r.get(f"{PRIMARY_ARM}_patched_correct") is True,
                "defect_accounted": ";".join(defect) if defect else "",
                "identity_coverage_product": r.get("identity_coverage_product"),
                "patch_a_kept_target_family_supported": r.get("patch_a_kept_target_family_supported"),
                "patch_b_applied": r.get("patch_b_applied"),
            }
        )
    for r in flipped:
        recovery_rows.append(
            {
                "set": "frozen_correct_flipped",
                "position": r["position"],
                "case_id": r["case_id"],
                "target": r["target"],
                "truth": r["truth"],
                "frozen_pred": r[f"{PRIMARY_ARM}_frozen_pred"],
                "patched_pred": r[f"{PRIMARY_ARM}_patched_pred"],
                "recovered": False,
                "defect_accounted": "FLIP",
                "identity_coverage_product": r.get("identity_coverage_product"),
                "patch_a_kept_target_family_supported": r.get("patch_a_kept_target_family_supported"),
                "patch_b_applied": r.get("patch_b_applied"),
            }
        )
    recovery_sha = write_csv(
        OUT / "ABLATION_VALIDATOR_R1_RECOVERY.csv",
        recovery_rows,
        [
            "set",
            "position",
            "case_id",
            "target",
            "truth",
            "frozen_pred",
            "patched_pred",
            "recovered",
            "defect_accounted",
            "identity_coverage_product",
            "patch_a_kept_target_family_supported",
            "patch_b_applied",
        ],
    )

    class_fields = [
        "target",
        "system",
        "system_id",
        "n",
        "correct",
        "accuracy",
        "accuracy_wilson_low",
        "accuracy_wilson_high",
        "accuracy_wilson",
        "n_pos",
        "sensitivity",
        "sensitivity_wilson_low",
        "sensitivity_wilson_high",
        "sensitivity_wilson",
        "n_neg",
        "specificity",
        "specificity_wilson_low",
        "specificity_wilson_high",
        "specificity_wilson",
        "correct_over_n",
    ]
    class_rows = []
    systems = [
        ("GS-Deterministic V4.1 frozen", "gs_det_frozen", f"{PRIMARY_ARM}_frozen_pred", f"{PRIMARY_ARM}_frozen_correct"),
        ("GS validator counterfactual (patched a+b)", "gs_counterfactual", f"{PRIMARY_ARM}_patched_pred", f"{PRIMARY_ARM}_patched_correct"),
        ("CONSTANT_PER_TARGET", "constant_per_target", "constant_per_target_pred", "constant_per_target_correct"),
        ("CONSTANT_ALL_NEGATIVE", "constant_all_negative", "constant_all_negative_pred", "constant_all_negative_correct"),
        ("CONSTANT_ALL_POSITIVE", "constant_all_positive", "constant_all_positive_pred", "constant_all_positive_correct"),
    ]
    for r in eval_rows:
        r["constant_per_target_pred"] = constant_pred(r, "CONSTANT_PER_TARGET")
        r["constant_all_negative_pred"] = constant_pred(r, "CONSTANT_ALL_NEGATIVE")
        r["constant_all_positive_pred"] = constant_pred(r, "CONSTANT_ALL_POSITIVE")
        r["constant_per_target_correct"] = is_correct(r["truth"], r["constant_per_target_pred"])
        r["constant_all_negative_correct"] = is_correct(r["truth"], r["constant_all_negative_pred"])
        r["constant_all_positive_correct"] = is_correct(r["truth"], r["constant_all_positive_pred"])
    for target in TARGETS:
        subset = [r for r in eval_rows if r["target"] == target]
        for label, sid, pred_key, corr_key in systems:
            class_rows.append(class_row(target, label, sid, subset, pred_key, corr_key))
    class_sha = write_csv(OUT / "ABLATION_VALIDATOR_R1_CLASS_DECOMPOSED.csv", class_rows, class_fields)

    const_modes = ("CONSTANT_PER_TARGET", "CONSTANT_ALL_NEGATIVE", "CONSTANT_ALL_POSITIVE")
    const_rows = [score_constant(eval_rows, mode) for mode in const_modes]
    cpt = next(r for r in const_rows if r["baseline"] == "CONSTANT_PER_TARGET")
    if cpt["correct"] != CONSTANT_PER_TARGET_K:
        raise SystemExit(f"CONSTANT_PER_TARGET MISMATCH: got {cpt['correct']}/41 expected {CONSTANT_PER_TARGET_K}/41")
    cf_ok = [r[f"{PRIMARY_ARM}_patched_correct"] is True for r in eval_rows]
    cpt_ok = [r["constant_per_target_correct"] is True for r in eval_rows]
    stats = mcnemar(cf_ok, cpt_ok)
    const_rows.append(
        {
            "kind": "mcnemar_counterfactual_vs_CONSTANT_PER_TARGET",
            "baseline": "CONSTANT_PER_TARGET",
            "system_id": "gs_counterfactual",
            "n": N_EVALUABLE,
            "correct": sum(cf_ok),
            "accuracy": "",
            "accuracy_wilson_low": "",
            "accuracy_wilson_high": "",
            "accuracy_wilson": "",
            "correct_over_n": f"{sum(cf_ok)}/{N_EVALUABLE}",
            **stats,
        }
    )
    frozen_ok = [r[f"{PRIMARY_ARM}_frozen_correct"] is True for r in eval_rows]
    frozen_stats = mcnemar(frozen_ok, cpt_ok)
    const_rows.append(
        {
            "kind": "mcnemar_frozen_gs_det_vs_CONSTANT_PER_TARGET",
            "baseline": "CONSTANT_PER_TARGET",
            "system_id": "gs_det_frozen",
            "n": N_EVALUABLE,
            "correct": sum(frozen_ok),
            "accuracy": "",
            "accuracy_wilson_low": "",
            "accuracy_wilson_high": "",
            "accuracy_wilson": "",
            "correct_over_n": f"{sum(frozen_ok)}/{N_EVALUABLE}",
            **frozen_stats,
        }
    )
    const_sha = write_csv(
        OUT / "ABLATION_VALIDATOR_R1_CONSTANT_BASELINE.csv",
        const_rows,
        [
            "kind",
            "baseline",
            "system_id",
            "n",
            "correct",
            "accuracy",
            "accuracy_wilson_low",
            "accuracy_wilson_high",
            "accuracy_wilson",
            "correct_over_n",
            "b",
            "c",
            "net",
            "mcnemar_note",
        ],
    )

    n_cf = sum(cf_ok)
    n_frozen = sum(frozen_ok)
    recovered_ids = ";".join(f"{r['position']}:{r['case_id']}" for r in recovered)
    unrecovered_ids = ";".join(f"{r['position']}:{r['case_id']}" for r in unrecovered)
    flipped_ids = ";".join(f"{r['position']}:{r['case_id']}" for r in flipped) or "(none)"
    a_recovered = [r for r in recovered if r.get("patch_a_kept_target_family_supported")]
    b_recovered = [r for r in recovered if r.get("patch_b_applied")]

    summary = f"""# VALIDATOR COUNTERFACTUAL R1

{DIAGNOSTIC_HEADER}

This is a post-hoc diagnostic on frozen, locked TargetMeasurements. It is **not**
prospective performance and must not be scored as a primary system result.

Patch iteration: **{PATCH_ITERATION}** (stop; do not retune (a) or (b)).
Search / HMM / LLM calls: **none**. POSITION_LOCKS writes: **none**.

## Answer

The two documented defects account for **{len(recovered)} of {N_SHARED_ERRORS}** shared errors
on the 41 truth-evaluable cases. **{len(flipped)} of {N_CORRECT_FROZEN}** frozen-correct calls flip.

| quantity | value |
| --- | --- |
| shared errors recovered | {len(recovered)}/{N_SHARED_ERRORS} |
| recovered positions | {recovered_ids or '(none)'} |
| shared errors remaining | {len(unrecovered)}/{N_SHARED_ERRORS} |
| remaining positions | {unrecovered_ids or '(none)'} |
| frozen-correct flips | {len(flipped)}/{N_CORRECT_FROZEN} |
| flipped positions | {flipped_ids} |
| recovered via (a) family_identity_is_decisive | {len(a_recovered)} |
| recovered via (b) classify_architecture | {len(b_recovered)} |
| frozen GS-Det correct/n | {n_frozen}/{N_EVALUABLE} |
| counterfactual correct/n | {n_cf}/{N_EVALUABLE} |
| CONSTANT_PER_TARGET correct/n | {cpt['correct']}/{N_EVALUABLE} |

## Patches applied (one iteration)

(a) `family_identity_is_decisive`: drop the "did not pass the family gate" substring
test; compare `_DECISIVE_IDENTITY_PRODUCT` (0.70) against identity × coverage.
Replay undoes `refine_weak_family_classification` only where that post-action
relabel is already stored, then re-applies it with the patched test.

(b) `classify_architecture`: if `reconstruction.hmm_coverage` and
`best_hmm.model_coverage` disagree by more than 0.2 on the same ORF, use
`best_hmm.model_coverage`. Re-run only when that disagreement is present, so
frozen fusion/partner evidence is not reconstructed.

## Shared-error case table

{md_table(
    ["pos", "case", "truth", "frozen", "patched", "recovered", "defect"],
    [
        [
            r["position"],
            r["case_id"],
            r["truth"],
            r[f"{PRIMARY_ARM}_frozen_pred"],
            r[f"{PRIMARY_ARM}_patched_pred"],
            "YES" if r.get(f"{PRIMARY_ARM}_patched_correct") is True else "NO",
            (
                "a"
                if r.get("patch_a_kept_target_family_supported") and r.get(f"{PRIMARY_ARM}_patched_correct")
                else "b"
                if r.get("patch_b_applied") and r.get(f"{PRIMARY_ARM}_patched_correct")
                else "neither"
            ),
        ]
        for r in shared
    ],
)}

## Class-decomposed metrics (counterfactual, with constant baseline)

{md_table(
    ["target", "system", "correct/n", "accuracy Wilson 95%", "n_pos", "sensitivity", "n_neg", "specificity"],
    [
        [
            r["target"],
            r["system"],
            r["correct_over_n"],
            r["accuracy_wilson"],
            r["n_pos"],
            r["sensitivity"] if r["sensitivity"] == NA_SPEC else f"{float(r['sensitivity']):.6f}" if isinstance(r["sensitivity"], float) else r["sensitivity"],
            r["n_neg"],
            r["specificity"] if r["specificity"] == NA_SPEC else f"{float(r['specificity']):.6f}" if isinstance(r["specificity"], float) else r["specificity"],
        ]
        for r in class_rows
    ],
)}

## Constant baseline (41 evaluable)

{md_table(
    ["baseline / comparison", "correct/n", "b", "c", "net", "McNemar"],
    [
        [r["baseline"] if r["kind"] == "baseline" else r["kind"], r["correct_over_n"], r.get("b", ""), r.get("c", ""), r.get("net", ""), r.get("mcnemar_note", "")]
        for r in const_rows
    ],
)}

Frozen GS-Det vs CONSTANT_PER_TARGET uses the locked endpoints. The counterfactual
row is the patched validator replay and is not a new system arm.

## Inputs

Locked family_evidence JSON under `manuscript_benchmark/RUNS/position_*/**/family/TARGET/family_evidence.json`
for GS-Deterministic, GS-Agentic, and GS-Exhaustive (180 files). Truth from
`TRUTH_M60/M60_EXTERNAL_TRUTH_FINAL_LOCKED.json`. Locked endpoints from
`M60_GS_*_LOCKED.json`. Frozen validator source was not modified.
"""
    summary_sha = write_text(OUT / "ABLATION_VALIDATOR_R1_SUMMARY.md", summary)

    manifest = {
        "POST_HOC_DIAGNOSTIC": DIAGNOSTIC_HEADER.split(" = ", 1)[-1],
        "not_prospective_performance": True,
        "patch_iteration": PATCH_ITERATION,
        "search_hmm_llm_rerun": False,
        "position_locks_written": False,
        "n_cases": 60,
        "n_evaluable": N_EVALUABLE,
        "n_shared_errors": N_SHARED_ERRORS,
        "n_frozen_correct": N_CORRECT_FROZEN,
        "n_recovered": len(recovered),
        "n_flipped_correct": len(flipped),
        "recovered_positions": [r["position"] for r in recovered],
        "unrecovered_positions": [r["position"] for r in unrecovered],
        "flipped_positions": [r["position"] for r in flipped],
        "recovered_via_a": [r["position"] for r in a_recovered],
        "recovered_via_b": [r["position"] for r in b_recovered],
        "frozen_correct_over_n": f"{n_frozen}/{N_EVALUABLE}",
        "counterfactual_correct_over_n": f"{n_cf}/{N_EVALUABLE}",
        "constant_per_target_correct_over_n": f"{cpt['correct']}/{N_EVALUABLE}",
        "outputs": {
            "ABLATION_VALIDATOR_R1_CASE_LEVEL.csv": case_sha,
            "ABLATION_VALIDATOR_R1_RECOVERY.csv": recovery_sha,
            "ABLATION_VALIDATOR_R1_CLASS_DECOMPOSED.csv": class_sha,
            "ABLATION_VALIDATOR_R1_CONSTANT_BASELINE.csv": const_sha,
            "ABLATION_VALIDATOR_R1_SUMMARY.md": summary_sha,
        },
        "written_utc": utc_now(),
    }
    man_sha = write_json(OUT / "ABLATION_VALIDATOR_R1_MANIFEST.json", manifest)
    manifest["outputs"]["ABLATION_VALIDATOR_R1_MANIFEST.json"] = man_sha
    write_json(OUT / "ABLATION_VALIDATOR_R1_MANIFEST.json", manifest)

    assert_no_lock_writes(lock_mtime)
    print(
        f"RECOVERED {len(recovered)}/{N_SHARED_ERRORS} ; "
        f"FLIPPED {len(flipped)}/{N_CORRECT_FROZEN} ; "
        f"COUNTERFACTUAL {n_cf}/{N_EVALUABLE} ; "
        f"PATCH_ITERATION={PATCH_ITERATION}",
        flush=True,
    )
    print(f"OUTPUT {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
