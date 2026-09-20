#!/usr/bin/env python3
"""Fetch and lock external labels for Cohort C pilot5 only (positions 1-5).

Does not inspect any other Cohort C genome. Does not read predictions.
Does not modify Agentic V1, V5, conventional baseline, thresholds, or
the hashed pilot5 manifest/predictions.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation_agentic"
CACHE = OUT / "cohort_C_pilot5_label_cache"
LABELS = OUT / "cohort_C_pilot5_external_labels_locked.jsonl"
UA = "GenomeSkeptic-external-validation/cohort-C-pilot5-unblind-labels-only"

PILOT_ACCESSIONS = ("GCF_055394735.1", "GCF_055378285.1")
ALLOWED_CASES = {
    ("GCF_055394735.1", "rpoB_RNAP_beta"),
    ("GCF_055394735.1", "tuf_EF_Tu"),
    ("GCF_055394735.1", "lacZ_beta_galactosidase"),
    ("GCF_055394735.1", "tetA_tetracycline_efflux"),
    ("GCF_055378285.1", "rpoB_RNAP_beta"),
}

SEEDS = {
    "rpoB_RNAP_beta": {
        "protein_id": "NP_418414.1",
        "gene_id": "948488",
        "symbols": ("rpoB",),
        "eggnog_seed_nogs": ("COG0085",),
        "related_symbols": ("rpoA", "rpoC", "rpoZ", "rpoD"),
    },
    "tuf_EF_Tu": {
        "protein_id": "NP_418240.1",
        "gene_id": None,
        "symbols": ("tuf", "tufA", "tufB"),
        "eggnog_seed_nogs": ("COG0050",),
        "related_symbols": ("tufB", "selB", "lepA"),
    },
    "lacZ_beta_galactosidase": {
        "protein_id": "NP_414878.1",
        "gene_id": None,
        "symbols": ("lacZ",),
        "eggnog_seed_nogs": ("COG3250",),
        "related_symbols": ("ebgA", "bglX", "lacA", "lacY"),
    },
}

TET_POSITIVE = {"tet(A)", "tet(B)", "tetA", "tetB"}
TET_RELATED = {
    "tet(C)", "tet(D)", "tet(E)", "tet(G)", "tet(H)", "tet(J)", "tet(K)",
    "tet(L)", "tet(M)", "tet(O)", "tet(Q)", "tet(S)", "tet(T)", "tet(W)",
    "tet(X)", "tet(Y)", "tet(Z)", "tetC", "tetD",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def http_json(url: str, timeout: int = 120) -> dict | list | None:
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
    raise RuntimeError(f"GET failed {url}: {last}")


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
    raise RuntimeError(f"GET bytes failed {url}: {last}")


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


def gene_payload_ids_tax_symbols(rec: dict) -> dict:
    gene = rec.get("gene") or rec
    gid = str(gene.get("gene_id") or rec.get("gene_id") or "")
    tax = gene.get("tax_id") or gene.get("taxonomy") or {}
    if isinstance(tax, dict):
        taxid = tax.get("tax_id") or tax.get("id")
        org = tax.get("organism_name") or tax.get("sci_name")
    else:
        taxid = tax
        org = gene.get("common_name") or gene.get("symbol")
    annotations = gene.get("annotations") or rec.get("annotations") or []
    symbols = set()
    prot = set()
    assemblies = set()
    pseudo = False
    for ann in annotations if isinstance(annotations, list) else []:
        for loc in ann.get("genomic_locations") or []:
            acc = (loc.get("genomic_accession") or loc.get("accession_version") or "")
            if acc:
                assemblies.add(acc)
        for ens in ann.get("ensembl_gene_ids") or []:
            pass
        if ann.get("genomic_range"):
            pass
    symbol = gene.get("symbol") or rec.get("symbol")
    if symbol:
        symbols.add(str(symbol))
    for syn in gene.get("synonyms") or []:
        symbols.add(str(syn))
    for prot_rec in gene.get("proteins") or rec.get("proteins") or []:
        pid = prot_rec.get("accession_version") or prot_rec.get("accession")
        if pid:
            prot.add(str(pid))
    desc = gene.get("description") or rec.get("description") or ""
    if "pseudo" in str(gene.get("type") or "").lower() or "pseudo" in str(desc).lower():
        pseudo = True
    return {
        "gene_id": gid,
        "tax_id": int(taxid) if str(taxid).isdigit() else taxid,
        "organism": org,
        "symbol": symbol,
        "symbols": sorted(symbols),
        "proteins": sorted(prot),
        "description": desc,
        "type": gene.get("type") or rec.get("type"),
        "pseudo": pseudo,
        "orientation_raw_keys": sorted(gene.keys())[:40],
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
        "&include_annotation_type=GENOME_GBFF"
    )
    print("download annotation", acc, flush=True)
    blob = http_bytes(url)
    if blob[:2] != b"PK":
        raise RuntimeError(f"annotation zip missing for {acc}: {blob[:120]!r}")
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


def parse_gff_target_features(gff_path: Path, wanted_symbols: set[str]) -> list[dict]:
    """Extract only features whose gene/product/Name matches wanted symbols.

    Does not return unrelated genes.
    """
    wanted_l = {w.lower() for w in wanted_symbols}
    rows = []
    opener = gzip.open if gff_path.suffix == ".gz" else open
    with opener(gff_path, "rt", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if not ln.strip() or ln.startswith("#"):
                continue
            parts = ln.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            seqid, _src, ftype, start, end, _sc, strand, _ph, attrs = parts[:9]
            ad = {}
            for item in attrs.split(";"):
                if "=" not in item:
                    continue
                k, v = item.split("=", 1)
                ad[k] = v
            blob = " ".join(ad.get(k, "") for k in ("gene", "Name", "product", "gene_biotype", "Note", "Dbxref", "ID", "locus_tag"))
            blob_l = blob.lower()
            if not any(w in blob_l or w.replace("(", "").replace(")", "") in blob_l for w in wanted_l):
                # also match tet(A)/tetA style
                compact = blob_l.replace("(", "").replace(")", "").replace(" ", "")
                if not any(w.replace("(", "").replace(")", "") in compact for w in wanted_l):
                    continue
            dbxref = ad.get("Dbxref") or ""
            gene_ids = re.findall(r"GeneID:(\d+)", dbxref)
            protein_ids = re.findall(r"(?:NP|WP|YP|AP)_\d+\.\d+", attrs)
            pseudo = "pseudo=true" in attrs.lower() or "pseudogene" in (ad.get("gene_biotype") or "").lower()
            rows.append(
                {
                    "seqid": seqid,
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
                    "pseudo": pseudo,
                    "partial": "partial=true" in attrs.lower(),
                }
            )
    return rows


def parse_gbff_amrfinder(gbff_path: Path) -> list[dict]:
    """Extract AMRFinderPlus / AMR gene features only (tet family)."""
    opener = gzip.open if gbff_path.suffix == ".gz" else open
    text = opener(gbff_path, "rt", encoding="utf-8", errors="replace").read()
    hits = []
    # Keep only tet-related qualifiers to avoid inspecting other AMR genes.
    for m in re.finditer(r'/gene="([^"]*tet[^"]*)"', text, flags=re.I):
        gene = m.group(1)
        window = text[max(0, m.start() - 800) : m.end() + 800]
        product = None
        pm = re.search(r'/product="([^"]+)"', window)
        if pm:
            product = pm.group(1)
        note = None
        nm = re.search(r'/note="([^"]+)"', window)
        if nm:
            note = nm.group(1)
        inference = None
        im = re.search(r'/inference="([^"]+)"', window)
        if im:
            inference = im.group(1)
        protein = None
        xm = re.search(r'/protein_id="([^"]+)"', window)
        if xm:
            protein = xm.group(1)
        if "tet" not in (gene + (product or "") + (note or "")).lower():
            continue
        hits.append(
            {
                "gene": gene,
                "product": product,
                "note": note,
                "inference": inference,
                "protein_id": protein,
                "amrfinder_mentioned": "amrfinder" in window.lower(),
            }
        )
    return hits


def eggnog_seed_membership(protein_id: str) -> dict:
    """Look up eggNOG 5 annotations for a frozen seed protein via UniProt cross-ref if possible."""
    # NCBI protein -> UniProt -> eggNOG. Independent of Genome Skeptic.
    info = {"protein_id": protein_id, "uniprot": None, "nogs": [], "source": None, "raw_note": None}
    try:
        uni = http_json(
            "https://rest.uniprot.org/uniprotkb/search?query="
            f"accession:{protein_id}+OR+{protein_id}&format=json&size=5"
        )
    except Exception as exc:
        info["raw_note"] = f"uniprot_search_failed:{exc}"
        uni = None
    results = (uni or {}).get("results") or []
    if not results:
        try:
            uni = http_json(
                "https://rest.uniprot.org/uniprotkb/search?query="
                f"{protein_id}&format=json&size=5"
            )
            results = (uni or {}).get("results") or []
        except Exception as exc:
            info["raw_note"] = f"uniprot_search_failed:{exc}"
    nogs = []
    uid = None
    for rec in results:
        uid = rec.get("primaryAccession") or uid
        for xref in rec.get("uniProtKBCrossReferences") or rec.get("dbReferences") or []:
            db = (xref.get("database") or xref.get("type") or "").lower()
            acc = xref.get("id") or xref.get("accession")
            if "eggnog" in db and acc:
                nogs.append(acc)
            if db in {"cog", "eggnog"} and acc:
                nogs.append(acc)
    info["uniprot"] = uid
    info["nogs"] = sorted(set(nogs))
    info["source"] = "UniProt eggNOG/COG cross-references for frozen seed protein"
    return info


def eggnog_members_for_nog(nog: str, taxids: set[int]) -> dict:
    """eggNOG 5 member dump via public API; restrict to the two pilot taxids."""
    urls = [
        f"http://eggnogapi5.embl.de/nog_data/json/extended_members/{nog}",
        f"http://eggnogapi5.embl.de/nog_data/json/members/{nog}",
    ]
    payload = None
    used = None
    last = None
    for url in urls:
        try:
            payload = http_json(url, timeout=180)
            used = url
            break
        except Exception as exc:
            last = exc
            payload = None
    hits = []
    members = []
    if isinstance(payload, dict):
        members = payload.get("members") or payload.get("data") or payload.get("proteins") or []
        if not members and "raw_data" in payload:
            members = payload["raw_data"]
    elif isinstance(payload, list):
        members = payload
    for mem in members:
        if isinstance(mem, str):
            # often "taxid.protein"
            tax = mem.split(".")[0]
            if tax.isdigit() and int(tax) in taxids:
                hits.append({"member": mem, "tax_id": int(tax)})
        elif isinstance(mem, dict):
            tax = mem.get("taxid") or mem.get("tax_id") or mem.get("ncbi_taxid")
            if str(tax).isdigit() and int(tax) in taxids:
                hits.append(mem)
        elif isinstance(mem, (list, tuple)) and mem:
            tax = str(mem[0]).split(".")[0]
            if tax.isdigit() and int(tax) in taxids:
                hits.append({"member": mem, "tax_id": int(tax)})
    return {
        "nog": nog,
        "api_url": used,
        "api_error": None if payload is not None else str(last),
        "n_members_inspected_total_unknown": True,
        "hits_in_pilot_taxids_only": hits,
        "n_hits_in_pilot_taxids": len(hits),
    }


def classify_ortholog(
    target: str,
    acc: str,
    taxid: int,
    ortholog_hits: list[dict],
    gff_hits: list[dict],
    eggnog: dict,
    taxon_queried_ok: bool,
) -> tuple[str, str, list[str]]:
    seed = SEEDS[target]
    complete = [
        h
        for h in gff_hits
        if h.get("type") in {"CDS", "mRNA", "gene"} and not h.get("pseudo") and not h.get("partial")
    ]
    cds = [h for h in complete if h.get("type") == "CDS"]
    gene_ids_in_assembly = {gid for h in gff_hits for gid in (h.get("gene_ids") or [])}
    orth_gene_ids = {str(x.get("gene_id") or "") for x in ortholog_hits if x.get("gene_id")}
    overlap = gene_ids_in_assembly & orth_gene_ids
    identifiers = []
    if overlap:
        identifiers.extend(sorted("GeneID:" + g for g in overlap))
    for h in cds[:8]:
        if h.get("protein_ids"):
            identifiers.extend(h["protein_ids"])
        if h.get("locus_tag"):
            identifiers.append(h["locus_tag"])
        if h.get("gene"):
            identifiers.append(str(h["gene"]))
    identifiers = list(dict.fromkeys(identifiers))

    eggnog_hit = bool((eggnog or {}).get("n_hits_in_pilot_taxids"))
    pgap_symbol_hit = any(
        (h.get("gene") or "").lower() in {s.lower() for s in seed["symbols"]}
        or any(s.lower() == str(h.get("gene") or "").lower() for s in seed["symbols"])
        for h in gff_hits
    )

    if overlap and cds:
        rationale = (
            f"NCBI Gene Ortholog group of frozen seed {seed['protein_id']} "
            f"(gene_id {seed['gene_id']}) contains GeneID(s) annotated on {acc} "
            f"as complete non-pseudo CDS."
        )
        if pgap_symbol_hit:
            rationale += " PGAP gene symbol corroborates but was not used as the sole standard."
        return "POSITIVE", rationale, identifiers
    if overlap and not cds:
        return (
            "AMBIGUOUS",
            "Ortholog-group GeneID present on assembly but no complete non-pseudo CDS extracted.",
            identifiers,
        )
    if ortholog_hits and not overlap:
        # taxon-level ortholog exists but this assembly's annotated gene IDs were not in the group
        if cds and pgap_symbol_hit:
            return (
                "AMBIGUOUS",
                "PGAP symbol match without overlapping NCBI Gene Ortholog GeneID on this assembly.",
                identifiers,
            )
        if taxon_queried_ok and not cds:
            rationale = (
                f"NCBI Gene Orthologs was applied to taxid {taxid}; no member of the "
                f"frozen seed ortholog group was found among this assembly's annotated genes."
            )
            if eggnog_hit:
                rationale += " eggNOG 5 has a NOG member at this taxid, creating a conflict; assigned AMBIGUOUS."
                return "AMBIGUOUS", rationale, identifiers
            return "NEGATIVE", rationale, identifiers
    if not taxon_queried_ok:
        if eggnog_hit and cds and pgap_symbol_hit:
            return (
                "POSITIVE",
                "NCBI Gene Orthologs did not return this taxon; eggNOG 5 NOG membership of the seed "
                "plus a complete corroborating CDS was used as independent orthology evidence.",
                identifiers,
            )
        if eggnog_hit and not cds:
            return (
                "AMBIGUOUS",
                "eggNOG 5 taxid membership without a complete CDS extracted from this assembly.",
                identifiers,
            )
        if not eggnog_hit:
            return (
                "AMBIGUOUS",
                "NCBI Gene Orthologs did not cover this taxon and eggNOG 5 did not return a member "
                "at this taxid; absence was not inferred.",
                identifiers,
            )
    if pgap_symbol_hit and not overlap:
        return (
            "AMBIGUOUS",
            "PGAP gene-symbol match without ortholog-group assignment on this assembly.",
            identifiers,
        )
    related = any(
        (h.get("gene") or "").lower() in {s.lower() for s in seed["related_symbols"]}
        for h in gff_hits
    )
    if related and not overlap:
        return (
            "RELATED_BUT_NON_TARGET",
            "Related gene symbol(s) present without seed ortholog-group membership.",
            identifiers,
        )
    if taxon_queried_ok:
        return (
            "NEGATIVE",
            "Independent ortholog resource was applied and returned no seed-group member "
            "and no complete corroborating CDS of that group.",
            identifiers,
        )
    return (
        "AMBIGUOUS",
        "Orthology resources incomplete for this taxon; absence not inferred.",
        identifiers,
    )


def classify_tet(gff_hits: list[dict], gbff_hits: list[dict]) -> tuple[str, str, list[str]]:
    names = []
    for h in gff_hits + gbff_hits:
        for key in ("gene", "Name", "product", "note"):
            val = h.get(key) if key != "Name" else h.get("gene")
            if val:
                names.append(str(val))
    blob = " ".join(names)
    compact = blob.lower().replace(" ", "")
    identifiers = []
    for h in gff_hits + gbff_hits:
        if h.get("protein_id"):
            identifiers.append(h["protein_id"])
        if h.get("protein_ids"):
            identifiers.extend(h["protein_ids"])
        if h.get("locus_tag"):
            identifiers.append(h["locus_tag"])
        if h.get("gene"):
            identifiers.append(str(h["gene"]))
    identifiers = list(dict.fromkeys(identifiers))

    def has_any(cands: set[str]) -> list[str]:
        found = []
        for c in cands:
            cl = c.lower()
            if cl in compact or cl.replace("(", "").replace(")", "") in compact.replace("(", "").replace(")", ""):
                found.append(c)
        return found

    pos = has_any(TET_POSITIVE)
    rel = has_any(TET_RELATED)
    amr_call = any(h.get("amrfinder_mentioned") for h in gbff_hits) or any(
        "amrfinder" in str(h.get("note") or "").lower() or "amrfinder" in str(h.get("inference") or "").lower()
        for h in gff_hits + gbff_hits
    )
    source_note = "AMRFinderPlus/PGAP AMR gene call published on this RefSeq assembly"
    if not amr_call:
        source_note = (
            "RefSeq AMR gene annotation on this assembly (PGAP uses AMRFinderPlus for AMR genes); "
            "no explicit AMRFinderPlus string was present in the inspected tet window"
        )
    if pos and not any("pseudo" in str(h).lower() for h in gff_hits + gbff_hits):
        return (
            "POSITIVE",
            f"{source_note}. Frozen positive family tet(A) OR tet(B) matched: {pos}.",
            identifiers,
        )
    if any("pseudo" in str(h).lower() for h in gff_hits + gbff_hits) and pos:
        return "AMBIGUOUS", f"{source_note}. tet(A)/tet(B) evidence appears pseudo/partial.", identifiers
    if rel and not pos:
        return (
            "RELATED_BUT_NON_TARGET",
            f"{source_note}. Related tetracycline gene(s) {rel} without tet(A) or tet(B).",
            identifiers,
        )
    if not pos and not rel:
        return (
            "NEGATIVE",
            f"{source_note}. No tet(A) or tet(B) and no other inspected tetracycline-efflux gene call.",
            identifiers,
        )
    return "AMBIGUOUS", f"{source_note}. Unresolved tet class from available calls.", identifiers


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    cohort = json.loads((OUT / "cohort_C_manifest.json").read_text(encoding="utf-8"))
    assemblies = {
        a["assembly_accession"]: a
        for a in cohort["assemblies"]
        if a["assembly_accession"] in PILOT_ACCESSIONS
    }
    if set(assemblies) != set(PILOT_ACCESSIONS):
        raise SystemExit(f"pilot accessions missing from cohort C manifest: {set(PILOT_ACCESSIONS)-set(assemblies)}")

    # Resolve missing seed gene_ids from frozen proteins only.
    for target, seed in SEEDS.items():
        if seed["gene_id"] is None:
            gid = gene_id_for_protein(seed["protein_id"])
            seed["gene_id"] = gid
            print(f"seed_gene_id {target} {seed['protein_id']} -> {gid}", flush=True)
        time.sleep(0.2)

    seed_eggnog = {}
    for target, seed in SEEDS.items():
        seed_eggnog[target] = eggnog_seed_membership(seed["protein_id"])
        print("seed_eggnog", target, seed_eggnog[target], flush=True)
        time.sleep(0.2)

    taxids = {int(assemblies[a]["taxonomy_id"]) for a in PILOT_ACCESSIONS}
    eggnog_by_target = {}
    for target, seed in SEEDS.items():
        nogs = list(seed["eggnog_seed_nogs"]) + list(seed_eggnog[target].get("nogs") or [])
        nogs = list(dict.fromkeys(nogs))
        parts = [eggnog_members_for_nog(n, taxids) for n in nogs]
        eggnog_by_target[target] = {
            "seed_uniprot": seed_eggnog[target],
            "nogs_queried": nogs,
            "per_nog": parts,
            "n_hits_in_pilot_taxids": sum(p.get("n_hits_in_pilot_taxids") or 0 for p in parts),
        }
        print("eggnog_target", target, eggnog_by_target[target]["n_hits_in_pilot_taxids"], flush=True)

    labels = []
    for acc in PILOT_ACCESSIONS:
        rec = assemblies[acc]
        taxid = int(rec["taxonomy_id"])
        zpath = download_annotation_zip(acc)
        extracted = extract_zip(zpath, CACHE / f"{acc}_extracted")
        gff = find_first(extracted, (".gff", ".gff.gz", ".gff3", ".gff3.gz"))
        gbff = find_first(extracted, (".gbff", ".gbff.gz", ".gbk", ".gbk.gz"))
        print(acc, "gff", gff, "gbff", gbff, flush=True)
        if gff is None:
            raise SystemExit(f"no GFF for {acc}")

        targets_here = [t for a, t in ALLOWED_CASES if a == acc]
        for target in targets_here:
            if target == "tetA_tetracycline_efflux":
                wanted = set(TET_POSITIVE) | set(TET_RELATED) | {"tet", "tetracycline efflux"}
                gff_hits = parse_gff_target_features(gff, wanted)
                gbff_hits = parse_gbff_amrfinder(gbff) if gbff else []
                klass, rationale, idents = classify_tet(gff_hits, gbff_hits)
                labels.append(
                    {
                        "frozen_execution_position": {
                            ("GCF_055394735.1", "rpoB_RNAP_beta"): 1,
                            ("GCF_055394735.1", "tuf_EF_Tu"): 2,
                            ("GCF_055394735.1", "lacZ_beta_galactosidase"): 3,
                            ("GCF_055394735.1", "tetA_tetracycline_efflux"): 4,
                            ("GCF_055378285.1", "rpoB_RNAP_beta"): 5,
                        }[(acc, target)],
                        "assembly": acc,
                        "organism": rec.get("organism"),
                        "taxid": taxid,
                        "biosample": rec.get("biosample"),
                        "target": target,
                        "reference_class": klass,
                        "reference_source": "AMRFinderPlus external call as published on this RefSeq assembly (PGAP AMRFinderPlus AMR gene annotation); frozen positive family = tet(A) OR tet(B)",
                        "reference_identifiers": idents,
                        "short_rationale": rationale,
                        "pgap_used_as_sole_truth": False,
                        "other_cohort_C_cases_inspected": False,
                        "gff_feature_count_inspected_for_this_target_only": len(gff_hits),
                        "gbff_tet_window_count": len(gbff_hits),
                    }
                )
                continue

            seed = SEEDS[target]
            wanted = set(seed["symbols"]) | set(seed["related_symbols"]) | {seed["protein_id"]}
            gff_hits = parse_gff_target_features(gff, wanted)
            taxon_hits_raw = []
            taxon_ok = False
            try:
                taxon_hits_raw = orthologs_for_gene(seed["gene_id"], taxon=taxid)
                taxon_ok = True
            except Exception as exc:
                print(f"ortholog taxon_filter failed {target} {taxid}: {exc}", flush=True)
                taxon_hits_raw = []
                taxon_ok = False
            parsed_hits = [gene_payload_ids_tax_symbols(x) for x in taxon_hits_raw]
            # If taxon filter returned empty, still record coverage: try species lookup flag.
            if not parsed_hits:
                # One unfiltered page to see whether the API is alive; do not scan other genomes.
                try:
                    probe = orthologs_for_gene(seed["gene_id"], taxon=taxid)
                    taxon_ok = True
                    parsed_hits = [gene_payload_ids_tax_symbols(x) for x in probe]
                except Exception:
                    taxon_ok = False
            klass, rationale, idents = classify_ortholog(
                target,
                acc,
                taxid,
                parsed_hits,
                gff_hits,
                eggnog_by_target[target],
                taxon_ok,
            )
            labels.append(
                {
                    "frozen_execution_position": {
                        ("GCF_055394735.1", "rpoB_RNAP_beta"): 1,
                        ("GCF_055394735.1", "tuf_EF_Tu"): 2,
                        ("GCF_055394735.1", "lacZ_beta_galactosidase"): 3,
                        ("GCF_055394735.1", "tetA_tetracycline_efflux"): 4,
                        ("GCF_055378285.1", "rpoB_RNAP_beta"): 5,
                    }[(acc, target)],
                    "assembly": acc,
                    "organism": rec.get("organism"),
                    "taxid": taxid,
                    "biosample": rec.get("biosample"),
                    "target": target,
                    "reference_class": klass,
                    "reference_source": (
                        "NCBI Gene Orthologs for frozen seed "
                        f"{seed['protein_id']} / gene_id {seed['gene_id']}; "
                        "eggNOG 5.0 NOG membership as independent orthology evidence; "
                        "PGAP gene symbols corroboration only"
                    ),
                    "reference_identifiers": idents + [f"seed_gene_id:{seed['gene_id']}", f"seed_protein:{seed['protein_id']}"],
                    "short_rationale": rationale,
                    "pgap_used_as_sole_truth": False,
                    "other_cohort_C_cases_inspected": False,
                    "ncbi_gene_orthologs_taxon_query_ok": taxon_ok,
                    "ncbi_gene_orthologs_hits_in_taxon": [
                        {k: h.get(k) for k in ("gene_id", "tax_id", "symbol", "proteins", "description")}
                        for h in parsed_hits[:12]
                    ],
                    "gff_feature_count_inspected_for_this_target_only": len(gff_hits),
                    "eggnog5": {
                        "nogs_queried": eggnog_by_target[target]["nogs_queried"],
                        "n_hits_in_pilot_taxids": eggnog_by_target[target]["n_hits_in_pilot_taxids"],
                        "seed_uniprot": seed_eggnog[target].get("uniprot"),
                        "seed_nogs": seed_eggnog[target].get("nogs"),
                    },
                }
            )
            time.sleep(0.3)

    labels.sort(key=lambda r: r["frozen_execution_position"])
    if len(labels) != 5:
        raise SystemExit(f"expected 5 labels, got {len(labels)}")
    if [r["frozen_execution_position"] for r in labels] != [1, 2, 3, 4, 5]:
        raise SystemExit("label positions are not 1-5")
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in labels]
    LABELS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    digest = sha256_file(LABELS)
    sidecar = OUT / "cohort_C_pilot5_external_labels_locked.sha256.json"
    sidecar.write_text(
        json.dumps(
            {
                "file": "cohort_C_pilot5_external_labels_locked.jsonl",
                "sha256": digest,
                "hashed_utc": datetime.now(timezone.utc).isoformat(),
                "hashed_before_prediction_comparison": True,
                "n_cases": 5,
                "other_cohort_C_cases_inspected": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("LABELS_LOCKED", digest, flush=True)
    for r in labels:
        print(
            r["frozen_execution_position"],
            r["assembly"],
            r["target"],
            r["reference_class"],
            r["short_rationale"][:180],
            flush=True,
        )


if __name__ == "__main__":
    main()
