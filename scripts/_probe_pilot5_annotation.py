#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

UA = "GenomeSkeptic-pilot5-unblind"
ACCS = ["GCF_055394735.1", "GCF_055378285.1"]
QUERIES = [
    ("symbols", "rpoB"),
    ("search_text", "RNA polymerase subunit beta"),
    ("symbols", "tuf"),
    ("symbols", "tufA"),
    ("search_text", "elongation factor Tu"),
    ("symbols", "lacZ"),
    ("search_text", "beta-galactosidase"),
    ("symbols", "tetA"),
    ("symbols", "tetB"),
    ("search_text", "tetracycline"),
    ("search_text", "tet(A)"),
    ("search_text", "tet(B)"),
]


def get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def main() -> None:
    for acc in ACCS:
        print("====", acc, flush=True)
        for kind, val in QUERIES:
            url = (
                "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/"
                f"{acc}/annotation_report?page_size=20&{kind}={quote(val)}"
            )
            try:
                data = get(url)
            except Exception as exc:
                print(" FAIL", kind, val, exc, flush=True)
                time.sleep(0.4)
                continue
            reports = data.get("reports") or []
            print(
                f" {kind}={val!r} n={len(reports)} next={bool(data.get('next_page_token'))}",
                flush=True,
            )
            for rec in reports[:8]:
                ann = rec.get("annotation") or rec
                prots = [
                    (p.get("accession_version"), p.get("length"))
                    for p in (ann.get("proteins") or [])[:1]
                ]
                print(
                    "  ",
                    ann.get("symbol"),
                    "|",
                    (ann.get("name") or "")[:90],
                    "|",
                    ann.get("locus_tag"),
                    "|",
                    prots,
                    "|",
                    ann.get("gene_type"),
                    flush=True,
                )
            time.sleep(0.25)


if __name__ == "__main__":
    main()
