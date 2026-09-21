#!/usr/bin/env python3
"""M60 Phase D–G: eligible pool, routine/challenge selection, cohort freeze.

Does not run manuscript study arms (Conventional, AMRFinderPlus, PGAP comparator,
GS-Agentic, GS-Exhaustive). Does not open truth or D20 results.
Challenge prescreen uses frozen V4.1 deterministic instruments only, as a
selection device for the pre-registered ambiguity score.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from genome_skeptic.config import Settings  # noqa: E402
from genome_skeptic.families import load_family  # noqa: E402
from genome_skeptic.manuscript.arms import run_gs_deterministic_v4_1  # noqa: E402
from lock_cohort_d20_final import score_case  # noqa: E402
from select_and_download_d20 import (  # noqa: E402
    COMPLETE_LEVELS,
    DRAFT_LEVELS,
    ensure_lineage,
    ensure_summary,
    fetch_genome_fasta,
    genus_of,
    load_lineage,
    load_rows,
    parse_date,
    quality_bucket,
    sanitize_fasta,
    sha256_file,
    taxonomy_for,
)

SEED = "20260920"
RELEASE_CUTOFF = date(2025, 1, 1)
TARGETS = ["tetA_tetracycline_efflux", "rpoB_RNAP_beta"]
N_ROUTINE_COMPLETE = 8
N_ROUTINE_DRAFT = 7
N_CHALLENGE_POOL_COMPLETE = 12
N_CHALLENGE_POOL_DRAFT = 12
N_FINAL = 15
EXPECTED_EXCLUSION = "7fe225d0bc779e8b887a3f7980141272f85f3cc8c58c309f99118ff91fe4ef55"
EXPECTED_PROTOCOL = "30de5efc92d1b2b0db9de0db6f8f98b965397b6adac17052603b3ab44b74df4f"
EXPECTED_MANIFEST = "97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b"
EXPECTED_CORE = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"

OUT = ROOT / "manuscript_benchmark"
EXCL_PATH = OUT / "M60_EXCLUSION_MANIFEST.json"
LINUX_WORK = Path("/home/aritr/m60_work") if Path("/home/aritr").exists() else OUT / "m60_work"
WORK = LINUX_WORK
FASTA_DIR = WORK / "fasta"
PRESCREEN_DIR = WORK / "challenge_prescreen"
CACHE_NOTE = "RefSeq metadata cache may reuse NCBI files; D20 prediction/result files are not read."

ACC_RE = re.compile(r"^(?:GCF|GCA)_\d+(?:\.\d+)?$", re.I)
NUC_RE = re.compile(r"^(?:NC|NZ|NM|NP|WP|YP)_\d+(?:\.\d+)?$", re.I)

D8_MANIFEST = ROOT / "external_validation_agentic_d8" / "D8_MANIFEST.json"
D12_MANIFEST = ROOT / "external_validation_agentic_d12" / "D12_MANIFEST.json"
D12_POOL = ROOT / "external_validation_agentic_d12" / "D12_CANDIDATE_POOL.json"
D20_POOL = ROOT / "external_validation_agentic_d20" / "candidate_pool_manifest.json"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sha256_file(path)


def write_sha_sidecar(path: Path, extra: dict | None = None) -> str:
    digest = sha256_file(path)
    try:
        rel = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel = str(path)
    blob = {"path": rel, "sha256": digest, "hashed_utc": utcnow()}
    if extra:
        blob.update(extra)
    Path(str(path) + ".sha256.json").write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")
    return digest


def routine_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"M60_ROUTINE|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def challenge_pool_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"M60_CHALLENGE_POOL|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def tie_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"M60|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def execution_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"M60_EXECUTION|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def walk_accessions(node, into: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"assembly_accession", "accession", "genome_accession"} and isinstance(value, str) and ACC_RE.match(value):
                into.add(value)
                into.add(value.split(".")[0])
            else:
                walk_accessions(value, into)
    elif isinstance(node, list):
        for item in node:
            walk_accessions(item, into)


def load_exclusion() -> dict:
    digest = sha256_file(EXCL_PATH)
    if digest != EXPECTED_EXCLUSION:
        raise SystemExit(f"exclusion SHA256 mismatch: {digest}")
    payload = json.loads(EXCL_PATH.read_text(encoding="utf-8"))
    blocked_acc: set[str] = set()
    blocked_nuc: set[str] = set()
    blocked_org_exact: set[str] = set()
    blocked_org_sub: list[str] = []
    reason_index: dict[str, dict] = {}
    for row in payload.get("excluded") or []:
        ident = str(row.get("accession") or "").strip()
        if not ident:
            continue
        rec = {"identifier": ident, "sources": list(row.get("sources") or []), "reasons": list(row.get("reasons") or [])}
        reason_index[ident] = rec
        if ACC_RE.match(ident):
            blocked_acc.add(ident)
            blocked_acc.add(ident.split(".")[0])
        elif NUC_RE.match(ident):
            blocked_nuc.add(ident)
        else:
            blocked_org_exact.add(ident.lower())
            if len(ident) >= 10:
                blocked_org_sub.append(ident.lower())
    return {
        "payload": payload,
        "sha256": digest,
        "blocked_acc": blocked_acc,
        "blocked_nuc": blocked_nuc,
        "blocked_org_exact": blocked_org_exact,
        "blocked_org_sub": blocked_org_sub,
        "reason_index": reason_index,
        "n_excluded": payload.get("n_excluded"),
    }


def exclusion_hit(row: dict, excl: dict) -> tuple[bool, str, str]:
    acc = row.get("assembly_accession") or ""
    stem = acc.split(".")[0]
    if acc in excl["blocked_acc"] or stem in excl["blocked_acc"]:
        rec = excl["reason_index"].get(acc) or excl["reason_index"].get(stem) or {}
        return True, "exclusion_manifest_accession", (rec.get("reasons") or ["excluded_accession"])[0]
    paired = row.get("gbrs_paired_asm") or ""
    if paired in excl["blocked_acc"] or paired.split(".")[0] in excl["blocked_acc"]:
        return True, "exclusion_manifest_paired_assembly", "paired_assembly_in_exclusion_manifest"
    organism = (row.get("organism_name") or "").strip()
    org_l = organism.lower()
    if org_l in excl["blocked_org_exact"]:
        rec = excl["reason_index"].get(organism) or {}
        return True, "exclusion_manifest_organism", (rec.get("reasons") or ["family_or_reference_source_organism"])[0]
    for marker in excl["blocked_org_sub"]:
        if marker in org_l:
            return True, "exclusion_manifest_organism_substring", marker
    blob = " ".join(str(row.get(k) or "") for k in ("assembly_accession", "gbrs_paired_asm", "asm_name", "organism_name", "ftp_path"))
    for nuc in excl["blocked_nuc"]:
        if nuc in blob:
            return True, "exclusion_manifest_nucleotide", nuc
    return False, "", ""


def quality_ok(row: dict) -> tuple[bool, str]:
    acc = row.get("assembly_accession") or ""
    if not acc.startswith("GCF_"):
        return False, "not_refseq_gcf"
    if (row.get("version_status") or "") != "latest":
        return False, "not_latest"
    excl = (row.get("excluded_from_refseq") or "").strip()
    if excl and excl.lower() not in {"na", "n/a"}:
        return False, "excluded_from_refseq"
    if (row.get("genome_rep") or "") != "Full":
        return False, "not_full_genome_rep"
    if (row.get("assembly_level") or "") not in COMPLETE_LEVELS | DRAFT_LEVELS:
        return False, "assembly_level_ineligible"
    rel = parse_date(row.get("seq_rel_date") or "")
    if rel is None or rel < RELEASE_CUTOFF:
        return False, "before_freshness_cutoff_2025-01-01"
    genus = genus_of(row.get("organism_name") or "")
    if not genus or genus.lower() in {"bacterium", "bacteria", "uncultured"}:
        return False, "unnamed_or_uninformative_genus"
    return True, ""


def metadata_record(row: dict, tax: dict) -> dict:
    n50_raw = row.get("contig_n50") or row.get("scaffold_n50") or ""
    return {
        "accession": row["assembly_accession"],
        "organism": row.get("organism_name"),
        "genus": tax.get("genus"),
        "species": tax.get("species"),
        "taxonomy": {
            "taxonomy_id": tax.get("taxonomy_id"),
            "species_taxid": tax.get("species_taxid"),
            "family": tax.get("family"),
            "order": tax.get("order"),
            "class": tax.get("class"),
            "phylum": tax.get("phylum"),
            "domain": tax.get("domain"),
        },
        "assembly_level": row.get("assembly_level"),
        "assembly_quality": quality_bucket(row.get("assembly_level") or ""),
        "refseq_status": row.get("version_status"),
        "refseq_category": row.get("refseq_category") or None,
        "genome_size": int(row["genome_size"]) if (row.get("genome_size") or "").isdigit() else None,
        "contig_count": int(row["contig_count"]) if (row.get("contig_count") or "").isdigit() else None,
        "n50": int(n50_raw) if str(n50_raw).isdigit() else None,
        "release_date": row.get("seq_rel_date"),
        "seq_rel_date": row.get("seq_rel_date"),
        "asm_submit_date": row.get("asm_submit_date") or None,
        "ftp_path": row.get("ftp_path") or None,
        "annotations_inspected": False,
        "truth_opened": False,
        "predictions_run": False,
    }


def species_key(tax: dict) -> str:
    if tax.get("species_taxid"):
        return f"taxid:{tax['species_taxid']}"
    return f"name:{(tax.get('species') or '').lower()}"


def fill_stratum(
    annotated: list[tuple[dict, dict]],
    target: str,
    levels: set[str],
    n: int,
    hash_fn,
    used_acc: set[str],
    used_species: set[str],
    used_genera: set[str],
    prefer_avoid_genera: set[str] | None = None,
) -> list[tuple[dict, dict]]:
    ranked = sorted(
        ((row, tax) for row, tax in annotated if (row.get("assembly_level") or "") in levels),
        key=lambda rt: (hash_fn(target, rt[0]["assembly_accession"]), rt[0]["assembly_accession"]),
    )
    picked: list[tuple[dict, dict]] = []
    avoid = prefer_avoid_genera or set()

    def accept(row: dict, tax: dict, require_new_genus: bool, avoid_prior: bool) -> bool:
        acc = row["assembly_accession"]
        if acc in used_acc or acc.split(".")[0] in used_acc:
            return False
        if species_key(tax) in used_species:
            return False
        if require_new_genus and tax["genus"] in used_genera:
            return False
        if avoid_prior and tax["genus"] in avoid:
            return False
        return True

    def drain(require_new_genus: bool, avoid_prior: bool) -> None:
        for row, tax in ranked:
            if len(picked) >= n:
                return
            if not accept(row, tax, require_new_genus, avoid_prior):
                continue
            used_acc.add(row["assembly_accession"])
            used_acc.add(row["assembly_accession"].split(".")[0])
            used_species.add(species_key(tax))
            used_genera.add(tax["genus"])
            picked.append((row, tax))

    drain(True, True)
    drain(True, False)
    if len(picked) < n:
        raise SystemExit(f"could not fill {target} levels={sorted(levels)} need={n} got={len(picked)} with unique genus")
    return picked


def write_target_fa(dest: Path, target: str) -> None:
    fam = load_family(target)
    if fam is None or not fam.members:
        raise SystemExit(f"missing frozen family {target}")
    member = max(fam.members, key=lambda m: len(m.sequence or ""))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        f">{target} target_type=gene_orthologue family={target} length_aa={len(member.sequence or '')}\n{member.sequence}\n",
        encoding="utf-8",
    )


def download_solver_fasta(acc: str, ftp_path: str) -> dict:
    orig = FASTA_DIR / "original" / f"{acc}.fna"
    solver = FASTA_DIR / "solver" / f"{acc}.fna"
    orig.parent.mkdir(parents=True, exist_ok=True)
    solver.parent.mkdir(parents=True, exist_ok=True)
    if orig.exists() and orig.stat().st_size > 1000 and solver.exists() and solver.stat().st_size > 1000:
        return {
            "original_fasta": str(orig),
            "solver_fasta": str(solver),
            "fasta_sha256": sha256_file(solver),
            "original_fasta_sha256": sha256_file(orig),
            "reused": True,
        }
    data, source = fetch_genome_fasta(acc, ftp_path)
    text = data.decode("utf-8", errors="replace")
    orig.write_text(text, encoding="utf-8")
    sanitized = sanitize_fasta(text)
    if sanitized.count(">") < 1:
        raise RuntimeError("sanitized fasta empty")
    solver.write_text(sanitized, encoding="utf-8")
    return {
        "original_fasta": str(orig),
        "solver_fasta": str(solver),
        "fasta_sha256": sha256_file(solver),
        "original_fasta_sha256": sha256_file(orig),
        "fasta_source": source,
        "reused": False,
        "headers_sanitized": True,
    }


def snapshot_from_outdir(out_dir: Path, target: str, seconds: float) -> dict:
    claims = load_json(out_dir / "claims.json") or []
    claim = next((c for c in claims if target in str(c.get("claim_id") or "")), None)
    if claim is None and claims:
        claim = claims[0]
    fam = load_json(out_dir / "family" / target / "family_evidence.json") or {}
    recon = fam.get("reconstruction") or {}
    multi = recon.get("multiplicity") or fam.get("multiplicity") or {}
    hits = load_json(out_dir / "search" / "gene_search_hits.json") or []
    if isinstance(hits, dict):
        hits = hits.get("hits") or hits.get("records") or []
    locus = load_json(out_dir / "locus_evidence.json") or []
    tests = []
    for t in (claim or {}).get("falsification_tests") or []:
        tests.append({"test_id": t.get("test_id"), "status": t.get("status"), "result": t.get("result")})
    m0_blob = {"target": target, "hits": hits, "family_evidence": fam, "locus_evidence_n": len(locus) if isinstance(locus, list) else None}
    return {
        "target": target,
        "final_result": (claim or {}).get("claim_type"),
        "claim_class": (claim or {}).get("status"),
        "architecture": fam.get("architecture") or (claim or {}).get("architecture_state"),
        "supports_orthologue": fam.get("supports_orthologue"),
        "hits": hits,
        "family_evidence": fam,
        "locus_evidence": locus,
        "multiplicity": multi,
        "competitive_family": recon.get("competitive_family") or fam.get("competitive_family") or {},
        "falsification_tests": tests,
        "m0_hash": sha256_text(json.dumps(m0_blob, sort_keys=True, default=str)),
        "runtime_seconds": seconds,
        "prescreen_is_selection_device_only": True,
        "manuscript_arm_result": False,
        "truth_opened": False,
    }


def run_prescreen(acc: str, target: str, solver_fasta: Path, settings: Settings) -> dict:
    case_dir = PRESCREEN_DIR / acc / target
    locked = case_dir / "v41_deterministic_prescreen.json"
    if locked.exists() and locked.stat().st_size > 50:
        return json.loads(locked.read_text(encoding="utf-8"))
    case_dir.mkdir(parents=True, exist_ok=True)
    target_fa = case_dir / "target.fa"
    write_target_fa(target_fa, target)
    empty_refs = WORK / "references.yaml"
    if not empty_refs.exists():
        empty_refs.write_text("references: []\n", encoding="utf-8")
    out_dir = case_dir / "gs_deterministic_prescreen"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    t0 = time.perf_counter()
    run_gs_deterministic_v4_1(
        Path(solver_fasta),
        target_fa,
        out_dir,
        settings,
        references=empty_refs,
        declared_organism=None,
        query_ids=[target],
    )
    seconds = time.perf_counter() - t0
    snap = snapshot_from_outdir(out_dir, target, seconds)
    locked.write_text(json.dumps(snap, indent=2, default=str) + "\n", encoding="utf-8")
    return snap


def overlap_accessions() -> dict[str, set[str]]:
    out = {"D8": set(), "D12": set(), "D12_candidate_pool": set(), "D20_candidate_pool": set()}
    walk_accessions(load_json(D8_MANIFEST) or {}, out["D8"])
    walk_accessions(load_json(D12_MANIFEST) or {}, out["D12"])
    walk_accessions(load_json(D12_POOL) or {}, out["D12_candidate_pool"])
    walk_accessions(load_json(D20_POOL) or {}, out["D20_candidate_pool"])
    return out


def main() -> int:
    if not sys.platform.startswith("linux"):
        raise SystemExit("M60 selection must run in the WSL/Linux production environment")
    protocol_sha = sha256_file(OUT / "M60_PROTOCOL.md")
    if protocol_sha != EXPECTED_PROTOCOL:
        raise SystemExit(f"original protocol SHA changed: {protocol_sha}")
    freeze_sha = sha256_file(OUT / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json")
    if freeze_sha != EXPECTED_MANIFEST:
        raise SystemExit(f"freeze manifest SHA changed: {freeze_sha}")
    env_path = OUT / "M60_ENVIRONMENT.json"
    env = load_json(env_path)
    if not env or not env.get("production_environment_ready"):
        raise SystemExit("production environment not ready; run scripts/m60_env_preflight.py first")
    if env.get("freeze_verification", {}).get("scientific_core_hash") != EXPECTED_CORE:
        raise SystemExit("scientific core hash mismatch in environment record")

    excl = load_exclusion()
    print("EXCLUSION_OK", excl["sha256"], "n=", excl["n_excluded"], flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    summary = ensure_summary()
    lineage = load_lineage(ensure_lineage())
    raw_rows = load_rows(summary)
    print(f"refseq_rows {len(raw_rows)} cache_note={CACHE_NOTE}", flush=True)

    reason_counts: Counter[str] = Counter()
    eligible_annotated: list[tuple[dict, dict]] = []
    for row in raw_rows:
        ok, why = quality_ok(row)
        if not ok:
            reason_counts[why] += 1
            continue
        hit, hit_kind, hit_detail = exclusion_hit(row, excl)
        if hit:
            reason_counts[f"{hit_kind}:{hit_detail}"] += 1
            continue
        tax = taxonomy_for(row, lineage)
        if not tax.get("genus") or not tax.get("species"):
            reason_counts["incomplete_taxonomy"] += 1
            continue
        eligible_annotated.append((row, tax))
    print(f"eligible {len(eligible_annotated)}", flush=True)

    pool_records = [metadata_record(row, tax) for row, tax in eligible_annotated]
    pool_path = OUT / "M60_ELIGIBLE_POOL.json"
    pool_payload = {
        "kind": "M60_ELIGIBLE_POOL",
        "created_utc": utcnow(),
        "seed": SEED,
        "source": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/assembly_summary.txt",
        "lineage_source": "NCBI new_taxdump rankedlineage.dmp",
        "exclusion_manifest_sha256": excl["sha256"],
        "freshness_cutoff": str(RELEASE_CUTOFF),
        "n_refseq_rows_scanned": len(raw_rows),
        "n_eligible": len(pool_records),
        "exclusion_reason_counts": dict(reason_counts),
        "truth_opened": False,
        "predictions_run": False,
        "d20_results_opened": False,
        "gene_content_used": False,
        "records": pool_records,
    }
    pool_sha = write_json(pool_path, pool_payload)
    write_sha_sidecar(pool_path, {"n_eligible": len(pool_records)})
    print("ELIGIBLE_POOL_SHA256", pool_sha, flush=True)

    used_acc: set[str] = set()
    used_species: set[str] = set()
    used_genera: set[str] = set()
    routine_cases: list[dict] = []
    for target in TARGETS:
        complete = fill_stratum(
            eligible_annotated, target, COMPLETE_LEVELS, N_ROUTINE_COMPLETE, routine_hash, used_acc, used_species, used_genera
        )
        draft = fill_stratum(
            eligible_annotated, target, DRAFT_LEVELS, N_ROUTINE_DRAFT, routine_hash, used_acc, used_species, used_genera
        )
        for row, tax in complete + draft:
            rec = metadata_record(row, tax)
            rec.update(
                {
                    "case_id": f"M60_{target}_{rec['accession']}",
                    "target": target,
                    "stratum": "routine",
                    "sampling_hash": routine_hash(target, rec["accession"]),
                    "selection_tie_hash": tie_hash(target, rec["accession"]),
                    "execution_hash": execution_hash(target, rec["accession"]),
                    "ambiguity_score": None,
                    "prescreen_run": False,
                }
            )
            routine_cases.append(rec)
        print(f"ROUTINE {target} {N_ROUTINE_COMPLETE}+{N_ROUTINE_DRAFT}", flush=True)

    routine_genera = {c["genus"] for c in routine_cases}
    challenge_pool: list[dict] = []
    for target in TARGETS:
        complete = fill_stratum(
            eligible_annotated,
            target,
            COMPLETE_LEVELS,
            N_CHALLENGE_POOL_COMPLETE,
            challenge_pool_hash,
            used_acc,
            used_species,
            used_genera,
            prefer_avoid_genera=routine_genera,
        )
        draft = fill_stratum(
            eligible_annotated,
            target,
            DRAFT_LEVELS,
            N_CHALLENGE_POOL_DRAFT,
            challenge_pool_hash,
            used_acc,
            used_species,
            used_genera,
            prefer_avoid_genera=routine_genera,
        )
        for row, tax in complete + draft:
            rec = metadata_record(row, tax)
            rec.update(
                {
                    "target": target,
                    "stratum": "challenge_candidate",
                    "sampling_hash": challenge_pool_hash(target, rec["accession"]),
                    "selection_tie_hash": tie_hash(target, rec["accession"]),
                }
            )
            challenge_pool.append(rec)
        print(f"CHALLENGE_POOL {target} {N_CHALLENGE_POOL_COMPLETE}+{N_CHALLENGE_POOL_DRAFT}", flush=True)

    cand_path = OUT / "M60_CHALLENGE_CANDIDATE_POOL.json"
    write_json(
        cand_path,
        {
            "kind": "M60_CHALLENGE_CANDIDATE_POOL",
            "created_utc": utcnow(),
            "n": len(challenge_pool),
            "truth_opened": False,
            "candidates": challenge_pool,
        },
    )

    settings = Settings()
    settings.llm.enabled = False
    settings.project.threads = max(1, min(4, os.cpu_count() or 2))

    scored_candidates: list[dict] = []
    failures: list[dict] = []
    for rec in challenge_pool:
        acc = rec["accession"]
        target = rec["target"]
        print(f"PRESCREEN {acc} {target}", flush=True)
        try:
            fasta = download_solver_fasta(acc, rec.get("ftp_path") or "")
            rec.update({k: fasta[k] for k in fasta if k != "reused"})
            snap = run_prescreen(acc, target, Path(fasta["solver_fasta"]), settings)
            scored = score_case(snap, settings)
            rec = {
                **rec,
                **scored,
                "prescreen_claim_class": snap.get("claim_class"),
                "prescreen_architecture": snap.get("architecture"),
                "prescreen_final_result": snap.get("final_result"),
                "m0_hash": snap.get("m0_hash"),
                "prescreen_runtime_seconds": snap.get("runtime_seconds"),
                "prescreen_ok": True,
            }
            scored_candidates.append(rec)
            print(f"SCORE {acc} {target} {rec['ambiguity_score']}", flush=True)
        except Exception as exc:
            tb = traceback.format_exc()
            failures.append({"accession": acc, "target": target, "error": f"{type(exc).__name__}: {exc}", "traceback": tb})
            (PRESCREEN_DIR / acc / target).mkdir(parents=True, exist_ok=True)
            (PRESCREEN_DIR / acc / target / "failure.json").write_text(
                json.dumps(failures[-1], indent=2) + "\n", encoding="utf-8"
            )
            print(f"FAIL {acc} {target} {exc}", flush=True)
            continue

    amb_path = OUT / "M60_CHALLENGE_AMBIGUITY_SCORES.json"
    write_json(
        amb_path,
        {
            "kind": "M60_CHALLENGE_AMBIGUITY_SCORES",
            "created_utc": utcnow(),
            "score_source": "scripts/lock_cohort_d20_final.py:score_case",
            "d20_results_opened": False,
            "truth_opened": False,
            "n_ok": len(scored_candidates),
            "n_fail": len(failures),
            "failures": [{"accession": f["accession"], "target": f["target"], "error": f["error"]} for f in failures],
            "cases": [
                {
                    "accession": c["accession"],
                    "target": c["target"],
                    "genus": c.get("genus"),
                    "assembly_quality": c.get("assembly_quality"),
                    "ambiguity_score": c["ambiguity_score"],
                    "components": c["components"],
                    "selection_tie_hash": c["selection_tie_hash"],
                    "prescreen_claim_class": c.get("prescreen_claim_class"),
                    "prescreen_architecture": c.get("prescreen_architecture"),
                }
                for c in scored_candidates
            ],
        },
    )

    challenge_selected: list[dict] = []
    by_target: dict[str, list[dict]] = defaultdict(list)
    for rec in scored_candidates:
        by_target[rec["target"]].append(rec)
    challenge_genera = set()
    for target in TARGETS:
        ranked = sorted(
            by_target[target],
            key=lambda c: (-int(c["ambiguity_score"]), c["selection_tie_hash"], c["accession"]),
        )
        picked: list[dict] = []

        def take(quality: str | None, n: int) -> None:
            for cand in ranked:
                if len([p for p in picked if quality is None or p.get("assembly_quality") == quality]) >= n and quality is not None:
                    continue
                if cand["accession"] in {p["accession"] for p in picked}:
                    continue
                if cand["genus"] in challenge_genera or cand["genus"] in routine_genera:
                    continue
                if quality is not None and cand.get("assembly_quality") != quality:
                    continue
                cand = dict(cand)
                cand["stratum"] = "challenge"
                cand["selection_rank"] = len(picked) + 1
                cand["case_id"] = f"M60_{target}_{cand['accession']}"
                cand["execution_hash"] = execution_hash(target, cand["accession"])
                cand["prescreen_run"] = True
                picked.append(cand)
                challenge_genera.add(cand["genus"])
                if len(picked) >= N_FINAL:
                    return

        take("complete_or_chromosome", 8)
        take("scaffold_or_contig", 7)
        if len(picked) < N_FINAL:
            take(None, N_FINAL)
        if len(picked) < N_FINAL:
            raise SystemExit(f"could not select {N_FINAL} {target} challenge cases; got {len(picked)}")
        challenge_selected.extend(picked[:N_FINAL])
        print(f"CHALLENGE_SELECTED {target} {len(picked[:N_FINAL])}", flush=True)

    all_cases = routine_cases + challenge_selected
    all_cases.sort(key=lambda c: (execution_hash(c["target"], c["accession"]), c["accession"]))
    for i, rec in enumerate(all_cases, start=1):
        rec["execution_position"] = i

    ov = overlap_accessions()
    accs = [c["accession"] for c in all_cases]
    overlap_hits = []
    for rec in all_cases:
        acc = rec["accession"]
        stem = acc.split(".")[0]
        for label, blocked in ov.items():
            if acc in blocked or stem in blocked:
                overlap_hits.append({"accession": acc, "overlap": label})
        hit, kind, detail = exclusion_hit(
            {"assembly_accession": acc, "organism_name": rec.get("organism"), "ftp_path": rec.get("ftp_path"), "gbrs_paired_asm": "", "asm_name": ""},
            excl,
        )
        if hit:
            overlap_hits.append({"accession": acc, "overlap": "exclusion_manifest", "kind": kind, "detail": detail})
    if len(accs) != len(set(accs)):
        overlap_hits.append({"overlap": "duplicate_accession_within_m60"})
    genus_counts = Counter(c["genus"] for c in all_cases)
    dominant = [g for g, n in genus_counts.items() if n > 1]
    counts = {
        "tetA_routine": sum(1 for c in all_cases if c["target"] == "tetA_tetracycline_efflux" and c["stratum"] == "routine"),
        "tetA_challenge": sum(1 for c in all_cases if c["target"] == "tetA_tetracycline_efflux" and c["stratum"] == "challenge"),
        "rpoB_routine": sum(1 for c in all_cases if c["target"] == "rpoB_RNAP_beta" and c["stratum"] == "routine"),
        "rpoB_challenge": sum(1 for c in all_cases if c["target"] == "rpoB_RNAP_beta" and c["stratum"] == "challenge"),
    }
    if any(v != 15 for v in counts.values()) or len(all_cases) != 60:
        raise SystemExit(f"count failure {counts} n={len(all_cases)}")
    if overlap_hits or dominant:
        raise SystemExit(f"overlap or diversity failure: overlap={overlap_hits} multi_genus={dominant}")

    manifest_cases = []
    for rec in all_cases:
        manifest_cases.append(
            {
                "case_id": rec["case_id"],
                "execution_position": rec["execution_position"],
                "accession": rec["accession"],
                "organism": rec.get("organism"),
                "genus": rec.get("genus"),
                "species": rec.get("species"),
                "taxonomy": rec.get("taxonomy"),
                "assembly_level": rec.get("assembly_level"),
                "assembly_quality": rec.get("assembly_quality"),
                "refseq_status": rec.get("refseq_status"),
                "genome_size": rec.get("genome_size"),
                "release_date": rec.get("release_date"),
                "target": rec["target"],
                "stratum": rec["stratum"],
                "sampling_hash": rec.get("sampling_hash"),
                "selection_tie_hash": rec.get("selection_tie_hash"),
                "execution_hash": rec.get("execution_hash"),
                "ambiguity_score": rec.get("ambiguity_score"),
                "selection_rank": rec.get("selection_rank"),
                "ftp_path": rec.get("ftp_path"),
                "truth_opened": False,
                "predictions_run": False,
                "d20_touched": False,
            }
        )

    manifest = {
        "kind": "M60_COHORT_MANIFEST",
        "created_utc": utcnow(),
        "freeze_id": "GENOME_SKEPTIC_V4_1_MANUSCRIPT",
        "seed": SEED,
        "protocol_original_sha256": EXPECTED_PROTOCOL,
        "protocol_v1_1_path": "manuscript_benchmark/M60_PROTOCOL_V1_1.md",
        "exclusion_manifest_sha256": excl["sha256"],
        "eligible_pool_sha256": pool_sha,
        "n_cases": 60,
        "counts": counts,
        "n_unique_accessions": len(set(accs)),
        "n_unique_genera": len(genus_counts),
        "n_unique_species": len({c.get("species") for c in all_cases}),
        "exclusion_overlap": 0,
        "d8_overlap": 0,
        "d12_overlap": 0,
        "d20_overlap": 0,
        "d20_touched": False,
        "d20_results_opened": False,
        "truth_opened": False,
        "predictions_run": False,
        "manuscript_arms_run": False,
        "comparators_run": False,
        "sampling_algorithm": {
            "routine_hash": 'SHA256("M60_ROUTINE|20260920|<target>|<assembly_accession>")',
            "challenge_pool_hash": 'SHA256("M60_CHALLENGE_POOL|20260920|<target>|<assembly_accession>")',
            "tie_break": 'SHA256("M60|20260920|<target>|<assembly_accession>")',
            "execution_hash": 'SHA256("M60_EXECUTION|20260920|<target>|<assembly_accession>")',
            "routine": "8 complete + 7 draft per target; unique genus/species/accession; metadata only",
            "challenge_pool": "12 complete + 12 draft per target; disjoint from routine; prefer unused genera",
            "challenge_select": "score_case on V4.1 deterministic prescreen; rank by -ambiguity, tie_hash; fill 8 complete + 7 draft",
        },
        "cases": manifest_cases,
    }
    man_json = OUT / "M60_COHORT_MANIFEST.json"
    man_csv = OUT / "M60_COHORT_MANIFEST.csv"
    write_json(man_json, manifest)
    fields = [
        "execution_position",
        "case_id",
        "accession",
        "organism",
        "genus",
        "species",
        "target",
        "stratum",
        "assembly_level",
        "assembly_quality",
        "genome_size",
        "release_date",
        "sampling_hash",
        "selection_tie_hash",
        "execution_hash",
        "ambiguity_score",
        "selection_rank",
    ]
    with man_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for rec in manifest_cases:
            w.writerow(rec)

    audit = OUT / "M60_SELECTION_AUDIT.md"
    phyla = Counter((c.get("taxonomy") or {}).get("phylum") or "unknown" for c in all_cases)
    families = Counter((c.get("taxonomy") or {}).get("family") or "unknown" for c in all_cases)
    audit.write_text(
        "\n".join(
            [
                "# M60 SELECTION AUDIT",
                "",
                f"Created: {utcnow()}",
                "Freeze: GENOME_SKEPTIC_V4_1_MANUSCRIPT",
                f"Seed: {SEED}",
                "",
                "## Counts",
                "",
                f"- tetA routine: {counts['tetA_routine']}",
                f"- tetA challenge: {counts['tetA_challenge']}",
                f"- rpoB routine: {counts['rpoB_routine']}",
                f"- rpoB challenge: {counts['rpoB_challenge']}",
                f"- unique accessions: {len(set(accs))}",
                f"- unique genera: {len(genus_counts)}",
                "",
                "## Sampling algorithm",
                "",
                "- Exclusion manifest applied first.",
                "- Eligible pool: current RefSeq bacteria, GCF latest Full, named genus, seq_rel_date >= 2025-01-01.",
                "- Routine: metadata only. Hash SHA256(\"M60_ROUTINE|20260920|<target>|<acc>\"). 8 complete + 7 draft/target. Unique genus.",
                "- Challenge candidate pool: SHA256(\"M60_CHALLENGE_POOL|20260920|<target>|<acc>\"). 12 complete + 12 draft/target.",
                "- Challenge score: frozen V4.1 deterministic instruments + unmodified score_case. No D20 results opened.",
                "- Challenge lock: higher ambiguity, then SHA256(\"M60|20260920|<target>|<acc>\"). Unique genus. Not selected because Agentic is expected to fix them.",
                "",
                "## Integrity",
                "",
                "- exclusion overlap: 0",
                "- D8 overlap: 0",
                "- D12 overlap: 0",
                "- D20 overlap: 0",
                "- D20 touched: NO",
                "- truth opened: NO",
                "- predictions run (manuscript arms / comparators): NO",
                f"- challenge prescreen failures skipped: {len(failures)}",
                "",
                "## Diversity (phylum)",
                "",
                *[f"- {k}: {v}" for k, v in phyla.most_common()],
                "",
                "## Diversity (family, top 20)",
                "",
                *[f"- {k}: {v}" for k, v in families.most_common(20)],
                "",
                "## Eligible pool",
                "",
                f"- n_eligible: {len(pool_records)}",
                f"- eligible pool SHA256: {pool_sha}",
                "",
                "STOP. Do not run Conventional, AMRFinderPlus, PGAP comparator, or manuscript GS arms yet.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    man_sha = write_sha_sidecar(man_json, {"n_cases": 60})
    csv_sha = write_sha_sidecar(man_csv, {"n_cases": 60})
    audit_sha = write_sha_sidecar(audit, {"n_cases": 60})
    print("M60_COHORT_MANIFEST.json", man_sha, flush=True)
    print("M60_COHORT_MANIFEST.csv", csv_sha, flush=True)
    print("M60_SELECTION_AUDIT.md", audit_sha, flush=True)
    print("EXCLUSION_OVERLAP 0", flush=True)
    print("D20_TOUCHED NO", flush=True)
    print("TRUTH_OPENED NO", flush=True)
    print("PREDICTIONS_RUN NO", flush=True)
    print("STOP", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
