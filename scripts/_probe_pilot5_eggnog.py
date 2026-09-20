#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

UA = "GenomeSkeptic-pilot5-unblind"
PROTS = [
    "WP_464229829.1",  # GCF_055394735 rpoB
    "WP_464232666.1",  # GCF_055394735 unlabeled RNAP beta
    "WP_464229820.1",  # GCF_055394735 tuf
    "WP_464280409.1",  # GCF_055378285 rpoB
]
SEEDS = ["NP_418414.1", "NP_418240.1", "NP_414878.1"]


def get(url: str, timeout: int = 60) -> tuple[int, bytes]:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(250000)
    except Exception as exc:
        print("FAIL", url, exc, flush=True)
        return 0, b""


def main() -> None:
    for pid in SEEDS + PROTS:
        print("====", pid, flush=True)
        url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/gene/accession/{pid}"
        code, raw = get(url)
        print(" datasets_gene", code, raw[:400].decode("utf-8", "replace"), flush=True)
        time.sleep(0.3)
        url = "https://rest.uniprot.org/uniprotkb/search?query=" + quote(pid) + "&format=json&size=3"
        code, raw = get(url)
        print(" uniprot", code, raw[:700].decode("utf-8", "replace"), flush=True)
        time.sleep(0.4)
        url = f"https://www.ebi.ac.uk/proteins/api/proteins?offset=0&size=3&accession={pid}"
        # WP may not be UniProt accession; try taxonomy xref
        url = "https://rest.uniprot.org/uniprotkb/search?query=" + quote(f"xref:refseq-{pid}") + "&format=json&size=2"
        code, raw = get(url)
        print(" uniprot_xref", code, raw[:800].decode("utf-8", "replace"), flush=True)
        time.sleep(0.4)

    print("==== extra searches", flush=True)
    extra = [
        ("GCF_055394735.1", "glycoside hydrolase"),
        ("GCF_055394735.1", "ebgA"),
        ("GCF_055394735.1", "efflux"),
        ("GCF_055394735.1", "AMR"),
        ("GCF_055378285.1", "glycoside hydrolase"),
        ("GCF_055394735.1", "DNA-directed RNA polymerase subunit beta"),
    ]
    for acc, term in extra:
        url = (
            "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/"
            f"{acc}/annotation_report?page_size=20&search_text={quote(term)}"
        )
        code, raw = get(url)
        data = json.loads(raw.decode("utf-8", "replace") or "{}")
        reports = data.get("reports") or []
        print(acc, term, "n=", len(reports), flush=True)
        for rec in reports[:6]:
            ann = rec.get("annotation") or rec
            print(" ", ann.get("symbol"), "|", (ann.get("name") or "")[:90], "|", ann.get("locus_tag"), flush=True)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
