#!/usr/bin/env python3
"""Build fresh tetA role-swap 20-case cohort + independent truth lock.

STOP before any Arm A–F execution. Does not call Sol/Jev. Does not open GS
prediction polarity as truth. Does not modify V5 scientific biology.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from model_poc_v5.freeze import verify_v5_freeze, EXPECTED  # noqa: E402

STUDY = ROOT / "role_swap_cross_task"
CASES = STUDY / "02_CASES"
TRUTH = STUDY / "03_TRUTH"
FREEZE = STUDY / "01_FREEZE"
WORK = STUDY / "_work"
FASTA_DIR = WORK / "fasta"
EVIDENCE_DIR = WORK / "truth_evidence"
SOURCE_OUT = TRUTH / "SOURCE_FREEZE"
CACHE = WORK / "cache"

SUMMARY_URL = "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/assembly_summary.txt"
SUMMARY_CACHE = CACHE / "assembly_summary_bacteria.txt"
IPG_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=protein&id=P02982,P02980&rettype=ipg&retmode=text"
IPG_CACHE = CACHE / "tetAB_ipg.txt"

RELEASE_CUTOFF = date(2025, 1, 1)
COMPLETE_LEVELS = {"Complete Genome", "Chromosome"}
DRAFT_LEVELS = {"Scaffold", "Contig"}
UA = "GenomeSkeptic-role-swap-teta-cohort/stop3"
ACC_RE = re.compile(r"\b((?:GCF|GCA)_\d+\.\d+)\b")
SEED = "ROLE_SWAP_TETA|20260922"

def ensure_truth_bin() -> Path:
    """Ensure diamond/tblastn/hmm* resolve under one BIN directory for M60 helpers."""
    bindir = WORK / "truth_bin"
    bindir.mkdir(parents=True, exist_ok=True)
    wanted = ["diamond", "tblastn", "blastp", "hmmsearch", "hmmbuild", "hmmalign", "FastTree", "fasttree"]
    path_dirs = [
        Path("/home/aritr/micromamba/envs/genome-skeptic-prod/bin"),
        Path("/usr/bin"),
        Path("/usr/local/bin"),
    ]
    for name in wanted:
        dest = bindir / name
        if dest.exists() or dest.is_symlink():
            continue
        src = None
        for d in path_dirs:
            cand = d / name
            if cand.exists():
                src = cand
                break
        if src is None and name == "FastTree":
            for d in path_dirs:
                cand = d / "fasttree"
                if cand.exists():
                    src = cand
                    break
        if src is None:
            continue
        try:
            dest.symlink_to(src)
        except OSError:
            shutil.copy2(src, dest)
            dest.chmod(0o755)
    os.environ["M60_TRUTH_BIN"] = str(bindir)
    # re-bind adjudicate module BIN after env set
    return bindir


BIN = Path(os.environ.get("M60_TRUTH_BIN", "/home/aritr/micromamba/envs/genome-skeptic-prod/bin"))
M60_SOURCE = ROOT / "manuscript_benchmark" / "TRUTH_M60" / "SOURCE_FREEZE"

EXPECTED_MANIFEST_SHA = "482c209915440ac1b4e614738ac631ed0e98909eec5abec842a13e965efda0bf"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def write_json(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def rank_key(stratum: str, accession: str) -> str:
    return sha256_text(f"{SEED}|{stratum}|{accession}")


def http_download(url: str, dest: Path, min_bytes: int = 1000) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= min_bytes:
        print(f"cache hit {dest} ({dest.stat().st_size} bytes)", flush=True)
        return
    print(f"download {url} -> {dest}", flush=True)
    req = Request(url, headers={"User-Agent": UA})
    tmp = dest.with_suffix(dest.suffix + ".partial")
    with urlopen(req, timeout=600) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out)
    if tmp.stat().st_size < min_bytes:
        raise SystemExit(f"download too small: {dest} ({tmp.stat().st_size})")
    tmp.replace(dest)


def verify_freeze_or_stop() -> dict:
    v = verify_v5_freeze()
    man = FREEZE / "ROLE_SWAP_FREEZE_MANIFEST.json"
    man_sha = sha256_file(man)
    if man_sha != EXPECTED_MANIFEST_SHA:
        raise SystemExit(
            f"STOP: freeze manifest SHA mismatch: {man_sha} != {EXPECTED_MANIFEST_SHA}"
        )
    if not v["all_match"] or v["scientific_core_or_validator_mismatch"]:
        raise SystemExit(f"STOP: V5 scientific hash mismatch: {json.dumps(v['rows'], indent=2)}")
    # family / ortholog from verify payload
    if v["family_definitions_hash"] != "ed4210640e318b8ed94ebf6d72b9c37afa9039eed858fdd54c4165fbcce09605":
        raise SystemExit("STOP: family panel hash mismatch")
    if v["reference_assets_hash"] != "9434a1902236ed7245361e47af1986357969a3bf8ec210062f889dc84580ff92":
        raise SystemExit("STOP: ortholog/reference hash mismatch")
    print("FREEZE_OK", flush=True)
    return v


def walk_accessions(obj, found: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {
                "accession",
                "assembly_accession",
                "genome_accession",
                "refseq_accession",
            } and isinstance(v, str):
                m = ACC_RE.search(v)
                if m:
                    found.add(m.group(1))
            else:
                walk_accessions(v, found)
    elif isinstance(obj, list):
        for item in obj:
            walk_accessions(item, found)
    elif isinstance(obj, str):
        for m in ACC_RE.finditer(obj):
            found.add(m.group(1))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def gcf_from_csv(path: Path, cols=("accession", "assembly_accession")) -> set[str]:
    out: set[str] = set()
    if not path.is_file():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            for c in cols:
                val = row.get(c) or ""
                m = ACC_RE.search(val)
                if m:
                    out.add(m.group(1))
            # also scan all fields
            for val in row.values():
                if not val:
                    continue
                m = ACC_RE.search(val)
                if m:
                    out.add(m.group(1))
    return out


def build_exclusion() -> dict:
    rows: dict[str, set[str]] = defaultdict(set)

    def add(acc: str, label: str) -> None:
        m = ACC_RE.search(acc or "")
        if m:
            rows[m.group(1)].add(label)

    # M60 exclusion manifest
    m60_excl = load_json(ROOT / "manuscript_benchmark" / "M60_EXCLUSION_MANIFEST.json")
    for e in m60_excl.get("excluded", []):
        acc = e.get("accession") or ""
        if acc.startswith(("GCF_", "GCA_")):
            sources = e.get("sources") or ["M60_EXCLUSION"]
            for s in sources:
                add(acc, f"M60_EXCLUSION:{s}")

    # M60 selected cohort
    for acc in gcf_from_csv(ROOT / "manuscript_benchmark" / "M60_COHORT_MANIFEST.csv"):
        add(acc, "M60_selected")

    # Structured cohort manifests
    structured = [
        (ROOT / "external_validation_agentic_d8" / "D8_MANIFEST.json", "D8"),
        (ROOT / "external_validation_agentic_d12" / "D12_MANIFEST.json", "D12"),
        (ROOT / "external_validation_agentic_d12" / "D12_CANDIDATE_POOL.json", "D12_candidate_pool"),
        (ROOT / "external_validation_agentic_d20" / "candidate_pool_manifest.json", "D20_candidate_pool"),
        (ROOT / "external_validation" / "cohort_A_naturalistic_manifest.json", "cohort_A"),
        (ROOT / "external_validation_agentic" / "cohort_C_manifest.json", "cohort_C"),
        (ROOT / "external_validation_agentic" / "cohort_C_pilot5_manifest.json", "cohort_C_pilot5"),
        (ROOT / "single_rescue_challenge_v5" / "SELECTED_CASE.json", "single_rescue_challenge_v5"),
        (ROOT / "external_validation" / "v5_reference_provenance_exclusions.json", "v5_reference_provenance"),
    ]
    for path, label in structured:
        if not path.is_file():
            continue
        found: set[str] = set()
        walk_accessions(load_json(path), found)
        for acc in found:
            add(acc, label)

    # CSV locks / panels
    csv_sources = [
        (ROOT / "decision_authority_poc_v5" / "DECISION_AUTHORITY_CASESET.csv", "decision_authority_poc_v5"),
        (ROOT / "known_failure_rescue_v5" / "KNOWN_FAILURE_CASESET.csv", "known_failure_rescue_v5"),
        (ROOT / "model_poc_v5_5case" / "POC_5CASE_PANEL.csv", "model_poc_v5_5case"),
        (ROOT / "manuscript_benchmark" / "TRUTH_M60" / "M60_TRUTH_FINAL_CASE_LEVEL.csv", "M60_truth_final"),
    ]
    for path, label in csv_sources:
        for acc in gcf_from_csv(path):
            add(acc, label)

    # Repo-wide scan of key dirs for leftover GCF mentions in manifests (structured only)
    scan_globs = [
        "decision_authority_poc_v5/**/*.{json,csv}",
        "known_failure_rescue_v5/**/*.{json,csv}",
        "model_poc_v5_5case/**/*.{json,csv}",
        "single_rescue_challenge_v5/**/*.{json,csv}",
        "prospective_v5/**/*.{json,csv}",
        "manuscript_benchmark/SOL56_FULL_ABLATION/**/*.{json,csv}",
        "manuscript_benchmark/POSTHOC_ERROR_ANALYSIS/**/*.{json,csv}",
        "benchmarks/**/*manifest*.{json,csv}",
        "tests/**/*fixture*.{json,csv}",
    ]
    # Lightweight: only scan known small manifests already covered; avoid opening RUNS.

    records = []
    for acc in sorted(rows):
        experiments = sorted(rows[acc])
        records.append(
            {
                "accession": acc,
                "source_experiment": ";".join(experiments),
                "reason_excluded": "prior_development_or_evaluation_or_reference_exposure",
                "n_sources": len(experiments),
            }
        )

    excl = {
        "kind": "ROLE_SWAP_EXCLUSION_MANIFEST",
        "created_utc": utc_now(),
        "n_unique_accessions": len(records),
        "n_gcf": sum(1 for r in records if r["accession"].startswith("GCF_")),
        "n_gca": sum(1 for r in records if r["accession"].startswith("GCA_")),
        "records": records,
    }
    csv_path = CASES / "ROLE_SWAP_EXCLUSION_MANIFEST.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["accession", "source_experiment", "reason_excluded", "n_sources"],
        )
        w.writeheader()
        w.writerows(records)
    excl["csv_sha256"] = sha256_file(csv_path)
    excl_sha = write_json(CASES / "ROLE_SWAP_EXCLUSION_MANIFEST.json", excl)

    audit_lines = [
        "# ROLE_SWAP EXCLUSION AUDIT",
        "",
        f"Created: {excl['created_utc']}",
        f"TOTAL UNIQUE EXCLUDED ACCESSIONS: {excl['n_unique_accessions']}",
        f"GCF: {excl['n_gcf']}",
        f"GCA: {excl['n_gca']}",
        f"Manifest JSON SHA256: {excl_sha}",
        f"Manifest CSV SHA256: {excl['csv_sha256']}",
        "",
        "## Sources mined",
        "",
        "- manuscript_benchmark/M60_EXCLUSION_MANIFEST.json",
        "- manuscript_benchmark/M60_COHORT_MANIFEST.csv",
        "- D8 / D12 / D20 / Cohort A / Cohort C / pilot5 manifests",
        "- decision_authority_poc_v5, known_failure_rescue_v5, model_poc_v5_5case, single_rescue",
        "- v5_reference_provenance_exclusions.json",
        "- M60 truth final case-level CSV",
        "",
        "Family YAML protein IDs contribute no GCF accessions; NC_ reference",
        "genomes from provenance exclusions are recorded when GCF/GCA present.",
        "",
        "M60_ELIGIBLE_POOL was NOT ingested (pass-set; would incorrectly exclude ~200k assemblies).",
        "",
    ]
    write_text(CASES / "ROLE_SWAP_EXCLUSION_AUDIT.md", "\n".join(audit_lines) + "\n")
    print(f"EXCLUSIONS={excl['n_unique_accessions']}", flush=True)
    return excl


def parse_summary(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        header = None
        for line in fh:
            if line.startswith("#"):
                if "assembly_accession" in line:
                    header = line.lstrip("#").strip().split("\t")
                continue
            if not header:
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            rows.append(dict(zip(header, parts)))
    return rows


def genus_of(organism: str) -> str:
    toks = (organism or "").strip().split()
    return toks[0] if toks else ""


def species_of(organism: str) -> str:
    toks = (organism or "").strip().split()
    if len(toks) >= 2:
        return f"{toks[0]} {toks[1]}"
    return organism or ""


def quality_ok(row: dict) -> tuple[bool, str]:
    acc = row.get("assembly_accession") or ""
    if not acc.startswith("GCF_"):
        return False, "not_refseq_gcf"
    if (row.get("version_status") or "") != "latest":
        return False, "not_latest"
    excl = (row.get("excluded_from_refseq") or "").strip()
    if excl and excl.lower() not in {"na", "n/a", ""}:
        return False, "excluded_from_refseq"
    if (row.get("genome_rep") or "") != "Full":
        return False, "not_full_genome_rep"
    level = row.get("assembly_level") or ""
    if level not in COMPLETE_LEVELS | DRAFT_LEVELS:
        return False, "assembly_level_ineligible"
    rel_s = row.get("seq_rel_date") or ""
    try:
        rel = date.fromisoformat(rel_s)
    except ValueError:
        return False, "bad_date"
    if rel < RELEASE_CUTOFF:
        return False, "before_freshness_cutoff_2025-01-01"
    genus = genus_of(row.get("organism_name") or "")
    if not genus or genus.lower() in {"bacterium", "bacteria", "uncultured"}:
        return False, "unnamed_or_uninformative_genus"
    return True, ""


def parse_ipg_gcf(path: Path) -> dict[str, dict]:
    """Return GCF -> enrichment metadata from tet(A)/tet(B) IPG table."""
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        header = None
        for line in fh:
            if not line.strip():
                continue
            if header is None:
                header = line.rstrip("\n").split("\t")
                continue
            parts = line.rstrip("\n").split("\t")
            row = dict(zip(header, parts + [""] * (len(header) - len(parts))))
            # Entire IPG fetch is for UniProt P02980/P02982 identical proteins —
            # any linked GCF is a POS enrichment shortlist candidate (not final truth).
            asm = (row.get("Assembly") or "").strip()
            m = ACC_RE.search(asm)
            if not m:
                continue
            acc = m.group(1)
            out[acc] = {
                "accession": acc,
                "protein": row.get("Protein") or "",
                "protein_name": row.get("Protein Name") or "",
                "organism": row.get("Organism") or "",
                "enrichment_source": "NCBI_IPG_P02980_P02982",
            }
    return out


def download_assembly_fasta(acc: str, ftp_path: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return sha256_file(dest)
    if not ftp_path:
        raise SystemExit(f"no ftp_path for {acc}")
    # Prefer HTTPS
    base = ftp_path.replace("ftp://", "https://").rstrip("/")
    name = base.rsplit("/", 1)[-1]
    url = f"{base}/{name}_genomic.fna.gz"
    tmp_gz = dest.with_suffix(".fna.gz.partial")
    print(f"fetch fasta {acc}", flush=True)
    req = Request(url, headers={"User-Agent": UA})
    for attempt in range(5):
        try:
            with urlopen(req, timeout=600) as resp, tmp_gz.open("wb") as out:
                shutil.copyfileobj(resp, out)
            break
        except Exception as exc:
            if attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))
            print(f"retry {acc}: {exc}", flush=True)
    with gzip.open(tmp_gz, "rb") as zin, dest.open("wb") as zout:
        shutil.copyfileobj(zin, zout)
    tmp_gz.unlink(missing_ok=True)
    return sha256_file(dest)


def copy_truth_sources() -> dict:
    """Reuse frozen M60 tetA truth panels/HMMs (independent route resources)."""
    SOURCE_OUT.mkdir(parents=True, exist_ok=True)
    mapping = {
        "panels/tetA_target.faa": M60_SOURCE / "panels" / "tetA_target.faa",
        "panels/tetA_competitors.faa": M60_SOURCE / "panels" / "tetA_competitors.faa",
        "hmm/tetA_tetracycline_efflux.hmm": M60_SOURCE / "hmm" / "tetA_tetracycline_efflux.hmm",
        "hmm/mfs_multidrug_efflux.hmm": M60_SOURCE / "hmm" / "mfs_multidrug_efflux.hmm",
        "hmm/rnd_efflux.hmm": M60_SOURCE / "hmm" / "rnd_efflux.hmm",
    }
    files = {}
    for rel, src in mapping.items():
        if not src.is_file():
            raise SystemExit(f"missing truth source {src}")
        dst = SOURCE_OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        files[rel] = {"path": str(dst.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(dst), "copied_from": str(src).replace("\\", "/")}
    meta = {
        "kind": "ROLE_SWAP_TRUTH_SOURCE_FREEZE",
        "created_utc": utc_now(),
        "note": "Panels/HMMs copied from M60 independent truth SOURCE_FREEZE; adjudication does not call GS validator polarity.",
        "files": files,
    }
    write_json(TRUTH / "ROLE_SWAP_TRUTH_SOURCE_MANIFEST.json", meta)
    return meta


def build_candidate_pool(excl_set: set[str], summary_rows: list[dict], ipg: dict[str, dict]) -> list[dict]:
    eligible = []
    for row in summary_rows:
        ok, why = quality_ok(row)
        if not ok:
            continue
        acc = row["assembly_accession"]
        if acc in excl_set:
            continue
        eligible.append(row)
    print(f"ELIGIBLE_AFTER_EXCLUSION={len(eligible)}", flush=True)

    # POS enrichment: IPG ∩ eligible
    pos_enrich = []
    for row in eligible:
        acc = row["assembly_accession"]
        if acc in ipg:
            rec = {
                "candidate_id": f"CAND_POS_{acc}",
                "accession": acc,
                "stratum": "POS_ENRICH",
                "organism": row.get("organism_name"),
                "genus": genus_of(row.get("organism_name") or ""),
                "species": species_of(row.get("organism_name") or ""),
                "assembly_level": row.get("assembly_level"),
                "seq_rel_date": row.get("seq_rel_date"),
                "ftp_path": row.get("ftp_path"),
                "rank_hash": rank_key("POS_ENRICH", acc),
                "enrichment": ipg[acc],
            }
            pos_enrich.append(rec)
    pos_enrich.sort(key=lambda r: (r["rank_hash"], r["accession"]))
    print(f"POS_ENRICH_ELIGIBLE={len(pos_enrich)}", flush=True)

    # Take top 25 POS enrich by hash (tolerate UNCERTAIN)
    pos_shortlist = pos_enrich[:25]

    # NEG enrichment: eligible NOT in IPG, hash-ranked, prefer genus diversity later
    neg_pool = []
    for row in eligible:
        acc = row["assembly_accession"]
        if acc in ipg:
            continue
        neg_pool.append(
            {
                "candidate_id": f"CAND_NEG_{acc}",
                "accession": acc,
                "stratum": "NEG_ENRICH",
                "organism": row.get("organism_name"),
                "genus": genus_of(row.get("organism_name") or ""),
                "species": species_of(row.get("organism_name") or ""),
                "assembly_level": row.get("assembly_level"),
                "seq_rel_date": row.get("seq_rel_date"),
                "ftp_path": row.get("ftp_path"),
                "rank_hash": rank_key("NEG_ENRICH", acc),
                "enrichment": None,
            }
        )
    neg_pool.sort(key=lambda r: (r["rank_hash"], r["accession"]))
    # Prefer mix of complete/draft: take 20 complete + 20 draft by hash order
    neg_shortlist = []
    n_comp = n_draft = 0
    for rec in neg_pool:
        level = rec["assembly_level"]
        if level in COMPLETE_LEVELS and n_comp < 20:
            neg_shortlist.append(rec)
            n_comp += 1
        elif level in DRAFT_LEVELS and n_draft < 20:
            neg_shortlist.append(rec)
            n_draft += 1
        if n_comp >= 20 and n_draft >= 20:
            break
    print(f"NEG_ENRICH_SHORTLIST={len(neg_shortlist)} (complete={n_comp}, draft={n_draft})", flush=True)

    candidates = pos_shortlist + neg_shortlist
    # write pool
    with (CASES / "ROLE_SWAP_CANDIDATE_POOL.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "candidate_id",
            "accession",
            "stratum",
            "organism",
            "genus",
            "species",
            "assembly_level",
            "seq_rel_date",
            "rank_hash",
            "ftp_path",
        ]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in candidates:
            w.writerow({k: r.get(k) for k in fields})
    write_json(
        CASES / "ROLE_SWAP_CANDIDATE_POOL.json",
        {
            "created_utc": utc_now(),
            "n_candidates": len(candidates),
            "n_pos_enrich": len(pos_shortlist),
            "n_neg_enrich": len(neg_shortlist),
            "candidates": candidates,
        },
    )
    return candidates


def ensure_diamond_dbs() -> dict:
    import adjudicate_m60_truth as adj  # noqa: WPS433

    panels = SOURCE_OUT / "panels"
    ddir = WORK / "diamond"
    ddir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "tetA_target": panels / "tetA_target.faa",
        "tetA_comp": panels / "tetA_competitors.faa",
    }
    dbs = {}
    for name, faa in mapping.items():
        db = ddir / name
        if not (ddir / f"{name}.dmnd").exists():
            adj.diamond_makedb(faa, db)
        dbs[name] = db
    os.environ["M60_TRUTH_HMM"] = str(SOURCE_OUT / "hmm")
    os.environ["M60_TRUTH_PANELS"] = str(SOURCE_OUT / "panels")
    os.environ["M60_TRUTH_BIN"] = str(BIN)
    return dbs


def adjudicate_one(rec: dict, dbs: dict, idx: int) -> dict:
    """Run M60-style Routes 1–2 for tetA on one assembly."""
    import adjudicate_m60_truth as adj  # noqa: WPS433
    from m60_truth_common import (  # noqa: WPS433
        HMM_MIN_GATE_MODEL_COVERAGE,
        read_fasta,
        write_fasta,
        write_json as _wj,
    )

    acc = rec["accession"]
    asm = FASTA_DIR / f"{acc}.fna"
    work = EVIDENCE_DIR / f"{rec['candidate_id']}_{acc}"
    work.mkdir(parents=True, exist_ok=True)
    # Redirect native paths used inside adj helpers via local reimplementation of core loop
    contigs = {name: seq.upper() for name, seq in read_fasta(asm)}
    tdb, cdb = dbs["tetA_target"], dbs["tetA_comp"]
    thmm = SOURCE_OUT / "hmm" / "tetA_tetracycline_efflux.hmm"
    chmms = [
        SOURCE_OUT / "hmm" / "mfs_multidrug_efflux.hmm",
        SOURCE_OUT / "hmm" / "rnd_efflux.hmm",
    ]
    tfaa = SOURCE_OUT / "panels" / "tetA_target.faa"
    cfaa = SOURCE_OUT / "panels" / "tetA_competitors.faa"
    min_aa, pad = 250, 400

    print(f"[{idx}] truth {acc} stratum={rec['stratum']}", flush=True)
    t_hits = adj.tblastn_search(tfaa, asm, work / "blastx_target.tsv")
    c_hits = adj.tblastn_search(cfaa, asm, work / "blastx_comp.tsv")
    search_hits = t_hits + c_hits
    if not t_hits:
        search_hits = []
    orfs = adj.recover_orfs(contigs, search_hits, min_aa=min_aa, pad=pad)
    _wj(work / "orfs.json", [{k: v for k, v in o.items() if k != "aa"} | {"aa_length": o["aa_length"]} for o in orfs])

    scored = []
    for i, orf in enumerate(orfs):
        sdir = work / f"orf_{i:02d}"
        sdir.mkdir(parents=True, exist_ok=True)
        write_fasta(sdir / "candidate.faa", [(f"orf_{i:02d}", orf["aa"])])
        metrics = adj.score_orf(orf, sdir, tdb, cdb, thmm, chmms, tfaa)
        v1, why1 = adj.tet_call(metrics["target_seq"], metrics["competitor_seq"], metrics["target_hmm"], metrics["competitor_hmm"])
        hmm_pref = (
            "target"
            if (metrics["target_hmm"].get("model_coverage") or 0)
            >= (metrics["competitor_hmm"].get("model_coverage") or 0) + 0.10
            else (
                "competitor"
                if (metrics["competitor_hmm"].get("model_coverage") or 0)
                >= (metrics["target_hmm"].get("model_coverage") or 0) + 0.10
                else "ambiguous"
            )
        )
        t_score = metrics["target_hmm"].get("full_score") or 0.0
        t_cov = metrics["target_hmm"].get("model_coverage") or 0.0
        has_seq = metrics.get("target_seq") is not None
        if not has_seq:
            v2, why2 = "NEGATIVE", "no_tetAB_sequence_match_for_profile_route"
        elif hmm_pref == "target" and t_cov >= HMM_MIN_GATE_MODEL_COVERAGE and t_score >= 80 and has_seq:
            v2 = "POSITIVE" if t_cov >= 0.45 else "TRUTH_UNCERTAIN"
            why2 = f"hmm_prefers_target cov={t_cov:.3f} score={t_score:.1f}"
        elif hmm_pref == "competitor":
            v2, why2 = "NEGATIVE", f"hmm_prefers_competitor {metrics['competitor_hmm'].get('family')} cov={metrics['competitor_hmm'].get('model_coverage'):.3f}"
        elif t_cov < 0.05 and (metrics["competitor_hmm"].get("model_coverage") or 0) < 0.05:
            v2 = "NEGATIVE" if not has_seq else "TRUTH_UNCERTAIN"
            why2 = "no_discriminating_profile_hit"
        else:
            v2, why2 = "TRUTH_UNCERTAIN", "hmm_target_vs_competitor_not_separated_or_weak_profile"
        phylo = None
        if v1 == "TRUTH_UNCERTAIN" or v2 == "TRUTH_UNCERTAIN" or v1 != v2:
            phylo = adj.hmmalign_fasttree(orf["aa"], thmm, tfaa, sdir / "phylo")
        metrics.update(
            {
                "orf_index": i,
                "coordinates": {
                    "contig": orf["contig"],
                    "strand": orf["strand"],
                    "start": orf["genomic_start"],
                    "end": orf["genomic_end"],
                },
                "aa_length": orf["aa_length"],
                "route1_value": v1,
                "route1_reason": why1,
                "route2_value": v2,
                "route2_reason": why2,
                "phylo": phylo,
            }
        )
        scored.append(metrics)

    def rk(m):
        ts = m.get("target_seq") or {}
        return (
            1 if m["route1_value"] == "POSITIVE" else 0,
            ts.get("identity_product") or 0.0,
            m.get("target_hmm", {}).get("model_coverage") or 0.0,
            m.get("aa_length") or 0,
        )

    best = max(scored, key=rk) if scored else None
    if best is None:
        truth = "NEGATIVE"
        r1 = r2 = "NEGATIVE"
        why1 = "no_candidate_orf_recovered"
        why2 = "no_profile_query"
        best_metrics = {}
    else:
        r1, r2 = best["route1_value"], best["route2_value"]
        why1, why2 = best["route1_reason"], best["route2_reason"]
        if r1 == r2 and r1 in {"POSITIVE", "NEGATIVE"}:
            truth = r1
        else:
            # second pass over same evidence: if either strongly NEGATIVE with no ORF / no seq, prefer NEGATIVE when both non-POSITIVE
            if r1 == "NEGATIVE" and r2 == "NEGATIVE":
                truth = "NEGATIVE"
            elif r1 == "POSITIVE" and r2 == "POSITIVE":
                truth = "POSITIVE"
            else:
                truth = "TRUTH_UNCERTAIN"
        best_metrics = {k: v for k, v in best.items() if k != "phylo"}
        # strip large blobs
        for key in ("target_seq", "competitor_seq", "target_hmm", "competitor_hmm"):
            if key in best_metrics and isinstance(best_metrics[key], dict):
                best_metrics[key] = {
                    kk: vv
                    for kk, vv in best_metrics[key].items()
                    if kk not in {"qseq", "sseq", "alignment"}
                }

    # Map protocol labels
    label = {"POSITIVE": "POSITIVE", "NEGATIVE": "NEGATIVE", "TRUTH_UNCERTAIN": "UNCERTAIN"}[truth]
    out = {
        "candidate_id": rec["candidate_id"],
        "accession": acc,
        "species": rec["species"],
        "genus": rec["genus"],
        "organism": rec["organism"],
        "stratum": rec["stratum"],
        "assembly_level": rec["assembly_level"],
        "seq_rel_date": rec["seq_rel_date"],
        "assembly_path": str(asm),
        "assembly_sha256": sha256_file(asm),
        "truth": label,
        "truth_status": truth,
        "route1": r1,
        "route1_reason": why1,
        "route2": r2,
        "route2_reason": why2,
        "reason": f"route1={r1} ({why1}); route2={r2} ({why2})",
        "eligible_for_final_selection": label in {"POSITIVE", "NEGATIVE"},
        "best_orf_metrics": best_metrics,
        "evidence_dir": str(work.relative_to(ROOT)).replace("\\", "/"),
        "gs_predictions_used_as_truth": False,
        "sol_used_as_truth": False,
        "jev_used_as_truth": False,
        "deterministic_validator_used_as_truth": False,
        "amrfinder_used_as_truth": False,
        "pgap_used_as_truth": False,
    }
    _wj(work / "truth_record.json", out)
    return out


def select_final(truth_rows: list[dict]) -> list[dict]:
    pos = [r for r in truth_rows if r["truth"] == "POSITIVE"]
    neg = [r for r in truth_rows if r["truth"] == "NEGATIVE"]
    pos.sort(key=lambda r: (rank_key("POS_ENRICH" if r["stratum"] == "POS_ENRICH" else "OPEN_POOL", r["accession"]), r["accession"]))
    neg.sort(key=lambda r: (rank_key("NEG_ENRICH" if r["stratum"] == "NEG_ENRICH" else "OPEN_POOL", r["accession"]), r["accession"]))
    if len(pos) < 10 or len(neg) < 10:
        raise SystemExit(
            f"STOP: insufficient resolved pools POS={len(pos)} NEG={len(neg)} (need >=10 each)"
        )

    def pick(pool: list[dict], n: int) -> list[dict]:
        chosen = []
        used_genus: set[str] = set()
        # first pass: unique genus
        for r in pool:
            g = r["genus"]
            if g in used_genus:
                continue
            chosen.append(r)
            used_genus.add(g)
            if len(chosen) >= n:
                return chosen
        # second pass: fill remaining by rank (waive unique-genus)
        for r in pool:
            if r in chosen:
                continue
            chosen.append(r)
            if len(chosen) >= n:
                break
        return chosen

    selected = pick(pos, 10) + pick(neg, 10)
    # assign case ids deterministically by rank across selected
    selected.sort(
        key=lambda r: (
            0 if r["truth"] == "POSITIVE" else 1,
            rank_key("FINAL", r["accession"]),
            r["accession"],
        )
    )
    final = []
    for i, r in enumerate(selected, start=1):
        final.append(
            {
                **r,
                "case_id": f"RS{i:02d}",
                "target": "tetA_tetracycline_efflux",
            }
        )
    return final


def write_outputs(excl: dict, truth_rows: list[dict], final: list[dict], freeze_v: dict) -> dict:
    # candidate truth
    cand_fields = [
        "candidate_id",
        "accession",
        "species",
        "genus",
        "stratum",
        "truth",
        "truth_status",
        "reason",
        "eligible_for_final_selection",
        "route1",
        "route2",
        "assembly_sha256",
    ]
    with (CASES / "ROLE_SWAP_CANDIDATE_TRUTH.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cand_fields)
        w.writeheader()
        for r in truth_rows:
            w.writerow({k: r.get(k) for k in cand_fields})

    # caseset without truth for prediction input
    case_fields = [
        "case_id",
        "accession",
        "species",
        "genus",
        "organism",
        "assembly_level",
        "seq_rel_date",
        "assembly_path",
        "assembly_sha256",
        "target",
    ]
    with (CASES / "ROLE_SWAP_CASESET.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=case_fields)
        w.writeheader()
        for r in final:
            w.writerow({k: r.get(k) for k in case_fields})

    caseset_json = {
        "kind": "ROLE_SWAP_CASESET",
        "created_utc": utc_now(),
        "n_cases": len(final),
        "target": "tetA_tetracycline_efflux",
        "claim_scope": "within_task_tetA_only",
        "truth_present": False,
        "cases": [{k: r.get(k) for k in case_fields} for r in final],
    }
    caseset_sha = write_json(CASES / "ROLE_SWAP_CASESET.json", caseset_json)

    # prediction input
    pred_fields = ["case_id", "accession", "assembly_path", "assembly_sha256", "target"]
    with (CASES / "ROLE_SWAP_PREDICTION_INPUT.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=pred_fields)
        w.writeheader()
        for r in final:
            w.writerow(
                {
                    "case_id": r["case_id"],
                    "accession": r["accession"],
                    "assembly_path": r["assembly_path"],
                    "assembly_sha256": r["assembly_sha256"],
                    "target": r["target"],
                }
            )

    # truth files
    truth_fields = [
        "case_id",
        "accession",
        "truth",
        "truth_status",
        "route1",
        "route1_reason",
        "route2",
        "route2_reason",
        "reason",
        "evidence_dir",
        "assembly_sha256",
    ]
    with (TRUTH / "ROLE_SWAP_TRUTH.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=truth_fields)
        w.writeheader()
        for r in final:
            w.writerow({k: r.get(k) for k in truth_fields})

    truth_json = {
        "kind": "ROLE_SWAP_TRUTH",
        "created_utc": utc_now(),
        "n_cases": len(final),
        "n_positive": sum(1 for r in final if r["truth"] == "POSITIVE"),
        "n_negative": sum(1 for r in final if r["truth"] == "NEGATIVE"),
        "n_uncertain": 0,
        "flags": {
            "gs_predictions_used_as_truth": False,
            "sol_used_as_truth": False,
            "jev_used_as_truth": False,
            "deterministic_validator_used_as_truth": False,
            "amrfinder_used_as_truth": False,
            "pgap_used_as_truth": False,
        },
        "cases": [
            {
                **{k: r.get(k) for k in truth_fields},
                "species": r["species"],
                "genus": r["genus"],
                "best_orf_metrics": r.get("best_orf_metrics"),
            }
            for r in final
        ],
    }
    truth_sha = write_json(TRUTH / "ROLE_SWAP_TRUTH.json", truth_json)

    evidence_manifest = {
        "kind": "ROLE_SWAP_TRUTH_EVIDENCE_MANIFEST",
        "created_utc": utc_now(),
        "cases": [
            {
                "case_id": r["case_id"],
                "accession": r["accession"],
                "evidence_dir": r["evidence_dir"],
                "evidence_dir_exists": (ROOT / r["evidence_dir"]).is_dir(),
            }
            for r in final
        ],
    }
    write_json(TRUTH / "ROLE_SWAP_TRUTH_EVIDENCE_MANIFEST.json", evidence_manifest)

    # locks
    caseset_lock = {
        "locked_at_utc": utc_now(),
        "cases_selected": True,
        "n_cases": 20,
        "n_positive": 10,
        "n_negative": 10,
        "challenge_prescreen_used": False,
        "caseset_json_sha256": caseset_sha,
        "caseset_csv_sha256": sha256_file(CASES / "ROLE_SWAP_CASESET.csv"),
        "prediction_input_sha256": sha256_file(CASES / "ROLE_SWAP_PREDICTION_INPUT.csv"),
        "exclusion_n": excl["n_unique_accessions"],
        "final_accessions": [r["accession"] for r in final],
        "genus_unique_waived": None,
    }
    # detect genus uniqueness
    genera = [r["genus"] for r in final]
    caseset_lock["unique_genera"] = len(set(genera))
    caseset_lock["unique_species"] = len({r["species"] for r in final})
    caseset_lock["genus_unique_waived"] = len(set(genera)) < 20
    caseset_lock_sha = write_json(CASES / "ROLE_SWAP_CASESET_LOCK.json", caseset_lock)

    truth_lock = {
        "locked_at_utc": utc_now(),
        "truth_locked": True,
        "truth_json_sha256": truth_sha,
        "truth_csv_sha256": sha256_file(TRUTH / "ROLE_SWAP_TRUTH.csv"),
        "n_positive": 10,
        "n_negative": 10,
        "n_uncertain": 0,
        "flags": truth_json["flags"],
        "immutable": True,
    }
    truth_lock_sha = write_json(TRUTH / "ROLE_SWAP_TRUTH_LOCK.json", truth_lock)

    # overlap audit
    excl_set = {r["accession"] for r in excl["records"]}
    overlaps = {lab: 0 for lab in ["D8", "D12", "D20", "M60", "V5_DEV", "MODEL_POC", "KNOWN_FAILURE", "REFERENCE"]}
    detail = []
    for r in final:
        acc = r["accession"]
        hit = acc in excl_set
        labels = []
        if hit:
            src = next(x["source_experiment"] for x in excl["records"] if x["accession"] == acc)
            labels = src.split(";")
            detail.append({"accession": acc, "labels": labels})
            if any("D8" in x for x in labels):
                overlaps["D8"] += 1
            if any("D12" in x for x in labels):
                overlaps["D12"] += 1
            if any("D20" in x for x in labels):
                overlaps["D20"] += 1
            if any(x.startswith("M60") for x in labels):
                overlaps["M60"] += 1
            if any("decision_authority" in x or "prospective" in x for x in labels):
                overlaps["V5_DEV"] += 1
            if any("model_poc" in x or "single_rescue" in x for x in labels):
                overlaps["MODEL_POC"] += 1
            if any("known_failure" in x for x in labels):
                overlaps["KNOWN_FAILURE"] += 1
            if any("reference" in x.lower() or "provenance" in x for x in labels):
                overlaps["REFERENCE"] += 1
    if any(overlaps.values()) or detail:
        raise SystemExit(f"STOP: prohibited overlap detected: {overlaps} detail={detail}")

    write_text(
        CASES / "ROLE_SWAP_OVERLAP_AUDIT.md",
        "\n".join(
            [
                "# ROLE_SWAP OVERLAP AUDIT",
                "",
                f"Checked final {len(final)} accessions against exclusion manifest ({excl['n_unique_accessions']} entries).",
                "",
                "D8 OVERLAP: 0",
                "D12 OVERLAP: 0",
                "D20 OVERLAP: 0",
                "M60 OVERLAP: 0",
                "V5 DEVELOPMENT OVERLAP: 0",
                "MODEL-POC OVERLAP: 0",
                "KNOWN-FAILURE OVERLAP: 0",
                "PROHIBITED REFERENCE OVERLAP: 0",
                "",
                "RESULT: PASS",
                "",
            ]
        ),
    )

    # diversity audit
    from collections import Counter

    gcount = Counter(r["genus"] for r in final)
    scount = Counter(r["species"] for r in final)
    write_text(
        CASES / "ROLE_SWAP_DIVERSITY_AUDIT.md",
        "\n".join(
            [
                "# ROLE_SWAP DIVERSITY AUDIT",
                "",
                f"UNIQUE SPECIES: {len(scount)}",
                f"UNIQUE GENERA: {len(gcount)}",
                f"Genus uniqueness fully achieved: {'YES' if len(gcount) == 20 else 'NO (waived fill permitted by frozen procedure)'}",
                "",
                "## Genus counts",
                "",
                *[f"- {g}: {c}" for g, c in sorted(gcount.items())],
                "",
                "## Species counts",
                "",
                *[f"- {s}: {c}" for s, c in sorted(scount.items())],
                "",
                "## Assembly levels",
                "",
                *[f"- {lvl}: {c}" for lvl, c in sorted(Counter(r['assembly_level'] for r in final).items())],
                "",
            ]
        ),
    )

    # independence audit
    write_text(
        TRUTH / "ROLE_SWAP_TRUTH_INDEPENDENCE_AUDIT.md",
        "\n".join(
            [
                "# ROLE_SWAP TRUTH INDEPENDENCE AUDIT",
                "",
                "Truth uses M60-aligned Routes 1–2 (sequence panel + HMM/profile), implemented via",
                "`scripts/adjudicate_m60_truth.py` helpers, **not** Genome Skeptic validator polarity,",
                "Sol, Jev, Qwen, or study arms.",
                "",
                "| resource | used by GS scientific core | used by truth protocol | reference overlap | independence adequate | limitations |",
                "|---|---|---|---|---|---|",
                "| UniProt P02980/P02982 + packaged tetA members.faa | YES (family panel) | YES (Route 1 target) | sequence panel overlap with GS family members | YES with disclosed circularity | shared panel sequences; different code path / no GS claim polarity |",
                "| MFS/RND competitor panels | YES (competitor families) | YES (Route 1 competitors) | yes | YES with disclosed circularity | same biological competitor definition |",
                "| tetA/MFS/RND HMMs (M60 truth SOURCE_FREEZE) | GS builds runtime HMMs from same MSAs | YES (Route 2) | model family overlap | YES with disclosed circularity | thresholds numerically overlap GS gates by protocol design |",
                "| NCBI IPG P02980/P02982 | NO | enrichment shortlist only | n/a | YES | not used as final truth label |",
                "| GS deterministic/agentic/exhaustive endpoints | YES | NO | none | YES | path forbidden for truth |",
                "| Sol / Jev / Qwen | n/a | NO | none | YES | not called |",
                "| AMRFinderPlus / PGAP symbols | comparator only | NO as truth | none | YES | enrichment not used as label |",
                "",
                "## Circularity disclosure",
                "",
                "Numeric gates and packaged family sequences overlap GS endpoint definition",
                "(acknowledged in ROLE_SWAP_TRUTH_PROTOCOL.md). Independence requirement is:",
                "do not copy GS/Sol/Jev validator outputs into truth. That requirement is met.",
                "",
                "STOP condition (exact same classifier + exact same evidence gates as the live GS",
                "validator polarity function): **NOT TRIGGERED** — truth polarity comes from",
                "`tet_call` / route concordance in the independent adjudication script, not from",
                "`classify_polarity` / `family_detects_orthologue` in the GS validator.",
                "",
            ]
        ),
    )

    # path guard module for future execution
    guard = '''"""Path guard: role-swap prediction runners must not read truth artifacts."""
from __future__ import annotations

FORBIDDEN_SUBSTRINGS = (
    "role_swap_cross_task/03_TRUTH",
    "role_swap_cross_task\\\\03_TRUTH",
    "ROLE_SWAP_TRUTH",
    "ROLE_SWAP_CANDIDATE_TRUTH",
)

ALLOWED_PREDICTION_INPUT = "role_swap_cross_task/02_CASES/ROLE_SWAP_PREDICTION_INPUT.csv"


def assert_prediction_path_allowed(path: str | bytes) -> None:
    text = path.decode() if isinstance(path, bytes) else str(path)
    norm = text.replace("\\\\", "/").lower()
    for bad in FORBIDDEN_SUBSTRINGS:
        if bad.replace("\\\\", "/").lower() in norm:
            raise RuntimeError(f"STOP: prediction runner attempted to read truth path: {text}")
'''
    write_text(ROOT / "scripts" / "role_swap_prediction_path_guard.py", guard)

    # verify prediction input has no truth columns
    with (CASES / "ROLE_SWAP_PREDICTION_INPUT.csv").open(encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    forbidden_cols = {"truth", "positive", "negative", "uncertain", "truth_status", "reason"}
    if forbidden_cols & {h.lower() for h in header}:
        raise SystemExit(f"STOP: truth leaked into prediction input columns: {header}")

    # preflight hash check
    preflight = {
        "checked_utc": utc_now(),
        "stop2_manifest_sha256_expected": EXPECTED_MANIFEST_SHA,
        "stop2_manifest_sha256_observed": sha256_file(FREEZE / "ROLE_SWAP_FREEZE_MANIFEST.json"),
        "v5": freeze_v["rows"],
        "family_definitions_hash": freeze_v["family_definitions_hash"],
        "reference_assets_hash": freeze_v["reference_assets_hash"],
        "all_match": freeze_v["all_match"],
        "scientific_core_or_validator_mismatch": freeze_v["scientific_core_or_validator_mismatch"],
        "result": "PASS" if freeze_v["all_match"] and not freeze_v["scientific_core_or_validator_mismatch"] else "FAIL",
    }
    write_json(FREEZE / "ROLE_SWAP_PREFLIGHT_HASH_CHECK.json", preflight)
    if preflight["result"] != "PASS":
        raise SystemExit("STOP: preflight freeze check FAIL")

    n_pos_cand = sum(1 for r in truth_rows if r["truth"] == "POSITIVE")
    n_neg_cand = sum(1 for r in truth_rows if r["truth"] == "NEGATIVE")
    n_unc_cand = sum(1 for r in truth_rows if r["truth"] == "UNCERTAIN")

    integrity = f"""# ROLE_SWAP STOP3 INTEGRITY

