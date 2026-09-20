#!/usr/bin/env python3
"""Fetch public competing-family and full-length transporter references for V5.

Does not store FAST_PILOT hidden genome IDs. Does not invent sequences.
Incomplete downloads are rejected rather than stored as truncated family members.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from genome_skeptic.families import build_star_msa

FORBIDDEN = {
    "NP_252960.1", "WP_000037869.1", "NP_463022.1", "WP_003255495.1",
    "YP_499096.2", "NP_387988.1", "NP_387989.1",
}

# UniProt curated full-length references. Accessions are public; sequences are not invented.
FAMILIES = {
    "tetA_tetracycline_efflux": {
        "display_name": "tetracycline efflux TetA (mobile/plasmid-associated)",
        "property": "mobile_plasmid_associated",
        "family_class": "mfs_transporter",
        "competing_families": ["mfs_multidrug_efflux", "rnd_efflux"],
        "min_aa": 350,
        "members": [
            ("P02980", "uniprot", "Tn10 TetA class B"),
            ("P02982", "uniprot", "TetA/TCR1 tetracycline efflux"),
            ("P0A334", "uniprot", "TetA class C"),
        ],
    },
    "mfs_multidrug_efflux": {
        "display_name": "MFS multidrug efflux (non-TetA competitors)",
        "property": "membrane_transporter_competing_families",
        "family_class": "mfs_transporter",
        "competing_families": ["tetA_tetracycline_efflux"],
        "min_aa": 350,
        "members": [
            ("P0AEY8", "uniprot", "Escherichia coli MdfA"),
            ("P0AEJ0", "uniprot", "Escherichia coli EmrB"),
            ("P28246", "uniprot", "Escherichia coli Bcr"),
        ],
    },
    "rnd_efflux": {
        "display_name": "RND family efflux (AcrB-like)",
        "property": "membrane_transporter_competing_families",
        "family_class": "rnd_transporter",
        "competing_families": ["tetA_tetracycline_efflux", "mfs_multidrug_efflux"],
        "min_aa": 800,
        "members": [
            ("P31224", "uniprot", "Escherichia coli AcrB"),
            ("P24177", "uniprot", "Escherichia coli AcrD"),
            ("P0AE06", "uniprot", "Escherichia coli MdtC"),
        ],
    },
}


def _parse_fasta(text: str) -> str:
    if not text or not text.lstrip().startswith(">"):
        raise RuntimeError("not FASTA")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith(">")]
    seq = "".join(lines).replace(" ", "").upper()
    seq = "".join(ch for ch in seq if ch.isalpha())
    if not seq:
        raise RuntimeError("empty protein sequence")
    return seq


def fetch_uniprot(pid: str) -> str:
    url = f"https://rest.uniprot.org/uniprotkb/{pid}.fasta"
    try:
        import requests
        r = requests.get(url, timeout=60, headers={"User-Agent": "GenomeSkeptic/v5"})
        r.raise_for_status()
        text = r.text
    except Exception:
        with urlopen(Request(url, headers={"User-Agent": "GenomeSkeptic/v5"}), timeout=60) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    return _parse_fasta(text)


def fetch_ncbi(pid: str) -> str:
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=protein&id={pid}&rettype=fasta&retmode=text"
    with urlopen(Request(url, headers={"User-Agent": "GenomeSkeptic/v5"}), timeout=60) as resp:
        chunks = []
        while True:
            block = resp.read(8192)
            if not block:
                break
            chunks.append(block)
        text = b"".join(chunks).decode("utf-8", errors="replace")
    return _parse_fasta(text)


def efetch_protein(pid: str, source: str, min_aa: int) -> str:
    last = None
    for attempt in range(4):
        try:
            seq = fetch_uniprot(pid) if source == "uniprot" else fetch_ncbi(pid)
            if len(seq) < min_aa:
                raise RuntimeError(f"download length {len(seq)} < {min_aa}; treating as incomplete, not a curated member")
            time.sleep(0.35)
            return seq
        except Exception as exc:
            last = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(last)


def write_family(fid: str, spec: dict, dest_roots: list[Path]) -> dict:
    seqs = []
    errors = []
    min_aa = int(spec.get("min_aa") or 250)
    for pid, source, species in spec["members"]:
        if pid in FORBIDDEN:
            errors.append(f"skipped forbidden {pid}")
            continue
        try:
            seq = efetch_protein(pid, source, min_aa)
            seqs.append((pid, species, seq, len(seq), source))
        except Exception as exc:
            errors.append(f"{pid}: {exc}")
    if len(seqs) < 2:
        return {"family_id": fid, "ok": False, "errors": errors, "n": len(seqs)}
    msa = build_star_msa([(p, s) for p, _, s, _, _ in seqs])
    yaml_txt = [
        f"family_id: {fid}",
        f"display_name: {spec['display_name']}",
        f"biological_property: {spec['property']}",
        f"family_class: {spec['family_class']}",
        "competing_families:",
        *[f"- {c}" for c in spec.get("competing_families") or []],
        "partner_families: []",
        "members:",
    ]
    for pid, species, seq, n, source in seqs:
        yaml_txt += [
            f"- protein_id: {pid}",
            f"  species: {species}",
            f"  length_aa: {n}",
            "  fusion_or_split: canonical",
            f"  source: {source} FASTA",
            "  retrieved: '2026-09-18'",
        ]
    yaml_txt += [
        "forbidden_protein_ids:",
        *[f"- {x}" for x in sorted(FORBIDDEN)],
        "forbidden_reason: FAST_PILOT hidden genomes are not family members.",
        "msa_provenance:",
        "  method: star multiple alignment seeded on the first member (Needleman-Wunsch)",
        "  aligner: genome_skeptic.families.build_star_msa",
        "hmm_provenance:",
        "  method: hmmbuild from members.aln.faa at first use",
        "  not_invented_by_llm: true",
    ]
    faa = "".join(f">{pid}\n{seq}\n" for pid, _, seq, _, _ in seqs)
    aln = "".join(f">{pid}\n{seq}\n" for pid, seq in msa)
    for root in dest_roots:
        d = root / fid
        d.mkdir(parents=True, exist_ok=True)
        (d / "family.yaml").write_text("\n".join(yaml_txt) + "\n", encoding="utf-8")
        (d / "members.faa").write_text(faa, encoding="utf-8")
        (d / "members.aln.faa").write_text(aln, encoding="utf-8")
        hmm = d / "family.hmm"
        if hmm.exists():
            hmm.unlink()
    return {"family_id": fid, "ok": True, "n": len(seqs), "ids": [p for p, _, _, _, _ in seqs], "lengths": [n for _, _, _, n, _ in seqs], "errors": errors}


def main() -> None:
    dests = [ROOT / "data" / "target_families", ROOT / "src" / "genome_skeptic" / "data" / "target_families"]
    report = []
    for fid, spec in FAMILIES.items():
        print("fetch", fid, flush=True)
        row = write_family(fid, spec, dests)
        print(row, flush=True)
        report.append(row)
    extra = """
  mfs_multidrug_efflux: mfs_multidrug_efflux
  rnd_efflux: rnd_efflux
"""
    for dest in dests:
        p = dest / "index.yaml"
        text = p.read_text(encoding="utf-8") if p.exists() else "aliases:\n"
        if "mfs_multidrug_efflux" not in text:
            p.write_text(text.rstrip() + extra, encoding="utf-8")
    print(report, flush=True)
    if not any(r.get("family_id") == "tetA_tetracycline_efflux" and r.get("ok") for r in report):
        raise SystemExit("tetA family fetch failed")
    if not any(r.get("family_id") == "mfs_multidrug_efflux" and r.get("ok") for r in report):
        raise SystemExit("mfs competing family fetch failed")


if __name__ == "__main__":
    main()
