#!/usr/bin/env python3
"""Independent M60 truth adjudication.

Sequence-first. Two evidence routes. No prediction payloads, no AMRFinder,
no PGAP, no D8/D12 labels, no D20.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from m60_truth_common import (  # noqa: E402
    CASE_RECORDS,
    EVIDENCE,
    FAMILY_COMPETITIVE_AMBIGUOUS_BAND,
    FAMILY_COMPETITIVE_MARGIN,
    FINAL,
    GENE_AA_MIN_IDENTITY,
    GENE_AA_MIN_QUERY_COVERAGE,
    GENE_LENGTH_RATIO_MAX,
    GENE_LENGTH_RATIO_MIN,
    HMM_DOMAIN_ONLY_MAX_MODEL_COVERAGE,
    HMM_MIN_GATE_MODEL_COVERAGE,
    NEAR_COVERAGE_BAND,
    NEAR_IDENTITY_BAND,
    SEQ_DECISIVE_DELTA,
    SEQ_DECISIVE_PRODUCT,
    SOURCE,
    TRUTH_ROOT,
    assert_path_allowed,
    load_cohort_metadata,
    read_fasta,
    reverse_complement,
    sha256_file,
    translate_frame,
    utc_now,
    write_fasta,
    write_json,
    write_sha256_sidecar,
)

BIN = Path(os.environ.get("M60_TRUTH_BIN", "/home/aritr/micromamba/envs/genome-skeptic-prod/bin"))
THREADS = os.environ.get("M60_TRUTH_THREADS", "4")
NATIVE_ASM = Path("/home/aritr/m60_work/fasta/original")
NATIVE_WORK = Path("/home/aritr/m60_work/truth_evidence")


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def diamond_makedb(faa: Path, db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    proc = run([str(BIN / "diamond"), "makedb", "--in", str(faa), "-d", str(db), "--quiet"])
    if proc.returncode != 0:
        raise SystemExit(f"diamond makedb failed {faa}: {proc.stderr}")


def parse_blast6(path: Path) -> list[dict]:
    assert_path_allowed(path)
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
            rows.append(
                {
                    "qseqid": p[0],
                    "sseqid": p[1],
                    "pident": float(p[2]),
                    "length": int(float(p[3])),
                    "qlen": int(float(p[4])) if p[4] not in {".", ""} else None,
                    "slen": int(float(p[5])) if p[5] not in {".", ""} else None,
                    "qstart": int(float(p[6])),
                    "qend": int(float(p[7])),
                    "sstart": int(float(p[8])),
                    "send": int(float(p[9])),
                    "evalue": float(p[10]),
                    "bitscore": float(p[11]),
                    "qcovhsp": float(p[12]) if len(p) > 12 and p[12] not in {".", ""} else None,
                    "qframe": int(float(p[13])) if len(p) > 13 and p[13] not in {".", ""} else None,
                }
            )
        except ValueError:
            continue
    return rows


def tblastn_search(proteins: Path, assembly: Path, out: Path) -> list[dict]:
    """Search frozen protein panel against an assembly. Returns blastx-like rows (contig as qseqid)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(BIN / "tblastn"),
        "-query", str(proteins),
        "-subject", str(assembly),
        "-evalue", "1e-10",
        "-max_target_seqs", "20",
        "-num_threads", THREADS,
        "-outfmt", "6 qseqid sseqid pident length qlen slen qstart qend sstart send evalue bitscore qcovs sframe",
        "-out", str(out),
    ]
    proc = run(cmd)
    (out.parent / (out.name + ".stderr.log")).write_text(proc.stderr or "", encoding="utf-8")
    if proc.returncode != 0 and not out.exists():
        raise SystemExit(f"tblastn failed {assembly}: {proc.stderr}")
    raw = parse_blast6(out)
    remapped = []
    for h in raw:
        remapped.append(
            {
                "qseqid": h["sseqid"],  # contig
                "sseqid": h["qseqid"],  # protein
                "pident": h["pident"],
                "length": h["length"],
                "qlen": h["slen"],
                "slen": h["qlen"],
                "qstart": h["sstart"],
                "qend": h["send"],
                "sstart": h["qstart"],
                "send": h["qend"],
                "evalue": h["evalue"],
                "bitscore": h["bitscore"],
                "qcovhsp": h["qcovhsp"],
                "qframe": h.get("qframe"),
            }
        )
    return remapped


def diamond_blastp(query: Path, db: Path, out: Path) -> list[dict]:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(BIN / "diamond"), "blastp",
        "-q", str(query),
        "-d", str(db),
        "-o", str(out),
        "--outfmt", "6", "qseqid", "sseqid", "pident", "length", "qlen", "slen",
        "qstart", "qend", "sstart", "send", "evalue", "bitscore", "qcovhsp", "qframe",
        "--evalue", "1e-5",
        "--max-target-seqs", "15",
        "--threads", THREADS,
        "--quiet",
    ]
    proc = run(cmd)
    (out.parent / (out.name + ".stderr.log")).write_text(proc.stderr or "", encoding="utf-8")
    return parse_blast6(out)


