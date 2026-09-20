#!/usr/bin/env python3
"""Download proteomes and run independent seed searches for pilot5 labels."""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "external_validation_agentic" / "cohort_C_pilot5_label_cache"
UA = "GenomeSkeptic-external-validation/cohort-C-pilot5-unblind-labels-only"
ACCS = ["GCF_055394735.1", "GCF_055378285.1"]
SEEDS = {
    "rpoB_RNAP_beta": "NP_418414.1",
    "tuf_EF_Tu": "NP_418240.1",
    "lacZ_beta_galactosidase": "NP_414878.1",
    "tetA_P02982_proxy": "NP_052923.1",  # not used as tet truth; downloaded only if needed
}


def http_bytes(url: str, timeout: int = 300) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(5):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last)


def download_proteome(acc: str) -> Path:
    dest = CACHE / f"{acc}.faa"
    if dest.exists() and dest.stat().st_size > 1000:
        print("have proteome", acc, dest.stat().st_size, flush=True)
        return dest
    url = (
        "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/"
        f"{acc}/download?include_annotation_type=PROT_FASTA"
    )
    print("download proteome", acc, flush=True)
    blob = http_bytes(url)
    if blob[:2] != b"PK":
        raise RuntimeError(blob[:120])
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".faa") or n.endswith(".fasta")]
        if not names:
            raise RuntimeError(zf.namelist()[:20])
        dest.write_bytes(zf.read(names[0]))
    print("wrote", dest, dest.stat().st_size, flush=True)
    return dest


def download_seed(pid: str) -> Path:
    dest = CACHE / f"{pid}.faa"
    if dest.exists() and dest.stat().st_size > 50:
        return dest
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=protein&id={pid}&rettype=fasta&retmode=text"
    dest.write_bytes(http_bytes(url, timeout=60))
    time.sleep(0.4)
    return dest


def download_gbff(acc: str) -> Path:
    dest_zip = CACHE / f"{acc}_gbff.zip"
    if not dest_zip.exists() or dest_zip.stat().st_size < 1000:
        url = (
            "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/"
            f"{acc}/download?include_annotation_type=GENOME_GBFF"
        )
        print("download gbff", acc, flush=True)
        dest_zip.write_bytes(http_bytes(url))
    outdir = CACHE / f"{acc}_gbff"
    outdir.mkdir(exist_ok=True)
    marker = outdir / "_ok"
    if not marker.exists():
        with zipfile.ZipFile(dest_zip) as zf:
            zf.extractall(outdir)
        marker.write_text("ok\n")
    return outdir


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for acc in ACCS:
        download_proteome(acc)
        download_gbff(acc)
    for pid in ("NP_418414.1", "NP_418240.1", "NP_414878.1"):
        p = download_seed(pid)
        print("seed", pid, p.stat().st_size, flush=True)


if __name__ == "__main__":
    main()
