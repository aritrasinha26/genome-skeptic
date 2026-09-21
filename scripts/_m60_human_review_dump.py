#!/usr/bin/env python3
"""Build prediction-free human-review packets for the 20 flagged M60 cases.

Does not open prediction files. Does not score accuracy.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
TRUTH = ROOT / "manuscript_benchmark" / "TRUTH_M60"
NATIVE = Path("/home/aritr/m60_work/truth_evidence")
CASES = [3, 7, 8, 9, 11, 20, 23, 25, 26, 29, 31, 34, 35, 39, 40, 50, 52, 55, 56, 60]


def parse_blast6(path: Path) -> list[dict]:
    rows = []
    if not path.exists() or path.stat().st_size == 0:
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        p = line.split("\t")
        if len(p) < 12:
            continue
        try:
            ident = float(p[2]) / 100.0 if float(p[2]) > 1.5 else float(p[2])
            qcov = float(p[12]) / 100.0 if len(p) > 12 and p[12] not in {".", ""} else None
            qlen = int(float(p[4])) if p[4] not in {".", ""} else None
            slen = int(float(p[5])) if p[5] not in {".", ""} else None
            rows.append(
                {
                    "query": p[0],
                    "subject": p[1],
                    "identity": round(ident, 4),
                    "aln_len": int(float(p[3])),
                    "qlen": qlen,
                    "slen": slen,
                    "coverage": None if qcov is None else round(qcov, 4),
                    "evalue": float(p[10]),
                    "bitscore": float(p[11]),
                    "length_ratio": round(qlen / slen, 4) if qlen and slen else None,
                }
            )
        except ValueError:
            continue
    rows.sort(key=lambda r: -((r["identity"] or 0) * (r["coverage"] or 0)))
    return rows[:8]


def main() -> None:
    out = []
    for pos in CASES:
        rec = json.loads((TRUTH / "CASE_RECORDS" / f"position_{pos:02d}.json").read_text(encoding="utf-8"))
        acc = rec["accession"]
        target = rec["target"]
        ev_pub = TRUTH / "EVIDENCE" / f"position_{pos:02d}_{acc}_{target}"
        ev_nat = NATIVE / f"position_{pos:02d}_{acc}_{target}"
        ev = ev_nat if ev_nat.exists() else ev_pub
        orfs = []
        orf_path = ev / "orfs.json"
        if orf_path.exists():
            orfs = json.loads(orf_path.read_text(encoding="utf-8"))
        orf_id = (rec.get("candidate_sequence_ids") or ["orf_00"])[0]
        idx = int(orf_id.split("_")[-1])
        orf_dir = ev / f"orf_{idx:02d}"
        packet = {
            "position": pos,
            "case_id": rec["case_id"],
            "accession": acc,
            "target": target,
            "stratum": rec["stratum"],
            "pre_review_truth": rec.get("final_truth") or rec.get("truth_value"),
            "route1": rec.get("evidence_route_1"),
            "route2": rec.get("evidence_route_2"),
            "concordance": rec.get("evidence_route_concordance"),
            "coords": rec.get("candidate_coordinates"),
            "aa_length_record": None,
            "sequence_identity": rec.get("sequence_similarity"),
            "sequence_coverage": rec.get("sequence_coverage"),
            "family_or_profile_result": rec.get("family_or_profile_result"),
            "phylo": rec.get("orthology_or_phylogeny_result"),
            "primary_refs": rec.get("primary_reference_accessions"),
            "competitor_refs": rec.get("competitor_reference_accessions"),
            "n_orfs": rec.get("n_orfs_scored"),
            "orfs_brief": [
                {
                    "contig": o.get("contig"),
                    "strand": o.get("strand"),
                    "start": o.get("genomic_start"),
                    "end": o.get("genomic_end"),
                    "aa_length": o.get("aa_length"),
                    "seed": o.get("seed_hit"),
                    "core_aa_length": (o.get("orf_meta") or {}).get("core_aa_length"),
                }
                for o in orfs
            ],
            "blastp_target_top": parse_blast6(orf_dir / "blastp_target.tsv") if orf_dir.exists() else [],
            "blastp_comp_top": parse_blast6(orf_dir / "blastp_comp.tsv") if orf_dir.exists() else [],
            "candidate_faa_exists": (orf_dir / "candidate.faa").exists() if orf_dir.exists() else False,
            "evidence_dir": str(ev),
        }
        if orfs and idx < len(orfs):
            packet["aa_length_record"] = orfs[idx].get("aa_length")
        elif orfs:
            packet["aa_length_record"] = orfs[0].get("aa_length")
        out.append(packet)
        print("=" * 80)
        print(f"POS {pos:02d} {acc} {target} stratum={rec['stratum']}")
        print(f" pre={packet['pre_review_truth']} conc={packet['concordance']}")
        print(f" r1={packet['route1']}")
        print(f" r2={packet['route2']}")
        print(f" ident={packet['sequence_identity']} cov={packet['sequence_coverage']} aa={packet['aa_length_record']}")
        print(f" hmm={packet['family_or_profile_result']}")
        print(f" target_blastp={packet['blastp_target_top'][:3]}")
        print(f" comp_blastp={packet['blastp_comp_top'][:3]}")
        print(f" orfs={packet['orfs_brief']}")
    (TRUTH / "HUMAN_REVIEW").mkdir(parents=True, exist_ok=True)
    (TRUTH / "HUMAN_REVIEW" / "_packet_dump.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