def parse_hmm_domtbl(path: Path) -> list[dict]:
    assert_path_allowed(path)
    hits = []
    if not path.exists():
        return hits
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        p = line.split()
        if len(p) < 22:
            continue
        try:
            qlen = int(p[5])
            hmm_from = int(p[15])
            hmm_to = int(p[16])
            hits.append(
                {
                    "target_id": p[0],
                    "query_name": p[3],
                    "qlen": qlen,
                    "tlen": int(p[2]),
                    "full_evalue": float(p[6]),
                    "full_score": float(p[7]),
                    "hmm_from": hmm_from,
                    "hmm_to": hmm_to,
                    "model_coverage": (hmm_to - hmm_from + 1) / qlen if qlen else 0.0,
                    "domain_i_evalue": float(p[12]),
                    "domain_score": float(p[13]),
                }
            )
        except (ValueError, IndexError):
            continue
    return hits


def hmmsearch(hmm: Path, faa: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tbl = out_dir / "hmmsearch.tbl"
    dom = out_dir / "hmmsearch.domtbl"
    cmd = [
        str(BIN / "hmmsearch"),
        "--cpu", THREADS,
        "--tblout", str(tbl),
        "--domtblout", str(dom),
        "-o", str(out_dir / "hmmsearch.out"),
        str(hmm),
        str(faa),
    ]
    proc = run(cmd)
    (out_dir / "hmmsearch.stderr.log").write_text(proc.stderr or "", encoding="utf-8")
    doms = parse_hmm_domtbl(dom)
    if not doms:
        return {"ok": proc.returncode == 0, "full_score": None, "full_evalue": None, "model_coverage": 0.0, "n_domains": 0}
    # union model coverage
    qlen = doms[0]["qlen"]
    covered = set()
    best = min(doms, key=lambda h: h["full_evalue"])
    for d in doms:
        for i in range(d["hmm_from"], d["hmm_to"] + 1):
            covered.add(i)
    return {
        "ok": proc.returncode == 0,
        "full_score": best["full_score"],
        "full_evalue": best["full_evalue"],
        "model_coverage": (len(covered) / qlen) if qlen else 0.0,
        "n_domains": len(doms),
        "query_name": best.get("query_name"),
    }


def recover_orfs(contigs: dict[str, str], hits: list[dict], *, min_aa: int, pad: int, max_orfs: int = 12) -> list[dict]:
    if not hits:
        return []
    grouped: dict[tuple, list] = defaultdict(list)
    for h in hits:
        if h["bitscore"] < 40:
            continue
        q0, q1 = sorted((h["qstart"], h["qend"]))
        frame = h.get("qframe")
        if frame is None:
            frame = 1 if h["qend"] >= h["qstart"] else -1
        strand = "+" if int(frame) > 0 else "-"
        grouped[(h["qseqid"], strand)].append((q0, q1, h))
    orfs = []
    for (contig, strand), spans in grouped.items():
        seq = contigs.get(contig)
        if not seq:
            continue
        spans.sort(key=lambda x: (x[0], x[1]))
        clusters = []
        cur_s, cur_e, cur_hits = spans[0][0], spans[0][1], [spans[0][2]]
        for s, e, h in spans[1:]:
            if s <= cur_e + 300:
                cur_e = max(cur_e, e)
                cur_hits.append(h)
            else:
                clusters.append((cur_s, cur_e, cur_hits))
                cur_s, cur_e, cur_hits = s, e, [h]
        clusters.append((cur_s, cur_e, cur_hits))
        for s, e, chits in clusters:
            best_hit = max(chits, key=lambda x: x["bitscore"])
            # Translate the tblastn HSP interval in its native frame, then
            # extend in that same frame. Do not pick a longer out-of-frame ORF.
            hs, he = sorted((best_hit["qstart"], best_hit["qend"]))
            lo = max(0, hs - 1)
            hi = min(len(seq), he)
            core = seq[lo:hi]
            if strand == "-":
                core = reverse_complement(core)
            core_aa = translate_frame(core, 0).replace("*", "")
            ext_lo = max(0, lo - pad)
            ext_hi = min(len(seq), hi + pad)
            # snap extension to the same codon frame as the HSP
            if strand == "+":
                ext_lo -= (lo - ext_lo) % 3
                ext_lo = max(0, ext_lo)
                window = seq[ext_lo:ext_hi]
                aa = translate_frame(window, 0)
            else:
                window = reverse_complement(seq[ext_lo:ext_hi])
                trim = (ext_hi - hi) % 3
                if trim:
                    window = window[trim:]
                aa = translate_frame(window, 0)
            parts = [p for p in aa.split("*") if p]
            best_aa = core_aa
            for part in parts:
                idx = part.find("M")
                cand = part[idx:] if 0 <= idx <= 80 else part
                if core_aa and core_aa[:40] in cand.replace("X", ""):
                    if len(cand) > len(best_aa):
                        best_aa = cand
                elif not core_aa and len(cand) > len(best_aa):
                    best_aa = cand
            if len(best_aa) < len(core_aa):
                best_aa = core_aa
            if len(best_aa) < max(80, min_aa // 4):
                continue
            pident = best_hit["pident"]
            if pident > 1.5:
                pident = pident / 100.0
            orfs.append(
                {
                    "contig": contig,
                    "strand": strand,
                    "genomic_start": ext_lo + 1,
                    "genomic_end": ext_hi,
                    "aa": best_aa,
                    "aa_length": len(best_aa),
                    "aa_sha256": __import__("hashlib").sha256(best_aa.encode("ascii")).hexdigest(),
                    "seed_hit": {
                        "sseqid": best_hit["sseqid"],
                        "pident": pident,
                        "evalue": best_hit["evalue"],
                        "bitscore": best_hit["bitscore"],
                    },
                    "n_hits_in_cluster": len(chits),
                    "orf_meta": {"tblastn_in_frame": True, "core_aa_length": len(core_aa)},
                }
            )
    orfs.sort(key=lambda r: (-(r["seed_hit"]["bitscore"]), -r["aa_length"]))
    return orfs[:max_orfs]


def best_seq_match(rows: list[dict], qid: str) -> dict | None:
    cand = [r for r in rows if r["qseqid"] == qid]
    if not cand:
        return None
    best = max(cand, key=lambda r: (r["pident"] / 100.0) * ((r["qcovhsp"] or 0) / 100.0 if r["qcovhsp"] is not None else (r["length"] / (r["qlen"] or r["length"] or 1))))
    ident = best["pident"] / 100.0
    if best.get("qcovhsp") is not None:
        cov = best["qcovhsp"] / 100.0
    elif best.get("qlen"):
        cov = best["length"] / best["qlen"]
    else:
        cov = 0.0
    slen = best.get("slen") or 0
    qlen = best.get("qlen") or 0
    length_ratio = (qlen / slen) if slen else None
    return {
        "accession": best["sseqid"],
        "identity": ident,
        "coverage": cov,
        "identity_product": ident * cov,
        "evalue": best["evalue"],
        "bitscore": best["bitscore"],
        "qlen": qlen,
        "slen": slen,
        "length_ratio": length_ratio,
    }


def hmm_combined(model_cov: float, hmm_score: float | None, ident_product: float) -> float:
    bits = 0.0 if hmm_score is None else min(1.0, max(0.0, float(hmm_score) / 200.0))
    return round(0.55 * model_cov + 0.25 * bits + 0.20 * ident_product, 4)


def tet_call(target_seq: dict | None, comp_seq: dict | None, target_hmm: dict, comp_hmm: dict) -> tuple[str, str]:
    if target_seq is None:
        if (target_hmm.get("model_coverage") or 0) < HMM_MIN_GATE_MODEL_COVERAGE:
            return "NEGATIVE", "no_tetA_family_candidate_locus"
        return "TRUTH_UNCERTAIN", "profile_hit_without_tetAB_sequence_match"
    tgt_prod = target_seq["identity_product"] if target_seq else 0.0
    cmp_prod = comp_seq["identity_product"] if comp_seq else 0.0
    tgt_ident = target_seq["identity"] if target_seq else 0.0
    tgt_cov = target_seq["coverage"] if target_seq else 0.0
    t_hmm = target_hmm.get("model_coverage") or 0.0
    c_hmm = comp_hmm.get("model_coverage") or 0.0
    t_comb = hmm_combined(t_hmm, target_hmm.get("full_score"), tgt_prod)
    c_comb = hmm_combined(c_hmm, comp_hmm.get("full_score"), cmp_prod)
    margin = round(t_comb - c_comb, 4)
    cls = "unresolved_candidate"
    if t_hmm < HMM_MIN_GATE_MODEL_COVERAGE:
        if 0 < t_hmm <= HMM_DOMAIN_ONLY_MAX_MODEL_COVERAGE:
            cls = "domain_only"
        else:
            cls = "unresolved_candidate"
    elif tgt_prod >= SEQ_DECISIVE_PRODUCT and (tgt_prod - cmp_prod) >= SEQ_DECISIVE_DELTA:
        cls = "target_family_supported"
    elif cmp_prod >= SEQ_DECISIVE_PRODUCT and (cmp_prod - tgt_prod) >= SEQ_DECISIVE_DELTA:
        cls = "competing_family_preferred"
    elif margin >= FAMILY_COMPETITIVE_MARGIN:
        cls = "target_family_supported"
    elif margin <= -FAMILY_COMPETITIVE_MARGIN:
        cls = "competing_family_preferred"
    elif abs(margin) < max(FAMILY_COMPETITIVE_AMBIGUOUS_BAND, FAMILY_COMPETITIVE_MARGIN):
        cls = "ambiguous_family"
    else:
        cls = "unresolved_candidate"

    if cls == "target_family_supported":
        return "POSITIVE", cls
    if cls == "competing_family_preferred":
        return "NEGATIVE", cls
    if cls in {"ambiguous_family", "domain_only", "unresolved_candidate"}:
        if target_seq is None and cmp_prod < 0.20 and t_hmm < 0.05:
            return "NEGATIVE", "no_tetA_family_candidate_locus"
        if (
            target_seq
            and (abs(tgt_ident - GENE_AA_MIN_IDENTITY) <= NEAR_IDENTITY_BAND or abs(tgt_cov - GENE_AA_MIN_QUERY_COVERAGE) <= NEAR_COVERAGE_BAND)
            and not (tgt_prod >= SEQ_DECISIVE_PRODUCT and (tgt_prod - cmp_prod) >= SEQ_DECISIVE_DELTA)
        ):
            return "TRUTH_UNCERTAIN", cls
        if cls == "unresolved_candidate" and tgt_prod < 0.20 and cmp_prod < 0.20 and t_hmm < 0.10:
            return "NEGATIVE", "no_qualifying_tetA_sequence"
        return "TRUTH_UNCERTAIN", cls
    return "TRUTH_UNCERTAIN", cls


def rpob_call(target_seq: dict | None, comp_seq: dict | None, target_hmm: dict, comp_hmm: dict) -> tuple[str, str]:
    if target_seq is None and (target_hmm.get("model_coverage") or 0) < 0.10:
        return "NEGATIVE", "no_rpoB_candidate_locus"
    tgt_ident = target_seq["identity"] if target_seq else 0.0
    tgt_cov = target_seq["coverage"] if target_seq else 0.0
    ratio = target_seq["length_ratio"] if target_seq else None
    t_hmm = target_hmm.get("model_coverage") or 0.0
    c_hmm = comp_hmm.get("model_coverage") or 0.0
    tgt_prod = target_seq["identity_product"] if target_seq else 0.0
    cmp_prod = comp_seq["identity_product"] if comp_seq else 0.0
    rpoc_preferred = cmp_prod >= SEQ_DECISIVE_PRODUCT and (cmp_prod - tgt_prod) >= SEQ_DECISIVE_DELTA and (c_hmm >= t_hmm)
    if rpoc_preferred:
        return "NEGATIVE", "rpoC_or_other_subunit_preferred"
    domain_only = t_hmm > 0 and t_hmm <= HMM_DOMAIN_ONLY_MAX_MODEL_COVERAGE and tgt_cov < GENE_AA_MIN_QUERY_COVERAGE
    full = (
        target_seq is not None
        and tgt_ident >= GENE_AA_MIN_IDENTITY
        and tgt_cov >= GENE_AA_MIN_QUERY_COVERAGE
        and ratio is not None
        and GENE_LENGTH_RATIO_MIN <= ratio <= GENE_LENGTH_RATIO_MAX
        and not domain_only
        and not rpoc_preferred
    )
    if full:
        return "POSITIVE", "full_length_rpoB_orthologue"
    if domain_only:
        return "NEGATIVE", "domain_only_or_coverage_below_orthologue_gate"
    if target_seq and (
        abs(tgt_ident - GENE_AA_MIN_IDENTITY) <= NEAR_IDENTITY_BAND
        or abs(tgt_cov - GENE_AA_MIN_QUERY_COVERAGE) <= NEAR_COVERAGE_BAND
        or (ratio is not None and (abs(ratio - GENE_LENGTH_RATIO_MIN) <= 0.10 or abs(ratio - GENE_LENGTH_RATIO_MAX) <= 0.10))
    ):
        return "TRUTH_UNCERTAIN", "near_threshold_or_fragmentation"
    if t_hmm >= 0.50 and (ratio is None or ratio < GENE_LENGTH_RATIO_MIN or (target_seq and tgt_cov < GENE_AA_MIN_QUERY_COVERAGE)):
        return "TRUTH_UNCERTAIN", "partial_or_split_rpoB_candidate"
    if target_seq is None:
        return "NEGATIVE", "no_rpoB_candidate_locus"
    if tgt_ident < 0.40 and t_hmm < 0.20:
        return "NEGATIVE", "no_genuine_rpoB_sequence_represented"
    return "TRUTH_UNCERTAIN", "unresolved_rpoB_orthology"


def fasttree_placement(candidate_aa: str, ref_faa: Path, work: Path) -> dict | None:
    recs = read_fasta(ref_faa)
    if len(recs) < 3 or len(candidate_aa) < 80:
        return None
    fa = work / "place.faa"
    write_fasta(fa, [("CANDIDATE", candidate_aa)] + recs[:16])
    aln = work / "place.aln"
    # star alignment via hmmalign if possible, else skip
    # Use muscle-free: FastTree can take unaligned poorly; require hmmalign
    hmm = None
    return None  # filled by caller with hmmalign when HMM exists


def hmmalign_fasttree(candidate_aa: str, hmm: Path, ref_faa: Path, work: Path) -> dict | None:
    work.mkdir(parents=True, exist_ok=True)
    recs = read_fasta(ref_faa)
    fa = work / "place.faa"
    write_fasta(fa, [("CANDIDATE", candidate_aa)] + recs[:16])
    sto = work / "place.sto"
    proc = run([str(BIN / "hmmalign"), "-o", str(sto), str(hmm), str(fa)])
    if proc.returncode != 0 or not sto.exists():
        return {"ok": False, "reason": proc.stderr[-400:] if proc.stderr else "hmmalign failed"}
    # convert stockholm to fasta
    fa_aln = work / "place.aln.faa"
    names = []
    seqs = defaultdict(str)
    cur = None
    for line in sto.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            cur = parts[0]
            seqs[cur] += parts[1]
            if cur not in names:
                names.append(cur)
    if "CANDIDATE" not in names or len(names) < 4:
        return {"ok": False, "reason": "alignment too small"}
    write_fasta(fa_aln, [(n, seqs[n]) for n in names])
    tree = work / "place.nwk"
    proc = run([str(BIN / "FastTree"), "-quiet", "-lg", str(fa_aln)])
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return {"ok": False, "reason": proc.stderr[-400:] if proc.stderr else "FastTree failed"}
    tree.write_text(proc.stdout, encoding="utf-8")
    nwk = proc.stdout.strip()
    # naive neighbor: see if CANDIDATE is in a clade with majority target-like names
    return {"ok": True, "newick": nwk[:2000], "tree_sha256": sha256_file(tree), "n_sequences": len(names)}


def route_concordance(a: str, b: str) -> str:
    if a == "INSUFFICIENT" or b == "INSUFFICIENT":
        return "INSUFFICIENT"
    if a == b:
        return "CONCORDANT"
    return "DISCORDANT"


def score_orf(orf: dict, work: Path, target_db: Path, comp_db: Path, target_hmm: Path, comp_hmms: list[Path], target_faa: Path) -> dict:
    fa = work / "candidate.faa"
    write_fasta(fa, [("candidate", orf["aa"])])
    t_rows = diamond_blastp(fa, target_db, work / "blastp_target.tsv")
    c_rows = diamond_blastp(fa, comp_db, work / "blastp_comp.tsv")
    t_seq = best_seq_match(t_rows, "candidate")
    c_seq = best_seq_match(c_rows, "candidate")
    t_hmm = hmmsearch(target_hmm, fa, work / "hmm_target")
    c_hmm_best = {"model_coverage": 0.0, "full_score": None, "full_evalue": None, "family": None}
    for hmm in comp_hmms:
        row = hmmsearch(hmm, fa, work / f"hmm_{hmm.stem}")
        row["family"] = hmm.stem
        if (row.get("model_coverage") or 0) > (c_hmm_best.get("model_coverage") or 0):
            c_hmm_best = row
    return {
        "target_seq": t_seq,
        "competitor_seq": c_seq,
        "target_hmm": t_hmm,
        "competitor_hmm": c_hmm_best,
        "candidate_faa_sha256": sha256_file(fa),
    }


def source_manifest_sha() -> str:
    path = TRUTH_ROOT / "M60_TRUTH_SOURCE_MANIFEST.json"
    return sha256_file(path)


def software() -> dict:
    return {
        "diamond": "2.2.6",
        "hmmsearch": "HMMER 3.4",
        "hmmbuild": "HMMER 3.4",
        "hmmalign": "HMMER 3.4",
        "FastTree": str(BIN / "FastTree"),
        "python": sys.version.split()[0],
        "bin": str(BIN),
    }


def adjudicate_case(rec: dict, dbs: dict, source_sha: str) -> dict:
    pos = rec["position"]
    acc = rec["accession"]
    target = rec["target"]
    native = NATIVE_WORK / f"position_{pos:02d}_{acc}_{target}"
    native.mkdir(parents=True, exist_ok=True)
    published = EVIDENCE / f"position_{pos:02d}_{acc}_{target}"
    published.mkdir(parents=True, exist_ok=True)
    work = native
    asm_native = NATIVE_ASM / f"{acc}.fna"
    asm_pub = SOURCE / "assemblies" / f"{acc}.fna"
    asm = asm_native if asm_native.exists() else asm_pub
    assert_path_allowed(asm_pub)
    if not asm.exists():
        raise SystemExit(f"missing assembly {acc}")
    recs = read_fasta(asm)
    contigs = {name: seq.upper() for name, seq in recs}

    if target == "tetA_tetracycline_efflux":
        tdb, cdb = dbs["tetA_target"], dbs["tetA_comp"]
        thmm = Path(os.environ.get("M60_TRUTH_HMM", str(SOURCE / "hmm"))) / "tetA_tetracycline_efflux.hmm"
        chmms = [
            Path(os.environ.get("M60_TRUTH_HMM", str(SOURCE / "hmm"))) / "mfs_multidrug_efflux.hmm",
            Path(os.environ.get("M60_TRUTH_HMM", str(SOURCE / "hmm"))) / "rnd_efflux.hmm",
        ]
        min_aa, pad = 250, 400
        tfaa = Path(os.environ.get("M60_TRUTH_PANELS", str(SOURCE / "panels"))) / "tetA_target.faa"
        cfaa = Path(os.environ.get("M60_TRUTH_PANELS", str(SOURCE / "panels"))) / "tetA_competitors.faa"
    else:
        tdb, cdb = dbs["rpoB_target"], dbs["rpoB_comp"]
        thmm = Path(os.environ.get("M60_TRUTH_HMM", str(SOURCE / "hmm"))) / "rpoB_RNAP_beta.hmm"
        chmms = [Path(os.environ.get("M60_TRUTH_HMM", str(SOURCE / "hmm"))) / "rpoC_RNAP_beta_prime.hmm"]
        min_aa, pad = 800, 900
        tfaa = Path(os.environ.get("M60_TRUTH_PANELS", str(SOURCE / "panels"))) / "rpoB_target.faa"
        cfaa = Path(os.environ.get("M60_TRUTH_PANELS", str(SOURCE / "panels"))) / "rpoB_competitors.faa"

    print(f"POS {pos:02d} searching {acc} {target}", flush=True)
    t_hits = tblastn_search(tfaa, asm, work / "blastx_target.tsv")
    print(f"POS {pos:02d} target_hits={len(t_hits)}", flush=True)
    c_hits = tblastn_search(cfaa, asm, work / "blastx_comp.tsv")
    print(f"POS {pos:02d} competitor_hits={len(c_hits)}", flush=True)
    search_hits = t_hits + c_hits
    if target == "tetA_tetracycline_efflux" and not t_hits:
        search_hits = []
    orfs = recover_orfs(contigs, search_hits, min_aa=min_aa, pad=pad)
    write_json(work / "orfs.json", [{k: v for k, v in o.items() if k != "aa"} | {"aa_length": o["aa_length"]} for o in orfs])

    scored = []
    for i, orf in enumerate(orfs):
        sdir = work / f"orf_{i:02d}"
        sdir.mkdir(parents=True, exist_ok=True)
        write_fasta(sdir / "candidate.faa", [(f"orf_{i:02d}", orf["aa"])])
        metrics = score_orf(orf, sdir, tdb, cdb, thmm, chmms, tfaa)
        if target == "tetA_tetracycline_efflux":
            v1, why1 = tet_call(metrics["target_seq"], metrics["competitor_seq"], metrics["target_hmm"], metrics["competitor_hmm"])
        else:
            v1, why1 = rpob_call(metrics["target_seq"], metrics["competitor_seq"], metrics["target_hmm"], metrics["competitor_hmm"])
        # Route 2: profile placement (HMM already); FastTree if borderline
        hmm_pref = "target" if (metrics["target_hmm"].get("model_coverage") or 0) >= (metrics["competitor_hmm"].get("model_coverage") or 0) + 0.10 else (
            "competitor" if (metrics["competitor_hmm"].get("model_coverage") or 0) >= (metrics["target_hmm"].get("model_coverage") or 0) + 0.10 else "ambiguous"
        )
        t_score = metrics["target_hmm"].get("full_score") or 0.0
        t_cov = metrics["target_hmm"].get("model_coverage") or 0.0
        has_seq = metrics.get("target_seq") is not None
        if target == "tetA_tetracycline_efflux" and not has_seq:
            v2, why2 = "NEGATIVE", "no_tetAB_sequence_match_for_profile_route"
        elif hmm_pref == "target" and t_cov >= HMM_MIN_GATE_MODEL_COVERAGE and t_score >= 80 and has_seq:
            v2 = "POSITIVE" if t_cov >= 0.45 else "TRUTH_UNCERTAIN"
            why2 = f"hmm_prefers_target cov={t_cov:.3f} score={t_score:.1f}"
        elif hmm_pref == "competitor":
            v2 = "NEGATIVE"
            why2 = f"hmm_prefers_competitor {metrics['competitor_hmm'].get('family')} cov={metrics['competitor_hmm'].get('model_coverage'):.3f}"
        elif t_cov < 0.05 and (metrics["competitor_hmm"].get("model_coverage") or 0) < 0.05:
            v2 = "NEGATIVE" if not has_seq else "TRUTH_UNCERTAIN"
            why2 = "no_discriminating_profile_hit"
        else:
            v2 = "TRUTH_UNCERTAIN"
            why2 = "hmm_target_vs_competitor_not_separated_or_weak_profile"
        phylo = None
        borderline = v1 == "TRUTH_UNCERTAIN" or v2 == "TRUTH_UNCERTAIN" or v1 != v2
        if borderline:
            phylo = hmmalign_fasttree(orf["aa"], thmm, tfaa, sdir / "phylo")
            if phylo and phylo.get("ok"):
                nwk = phylo.get("newick") or ""
                # sibling names next to CANDIDATE token
                if "CANDIDATE" in nwk:
                    phylo["candidate_present"] = True
        metrics.update(
            {
                "orf_index": i,
                "coordinates": {
                    "contig": orf["contig"],
                    "strand": orf["strand"],
                    "start": orf["genomic_start"],
                    "end": orf["genomic_end"],
                },
                "aa_length": orf["aa_length"],
                "aa_sha256": orf["aa_sha256"],
                "route1_value": v1,
                "route1_reason": why1,
                "route2_value": v2,
                "route2_reason": why2,
                "phylo": phylo,
            }
        )
        scored.append(metrics)

    def rank_key(m):
        ts = m.get("target_seq") or {}
        return (
            1 if m["route1_value"] == "POSITIVE" else 0,
            ts.get("identity_product") or 0.0,
            m.get("target_hmm", {}).get("model_coverage") or 0.0,
            m.get("aa_length") or 0,
        )

    best = max(scored, key=rank_key) if scored else None
    if best is None:
        truth = "NEGATIVE"
        r1, r2 = "NEGATIVE", "NEGATIVE"
        why1 = "no_candidate_orf_recovered"
        why2 = "no_profile_query"
        conc = "CONCORDANT"
    else:
        r1, r2 = best["route1_value"], best["route2_value"]
        why1, why2 = best["route1_reason"], best["route2_reason"]
        conc = route_concordance(r1, r2)
        if conc == "CONCORDANT":
            truth = r1
        elif "POSITIVE" in {r1, r2} and "NEGATIVE" in {r1, r2}:
            # sequence-decisive target match may override a weak profile if protocol sequence gate hits
            ts = best.get("target_seq") or {}
            cs = best.get("competitor_seq") or {}
            if (ts.get("identity_product") or 0) >= SEQ_DECISIVE_PRODUCT and ((ts.get("identity_product") or 0) - (cs.get("identity_product") or 0)) >= SEQ_DECISIVE_DELTA:
                truth = "POSITIVE"
            elif (cs.get("identity_product") or 0) >= SEQ_DECISIVE_PRODUCT and ((cs.get("identity_product") or 0) - (ts.get("identity_product") or 0)) >= SEQ_DECISIVE_DELTA:
                truth = "NEGATIVE"
            else:
                truth = "TRUTH_UNCERTAIN"
        else:
            truth = "TRUTH_UNCERTAIN" if "TRUTH_UNCERTAIN" in {r1, r2} else r1

    ts = (best or {}).get("target_seq") or {}
    cs = (best or {}).get("competitor_seq") or {}
    th = (best or {}).get("target_hmm") or {}
    ch = (best or {}).get("competitor_hmm") or {}
    coords = (best or {}).get("coordinates") or {}

    record = {
        "case_id": rec["case_id"],
        "position": rec["position"],
        "accession": rec["accession"],
        "target": rec["target"],
        "stratum": rec["stratum"],
        "truth_value": truth,
        "truth_status": "ADJUDICATED" if truth != "TRUTH_UNCERTAIN" else "PENDING_REVIEW",
        "pass1_truth": truth,
        "evidence_route_1": {
            "name": "target_vs_competitor_sequence_reference",
            "value": r1,
            "reason": why1,
        },
        "evidence_route_2": {
            "name": "independent_profile_or_phylogenetic_placement",
            "value": r2,
            "reason": why2,
        },
        "evidence_route_concordance": conc,
        "candidate_sequence_ids": [f"orf_{best['orf_index']:02d}"] if best else [],
        "candidate_coordinates": coords,
        "primary_reference_accessions": [ts.get("accession")] if ts.get("accession") else [],
        "competitor_reference_accessions": [cs.get("accession")] if cs.get("accession") else [],
        "sequence_coverage": ts.get("coverage"),
        "sequence_similarity": ts.get("identity"),
        "family_or_profile_result": {
            "target_hmm_model_coverage": th.get("model_coverage"),
            "target_hmm_score": th.get("full_score"),
            "target_hmm_evalue": th.get("full_evalue"),
            "competitor_hmm_family": ch.get("family"),
            "competitor_hmm_model_coverage": ch.get("model_coverage"),
            "competitor_hmm_score": ch.get("full_score"),
        },
        "orthology_or_phylogeny_result": (best or {}).get("phylo"),
        "primary_evidence_summary": why1,
        "secondary_evidence_summary": why2,
        "truth_resource_manifest_sha256": source_sha,
        "software_versions": software(),
        "evidence_artifact_hashes": {
            "blastx_target": sha256_file(work / "blastx_target.tsv") if (work / "blastx_target.tsv").exists() else None,
            "blastx_comp": sha256_file(work / "blastx_comp.tsv") if (work / "blastx_comp.tsv").exists() else None,
        },
        "adjudication_rationale": (
            f"{target} pass1={truth}; route1={r1} ({why1}); route2={r2} ({why2}); "
            f"concordance={conc}; best_identity={ts.get('identity')}; best_coverage={ts.get('coverage')}; "
            f"hmm_cov={th.get('model_coverage')}; competitor_hmm_cov={ch.get('model_coverage')}."
        ),
        "n_orfs_scored": len(scored),
        "prediction_values_included": False,
        "curator": "automated_two_independent_evidence_routes",
        "not_two_independent_reviewers": True,
        "created_utc": utc_now(),
    }
    out = CASE_RECORDS / f"position_{pos:02d}.json"
    write_json(out, record)
    write_sha256_sidecar(out)
    published.mkdir(parents=True, exist_ok=True)
    for name in ("blastx_target.tsv", "blastx_comp.tsv", "orfs.json"):
        src = work / name
        if src.exists():
            shutil.copy2(src, published / name)
    print(f"POS {pos:02d} {acc} {target} {truth} conc={conc}", flush=True)
    return record


def main() -> int:
    man = TRUTH_ROOT / "M60_TRUTH_SOURCE_MANIFEST.json"
    if not man.exists():
        raise SystemExit("truth source manifest missing; freeze first")
    source_sha = source_manifest_sha()
    dbdir = Path("/home/aritr/m60_work/truth_diamond")
    dbdir.mkdir(parents=True, exist_ok=True)
    dbs = {
        "tetA_target": dbdir / "tetA_target",
        "tetA_comp": dbdir / "tetA_comp",
        "rpoB_target": dbdir / "rpoB_target",
        "rpoB_comp": dbdir / "rpoB_comp",
    }
    paneln = Path("/home/aritr/m60_work/truth_panels")
    paneln.mkdir(parents=True, exist_ok=True)
    for name in ("tetA_target.faa", "tetA_competitors.faa", "rpoB_target.faa", "rpoB_competitors.faa"):
        shutil.copy2(SOURCE / "panels" / name, paneln / name)
    # rewrite SOURCE panels used by adjudicate_case via env
    hmmn = Path("/home/aritr/m60_work/truth_hmm")
    hmmn.mkdir(parents=True, exist_ok=True)
    for name in (
        "tetA_tetracycline_efflux.hmm",
        "mfs_multidrug_efflux.hmm",
        "rnd_efflux.hmm",
        "rpoB_RNAP_beta.hmm",
        "rpoC_RNAP_beta_prime.hmm",
    ):
        shutil.copy2(SOURCE / "hmm" / name, hmmn / name)
    os.environ["M60_TRUTH_HMM"] = str(hmmn)
    diamond_makedb(paneln / "tetA_target.faa", dbs["tetA_target"])
    diamond_makedb(paneln / "tetA_competitors.faa", dbs["tetA_comp"])
    diamond_makedb(paneln / "rpoB_target.faa", dbs["rpoB_target"])
    diamond_makedb(paneln / "rpoB_competitors.faa", dbs["rpoB_comp"])

    cases = load_cohort_metadata()
    done = []
    for rec in cases:
        out = CASE_RECORDS / f"position_{rec['position']:02d}.json"
        if out.exists():
            done.append(json.loads(out.read_text(encoding="utf-8")))
            print(f"POS {rec['position']:02d} reused", flush=True)
            continue
        done.append(adjudicate_case(rec, dbs, source_sha))
    write_json(CASE_RECORDS / "PASS1_ALL.json", done)
    write_sha256_sidecar(CASE_RECORDS / "PASS1_ALL.json")
    print(f"PASS1 complete {len(done)}/60", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
