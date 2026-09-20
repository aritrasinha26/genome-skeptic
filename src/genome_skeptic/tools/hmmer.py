from __future__ import annotations

from pathlib import Path

from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def hmmer_tools_available() -> list[str]:
    found = []
    if available("hmmsearch"):
        found.append("hmmsearch")
    if available("hmmbuild"):
        found.append("hmmbuild")
    return found


def _parse_tblout(path: Path) -> list[dict]:
    """Parse HMMER --tblout full-sequence hits. Scores are tool output, never invented."""
    hits: list[dict] = []
    if not path.exists():
        return hits
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            hits.append(
                {
                    "target_id": parts[0],
                    "query_name": parts[2],
                    "full_evalue": float(parts[4]),
                    "full_score": float(parts[5]),
                    "full_bias": float(parts[6]),
                    "best_domain_evalue": float(parts[7]),
                    "best_domain_score": float(parts[8]) if len(parts) > 8 else None,
                    "n_reported_domains": int(parts[15]) if len(parts) > 15 else None,
                    "search_kind": "hmm_full",
                    "tool": "hmmsearch",
                }
            )
        except (ValueError, IndexError):
            continue
    return hits


def _parse_domtblout(path: Path) -> list[dict]:
    """Parse HMMER --domtblout domain hits with coordinates and coverage."""
    hits: list[dict] = []
    if not path.exists():
        return hits
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 22:
            continue
        try:
            tlen = int(parts[2])
            qlen = int(parts[5])
            hmm_from = int(parts[15])
            hmm_to = int(parts[16])
            ali_from = int(parts[17])
            ali_to = int(parts[18])
            env_from = int(parts[19])
            env_to = int(parts[20])
            hits.append(
                {
                    "target_id": parts[0],
                    "tlen": tlen,
                    "query_name": parts[3],
                    "qlen": qlen,
                    "full_evalue": float(parts[6]),
                    "full_score": float(parts[7]),
                    "domain_index": int(parts[9]),
                    "n_domains": int(parts[10]),
                    "domain_c_evalue": float(parts[11]),
                    "domain_i_evalue": float(parts[12]),
                    "domain_score": float(parts[13]),
                    "hmm_from": hmm_from,
                    "hmm_to": hmm_to,
                    "ali_from": ali_from,
                    "ali_to": ali_to,
                    "env_from": env_from,
                    "env_to": env_to,
                    "model_span": max(0, hmm_to - hmm_from + 1),
                    "query_span": max(0, ali_to - ali_from + 1),
                    "model_coverage": (hmm_to - hmm_from + 1) / qlen if qlen else 0.0,
                    "query_coverage": (ali_to - ali_from + 1) / tlen if tlen else 0.0,
                    "accuracy": float(parts[21]) if parts[21] not in {".", "-"} else None,
                    "search_kind": "hmm_domain",
                    "tool": "hmmsearch",
                }
            )
        except (ValueError, IndexError):
            continue
    return hits


def summarize_hmm_target(seq_hits: list[dict], domain_hits: list[dict], target_id: str) -> dict | None:
    """Combine full-sequence and domain rows for one query protein/ORF. Do not invent values."""
    seq = [h for h in seq_hits if h.get("target_id") == target_id]
    doms = sorted(
        [h for h in domain_hits if h.get("target_id") == target_id],
        key=lambda h: h.get("hmm_from") or 0,
    )
    if not seq and not doms:
        return None
    best_seq = min(seq, key=lambda h: h.get("full_evalue", 1e9)) if seq else None
    qlen = next((d.get("qlen") for d in doms if d.get("qlen")), None)
    tlen = next((d.get("tlen") for d in doms if d.get("tlen")), None)
    model_covered = set()
    query_covered = set()
    for d in doms:
        qlen = qlen or d.get("qlen")
        tlen = tlen or d.get("tlen")
        for i in range(int(d.get("hmm_from") or 1), int(d.get("hmm_to") or 0) + 1):
            model_covered.add(i)
        for i in range(int(d.get("ali_from") or 1), int(d.get("ali_to") or 0) + 1):
            query_covered.add(i)
    model_cov = (len(model_covered) / qlen) if qlen else 0.0
    query_cov = (len(query_covered) / tlen) if tlen else 0.0
    order = [int(d.get("domain_index") or i + 1) for i, d in enumerate(doms)]
    n_dom = len(doms)
    domain_complete = []
    for d in doms:
        span = float(d.get("model_span") or 0)
        # Completeness of this reported domain relative to its own aligned HMM span is 1 if present.
        domain_complete.append(
            {
                "domain_index": d.get("domain_index"),
                "hmm_from": d.get("hmm_from"),
                "hmm_to": d.get("hmm_to"),
                "domain_score": d.get("domain_score"),
                "domain_i_evalue": d.get("domain_i_evalue"),
                "complete": bool(span > 0),
            }
        )
    return {
        "target_id": target_id,
        "full_evalue": (best_seq or doms[0]).get("full_evalue"),
        "full_score": (best_seq or {}).get("full_score") or (doms[0].get("full_score") if doms else None),
        "best_domain_evalue": (best_seq or {}).get("best_domain_evalue") or (doms[0].get("domain_i_evalue") if doms else None),
        "best_domain_score": (best_seq or {}).get("best_domain_score") or (max((d.get("domain_score") or 0) for d in doms) if doms else None),
        "model_length": qlen,
        "query_length": tlen,
        "model_coverage": round(model_cov, 4),
        "query_coverage": round(query_cov, 4),
        "n_domains": n_dom,
        "domain_order": order,
        "domain_completeness": domain_complete,
        "domains": doms,
        "tool": "hmmsearch",
        "invented": False,
    }


