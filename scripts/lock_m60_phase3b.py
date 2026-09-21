#!/usr/bin/env python3
"""M60 Phase 3B: blinded human truth adjudication.

Review only the 20 cases in M60_HUMAN_REVIEW_REQUIRED.csv.
Does not open prediction payloads. Does not score accuracy.
Does not overwrite the original Phase 3 truth lock.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from m60_truth_common import (  # noqa: E402
    CASE_RECORDS,
    TRUTH_ROOT,
    sha256_file,
    utc_now,
    write_json,
    write_sha256_sidecar,
)

EXPECTED_TRUTH = "bb37539060efd3e89e0bd548fe1d0e573991dab0816bdead729286cbfcfedb38"
EXPECTED_LOCK = "f6636498de4f7ebc61b50fc85a5a1f48065100b27bfb5eda29e712249fe8c491"

HUMAN_REVIEW_DIR = TRUTH_ROOT / "HUMAN_REVIEW"
NATIVE = Path("/home/aritr/m60_work/truth_evidence")

RPOB_MEMBERS = {
    "NP_418414.1",
    "NP_215181.1",
    "WP_004081508.1",
    "WP_010871995.1",
    "WP_243759718.1",
    "WP_506804874.1",
    "WP_010881267.1",
    "P0A8V2",
    "P37870",
    "O67077",
    "Q9WYB5",
}
RPOC_MEMBERS = {"NP_418415.1", "NP_215182.1"}
TETA_MEMBERS = {"P02980", "P02982"}

REVIEWER = "blinded_human_adjudicator_phase3b"
REVIEW_DATE = "2026-09-21"

# Frozen-endpoint human calls. Only POSITIVE/NEGATIVE when independent
# evidence is decisive under M60_PROTOCOL_V1_1.md. Otherwise retain UNCERTAIN.
ADJUDICATION = {
    3: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "Best independent locus is 613 aa vs O67077 at identity 0.475, coverage 0.953; "
            "HMM coverage 0. A longer 1692 aa locus matches rpoC (NP_418415.1) at identity 0.542. "
            "No frozen rpoB member reaches identity 0.60 with coverage 0.80 and length ratio 0.80-1.20. "
            "Orthology remains unresolved; HMM cannot override the identity gate."
        ),
        "confidence_note": (
            "Retained UNCERTAIN: identity below 0.60 and no discriminating profile; "
            "not converted to NEGATIVE because residual rpoB-like sequence exists."
        ),
    },
    7: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "Scored locus 766 aa vs O67077 at identity 0.436, coverage 0.779 (below 0.80, inside "
            "near-threshold coverage band). HMM coverage 0. A 1351 aa locus matches rpoC "
            "(NP_215182.1) at identity 0.582. No full-length rpoB member meets identity 0.60. "
            "Fragmentation versus partner-subunit identity is not resolvable from the packet."
        ),
        "confidence_note": "Retained UNCERTAIN: near-threshold/fragmented architecture, not sequence-decisive.",
    },
    8: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "Candidate is a 204 aa fragment (length ratio 0.51 vs P02980 401 aa) at identity 0.330, "
            "coverage 1.0 (product 0.330, far below 0.70). Competitor P0AEY8 identity 0.279, "
            "coverage 0.588. Target HMM coverage 0.424 (domain-only band), score 109.9. "
            "Not convincing tet(A)/tet(B) family-level placement. Competitor is not sequence-decisive "
            "(product 0.164 < 0.70), so absence is also not proven."
        ),
        "confidence_note": (
            "Retained UNCERTAIN: residual tetAB-like fragment without family-level placement; "
            "route-1 POSITIVE is not supported under the frozen tetA gate."
        ),
    },
    9: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "1155 aa candidate vs P37870 at identity 0.479, coverage 0.993, length ratio 0.968. "
            "Other frozen members are also below 0.60 (WP_506804874.1 0.472; WP_010871995.1 0.483). "
            "HMM prefers target (coverage 0.948, score 1443) with rpoC HMM 0. Full-length architecture "
            "is consistent with RNAP beta, but identity remains below the frozen 0.60 gate. "
            "Profile evidence is corroboration only and does not override identity."
        ),
        "confidence_note": "Retained UNCERTAIN: identity 0.479 < 0.60 despite strong HMM.",
    },
    11: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "1372 aa candidate vs NP_418414.1/P0A8V2 at identity 0.582, coverage 0.988, "
            "length ratio 1.022. HMM coverage 0.990, score 1742.4; rpoC HMM 0. Identity sits in "
            "the frozen near-threshold band (|0.582-0.60|=0.018 <= 0.10) and does not meet >= 0.60. "
            "HMM cannot licence a POSITIVE override."
        ),
        "confidence_note": "Retained UNCERTAIN: near-threshold identity 0.582; architecture full-length but gate unmet.",
    },
    20: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "Scored locus is a 278 aa domain-scale peptide vs Q9WYB5 (281 aa) at identity 0.351, "
            "coverage 0.932; HMM 0. A 1326 aa locus matches rpoC (NP_215182.1) at identity 0.901. "
            "A 776 aa O67077-seeded ORF is present but was not sequence-decisive. Domain fragment "
            "versus unresolved split cannot be closed from this packet."
        ),
        "confidence_note": (
            "Retained UNCERTAIN: not NEGATIVE because rpoC presence does not prove rpoB absence, "
            "and additional partial ORFs remain."
        ),
    },
    23: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "161 aa fragment vs P02982 at identity 0.253, coverage 0.882 (product 0.223); "
            "length ratio 0.40. Competitor P28246 identity 0.354, coverage 1.0 (product 0.354), "
            "still far below 0.70. HMM target coverage 0.329 vs competitor MFS 0.418 — not separated. "
            "No convincing tet(A)/tet(B) family-level placement; competitor product is also not decisive."
        ),
        "confidence_note": "Retained UNCERTAIN: ambiguous remote MFS/tetAB fragment.",
    },
    25: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "1380 aa candidate vs NP_418414.1 at identity 0.579, coverage 0.984, length ratio 1.028. "
            "HMM coverage 0.989, score 1715.4; rpoC HMM 0. Near-threshold identity band; "
            "identity gate 0.60 not met. HMM is corroboration only."
        ),
        "confidence_note": "Retained UNCERTAIN: identity 0.579 < 0.60.",
    },
    26: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "1397 aa candidate vs NP_418414.1 at identity 0.561, coverage 0.996, length ratio 1.041. "
            "HMM coverage 0.990, score 1695.6; rpoC HMM 0. Near-threshold identity; frozen POSITIVE "
            "requires identity >= 0.60."
        ),
        "confidence_note": "Retained UNCERTAIN: identity 0.561 < 0.60.",
    },
    29: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "404 aa candidate vs P02980 at identity 0.280, coverage 0.460 (product 0.129). "
            "Competitor P28246 identity 0.269, coverage 0.918 (product 0.247). HMM coverage 0.742 "
            "but score only 41.7. Neither tetAB nor competitor is sequence-decisive "
            "(product >= 0.70 with delta >= 0.20). Not convincing tet(A)/tet(B) placement."
        ),
        "confidence_note": (
            "Retained UNCERTAIN: route-1 POSITIVE is not supported; competitor not decisive enough for NEGATIVE."
        ),
    },
    31: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "335 aa candidate vs P02982 at identity 0.224, coverage 0.319 (product 0.071). "
            "Competitor P0AEJ0 identity 0.275, coverage 1.0 (product 0.275). HMM coverage 0.434, "
            "score 43.2. Seed of this ORF is the competitor family. TetAB alignment is a short "
            "spurious HSP. Competitor product still < 0.70, so competing-family preference is not "
            "sequence-decisive."
        ),
        "confidence_note": "Retained UNCERTAIN: remote MFS-like locus without tetAB family-level match.",
    },
    34: {
        "human_review_truth": "NEGATIVE",
        "evidence_basis": (
            "No independent sequence match to frozen tet(A)/tet(B) members P02980 or P02982 "
            "(target blastp empty; no tetAB tblastn seed among recovered ORFs). The recovered "
            "locus is competitor P0AEJ0 at identity 0.340, coverage 0.982. Residual tetA HMM "
            "coverage 0.412, score 34.3 is a weak generic MFS profile on a non-tetAB protein. "
            "Protocol step 1: no tetA family candidate locus -> NEGATIVE. Remote HMM is not a locus."
        ),
        "confidence_note": (
            "Resolved NEGATIVE with high confidence: absence of tetAB sequence match is decisive; "
            "generic MFS HMM does not create a tet(A)/tet(B) candidate."
        ),
    },
    35: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "754 aa candidate vs O67077 at identity 0.535, coverage 0.613 (below 0.80). HMM 0. "
            "A 1336 aa locus matches rpoC (NP_215182.1) at identity 0.646. Partial coverage "
            "without a resolvable split."
        ),
        "confidence_note": "Retained UNCERTAIN: fragmented rpoB-like locus, identity below gate.",
    },
    39: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "707 aa candidate vs O67077 at identity 0.477, coverage 0.874, length ratio 1.115. "
            "HMM 0. A 1319 aa locus matches rpoC (NP_418415.1) at identity 0.488. Identity below 0.60; "
            "no discriminating profile."
        ),
        "confidence_note": "Retained UNCERTAIN: unresolved rpoB orthology.",
    },
    40: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "1379 aa candidate vs NP_418414.1 at identity 0.582, coverage 0.985, length ratio 1.028. "
            "HMM coverage 0.990, score 1709.3; rpoC HMM 0. Near-threshold identity; gate unmet."
        ),
        "confidence_note": "Retained UNCERTAIN: identity 0.582 < 0.60.",
    },
    50: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "644 aa candidate vs O67077 at identity 0.484, coverage 0.798 (just below 0.80, "
            "inside near-threshold coverage band), length ratio 1.016. HMM 0. A 1424 aa locus "
            "matches rpoC (NP_418415.1) at identity 0.488."
        ),
        "confidence_note": "Retained UNCERTAIN: near-threshold coverage and identity below 0.60.",
    },
    52: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "1380 aa candidate vs NP_418414.1 at identity 0.581, coverage 0.984, length ratio 1.028. "
            "HMM coverage 0.989, score 1720.3; rpoC HMM 0. Near-threshold identity; gate unmet."
        ),
        "confidence_note": "Retained UNCERTAIN: identity 0.581 < 0.60.",
    },
    55: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "666 aa candidate vs O67077 at identity 0.483, coverage 0.869, length ratio 1.051. "
            "HMM 0. A 1310 aa locus matches rpoC (NP_215182.1) at identity 0.590. Identity below 0.60."
        ),
        "confidence_note": "Retained UNCERTAIN: unresolved rpoB orthology.",
    },
    56: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "677 aa candidate vs O67077 at identity 0.502, coverage 0.753 (below 0.80). HMM 0. "
            "A 1320 aa locus matches rpoC (NP_215182.1) at identity 0.633. Near-threshold coverage "
            "without decisive architecture."
        ),
        "confidence_note": "Retained UNCERTAIN: identity 0.502 and coverage 0.753 both fail the rpoB gate.",
    },
    60: {
        "human_review_truth": "TRUTH_UNCERTAIN",
        "evidence_basis": (
            "1379 aa candidate vs NP_418414.1 at identity 0.583, coverage 0.985, length ratio 1.028. "
            "HMM coverage 0.989, score 1714.1; rpoC HMM 0. Closest near-threshold case in the review "
            "set, still below identity 0.60. HMM cannot override."
        ),
        "confidence_note": "Retained UNCERTAIN: identity 0.583 < 0.60.",
    },
}


FORBIDDEN_PACKET_TOKENS = (
    "amrfinder",
    "pgap",
    "genome skeptic",
    "gs_agentic",
    "gs_deterministic",
    "gs_exhaustive",
    "conventional",
    "claims.json",
    "d20",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_original_lock() -> None:
    truth = TRUTH_ROOT / "M60_EXTERNAL_TRUTH_LOCKED.json"
    lock = TRUTH_ROOT / "M60_TRUTH_LOCK_MANIFEST.json"
    t = _sha256(truth)
    l = _sha256(lock)
    if t != EXPECTED_TRUTH:
        raise SystemExit(f"ORIGINAL TRUTH HASH MISMATCH got={t} expected={EXPECTED_TRUTH}")
    if l != EXPECTED_LOCK:
        raise SystemExit(f"ORIGINAL LOCK MANIFEST HASH MISMATCH got={l} expected={EXPECTED_LOCK}")
    print(f"ORIGINAL_TRUTH_SHA256 MATCH {t}")
    print(f"ORIGINAL_LOCK_MANIFEST_SHA256 MATCH {l}")


def parse_blast6(path: Path, limit: int = 8) -> list[dict]:
    rows = []
    if not path.exists() or path.stat().st_size == 0:
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        p = line.split("\t")
        if len(p) < 12:
            continue
        try:
            ident_raw = float(p[2])
            ident = ident_raw / 100.0 if ident_raw > 1.5 else ident_raw
            qlen = int(float(p[4])) if p[4] not in {".", ""} else None
            slen = int(float(p[5])) if p[5] not in {".", ""} else None
            qcov = None
            if len(p) > 12 and p[12] not in {".", ""}:
                qc = float(p[12])
                qcov = qc / 100.0 if qc > 1.5 else qc
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
                    "family_panel": (
                        "target_rpoB"
                        if p[1] in RPOB_MEMBERS
                        else "competitor_rpoC"
                        if p[1] in RPOC_MEMBERS
                        else "target_tetAB"
                        if p[1] in TETA_MEMBERS
                        else "other_or_competitor"
                    ),
                }
            )
        except ValueError:
            continue
    rows.sort(key=lambda r: -((r.get("identity") or 0) * (r.get("coverage") or 0)))
    return rows[:limit]


def read_faa(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    recs = []
    header = None
    chunks: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(">"):
            if header is not None:
                recs.append((header, "".join(chunks)))
            header = line[1:].strip().split()[0]
            chunks = []
        else:
            chunks.append(line.strip())
    if header is not None:
        recs.append((header, "".join(chunks)))
    return recs


def evidence_dir(rec: dict) -> Path:
    acc = rec["accession"]
    target = rec["target"]
    pos = int(rec["position"])
    pub = TRUTH_ROOT / "EVIDENCE" / f"position_{pos:02d}_{acc}_{target}"
    nat = NATIVE / f"position_{pos:02d}_{acc}_{target}"
    return nat if nat.exists() else pub


def assert_packet_clean(obj) -> None:
    blob = json.dumps(obj).lower()
    for tok in FORBIDDEN_PACKET_TOKENS:
        if tok in blob:
            raise SystemExit(f"predictor token leaked into packet: {tok}")


def build_packet(rec: dict, review_row: dict) -> dict:
    pos = int(rec["position"])
    ev = evidence_dir(rec)
    orfs = []
    orf_path = ev / "orfs.json"
    if orf_path.exists():
        orfs = json.loads(orf_path.read_text(encoding="utf-8"))
    orf_id = (rec.get("candidate_sequence_ids") or ["orf_00"])[0]
    try:
        idx = int(str(orf_id).split("_")[-1])
    except ValueError:
        idx = 0
    orf_dir = ev / f"orf_{idx:02d}"
    faa = read_faa(orf_dir / "candidate.faa") if orf_dir.exists() else []
    seq = faa[0][1] if faa else ""
    coords = rec.get("candidate_coordinates") or {}
    fam = rec.get("family_or_profile_result") or {}
    phy = rec.get("orthology_or_phylogeny_result") or {}
    r1 = rec.get("evidence_route_1") or {}
    r2 = rec.get("evidence_route_2") or {}

    independent_orfs = []
    for o in orfs:
        seed = o.get("seed_hit") or {}
        independent_orfs.append(
            {
                "contig": o.get("contig"),
                "strand": o.get("strand"),
                "start": o.get("genomic_start"),
                "end": o.get("genomic_end"),
                "aa_length": o.get("aa_length"),
                "core_aa_length": (o.get("orf_meta") or {}).get("core_aa_length"),
                "independent_seed_subject": seed.get("sseqid"),
                "independent_seed_identity": seed.get("pident"),
                "independent_seed_evalue": seed.get("evalue"),
                "independent_seed_bitscore": seed.get("bitscore"),
            }
        )

    packet = {
        "case_id": rec["case_id"],
        "position": pos,
        "accession": rec["accession"],
        "target": rec["target"],
        "stratum": rec["stratum"],
        "reason_flagged": review_row.get("reason_for_review"),
        "candidate_sequence_ids": rec.get("candidate_sequence_ids"),
        "candidate_sequences": [
            {
                "sequence_id": orf_id,
                "aa_length": len(seq) if seq else (orfs[idx].get("aa_length") if idx < len(orfs) else None),
                "amino_acid_sequence": seq or None,
            }
        ],
        "coordinates": {
            "contig": coords.get("contig"),
            "strand": coords.get("strand"),
            "start": coords.get("start"),
            "end": coords.get("end"),
        },
        "sequence_length_aa": rec.get("sequence_coverage") and (
            orfs[idx].get("aa_length") if idx < len(orfs) else (len(seq) or None)
        ) or (orfs[idx].get("aa_length") if idx < len(orfs) else (len(seq) or None)),
        "independent_reference_matches": independent_orfs,
        "target_reference_evidence": parse_blast6(orf_dir / "blastp_target.tsv") if orf_dir.exists() else [],
        "competitor_reference_evidence": parse_blast6(orf_dir / "blastp_comp.tsv") if orf_dir.exists() else [],
        "coverage": rec.get("sequence_coverage"),
        "identity": rec.get("sequence_similarity"),
        "profile_domain_evidence": {
            "target_hmm_model_coverage": fam.get("target_hmm_model_coverage"),
            "target_hmm_score": fam.get("target_hmm_score"),
            "target_hmm_evalue": fam.get("target_hmm_evalue"),
            "competitor_hmm_family": fam.get("competitor_hmm_family"),
            "competitor_hmm_model_coverage": fam.get("competitor_hmm_model_coverage"),
            "competitor_hmm_score": fam.get("competitor_hmm_score"),
        },
        "orthology_phylogenetic_evidence": phy,
        "evidence_route_disagreement": {
            "concordance": rec.get("evidence_route_concordance"),
            "route1_value": r1.get("value"),
            "route1_reason": r1.get("reason"),
            "route2_value": r2.get("value"),
            "route2_reason": r2.get("reason"),
        },
        "relevant_evidence_artifact_paths": [
            str(ev).replace("\\", "/"),
            f"manuscript_benchmark/TRUTH_M60/EVIDENCE/position_{pos:02d}_{rec['accession']}_{rec['target']}",
            f"manuscript_benchmark/TRUTH_M60/CASE_RECORDS/position_{pos:02d}.json",
        ],
        "prediction_payloads_included": False,
        "predictor_names_included": False,
    }
    assert_packet_clean(packet)
    return packet


def packet_markdown(p: dict) -> str:
    seq = (p["candidate_sequences"][0].get("amino_acid_sequence") or "")
    seq_show = seq if seq else "(sequence file not present in evidence directory)"
    coords = p["coordinates"]
    fam = p["profile_domain_evidence"]
    routes = p["evidence_route_disagreement"]
    lines = [
        f"# Human-review packet {p['case_id']}",
        "",
        "Prediction-free independent evidence only.",
        "",
        f"- case_id: `{p['case_id']}`",
        f"- accession: `{p['accession']}`",
        f"- target: `{p['target']}`",
        f"- stratum: `{p['stratum']}`",
        f"- reason flagged: {p['reason_flagged']}",
        f"- candidate sequence id: {p['candidate_sequence_ids']}",
        f"- coordinates: {coords.get('contig')} {coords.get('strand')} {coords.get('start')}-{coords.get('end')}",
        f"- sequence length (aa): {p['sequence_length_aa']}",
        f"- coverage: {p['coverage']}",
        f"- identity: {p['identity']}",
        "",
        "## Target-reference evidence",
        "",
        "```json",
        json.dumps(p["target_reference_evidence"], indent=2),
        "```",
        "",
        "## Competitor-reference evidence",
        "",
        "```json",
        json.dumps(p["competitor_reference_evidence"], indent=2),
        "```",
        "",
        "## Profile / domain evidence",
        "",
        "```json",
        json.dumps(fam, indent=2),
        "```",
        "",
        "## Orthology / phylogenetic evidence",
        "",
        "```json",
        json.dumps(p["orthology_phylogenetic_evidence"], indent=2),
        "```",
        "",
        "## Evidence-route disagreement",
        "",
        "```json",
        json.dumps(routes, indent=2),
        "```",
        "",
        "## Independent reference matches (all recovered loci)",
        "",
        "```json",
        json.dumps(p["independent_reference_matches"], indent=2),
        "```",
        "",
        "## Candidate amino-acid sequence",
        "",
        f"> {p['candidate_sequences'][0]['sequence_id']} len={p['candidate_sequences'][0]['aa_length']}",
        "",
        seq_show,
        "",
        "## Relevant evidence artifact paths",
        "",
    ]
    for path in p["relevant_evidence_artifact_paths"]:
        lines.append(f"- `{path}`")
    lines.append("")
    return "\n".join(lines)


def count(rows, pred) -> int:
    return sum(1 for r in rows if pred(r))


def main() -> int:
    verify_original_lock()

    original = json.loads((TRUTH_ROOT / "M60_EXTERNAL_TRUTH_LOCKED.json").read_text(encoding="utf-8"))
    if original.get("n_cases") != 60:
        raise SystemExit("original lock n_cases != 60")

    review_required = {}
    with (TRUTH_ROOT / "M60_HUMAN_REVIEW_REQUIRED.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            review_required[int(row["position"])] = row
    if len(review_required) != 20:
        raise SystemExit(f"expected 20 review cases, got {len(review_required)}")
    expected_pos = set(ADJUDICATION)
    if set(review_required) != expected_pos:
        raise SystemExit(f"review positions {sorted(review_required)} != {sorted(expected_pos)}")

    HUMAN_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    packets = []
    for pos in sorted(review_required):
        rec = json.loads((CASE_RECORDS / f"position_{pos:02d}.json").read_text(encoding="utf-8"))
        packet = build_packet(rec, review_required[pos])
        packets.append(packet)
        stem = f"position_{pos:02d}_{rec['case_id']}"
        (HUMAN_REVIEW_DIR / f"{stem}.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        (HUMAN_REVIEW_DIR / f"{stem}.md").write_text(packet_markdown(packet), encoding="utf-8")

    index_rows = [
        {
            "position": p["position"],
            "case_id": p["case_id"],
            "accession": p["accession"],
            "target": p["target"],
            "stratum": p["stratum"],
            "reason_flagged": p["reason_flagged"],
            "packet_json": f"position_{p['position']:02d}_{p['case_id']}.json",
            "packet_md": f"position_{p['position']:02d}_{p['case_id']}.md",
        }
        for p in packets
    ]
    with (HUMAN_REVIEW_DIR / "INDEX.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(index_rows[0].keys()))
        w.writeheader()
        w.writerows(index_rows)

    adj_rows = []
    overlay = {}
    for pos, row in sorted(review_required.items()):
        rec = json.loads((CASE_RECORDS / f"position_{pos:02d}.json").read_text(encoding="utf-8"))
        pre = rec.get("final_truth") or rec.get("truth_value")
        call = ADJUDICATION[pos]
        human = call["human_review_truth"]
        changed = "yes" if human != pre else "no"
        adj_rows.append(
            {
                "case_id": rec["case_id"],
                "position": pos,
                "target": rec["target"],
                "pre_review_truth": pre,
                "human_review_truth": human,
                "changed_yes_no": changed,
                "evidence_basis": call["evidence_basis"],
                "reviewer": REVIEWER,
                "review_date": REVIEW_DATE,
                "confidence_note": call["confidence_note"],
            }
        )
        overlay[pos] = {
            "human_review_truth": human,
            "changed_yes_no": changed,
            "evidence_basis": call["evidence_basis"],
            "confidence_note": call["confidence_note"],
            "pre_review_truth": pre,
        }

    adj_path = TRUTH_ROOT / "M60_HUMAN_ADJUDICATION.csv"
    with adj_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "case_id",
                "position",
                "target",
                "pre_review_truth",
                "human_review_truth",
                "changed_yes_no",
                "evidence_basis",
                "reviewer",
                "review_date",
                "confidence_note",
            ],
        )
        w.writeheader()
        w.writerows(adj_rows)
    write_sha256_sidecar(adj_path)

    original_review = []
    with (TRUTH_ROOT / "M60_TRUTH_REVIEW.csv").open(encoding="utf-8", newline="") as fh:
        original_review = list(csv.DictReader(fh))

    final_cases = []
    final_case_csv = []
    final_review_csv = []
    for case in original["cases"]:
        pos = int(case["position"])
        updated = dict(case)
        if pos in overlay:
            human = overlay[pos]["human_review_truth"]
            updated["truth_value"] = human
            updated["final_truth"] = human
            updated["human_review_truth"] = human
            updated["pre_review_truth"] = overlay[pos]["pre_review_truth"]
            updated["human_review_changed"] = overlay[pos]["changed_yes_no"]
            updated["human_review_evidence_basis"] = overlay[pos]["evidence_basis"]
            updated["human_reviewer"] = REVIEWER
            updated["human_review_date"] = REVIEW_DATE
            updated["human_review_completed"] = True
            updated["truth_status"] = (
                "ADJUDICATED" if human in {"POSITIVE", "NEGATIVE"} else "HUMAN_REVIEWED_UNCERTAIN"
            )
        else:
            updated["human_review_completed"] = False
            updated["human_review_truth"] = case.get("truth_value")
            updated["pre_review_truth"] = case.get("truth_value")
            updated["human_review_changed"] = "no"
        final_cases.append(updated)
        final_case_csv.append(
            {
                "case_id": updated["case_id"],
                "position": updated["position"],
                "accession": updated["accession"],
                "target": updated["target"],
                "stratum": updated["stratum"],
                "truth_value": updated["truth_value"],
                "truth_status": updated["truth_status"],
                "evidence_route_concordance": updated.get("evidence_route_concordance"),
                "sequence_similarity": updated.get("sequence_similarity"),
                "sequence_coverage": updated.get("sequence_coverage"),
                "primary_reference_accessions": ";".join(updated.get("primary_reference_accessions") or []),
                "human_review_required": pos in overlay,
                "human_review_completed": updated.get("human_review_completed"),
                "human_review_truth": updated.get("human_review_truth"),
            }
        )

    review_by_pos = {int(r["position"]): r for r in original_review}
    for pos in range(1, 61):
        base = dict(review_by_pos[pos])
        if pos in overlay:
            base["pre_review_truth"] = overlay[pos]["pre_review_truth"]
            base["human_review_truth"] = overlay[pos]["human_review_truth"]
            base["changed_yes_no"] = overlay[pos]["changed_yes_no"]
            base["final_truth"] = overlay[pos]["human_review_truth"]
            base["resolution_note"] = overlay[pos]["evidence_basis"]
            base["reviewer"] = REVIEWER
            base["review_date"] = REVIEW_DATE
            base["human_review_completed"] = True
        else:
            base["pre_review_truth"] = base.get("final_truth")
            base["human_review_truth"] = base.get("final_truth")
            base["changed_yes_no"] = "no"
            base["reviewer"] = ""
            base["review_date"] = ""
            base["human_review_completed"] = False
        final_review_csv.append(base)

    summary = {
        "kind": "M60_BLINDED_TRUTH_SET_SUMMARY_FINAL",
        "total": 60,
        "tetA": 30,
        "rpoB": 30,
        "POSITIVE": count(final_cases, lambda r: r["truth_value"] == "POSITIVE"),
        "NEGATIVE": count(final_cases, lambda r: r["truth_value"] == "NEGATIVE"),
        "TRUTH_UNCERTAIN": count(final_cases, lambda r: r["truth_value"] == "TRUTH_UNCERTAIN"),
        "tetA_POSITIVE": count(final_cases, lambda r: r["target"].startswith("tetA") and r["truth_value"] == "POSITIVE"),
        "tetA_NEGATIVE": count(final_cases, lambda r: r["target"].startswith("tetA") and r["truth_value"] == "NEGATIVE"),
        "tetA_TRUTH_UNCERTAIN": count(
            final_cases, lambda r: r["target"].startswith("tetA") and r["truth_value"] == "TRUTH_UNCERTAIN"
        ),
        "rpoB_POSITIVE": count(final_cases, lambda r: r["target"].startswith("rpoB") and r["truth_value"] == "POSITIVE"),
        "rpoB_NEGATIVE": count(final_cases, lambda r: r["target"].startswith("rpoB") and r["truth_value"] == "NEGATIVE"),
        "rpoB_TRUTH_UNCERTAIN": count(
            final_cases, lambda r: r["target"].startswith("rpoB") and r["truth_value"] == "TRUTH_UNCERTAIN"
        ),
        "human_review_cases": 20,
        "cases_resolved_by_human_review": count(adj_rows, lambda r: r["changed_yes_no"] == "yes"),
        "cases_remaining_uncertain_after_human_review": count(
            adj_rows, lambda r: r["human_review_truth"] == "TRUTH_UNCERTAIN"
        ),
        "accuracy_scored": False,
        "prediction_payloads_opened": False,
        "d20_touched": False,
        "original_truth_lock_unaltered": True,
        "original_truth_sha256": EXPECTED_TRUTH,
        "original_lock_manifest_sha256": EXPECTED_LOCK,
    }

    final_json = {
        "kind": "M60_EXTERNAL_TRUTH_FINAL_LOCKED",
        "freeze_id": "GENOME_SKEPTIC_V4_1_MANUSCRIPT",
        "n_cases": 60,
        "created_utc": utc_now(),
        "do_not_regenerate": True,
        "phase": "3B_human_adjudication",
        "original_truth_lock_unaltered": True,
        "original_truth_sha256": EXPECTED_TRUTH,
        "original_lock_manifest_sha256": EXPECTED_LOCK,
        "prediction_payloads_opened": False,
        "amrfinder_used_as_truth": False,
        "pgap_used_as_truth": False,
        "gs_predictions_used_as_truth": False,
        "d20_touched": False,
        "accuracy_scored": False,
        "two_independent_evidence_routes": True,
        "two_independent_reviewers": False,
        "human_review_completed": True,
        "human_review_cases": 20,
        "reviewer": REVIEWER,
        "review_date": REVIEW_DATE,
        "cases": final_cases,
        "blinded_summary": summary,
    }

    tpath = TRUTH_ROOT / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json"
    write_json(tpath, final_json)

    csv_path = TRUTH_ROOT / "M60_TRUTH_FINAL_CASE_LEVEL.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(final_case_csv[0].keys()))
        w.writeheader()
        w.writerows(final_case_csv)

    rev_path = TRUTH_ROOT / "M60_TRUTH_FINAL_REVIEW.csv"
    with rev_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(final_review_csv[0].keys()))
        w.writeheader()
        w.writerows(final_review_csv)

    hashes = {
        "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json": write_sha256_sidecar(tpath),
        "M60_TRUTH_FINAL_CASE_LEVEL.csv": write_sha256_sidecar(csv_path),
        "M60_TRUTH_FINAL_REVIEW.csv": write_sha256_sidecar(rev_path),
        "M60_HUMAN_ADJUDICATION.csv": sha256_file(adj_path),
    }
    packet_hashes = {}
    for p in packets:
        for ext in (".json", ".md"):
            path = HUMAN_REVIEW_DIR / f"position_{p['position']:02d}_{p['case_id']}{ext}"
            packet_hashes[path.name] = sha256_file(path)
    hashes["HUMAN_REVIEW_INDEX.csv"] = sha256_file(HUMAN_REVIEW_DIR / "INDEX.csv")

    # Confirm original files still match expected hashes after writing new files.
    verify_original_lock()

    manifest = {
        "kind": "M60_TRUTH_FINAL_LOCK_MANIFEST",
        "immutable": True,
        "n_cases": 60,
        "created_utc": utc_now(),
        "phase": "3B_human_adjudication",
        "original_truth_lock_unaltered": True,
        "original_file_sha256": {
            "M60_EXTERNAL_TRUTH_LOCKED.json": EXPECTED_TRUTH,
            "M60_TRUTH_LOCK_MANIFEST.json": EXPECTED_LOCK,
        },
        "file_sha256": hashes,
        "human_review_packet_sha256": packet_hashes,
        "blinded_summary": summary,
        "prediction_payloads_opened": False,
        "amrfinder_used_as_truth": False,
        "pgap_used_as_truth": False,
        "gs_predictions_used_as_truth": False,
        "d20_touched": False,
        "accuracy_scored": False,
        "m60_cases_replaced": False,
        "scientific_code_changed": False,
        "prediction_reruns": False,
        "original_lock_overwritten": False,
        "ready_for_final_unblind": True,
    }
    mpath = TRUTH_ROOT / "M60_TRUTH_FINAL_LOCK_MANIFEST.json"
    write_json(mpath, manifest)
    lock_sha = write_sha256_sidecar(mpath)
    hashes["M60_TRUTH_FINAL_LOCK_MANIFEST.json"] = lock_sha
    # rewrite manifest with its own hash recorded after sidecar (sidecar already has content hash)
    truth_sha = hashes["M60_EXTERNAL_TRUTH_FINAL_LOCKED.json"]

    stop = {
        "TOTAL_CASES": 60,
        "FINAL_POSITIVE": summary["POSITIVE"],
        "FINAL_NEGATIVE": summary["NEGATIVE"],
        "FINAL_TRUTH_UNCERTAIN": summary["TRUTH_UNCERTAIN"],
        "TETA_POSITIVE": summary["tetA_POSITIVE"],
        "TETA_NEGATIVE": summary["tetA_NEGATIVE"],
        "TETA_UNCERTAIN": summary["tetA_TRUTH_UNCERTAIN"],
        "RPOB_POSITIVE": summary["rpoB_POSITIVE"],
        "RPOB_NEGATIVE": summary["rpoB_NEGATIVE"],
        "RPOB_UNCERTAIN": summary["rpoB_TRUTH_UNCERTAIN"],
        "HUMAN_REVIEW_CASES": 20,
        "CASES_RESOLVED_BY_HUMAN_REVIEW": summary["cases_resolved_by_human_review"],
        "CASES_REMAINING_UNCERTAIN": summary["cases_remaining_uncertain_after_human_review"],
        "PREDICTION_PAYLOADS_OPENED": "NO",
        "ACCURACY_SCORED": "NO",
        "D20_TOUCHED": "NO",
        "FINAL_TRUTH_SHA256": truth_sha,
        "FINAL_TRUTH_LOCK_MANIFEST_SHA256": lock_sha,
        "READY_FOR_FINAL_UNBLIND": "YES",
        "resolved_case_ids": [r["case_id"] for r in adj_rows if r["changed_yes_no"] == "yes"],
    }
    print(json.dumps(stop, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
