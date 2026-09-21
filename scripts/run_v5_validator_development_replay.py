#!/usr/bin/env python3
"""Replay locked M60 TargetMeasurements through the repaired V5 validator.

DEVELOPMENT / POST-HOC
NOT VALIDATION

M60 truth and errors are already known. This replay is not prospective
evidence and must not be scored as a V5 confirmation result.

Does not re-run search, HMM, or LLM. Does not write POSITION_LOCKS,
M60 locks, M60 truth, or V4.1 manuscript artifacts.
"""
from __future__ import annotations

import csv
import hashlib
import json
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
from genome_skeptic.models import ClaimType, GeneSearchHit, LocusReconstruction, TargetFamily, TargetType  # noqa: E402
from genome_skeptic.agents.diagnostic_needs_v4_1_dev import family_identity_is_decisive  # noqa: E402
from genome_skeptic.validators.falsification import classify_polarity  # noqa: E402
from genome_skeptic.validators.family_orthology import FamilyEvidence, classify_family_orthology  # noqa: E402
from genome_skeptic.validators.locus_reconstruction import (  # noqa: E402
    architecture_profile_coverage,
    classify_architecture,
)

MB = ROOT / "manuscript_benchmark"
TRUTH_ROOT = MB / "TRUTH_M60"
RUNS = MB / "RUNS"
LOCK_ROOT = MB / "POSITION_LOCKS"
OUT = ROOT / "prospective_v5" / "DEVELOPMENT_REPLAY"

BANNER = "DEVELOPMENT / POST-HOC ; NOT VALIDATION"
REFINE_WEAK_NOTE = (
    "target family support is not sequence-decisive; competing-family comparison did not settle identity"
)
SHARED_ERROR_POSITIONS = (13, 14, 19, 36, 37, 41, 44, 48)
ARMS = (
    ("gs_det", "GS_DETERMINISTIC_V4_1", "GS-Deterministic V4.1"),
)
PRIMARY_ARM = "gs_det"
N_EVALUABLE = 41
N_CORRECT_FROZEN = 33
N_SHARED_ERRORS = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda fh_iter=fh: fh_iter.read(1 << 20), b""):
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


