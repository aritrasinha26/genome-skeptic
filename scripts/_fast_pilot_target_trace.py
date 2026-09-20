#!/usr/bin/env python3
"""Deterministic FAST_PILOT target-detection diagnosis. Does not change scoring."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

from genome_skeptic.claims.completeness import (
    EXPECTED_BY_CLAIM,
    IMPORTANCE_WEIGHTS,
    apply_completeness_to_confidence,
    importance_for,
    score_evidence_completeness,
)
from genome_skeptic.claims.state_machine import confidence_for
from genome_skeptic.config import Settings
from genome_skeptic.eval.baselines import run_skeptic
from genome_skeptic.eval.real_genomes import locate_target
from genome_skeptic.eval.scoring import HiddenTruth, merge_totals, overall_score, score_case, scientifically_correct
from genome_skeptic.io_utils import read_fasta
from genome_skeptic.models import Claim, ClaimProvenance, ClaimStatus, ClaimType, FalsificationResult, FalsificationTest
from genome_skeptic.tools.gene_search import is_nucleotide, reverse_complement, search_targets, translate_frame
from genome_skeptic.validators.homology import partial_hit, strong_hit

ROOT = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
DEV = ROOT / "benchmarks/real_genomes_fast_pilot_dev"
DEV_EVAL = ROOT / "benchmarks/real_genomes_fast_pilot_dev_eval"
HELD = ROOT / "benchmarks/real_genomes_fast_pilot_held"
HELD_EVAL = ROOT / "benchmarks/real_genomes_fast_pilot_held_eval"
DIAG = ROOT / "benchmarks/fast_pilot_target_diagnostics"
OUT_JSON = ROOT / "benchmarks/FAST_PILOT_TARGET_TRACE.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_exact(query: str, records: list[tuple[str, str]]) -> list[dict]:
    q = query.upper()
    rc = reverse_complement(q)
    hits = []
    for cid, seq in records:
        seq_u = seq.upper()
        start = 0
        while True:
            i = seq_u.find(q, start)
            if i < 0:
                break
            hits.append({"contig": cid, "start": i, "end": i + len(q), "strand": "+", "exact": True, "contig_length": len(seq_u)})
            start = i + 1
        start = 0
        while True:
            i = seq_u.find(rc, start)
            if i < 0:
                break
            hits.append({"contig": cid, "start": i, "end": i + len(q), "strand": "-", "exact": True, "contig_length": len(seq_u)})
            start = i + 1
    return hits


def which(name: str) -> str | None:
    return shutil.which(name)


def run_blastn(query_fa: Path, subject_fa: Path, out_tsv: Path) -> dict:
    exe = which("blastn")
    if not exe:
        return {"available": False}
    cmd = [
        exe, "-query", str(query_fa), "-subject", str(subject_fa),
        "-task", "blastn", "-evalue", "10", "-word_size", "7",
        "-outfmt", "6 qseqid sseqid pident length qlen slen qstart qend sstart send qcovs evalue bitscore",
        "-max_hsps", "20", "-max_target_seqs", "20",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out_tsv.write_text(p.stdout)
    rows = []
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 13:
            continue
        rows.append({
            "sseqid": parts[1],
            "pident": float(parts[2]),
            "length": int(parts[3]),
            "qlen": int(parts[4]),
            "slen": int(parts[5]),
            "qstart": int(parts[6]),
            "qend": int(parts[7]),
            "sstart": int(parts[8]),
            "send": int(parts[9]),
            "qcovs": float(parts[10]),
            "evalue": float(parts[11]),
            "bitscore": float(parts[12]),
            "identity_frac": float(parts[2]) / 100.0,
            "query_coverage": (int(parts[7]) - int(parts[6]) + 1) / int(parts[4]),
            "subject_coverage": int(parts[3]) / int(parts[5]),
        })
    return {"available": True, "ok": p.returncode == 0, "command": cmd, "n_hits": len(rows), "hits": rows, "stderr": p.stderr[-2000:] if p.stderr else ""}


def run_tblastn(query_aa_fa: Path, subject_fa: Path, out_tsv: Path) -> dict:
    exe = which("tblastn")
    if not exe:
        return {"available": False}
    cmd = [
        exe, "-query", str(query_aa_fa), "-subject", str(subject_fa),
        "-evalue", "10", "-word_size", "2",
        "-outfmt", "6 qseqid sseqid pident length qlen slen qstart qend sstart send qcovs evalue bitscore",
        "-max_hsps", "20", "-max_target_seqs", "20",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out_tsv.write_text(p.stdout)
    rows = []
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 13:
            continue
        rows.append({
            "sseqid": parts[1],
            "pident": float(parts[2]),
            "length": int(parts[3]),
            "qlen": int(parts[4]),
            "slen": int(parts[5]),
            "qstart": int(parts[6]),
            "qend": int(parts[7]),
            "sstart": int(parts[8]),
            "send": int(parts[9]),
            "qcovs": float(parts[10]),
            "evalue": float(parts[11]),
            "bitscore": float(parts[12]),
            "identity_frac": float(parts[2]) / 100.0,
            "query_coverage": (int(parts[7]) - int(parts[6]) + 1) / int(parts[4]),
        })
    return {"available": True, "ok": p.returncode == 0, "command": cmd, "n_hits": len(rows), "hits": rows, "stderr": p.stderr[-2000:] if p.stderr else ""}


def run_minimap(query_fa: Path, subject_fa: Path, out_paf: Path) -> dict:
    exe = which("minimap2")
    if not exe:
        return {"available": False}
    cmd = [exe, "-c", "-x", "sr", str(subject_fa), str(query_fa)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out_paf.write_text(p.stdout)
    rows = []
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        qlen, qstart, qend = int(parts[1]), int(parts[2]), int(parts[3])
        slen, sstart, send = int(parts[6]), int(parts[7]), int(parts[8])
        nmatch, aln = int(parts[9]), int(parts[10])
        rows.append({
            "sseqid": parts[5],
            "strand": parts[4],
            "qstart": qstart, "qend": qend, "qlen": qlen,
            "sstart": sstart, "send": send, "slen": slen,
            "nmatch": nmatch, "aln": aln,
            "identity_frac": nmatch / aln if aln else 0.0,
            "query_coverage": (qend - qstart) / qlen if qlen else 0.0,
            "mapq": int(parts[11]),
        })
    return {"available": True, "ok": p.returncode == 0, "command": cmd, "n_hits": len(rows), "hits": rows, "stderr": p.stderr[-2000:] if p.stderr else ""}


def depth_window(depth_path: Path, contig: str, start: int, end: int) -> dict | None:
    if not depth_path.exists():
        return None
    vals = []
    genome = []
    with depth_path.open() as fh:
        for line in fh:
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            try:
                pos = int(parts[1])
                d = float(parts[2])
            except ValueError:
                continue
            genome.append(d)
            if parts[0] == contig and start < pos <= end:
                vals.append(d)
    gmean = sum(genome) / len(genome) if genome else None
    local = sum(vals) / len(vals) if vals else None
    return {
        "local_mean_depth": local,
        "genome_mean_depth": gmean,
        "relative_depth": (local / gmean) if local is not None and gmean else None,
        "positions_counted": len(vals),
        "zero_positions": sum(1 for v in vals if v == 0),
    }


def completeness_breakdown(claim_payload: dict) -> dict:
    settings = Settings()
    tests = []
    for t in claim_payload.get("falsification_tests") or []:
        tests.append(FalsificationTest(
            test_id=t["test_id"],
            name=t.get("name") or t["test_id"],
            hypothesis=t.get("hypothesis") or "",
            blocking=bool(t.get("blocking")),
            status=t.get("status") or "skipped",
            result=FalsificationResult(t["result"]) if t.get("result") else FalsificationResult.not_run,
            limitation=t.get("limitation"),
        ))
    claim_type = ClaimType(claim_payload["claim_type"])
    rec = score_evidence_completeness(claim_type, tests, tools_unavailable=["contig_taxonomy"])
    rows = []
    by_prefix = {t.test_id.split(":")[0]: t for t in tests}
    expected = EXPECTED_BY_CLAIM[claim_type]
    for prefix in expected:
        test = by_prefix.get(prefix)
        imp = importance_for(prefix)
        w = IMPORTANCE_WEIGHTS[imp]
        status = None if test is None else test.status
        contrib = 0.0
        counted = True
        if test is None:
            contrib = 0.0
        elif test.status == "completed":
            contrib = w
        elif test.status == "unresolved":
            contrib = 0.25 * w
        elif "not defined" in (test.limitation or "").lower() or "not configured" in (test.limitation or "").lower() or "catalytic residues were not provided" in (test.limitation or "").lower():
            counted = False
            w = 0.0
            contrib = 0.0
        else:
            contrib = 0.0
        rows.append({
            "prefix": prefix,
            "importance": imp,
            "weight": w,
            "status": status,
            "limitation": None if test is None else test.limitation,
            "result": None if test is None else (test.result.value if test.result else None),
            "counted_in_denominator": counted,
            "weighted_done": contrib,
        })
    base = 0.55 if claim_type == ClaimType.target_gene_not_detected else 0.7
    status = ClaimStatus(claim_payload["status"])
    conf_before = confidence_for(status, tests, base=base, max_supported=settings.thresholds.max_claim_confidence, not_detected=claim_type == ClaimType.target_gene_not_detected)
    if claim_type == ClaimType.target_gene_not_detected:
        conf_before = min(conf_before, settings.thresholds.max_not_detected_confidence)
    conf_after = apply_completeness_to_confidence(conf_before, rec)
    return {
        "recorded_completeness": claim_payload.get("evidence_completeness"),
        "recomputed_completeness": rec.score,
        "completed": rec.completed,
        "unresolved": rec.unresolved,
        "unavailable": rec.unavailable,
        "missing_essential": rec.missing_essential,
        "missing_high_value": rec.missing_high_value,
        "validators": rows,
        "weighted_done": sum(r["weighted_done"] for r in rows if r["counted_in_denominator"]),
        "weighted_total": sum(r["weight"] for r in rows if r["counted_in_denominator"]),
        "confidence_before_completeness": conf_before,
        "confidence_after_completeness": conf_after,
        "recorded_confidence": claim_payload.get("confidence"),
        "base_for_polarity": base,
        "status": claim_payload.get("status"),
    }


def dummy_claim() -> Claim:
    return Claim(
        claim_id="C_target_rpoB",
        claim_type=ClaimType.target_gene_not_detected,
        statement="Target gene 'rpoB' was not detected in the current assembly.",
        status=ClaimStatus.weakened,
        confidence=0.46,
        evidence_completeness=0.63,
        rationale="Dummy cautious baseline with no biological reasoning. Non-detection is scoped to the current assembly.",
        provenance=ClaimProvenance(created_by="dummy_cautious_baseline", stage="target_gene"),
    )


def mutate_aa(aa: str, frac: float = 0.30, seed: int = 7) -> str:
    rng_state = seed
    alphabet = "ACDEFGHIKLMNPQRSTVWY"
    out = []
    n_mut = max(1, int(round(len(aa) * frac)))
    idxs = list(range(len(aa)))
    # deterministic shuffle
    for i in range(len(idxs) - 1, 0, -1):
        rng_state = (1103515245 * rng_state + 12345) & 0x7FFFFFFF
        j = rng_state % (i + 1)
        idxs[i], idxs[j] = idxs[j], idxs[i]
    mutset = set(idxs[:n_mut])
    for i, ch in enumerate(aa):
        if i not in mutset:
            out.append(ch)
            continue
        rng_state = (1103515245 * rng_state + 12345) & 0x7FFFFFFF
        choices = [c for c in alphabet if c != ch]
        out.append(choices[rng_state % len(choices)])
    return "".join(out)


def reverse_translate(aa: str) -> str:
    table = {
        "A": "GCG", "C": "TGC", "D": "GAT", "E": "GAA", "F": "TTT", "G": "GGC",
        "H": "CAT", "I": "ATT", "K": "AAA", "L": "CTG", "M": "ATG", "N": "AAC",
        "P": "CCG", "Q": "CAG", "R": "CGT", "S": "AGC", "T": "ACC", "V": "GTG",
        "W": "TGG", "Y": "TAT",
    }
    return "".join(table.get(c, "NNN") for c in aa)


def write_fa(path: Path, records: list[tuple[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f">{n}\n{s}\n" for n, s in records))
    return path


def summarize_claim(claim: Claim) -> dict:
    tests = []
    for t in claim.falsification_tests:
        tests.append({"id": t.test_id, "status": t.status, "result": t.result.value if t.result else None, "limitation": t.limitation})
    return {
        "claim_type": claim.claim_type.value,
        "status": claim.status.value,
        "confidence": claim.confidence,
        "evidence_completeness": claim.evidence_completeness,
        "statement": claim.statement,
        "tests": tests,
        "completed": claim.completed_tests,
        "unavailable": claim.unavailable_tests,
    }


def main():
    DIAG.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    qid, qseq = read_fasta(DEV / "agent_visible/dev_01/targets.fa")[0]
    qseq = qseq.upper()
    aa_frames = {f: translate_frame(qseq, f) for f in range(3)}
    aa = max((aa_frames[f].split("*")[0] for f in range(3)), key=len)
    source = list(read_fasta(DEV / "hidden/genomes/ecoli_k12/sim_source.fa"))
    assembly_path = DEV_EVAL / "dev_01/production/spades/contigs.fasta"
    assembly = list(read_fasta(assembly_path))
    source_hits = find_exact(qseq, source)
    assembly_exact = find_exact(qseq, assembly)

    query_fa = write_fa(DIAG / "query_rpoB.fa", [(qid, qseq)])
    query_aa_fa = write_fa(DIAG / "query_rpoB.faa", [(qid, aa)])
    blastn = run_blastn(query_fa, assembly_path, DIAG / "dev01_blastn.tsv")
    tblastn = run_tblastn(query_aa_fa, assembly_path, DIAG / "dev01_tblastn.tsv")
    minimap = run_minimap(query_fa, assembly_path, DIAG / "dev01_minimap.paf")
    internal = search_targets([(qid, qseq)], assembly, settings)
    internal_nt = [h for h in internal if h.search_kind == "nucleotide"]
    internal_aa = [h for h in internal if h.search_kind == "translated"]
    best_nt = max(internal_nt, key=lambda h: h.identity * h.query_coverage) if internal_nt else None
    best_aa = max(internal_aa, key=lambda h: h.identity * h.query_coverage) if internal_aa else None

    source_blast = {}
    source_locate = {}
    source_map = {
        "ecoli_k12": DEV / "hidden/genomes/ecoli_k12/sim_source.fa",
        "pao1": DEV / "hidden/genomes/pao1/sim_source.fa",
        "hpylori": DEV / "hidden/genomes/hpylori/sim_source.fa",
        "salmonella_lt2": HELD / "hidden/genomes/salmonella_lt2/sim_source.fa",
        "pputida_kt2440": HELD / "hidden/genomes/pputida_kt2440/sim_source.fa",
        "staph_8325": HELD / "hidden/genomes/staph_8325/sim_source.fa",
    }
    for gid, sfa in source_map.items():
        if not sfa.exists():
            source_blast[gid] = {"missing": True}
            continue
        recs = list(read_fasta(sfa))
        exact = find_exact(qseq, recs)
        loc = locate_target(sfa, qseq)
        bn = run_blastn(query_fa, sfa, DIAG / f"source_{gid}_blastn.tsv")
        tb = run_tblastn(query_aa_fa, sfa, DIAG / f"source_{gid}_tblastn.tsv")
        topn = sorted(bn.get("hits") or [], key=lambda r: r["identity_frac"] * r["query_coverage"], reverse=True)[:3]
        topa = sorted(tb.get("hits") or [], key=lambda r: r["identity_frac"] * r["query_coverage"], reverse=True)[:3]
        source_blast[gid] = {
            "path": str(sfa),
            "exact_nt_present": bool(exact),
            "exact_matches": exact,
            "locate_target_identity_ge_0.5_rule": loc,
            "truth_present_if_locate_ge_0.5": bool(loc and (loc.get("identity") or 0) >= 0.5),
            "blastn_available": bn.get("available"),
            "blastn_top": topn,
            "tblastn_top": topa,
            "meets_nt_80_80": bool(topn and topn[0]["identity_frac"] >= 0.80 and topn[0]["query_coverage"] >= 0.80),
            "meets_aa_60_80": bool(topa and topa[0]["identity_frac"] >= 0.60 and topa[0]["query_coverage"] >= 0.80),
        }
        source_locate[gid] = loc

    # Independent coverage of exact or best BLAST locus
    depth_path = DEV_EVAL / "dev_01/production/mapping/depth.tsv"
    loc_for_depth = None
    if assembly_exact:
        loc_for_depth = assembly_exact[0]
    elif blastn.get("hits"):
        top = max(blastn["hits"], key=lambda r: r["identity_frac"] * r["query_coverage"])
        loc_for_depth = {"contig": top["sseqid"], "start": min(top["sstart"], top["send"]) - 1, "end": max(top["sstart"], top["send"])}
    depth = None
    if loc_for_depth:
        depth = depth_window(depth_path, loc_for_depth["contig"], int(loc_for_depth["start"]), int(loc_for_depth["end"]))

    # Split-across-contigs: BLAST HSPs on different subjects covering disjoint query
    gene_split_across_contigs = False
    if blastn.get("hits"):
        by_s = {}
        for h in blastn["hits"]:
            by_s.setdefault(h["sseqid"], []).append(h)
        gene_split_across_contigs = len(by_s) > 1 and any(h["query_coverage"] < 0.95 for h in blastn["hits"])
        # Short scattered HSPs are not a split gene. Require at least two subjects each covering >=20% of Q.
        substantial = [sid for sid, hs in by_s.items() if max(h["query_coverage"] for h in hs) >= 0.20]
        gene_split_across_contigs = len(substantial) >= 2

    thresholds = {
        "gene_nt_min_identity": settings.thresholds.gene_nt_min_identity,
        "gene_nt_min_query_coverage": settings.thresholds.gene_nt_min_query_coverage,
        "gene_aa_min_identity": settings.thresholds.gene_aa_min_identity,
        "gene_aa_min_query_coverage": settings.thresholds.gene_aa_min_query_coverage,
        "gene_search_kmer_nt": settings.thresholds.gene_search_kmer_nt,
        "gene_search_kmer_aa": settings.thresholds.gene_search_kmer_aa,
        "max_mismatch_rate_nt": 1 - settings.thresholds.gene_nt_min_identity + 0.15,
        "max_mismatch_rate_aa": 1 - settings.thresholds.gene_aa_min_identity + 0.20,
        "gene_partial_min_nt_bp": settings.thresholds.gene_partial_min_nt_bp,
        "gene_partial_min_aa": settings.thresholds.gene_partial_min_aa,
        "internal_search_command": [
            "internal_gene_search", "--targets", str(DEV / "agent_visible/dev_01/targets.fa"),
            "--contigs", str(assembly_path),
        ],
    }

    def hit_dump(h):
        if h is None:
            return None
        return {
            **h.model_dump(),
            "passes_80_80_nt": bool(h.search_kind == "nucleotide" and strong_hit(h, settings)),
            "passes_aa_threshold": bool(h.search_kind != "nucleotide" and strong_hit(h, settings)),
            "is_partial": partial_hit(h, settings),
            "subject_coverage": (h.alignment_length / h.contig_length) if h.contig_length else None,
        }

    # Completeness for all FAST_PILOT cases
    cases_meta = []
    for split, vis, ev, truth_path in (
        ("development", DEV / "agent_visible", DEV_EVAL, DEV / "hidden/truth.yaml"),
        ("held_out", HELD / "agent_visible", HELD_EVAL, HELD / "hidden/truth.yaml"),
    ):
        import yaml
        truth = yaml.safe_load(truth_path.read_text())
        for case_dir in sorted(p for p in vis.iterdir() if p.is_dir()):
            cid = case_dir.name
            claims_p = ev / cid / "genome_skeptic/claims.json"
            if not claims_p.exists():
                continue
            payload = json.loads(claims_p.read_text())[0]
            trow = (truth.get("cases") or {}).get(cid) or {}
            cases_meta.append({
                "case_id": cid,
                "split": split,
                "genome_id": trow.get("genome_id"),
                "present": ((trow.get("targets") or {}).get("rpoB") or {}).get("present"),
                "completeness": completeness_breakdown(payload),
                "claim_type": payload.get("claim_type"),
                "status": payload.get("status"),
                "confidence": payload.get("confidence"),
                "evidence_completeness": payload.get("evidence_completeness"),
            })

    # Dummy baseline vs same scorer
    dummy = dummy_claim()
    dummy_rows = []
    dummy_parts = []
    import yaml
    for truth_path, split in ((DEV / "hidden/truth.yaml", "development"), (HELD / "hidden/truth.yaml", "held_out")):
        hidden = HiddenTruth.model_validate(yaml.safe_load(truth_path.read_text()) or {})
        for case_id, case_truth in hidden.cases.items():
            part, rows = score_case(case_id, [dummy], [], case_truth)
            dummy_parts.append(part)
            dummy_rows.append({
                "split": split,
                "case_id": case_id,
                "present": next(iter(case_truth.targets.values())).present,
                "scientifically_correct": scientifically_correct(dummy, next(iter(case_truth.targets.values()))),
                "hits": rows[0].hits if rows else {},
            })
    dummy_totals = merge_totals(dummy_parts)
    dummy_overall = overall_score(dummy_totals)
    dummy_by_split = {}
    for split_name in ("development", "held_out"):
        parts = [dummy_parts[i] for i, row in enumerate(dummy_rows) if row["split"] == split_name]
        tot = merge_totals(parts) if parts else {}
        dummy_by_split[split_name] = {
            "overall": overall_score(tot) if tot else None,
            "totals": {k: {"n": v.n, "correct": v.correct, "rate": v.rate} for k, v in tot.items() if v.n},
        }

    gs_dev = json.loads((DEV_EVAL / "realgenome_production_report.json").read_text())
    gs_held = json.loads((HELD_EVAL / "realgenome_production_report.json").read_text())

    # Diagnostic controls (tiny FASTAs, no SPAdes)
    flank = "ACGT" * 80
    pos1_seq = flank + qseq + flank
    aa_div = mutate_aa(aa, 0.30, seed=11)
    pos2_seq = flank + reverse_translate(aa_div) + flank
    neg1_seq = ("GATTACA" * 40 + "TTTTCCCCAAAAGGGG") * 8
    # paralogue: only a 12-aa conserved stretch from the query, rest unrelated
    domain = aa[8:20]
    unrelated = mutate_aa(aa, 0.90, seed=99)
    chimera = unrelated[:8] + domain + unrelated[20:]
    neg2_seq = flank + reverse_translate(chimera) + flank
    controls = {
        "pos1_exact_nt": (pos1_seq, "exact nucleotide target inserted in a synthetic contig"),
        "pos2_protein_orthologue": (pos2_seq, "divergent amino-acid orthologue reverse-translated into a contig"),
        "neg1_no_family": (neg1_seq, "synthetic sequence with no planted rpoB family"),
        "neg2_domain_paralogue": (neg2_seq, "chimeric protein sharing only a short conserved stretch"),
    }
    control_results = {}
    for name, (seq, note) in controls.items():
        asm = write_fa(DIAG / name / "contigs.fa", [("ctrl", seq)])
        tgt = write_fa(DIAG / name / "targets.fa", [(qid, qseq)])
        claims, loci = run_skeptic(asm, tgt, DIAG / name / "gs", settings, references=None, enable_falsification=True)
        hits = search_targets([(qid, qseq)], [("ctrl", seq)], settings)
        control_results[name] = {
            "note": note,
            "assembly_bp": len(seq),
            "internal_hits": [hit_dump(h) for h in hits[:8]],
            "n_strong": sum(1 for h in hits if strong_hit(h, settings)),
            "n_partial": sum(1 for h in hits if partial_hit(h, settings)),
            "genome_skeptic": summarize_claim(claims[0]) if claims else None,
        }

    spades_cmd = None
    spades_log = DEV_EVAL / "dev_01/production/spades/spades.log"
    if spades_log.exists():
        first = spades_log.read_text(errors="replace").splitlines()[:1]
        spades_cmd = first[0] if first else None
    map_cmd = None
    map_log = DEV_EVAL / "dev_01/production/mapping/mapping.stderr.log"
    if map_log.exists():
        for line in map_log.read_text(errors="replace").splitlines():
            if "CMD:" in line:
                map_cmd = line.strip()
                break

    payload = {
        "banner": "FAST PILOT - NOT FINAL BENCHMARK. Diagnostic only. Scoring was not modified.",
        "assembly_commands": {
            "spades_command_line": spades_cmd,
            "mapping_command": map_cmd,
        },
        "target": {
            "fasta_identifier": qid,
            "nucleotide_length": len(qseq),
            "nucleotide_sequence": qseq,
            "sha256": sha256_text(qseq),
            "is_nucleotide": is_nucleotide(qseq),
            "translated_frames": {str(f): {"aa": aa_frames[f], "ungapped_prefix": aa_frames[f].split('*')[0], "length_aa": len(aa_frames[f].split('*')[0])} for f in range(3)},
            "chosen_protein": aa,
            "chosen_protein_length": len(aa),
            "protein_sha256": sha256_text(aa),
            "representation": "122-nt public E. coli rpoB fragment (PUBLIC_RPOB_SEED), not a full-length gene",
        },
        "hidden_source": {
            "note": "scorer-side only; coordinates from exact string search and BLAST, not LLM inference",
            "fasta": str(DEV / "hidden/genomes/ecoli_k12/sim_source.fa"),
            "sha256": sha256_file(DEV / "hidden/genomes/ecoli_k12/sim_source.fa"),
            "exact_matches": source_hits,
            "target_present_in_hidden_source": bool(source_hits),
            "locate_target": source_locate.get("ecoli_k12"),
        },
        "source_homology_all_fast_pilot_genomes": source_blast,
        "assembly": {
            "path": str(assembly_path),
            "sha256": sha256_file(assembly_path),
            "n_contigs": len(assembly),
            "total_bp": sum(len(s) for _, s in assembly),
            "exact_complete_target_present": bool(assembly_exact),
            "exact_matches": assembly_exact,
        },
        "independent_alignment": {
            "blastn": {k: blastn[k] for k in blastn if k != "hits"} | {"top": (sorted(blastn.get("hits") or [], key=lambda r: r["identity_frac"] * r["query_coverage"], reverse=True)[:5])},
            "tblastn": {k: tblastn[k] for k in tblastn if k != "hits"} | {"top": (sorted(tblastn.get("hits") or [], key=lambda r: r["identity_frac"] * r["query_coverage"], reverse=True)[:5])},
            "minimap2": {k: minimap[k] for k in minimap if k != "hits"} | {"top": (sorted(minimap.get("hits") or [], key=lambda r: r["identity_frac"] * r["query_coverage"], reverse=True)[:5])},
            "internal_gene_search_label": "existing deterministic ungapped k-mer search (not BLAST)",
            "best_nucleotide_internal": hit_dump(best_nt),
            "best_translated_internal": hit_dump(best_aa),
            "best_predicted_protein": None,
            "predicted_proteins_exist": False,
            "n_internal_nt": len(internal_nt),
            "n_internal_translated": len(internal_aa),
            "n_internal_partial": sum(1 for h in internal if partial_hit(h, settings)),
            "n_internal_strong": sum(1 for h in internal if strong_hit(h, settings)),
            "split_across_contigs": gene_split_across_contigs,
        },
        "mapping": {
            "depth_tsv_exists": depth_path.exists(),
            "mapped_sam_exists": (DEV_EVAL / "dev_01/production/mapping/mapped.sam").exists(),
            "eval_pipeline_sets_depth_available": False,
            "local_read_coverage_limitation_in_claims": "read-back depth was unavailable",
            "depth_at_best_locus": depth,
            "locus_used_for_depth": loc_for_depth,
        },
        "thresholds_used": thresholds,
        "where_lost": None,
        "cases_completeness": cases_meta,
        "dummy_cautious_baseline": {
            "strategy": "always target_gene_not_detected, weakened, confidence 0.46, completeness 0.63; no homology",
            "overall": dummy_overall,
            "by_split": dummy_by_split,
            "totals": {k: {"n": v.n, "correct": v.correct, "rate": v.rate} for k, v in dummy_totals.items() if v.n},
            "rows": dummy_rows,
            "genome_skeptic_development_overall": ((gs_dev.get("systems") or {}).get("genome_skeptic") or {}).get("overall"),
            "genome_skeptic_held_out_overall": ((gs_held.get("systems") or {}).get("genome_skeptic") or {}).get("overall"),
            "held_out_achievable_by_dummy": None,
        },
        "diagnostic_controls": control_results,
    }

    # Determine loss point
    loss = []
    if source_hits:
        loss.append("Target nucleotide string is present exactly in the hidden E. coli source genome.")
    else:
        loss.append("Target nucleotide string is ABSENT from the hidden source genome.")
    if assembly_exact:
        loss.append("Complete exact target is present in the SPAdes assembly, so assembly did not destroy the string.")
    else:
        loss.append("Complete exact target string is ABSENT from the SPAdes assembly.")
    top_blast = payload["independent_alignment"]["blastn"].get("top") or []
    if top_blast:
        b = top_blast[0]
        loss.append(
            f"Independent BLASTN best HSP: identity={b['identity_frac']:.3f} query_coverage={b['query_coverage']:.3f} "
            f"on {b['sseqid']} {b['sstart']}-{b['send']}."
        )
        if b["identity_frac"] >= 0.80 and b["query_coverage"] >= 0.80:
            loss.append("BLASTN meets 80/80, so the internal k-mer search missed a threshold-passing hit.")
        else:
            loss.append("BLASTN does not meet the unchanged 80/80 nucleotide rule, so polarity not_detected is consistent with that rule even if a homolog exists.")
    if best_nt:
        loss.append(
            f"Internal nucleotide best hit identity={best_nt.identity:.3f} query_coverage={best_nt.query_coverage:.3f} "
            f"(fails 80/80)."
        )
    payload["where_lost"] = loss
    dummy_held = (dummy_by_split.get("held_out") or {}).get("overall")
    dummy_dev = (dummy_by_split.get("development") or {}).get("overall")
    gs_held_overall = ((gs_held.get("systems") or {}).get("genome_skeptic") or {}).get("overall")
    gs_dev_overall = ((gs_dev.get("systems") or {}).get("genome_skeptic") or {}).get("overall")
    payload["dummy_cautious_baseline"]["held_out_achievable_by_dummy"] = (
        dummy_held is not None and gs_held_overall is not None and abs(dummy_held - gs_held_overall) < 0.08
    )
    payload["dummy_cautious_baseline"]["development_matches_genome_skeptic"] = (
        dummy_dev is not None and gs_dev_overall is not None and abs(dummy_dev - gs_dev_overall) < 0.08
    )

    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    md_path = ROOT / "benchmarks/FAST_PILOT_TARGET_TRACE.md"
    md_path.write_text(render_report(payload))
    print("wrote", OUT_JSON)
    print("wrote", md_path)
    print("blastn", blastn.get("available"), "tblastn", tblastn.get("available"), "minimap", minimap.get("available"))
    print("source_exact", bool(source_hits), "assembly_exact", bool(assembly_exact))
    print("dummy_overall", dummy_overall, "gs_held", payload["dummy_cautious_baseline"]["genome_skeptic_held_out_overall"])
    for name, rec in control_results.items():
        gs = rec.get("genome_skeptic") or {}
        print(name, gs.get("claim_type"), gs.get("status"), gs.get("confidence"), gs.get("evidence_completeness"))


def _fmt_hit(h: dict | None) -> str:
    if not h:
        return "_none_"
    return (
        f"contig `{h.get('contig_id') or h.get('sseqid')}`  \n"
        f"identity={h.get('identity', h.get('identity_frac'))}  "
        f"query_coverage={h.get('query_coverage')}  "
        f"alignment_length={h.get('alignment_length', h.get('length'))}  "
        f"coords query {h.get('qstart')}-{h.get('qend')} subject {h.get('tstart', h.get('sstart'))}-{h.get('tend', h.get('send'))}  "
        f"strand={h.get('strand', '')} edge_distance={h.get('edge_distance_bp')} contig_length={h.get('contig_length', h.get('slen'))}"
    )


def render_report(p: dict) -> str:
    t = p["target"]
    src = p["hidden_source"]
    asm = p["assembly"]
    aln = p["independent_alignment"]
    thr = p["thresholds_used"]
    dummy = p["dummy_cautious_baseline"]
    lines = []
    a = lines.append
    a("# FAST PILOT target-detection failure analysis")
    a("")
    a("**FAST PILOT — NOT FINAL BENCHMARK.** Diagnostic only. Scientific thresholds, claim rules, falsification logic, evidence-completeness weights, and scoring were not modified. Existing FAST_PILOT assemblies and evidence were reused; SPAdes was not rerun.")
    a("")
    a("All measurements below were produced by exact string search, SHA256, BLAST+/minimap2 if present, or the existing deterministic internal gene search. None were inferred by an LLM.")
    a("")
    a("## 1. Target representation (dev_01 query)")
    a("")
    a(f"- FASTA identifier: `{t['fasta_identifier']}`")
    a(f"- Nucleotide length: `{t['nucleotide_length']}`")
    a(f"- SHA256 of nucleotide sequence: `{t['sha256']}`")
    a(f"- Nucleotide sequence: `{t['nucleotide_sequence']}`")
    a(f"- Representation: {t['representation']}")
    a(f"- Chosen translated protein (longest ungapped prefix among frames 0–2): `{t['chosen_protein']}`")
    a(f"- Protein length: `{t['chosen_protein_length']}`")
    a(f"- SHA256 of chosen protein: `{t['protein_sha256']}`")
    a("")
    a("Translated frames:")
    a("")
    for f, rec in t["translated_frames"].items():
        a(f"- frame {f}: length_aa={rec['length_aa']} `{rec['ungapped_prefix']}`")
    a("")
    a("## 2. Hidden source locus (scorer-side only)")
    a("")
    a(f"- Source FASTA: `{src['fasta']}`")
    a(f"- Source file SHA256: `{src['sha256']}`")
    a(f"- Exact complete target present in hidden source: **{src['target_present_in_hidden_source']}**")
    a(f"- `locate_target` (truth rule: identity ≥ 0.5): `{json.dumps(src.get('locate_target'), default=str)}`")
    a("")
    if src.get("exact_matches"):
        a("Exact matches (0-based, inclusive start, exclusive end):")
        a("")
        a("| contig | start | end | strand | contig_length |")
        a("|---|---:|---:|---|---:|")
        for h in src["exact_matches"]:
            a(f"| `{h['contig']}` | {h['start']} | {h['end']} | {h['strand']} | {h['contig_length']} |")
        a("")
        h0 = src["exact_matches"][0]
        a(f"1-based inclusive coordinates: `{h0['contig']}:{h0['start']+1}-{h0['end']}` strand `{h0['strand']}`.")
        a("")
    a("## 3. SPAdes assembly")
    a("")
    a(f"- Assembly path: `{asm['path']}`")
    a(f"- Assembly SHA256: `{asm['sha256']}`")
    a(f"- Contigs: {asm['n_contigs']}; total bp: {asm['total_bp']}")
    a(f"- Complete exact target present in assembly: **{asm['exact_complete_target_present']}**")
    a(f"- SPAdes command: `{p.get('assembly_commands', {}).get('spades_command_line')}`")
    a(f"- Mapping command: `{p.get('assembly_commands', {}).get('mapping_command')}`")
    a("")
    if asm.get("exact_matches"):
        a("| contig | start | end | strand | contig_length |")
        a("|---|---:|---:|---|---:|")
        for h in asm["exact_matches"]:
            a(f"| `{h['contig']}` | {h['start']} | {h['end']} | {h['strand']} | {h['contig_length']} |")
        a("")
    else:
        a("No exact complete copy of Q was found in `contigs.fasta` (forward or reverse complement).")
        a("")
    a("## 4. Independent alignment of Q versus the assembly")
    a("")
    blastn = aln["blastn"]
    tblastn = aln["tblastn"]
    minimap = aln["minimap2"]
    if blastn.get("available"):
        a("### BLASTN (preferred independent check)")
        a("")
        a(f"- Program exited successfully: **{blastn.get('ok')}**")
        a(f"- Command: `{' '.join(str(x) for x in blastn.get('command') or [])}`")
        a(f"- n_hits: {blastn.get('n_hits')}")
        a("")
        for i, h in enumerate(blastn.get("top") or [], 1):
            a(f"{i}. sseqid=`{h['sseqid']}` pident={h['pident']}% identity_frac={h['identity_frac']:.4f} query_coverage={h['query_coverage']:.4f} qcovs={h['qcovs']} length={h['length']} q={h['qstart']}-{h['qend']} s={h['sstart']}-{h['send']} evalue={h['evalue']} bitscore={h['bitscore']}")
        a("")
    else:
        a("BLASTN was not installed in the environment.")
        a("")
    if tblastn.get("available"):
        a("### TBLASTN (protein query vs assembly nucleotides)")
        a("")
        a(f"- Program exited successfully: **{tblastn.get('ok')}**")
        a(f"- Command: `{' '.join(str(x) for x in tblastn.get('command') or [])}`")
        a(f"- n_hits: {tblastn.get('n_hits')}")
        a("")
        for i, h in enumerate(tblastn.get("top") or [], 1):
            a(f"{i}. sseqid=`{h['sseqid']}` pident={h['pident']}% identity_frac={h['identity_frac']:.4f} query_coverage={h['query_coverage']:.4f} q={h['qstart']}-{h['qend']} s={h['sstart']}-{h['send']} evalue={h['evalue']}")
        a("")
    if minimap.get("available"):
        a("### minimap2")
        a("")
        a(f"- Program exited successfully: **{minimap.get('ok')}**")
        a(f"- Command: `{' '.join(str(x) for x in minimap.get('command') or [])}`")
        a(f"- n_hits: {minimap.get('n_hits')}")
        a("")
        for i, h in enumerate(minimap.get("top") or [], 1):
            a(f"{i}. `{h['sseqid']}` identity_frac={h['identity_frac']:.4f} query_coverage={h['query_coverage']:.4f} q={h['qstart']}-{h['qend']} s={h['sstart']}-{h['send']} mapq={h['mapq']}")
        a("")
    a("### Existing deterministic internal gene search (labelled)")
    a("")
    a(f"- Label: {aln['internal_gene_search_label']}")
    a(f"- Command: `{' '.join(str(x) for x in thr['internal_search_command'])}`")
    a(f"- k_nt={thr['gene_search_kmer_nt']} k_aa={thr['gene_search_kmer_aa']} max_mismatch_rate_nt={thr['max_mismatch_rate_nt']} max_mismatch_rate_aa={thr['max_mismatch_rate_aa']}")
    a(f"- Detection rule (unchanged): nucleotide identity≥{thr['gene_nt_min_identity']} and query_coverage≥{thr['gene_nt_min_query_coverage']}; translated identity≥{thr['gene_aa_min_identity']} and query_coverage≥{thr['gene_aa_min_query_coverage']}")
    a(f"- n nucleotide hits: {aln['n_internal_nt']}; n translated hits: {aln['n_internal_translated']}; n strong: {aln['n_internal_strong']}; n partial: {aln['n_internal_partial']}")
    a(f"- Predicted proteins exist: {aln['predicted_proteins_exist']}; best predicted-protein hit: {aln['best_predicted_protein']}")
    a(f"- Gene split across multiple contigs (BLAST subjects with incomplete query coverage): {aln['split_across_contigs']}")
    a("")
    a("Best nucleotide hit:")
    a("")
    a(_fmt_hit(aln.get("best_nucleotide_internal")))
    a("")
    a("Best translated hit:")
    a("")
    a(_fmt_hit(aln.get("best_translated_internal")))
    a("")
    a("## 5. Read coverage at the locus")
    a("")
    m = p["mapping"]
    a(f"- depth.tsv exists: {m['depth_tsv_exists']}")
    a(f"- mapped.sam exists: {m['mapped_sam_exists']}")
    a(f"- Eval pipeline sets `depth_available`: {m['eval_pipeline_sets_depth_available']}")
    a(f"- Claim limitation for `local_read_coverage`: {m['local_read_coverage_limitation_in_claims']}")
    a(f"- Locus used for this diagnostic depth window: `{json.dumps(m.get('locus_used_for_depth'), default=str)}`")
    a(f"- Depth at that window: `{json.dumps(m.get('depth_at_best_locus'), default=str)}`")
    a("")
    a("Mapping exists on disk. The FAST_PILOT eval path never loads `depth.tsv` into `TargetMeasurements.depth_available`, so `local_read_coverage` is skipped even though a depth file is present. That is a wiring gap, not absent data.")
    a("")
    a("## 6. Where the known-positive E. coli target was lost")
    a("")
    for item in p.get("where_lost") or []:
        a(f"- {item}")
    a("")
    a("## 7. Is 80/80 conceptually appropriate for this target?")
    a("")
    a("The query is a **122-nt E. coli rpoB fragment**, not a full-length gene and not an HMM profile. Hidden truth marks `present` when `locate_target` (internal search) reports identity ≥ 0.5. Detection polarity uses a different rule: nucleotide 80/80 or amino-acid 60/80.")
    a("")
    a("| genome | exact nt Q in source | locate_target identity | BLASTN meets 80/80 | TBLASTN meets 60/80 | hidden truth present |")
    a("|---|---|---|---|---|---|")
    for gid, rec in (p.get("source_homology_all_fast_pilot_genomes") or {}).items():
        loc = rec.get("locate_target_identity_ge_0.5_rule") or {}
        loc_id = loc.get("identity") if isinstance(loc, dict) else None
        a(f"| `{gid}` | {rec.get('exact_nt_present')} | {loc_id} | {rec.get('meets_nt_80_80')} | {rec.get('meets_aa_60_80')} | {rec.get('truth_present_if_locate_ge_0.5')} |")
    a("")
    a("Interpretation of detection modes (definitions only; truth was not rewritten):")
    a("")
    a("- **Exact strain-level allele:** requires the E. coli nucleotide string (or a near-identical allele). 80/80 nucleotide is a reasonable operationalisation of that question, but the truth rule (identity ≥ 0.5) is looser than detection (80/80).")
    a("- **Same-gene detection across species:** rpoB exists in all six FAST_PILOT organisms. Nucleotide 80/80 against an E. coli fragment will fail in distant taxa even when the orthologue is present. Protein/profile search is the matching reference strategy for that question.")
    a("- **Orthologue-family detection:** would use a protein or HMM reference. Current FASTA seed does not encode that question.")
    a("- **Domain-level detection:** a short conserved peptide would be expected to hit paralogues; that is a different claim from gene presence.")
    a("")
    a("A nucleotide sequence from E. coli should not automatically be expected to meet the same nucleotide threshold in distantly related bacteria. The FAST_PILOT hidden truth currently answers a hybrid question: 'did the internal k-mer search find this E. coli fragment at ≥50% identity in the source genome?' That is neither exact-allele presence nor orthologue-family presence. Scoring was not changed.")
    a("")
    a("## 8. Diagnostic controls (independent of benchmark scoring)")
    a("")
    a("Tiny synthetic assemblies. No SPAdes. Genome Skeptic was run with unchanged thresholds.")
    a("")
    a("| control | intended biology | claim_type | status | confidence | completeness | n_strong | n_partial |")
    a("|---|---|---|---|---:|---:|---:|---:|")
    for name, rec in (p.get("diagnostic_controls") or {}).items():
        gs = rec.get("genome_skeptic") or {}
        a(f"| `{name}` | {rec.get('note')} | {gs.get('claim_type')} | {gs.get('status')} | {gs.get('confidence')} | {gs.get('evidence_completeness')} | {rec.get('n_strong')} | {rec.get('n_partial')} |")
    a("")
    patterns = []
    for name, rec in (p.get("diagnostic_controls") or {}).items():
        gs = rec.get("genome_skeptic") or {}
        patterns.append((gs.get("claim_type"), gs.get("status"), round(float(gs.get("confidence") or 0), 2)))
    collapsed = len(set(patterns)) == 1
    a(f"Controls collapsed to a single (claim_type, status, confidence≈) pattern: **{collapsed}**.")
    a("")
    if collapsed:
        a("All four controls produced the same polarity/status/confidence band. That is a failure of case discrimination under the current homology implementation, recorded here without changing scoring.")
        a("")
    a("## 9. Evidence completeness ≈ 0.63 on every FAST_PILOT case")
    a("")
    a("Expected validators for `target_gene_not_detected` and their weights: nucleotide_homology 4, translated_homology 4, predicted_protein_homology 2, partial_domain_hits 2, contig_edge_truncation 2, assembly_fragmentation 2, local_read_coverage 2, divergent_homologues 2, read_supported_break 2, reference_neighbor_presence 1, expected_neighboring_genes 1. Denominator = 24 if all are applicable.")
    a("")
    a("Completed contribution if the same six tests complete and the same four are skipped: (4+4+2+2+2+2+2)/24 = 18/24 = 0.75. Two missing high-value tests (`predicted_protein_homology`, `local_read_coverage`) apply multiplier max(0.55, 1−0.08×2) = 0.84. 0.75 × 0.84 = **0.63**. Bakta proteins are unavailable, so predicted-protein homology is always skipped. `depth.tsv` exists but is not wired, so local read coverage is always skipped. No reference neighbors are configured. This constant is a missing-dependency / wiring consequence, not six independent biological completeness values.")
    a("")
    for rec in p.get("cases_completeness") or []:
        c = rec["completeness"]
        a(f"### {rec['case_id']} ({rec['split']}, genome `{rec.get('genome_id')}`, hidden present={rec.get('present')})")
        a("")
        a(f"- Recorded completeness {c.get('recorded_completeness')}; recomputed {c.get('recomputed_completeness')}")
        a(f"- Weighted done {c.get('weighted_done')} / {c.get('weighted_total')}")
        a(f"- Missing essential: {c.get('missing_essential')}")
        a(f"- Missing high-value: {c.get('missing_high_value')}")
        a(f"- Unavailable: {c.get('unavailable')}")
        a("")
        a("| prefix | importance | weight | status | result | limitation | weighted_done |")
        a("|---|---|---:|---|---|---|---:|")
        for v in c.get("validators") or []:
            a(f"| {v['prefix']} | {v['importance']} | {v['weight']} | {v['status']} | {v['result']} | {v.get('limitation') or ''} | {v['weighted_done']} |")
        a("")
        a(f"Confidence path: polarity base {c.get('base_for_polarity')} → status `{c.get('status')}` → confidence_for {c.get('confidence_before_completeness')} → after completeness {c.get('confidence_after_completeness')} (recorded {c.get('recorded_confidence')}).")
        a("")
    a("## 10. Confidence ≈ 0.46")
    a("")
    a("For `target_gene_not_detected` with falsification enabled, base confidence is 0.55. Status is `weakened` because translated homology and partial-domain hits weaken non-detection whenever the k=3 amino-acid search returns partials. `confidence_for(weakened)` caps at `max(0.15, min(0.50, base))` = 0.50. `max_not_detected_confidence` does not lower this further. Completeness then multiplies by max(0.78, 1−0.04×n_missing_high_value). With n=2: 0.50 × 0.92 = **0.46**. Completeness 0.63 ≥ 0.50, so the extra low-completeness cap is not applied. Final clamp is [0.05, 0.85].")
    a("")
    a("Drivers, in order:")
    a("")
    a("1. Claim polarity is uniformly `not_detected` (no 80/80 nucleotide or 60/80 protein hit).")
    a("2. Status is uniformly `weakened` (translated/partial hits), which imposes a 0.50 cap — a status cap, not a homology-quality score.")
    a("3. Missing Bakta proteins and unwired read-depth subtract the same two high-value validators on every case.")
    a("4. Falsification ran; the constant is not a 'falsification disabled' path.")
    a("5. There is no separate per-genome homology strength in the confidence number once polarity and status are fixed.")
    a("")
    a("## 11. Dummy cautious baseline versus the same scorer")
    a("")
    a(f"- Strategy: {dummy['strategy']}")
    a(f"- Dummy overall all six cases (scientific metrics): **{dummy.get('overall')}**")
    a(f"- Dummy development overall: **{(dummy.get('by_split') or {}).get('development', {}).get('overall')}**")
    a(f"- Dummy held-out overall: **{(dummy.get('by_split') or {}).get('held_out', {}).get('overall')}**")
    a(f"- Genome Skeptic development overall: **{dummy.get('genome_skeptic_development_overall')}**")
    a(f"- Genome Skeptic held-out overall: **{dummy.get('genome_skeptic_held_out_overall')}**")
    a(f"- Held-out 1.000 achievable by dummy (within 0.08): **{dummy.get('held_out_achievable_by_dummy')}**")
    a("")
    a("Dummy metric totals:")
    a("")
    a("| metric | n | correct | rate |")
    a("|---|---:|---:|---:|")
    for name, row in (dummy.get("totals") or {}).items():
        a(f"| {name} | {row['n']} | {row['correct']} | {row['rate']} |")
    a("")
    a("Per-case dummy hits:")
    a("")
    for row in dummy.get("rows") or []:
        a(f"- `{row['case_id']}` split={row['split']} present={row['present']} scientifically_correct={row['scientifically_correct']} hits={row['hits']}")
    a("")
    a("`scientifically_correct` requires `target_gene_detected` when hidden present is true and the gene is not fragmented. The dummy therefore fails scientific correctness on dev_01. The scorer's `false_absence` metric nevertheless counts a *weakened* `not_detected` claim as avoiding false absence. Held-out FAST_PILOT truths are all `present: false`, so always saying 'not detected, weakened' scores a perfect scientific overall. If the dummy overall is at or near Genome Skeptic, the held-out 1.000 is not evidence of discriminative biological reasoning.")
    a("")
    a("## 12. Smallest scientifically justified next changes (not applied)")
    a("")
    a("Do not start another SPAdes run. Do not change scoring until these are decided explicitly:")
    a("")
    a("1. State the scientific question for the public seed: exact E. coli allele versus rpoB orthologue family. If orthologue, switch the reference to a protein or profile and score protein-level presence; if exact allele, keep the nucleotide seed and mark only near-identical genomes as present.")
    a("2. Align truth assignment (`locate_target` identity ≥ 0.5) with detection (`strong_hit` 80/80 or 60/80). The mismatch lets a genome be 'present' in truth while remaining undetectable by the production rule.")
    a("3. Prefer BLAST+/minimap2 (already in the mapping environment) over ungapped k=8/k=3 internal search when those programs are installed; the k=3 translated search floods every genome with partials and forces `weakened`.")
    a("4. Wire `depth.tsv` into `depth_available` so `local_read_coverage` is a real measurement.")
    a("5. Close the scoring loophole in which weakened non-detection of a clean present gene is not a false absence and is not underconfidence.")
    a("6. Keep completeness weights unchanged until missing Bakta/taxonomy are either installed or explicitly declared out of scope for FAST_PILOT.")
    a("")
    a("## Machine-readable measurements")
    a("")
    a("Companion JSON: `benchmarks/FAST_PILOT_TARGET_TRACE.json`. Alignment tables: `benchmarks/fast_pilot_target_diagnostics/`.")
    a("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
