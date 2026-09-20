#!/usr/bin/env python3
"""Scorer-side NCBI feature-table fetch for authentic rpoB loci. Not used by the agent."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
OUT = ROOT / "benchmarks/semantics_v2/annotations"
ACCESSIONS = {
    "ecoli_k12": "NC_000913.3",
    "pao1": "NC_002516.2",
    "hpylori": "NC_000915.1",
    "salmonella_lt2": "NC_003197.2",
    "pputida_kt2440": "NC_002947.4",
    "staph_8325": "NC_007795.1",
}


def fetch_ft(acc: str) -> str:
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=nuccore&id={acc}&rettype=ft&retmode=text"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "GenomeSkeptic/eval (scientific benchmark)"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_rpob(ft: str) -> dict | None:
    lines = ft.splitlines()
    i = 0
    best = None
    while i < len(lines):
        line = lines[i]
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] in {"gene", "CDS"}:
            feat_type = parts[2]
            try:
                start, end = int(parts[0]), int(parts[1])
            except ValueError:
                i += 1
                continue
            strand = "+" if start <= end else "-"
            lo, hi = min(start, end), max(start, end)
            attrs = {}
            i += 1
            while i < len(lines) and lines[i].startswith("\t\t\t"):
                kv = lines[i].strip().split("\t")
                if len(kv) >= 2:
                    attrs[kv[0]] = kv[1]
                elif len(kv) == 1:
                    attrs[kv[0]] = True
                i += 1
            gene = str(attrs.get("gene") or "")
            product = str(attrs.get("product") or "").lower()
            is_rpob = gene == "rpoB" or "rna polymerase" in product and "subunit beta" in product and "beta'" not in product and "beta-prime" not in product
            if is_rpob and feat_type == "CDS":
                rec = {
                    "feature": feat_type,
                    "start": lo,
                    "end": hi,
                    "strand": strand,
                    "gene": gene or "rpoB",
                    "locus_tag": attrs.get("locus_tag"),
                    "protein_id": attrs.get("protein_id"),
                    "product": attrs.get("product"),
                    "nucleotide_length": hi - lo + 1,
                    "translation": attrs.get("translation"),
                }
                if rec.get("translation"):
                    rec["protein_length"] = len(rec["translation"].replace("*", ""))
                best = rec
                continue
            continue
        i += 1
    return best


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for gid, acc in ACCESSIONS.items():
        print("fetch", gid, acc, flush=True)
        text = fetch_ft(acc)
        (OUT / f"{gid}_{acc}.ft.txt").write_text(text)
        rec = parse_rpob(text)
        summary[gid] = {"accession": acc, "rpoB": rec, "bytes": len(text)}
        print(" ", "found" if rec else "MISSING", rec.get("locus_tag") if rec else None, rec.get("nucleotide_length") if rec else None)
    (OUT / "rpoB_loci.json").write_text(json.dumps(summary, indent=2))
    print("wrote", OUT / "rpoB_loci.json")


if __name__ == "__main__":
    main()