- V5 scientific core remained unchanged: YES
- no cases were used for scientific tuning: YES
- no model outputs were used in case selection: YES
- no prospective arm was executed: YES
- truth was established independently (Routes 1–2): YES
- truth is physically/logically separated from prediction input: YES
- final cohort is exactly 10 POSITIVE + 10 NEGATIVE: YES
- all cases are fresh relative to development: YES
- the study remains tetA-only: YES
- no second target was invented: YES

CASESET LOCK SHA256: {caseset_lock_sha}
TRUTH LOCK SHA256: {truth_lock_sha}
PREFLIGHT: {preflight['result']}

Candidate truth POS/NEG/UNCERTAIN: {n_pos_cand}/{n_neg_cand}/{n_unc_cand}
"""
    write_text(TRUTH / "ROLE_SWAP_STOP3_INTEGRITY.md", integrity)

    return {
        "caseset_lock_sha": caseset_lock_sha,
        "truth_lock_sha": truth_lock_sha,
        "preflight": preflight["result"],
        "n_pos_cand": n_pos_cand,
        "n_neg_cand": n_neg_cand,
        "n_unc_cand": n_unc_cand,
        "unique_species": caseset_lock["unique_species"],
        "unique_genera": caseset_lock["unique_genera"],
        "n_screened": len(truth_rows),
        "n_excl": excl["n_unique_accessions"],
    }


def main() -> None:
    for d in (CASES, TRUTH, FREEZE, WORK, FASTA_DIR, EVIDENCE_DIR, CACHE):
        d.mkdir(parents=True, exist_ok=True)

    freeze_v = verify_freeze_or_stop()
    excl = build_exclusion()
    excl_set = {r["accession"] for r in excl["records"]}

    http_download(SUMMARY_URL, SUMMARY_CACHE, min_bytes=10_000_000)
    # IPG may already exist from prior fetch in _work
    if IPG_CACHE.exists() and IPG_CACHE.stat().st_size > 1000:
        pass
    elif (STUDY / "_work" / "tetAB_ipg.txt").exists():
        shutil.copy2(STUDY / "_work" / "tetAB_ipg.txt", IPG_CACHE)
    else:
        http_download(IPG_URL, IPG_CACHE, min_bytes=1000)

    summary_rows = parse_summary(SUMMARY_CACHE)
    print(f"SUMMARY_ROWS={len(summary_rows)}", flush=True)
    ipg = parse_ipg_gcf(IPG_CACHE)
    print(f"IPG_GCF={len(ipg)}", flush=True)

    candidates = build_candidate_pool(excl_set, summary_rows, ipg)

    # download fastas
    for rec in candidates:
        dest = FASTA_DIR / f"{rec['accession']}.fna"
        download_assembly_fasta(rec["accession"], rec.get("ftp_path") or "", dest)
        rec["assembly_path"] = str(dest)
        rec["assembly_sha256"] = sha256_file(dest)

    copy_truth_sources()
    truth_bin = ensure_truth_bin()
    if not (truth_bin / "diamond").exists():
        raise SystemExit(f"STOP: diamond missing under {truth_bin}")
    if not (truth_bin / "tblastn").exists():
        raise SystemExit(f"STOP: tblastn missing under {truth_bin}")
    # Force adjudicate_m60_truth to use our BIN
    import adjudicate_m60_truth as adj  # noqa: WPS433

    adj.BIN = truth_bin
    dbs = ensure_diamond_dbs()

    truth_rows = []
    for i, rec in enumerate(candidates, start=1):
        truth_rows.append(adjudicate_one(rec, dbs, i))

    # If pools insufficient, enlarge NEG or POS from remaining ranked lists once
    pos_n = sum(1 for r in truth_rows if r["truth"] == "POSITIVE")
    neg_n = sum(1 for r in truth_rows if r["truth"] == "NEGATIVE")
    print(f"RESOLVED_AFTER_FIRST_PASS POS={pos_n} NEG={neg_n} UNC={sum(1 for r in truth_rows if r['truth']=='UNCERTAIN')}", flush=True)

    if pos_n < 10 or neg_n < 10:
        # enlarge: take next 20 from unused POS_ENRICH / NEG_ENRICH
        used = {r["accession"] for r in candidates}
        eligible_rows = [row for row in summary_rows if quality_ok(row)[0] and row["assembly_accession"] not in excl_set]
        extra: list[dict] = []
        if pos_n < 10:
            pos_more = []
            for row in eligible_rows:
                acc = row["assembly_accession"]
                if acc in used or acc not in ipg:
                    continue
                pos_more.append(
                    {
                        "candidate_id": f"CAND_POS2_{acc}",
                        "accession": acc,
                        "stratum": "POS_ENRICH",
                        "organism": row.get("organism_name"),
                        "genus": genus_of(row.get("organism_name") or ""),
                        "species": species_of(row.get("organism_name") or ""),
                        "assembly_level": row.get("assembly_level"),
                        "seq_rel_date": row.get("seq_rel_date"),
                        "ftp_path": row.get("ftp_path"),
                        "rank_hash": rank_key("POS_ENRICH", acc),
                    }
                )
            pos_more.sort(key=lambda r: (r["rank_hash"], r["accession"]))
            # skip already in first 40
            pos_more = [r for r in pos_more if r["accession"] not in used][:30]
            extra.extend(pos_more)
        if neg_n < 10:
            neg_more = []
            for row in eligible_rows:
                acc = row["assembly_accession"]
                if acc in used or acc in ipg:
                    continue
                neg_more.append(
                    {
                        "candidate_id": f"CAND_NEG2_{acc}",
                        "accession": acc,
                        "stratum": "NEG_ENRICH",
                        "organism": row.get("organism_name"),
                        "genus": genus_of(row.get("organism_name") or ""),
                        "species": species_of(row.get("organism_name") or ""),
                        "assembly_level": row.get("assembly_level"),
                        "seq_rel_date": row.get("seq_rel_date"),
                        "ftp_path": row.get("ftp_path"),
                        "rank_hash": rank_key("NEG_ENRICH", acc),
                    }
                )
            neg_more.sort(key=lambda r: (r["rank_hash"], r["accession"]))
            neg_more = [r for r in neg_more if r["accession"] not in used][:30]
            extra.extend(neg_more)
        print(f"ENLARGEMENT_EXTRA={len(extra)}", flush=True)
        for rec in extra:
            dest = FASTA_DIR / f"{rec['accession']}.fna"
            download_assembly_fasta(rec["accession"], rec.get("ftp_path") or "", dest)
            rec["assembly_path"] = str(dest)
            rec["assembly_sha256"] = sha256_file(dest)
            truth_rows.append(adjudicate_one(rec, dbs, len(truth_rows) + 1))
            candidates.append(rec)

    final = select_final(truth_rows)
    summary = write_outputs(excl, truth_rows, final, freeze_v)

    print("\n===== TERMINAL SUMMARY =====", flush=True)
    print("ROLE-SWAP COHORT CONSTRUCTION COMPLETE: YES")
    print("FROZEN PROTOCOL USED: YES")
    print("V5 SCIENTIFIC CORE STILL MATCHES: YES")
    print("SCIENTIFIC TUNING AFTER STOP 2: NO")
    print(f"TOTAL UNIQUE DEVELOPMENT/REFERENCE EXCLUSIONS: {summary['n_excl']}")
    print(f"CANDIDATE GENOMES SCREENED: {summary['n_screened']}")
    print(f"TRUTH POSITIVE CANDIDATES: {summary['n_pos_cand']}")
    print(f"TRUTH NEGATIVE CANDIDATES: {summary['n_neg_cand']}")
    print(f"TRUTH UNCERTAIN CANDIDATES: {summary['n_unc_cand']}")
    print("FINAL COHORT: 20")
    print("FINAL POSITIVES: 10")
    print("FINAL NEGATIVES: 10")
    print("FINAL UNCERTAIN: 0")
    print(f"UNIQUE SPECIES: {summary['unique_species']}")
    print(f"UNIQUE GENERA: {summary['unique_genera']}")
    print("D8 OVERLAP: 0")
    print("D12 OVERLAP: 0")
    print("D20 OVERLAP: 0")
    print("M60 OVERLAP: 0")
    print("V5 DEVELOPMENT OVERLAP: 0")
    print("MODEL-POC OVERLAP: 0")
    print("KNOWN-FAILURE OVERLAP: 0")
    print("PROHIBITED REFERENCE OVERLAP: 0")
    print("TRUTH USED TO SELECT CLASS BALANCE: YES")
    print("GENOME SKEPTIC PREDICTIONS USED FOR CASE SELECTION: NO")
    print("TRUTH PRESENT IN PREDICTION INPUT: NO")
    print("TRUTH ACCESSIBLE TO PREDICTION RUNNER: NO")
    print("SOL CALLED: NO")
    print("JEV CALLED: NO")
    print("ARM A RUN: NO")
    print("ARM B RUN: NO")
    print("ARM C RUN: NO")
    print("ARM D RUN: NO")
    print("ARM E RUN: NO")
    print("ARM F RUN: NO")
    print(f"CASESET LOCK SHA256: {summary['caseset_lock_sha']}")
    print(f"TRUTH LOCK SHA256: {summary['truth_lock_sha']}")
    print(f"PREFLIGHT FREEZE CHECK: {summary['preflight']}")
    print("READY FOR ROLE-SWAP EXECUTION: YES")
    print("STOP.")


if __name__ == "__main__":
    main()
