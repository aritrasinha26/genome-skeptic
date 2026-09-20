#!/usr/bin/env python3
from __future__ import annotations

import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UA = "GenomeSkeptic-pilot5-unblind"
QUERIES = "\n".join(
    [
        "WP_464229829.1",
        "WP_464232666.1",
        "WP_464229820.1",
        "WP_464280409.1",
        "WP_464280408.1",
    ]
)


def main() -> None:
    data = urlencode(
        {
            "queries": QUERIES,
            "db": "cdd",
            "smode": "auto",
            "tdata": "hits",
            "dmode": "rep",
            "cddefl": "false",
            "qdefl": "false",
            "maxhit": "15",
            "useid1": "true",
        }
    ).encode()
    req = Request(
        "https://www.ncbi.nlm.nih.gov/Structure/bwrpsb/bwrpsb.cgi",
        data=data,
        headers={"User-Agent": UA},
    )
    with urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", "replace")
    print(raw[:1500], flush=True)
    cdsid = None
    for ln in raw.splitlines():
        if ln.startswith("#cdsid"):
            cdsid = ln.split("\t")[-1].strip()
    print("CDSID", cdsid, flush=True)
    if not cdsid:
        raise SystemExit("no cdsid")
    for i in range(20):
        time.sleep(3)
        url = f"https://www.ncbi.nlm.nih.gov/Structure/bwrpsb/bwrpsb.cgi?cdsid={cdsid}&tdata=hits"
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=60) as resp:
            out = resp.read().decode("utf-8", "replace")
        status = None
        for ln in out.splitlines():
            if ln.startswith("#status"):
                status = ln
        print("poll", i, status, flush=True)
        if status and status.split("\t")[1].strip() == "0":
            print(out, flush=True)
            return
    raise SystemExit("cd-search timeout")


if __name__ == "__main__":
    main()
