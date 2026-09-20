#!/usr/bin/env python3
"""Exact-symbol definition lookup. No isolate data."""
from __future__ import annotations
import csv, io, json, urllib.request

URL = "https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/latest/ReferenceGeneHierarchy.txt"
WANTED = {"mdfa", "mdf(a)", "acrb", "acrd", "emrb", "bcr", "teta", "tet(a)", "tet(b)", "rpob", "rpoc", "reca", "lacz", "tuf"}

req = urllib.request.Request(URL, headers={"User-Agent": "GenomeSkeptic-V5-definition-screen"})
with urllib.request.urlopen(req, timeout=60) as resp:
    raw = resp.read().decode("utf-8", errors="replace")
rows = list(csv.DictReader(io.StringIO(raw), delimiter="\t"))
hits = []
for row in rows:
    sym = (row.get("symbol") or "").strip()
    key = "".join(ch for ch in sym.lower() if ch.isalnum() or ch in "()")
    key2 = "".join(ch for ch in key if ch.isalnum())
    if key2 in WANTED or key.lower() in WANTED:
        hits.append({
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "type": row.get("type"),
            "subtype": row.get("subtype"),
            "class": row.get("class"),
            "parent_node_id": row.get("parent_node_id"),
        })
print(json.dumps(hits, indent=2))
print("N", len(hits))
