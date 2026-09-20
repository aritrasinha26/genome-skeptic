#!/usr/bin/env python3
"""Fetch public RefSeq proteins for V4.1 families. Hidden FAST_PILOT IDs are never stored as members."""
from __future__ import annotations

import sys
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

FAMILIES = {
    "recA_recombinase": {
        "display_name": "RecA recombinase (single-copy housekeeping)",
        "property": "highly_conserved_single_copy_housekeeping",
        "members": [
            ("NP_417179.1", "Escherichia coli str. K-12 substr. MG1655"),
            ("NP_214765.1", "Mycobacterium tuberculosis H37Rv"),
            ("NP_228245.1", "Thermotoga maritima"),
            ("NP_213126.1", "Aquifex aeolicus"),
        ],
    },
    "tuf_EF_Tu": {
        "display_name": "elongation factor Tu (multi-copy paralogues tufA/tufB)",
        "property": "multi_copy_genuine_paralogues",
        "members": [
            ("NP_418240.1", "Escherichia coli str. K-12 substr. MG1655 tufA"),
            ("NP_216072.1", "Mycobacterium tuberculosis H37Rv"),
            ("NP_228108.1", "Thermotoga maritima"),
            ("NP_213616.1", "Aquifex aeolicus"),
        ],
    },
    "lacZ_beta_galactosidase": {
        "display_name": "beta-galactosidase LacZ (accessory, absent from many strains)",
        "property": "accessory_absent_from_many_strains",
        "members": [
            ("NP_414878.1", "Escherichia coli str. K-12 substr. MG1655"),
            ("WP_000241775.1", "Shigella flexneri"),
            ("WP_004084538.1", "Klebsiella pneumoniae"),
        ],
    },
    "tetA_tetracycline_efflux": {
        "display_name": "tetracycline efflux TetA (mobile/plasmid-associated)",
        "property": "mobile_plasmid_associated",
        "members": [
            ("AAA87452.1", "Tn10 TetA"),
            ("WP_000048591.1", "tetracycline efflux protein"),
            ("WP_001301208.1", "TetA family transporter"),
        ],
    },
}


def efetch_protein(pid: str) -> str:
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=protein&id={pid}&rettype=fasta&retmode=text"
    with urlopen(Request(url, headers={"User-Agent": "GenomeSkeptic/v4.1"}), timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    if not text.lstrip().startswith(">"):
        raise RuntimeError(f"not FASTA for {pid}")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith(">")]
    return "".join(lines)


def write_family(fid: str, spec: dict, dest_roots: list[Path]) -> dict:
    seqs = []
    errors = []
    for pid, species in spec["members"]:
        if pid in FORBIDDEN:
            errors.append(f"skipped forbidden {pid}")
            continue
        try:
            seq = efetch_protein(pid)
            seqs.append((pid, species, seq, len(seq)))
        except Exception as exc:
            errors.append(f"{pid}: {exc}")
    if len(seqs) < 2:
        return {"family_id": fid, "ok": False, "errors": errors, "n": len(seqs)}
    msa = build_star_msa([(p, s) for p, _, s, _ in seqs])
    yaml_txt = [
        f"family_id: {fid}",
        f"display_name: {spec['display_name']}",
        f"biological_property: {spec['property']}",
        "partner_families: []",
        "members:",
    ]
    for pid, species, seq, n in seqs:
        yaml_txt += [
            f"- protein_id: {pid}",
            f"  species: {species}",
            f"  length_aa: {n}",
            "  fusion_or_split: canonical",
            "  source: NCBI protein FASTA",
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
    faa = "".join(f">{pid}\n{seq}\n" for pid, _, seq, _ in seqs)
    aln = "".join(f">{pid}\n{seq}\n" for pid, seq in msa)
    for root in dest_roots:
        d = root / fid
        d.mkdir(parents=True, exist_ok=True)
        (d / "family.yaml").write_text("\n".join(yaml_txt) + "\n", encoding="utf-8")
        (d / "members.faa").write_text(faa, encoding="utf-8")
        (d / "members.aln.faa").write_text(aln, encoding="utf-8")
    return {"family_id": fid, "ok": True, "n": len(seqs), "ids": [p for p, _, _, _ in seqs], "errors": errors}


def main() -> None:
    dests = [ROOT / "data" / "target_families", ROOT / "src" / "genome_skeptic" / "data" / "target_families"]
    report = []
    for fid, spec in FAMILIES.items():
        print("fetch", fid, flush=True)
        report.append(write_family(fid, spec, dests))
    aliases = (ROOT / "data" / "target_families" / "index.yaml").read_text(encoding="utf-8")
    extra = """
  recA: recA_recombinase
  recA_recombinase: recA_recombinase
  tuf: tuf_EF_Tu
  tuf_EF_Tu: tuf_EF_Tu
  lacZ: lacZ_beta_galactosidase
  lacZ_beta_galactosidase: lacZ_beta_galactosidase
  tetA: tetA_tetracycline_efflux
  tetA_tetracycline_efflux: tetA_tetracycline_efflux
"""
    if "recA_recombinase" not in aliases:
        for dest in dests:
            p = dest / "index.yaml"
            text = p.read_text(encoding="utf-8") if p.exists() else "aliases:\n"
            if "recA_recombinase" not in text:
                p.write_text(text.rstrip() + extra, encoding="utf-8")
    print(report, flush=True)


if __name__ == "__main__":
    main()