def run_hmmsearch(hmm_path: Path, seqs_fa: Path, out_dir: Path, threads: int) -> ToolResult:
    if not available("hmmsearch"):
        return ToolResult(name="hmmsearch", stage="target_gene", ok=False, error="hmmsearch not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    tbl = out_dir / "hmmsearch.tbl"
    domtbl = out_dir / "hmmsearch.domtbl"
    cmd = [
        "hmmsearch", "--noali",
        "--tblout", str(tbl),
        "--domtblout", str(domtbl),
        "--cpu", str(threads),
        str(hmm_path), str(seqs_fa),
    ]
    result = run_command("hmmsearch", "target_gene", cmd, out_dir)
    seq_hits = _parse_tblout(tbl) if tbl.exists() else []
    domain_hits = _parse_domtblout(domtbl) if domtbl.exists() else []
    result.outputs["tblout"] = str(tbl)
    result.outputs["domtblout"] = str(domtbl)
    result.metrics["sequence_hits"] = seq_hits
    result.metrics["domain_hits"] = domain_hits
    result.metrics["n_sequence_hits"] = len(seq_hits)
    result.metrics["n_domain_hits"] = len(domain_hits)
    result.metrics["evalues_from_tool"] = True
    result.metrics["scores_invented"] = False
    targets = sorted({h["target_id"] for h in seq_hits + domain_hits})
    result.metrics["by_target"] = {
        tid: summarize_hmm_target(seq_hits, domain_hits, tid) for tid in targets
    }
    if not result.ok and (seq_hits or domain_hits):
        result.ok = True
        result.error = None
    return result


def run_hmmbuild(alignment: Path, hmm_path: Path, out_dir: Path) -> ToolResult:
    if not available("hmmbuild"):
        return ToolResult(name="hmmbuild", stage="target_gene", ok=False, error="hmmbuild not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    hmm_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["hmmbuild", "--amino", str(hmm_path), str(alignment)]
    result = run_command("hmmbuild", "target_gene", cmd, out_dir)
    if result.ok:
        result.outputs["hmm"] = str(hmm_path)
        result.metrics["hmm_source"] = "curated_family_alignment"
        result.metrics["alignment"] = str(alignment)
    return result


def run_hmmbuild_and_search(query_faa: Path, seqs_fa: Path, out_dir: Path, threads: int) -> ToolResult:
    """Legacy single-sequence HMM. Prefer curated family models for gene_orthologue."""
    if not available("hmmbuild") or not available("hmmsearch"):
        return ToolResult(name="hmmbuild_hmmsearch", stage="target_gene", ok=False, error="hmmbuild/hmmsearch not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    hmm = out_dir / "query.hmm"
    built = run_hmmbuild(query_faa, hmm, out_dir)
    if not built.ok:
        return built
    result = run_hmmsearch(hmm, seqs_fa, out_dir, threads)
    result.metrics["hmm_source"] = "single_sequence_hmmbuild"
    result.metrics["limitation"] = "HMM was built from the query sequence, not a curated family model"
    return result
