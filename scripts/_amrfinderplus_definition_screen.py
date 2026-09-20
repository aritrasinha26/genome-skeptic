#!/usr/bin/env python3
"""AMRFinderPlus definition-level overlap only. Does not download HMMs, sequences, isolate calls, or MicroBIGG-E."""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

HIERARCHY_URL = "https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/latest/ReferenceGeneHierarchy.txt"
CATALOG_URL = "https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/latest/ReferenceGeneCatalog.txt"

# Query terms are V5 target names / member gene symbols only.
QUERIES = {
    "tetA_tetracycline_efflux": ["teta", "tet(a)", "tet(b)", "tetb"],
    "mfs_multidrug_efflux": ["mdfa", "emrb", "bcr"],
    "rnd_efflux": ["acrb", "acrd"],
    "recA_recombinase": ["reca"],
    "tuf_EF_Tu": ["tuf", "tufa", "tufb"],
    "lacZ_beta_galactosidase": ["lacz"],
    "rpoB_RNAP_beta": ["rpob"],
    "rpoC_RNAP_beta_prime": ["rpoc"],
}


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _row_text(row: dict) -> str:
    return " ".join(str(v) for v in row.values() if v is not None).lower()


def _load_tsv(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "GenomeSkeptic-V5-definition-screen"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    return list(reader)


def _safe_fields(row: dict) -> dict:
    keep = [
        "node_id",
        "parent_node_id",
        "symbol",
        "name",
        "synonyms",
        "type",
        "subtype",
        "class",
        "subclass",
        "scope",
        "allele",
        "gene_family",
        "gene_symbol",
        "product_name",
        "hierarchy_node",
        "subtype",
    ]
    out = {}
    for k in keep:
        if k in row and row[k] not in (None, ""):
            out[k] = row[k]
    # Never keep HMM accessions, protein accessions, or isolate fields.
    return out


def match_family(rows: list[dict], terms: list[str]) -> list[dict]:
    hits = []
    for row in rows:
        blob = _norm(_row_text(row))
        symbol = _norm(row.get("symbol") or row.get("gene_symbol") or "")
        name = (row.get("name") or row.get("product_name") or "").lower()
        for term in terms:
            nt = _norm(term)
            if symbol == nt or symbol.startswith(nt) or f" {term.lower()} " in f" {name} ":
                hits.append(_safe_fields(row))
                break
            if nt in symbol and len(nt) >= 4:
                hits.append(_safe_fields(row))
                break
    # unique by symbol+name
    seen = set()
    uniq = []
    for h in hits:
        key = (h.get("symbol") or h.get("gene_symbol"), h.get("name") or h.get("product_name"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    return uniq[:40]


def main() -> None:
    dest = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/external_validation/ncbi_amrfinderplus_definition_only.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    hierarchy = _load_tsv(HIERARCHY_URL)
    catalog = _load_tsv(CATALOG_URL)
    payload = {
        "kind": "amrfinderplus_definition_level_screen",
        "hierarchy_url": HIERARCHY_URL,
        "catalog_url": CATALOG_URL,
        "n_hierarchy_nodes": len(hierarchy),
        "n_catalog_rows": len(catalog),
        "hmm_profiles_downloaded": False,
        "reference_sequences_downloaded": False,
        "isolate_calls_inspected": False,
        "microbigge_inspected": False,
        "matches_by_v5_target": {},
    }
    for fid, terms in QUERIES.items():
        payload["matches_by_v5_target"][fid] = {
            "query_terms": terms,
            "hierarchy_matches": match_family(hierarchy, terms),
            "catalog_matches": match_family(catalog, terms),
        }
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: {
        "n_hierarchy": len(v["hierarchy_matches"]),
        "n_catalog": len(v["catalog_matches"]),
        "hierarchy_symbols": [m.get("symbol") or m.get("gene_symbol") for m in v["hierarchy_matches"][:15]],
        "catalog_symbols": [m.get("symbol") or m.get("gene_symbol") for m in v["catalog_matches"][:15]],
        "hierarchy_types": list({m.get("type") for m in v["hierarchy_matches"] if m.get("type")}),
    } for k, v in payload["matches_by_v5_target"].items()}, indent=2))


if __name__ == "__main__":
    main()
