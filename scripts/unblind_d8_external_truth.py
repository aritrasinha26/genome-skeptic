#!/usr/bin/env python3
"""Assign D8_MINI_EXTERNAL independent truth. Does not read system predictions."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation_agentic_d8"
MANIFEST = OUT / "D8_MANIFEST.json"
CACHE = OUT / "truth_cache"
TRUTH = OUT / "D8_EXTERNAL_TRUTH_LOCKED.json"
UA = "GenomeSkeptic-external-validation/D8-MINI-EXTERNAL-truth-only"

EXPECTED_MANIFEST = "37862918643052fa8cb81ff5e180161973a6dd5311aef62bd78c59f8ea74cdbd"
EXPECTED_CONV = "e2cdb6c91a788f6dd6126ba1bb1ce14aea512e71c110036a66e97e05b4214b51"
EXPECTED_V5 = "0475084d908218c7676820e612745c4e6a309f71b0644642ac08dd8f4b4665db"
EXPECTED_AGENTIC = "2331e5fd5c265df2046f7fcc1f43dd7ed9e5f51ed4b2c5ecf03b48fc5df63d16"

SEEDS = {
    "rpoB_RNAP_beta": {
        "protein_id": "NP_418414.1",
        "gene_id": "948488",
        "symbols": ("rpoB",),
        "related_symbols": ("rpoA", "rpoC", "rpoZ", "rpoD"),
        "min_len": 1000,
        "max_len": 2000,
        "evalue": 1e-50,
        "min_qcov": 0.80,
    },
    "tuf_EF_Tu": {
        "protein_id": "NP_417798.1",
        "gene_id": "947838",
        "symbols": ("tuf", "tufA", "tufB"),
        "related_symbols": ("tsf", "selB", "lepA", "fusA", "tufS"),
        "min_len": 340,
        "max_len": 460,
        "evalue": 1e-50,
        "min_qcov": 0.80,
    },
    "lacZ_beta_galactosidase": {
        "protein_id": "NP_414878.1",
        "gene_id": "945006",
        "symbols": ("lacZ",),
        "related_symbols": ("ebgA", "bglX", "lacA", "lacY"),
        "min_len": 800,
        "max_len": 1400,
        "evalue": 1e-10,
        "min_qcov": 0.70,
    },
}

TET_POSITIVE = {"tet(a)", "tet(b)", "teta", "tetb"}
TET_RELATED = {
    "tet(c)", "tet(d)", "tet(e)", "tet(g)", "tet(h)", "tet(j)", "tet(k)",
    "tet(l)", "tet(m)", "tet(o)", "tet(q)", "tet(s)", "tet(t)", "tet(w)",
    "tet(x)", "tet(y)", "tet(z)", "tetc", "tetd", "tetk", "tetl", "tetm",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_json(url: str, timeout: int = 120):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last = None
    for attempt in range(5):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
            time.sleep(1.2 * (attempt + 1))
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"GET JSON failed {url}: {last}")


def http_bytes(url: str, timeout: int = 300) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(6):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:
            last = exc
            time.sleep(1.6 * (attempt + 1))
    raise RuntimeError(f"GET bytes failed {url}: {last}")


def http_text(url: str, timeout: int = 120) -> str | None:
    try:
        return http_bytes(url, timeout=timeout).decode("utf-8", errors="replace")
    except Exception:
        return None


def to_wsl(path: Path) -> str:
    s = str(path.resolve())
    if len(s) >= 2 and s[1] == ":":
        return "/mnt/" + s[0].lower() + s[2:].replace("\\", "/")
    return s.replace("\\", "/")


def verify_locks() -> dict:
    files = {
        "D8_MANIFEST.json": (MANIFEST, EXPECTED_MANIFEST),
        "D8_CONVENTIONAL_LOCKED.json": (OUT / "D8_CONVENTIONAL_LOCKED.json", EXPECTED_CONV),
        "D8_V5_LOCKED.json": (OUT / "D8_V5_LOCKED.json", EXPECTED_V5),
        "D8_AGENTIC_V2_LOCKED.json": (OUT / "D8_AGENTIC_V2_LOCKED.json", EXPECTED_AGENTIC),
    }
    out = {}
    for name, (path, expected) in files.items():
        digest = sha256_file(path)
        if digest != expected:
            raise SystemExit(f"HASH MISMATCH {name} computed={digest} expected={expected}")
        out[name] = digest
    return out


def confirm_prediction_structure() -> dict:
    """Structural lock check only: counts, accessions, agentic pos7 failure. No scientific use."""
    summary = {}
    for name, system in (
        ("D8_CONVENTIONAL_LOCKED.json", "conventional"),
        ("D8_V5_LOCKED.json", "v5"),
        ("D8_AGENTIC_V2_LOCKED.json", "agentic"),
    ):
        blob = json.loads((OUT / name).read_text(encoding="utf-8"))
        recs = blob.get("predictions") or []
        if len(recs) != 8:
            raise SystemExit(f"{name} has {len(recs)} records, expected 8")
        pairs = [(r.get("assembly_accession"), r.get("target"), r.get("ok"), r.get("agent_failure")) for r in recs]
        summary[system] = {
            "n": len(recs),
            "pairs": [(a, t, ok) for a, t, ok, _ in pairs],
        }
        if system == "agentic":
            pos7 = recs[6]
            if pos7.get("assembly_accession") != "GCF_053618555.1" or pos7.get("target") != "tetA_tetracycline_efflux":
                raise SystemExit(f"agentic position 7 identity mismatch: {pos7.get('assembly_accession')} {pos7.get('target')}")
            if pos7.get("ok") is not False:
                raise SystemExit("agentic position 7 is not recorded as ok=False")
            reason = str(pos7.get("agent_failure") or "")
            if reason != "planner cited no evidence IDs":
                raise SystemExit(f"agentic position 7 reason mismatch: {reason!r}")
            summary["agentic_pos7"] = {
                "assembly_accession": pos7.get("assembly_accession"),
                "target": pos7.get("target"),
                "ok": pos7.get("ok"),
                "reason": reason,
            }
    return summary


def gene_id_for_protein(protein_id: str) -> str | None:
    data = http_json(f"https://api.ncbi.nlm.nih.gov/datasets/v2/gene/accession/{protein_id}")
    genes = (data or {}).get("genes") or []
    for rec in genes:
        gene = rec.get("gene") or rec
        gid = str(gene.get("gene_id") or "")
        if gid:
            return gid
    return None


def orthologs_for_gene(gene_id: str, taxon: int | None = None) -> list[dict]:
    out: list[dict] = []
    page = None
    while True:
        url = (
            f"https://api.ncbi.nlm.nih.gov/datasets/v2/gene/id/{gene_id}/orthologs"
            f"?page_size=1000&returned_content=COMPLETE"
        )
        if taxon is not None:
            url += f"&taxon_filter={taxon}"
        if page:
            url += f"&page_token={page}"
        data = http_json(url) or {}
        genes = data.get("genes") or data.get("orthologs") or []
        if isinstance(genes, dict):
            genes = genes.get("genes") or []
        out.extend(genes)
        page = data.get("next_page_token") or data.get("page_token")
        if not page:
            break
        time.sleep(0.2)
    return out


def taxon_has_ncbi_genes(taxid: int) -> dict:
    data = http_json(
        f"https://api.ncbi.nlm.nih.gov/datasets/v2/gene/taxon/{taxid}?page_size=1&returned_content=IDS_ONLY"
    )
    if data is None:
        return {"indexed": False, "raw_keys": [], "n_reported": 0}
    genes = data.get("genes") or data.get("reports") or []
    total = data.get("total_count") or data.get("total") or len(genes)
    return {
        "indexed": bool(genes) or bool(total),
        "n_reported": total,
        "raw_keys": sorted((data or {}).keys())[:20],
    }


def parse_gene_rec(rec: dict) -> dict:
    gene = rec.get("gene") or rec
    gid = str(gene.get("gene_id") or rec.get("gene_id") or "")
    tax = gene.get("tax_id") or gene.get("taxonomy") or {}
    if isinstance(tax, dict):
        taxid = tax.get("tax_id") or tax.get("id")
        org = tax.get("organism_name") or tax.get("sci_name")
    else:
        taxid = tax
        org = gene.get("common_name")
    proteins = set()
    for prot in gene.get("proteins") or rec.get("proteins") or []:
        pid = prot.get("accession_version") or prot.get("accession")
        if pid:
            proteins.add(str(pid))
    assemblies = set()
    for ann in gene.get("annotations") or rec.get("annotations") or []:
        acc = ann.get("assembly_accession") or ann.get("assembly_accession_version")
        if acc:
            assemblies.add(str(acc))
        for loc in ann.get("genomic_locations") or []:
            gacc = loc.get("assembly_accession") or loc.get("genomic_accession")
            if gacc and str(gacc).startswith("GCF_"):
                assemblies.add(str(gacc))
    symbol = gene.get("symbol") or rec.get("symbol")
    desc = gene.get("description") or rec.get("description") or ""
    gtype = str(gene.get("type") or rec.get("type") or "")
    pseudo = "pseudo" in gtype.lower() or "pseudo" in str(desc).lower()
    return {
        "gene_id": gid,
        "tax_id": int(taxid) if str(taxid).isdigit() else taxid,
        "organism": org,
        "symbol": symbol,
        "proteins": sorted(proteins),
        "assemblies": sorted(assemblies),
        "description": desc,
        "type": gtype,
        "pseudo": pseudo,
    }


def download_annotation_zip(acc: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / f"{acc}_annotation.zip"
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    url = (
        "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/"
        f"{acc}/download?include_annotation_type=GENOME_GFF"
        "&include_annotation_type=GENOME_GBFF"
        "&include_annotation_type=PROT_FASTA"
    )
    print("download annotation", acc, flush=True)
    blob = http_bytes(url, timeout=420)
    if blob[:2] != b"PK":
        raise RuntimeError(f"annotation zip missing for {acc}: {blob[:160]!r}")
    dest.write_bytes(blob)
    return dest


def extract_zip(zpath: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    marker = dest_dir / "_extracted.ok"
    if marker.exists():
        return dest_dir
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest_dir)
    marker.write_text("ok\n", encoding="utf-8")
    return dest_dir


def find_first(root: Path, suffixes: tuple[str, ...]) -> Path | None:
    hits = []
    for p in root.rglob("*"):
        if p.is_file() and p.name.lower().endswith(suffixes):
            hits.append(p)
    hits.sort(key=lambda p: (len(str(p)), str(p)))
    return hits[0] if hits else None


def opener(path: Path):
    return gzip.open if path.suffix == ".gz" or path.name.endswith(".gz") else open


def parse_gff_all_cds(gff_path: Path) -> list[dict]:
    rows = []
    with opener(gff_path)(gff_path, "rt", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if not ln.strip() or ln.startswith("#"):
                continue
            parts = ln.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            seqid, source, ftype, start, end, _sc, strand, _ph, attrs = parts[:9]
            ad = {}
            for item in attrs.split(";"):
                if "=" not in item:
                    continue
                k, v = item.split("=", 1)
                ad[k] = v
            gene_ids = re.findall(r"GeneID:(\d+)", attrs)
            protein_ids = re.findall(r"(?:NP|WP|YP|AP|XP)_\d+\.\d+", attrs)
            if ad.get("protein_id"):
                protein_ids.append(ad["protein_id"])
            protein_ids = list(dict.fromkeys(protein_ids))
            rows.append(
                {
                    "seqid": seqid,
                    "source": source,
                    "type": ftype,
                    "start": int(start),
                    "end": int(end),
                    "strand": strand,
                    "gene": ad.get("gene") or ad.get("Name"),
                    "product": ad.get("product"),
                    "locus_tag": ad.get("locus_tag"),
                    "gene_biotype": ad.get("gene_biotype"),
                    "note": ad.get("Note"),
                    "inference": ad.get("inference"),
                    "gene_ids": gene_ids,
                    "protein_ids": protein_ids,
                    "pseudo": "pseudo=true" in attrs.lower() or "pseudogene" in (ad.get("gene_biotype") or "").lower(),
                    "partial": "partial=true" in attrs.lower(),
                    "attrs": ad,
                }
            )
    return rows


def parse_gbff_amr(gbff_path: Path) -> dict:
    with opener(gbff_path)(gbff_path, "rt", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    header = text[:20000]
    sw = None
    db = None
    for pat, key in (
        (r"AMRFinderPlus-Software-Version\s*::\s*([^\n]+)", "software"),
        (r"AMRFinderPlus software[:\s]+([0-9][^\n;]+)", "software"),
        (r"AMRFinderPlus-Database-Version\s*::\s*([^\n]+)", "database"),
        (r"AMRFinderPlus database[:\s]+([^\n;]+)", "database"),
    ):
        m = re.search(pat, header, flags=re.I)
        if m:
            val = m.group(1).strip()
            if key == "software" and not sw:
                sw = val
            if key == "database" and not db:
                db = val
    calls = []
    for m in re.finditer(r"/inference=\"([^\"]*AMRFinder[^\"]*)\"", text, flags=re.I):
        inf = m.group(1)
        window = text[max(0, m.start() - 1200) : m.end() + 1200]
        gene = None
        gm = re.search(r"/gene=\"([^\"]+)\"", window)
        if gm:
            gene = gm.group(1)
        product = None
        pm = re.search(r"/product=\"([^\"]+)\"", window)
        if pm:
            product = pm.group(1)
        protein = None
        xm = re.search(r"/protein_id=\"([^\"]+)\"", window)
        if xm:
            protein = xm.group(1)
        locus = None
        lm = re.search(r"/locus_tag=\"([^\"]+)\"", window)
        if lm:
            locus = lm.group(1)
        element = None
        em = re.search(r"AMRFinderPlus:([^:\"]+):([^:\"]+)", inf)
        if em:
            if not sw:
                sw = em.group(1)
            if not db:
                db = em.group(2)
            element = inf
        calls.append(
            {
                "gene": gene,
                "product": product,
                "protein_id": protein,
                "locus_tag": locus,
                "inference": inf,
                "amrfinder_element": element,
            }
        )
    tet_windows = []
    for m in re.finditer(r"/gene=\"([^\"]*tet[^\"]*)\"", text, flags=re.I):
        gene = m.group(1)
        window = text[max(0, m.start() - 900) : m.end() + 900]
        product = None
        pm = re.search(r"/product=\"([^\"]+)\"", window)
        if pm:
            product = pm.group(1)
        note = None
        nm = re.search(r"/note=\"([^\"]+)\"", window)
        if nm:
            note = nm.group(1)
        inference = None
        im = re.search(r"/inference=\"([^\"]+)\"", window)
        if im:
            inference = im.group(1)
        protein = None
        xm = re.search(r"/protein_id=\"([^\"]+)\"", window)
        if xm:
            protein = xm.group(1)
        locus = None
        lm = re.search(r"/locus_tag=\"([^\"]+)\"", window)
        if lm:
            locus = lm.group(1)
        tet_windows.append(
            {
                "gene": gene,
                "product": product,
                "note": note,
                "inference": inference,
                "protein_id": protein,
                "locus_tag": locus,
                "amrfinder_mentioned": "amrfinder" in window.lower(),
            }
        )
    return {
        "amrfinder_software_version": sw,
        "amrfinder_database_version": db,
        "amrfinder_calls": calls,
        "tet_gene_windows": tet_windows,
        "n_amrfinder_inference": len(calls),
        "header_has_amrfinder": "amrfinder" in header.lower(),
    }


def ftp_amrfinder_report(ftp_path: str, acc: str) -> dict:
    if not ftp_path:
        return {"found": False, "reason": "no ftp_path"}
    base = ftp_path.rstrip("/") + "/"
    listing = http_text(base, timeout=60)
    hits = []
    if listing:
        for name in re.findall(r"href=\"([^\"]+)\"", listing, flags=re.I):
            low = name.lower()
            if "amr" in low and any(low.endswith(s) for s in (".tsv", ".txt", ".tsv.gz", ".txt.gz")):
                hits.append(name)
        if not hits:
            for name in re.findall(r"([\w.\-]+amrfinderplus[\w.\-]*)", listing, flags=re.I):
                hits.append(name)
    rows = []
    used = None
    raw_head = None
    for name in hits[:6]:
        url = name if name.startswith("http") else base + name.split("/")[-1]
        try:
            blob = http_bytes(url, timeout=90)
        except Exception:
            continue
        text = blob.decode("utf-8", errors="replace")
        used = url
        raw_head = "\n".join(text.splitlines()[:30])
        for ln in text.splitlines():
            if not ln.strip() or ln.startswith("#"):
                continue
            parts = re.split(r"\t|,", ln)
            if any("tet" in p.lower() for p in parts):
                rows.append({"line": ln, "parts": parts[:12]})
        break
    return {
        "found": bool(used),
        "url": used,
        "candidate_names": hits[:12],
        "tet_rows": rows,
        "raw_head": raw_head,
        "listing_ok": listing is not None,
    }


def download_seed_faa(pid: str) -> Path:
    dest = CACHE / f"{pid}.faa"
    if dest.exists() and dest.stat().st_size > 50:
        text = dest.read_text(encoding="utf-8", errors="replace")
        if text.lstrip().startswith(">"):
            return dest
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=protein&id={pid}&rettype=fasta&retmode=text"
    )
    text = http_bytes(url, timeout=60).decode("utf-8", errors="replace")
    if not text.lstrip().startswith(">"):
        raise RuntimeError(f"seed fasta failed for {pid}: {text[:180]!r}")
    dest.write_text(text, encoding="utf-8")
    time.sleep(0.35)
    return dest


def parse_fasta_headers(faa: Path) -> dict[str, str]:
    headers = {}
    acc = None
    with faa.open("rt", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if ln.startswith(">"):
                acc = ln[1:].split()[0]
                headers[acc] = ln[1:].strip()
    return headers


def _merge_intervals(spans: list[tuple[int, int]]) -> int:
    if not spans:
        return 0
    spans = sorted(spans)
    total = 0
    cur_a, cur_b = spans[0]
    for a, b in spans[1:]:
        if a <= cur_b + 1:
            cur_b = max(cur_b, b)
        else:
            total += cur_b - cur_a + 1
            cur_a, cur_b = a, b
    total += cur_b - cur_a + 1
    return total


def run_phmmer(seed_fa: Path, proteome: Path, out_prefix: Path, acc: str | None = None) -> dict:
    tbl = Path(str(out_prefix) + ".tbl")
    dom = Path(str(out_prefix) + ".domtbl")
    if acc and not tbl.exists():
        legacy_tbl = CACHE / f"{acc.split('.')[0]}.tbl"
        legacy_dom = CACHE / f"{acc.split('.')[0]}.domtbl"
        if legacy_tbl.exists() and legacy_dom.exists():
            tbl, dom = legacy_tbl, legacy_dom
    if not (tbl.exists() and dom.exists() and tbl.stat().st_size > 0):
        seed_w = to_wsl(seed_fa)
        prot_w = to_wsl(proteome)
        tbl_w = to_wsl(tbl)
        dom_w = to_wsl(dom)
        cmd = [
            "wsl",
            "-e",
            "phmmer",
            "--tblout",
            tbl_w,
            "--domtblout",
            dom_w,
            "-E",
            "1e-5",
            "--noali",
            seed_w,
            prot_w,
        ]
        print("phmmer", seed_fa.name, proteome.name, flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"phmmer failed: {proc.stderr[-500:] or proc.stdout[-500:]}")
    seq_hits = {}
    with tbl.open("rt", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if not ln.strip() or ln.startswith("#"):
                continue
            p = ln.split()
            if len(p) < 6:
                continue
            seq_hits[p[0]] = {
                "target": p[0],
                "evalue": float(p[4]),
                "score": float(p[5]),
                "description": " ".join(p[18:]) if len(p) > 18 else "",
            }
    domains: dict[str, list[dict]] = {}
    qlen = None
    with dom.open("rt", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if not ln.strip() or ln.startswith("#"):
                continue
            p = ln.split()
            if len(p) < 23:
                continue
            target = p[0]
            qlen = int(p[5]) if p[5].isdigit() else qlen
            tlen = int(p[2]) if p[2].isdigit() else None
            hmm_from = int(p[15])
            hmm_to = int(p[16])
            ali_from = int(p[17])
            ali_to = int(p[18])
            domains.setdefault(target, []).append(
                {
                    "tlen": tlen,
                    "hmm_from": hmm_from,
                    "hmm_to": hmm_to,
                    "ali_from": ali_from,
                    "ali_to": ali_to,
                    "dom_evalue": float(p[12]),
                }
            )
    hits = []
    for target, rec in seq_hits.items():
        doms = domains.get(target) or []
        tlen = doms[0]["tlen"] if doms else None
        merged = _merge_intervals([(d["hmm_from"], d["hmm_to"]) for d in doms]) if doms else 0
        env_qcov = None
        if doms and qlen:
            env_qcov = (max(d["hmm_to"] for d in doms) - min(d["hmm_from"] for d in doms) + 1) / qlen
        qcov = env_qcov
        hits.append(
            {
                "target": target,
                "tlen": tlen,
                "evalue": rec["evalue"],
                "score": rec["score"],
                "qlen": qlen,
                "n_domains": len(doms),
                "hmm_coverage_aa": merged,
                "qcov": qcov,
                "qcov_envelope": env_qcov,
                "description": rec.get("description"),
            }
        )
    hits.sort(key=lambda r: r["evalue"])
    return {"qlen": qlen, "n_hits_e1e5": len(hits), "hits": hits}


def cluster_loci(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["seqid"], []).append(r)
    loci = []
    for seqid, items in grouped.items():
        items.sort(key=lambda r: (r["start"], r["end"]))
        cur = None
        for r in items:
            if cur is None:
                cur = dict(r)
                cur["members"] = [r]
                continue
            if r["start"] <= cur["end"] + 30 and r.get("strand") == cur.get("strand"):
                cur["end"] = max(cur["end"], r["end"])
                cur["members"].append(r)
                for pid in r.get("protein_ids") or []:
                    cur.setdefault("protein_ids", [])
                    if pid not in cur["protein_ids"]:
                        cur["protein_ids"].append(pid)
            else:
                loci.append(cur)
                cur = dict(r)
                cur["members"] = [r]
        if cur:
            loci.append(cur)
    return loci


def compact_name(val: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (val or "").lower())


def tet_class_from_name(name: str | None) -> str | None:
    raw = (name or "").strip()
    if not raw:
        return None
    low = raw.lower().replace(" ", "")
    if low.startswith("tetr") and not low.startswith("tet(a)") and not low.startswith("tet(b)"):
        # tetR / TetR(A) repressor, tetratricopeptide, etc.
        if re.fullmatch(r"tetr(\(a\))?", low):
            return None
        if "repressor" in raw.lower():
            return None
    if re.fullmatch(r"tet\([ab]\)", low) or re.fullmatch(r"tet[ab]", low):
        letter = "A" if low[-1] == "a" or low.endswith("(a)") else "B"
        return f"tet({letter})"
    m = re.fullmatch(r"tet\(([a-z0-9]+)\)", low)
    if m:
        letter = m.group(1)
        if letter in {"a", "b"}:
            return f"tet({letter.upper()})"
        return f"tet({letter.upper()})"
    return None


def pgap_annotation_meta(acc: str) -> dict:
    report = CACHE / f"{acc}_extracted" / "ncbi_dataset" / "data" / "assembly_data_report.jsonl"
    if not report.exists():
        hits = list((CACHE / f"{acc}_extracted").rglob("assembly_data_report.jsonl"))
        report = hits[0] if hits else None
    if report is None or not report.exists():
        return {}
    rec = json.loads(report.read_text(encoding="utf-8", errors="replace").splitlines()[0])
    info = rec.get("annotationInfo") or {}
    return {
        "pgap_pipeline": info.get("pipeline"),
        "pgap_software_version": info.get("softwareVersion"),
        "annotation_name": info.get("name"),
        "annotation_release_date": info.get("releaseDate"),
        "annotation_method": info.get("method"),
        "annotation_provider": info.get("provider"),
    }


def assign_tet(case: dict, gff_rows: list[dict], gbff: dict, ftp: dict) -> dict:
    calls = []
    for r in gff_rows:
        if r.get("type") not in {"CDS", "gene"}:
            continue
        gene = r.get("gene")
        product = r.get("product")
        klass = tet_class_from_name(gene)
        related_klass = None
        if klass is None:
            related_klass = tet_class_from_name(gene)  # None for tetR
            prod_l = (product or "").lower()
            gene_l = (gene or "").lower()
            if re.search(r"\btet\([c-z0-9]+\)\b", gene_l) or re.search(r"\btet[c-z]\b", gene_l):
                related_klass = gene
            elif "tetracycline" in prod_l and "efflux" in prod_l and klass is None:
                if tet_class_from_name(gene) is None and "tet(a)" not in prod_l and "tet(b)" not in prod_l:
                    related_klass = product
        if klass is None and related_klass is None:
            continue
        calls.append(
            {
                "gene": gene,
                "product": product,
                "protein_id": (r.get("protein_ids") or [None])[0],
                "locus_tag": r.get("locus_tag"),
                "seqid": r.get("seqid"),
                "start": r.get("start"),
                "end": r.get("end"),
                "class_parsed": klass,
                "related_label": related_klass,
                "pseudo": bool(r.get("pseudo")),
                "partial": bool(r.get("partial")),
                "inference": r.get("inference"),
                "source": r.get("source"),
                "type": r.get("type"),
            }
        )
    exact = [c for c in calls if c.get("class_parsed") in {"tet(A)", "tet(B)"} and c.get("type") == "CDS"]
    related = [c for c in calls if c.get("class_parsed") not in {"tet(A)", "tet(B)"} and c.get("type") == "CDS"]
    exact_complete = [c for c in exact if not c.get("pseudo") and not c.get("partial")]
    exact_bad = [c for c in exact if c.get("pseudo") or c.get("partial")]
    related = [c for c in related if c.get("related_label") or (c.get("gene") or "").lower() not in {"tetr(a)", "tetr"}]
    pgap = pgap_annotation_meta(case["assembly_accession"])
    sw = gbff.get("amrfinder_software_version")
    dbv = gbff.get("amrfinder_database_version")
    if not sw:
        for c in gbff.get("amrfinder_calls") or []:
            inf = c.get("inference") or ""
            m = re.search(r"AMRFinderPlus:([^:]+):([^:\"\s]+)", inf)
            if m:
                sw = m.group(1)
                dbv = dbv or m.group(2)
                break
    source = (
        "Post-lock NCBI RefSeq/PGAP AMR gene annotation on this assembly "
        f"(PGAP {pgap.get('pgap_software_version') or 'unspecified'}; annotation {pgap.get('annotation_name')}; "
        f"release {pgap.get('annotation_release_date')}). "
        "PGAP uses AMRFinderPlus/NCBIfam-AMRFinder for AMR genes. "
        "This GBFF did not embed AMRFinderPlus software/database version strings. "
        "Frozen FAMILY positives = tet(A) OR tet(B); tet(C) not counted. tetR is not a family member."
    )
    if exact_complete:
        decision = "POSITIVE"
        status = "EVALUABLE"
        rationale = (
            f"AMRFinderPlus/PGAP AMR call on this assembly includes complete non-pseudo "
            f"tet(A)/tet(B): {sorted({c.get('class_parsed') or c.get('gene') for c in exact_complete})}."
        )
    elif exact_bad:
        decision = None
        status = "TRUTH_UNCERTAIN"
        rationale = "tet(A)/tet(B) evidence is present but marked pseudo or partial."
    else:
        decision = "NEGATIVE"
        status = "EVALUABLE"
        if related:
            rationale = (
                "AMRFinderPlus/PGAP has related tetracycline gene(s) "
                f"{sorted({c.get('class_parsed') or c.get('gene') for c in related})} "
                "without tet(A) or tet(B). tet(C) and other classes are not FAMILY positives under the frozen contract."
            )
        else:
            rationale = (
                "No tet(A) or tet(B) AMRFinderPlus/PGAP AMR gene call on this assembly. "
                "Absence of a frozen-family call is scored FAMILY negative."
            )
    supporting = []
    for c in exact_complete or exact or related:
        supporting.append(
            {
                "gene": c.get("gene"),
                "product": c.get("product"),
                "protein_id": c.get("protein_id"),
                "locus_tag": c.get("locus_tag"),
                "parsed_class": c.get("class_parsed"),
            }
        )
    return {
        "execution_position": case["execution_position"],
        "assembly_accession": case["assembly_accession"],
        "organism": case.get("organism"),
        "taxonomy_id": case.get("taxonomy_id"),
        "target": "tetA_tetracycline_efflux",
        "endpoint": "FAMILY_PRESENCE_ABSENCE",
        "truth_status": status,
        "truth": decision,
        "family_members_counted_as_positive": ["tet(A)", "tet(B)"],
        "tetC_counted_as_positive": False,
        "amrfinder_software_version": sw,
        "amrfinder_database_version": dbv,
        "pgap_annotation": pgap,
        "amrfinder_source": source,
        "exact_calls": exact,
        "related_calls": related,
        "supporting_accessions": supporting[:12],
        "ftp_amrfinder_report": {
            "found": ftp.get("found"),
            "url": ftp.get("url"),
            "n_tet_rows": len(ftp.get("tet_rows") or []),
        },
        "gbff_n_amrfinder_inference": gbff.get("n_amrfinder_inference"),
        "short_rationale": rationale,
        "pgap_used_as_sole_truth": False,
        "predictions_consulted": False,
    }


def genuine_phmmer_hits(target: str, phm: dict) -> list[dict]:
    seed = SEEDS[target]
    genuine = []
    seen = set()
    for h in phm.get("hits") or []:
        if h.get("evalue") is None or h["evalue"] > seed["evalue"]:
            continue
        qcov = h.get("qcov") or 0
        tlen = h.get("tlen") or 0
        if qcov < seed["min_qcov"]:
            continue
        if tlen and (tlen < seed["min_len"] or tlen > seed["max_len"]):
            continue
        key = h["target"]
        if key in seen:
            continue
        seen.add(key)
        genuine.append(h)
    return genuine


def map_proteins_to_loci(proteins: set[str], gff_rows: list[dict], gene_ids: set[str] | None = None) -> list[dict]:
    gene_ids = gene_ids or set()
    cds = []
    for r in gff_rows:
        if r.get("type") != "CDS":
            continue
        pids = set(r.get("protein_ids") or [])
        gids = set(r.get("gene_ids") or [])
        if pids & proteins or gids & gene_ids:
            cds.append(r)
    return cluster_loci([c for c in cds if not c.get("pseudo") and not c.get("partial")])


def assign_ortholog(case: dict, target: str, gff_rows: list[dict], phm: dict, headers: dict) -> dict:
    seed = SEEDS[target]
    taxid = int(case["taxonomy_id"])
    acc = case["assembly_accession"]
    taxon_index = taxon_has_ncbi_genes(taxid)
    time.sleep(0.25)
    orth_raw = []
    taxon_query_ok = False
    taxon_query_error = None
    try:
        orth_raw = orthologs_for_gene(seed["gene_id"], taxon=taxid)
        taxon_query_ok = True
    except Exception as exc:
        taxon_query_error = str(exc)
        taxon_query_ok = False
    parsed = [parse_gene_rec(x) for x in orth_raw]
    orth_proteins = {p for rec in parsed for p in rec.get("proteins") or []}
    orth_gene_ids = {rec["gene_id"] for rec in parsed if rec.get("gene_id")}
    on_this_assembly = [rec for rec in parsed if acc in (rec.get("assemblies") or [])]
    loci_from_orth = map_proteins_to_loci(orth_proteins, gff_rows, orth_gene_ids)
    genuine = genuine_phmmer_hits(target, phm)
    genuine_proteins = {h["target"] for h in genuine}
    loci_from_phmmer = map_proteins_to_loci(genuine_proteins, gff_rows)
    pgap_symbol_cds = []
    related_cds = []
    for r in gff_rows:
        if r.get("type") != "CDS":
            continue
        g = (r.get("gene") or "").lower()
        if g in {s.lower() for s in seed["symbols"]}:
            pgap_symbol_cds.append(r)
        if g in {s.lower() for s in seed["related_symbols"]}:
            related_cds.append(r)
    corroboration = []
    if on_this_assembly or loci_from_orth:
        corroboration.append("NCBI_Gene_Orthologs")
    if genuine:
        corroboration.append("independent_phmmer_seed_vs_proteome")
    if pgap_symbol_cds:
        corroboration.append("PGAP_symbol_corroboration_only")

    def pack_loci(loci: list[dict], extra_by_protein: dict | None = None) -> list[dict]:
        out = []
        for loc in loci:
            pids = loc.get("protein_ids") or []
            ph = None
            for pid in pids:
                if extra_by_protein and pid in extra_by_protein:
                    ph = extra_by_protein[pid]
                    break
            out.append(
                {
                    "seqid": loc.get("seqid"),
                    "start": loc.get("start"),
                    "end": loc.get("end"),
                    "strand": loc.get("strand"),
                    "locus_tag": loc.get("locus_tag"),
                    "gene": loc.get("gene"),
                    "product": loc.get("product"),
                    "protein_ids": pids,
                    "gene_ids": loc.get("gene_ids"),
                    "phmmer": ph,
                }
            )
        return out

    ph_by_prot = {h["target"]: h for h in genuine}
    orthology_present = bool(loci_from_orth) or bool(on_this_assembly and loci_from_phmmer)
    phmmer_present = bool(loci_from_phmmer)

    if target == "tuf_EF_Tu":
        endpoint = "EXACT_MULTIPLICITY"
        chosen_loci = loci_from_orth or loci_from_phmmer
        if loci_from_orth and loci_from_phmmer:
            # prefer intersection of genuine orthologous loci
            orth_pids = {p for loc in loci_from_orth for p in (loc.get("protein_ids") or [])}
            phm_pids = {p for loc in loci_from_phmmer for p in (loc.get("protein_ids") or [])}
            keep = orth_pids & phm_pids if orth_pids & phm_pids else orth_pids
            chosen_loci = [loc for loc in loci_from_orth if set(loc.get("protein_ids") or []) & keep] or loci_from_orth
        if not chosen_loci and genuine:
            # protein hit exists but GFF mapping failed
            status = "TRUTH_UNCERTAIN"
            decision = None
            multiplicity = None
            rationale = (
                "Independent phmmer found EF-Tu-like complete hits but they could not be mapped to distinct genomic loci."
            )
        elif not chosen_loci:
            if taxon_query_ok and taxon_index.get("indexed") and not orth_proteins:
                status = "EVALUABLE"
                decision = 0
                multiplicity = 0
                rationale = (
                    f"NCBI Gene Orthologs of authentic E. coli tufA {seed['protein_id']} / gene_id {seed['gene_id']} "
                    f"returned no member in taxid {taxid}, and independent phmmer of that seed found no complete "
                    "EF-Tu-length hit on this proteome."
                )
            elif (not taxon_index.get("indexed")) and not genuine:
                status = "EVALUABLE"
                decision = 0
                multiplicity = 0
                rationale = (
                    "NCBI Gene Orthologs does not index this taxid. Independent phmmer of authentic tufA "
                    f"{seed['protein_id']} against all proteins of this assembly found no complete EF-Tu ortholog."
                )
            else:
                status = "TRUTH_UNCERTAIN"
                decision = None
                multiplicity = None
                rationale = "Independent orthology was incomplete for EF-Tu copy-number assignment."
        else:
            status = "EVALUABLE"
            multiplicity = len(chosen_loci)
            decision = multiplicity
            src = "NCBI Gene Orthologs" if loci_from_orth else "independent phmmer mapping of authentic tufA"
            rationale = (
                f"{src} identified {multiplicity} distinct complete non-pseudo EF-Tu locus/loci. "
                "Counts are genomic intervals, not collapsed annotation names. PGAP tuf/tufA/tufB symbols were not used as the sole standard."
            )
        packed = pack_loci(chosen_loci, ph_by_prot)
        return {
            "execution_position": case["execution_position"],
            "assembly_accession": acc,
            "organism": case.get("organism"),
            "taxonomy_id": taxid,
            "target": target,
            "endpoint": endpoint,
            "truth_status": status,
            "truth": decision,
            "multiplicity": multiplicity,
            "genuine_tuf_loci": packed,
            "orthology_source": (
                "NCBI Gene Orthologs seed tufA NP_417798.1 / gene_id 947838; "
                "independent post-lock phmmer of that seed against all proteins of this assembly; "
                "PGAP symbols corroboration only. NP_418240.1 was not used because the current NCBI record is not EF-Tu."
            ),
            "ncbi_gene_orthologs": {
                "seed_protein": seed["protein_id"],
                "seed_gene_id": seed["gene_id"],
                "taxon_query_ok": taxon_query_ok,
                "taxon_query_error": taxon_query_error,
                "taxon_indexed_in_ncbi_gene": taxon_index,
                "n_ortholog_records_in_taxon": len(parsed),
                "ortholog_gene_ids": sorted(orth_gene_ids),
                "ortholog_proteins": sorted(orth_proteins)[:40],
                "records_annotated_on_this_assembly": [
                    {k: rec.get(k) for k in ("gene_id", "symbol", "proteins", "description")}
                    for rec in on_this_assembly[:12]
                ],
            },
            "phmmer": {
                "seed": seed["protein_id"],
                "n_hits_e1e5": phm.get("n_hits_e1e5"),
                "genuine_hits": genuine[:20],
            },
            "pgap_symbol_cds_count": len(pgap_symbol_cds),
            "related_symbol_cds_count": len(related_cds),
            "corroboration": corroboration,
            "short_rationale": rationale,
            "pgap_used_as_sole_truth": False,
            "predictions_consulted": False,
        }

    # presence/absence for rpoB and lacZ
    endpoint = "ORTHOLOGOUS_GENE_PRESENCE_ABSENCE"
    if target == "lacZ_beta_galactosidase" and pgap_symbol_cds and not (orthology_present or phmmer_present):
        # name equality insufficient
        pass
    present_loci = loci_from_orth or loci_from_phmmer
    if loci_from_orth and loci_from_phmmer:
        present_loci = loci_from_orth
    if present_loci:
        status = "EVALUABLE"
        decision = "POSITIVE"
        src = []
        if loci_from_orth:
            src.append("NCBI Gene Orthologs member mapped to a complete non-pseudo CDS on this assembly")
        if loci_from_phmmer:
            src.append("independent phmmer of the frozen/authentic seed produced a complete orthologous hit")
        rationale = "; ".join(src) + ". PGAP gene-name equality was not used as the sole standard."
        if target == "lacZ_beta_galactosidase":
            rationale += " Other beta-galactosidases were not treated as lacZ."
    elif taxon_query_ok and taxon_index.get("indexed") and not orth_proteins and not genuine:
        status = "EVALUABLE"
        decision = "NEGATIVE"
        rationale = (
            f"NCBI Gene Orthologs of seed {seed['protein_id']} / gene_id {seed['gene_id']} was applied to taxid {taxid} "
            "and returned no member; independent phmmer of that seed against this proteome also found no complete "
            "orthologous hit."
        )
        if target == "lacZ_beta_galactosidase":
            rationale += " Generic beta-galactosidase products without LacZ orthology were not counted as lacZ."
    elif (not taxon_index.get("indexed") or not taxon_query_ok) and not genuine:
        # no NCBI coverage and no phmmer hit: Cohort C treated this as NEGATIVE when phmmer of the seed had zero hits
        status = "EVALUABLE"
        decision = "NEGATIVE"
        rationale = (
            f"NCBI Gene Orthologs does not reliably index taxid {taxid}. Independent phmmer of seed "
            f"{seed['protein_id']} against all proteins of this assembly at the frozen-seed completeness thresholds "
            "returned no genuine orthologous hit. Absence is assigned from the independent seed search, not from PGAP name equality."
        )
        if target == "lacZ_beta_galactosidase":
            rationale += " Beta-galactosidase-like names without LacZ seed orthology were not counted."
    elif genuine and not present_loci:
        status = "TRUTH_UNCERTAIN"
        decision = None
        rationale = "Seed-search hits exist but could not be mapped to complete non-pseudo loci on this assembly."
    elif pgap_symbol_cds and not present_loci:
        status = "TRUTH_UNCERTAIN"
        decision = None
        rationale = "PGAP gene symbol matches without independent orthology on this assembly; name equality is insufficient."
    else:
        status = "TRUTH_UNCERTAIN"
        decision = None
        rationale = "Independent orthology could not be established reliably."

    packed = pack_loci(present_loci, {h["target"]: h for h in genuine})
    source = (
        f"NCBI Gene Orthologs seed {seed['protein_id']} / gene_id {seed['gene_id']}; "
        "independent post-lock phmmer of that seed against all proteins of this assembly; "
        "PGAP gene symbol used only as corroboration"
    )
    return {
        "execution_position": case["execution_position"],
        "assembly_accession": acc,
        "organism": case.get("organism"),
        "taxonomy_id": taxid,
        "target": target,
        "endpoint": endpoint,
        "truth_status": status,
        "truth": decision,
        "candidate_loci": packed,
        "orthology_source": source,
        "ncbi_gene_orthologs": {
            "seed_protein": seed["protein_id"],
            "seed_gene_id": seed["gene_id"],
            "taxon_query_ok": taxon_query_ok,
            "taxon_query_error": taxon_query_error,
            "taxon_indexed_in_ncbi_gene": taxon_index,
            "n_ortholog_records_in_taxon": len(parsed),
            "ortholog_gene_ids": sorted(orth_gene_ids),
            "ortholog_proteins": sorted(orth_proteins)[:40],
            "records_annotated_on_this_assembly": [
                {k: rec.get(k) for k in ("gene_id", "symbol", "proteins", "description")}
                for rec in on_this_assembly[:12]
            ],
        },
        "phmmer": {
            "seed": seed["protein_id"],
            "n_hits_e1e5": phm.get("n_hits_e1e5"),
            "genuine_hits": genuine[:20],
        },
        "pgap_symbol_cds_count": len(pgap_symbol_cds),
        "related_symbol_cds_count": len(related_cds),
        "corroboration": corroboration,
        "short_rationale": rationale,
        "pgap_used_as_sole_truth": False,
        "predictions_consulted": False,
    }


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    hashes = verify_locks()
    struct = confirm_prediction_structure()
    print("LOCK_VERIFIED", json.dumps(hashes, indent=2), flush=True)
    print("STRUCTURAL_COUNTS", {k: (v if k == "agentic_pos7" else v.get("n") if isinstance(v, dict) and "n" in v else v) for k, v in struct.items()}, flush=True)
    print("AGENTIC_POS7", struct["agentic_pos7"], flush=True)
    print("TRUTH_ASSIGNMENT_START predictions_not_used=True", flush=True)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = sorted(manifest["cases"], key=lambda r: r["execution_position"])
    if len(cases) != 8:
        raise SystemExit(f"manifest cases {len(cases)}")

    for target, seed in SEEDS.items():
        if seed["gene_id"] is None:
            seed["gene_id"] = gene_id_for_protein(seed["protein_id"])
            print(f"seed_gene_id {target} -> {seed['gene_id']}", flush=True)
        download_seed_faa(seed["protein_id"])

    labels = []
    proteome_phmmer: dict[str, dict] = {}
    gff_cache: dict[str, list[dict]] = {}
    gbff_cache: dict[str, dict] = {}
    header_cache: dict[str, dict] = {}
    ftp_cache: dict[str, dict] = {}

    unique_acc = list(dict.fromkeys(c["assembly_accession"] for c in cases))
    for acc in unique_acc:
        rec = next(c for c in cases if c["assembly_accession"] == acc)
        zpath = download_annotation_zip(acc)
        extracted = extract_zip(zpath, CACHE / f"{acc}_extracted")
        gff = find_first(extracted, (".gff", ".gff.gz", ".gff3", ".gff3.gz"))
        gbff = find_first(extracted, (".gbff", ".gbff.gz", ".gbk", ".gbk.gz"))
        faa = find_first(extracted, (".faa", ".faa.gz", ".fasta", ".fasta.gz"))
        print(acc, "gff", gff, "gbff", gbff, "faa", faa, flush=True)
        if gff is None or faa is None:
            raise SystemExit(f"missing annotation files for {acc}")
        gff_cache[acc] = parse_gff_all_cds(gff)
        gbff_cache[acc] = parse_gbff_amr(gbff) if gbff else {}
        header_cache[acc] = parse_fasta_headers(faa)
        ftp_cache[acc] = ftp_amrfinder_report(rec.get("ftp_path") or "", acc)
        proteome_phmmer[acc] = {"faa": faa}

    needed_seeds = {}
    for case in cases:
        if case["target"] in SEEDS:
            needed_seeds.setdefault(case["assembly_accession"], set()).add(case["target"])

    phmmer_results: dict[tuple[str, str], dict] = {}
    for acc, targets in needed_seeds.items():
        faa = proteome_phmmer[acc]["faa"]
        for target in sorted(targets):
            seed_fa = CACHE / f"{SEEDS[target]['protein_id']}.faa"
            prefix = CACHE / f"{acc}_{target}_phmmer"
            phmmer_results[(acc, target)] = run_phmmer(seed_fa, faa, prefix, acc=acc)

    for case in cases:
        acc = case["assembly_accession"]
        target = case["target"]
        print(f"ASSIGN pos={case['execution_position']} {acc} {target}", flush=True)
        if target == "tetA_tetracycline_efflux":
            labels.append(assign_tet(case, gff_cache[acc], gbff_cache[acc], ftp_cache[acc]))
        else:
            labels.append(
                assign_ortholog(
                    case,
                    target,
                    gff_cache[acc],
                    phmmer_results[(acc, target)],
                    header_cache[acc],
                )
            )

    labels.sort(key=lambda r: r["execution_position"])
    if [r["execution_position"] for r in labels] != list(range(1, 9)):
        raise SystemExit("positions not 1-8")
    payload = {
        "kind": "D8_EXTERNAL_TRUTH_LOCKED",
        "cohort": "D8_MINI_EXTERNAL",
        "created_utc": utc_now(),
        "predictions_consulted": False,
        "d20_touched": False,
        "lock_hashes_verified_before_truth": hashes,
        "agentic_position_7_failure_confirmed_before_truth": struct["agentic_pos7"],
        "frozen_family_tet_positives": ["tet(A)", "tet(B)"],
        "tetC_not_a_frozen_member": True,
        "tuf_seed_used": "NP_417798.1 / gene_id 947838 (authentic tufA); NP_418240.1 not used",
        "n_cases": 8,
        "cases": labels,
    }
    tmp = OUT / "D8_EXTERNAL_TRUTH_LOCKED.json.tmp"
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(TRUTH)
    digest = sha256_file(TRUTH)
    sidecar = OUT / "D8_EXTERNAL_TRUTH_LOCKED.json.sha256.json"
    sidecar.write_text(
        json.dumps(
            {
                "file": "D8_EXTERNAL_TRUTH_LOCKED.json",
                "sha256": digest,
                "hashed_utc": utc_now(),
                "hashed_before_prediction_join": True,
                "predictions_consulted": False,
                "d20_touched": False,
                "n_cases": 8,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("D8_TRUTH_LOCKED", digest, flush=True)
    for r in labels:
        print(
            r["execution_position"],
            r["assembly_accession"],
            r["target"],
            r.get("truth_status"),
            r.get("truth"),
            (r.get("short_rationale") or "")[:200],
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
