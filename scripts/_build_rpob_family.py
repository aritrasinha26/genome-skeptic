#!/usr/bin/env python3
"""Build curated public rpoB/rpoC family files. Not a hidden-genome extract."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "_tmp_family_fetch.faa"

RPOB = [
    ("NP_418414.1", "Escherichia coli str. K-12 substr. MG1655", "948488", "b3987"),
    ("NP_215181.1", "Mycobacterium tuberculosis H37Rv", "888164", "Rv0667"),
    ("WP_004081508.1", "Thermotoga maritima", None, None),
    ("WP_010871995.1", "Synechocystis sp.", None, "sll1787"),
    ("WP_243759718.1", "Deinococcus radiodurans", None, None),
    ("WP_506804874.1", "Streptococcus pyogenes", None, None),
    ("WP_010881267.1", "Aquifex aeolicus", None, None),
]
RPOC = [
    ("NP_418415.1", "Escherichia coli str. K-12 substr. MG1655", "948489", "b3988"),
    ("NP_215182.1", "Mycobacterium tuberculosis H37Rv", None, "Rv0668"),
]
FORBIDDEN = [
    "NP_252960.1",
    "WP_000037869.1",
    "NP_463022.1",
    "WP_003255495.1",
    "YP_499096.2",
    "NP_387988.1",
    "NP_387989.1",
]


def parse_fasta(text: str) -> dict[str, tuple[str, str]]:
    recs: dict[str, tuple[str, str]] = {}
    name = None
    header = None
    seq: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if name:
                recs[name] = (header or name, "".join(seq))
            header = line[1:]
            name = header.split()[0]
            seq = []
        else:
            seq.append(line.strip())
    if name:
        recs[name] = (header or name, "".join(seq))
    return recs


def nw(a: str, b: str, match: int = 1, mismatch: int = -1, gap: int = -1) -> tuple[str, str]:
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    ptr = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i * gap
        ptr[i][0] = 2
    for j in range(1, m + 1):
        dp[0][j] = j * gap
        ptr[0][j] = 3
    for i in range(1, n + 1):
        ai = a[i - 1]
        row = dp[i]
        prev = dp[i - 1]
        prow = ptr[i]
        for j in range(1, m + 1):
            s = prev[j - 1] + (match if ai == b[j - 1] else mismatch)
            u = prev[j] + gap
            left = row[j - 1] + gap
            if s >= u and s >= left:
                row[j] = s
                prow[j] = 1
            elif u >= left:
                row[j] = u
                prow[j] = 2
            else:
                row[j] = left
                prow[j] = 3
    i, j = n, m
    aa: list[str] = []
    bb: list[str] = []
    while i > 0 or j > 0:
        p = ptr[i][j]
        if p == 1:
            aa.append(a[i - 1])
            bb.append(b[j - 1])
            i -= 1
            j -= 1
        elif p == 2:
            aa.append(a[i - 1])
            bb.append("-")
            i -= 1
        else:
            aa.append("-")
            bb.append(b[j - 1])
            j -= 1
    return "".join(reversed(aa)), "".join(reversed(bb))


def star_msa(seed: str, seqs: list[str]) -> list[str]:
    pairs = [nw(seed, s) for s in seqs]
    maps: list[list[int | None]] = []
    for aln_seed, _ in pairs:
        idx = 0
        mp: list[int | None] = []
        for c in aln_seed:
            if c == "-":
                mp.append(None)
            else:
                mp.append(idx)
                idx += 1
        maps.append(mp)
    nseed = len(seed)
    pre_gaps = [0] * (nseed + 1)
    for mp in maps:
        run = 0
        for x in mp:
            if x is None:
                run += 1
            else:
                pre_gaps[x] = max(pre_gaps[x], run)
                run = 0
        pre_gaps[nseed] = max(pre_gaps[nseed], run)
    master: list[tuple[str, int]] = []
    for i in range(nseed):
        for _ in range(pre_gaps[i]):
            master.append(("gap", i))
        master.append(("res", i))
    for _ in range(pre_gaps[nseed]):
        master.append(("gap", nseed))
    aligned = [""]
    seed_aln = []
    for kind, i in master:
        seed_aln.append(seed[i] if kind == "res" else "-")
    aligned[0] = "".join(seed_aln)
    for (aln_seed, aln_seq), mp in zip(pairs, maps):
        before: dict[int, list[str]] = {i: [] for i in range(nseed + 1)}
        run: list[str] = []
        for x, ch in zip(mp, aln_seq):
            if x is None:
                run.append(ch)
            else:
                before[x] = run
                run = []
        before[nseed] = run
        res_char: dict[int, str] = {}
        si = 0
        for cs, cq in zip(aln_seed, aln_seq):
            if cs != "-":
                res_char[si] = cq
                si += 1
        out: list[str] = []
        gap_used = {i: 0 for i in range(nseed + 1)}
        for kind, i in master:
            if kind == "res":
                out.append(res_char.get(i, "-"))
            else:
                buf = before[i]
                k = gap_used[i]
                out.append(buf[k] if k < len(buf) else "-")
                gap_used[i] = k + 1
        aligned.append("".join(out))
    width = len(aligned[0])
    if any(len(x) != width for x in aligned):
        raise ValueError([len(x) for x in aligned])
    return aligned


def write_fa(path: Path, ids: list[tuple], by_id: dict[str, tuple[str, str]]) -> None:
    chunks: list[str] = []
    for pid, species, gene, locus in ids:
        seq = by_id[pid][1]
        sp = species.replace(" ", "_")
        chunks.append(
            f">{pid} species={sp} gene_id={gene or 'NA'} locus_tag={locus or 'NA'} length_aa={len(seq)}\n"
        )
        for i in range(0, len(seq), 80):
            chunks.append(seq[i : i + 80] + "\n")
    path.write_text("".join(chunks), encoding="utf-8")


def write_aln(path: Path, ids: list[str], aligned: list[str]) -> None:
    chunks: list[str] = []
    for pid, seq in zip(ids, aligned):
        chunks.append(f">{pid}\n")
        for i in range(0, len(seq), 80):
            chunks.append(seq[i : i + 80] + "\n")
    path.write_text("".join(chunks), encoding="utf-8")


def main() -> None:
    by_id = parse_fasta(SRC.read_text(encoding="utf-8"))
    rpob_seqs = [by_id[p[0]][1] for p in RPOB]
    aln = star_msa(rpob_seqs[0], rpob_seqs[1:])
    members_meta = []
    for pid, species, gene, locus in RPOB:
        if pid in FORBIDDEN:
            raise SystemExit(f"forbidden protein in family: {pid}")
        members_meta.append(
            {
                "protein_id": pid,
                "species": species,
                "gene_id": gene,
                "locus_tag": locus,
                "length_aa": len(by_id[pid][1]),
                "fusion_or_split": "canonical",
                "source": "NCBI RefSeq protein FASTA",
                "retrieved": "2026-09-18",
            }
        )
    family_yaml = {
        "family_id": "rpoB_RNAP_beta",
        "display_name": "bacterial RNA polymerase subunit beta (RpoB)",
        "domain_architecture": [
            "PF00562 RNA_pol_Rpb2_1",
            "PF04560 RNA_pol_Rpb2_2",
            "PF04561 RNA_pol_Rpb2_3",
            "PF04565 RNA_pol_Rpb2_4",
            "PF04566 RNA_pol_Rpb2_5",
            "PF04563 RNA_pol_Rpb2_6",
            "PF10385 RNA_pol_Rpb2_7",
        ],
        "domain_architecture_provenance": (
            "Pfam/InterPro IPR007121 DNA-directed RNA polymerase subunit beta. "
            "Domain names are documented family architecture, not HMMER scores from this run."
        ),
        "known_fusion_or_split": [
            {
                "state": "fusion",
                "partner_family": "rpoC_RNAP_beta_prime",
                "description": (
                    "Some bacteria encode RNA polymerase beta and beta-prime as a single polypeptide. "
                    "Family-profile coverage inside a longer protein plus partner-family evidence "
                    "distinguishes a fusion orthologue from a domain fragment."
                ),
                "not_a_species_rule": True,
            },
            {
                "state": "split",
                "description": (
                    "Adjacent ORFs on the same contig and strand may jointly cover the family profile "
                    "in order. This is distinct from assembly fragmentation across contig boundaries."
                ),
            },
        ],
        "partner_families": ["rpoC_RNAP_beta_prime"],
        "members": members_meta,
        "forbidden_protein_ids": FORBIDDEN,
        "forbidden_reason": (
            "FAST_PILOT/production hidden benchmark genomes are not permitted family members. "
            "MG1655 RpoB is included because it is already the agent-visible query, not because it defines the family."
        ),
        "msa_provenance": {
            "method": "star multiple alignment seeded on NP_418414.1 using Needleman-Wunsch (match=1 mismatch=-1 gap=-1)",
            "aligner": "genome_skeptic.families.build_star_msa",
            "n_sequences": len(RPOB),
            "alignment_width": len(aln[0]),
            "not_a_published_pfam_msa": True,
        },
        "hmm_provenance": {
            "method": "hmmbuild from the curated star MSA at first use",
            "built_from": "members.aln.faa",
            "not_invented_by_llm": True,
        },
        "phylo_provenance": {
            "default": "phylogenetic placement is not required for classification",
            "used_when": "cheaper evidence leaves paralogy or family identity ambiguous",
            "tool": "FastTree when available; never invented",
        },
    }
    rpoc_meta = []
    for pid, species, gene, locus in RPOC:
        rpoc_meta.append(
            {
                "protein_id": pid,
                "species": species,
                "gene_id": gene,
                "locus_tag": locus,
                "length_aa": len(by_id[pid][1]),
                "fusion_or_split": "canonical",
                "source": "NCBI RefSeq protein FASTA",
                "retrieved": "2026-09-18",
            }
        )
    rpoc_yaml = {
        "family_id": "rpoC_RNAP_beta_prime",
        "display_name": "bacterial RNA polymerase subunit beta-prime (RpoC)",
        "role": "partner family for fusion tests; not a substitute rpoB definition",
        "members": rpoc_meta,
        "forbidden_protein_ids": FORBIDDEN,
        "domain_architecture": ["PF04997 RNA_pol_Rpb1_1", "PF00623 RNA_pol_Rpb1_2", "PF04983 RNA_pol_Rpb1_3"],
        "msa_provenance": {"method": "star MSA seeded on NP_418415.1"},
        "hmm_provenance": {"method": "hmmbuild from members.aln.faa at first use"},
        "phylo_provenance": {"default": "not used unless extra fusion sequence identity is ambiguous"},
    }
    rpoc_seqs = [by_id[p[0]][1] for p in RPOC]
    rpoc_aln = star_msa(rpoc_seqs[0], rpoc_seqs[1:])
    index = {
        "aliases": {
            "rpoB": "rpoB_RNAP_beta",
            "rpoB_RNAP_beta": "rpoB_RNAP_beta",
            "rpoC": "rpoC_RNAP_beta_prime",
            "rpoC_RNAP_beta_prime": "rpoC_RNAP_beta_prime",
        }
    }
    for base in (ROOT / "data" / "target_families", ROOT / "src" / "genome_skeptic" / "data" / "target_families"):
        (base / "rpoB_RNAP_beta").mkdir(parents=True, exist_ok=True)
        (base / "rpoC_RNAP_beta_prime").mkdir(parents=True, exist_ok=True)
        write_fa(base / "rpoB_RNAP_beta" / "members.faa", RPOB, by_id)
        write_aln(base / "rpoB_RNAP_beta" / "members.aln.faa", [p[0] for p in RPOB], aln)
        (base / "rpoB_RNAP_beta" / "family.yaml").write_text(yaml.safe_dump(family_yaml, sort_keys=False), encoding="utf-8")
        write_fa(base / "rpoC_RNAP_beta_prime" / "members.faa", RPOC, by_id)
        write_aln(base / "rpoC_RNAP_beta_prime" / "members.aln.faa", [p[0] for p in RPOC], rpoc_aln)
        (base / "rpoC_RNAP_beta_prime" / "family.yaml").write_text(yaml.safe_dump(rpoc_yaml, sort_keys=False), encoding="utf-8")
        (base / "index.yaml").write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")
    print("rpoB members", len(RPOB), "aln_width", len(aln[0]))
    print("rpoC members", len(RPOC), "aln_width", len(rpoc_aln[0]))


if __name__ == "__main__":
    main()