def endpoint_from_evidence(ev: FamilyEvidence) -> str:
    polarity = classify_polarity(
        list(ev.member_hits or []),
        Settings(),
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


def apply_refine_weak_if_not_decisive(competitive: dict, reconstruction: dict) -> bool:
    if competitive.get("classification") != "target_family_supported":
        return False
    if family_identity_is_decisive(competitive, reconstruction=reconstruction):
        return False
    competitive["classification"] = "ambiguous_family"
    conflicts = list(competitive.get("conflicting_evidence") or [])
    conflicts.append(REFINE_WEAK_NOTE)
    competitive["conflicting_evidence"] = conflicts
    return True


def apply_architecture_repair(
    ev: FamilyEvidence,
    family: TargetFamily,
    settings: Settings,
) -> tuple[bool, str | None, str | None]:
    recon_raw = dict(ev.reconstruction or {})
    if not recon_raw:
        return False, None, ev.architecture
    rec = LocusReconstruction.model_validate(recon_raw)
    frozen_arch = rec.architecture
    if architecture_profile_coverage(rec, ev.best_hmm) <= float(rec.hmm_coverage or 0.0):
        return False, frozen_arch, frozen_arch
    patched = classify_architecture(
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
    return True, frozen_arch, patched.architecture


def replay_v5(
    blob: dict,
    target: str,
    settings: Settings,
    family_cache: dict[str, TargetFamily | None],
) -> dict:
    ev = family_evidence_from_json(deepcopy(blob))
    recon = dict(ev.reconstruction or {})
    competitive = dict(recon.get("competitive_family") or blob.get("competitive_family") or {})
    frozen_cls = competitive.get("classification")
    undid = undo_refine_weak(competitive)
    a_relabelled = apply_refine_weak_if_not_decisive(competitive, recon) if undid else False
    a_kept = bool(undid and competitive.get("classification") == "target_family_supported")
    recon["competitive_family"] = competitive
    ev.reconstruction = recon

    family_id = ev.family_id or target
    if family_id not in family_cache:
        family_cache[family_id] = load_family(family_id) or dummy_family(family_id)
    family = family_cache[family_id] or dummy_family(family_id)
    b_applied, frozen_arch, patched_arch = apply_architecture_repair(ev, family, settings)

    classify_family_orthology(
        ev,
        family,
        settings,
        query_hits=list(ev.member_hits or []),
        locus_evidence=None,
    )
    apply_reconstruction_override(ev)
    pred = endpoint_from_evidence(ev)
    return {
        "v5_pred": pred,
        "v5_classification": (ev.reconstruction or {}).get("competitive_family", {}).get("classification"),
        "v5_architecture": ev.architecture,
        "v5_domain_only": ev.domain_only,
        "v5_supports_orthologue": ev.supports_orthologue,
        "frozen_classification": frozen_cls,
        "patch_a_undid_refine_weak": undid,
        "patch_a_still_relabelled": a_relabelled,
        "patch_a_kept_target_family_supported": a_kept,
        "patch_b_applied": b_applied,
        "frozen_architecture": frozen_arch if frozen_arch is not None else blob.get("architecture"),
        "decisive_under_v5": family_identity_is_decisive(competitive, reconstruction=recon),
    }


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(obj) if isinstance(obj, dict) else obj
    if isinstance(payload, dict):
        payload = {
            "DEVELOPMENT_POST_HOC": True,
            "NOT_VALIDATION": True,
            "NOT_PROSPECTIVE": True,
            **payload,
        }
    text = json.dumps(payload, indent=2, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"# {BANNER}\n")
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    return sha256_file(path)


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.startswith(BANNER):
        text = BANNER + "\n\n" + text
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def constant_classifier(rows: list[dict], target_prefix: str) -> bool:
    preds = {r["v5_pred"] for r in rows if r["target"].startswith(target_prefix)}
    return len(preds) <= 1


def assert_no_lock_writes(before: dict[str, float]) -> None:
    after = {str(p): p.stat().st_mtime for p in LOCK_ROOT.glob("position_*/POSITION_LOCK.json")}
    if after != before:
        raise SystemExit("POSITION_LOCKS were modified; aborting development replay")


def main() -> int:
    print(BANNER, flush=True)
    lock_mtime = {str(p): p.stat().st_mtime for p in LOCK_ROOT.glob("position_*/POSITION_LOCK.json")}
    settings = Settings()
    truth_obj = load_json(TRUTH_ROOT / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json")
    truth_cases = {c["case_id"]: c for c in truth_obj["cases"]}
    locked = index_preds(load_json(MB / "M60_GS_DETERMINISTIC_LOCKED.json"))
    family_cache: dict[str, TargetFamily | None] = {}
    rows = []
    missing = []
    for cid, tcase in sorted(truth_cases.items(), key=lambda kv: int(kv[1]["position"])):
        position = int(tcase["position"])
        accession = tcase["accession"]
        target = tcase["target"]
        truth = tcase["truth_value"]
        frozen_pred = gs_binary(locked[cid])
        path = find_family_evidence(position, accession, target, "GS_DETERMINISTIC_V4_1")
        row = {
            "case_id": cid,
            "position": position,
            "accession": accession,
            "target": target,
            "stratum": tcase.get("stratum"),
            "truth": truth,
            "evaluable": truth in {"POSITIVE", "NEGATIVE"},
            "shared_error": position in SHARED_ERROR_POSITIONS,
            "v4_pred": frozen_pred,
        }
        if not path.is_file():
            missing.append(str(path))
            row["v5_pred"] = "MISSING"
            rows.append(row)
            continue
        blob = load_json(path)
        frozen_ev = family_evidence_from_json(blob)
        frozen_replay = endpoint_from_evidence(frozen_ev)
        v5 = replay_v5(blob, target, settings, family_cache)
        row["v4_frozen_replay_pred"] = frozen_replay
        row["v4_frozen_replay_matches_lock"] = frozen_replay == frozen_pred
        row["v5_pred"] = v5["v5_pred"]
        row["v4_correct"] = is_correct(truth, frozen_pred)
        row["v5_correct"] = is_correct(truth, v5["v5_pred"])
        row["endpoint_changed"] = frozen_pred != v5["v5_pred"]
        row["frozen_architecture"] = blob.get("architecture")
        row["v5_architecture"] = v5["v5_architecture"]
        row["frozen_classification"] = (blob.get("reconstruction") or {}).get("competitive_family", {}).get("classification")
        row["v5_classification"] = v5["v5_classification"]
        row["patch_a_kept_target_family_supported"] = v5["patch_a_kept_target_family_supported"]
        row["patch_b_applied"] = v5["patch_b_applied"]
        row["family_evidence"] = str(path.relative_to(ROOT)).replace("\\", "/")
        rows.append(row)

    if missing:
        raise SystemExit(f"missing family_evidence.json n={len(missing)} first={missing[0]}")
    mismatch = [r for r in rows if r.get("v4_frozen_replay_matches_lock") is False]
    if mismatch:
        ids = ",".join(str(r["position"]) for r in mismatch)
        raise SystemExit(f"frozen classify_polarity does not match V4.1 locks at {ids}")

    eval_rows = [r for r in rows if r["evaluable"]]
    if len(eval_rows) != N_EVALUABLE:
        raise SystemExit(f"evaluable {len(eval_rows)} != {N_EVALUABLE}")
    shared = [r for r in eval_rows if r["shared_error"]]
    if len(shared) != N_SHARED_ERRORS:
        raise SystemExit(f"shared errors {len(shared)} != {N_SHARED_ERRORS}")
    correct33 = [r for r in eval_rows if r.get("v4_correct") is True]
    if len(correct33) != N_CORRECT_FROZEN:
        raise SystemExit(f"frozen correct {len(correct33)} != {N_CORRECT_FROZEN}")

    rescued = [r for r in shared if r.get("v5_correct") is True]
    remaining = [r for r in shared if r.get("v5_correct") is not True]
    degraded = [r for r in correct33 if r.get("v5_correct") is not True]
    changed = [r for r in rows if r.get("endpoint_changed")]
    v5_correct = sum(1 for r in eval_rows if r.get("v5_correct") is True)
    v4_correct = sum(1 for r in eval_rows if r.get("v4_correct") is True)

    teta = [r for r in rows if r["target"].startswith("tetA")]
    rpob = [r for r in rows if r["target"].startswith("rpoB")]
    teta_pos = sum(1 for r in teta if r["v5_pred"] == "POSITIVE")
    teta_neg = sum(1 for r in teta if r["v5_pred"] == "NEGATIVE")
    rpob_pos = sum(1 for r in rpob if r["v5_pred"] == "POSITIVE")
    rpob_neg = sum(1 for r in rpob if r["v5_pred"] == "NEGATIVE")
    teta_constant = constant_classifier(teta, "tetA")
    rpob_constant = constant_classifier(rpob, "rpoB")
    v5_constant = teta_constant and rpob_constant

    OUT.mkdir(parents=True, exist_ok=True)
    case_sha = write_csv(
        OUT / "V5_DEVELOPMENT_REPLAY_CASE_LEVEL.csv",
        rows,
        [
            "case_id",
            "position",
            "accession",
            "target",
            "stratum",
            "truth",
            "evaluable",
            "shared_error",
            "v4_pred",
            "v5_pred",
            "v4_correct",
            "v5_correct",
            "endpoint_changed",
            "frozen_architecture",
            "v5_architecture",
            "frozen_classification",
            "v5_classification",
            "patch_a_kept_target_family_supported",
            "patch_b_applied",
            "family_evidence",
        ],
    )
    summary = {
        "label": BANNER,
        "n_cases": len(rows),
        "n_evaluable": len(eval_rows),
        "v4_correct_over_n": f"{v4_correct}/{N_EVALUABLE}",
        "v5_correct_over_n": f"{v5_correct}/{N_EVALUABLE}",
        "n_changed": len(changed),
        "changed_positions": [r["position"] for r in changed],
        "n_rescued_known_errors": len(rescued),
        "rescued_positions": [r["position"] for r in rescued],
        "n_remaining_known_errors": len(remaining),
        "remaining_error_positions": [r["position"] for r in remaining],
        "n_previously_correct_degraded": len(degraded),
        "degraded_positions": [r["position"] for r in degraded],
        "teta_v5_positive": teta_pos,
        "teta_v5_negative": teta_neg,
        "rpob_v5_positive": rpob_pos,
        "rpob_v5_negative": rpob_neg,
        "teta_constant_classifier": teta_constant,
        "rpob_constant_classifier": rpob_constant,
        "v5_constant_classifier_on_m60": v5_constant,
        "additional_tuning_performed": False,
        "search_hmm_llm_rerun": False,
        "position_locks_written": False,
        "written_utc": utc_now(),
        "outputs": {"V5_DEVELOPMENT_REPLAY_CASE_LEVEL.csv": case_sha},
    }
    man_sha = write_json(OUT / "V5_DEVELOPMENT_REPLAY_MANIFEST.json", summary)
    summary["outputs"]["V5_DEVELOPMENT_REPLAY_MANIFEST.json"] = man_sha
    write_json(OUT / "V5_DEVELOPMENT_REPLAY_MANIFEST.json", summary)
    report = f"""# V5 validator development replay

{BANNER}

M60 locked TargetMeasurements were replayed through the repaired V5
decision layer exactly once. Searches were not rerun. This is not
prospective validation.

| quantity | value |
| --- | --- |
| V4.1 M60 accuracy | {v4_correct}/{N_EVALUABLE} |
| V5 development-replay accuracy | {v5_correct}/{N_EVALUABLE} |
| endpoints changed | {len(changed)} |
| known M60 errors rescued | {len(rescued)} |
| previously correct cases degraded | {len(degraded)} |
| tet(A) V5 POSITIVE | {teta_pos} |
| tet(A) V5 NEGATIVE | {teta_neg} |
| rpoB V5 POSITIVE | {rpob_pos} |
| rpoB V5 NEGATIVE | {rpob_neg} |
| V5 remains constant classifier | {"YES" if v5_constant else "NO"} |
| additional tuning | NO |
"""
    write_text(OUT / "V5_DEVELOPMENT_REPLAY_REPORT.md", report)
    assert_no_lock_writes(lock_mtime)
    print(f"V4.1 {v4_correct}/{N_EVALUABLE}", flush=True)
    print(f"V5 {v5_correct}/{N_EVALUABLE}", flush=True)
    print(f"CHANGED {len(changed)} RESCUED {len(rescued)} DEGRADED {len(degraded)}", flush=True)
    print(f"TETA +{teta_pos} -{teta_neg} ; RPOB +{rpob_pos} -{rpob_neg}", flush=True)
    print(f"V5_CONSTANT_CLASSIFIER {'YES' if v5_constant else 'NO'}", flush=True)
    print(f"OUTPUT {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
