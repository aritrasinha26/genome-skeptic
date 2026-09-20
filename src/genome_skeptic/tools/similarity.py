from __future__ import annotations

from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.io_utils import read_fasta
from genome_skeptic.models import GeneSearchHit, ToolResult
from genome_skeptic.tools.base import available, run_command


def similarity_tools_available() -> list[str]:
    found = []
    if available("mmseqs"):
        found.append("mmseqs")
    if available("diamond"):
        found.append("diamond")
    return found


def _parse_search_tsv(path: Path, search_kind: str, tool: str) -> list[GeneSearchHit]:
    hits: list[GeneSearchHit] = []
    if not path.exists():
        return hits
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        try:
            pident = float(parts[2])
            alnlen = int(float(parts[3]))
            qstart = int(parts[4]) - 1
            qend = int(parts[5])
            tstart = int(parts[6]) - 1
            tend = int(parts[7])
            evalue = float(parts[8])
            qlen = int(float(parts[9])) if len(parts) > 9 else max(qend, 1)
        except ValueError:
            continue
        identity = pident / 100.0 if pident > 1.5 else pident
        qcov = (qend - qstart) / qlen if qlen else 0.0
        if len(parts) > 10:
            try:
                extra = float(parts[10])
                qcov = extra / 100.0 if extra > 1.5 else extra
            except ValueError:
                pass
        strand: str = "+"
        if tend < tstart:
            tstart, tend, strand = tend, tstart, "-"
        hits.append(
            GeneSearchHit(
                query_id=parts[0],
                contig_id=parts[1],
                search_kind=search_kind,  # type: ignore[arg-type]
                qstart=qstart,
                qend=qend,
                tstart=tstart,
                tend=tend,
                strand=strand,  # type: ignore[arg-type]
                identity=identity,
                query_coverage=qcov,
                alignment_length=alnlen,
                query_length=qlen,
                contig_length=0,
                evalue=evalue,
                tool=tool,
            )
        )
    return hits


def run_mmseqs_search(query_fa: Path, target_fa: Path, out_dir: Path, threads: int, search_kind: str) -> ToolResult:
    if not available("mmseqs"):
        return ToolResult(name="mmseqs", stage="target_gene", ok=False, error="mmseqs not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "mmseqs.m8"
    tmp = out_dir / "mmseqs_tmp"
    search_type = {"nucleotide": "3", "protein": "1", "translated": "2"}.get(search_kind, "0")
    mem = "1G"
    try:
        pages = int(Path("/proc/meminfo").read_text().split("MemAvailable:")[1].split()[0])
        gb = max(1, min(8, pages // (1024 * 1024) - 1))
        mem = f"{gb}G"
    except Exception:
        pass
    cmd = [
        "mmseqs", "easy-search", str(query_fa), str(target_fa), str(result_path), str(tmp),
        "--threads", str(max(1, min(threads, 2))),
        "--search-type", search_type,
        "--split-memory-limit", mem,
        "--format-output", "query,target,pident,alnlen,qstart,qend,tstart,tend,evalue,qlen,qcov",
    ]
    result = run_command("mmseqs", "target_gene", cmd, out_dir)
    if result.ok:
        hits = _parse_search_tsv(result_path, search_kind if search_kind != "translated" else "translated", "mmseqs")
        result.outputs["hits_tsv"] = str(result_path)
        result.metrics["hits"] = [h.model_dump() for h in hits]
        result.metrics["n_hits"] = len(hits)
    return result


def run_diamond_search(query_fa: Path, target_fa: Path, out_dir: Path, threads: int, mode: str) -> ToolResult:
    if not available("diamond"):
        return ToolResult(name="diamond", stage="target_gene", ok=False, error="diamond not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    db = out_dir / "diamond.dmnd"
    result_path = out_dir / "diamond.m8"
    makedb = run_command("diamond_makedb", "target_gene", ["diamond", "makedb", "--in", str(target_fa), "-d", str(db)], out_dir)
    if not makedb.ok:
        return makedb
    cmd = [
        "diamond", mode, "-q", str(query_fa), "-d", str(db), "-o", str(result_path),
        "--threads", str(threads),
        "--outfmt", "6", "qseqid", "sseqid", "pident", "length", "qstart", "qend", "sstart", "send", "evalue", "qlen", "qcovhsp",
    ]
    result = run_command("diamond", "target_gene", cmd, out_dir)
    kind = "protein" if mode == "blastp" else "translated"
    if result.ok:
        hits = _parse_search_tsv(result_path, kind, "diamond")
        result.outputs["hits_tsv"] = str(result_path)
        result.metrics["hits"] = [h.model_dump() for h in hits]
        result.metrics["n_hits"] = len(hits)
    return result


def run_preferred_similarity_search(query_fa: Path, target_fa: Path, out_dir: Path, settings: Settings, search_kind: str) -> ToolResult:
    """Prefer MMseqs2, then DIAMOND. Never invent identity/coverage/E-values.

    If MMseqs2 is installed but cannot execute (e.g. host RAM), DIAMOND is used
    when applicable. That is a production-tool fallback, not a toy search.
    """
    mmseqs_result = None
    if available("mmseqs"):
        mmseqs_result = run_mmseqs_search(query_fa, target_fa, out_dir / "mmseqs", settings.project.threads, search_kind)
        if mmseqs_result.ok:
            return mmseqs_result
    if available("diamond") and search_kind in {"protein", "translated"}:
        mode = "blastp" if search_kind == "protein" else "blastx"
        query_is_nt = False
        try:
            recs = read_fasta(query_fa)
            if recs:
                from genome_skeptic.tools.gene_search import is_nucleotide
                query_is_nt = is_nucleotide(recs[0][1])
        except Exception:
            query_is_nt = search_kind == "translated"
        if search_kind == "translated" and not query_is_nt:
            mode = "blastp"
        diamond_result = run_diamond_search(query_fa, target_fa, out_dir / "diamond", settings.project.threads, mode)
        if mmseqs_result is not None and not mmseqs_result.ok:
            diamond_result.metrics = dict(diamond_result.metrics or {})
            diamond_result.metrics["mmseqs_failed"] = mmseqs_result.error
        return diamond_result
    if mmseqs_result is not None:
        return mmseqs_result
    return ToolResult(
        name="similarity_search",
        stage="target_gene",
        ok=False,
        error="neither mmseqs nor diamond is available",
    )
