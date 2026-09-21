#!/usr/bin/env python3
"""Read-only extractor of locked M60 artifacts for post-hoc error forensics.

Does not regenerate predictions, modify scientific code, or touch D20.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOL_ROOT = ROOT.parent / "GenomeSkeptic_SolAblation"
OUT = Path(__file__).resolve().parent / "_extracted"
SKIP_DIRS = {
    "hmmbuild",
    "hmmsearch",
    "hmm_targets",
    "diamond",
    "mmseqs",
    "blast",
    "tmp",
    "__pycache__",
}
KEEP_JSON_NAMES = {
    "case_locked.json",
    "claims.json",
    "evidence.json",
    "locus_evidence.json",
    "locus_stages.json",
    "agentic_provenance.json",
    "family_evidence.json",
    "planner_decision.json",
    "critic_review.json",
    "call_log.json",
}
ERROR_POSITIONS = (13, 14, 19, 36, 37, 41, 44, 48)
EXPECTED_TRUTH = "a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9"
EXPECTED_SOL_MANIFEST = "2a9f86956ca12026b4ff39fc7bcaf297db992ba4db53421a9482683ae1885a39"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def win_open_path(path: Path) -> Path:
    raw = str(path.resolve())
    if os.name == "nt" and not raw.startswith("\\\\?\\"):
        if raw.startswith("\\\\"):
            return Path("\\\\?\\UNC\\" + raw[2:])
        return Path("\\\\?\\" + raw)
    return path


def compact_hit(h: dict) -> dict:
    keys = [
        "query_id",
        "contig_id",
        "orf_id",
        "search_kind",
        "tool",
        "identity",
        "query_coverage",
        "subject_coverage",
        "alignment_length",
        "evalue",
        "bitscore",
        "qstart",
        "qend",
        "tstart",
        "tend",
        "strand",
        "query_length",
        "subject_length",
        "near_contig_edge",
        "possible_edge_truncation",
        "domain_name",
    ]
    return {k: h.get(k) for k in keys if k in h}


def compact_family(ev: dict) -> dict:
    recon = dict(ev.get("reconstruction") or {})
    recon.pop("candidate_aa", None)
    recon.pop("translated_sequence", None)
    segs = []
    for seg in recon.get("candidate_segments") or []:
        if isinstance(seg, dict):
            segs.append({k: seg.get(k) for k in ("contig", "start", "end", "strand", "orf_id", "frame") if k in seg})
        else:
            segs.append(seg)
    recon["candidate_segments"] = segs
    member_hits = [compact_hit(h) for h in (ev.get("member_hits") or [])[:12]]
    return {
        "family_id": ev.get("family_id"),
        "architecture": ev.get("architecture"),
        "domain_only": ev.get("domain_only"),
        "supports_orthologue": ev.get("supports_orthologue"),
        "hierarchy": ev.get("hierarchy"),
        "best_hmm": ev.get("best_hmm"),
        "metrics": ev.get("metrics"),
        "limitations": (ev.get("limitations") or [])[:12],
        "fusion": ev.get("fusion"),
        "split": ev.get("split"),
        "fragmented": ev.get("fragmented"),
        "paralogue": ev.get("paralogue"),
        "n_member_hits": len(ev.get("member_hits") or []),
        "member_hits_top": member_hits,
        "reconstruction": {
            "architecture": recon.get("architecture"),
            "contig": recon.get("contig"),
            "strand": recon.get("strand"),
            "genomic_start": recon.get("genomic_start"),
            "genomic_end": recon.get("genomic_end"),
            "hmm_coverage": recon.get("hmm_coverage"),
            "sequence_identity": recon.get("sequence_identity"),
            "protein_coverage": recon.get("protein_coverage"),
            "query_identity": recon.get("query_identity"),
            "family_gate_passed": recon.get("family_gate_passed"),
            "contig_edge": recon.get("contig_edge"),
            "protein_length": recon.get("protein_length"),
            "competitive_family": recon.get("competitive_family"),
            "multiplicity": recon.get("multiplicity"),
            "paralogue_record": recon.get("paralogue_record"),
            "ortholog_reference_discrimination": recon.get("ortholog_reference_discrimination"),
            "candidate_segments": recon.get("candidate_segments"),
            "divergence": recon.get("divergence"),
        },
    }


def compact_claim(c: dict) -> dict:
    return {
        "claim_type": c.get("claim_type") or (c.get("claim_class") and None),
        "status": c.get("status"),
        "confidence": c.get("confidence"),
        "statement": c.get("statement"),
        "rationale": (c.get("rationale") or "")[:1200],
        "architecture": c.get("architecture"),
        "homology_support": c.get("homology_support"),
        "orthology_class": c.get("orthology_class"),
        "query_id": c.get("query_id"),
        "target_type": (c.get("profile") or {}).get("target_type") if isinstance(c.get("profile"), dict) else c.get("target_type"),
        "provenance": {
            "evidence_ledger_ids": ((c.get("provenance") or {}).get("evidence_ledger_ids") or [])[:40],
            "notes": ((c.get("provenance") or {}).get("notes") or "")[:800],
        },
        "metrics": {k: (c.get("metrics") or {}).get(k) for k in (
            "homology_support", "n_strong", "n_partial", "architecture", "family_support",
            "domain_only", "paralogue_loci", "best_identity", "best_coverage",
        ) if (c.get("metrics") or {}).get(k) is not None} if isinstance(c.get("metrics"), dict) else c.get("metrics"),
    }


def compact_evidence(rows: list) -> list:
    out = []
    for e in rows or []:
        out.append({
            "id": e.get("id"),
            "kind": e.get("kind") or e.get("evidence_kind") or e.get("type"),
            "origin": e.get("origin") or ((e.get("provenance") or {}).get("created_by") if isinstance(e.get("provenance"), dict) else None),
            "summary": (e.get("summary") or e.get("statement") or e.get("note") or "")[:300],
            "fields": sorted(e.keys())[:20],
        })
        if len(out) >= 80:
            break
    return out


def parse_blastx(path: Path, n: int = 8) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        rows.append({
            "qseqid": parts[0],
            "sseqid": parts[1],
            "pident": float(parts[2]) if parts[2] else None,
            "length": int(parts[3]) if parts[3].isdigit() else parts[3],
            "mismatch": parts[4],
            "gapopen": parts[5],
            "qstart": parts[6],
            "qend": parts[7],
            "sstart": parts[8],
            "send": parts[9],
            "evalue": parts[10],
            "bitscore": parts[11],
        })
        if len(rows) >= n:
            break
    return rows


def find_named_jsons(run_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not run_dir.exists():
        return found
    stack = [win_open_path(run_dir)]
    while stack:
        cur = stack.pop()
        try:
            names = os.listdir(cur)
        except (OSError, FileNotFoundError):
            continue
        for name in names:
            if name in SKIP_DIRS:
                continue
            child = cur / name
            try:
                is_dir = child.is_dir()
            except OSError:
                continue
            if is_dir:
                # Stay shallow-ish: skip nested tool dumps.
                if name.startswith("hmm_") or name.endswith(".d"):
                    continue
                stack.append(child)
            elif name in KEEP_JSON_NAMES:
                rel = name if name not in found else f"{child.parent.name}/{name}"
                found[str(child)] = child
    by_name = {}
    for p in found.values():
        key = p.name
        if p.name == "family_evidence.json":
            key = "family_evidence.json"
        by_name.setdefault(key, p)
    return by_name


def extract_arm(run_dir: Path) -> dict:
    files = find_named_jsons(run_dir)
    payload = {"run_dir": str(run_dir), "files_found": sorted({p.name for p in files.values()})}
    for label, name in [
        ("claims", "claims.json"),
        ("evidence", "evidence.json"),
        ("locus_stages", "locus_stages.json"),
        ("family_evidence", "family_evidence.json"),
        ("agentic_provenance", "agentic_provenance.json"),
        ("planner_decision", "planner_decision.json"),
        ("critic_review", "critic_review.json"),
    ]:
        path = files.get(name)
        if path is None:
            payload[label] = None
            continue
        try:
            obj = json.loads(win_open_path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            payload[label] = {"error": str(exc), "path": str(path)}
            continue
        if label == "family_evidence" and isinstance(obj, dict):
            payload[label] = compact_family(obj)
        elif label == "claims" and isinstance(obj, list):
            payload[label] = [compact_claim(c) for c in obj]
        elif label == "evidence" and isinstance(obj, list):
            payload[label] = compact_evidence(obj)
        elif label == "agentic_provenance" and isinstance(obj, dict):
            payload[label] = {
                "follow_up_policy": obj.get("follow_up_policy"),
                "selected_action": obj.get("selected_action"),
                "actions_executed": obj.get("actions_executed"),
                "diagnostic_needs_m0": obj.get("diagnostic_needs_m0"),
                "diagnostic_needs_m_final": obj.get("diagnostic_needs_m_final"),
                "measurement_state": obj.get("measurement_state"),
                "locus_stages_m0": obj.get("locus_stages_m0"),
                "locus_stages_m_final": obj.get("locus_stages_m_final"),
                "validator_consumed_measurement_hash": obj.get("validator_consumed_measurement_hash"),
                "measurements_changed_before_validation": obj.get("measurements_changed_before_validation"),
                "critic_second_action": obj.get("critic_second_action"),
                "planner_grounding_status": obj.get("planner_grounding_status"),
            }
        else:
            payload[label] = obj
    return payload


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    truth_path = ROOT / "manuscript_benchmark" / "TRUTH_M60" / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json"
    case_csv = ROOT / "manuscript_benchmark" / "RESULTS_M60" / "M60_FINAL_CASE_LEVEL_RESULTS.csv"
    sol_csv = SOL_ROOT / "manuscript_benchmark" / "SOL56_FULL_ABLATION" / "SOL56_M60_CASE_LEVEL.csv"
    sol_manifest = SOL_ROOT / "manuscript_benchmark" / "SOL56_FULL_ABLATION" / "SOL56_M60_MANIFEST.json"
    verification = {
        "truth_sha256": sha256_file(truth_path),
        "truth_expected": EXPECTED_TRUTH,
        "truth_ok": sha256_file(truth_path) == EXPECTED_TRUTH,
        "sol_manifest_file_sha256": sha256_file(sol_manifest),
        "sol_manifest_expected": EXPECTED_SOL_MANIFEST,
        "sol_manifest_ok": sha256_file(sol_manifest) == EXPECTED_SOL_MANIFEST,
        "d20_touched": False,
        "scientific_code_modified": False,
        "predictions_rerun": False,
    }
    (OUT / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    if not verification["truth_ok"]:
        raise SystemExit(f"truth hash mismatch: {verification}")

    truth = load_json(truth_path)
    truth_by_pos = {c["position"]: c for c in truth["cases"]}
    rows = list(csv.DictReader(case_csv.open(encoding="utf-8")))
    sol_rows = {int(r["position"]): r for r in csv.DictReader(sol_csv.open(encoding="utf-8"))}

    errors = []
    for r in rows:
        if r["evaluable"] != "True":
            continue
        if r["gs_det_pred"] != r["truth"]:
            errors.append(r)
    shared = []
    discrepancy = []
    for r in errors:
        pos = int(r["position"])
        sol = sol_rows[pos]
        same = (
            r["gs_agent_pred"] == r["gs_det_pred"]
            and r["gs_exh_pred"] == r["gs_det_pred"]
            and sol["sol_pred"] == r["gs_det_pred"]
            and r["gs_agent_correct"] == "False"
            and r["gs_exh_correct"] == "False"
            and sol["sol_correct"] == "False"
        )
        rec = {
            "case_id": r["case_id"],
            "position": pos,
            "target": r["target"],
            "stratum": r["stratum"],
            "truth": r["truth"],
            "gs_det_pred": r["gs_det_pred"],
            "gs_agent_pred": r["gs_agent_pred"],
            "gs_exh_pred": r["gs_exh_pred"],
            "sol_pred": sol["sol_pred"],
            "same_wrong_across_all_gs_arms": same,
        }
        (shared if same else discrepancy).append(rec)
    ident = {
        "n_det_errors_evaluable": len(errors),
        "n_shared": len(shared),
        "shared": shared,
        "discrepancy": discrepancy,
        "stop": bool(discrepancy) or len(shared) != 8,
    }
    (OUT / "error_identity.json").write_text(json.dumps(ident, indent=2) + "\n", encoding="utf-8")
    if ident["stop"]:
        raise SystemExit("ERROR IDENTITY DISCREPANCY: " + json.dumps(ident, indent=2))

    cases = {}
    for rec in shared:
        pos = rec["position"]
        tcase = truth_by_pos[pos]
        acc = tcase["accession"]
        target = tcase["target"]
        pos_dir = ROOT / "manuscript_benchmark" / "POSITION_LOCKS" / f"position_{pos}"
        run_root = ROOT / "manuscript_benchmark" / "RUNS" / f"position_{pos}" / acc / target
        ev_dir = ROOT / "manuscript_benchmark" / "TRUTH_M60" / "EVIDENCE" / f"position_{pos:02d}_{acc}_{target}"
        if not ev_dir.exists():
            ev_dir = ROOT / "manuscript_benchmark" / "TRUTH_M60" / "EVIDENCE" / f"position_{pos}_{acc}_{target}"
        sol_lock = SOL_ROOT / "manuscript_benchmark" / "SOL56_FULL_ABLATION" / "locks" / f"position_{pos}.json"
        sol_lock_obj = load_json(sol_lock)
        sol_run = Path(str(sol_lock_obj.get("case_dir") or "").replace("/mnt/c/", "C:/").replace("/", os.sep))
        if not sol_run.exists():
            sol_run = (
                SOL_ROOT
                / "manuscript_benchmark"
                / "ABLATION_SOL56_HIGH_POSTHOC"
                / "full"
                / rec["case_id"]
                / "GS_AGENTIC_V4_1_SOL56_HIGH_POSTHOC"
            )
        orfs = None
        orf_path = ev_dir / "orfs.json"
        if orf_path.exists():
            raw_orfs = load_json(orf_path)
            wanted = set(tcase.get("candidate_sequence_ids") or [])
            coords = tcase.get("candidate_coordinates") or {}
            keep = []
            for o in raw_orfs if isinstance(raw_orfs, list) else raw_orfs.get("orfs") or []:
                oid = o.get("orf_id") or o.get("id")
                if oid in wanted:
                    keep.append({k: o.get(k) for k in ("orf_id", "id", "contig_id", "contig", "start", "end", "strand", "length_aa", "near_contig_edge") if k in o})
            if not keep and coords:
                for o in raw_orfs if isinstance(raw_orfs, list) else raw_orfs.get("orfs") or []:
                    if o.get("contig_id") == coords.get("contig") or o.get("contig") == coords.get("contig"):
                        if o.get("start") == coords.get("start") or abs((o.get("start") or 0) - (coords.get("start") or 0)) < 5:
                            keep.append({k: o.get(k) for k in ("orf_id", "id", "contig_id", "contig", "start", "end", "strand", "length_aa", "near_contig_edge") if k in o})
            orfs = keep[:6]
        cases[str(pos)] = {
            "identity": rec,
            "truth": {
                "truth_value": tcase.get("truth_value"),
                "truth_status": tcase.get("truth_status"),
                "evidence_route_1": tcase.get("evidence_route_1"),
                "evidence_route_2": tcase.get("evidence_route_2"),
                "evidence_route_concordance": tcase.get("evidence_route_concordance"),
                "candidate_sequence_ids": tcase.get("candidate_sequence_ids"),
                "candidate_coordinates": tcase.get("candidate_coordinates"),
                "primary_reference_accessions": tcase.get("primary_reference_accessions"),
                "competitor_reference_accessions": tcase.get("competitor_reference_accessions"),
                "sequence_coverage": tcase.get("sequence_coverage"),
                "sequence_similarity": tcase.get("sequence_similarity"),
                "family_or_profile_result": tcase.get("family_or_profile_result"),
                "orthology_or_phylogeny_result": tcase.get("orthology_or_phylogeny_result"),
                "primary_evidence_summary": tcase.get("primary_evidence_summary"),
                "secondary_evidence_summary": tcase.get("secondary_evidence_summary"),
                "adjudication_rationale": tcase.get("adjudication_rationale"),
            },
            "truth_blastx_target": parse_blastx(ev_dir / "blastx_target.tsv"),
            "truth_blastx_comp": parse_blastx(ev_dir / "blastx_comp.tsv"),
            "truth_orfs": orfs,
            "position_locks": {
                "det": load_json(pos_dir / "GS_DETERMINISTIC_V4_1.json"),
                "qwen": load_json(pos_dir / "GS_AGENTIC_V4_1.json"),
                "exh": load_json(pos_dir / "GS_EXHAUSTIVE_V4_1.json"),
            },
            "sol_lock": sol_lock_obj,
            "runs": {
                "GS_DETERMINISTIC_V4_1": extract_arm(run_root / "GS_DETERMINISTIC_V4_1"),
                "GS_AGENTIC_V4_1": extract_arm(run_root / "GS_AGENTIC_V4_1"),
                "GS_EXHAUSTIVE_V4_1": extract_arm(run_root / "GS_EXHAUSTIVE_V4_1"),
                "SOL": extract_arm(sol_run),
            },
        }
        (OUT / f"position_{pos:02d}_{rec['case_id']}.json").write_text(
            json.dumps(cases[str(pos)], indent=2, default=str) + "\n", encoding="utf-8"
        )
    (OUT / "all_error_cases.json").write_text(json.dumps(cases, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "n": len(cases), "positions": sorted(int(x) for x in cases)}, indent=2))


if __name__ == "__main__":
    main()
