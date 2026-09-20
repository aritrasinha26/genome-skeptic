#!/usr/bin/env python3
"""Assign D12 independent external truth. Does not read system predictions for labels.

Does not modify V3, regenerate predictions, or access D20 truth/outputs.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import unblind_d8_external_truth as d8  # noqa: E402
from d12_common import EXPECTED_D20_POOL, sha256_file  # noqa: E402

OUT = ROOT / "external_validation_agentic_d12"
CACHE = OUT / "truth_cache"
TRUTH = OUT / "D12_EXTERNAL_TRUTH_LOCKED.json"
POOL = OUT / "D12_CANDIDATE_POOL.json"
D20_POOL = ROOT / "external_validation_agentic_d20" / "candidate_pool_manifest.json"

EXPECTED = {
    "D12_MANIFEST.json": "54b477d3cf8197ffa73d7ffb2e94ffe4a993b861565a3266085d33ae68b0546f",
    "D12_CONVENTIONAL_LOCKED.json": "9cd5657a0e24e877f20f3ad83ec34d495231c1d0f2897336861999d9f4082f57",
    "D12_V5_LOCKED.json": "66652425bbdff574f91c9da19876c02f7a684653a9096f65bd44a95745dfead4",
    "D12_AGENTIC_V3_LOCKED.json": "64a2dd3365805d68f431f487d9aebd7cb685466096d1710d67d962895c3cc25c",
}

ENDPOINT_KIND = {
    "tetA_tetracycline_efflux": "FAMILY_PRESENCE_ABSENCE",
    "rpoB_RNAP_beta": "ORTHOLOGOUS_GENE_PRESENCE_ABSENCE",
    "lacZ_beta_galactosidase": "ORTHOLOGOUS_GENE_PRESENCE_ABSENCE",
    "tuf_EF_Tu": "EXACT_MULTIPLICITY",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pred_polarity(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return "EXECUTION_FAILURE"
    fr = rec.get("final_result") or ""
    if fr == "target_gene_detected":
        return "DETECTED"
    if fr == "target_gene_not_detected":
        return "NOT_DETECTED"
    return fr or "UNKNOWN"


def predicted_multiplicity(rec: dict) -> int | None:
    multi = rec.get("multiplicity") or {}
    if isinstance(multi, dict) and multi.get("number_of_candidate_loci") is not None:
        try:
            return int(multi["number_of_candidate_loci"])
        except (TypeError, ValueError):
            return None
    pol = pred_polarity(rec)
    if pol == "DETECTED":
        return 1
    if pol == "NOT_DETECTED":
        return 0
    return None


def scored_endpoint(rec: dict, target: str) -> str:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return f"EXECUTION_FAILURE ({rec.get('agent_failure')})"
    if target == "tuf_EF_Tu":
        n = predicted_multiplicity(rec)
        missing = not isinstance(rec.get("multiplicity"), dict) or rec.get("multiplicity", {}).get(
            "number_of_candidate_loci"
        ) is None
        tag = " (lock omitted multiplicity; inferred from polarity)" if missing else ""
        return f"MULTIPLICITY={n}{tag}"
    return pred_polarity(rec)


def verify_locks() -> dict:
    out = {}
    for name, expected in EXPECTED.items():
        path = OUT / name
        digest = sha256_file(path)
        if digest != expected:
            raise SystemExit(f"HASH MISMATCH {name} computed={digest} expected={expected}")
        out[name] = digest
    return out


def confirm_prediction_structure() -> dict:
    summary = {}
    for name, system in (
        ("D12_CONVENTIONAL_LOCKED.json", "conventional"),
        ("D12_V5_LOCKED.json", "v5"),
        ("D12_AGENTIC_V3_LOCKED.json", "agentic"),
    ):
        blob = json.loads((OUT / name).read_text(encoding="utf-8"))
        recs = blob.get("predictions") or []
        if len(recs) != 12:
            raise SystemExit(f"{name} has {len(recs)} records, expected 12")
        summary[system] = {
            "n": len(recs),
            "n_ok": sum(1 for r in recs if r.get("ok") is True),
            "n_failures": sum(1 for r in recs if r.get("ok") is False or r.get("agent_failure")),
        }
    return summary


def step1_endpoint_audit() -> dict:
    """Compare locked V5 vs Agentic scored endpoints. Not used for truth assignment."""
    v5 = json.loads((OUT / "D12_V5_LOCKED.json").read_text(encoding="utf-8"))["predictions"]
    ag = json.loads((OUT / "D12_AGENTIC_V3_LOCKED.json").read_text(encoding="utf-8"))["predictions"]
    if len(v5) != 12 or len(ag) != 12:
        raise SystemExit("locked prediction counts are not 12")
    rows = []
    print("==================================================", flush=True)
    print("STEP 1 — TARGET-SPECIFIC SCORED ENDPOINTS", flush=True)
    print("==================================================", flush=True)
    print("position\ttarget\tV5 scored endpoint\tAgentic V3 scored endpoint\tidentical", flush=True)
    for i, (v, a) in enumerate(zip(v5, ag), 1):
        if v.get("assembly_accession") != a.get("assembly_accession") or v.get("target") != a.get("target"):
            raise SystemExit(f"lock order mismatch at position {i}")
        target = v["target"]
        v_ep = scored_endpoint(v, target)
        a_ep = scored_endpoint(a, target)
        identical = v_ep.split(" (lock omitted")[0] == a_ep.split(" (lock omitted")[0]
        rows.append(
            {
                "position": i,
                "assembly_accession": v["assembly_accession"],
                "target": target,
                "endpoint_kind": ENDPOINT_KIND[target],
                "v5_scored_endpoint": v_ep,
                "agentic_scored_endpoint": a_ep,
                "identical": identical,
            }
        )
        print(f"{i}\t{target}\t{v_ep}\t{a_ep}\t{'YES' if identical else 'NO'}", flush=True)
    n_ident = sum(1 for r in rows if r["identical"])
    different = [r for r in rows if not r["identical"]]
    print("", flush=True)
    print("TARGET-SPECIFIC ENDPOINTS IDENTICAL:", flush=True)
    print(f"{n_ident} / 12", flush=True)
    print("", flush=True)
    print("DIFFERENT ENDPOINT CASES:", flush=True)
    if not different:
        print("[]", flush=True)
    else:
        for r in different:
            print(
                f"  pos {r['position']} {r['assembly_accession']} {r['target']}: "
                f"V5={r['v5_scored_endpoint']} Agentic={r['agentic_scored_endpoint']}",
                flush=True,
            )
    print("", flush=True)
    return {"n_identical": n_ident, "rows": rows, "different": different}


def run_phmmer_local(seed_fa: Path, proteome: Path, out_prefix: Path, acc: str | None = None) -> dict:
    tbl = Path(str(out_prefix) + ".tbl")
    dom = Path(str(out_prefix) + ".domtbl")
    if acc and not tbl.exists():
        legacy_tbl = CACHE / f"{acc.split('.')[0]}.tbl"
        legacy_dom = CACHE / f"{acc.split('.')[0]}.domtbl"
        if legacy_tbl.exists() and legacy_dom.exists():
            tbl, dom = legacy_tbl, legacy_dom
    if not (tbl.exists() and dom.exists() and tbl.stat().st_size > 0):
        exe = shutil.which("phmmer")
        if exe:
            cmd = [
                exe,
                "--tblout",
                str(tbl),
                "--domtblout",
                str(dom),
                "-E",
                "1e-5",
                "--noali",
                str(seed_fa),
                str(proteome),
            ]
        else:
            cmd = [
                "wsl",
                "-e",
                "phmmer",
                "--tblout",
                d8.to_wsl(tbl),
                "--domtblout",
                d8.to_wsl(dom),
                "-E",
                "1e-5",
                "--noali",
                d8.to_wsl(seed_fa),
                d8.to_wsl(proteome),
            ]
        print("phmmer", seed_fa.name, proteome.name, flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"phmmer failed: {proc.stderr[-500:] or proc.stdout[-500:]}")
    return d8.run_phmmer(seed_fa, proteome, out_prefix, acc=acc)


def taxid_from_extracted(extracted: Path) -> int | None:
    hits = list(extracted.rglob("assembly_data_report.jsonl"))
    if not hits:
        return None
    rec = json.loads(hits[0].read_text(encoding="utf-8", errors="replace").splitlines()[0])
    org = rec.get("organism") or {}
    for key in ("taxId", "taxid", "taxonomy_id"):
        val = org.get(key) or rec.get(key)
        if val is not None and str(val).isdigit():
            return int(val)
    return None


def confirm_d20_untouched() -> str:
    if not D20_POOL.exists():
        raise SystemExit("D20 candidate pool missing; exclusion cannot be verified")
    digest = sha256_file(D20_POOL)
    if digest != EXPECTED_D20_POOL:
        raise SystemExit(f"D20 pool hash changed: {digest}")
    return digest


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    d8.CACHE = CACHE
    d8.OUT = OUT
    hashes = verify_locks()
    struct = confirm_prediction_structure()
    d20_sha = confirm_d20_untouched()
    print("LOCK_VERIFIED", json.dumps(hashes, indent=2), flush=True)
    print("STRUCTURAL_COUNTS", json.dumps(struct), flush=True)
    print("D20_POOL_UNTOUCHED", d20_sha, flush=True)
    audit = step1_endpoint_audit()
    (OUT / "D12_ENDPOINT_AUDIT.json").write_text(
        json.dumps(
            {
                "kind": "D12_ENDPOINT_AUDIT",
                "created_utc": utc_now(),
                "lock_hashes_verified": hashes,
                "n_identical": audit["n_identical"],
                "n_cases": 12,
                "rows": audit["rows"],
                "predictions_used_only_for_endpoint_comparison": True,
                "predictions_not_used_for_truth": True,
                "d20_touched": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("==================================================", flush=True)
    print("STEP 2 — INDEPENDENT TRUTH ASSIGNMENT", flush=True)
    print("==================================================", flush=True)
    print("TRUTH_ASSIGNMENT_START predictions_not_used=True", flush=True)

    manifest = json.loads((OUT / "D12_MANIFEST.json").read_text(encoding="utf-8"))
    cases = sorted(manifest["cases"], key=lambda r: r["execution_position"])
    if len(cases) != 12:
        raise SystemExit(f"manifest cases {len(cases)}")
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    pool_by_acc = {c["assembly_accession"]: c for c in pool.get("candidates") or []}

    for target, seed in d8.SEEDS.items():
        if seed["gene_id"] is None:
            seed["gene_id"] = d8.gene_id_for_protein(seed["protein_id"])
            print(f"seed_gene_id {target} -> {seed['gene_id']}", flush=True)
        d8.download_seed_faa(seed["protein_id"])

    labels = []
    gff_cache: dict[str, list[dict]] = {}
    gbff_cache: dict[str, dict] = {}
    header_cache: dict[str, dict] = {}
    ftp_cache: dict[str, dict] = {}
    proteome_faa: dict[str, Path] = {}

    unique_acc = list(dict.fromkeys(c["assembly_accession"] for c in cases))
    for acc in unique_acc:
        rec = next(c for c in cases if c["assembly_accession"] == acc)
        pool_rec = pool_by_acc.get(acc) or {}
        zpath = d8.download_annotation_zip(acc)
        extracted = d8.extract_zip(zpath, CACHE / f"{acc}_extracted")
        gff = d8.find_first(extracted, (".gff", ".gff.gz", ".gff3", ".gff3.gz"))
        gbff = d8.find_first(extracted, (".gbff", ".gbff.gz", ".gbk", ".gbk.gz"))
        faa = d8.find_first(extracted, (".faa", ".faa.gz", ".fasta", ".fasta.gz"))
        print(acc, "gff", gff, "gbff", gbff, "faa", faa, flush=True)
        if gff is None or faa is None:
            raise SystemExit(f"missing annotation files for {acc}")
        gff_cache[acc] = d8.parse_gff_all_cds(gff)
        gbff_cache[acc] = d8.parse_gbff_amr(gbff) if gbff else {}
        header_cache[acc] = d8.parse_fasta_headers(faa)
        ftp_cache[acc] = d8.ftp_amrfinder_report(pool_rec.get("ftp_path") or rec.get("ftp_path") or "", acc)
        proteome_faa[acc] = faa
        taxid = rec.get("taxonomy_id") or pool_rec.get("taxonomy_id") or taxid_from_extracted(extracted)
        rec["taxonomy_id"] = taxid
        rec["ftp_path"] = rec.get("ftp_path") or pool_rec.get("ftp_path")
        print(acc, "taxonomy_id", taxid, flush=True)

    needed_seeds: dict[str, set[str]] = {}
    for case in cases:
        if case["target"] in d8.SEEDS:
            needed_seeds.setdefault(case["assembly_accession"], set()).add(case["target"])

    phmmer_results: dict[tuple[str, str], dict] = {}
    for acc, targets in needed_seeds.items():
        faa = proteome_faa[acc]
        for target in sorted(targets):
            seed_fa = CACHE / f"{d8.SEEDS[target]['protein_id']}.faa"
            prefix = CACHE / f"{acc}_{target}_phmmer"
            phmmer_results[(acc, target)] = run_phmmer_local(seed_fa, faa, prefix, acc=acc)

    for case in cases:
        acc = case["assembly_accession"]
        target = case["target"]
        if case.get("taxonomy_id") is None:
            raise SystemExit(f"missing taxonomy_id for {acc}")
        print(f"ASSIGN pos={case['execution_position']} {acc} {target}", flush=True)
        if target == "tetA_tetracycline_efflux":
            labels.append(d8.assign_tet(case, gff_cache[acc], gbff_cache[acc], ftp_cache[acc]))
        else:
            labels.append(
                d8.assign_ortholog(
                    case,
                    target,
                    gff_cache[acc],
                    phmmer_results[(acc, target)],
                    header_cache[acc],
                )
            )

    labels.sort(key=lambda r: r["execution_position"])
    if [r["execution_position"] for r in labels] != list(range(1, 13)):
        raise SystemExit("positions not 1-12")
    payload = {
        "kind": "D12_EXTERNAL_TRUTH_LOCKED",
        "cohort": "V3_D12_EXTERNAL",
        "created_utc": utc_now(),
        "predictions_consulted": False,
        "d20_touched": False,
        "d20_candidate_pool_sha256": d20_sha,
        "lock_hashes_verified_before_truth": hashes,
        "structural_counts_before_truth": struct,
        "endpoint_audit_n_identical_before_truth": audit["n_identical"],
        "frozen_family_tet_positives": ["tet(A)", "tet(B)"],
        "tetC_not_a_frozen_member": True,
        "tuf_seed_used": "NP_417798.1 / gene_id 947838 (authentic tufA); NP_418240.1 not used",
        "n_cases": 12,
        "cases": labels,
    }
    tmp = OUT / "D12_EXTERNAL_TRUTH_LOCKED.json.tmp"
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(TRUTH)
    digest = sha256_file(TRUTH)
    sidecar = OUT / "D12_EXTERNAL_TRUTH_LOCKED.json.sha256.json"
    sidecar.write_text(
        json.dumps(
            {
                "file": "D12_EXTERNAL_TRUTH_LOCKED.json",
                "sha256": digest,
                "hashed_utc": utc_now(),
                "hashed_before_prediction_join": True,
                "predictions_consulted": False,
                "d20_touched": False,
                "n_cases": 12,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("D12_TRUTH_LOCKED", digest, flush=True)
    for r in labels:
        print(
            r["execution_position"],
            r["assembly_accession"],
            r["target"],
            r.get("truth_status"),
            r.get("truth"),
            (r.get("short_rationale") or "")[:220],
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
