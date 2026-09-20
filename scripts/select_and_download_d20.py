#!/usr/bin/env python3
"""Gate 1 Step 1: metadata-only D20 40-case candidate pool + FASTA lock.

Does not inspect gene annotations, AMRFinder, PGAP, eggNOG, or NCBI orthologs.
Does not run Genome Skeptic, Agentic V2, planner, or critic.
Does not modify frozen scientific source.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation_agentic_d20"
CACHE = ROOT / "external_validation_agentic" / "_cache"
SUMMARY_CACHE = CACHE / "assembly_summary_bacteria.txt"
LINEAGE_CACHE = CACHE / "rankedlineage.dmp"
SUMMARY_URL = "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/assembly_summary.txt"
TAXDUMP_URL = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/new_taxdump.zip"
EXCL_PATH = ROOT / "external_validation" / "v5_reference_provenance_exclusions.json"
COHORT_A_PATH = ROOT / "external_validation" / "cohort_A_naturalistic_manifest.json"
COHORT_C_PATH = ROOT / "external_validation_agentic" / "cohort_C_manifest.json"
FREEZE_MANIFEST = ROOT / "agentic_freeze" / "GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json"
EXPECTED_FREEZE_SHA = "736bd2bdc34b1967a429602903f26ebfa5cdb031c6787a7f0ebf77926517c696"
EXPECTED_DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"

SEED = "20260920"
RELEASE_CUTOFF = date(2025, 1, 1)
UA = "GenomeSkeptic-external-validation/cohort-D20-metadata-fasta-only"

TARGETS = [
    "rpoB_RNAP_beta",
    "tuf_EF_Tu",
    "lacZ_beta_galactosidase",
    "tetA_tetracycline_efflux",
]
COMPLETE_LEVELS = {"Complete Genome", "Chromosome"}
DRAFT_LEVELS = {"Scaffold", "Contig"}
N_COMPLETE = 6
N_DRAFT = 4

EXCLUDED_TAXIDS = {
    511145, 208964, 85962, 224308, 160488, 93061, 99287, 243277, 83332, 243274, 224324,
}
EXCLUDED_NUC = {
    "NC_000853.1", "NC_000913.3", "NC_000915.1", "NC_000918.1", "NC_000962.3",
    "NC_000964.3", "NC_002505.1", "NC_002516.2", "NC_002947.4", "NC_003197.2",
    "NC_003277.2", "NC_007795.1", "U00096.3",
}
EXCLUDED_GCF = {
    "GCF_000005845.2", "GCF_000006765.1", "GCF_000008525.1", "GCF_000009045.1",
    "GCF_000007565.2", "GCF_000013425.1", "GCF_000006945.2", "GCF_000006745.1",
    "GCF_000195955.2", "GCF_000008545.1", "GCF_000008605.1",
}
EXCLUDED_ORGANISM_MARKERS = (
    "k-12 substr. mg1655", "substr. mg1655", "pseudomonas aeruginosa pao1",
    "helicobacter pylori 26695", "subtilis subsp. subtilis str. 168", "putida kt2440",
    "nctc 8325", "typhimurium str. lt2", "el tor str. n16961", "tuberculosis h37rv",
    "thermotoga maritima", "aquifex aeolicus",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sampling_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def normalize_genus(name: str) -> str:
    text = (name or "").replace("[", "").replace("]", "").strip()
    text = text.replace(" (SeqCode)", "").replace("(SeqCode)", "").strip()
    parts = text.split()
    if not parts:
        return ""
    if parts[0].lower() == "candidatus" and len(parts) > 1:
        return parts[1]
    return parts[0]


def genus_of(organism: str) -> str:
    return normalize_genus(organism)


def parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw or raw.lower() in {"na", "n/a"}:
        return None
    try:
        y, m, d = raw.split("/")[0].split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def download(url: str, dest: Path, min_bytes: int) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    req = Request(url, headers={"User-Agent": UA})
    print(f"download {url}", flush=True)
    with urlopen(req, timeout=600) as resp, tmp.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    tmp.replace(dest)
    return dest


def ensure_summary() -> Path:
    return download(SUMMARY_URL, SUMMARY_CACHE, 5_000_000)


def ensure_lineage() -> Path:
    if LINEAGE_CACHE.exists() and LINEAGE_CACHE.stat().st_size > 1_000_000:
        return LINEAGE_CACHE
    zip_path = download(TAXDUMP_URL, CACHE / "new_taxdump.zip", 1_000_000)
    print("extract rankedlineage.dmp", flush=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        pick = next((n for n in names if n.endswith("rankedlineage.dmp") or n == "rankedlineage.dmp"), None)
        if pick is None:
            raise RuntimeError(f"rankedlineage.dmp missing: {names[:20]}")
        LINEAGE_CACHE.write_bytes(zf.read(pick))
    return LINEAGE_CACHE


def load_lineage(path: Path) -> dict[int, dict]:
    out: dict[int, dict] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            parts = [p.strip() for p in ln.rstrip("\n").split("|")]
            if len(parts) < 10:
                continue
            try:
                taxid = int(parts[0])
            except ValueError:
                continue
            out[taxid] = {
                "tax_name": parts[1],
                "species": parts[2],
                "genus": normalize_genus(parts[3] or parts[1]),
                "family": parts[4],
                "order": parts[5],
                "class": parts[6],
                "phylum": parts[7],
                "kingdom": parts[8],
                "domain": parts[9],
            }
    return out


def load_rows(path: Path) -> list[dict]:
    cols = None
    rows = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if ln.startswith("#assembly_accession") or ln.startswith("# assembly_accession"):
                cols = ln.lstrip("#").strip().split("\t")
                continue
            if ln.startswith("#") or not ln.strip():
                continue
            if cols is None:
                continue
            parts = ln.rstrip("\n").split("\t")
            rec = {cols[i]: parts[i] if i < len(parts) else "" for i in range(len(cols))}
            rows.append(rec)
    if cols is None:
        raise RuntimeError("assembly_summary header not found")
    return rows


def load_accessions(path: Path, key: str = "assemblies") -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    accs = set()
    for rec in payload.get(key) or payload.get("genomes") or []:
        acc = rec.get("assembly_accession")
        if acc:
            accs.add(acc)
            accs.add(acc.split(".")[0])
    return accs


def load_genera_from_manifest(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out = set()
    for g in payload.get("genera") or []:
        ng = normalize_genus(str(g))
        if ng:
            out.add(ng)
    sampling = payload.get("sampling") or {}
    for rec in sampling.get("per_genus") or []:
        ng = normalize_genus(str(rec.get("genus") or ""))
        if ng:
            out.add(ng)
    for rec in payload.get("assemblies") or []:
        ng = normalize_genus(str(rec.get("genus") or rec.get("organism") or ""))
        if ng:
            out.add(ng)
    return out


def load_exclusion_accessions() -> set[str]:
    payload = json.loads(EXCL_PATH.read_text(encoding="utf-8"))
    accs = set(EXCLUDED_GCF)
    for rec in payload.get("excluded_source_reference_genomes") or []:
        acc = rec.get("accession") or ""
        if acc:
            accs.add(acc)
            accs.add(acc.split(".")[0])
        for extra in rec.get("extra_accessions") or []:
            accs.add(extra)
            accs.add(str(extra).split(".")[0])
    for acc in payload.get("excluded_nucleotide_accessions") or []:
        accs.add(acc)
    return accs


def taxonomy_for(row: dict, lineage: dict[int, dict]) -> dict:
    taxid = int(row["taxid"]) if (row.get("taxid") or "").isdigit() else None
    spid = int(row["species_taxid"]) if (row.get("species_taxid") or "").isdigit() else None
    info = lineage.get(taxid) or lineage.get(spid) or {}
    genus = normalize_genus(info.get("genus") or "") or genus_of(row.get("organism_name") or "")
    species = (info.get("species") or info.get("tax_name") or "").strip()
    if not species:
        parts = (row.get("organism_name") or "").replace("[", "").replace("]", "").split()
        if parts and parts[0].lower() == "candidatus" and len(parts) >= 3:
            species = " ".join(parts[1:3])
        elif len(parts) >= 2:
            species = " ".join(parts[:2])
        else:
            species = row.get("organism_name") or ""
    return {
        "taxonomy_id": taxid,
        "species_taxid": spid,
        "genus": genus,
        "species": species,
        "phylum": info.get("phylum") or None,
        "class": info.get("class") or None,
        "order": info.get("order") or None,
        "family": info.get("family") or None,
        "domain": info.get("domain") or None,
    }


def is_excluded(row: dict, blocked_acc: set[str], excl_acc: set[str]) -> tuple[bool, str]:
    acc = row.get("assembly_accession") or ""
    stem = acc.split(".")[0]
    if acc in blocked_acc or stem in blocked_acc:
        return True, "prior_cohort_or_pilot_accession"
    if acc in excl_acc or stem in excl_acc or acc in EXCLUDED_GCF:
        return True, "excluded_GCF_provenance"
    taxid = int(row["taxid"]) if (row.get("taxid") or "").isdigit() else -1
    if taxid in EXCLUDED_TAXIDS:
        return True, "excluded_taxid_provenance"
    organism = (row.get("organism_name") or "").lower()
    if any(m in organism for m in EXCLUDED_ORGANISM_MARKERS):
        return True, "excluded_organism_provenance"
    ident_blob = " ".join(str(row.get(k) or "") for k in ("assembly_accession", "gbrs_paired_asm", "asm_name", "organism_name", "ftp_path"))
    if any(n in ident_blob for n in EXCLUDED_NUC):
        return True, "excluded_nucleotide_accession"
    return False, ""


def eligible_row(row: dict, blocked_acc: set[str], excl_acc: set[str]) -> bool:
    acc = row.get("assembly_accession") or ""
    if not acc.startswith("GCF_"):
        return False
    if (row.get("version_status") or "") != "latest":
        return False
    excl = (row.get("excluded_from_refseq") or "").strip()
    if excl and excl.lower() not in {"na", "n/a"}:
        return False
    if (row.get("genome_rep") or "") != "Full":
        return False
    if (row.get("assembly_level") or "") not in COMPLETE_LEVELS | DRAFT_LEVELS:
        return False
    rel = parse_date(row.get("seq_rel_date") or "")
    if rel is None or rel < RELEASE_CUTOFF:
        return False
    genus = genus_of(row.get("organism_name") or "")
    if not genus or genus.lower() in {"bacterium", "bacteria", "uncultured"}:
        return False
    blocked, _ = is_excluded(row, blocked_acc, excl_acc)
    return not blocked


def sanitize_fasta(text: str) -> str:
    """Opaque contig_N headers. Strips product/gene/organism-function annotation text."""
    out: list[str] = []
    n = 0
    seq: list[str] = []

    def flush() -> None:
        if not seq:
            return
        body = "".join(seq)
        for j in range(0, len(body), 80):
            out.append(body[j : j + 80])

    for line in text.splitlines():
        if line.startswith(">"):
            flush()
            seq = []
            n += 1
            out.append(f">contig_{n}")
        else:
            seq.append("".join(ch for ch in line.strip().upper() if ch.isalpha()))
    flush()
    return "\n".join(out) + ("\n" if out else "")


def fetch_genome_fasta(acc: str, ftp_path: str) -> tuple[bytes, str]:
    last = None
    datasets = (
        "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/"
        f"{acc}/download?include_annotation_type=GENOME_FASTA"
    )
    for attempt in range(4):
        try:
            req = Request(datasets, headers={"User-Agent": UA})
            with urlopen(req, timeout=180) as resp:
                blob = resp.read()
            if blob[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    names = [n for n in zf.namelist() if n.endswith(".fna") or n.endswith(".fasta")]
                    genomic = [n for n in names if "genomic" in n.lower() or n.endswith(".fna")]
                    pick = genomic[0] if genomic else (names[0] if names else None)
                    if pick is None:
                        raise RuntimeError(f"no fasta in zip: {zf.namelist()[:12]}")
                    return zf.read(pick), datasets
            raise RuntimeError(f"not a zip: {blob[:60]!r}")
        except Exception as exc:
            last = exc
            time.sleep(1.2 * (attempt + 1))
    ftp = (ftp_path or "").rstrip("/")
    if ftp.startswith("ftp://"):
        ftp = "https://" + ftp[len("ftp://") :]
    if ftp:
        name = ftp.rsplit("/", 1)[-1]
        gz_url = f"{ftp}/{name}_genomic.fna.gz"
        try:
            req = Request(gz_url, headers={"User-Agent": UA})
            with urlopen(req, timeout=180) as resp:
                raw = resp.read()
            return gzip.decompress(raw), gz_url
        except Exception as exc:
            last = exc
    raise RuntimeError(last)


def quality_bucket(level: str) -> str:
    if level in COMPLETE_LEVELS:
        return "complete_or_chromosome"
    if level in DRAFT_LEVELS:
        return "scaffold_or_contig"
    return "other"


def verify_freeze() -> dict:
    digest = sha256_file(FREEZE_MANIFEST)
    if digest != EXPECTED_FREEZE_SHA:
        raise SystemExit(f"freeze SHA256 mismatch: {digest} != {EXPECTED_FREEZE_SHA}")
    payload = json.loads(FREEZE_MANIFEST.read_text(encoding="utf-8"))
    if payload.get("freeze_id") != "GENOME_SKEPTIC_AGENTIC_V2_D20":
        raise SystemExit("freeze_id mismatch")
    if payload.get("model_digest") != EXPECTED_DIGEST:
        raise SystemExit("model digest mismatch")
    mismatches = []
    for row in payload.get("files") or []:
        path = ROOT / row["path"]
        if not path.is_file():
            mismatches.append(row["path"])
            continue
        if sha256_file(path) != row["sha256"]:
            mismatches.append(row["path"])
    if mismatches:
        raise SystemExit("frozen files changed:\n" + "\n".join(mismatches[:20]))
    return {"freeze_id": payload["freeze_id"], "manifest_sha256": digest, "n_files": payload.get("n_files")}


def main() -> None:
    freeze = verify_freeze()
    print("FREEZE_OK", freeze["manifest_sha256"], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    orig_dir = OUT / "inputs" / "original"
    solver_dir = OUT / "inputs" / "solver"
    orig_dir.mkdir(parents=True, exist_ok=True)
    solver_dir.mkdir(parents=True, exist_ok=True)

    cohort_a_acc = load_accessions(COHORT_A_PATH)
    cohort_c_acc = load_accessions(COHORT_C_PATH)
    blocked_acc = set(cohort_a_acc) | set(cohort_c_acc)
    prior_genera = load_genera_from_manifest(COHORT_A_PATH) | load_genera_from_manifest(COHORT_C_PATH)
    excl_acc = load_exclusion_accessions()

    summary = ensure_summary()
    lineage = load_lineage(ensure_lineage())
    rows = [r for r in load_rows(summary) if eligible_row(r, blocked_acc, excl_acc)]
    print(f"eligible_metadata_rows {len(rows)}", flush=True)

    annotated = []
    for row in rows:
        tax = taxonomy_for(row, lineage)
        if not tax["genus"] or not tax["species"]:
            continue
        annotated.append((row, tax))

    used_acc: set[str] = set()
    used_species: set[str] = set()
    used_genera: set[str] = set()
    failures: list[dict] = []
    selected: list[dict] = []

    def species_key(tax: dict) -> str:
        if tax.get("species_taxid"):
            return f"taxid:{tax['species_taxid']}"
        return f"name:{(tax.get('species') or '').lower()}"

    def try_download(row: dict, tax: dict, target: str) -> dict | None:
        acc = row["assembly_accession"]
        orig_path = orig_dir / f"{acc}.fna"
        solver_path = solver_dir / f"{acc}.fna"
        stamp = datetime.now(timezone.utc).isoformat()
        source = None
        try:
            if orig_path.exists() and orig_path.stat().st_size > 1000:
                text = orig_path.read_text(encoding="utf-8", errors="replace")
                source = "reused_local_original"
            else:
                data, source = fetch_genome_fasta(acc, row.get("ftp_path") or "")
                text = data.decode("utf-8", errors="replace")
                orig_path.write_text(text, encoding="utf-8")
            sanitized = sanitize_fasta(text)
            if sanitized.count(">") < 1:
                raise RuntimeError("sanitized fasta empty")
            solver_path.write_text(sanitized, encoding="utf-8")
        except Exception as exc:
            failures.append(
                {
                    "assembly_accession": acc,
                    "target": target,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "sampling_hash": sampling_hash(target, acc),
                }
            )
            print(f"FAIL {acc} {target} {exc}", flush=True)
            return None
        n50_raw = row.get("contig_n50") or row.get("scaffold_n50") or ""
        rec = {
            "assembly_accession": acc,
            "organism": row.get("organism_name"),
            "genus": tax["genus"],
            "species": tax["species"],
            "taxonomy_id": tax["taxonomy_id"],
            "species_taxid": tax["species_taxid"],
            "phylum": tax["phylum"],
            "class": tax["class"],
            "order": tax["order"],
            "family": tax["family"],
            "target": target,
            "release_date": row.get("seq_rel_date"),
            "assembly_level": row.get("assembly_level"),
            "assembly_quality": quality_bucket(row.get("assembly_level") or ""),
            "refseq_status": row.get("version_status"),
            "refseq_category": row.get("refseq_category") or None,
            "genome_size": int(row["genome_size"]) if (row.get("genome_size") or "").isdigit() else None,
            "contig_count": int(row["contig_count"]) if (row.get("contig_count") or "").isdigit() else None,
            "n50": int(n50_raw) if str(n50_raw).isdigit() else None,
            "ftp_path": row.get("ftp_path") or None,
            "fasta_source": source,
            "original_fasta": str(orig_path.relative_to(ROOT)).replace("\\", "/"),
            "original_fasta_bytes": orig_path.stat().st_size,
            "original_fasta_sha256": sha256_file(orig_path),
            "solver_fasta": str(solver_path.relative_to(ROOT)).replace("\\", "/"),
            "solver_fasta_bytes": solver_path.stat().st_size,
            "fasta_sha256": sha256_file(solver_path),
            "download_timestamp_utc": stamp,
            "headers_sanitized": True,
            "sanitization_rule": "opaque contig_N identifiers; product/gene/organism-function text stripped",
            "sampling_hash": sampling_hash(target, acc),
            "gff_downloaded": False,
            "gbff_downloaded": False,
            "protein_fasta_downloaded": False,
            "amrfinder_downloaded": False,
            "annotations_inspected": False,
            "external_labels_opened": False,
            "avoided_prior_cohort_genus": tax["genus"] not in prior_genera,
        }
        print(f"OK {acc} {target} {tax['genus']} {row.get('assembly_level')}", flush=True)
        time.sleep(0.25)
        return rec

    def fill(target: str, levels: set[str], n: int) -> list[dict]:
        ranked = sorted(
            ((row, tax) for row, tax in annotated if (row.get("assembly_level") or "") in levels),
            key=lambda rt: (sampling_hash(target, rt[0]["assembly_accession"]), rt[0]["assembly_accession"]),
        )
        picked: list[dict] = []

        def accept(row: dict, tax: dict, prefer_new_genus: bool, avoid_prior: bool) -> bool:
            acc = row["assembly_accession"]
            if acc in used_acc or acc.split(".")[0] in used_acc:
                return False
            if species_key(tax) in used_species:
                return False
            if prefer_new_genus and tax["genus"] in used_genera:
                return False
            if avoid_prior and tax["genus"] in prior_genera:
                return False
            return True

        def drain(prefer_new_genus: bool, avoid_prior: bool) -> None:
            for row, tax in ranked:
                if len(picked) >= n:
                    return
                if not accept(row, tax, prefer_new_genus, avoid_prior):
                    continue
                rec = try_download(row, tax, target)
                if rec is None:
                    used_acc.add(row["assembly_accession"])
                    continue
                used_acc.add(rec["assembly_accession"])
                used_acc.add(rec["assembly_accession"].split(".")[0])
                used_species.add(species_key(tax))
                used_genera.add(tax["genus"])
                picked.append(rec)

        drain(True, True)
        drain(True, False)
        drain(False, False)
        if len(picked) < n:
            raise SystemExit(f"could not fill {target} {sorted(levels)} need={n} got={len(picked)}")
        return picked

    for target in TARGETS:
        print(f"SELECT {target}", flush=True)
        selected.extend(fill(target, COMPLETE_LEVELS, N_COMPLETE))
        selected.extend(fill(target, DRAFT_LEVELS, N_DRAFT))

    selected.sort(key=lambda r: (r["target"], r["sampling_hash"], r["assembly_accession"]))
    counts = defaultdict(int)
    quality = defaultdict(int)
    for rec in selected:
        counts[rec["target"]] += 1
        quality[rec["assembly_quality"]] += 1

    payload = {
        "kind": "d20_candidate_pool_manifest",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V2_D20",
        "agentic_freeze_manifest_sha256": freeze["manifest_sha256"],
        "model": "qwen3:4b",
        "model_digest": EXPECTED_DIGEST,
        "seed": SEED,
        "sampling_hash_formula": 'SHA256("20260920|<target>|<assembly_accession>")',
        "release_cutoff": "2025-01-01",
        "n_candidates": len(selected),
        "target_counts": dict(counts),
        "assembly_quality_counts": dict(quality),
        "n_unique_genomes": len({r["assembly_accession"] for r in selected}),
        "n_unique_species": len({r["species"] for r in selected}),
        "n_unique_genera": len({r["genus"] for r in selected}),
        "prior_cohort_genera_avoided_where_practical": sorted(prior_genera),
        "external_labels_opened": False,
        "gene_content_used_for_selection": False,
        "agentic_v2_executed": False,
        "planner_called": False,
        "critic_called": False,
        "download_failures_skipped": failures,
        "candidates": selected,
    }
    json_path = OUT / "candidate_pool_manifest.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    csv_path = OUT / "candidate_pool_manifest.csv"
    fields = [
        "assembly_accession", "organism", "genus", "species", "target", "release_date",
        "assembly_level", "assembly_quality", "refseq_status", "fasta_source",
        "fasta_sha256", "sampling_hash", "solver_fasta_bytes", "download_timestamp_utc",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for rec in selected:
            w.writerow(rec)
    locks = {}
    for path in (json_path, csv_path):
        digest = sha256_file(path)
        locks[path.name] = digest
        (OUT / f"{path.name}.sha256.json").write_text(
            json.dumps(
                {
                    "file": path.name,
                    "sha256": digest,
                    "hashed_utc": datetime.now(timezone.utc).isoformat(),
                    "hashed_before_v5_prescreen": True,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print("CANDIDATE_JSON", locks[json_path.name], flush=True)
    print("CANDIDATE_CSV", locks[csv_path.name], flush=True)
    print("N", len(selected), "GENERA", payload["n_unique_genera"], "SPECIES", payload["n_unique_species"], flush=True)


if __name__ == "__main__":
    main()
