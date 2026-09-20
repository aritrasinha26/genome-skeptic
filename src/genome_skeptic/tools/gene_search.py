from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from typing import Literal

from genome_skeptic.config import Settings
from genome_skeptic.coords import gff_to_internal, intervals_overlap
from genome_skeptic.io_utils import read_fasta
from genome_skeptic.models import GeneSearchHit, ToolResult


_NT = set("ACGTUN")
_AA = set("ACDEFGHIKLMNPQRSTVWY")

# Standard bacterial translation table 11 is identical to table 1 for these codons.
_CODONS = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}

_COMPLEMENT = str.maketrans("ACGTUNacgtun", "TGCAANtgcaan")


def reverse_complement(seq: str) -> str:
    return seq.translate(_COMPLEMENT)[::-1]


def is_nucleotide(seq: str) -> bool:
    letters = [c for c in seq.upper() if c.isalpha()]
    if not letters:
        return True
    return sum(c in _NT for c in letters) / len(letters) >= 0.85


def translate_frame(seq: str, frame: int = 0) -> str:
    seq = seq.upper().replace("U", "T")
    aa: list[str] = []
    for i in range(frame, len(seq) - 2, 3):
        aa.append(_CODONS.get(seq[i:i + 3], "X"))
    return "".join(aa)


_ORF_CACHE: dict[str, list[dict]] = {}
_ORF_CACHE_MAX = 24


def _orf_cache_key(contigs: list[tuple[str, str]], min_aa: int, edge_bp: int) -> str:
    h = hashlib.sha256()
    h.update(f"{int(min_aa)}:{int(edge_bp)}:{len(contigs)}".encode())
    for cid, seq in contigs:
        h.update(cid.encode("utf-8", "ignore"))
        h.update(b"\0")
        n = len(seq or "")
        h.update(str(n).encode())
        if seq:
            h.update(seq[:96].encode("ascii", "ignore"))
            h.update(seq[-96:].encode("ascii", "ignore"))
            h.update(str(hash(seq)).encode())
        h.update(b"\0")
    return h.hexdigest()


def extract_orfs(
    contigs: list[tuple[str, str]],
    *,
    min_aa: int = 80,
    edge_bp: int = 300,
) -> list[dict]:
    """Six-frame stop-to-stop ORFs with genomic coordinates. Sequences are translations, not invented proteins."""
    key = _orf_cache_key(contigs, min_aa, edge_bp)
    cached = _ORF_CACHE.get(key)
    if cached is not None:
        return copy.deepcopy(cached)
    orfs: list[dict] = []
    for cid, seq in contigs:
        nt_plus = seq.upper().replace("U", "T")
        n = len(nt_plus)
        for strand, nt in (("+", nt_plus), ("-", reverse_complement(nt_plus))):
            for frame in range(3):
                aa = translate_frame(nt, frame)
                start = 0
                while start < len(aa):
                    while start < len(aa) and aa[start] == "*":
                        start += 1
                    end = start
                    while end < len(aa) and aa[end] != "*":
                        end += 1
                    if end - start >= min_aa:
                        if strand == "+":
                            tstart = frame + start * 3
                            tend = frame + end * 3
                        else:
                            rc_start = frame + start * 3
                            rc_end = frame + end * 3
                            tstart = n - rc_end
                            tend = n - rc_start
                        lo, hi = min(tstart, tend), max(tstart, tend)
                        orf_id = f"{cid}:{lo}-{hi}:{strand}"
                        orfs.append(
                            {
                                "orf_id": orf_id,
                                "contig_id": cid,
                                "start": lo,
                                "end": hi,
                                "strand": strand,
                                "sequence": aa[start:end],
                                "length_aa": end - start,
                                "contig_length": n,
                                "near_contig_edge": lo <= edge_bp or (n - hi) <= edge_bp,
                            }
                        )
                    start = end + 1
    if len(_ORF_CACHE) >= _ORF_CACHE_MAX:
        _ORF_CACHE.pop(next(iter(_ORF_CACHE)))
    _ORF_CACHE[key] = orfs
    return copy.deepcopy(orfs)


def _kmer_positions(seq: str, k: int) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    if k <= 0 or len(seq) < k:
        return out
    for i in range(len(seq) - k + 1):
        mer = seq[i:i + k]
        if "N" in mer or "X" in mer or "*" in mer:
            continue
        out.setdefault(mer, []).append(i)
    return out


def _extend(query: str, target: str, q0: int, t0: int, k: int, max_mismatch_rate: float) -> tuple[int, int, int, int, int, int]:
    q_end = q0 + k
    t_end = t0 + k
    matches = k
    aligned = k

    while q_end < len(query) and t_end < len(target):
        aligned += 1
        if query[q_end] == target[t_end]:
            matches += 1
        elif (aligned - matches) / aligned > max_mismatch_rate:
            aligned -= 1
            break
        q_end += 1
        t_end += 1

    q_start = q0
    t_start = t0
    while q_start > 0 and t_start > 0:
        trial_aligned = aligned + 1
        trial_matches = matches + (1 if query[q_start - 1] == target[t_start - 1] else 0)
        if query[q_start - 1] != target[t_start - 1] and (trial_aligned - trial_matches) / trial_aligned > max_mismatch_rate:
            break
        q_start -= 1
        t_start -= 1
        aligned = trial_aligned
        matches = trial_matches
    return q_start, q_end, t_start, t_end, matches, aligned


def _search_ungapped(
    query_id: str,
    query: str,
    contig_id: str,
    contig: str,
    strand: str,
    search_kind: str,
    k: int,
    max_mismatch_rate: float,
    nt_coords: bool,
    frame: int = 0,
    contig_nt_length: int | None = None,
) -> list[GeneSearchHit]:
    query = query.upper()
    contig_seq = contig.upper()
    q_kmers = _kmer_positions(query, k)
    if not q_kmers:
        return []
    hits: list[GeneSearchHit] = []
    seen: set[tuple[int, int, int, int]] = set()
    contig_len_nt = contig_nt_length if contig_nt_length is not None else len(contig_seq)

    for tpos in range(0, len(contig_seq) - k + 1):
        mer = contig_seq[tpos:tpos + k]
        qpositions = q_kmers.get(mer)
        if not qpositions:
            continue
        for qpos in qpositions:
            q_start, q_end, t_start, t_end, matches, aligned = _extend(
                query, contig_seq, qpos, tpos, k, max_mismatch_rate
            )
            key = (q_start, q_end, t_start, t_end)
            if key in seen or aligned <= 0:
                continue
            seen.add(key)
            identity = matches / aligned
            query_coverage = (q_end - q_start) / len(query) if query else 0.0
            if nt_coords:
                tstart = t_start
                tend = t_end
                aln_len = aligned
            else:
                tstart = t_start * 3 + frame
                tend = t_end * 3 + frame
                aln_len = aligned * 3
            if strand == "-":
                tstart, tend = contig_len_nt - tend, contig_len_nt - tstart
            edge_distance = min(max(tstart, 0), max(contig_len_nt - tend, 0))
            q_overhang_left = q_start
            q_overhang_right = len(query) - q_end
            if not nt_coords:
                q_overhang_left *= 3
                q_overhang_right *= 3
            left_room = tstart
            right_room = contig_len_nt - tend
            possible_truncation = (q_overhang_left > left_room) or (q_overhang_right > right_room)
            hits.append(
                GeneSearchHit(
                    query_id=query_id,
                    contig_id=contig_id,
                    search_kind=search_kind,  # type: ignore[arg-type]
                    qstart=q_start,
                    qend=q_end,
                    tstart=tstart,
                    tend=tend,
                    strand=strand,  # type: ignore[arg-type]
                    identity=identity,
                    query_coverage=query_coverage,
                    alignment_length=aln_len,
                    query_length=len(query),
                    contig_length=contig_len_nt,
                    near_contig_edge=False,
                    possible_edge_truncation=possible_truncation,
                    edge_distance_bp=edge_distance,
                )
            )
    hits.sort(key=lambda h: (h.query_coverage * h.identity, h.alignment_length), reverse=True)
    return hits


def _dedupe_hits(hits: list[GeneSearchHit], max_hits: int) -> list[GeneSearchHit]:
    """Keep up to max_hits per query. Do not let one query starve another."""
    kept: list[GeneSearchHit] = []
    by_query: dict[str, list[GeneSearchHit]] = {}
    for hit in hits:
        bucket = by_query.setdefault(hit.query_id, [])
        if len(bucket) >= max_hits:
            continue
        overlapping = False
        for prev in bucket:
            if prev.contig_id != hit.contig_id or prev.search_kind != hit.search_kind or prev.strand != hit.strand:
                continue
            q_overlap = min(prev.qend, hit.qend) - max(prev.qstart, hit.qstart)
            t_overlap = min(prev.tend, hit.tend) - max(prev.tstart, hit.tstart)
            if q_overlap > 0 and t_overlap > 0:
                overlapping = True
                break
        if not overlapping:
            bucket.append(hit)
            kept.append(hit)
    return kept


def annotate_edges(hits: list[GeneSearchHit], edge_bp: int) -> list[GeneSearchHit]:
    for hit in hits:
        hit.near_contig_edge = hit.edge_distance_bp <= edge_bp
        if hit.near_contig_edge and hit.query_coverage < 0.95:
            hit.possible_edge_truncation = True
    return hits


def search_targets(targets: list[tuple[str, str]], contigs: list[tuple[str, str]], settings: Settings) -> list[GeneSearchHit]:
    t = settings.thresholds
    all_hits: list[GeneSearchHit] = []
    for qid, qseq in targets:
        qseq_u = qseq.upper()
        query_hits: list[GeneSearchHit] = []
        nt_query = is_nucleotide(qseq_u)
        for cid, cseq in contigs:
            cseq_u = cseq.upper()
            if nt_query:
                for strand, target in (("+", cseq_u), ("-", reverse_complement(cseq_u))):
                    query_hits.extend(
                        _search_ungapped(
                            qid, qseq_u, cid, target, strand, "nucleotide",
                            t.gene_search_kmer_nt, 1 - t.gene_nt_min_identity + 0.15,
                            nt_coords=True, contig_nt_length=len(cseq_u),
                        )
                    )
            aa_query = qseq_u if not nt_query else max((translate_frame(qseq_u, f) for f in range(3)), key=len)
            aa_query = aa_query.split("*")[0] if aa_query else aa_query
            if aa_query and any(c in _AA for c in aa_query):
                for strand, nt in (("+", cseq_u), ("-", reverse_complement(cseq_u))):
                    for frame in range(3):
                        aa_contig = translate_frame(nt, frame)
                        query_hits.extend(
                            _search_ungapped(
                                qid, aa_query, cid, aa_contig, strand, "translated",
                                t.gene_search_kmer_aa, 1 - t.gene_aa_min_identity + 0.20,
                                nt_coords=False, frame=frame, contig_nt_length=len(cseq_u),
                            )
                        )
        query_hits.sort(key=lambda h: (h.query_coverage * h.identity, h.alignment_length), reverse=True)
        query_hits = annotate_edges(_dedupe_hits(query_hits, t.gene_max_hits_per_query), t.contig_edge_proximity_bp)
        all_hits.extend(query_hits)
    return all_hits


def search_proteins(query_id: str, query_aa: str, proteins: list[tuple[str, str]], settings: Settings) -> list[GeneSearchHit]:
    t = settings.thresholds
    hits: list[GeneSearchHit] = []
    for pid, pseq in proteins:
        hits.extend(
            _search_ungapped(
                query_id, query_aa.upper(), pid, pseq.upper(), "+", "protein",
                t.gene_search_kmer_aa, 1 - t.gene_aa_min_identity + 0.20,
                nt_coords=True, contig_nt_length=len(pseq),
            )
        )
    for h in hits:
        h.search_kind = "protein"
        h.tool = "internal_gene_search"
    hits.sort(key=lambda h: (h.query_coverage * h.identity, h.alignment_length), reverse=True)
    return _dedupe_hits(hits, t.gene_max_hits_per_query)


def search_domains(query_id: str, query_aa: str, domains: list, contigs: list[tuple[str, str]], settings: Settings) -> list[GeneSearchHit]:
    from genome_skeptic.models import QueryDomain
    t = settings.thresholds
    hits: list[GeneSearchHit] = []
    for domain in domains:
        if isinstance(domain, QueryDomain):
            name, start, end = domain.name, domain.start, domain.end
        else:
            name, start, end = domain["name"], domain["start"], domain["end"]
        fragment = query_aa[start:end].upper()
        if len(fragment) < t.gene_search_kmer_aa:
            continue
        for cid, cseq in contigs:
            cseq_u = cseq.upper()
            for strand, nt in (("+", cseq_u), ("-", reverse_complement(cseq_u))):
                for frame in range(3):
                    aa_contig = translate_frame(nt, frame)
                    found = _search_ungapped(
                        query_id, fragment, cid, aa_contig, strand, "domain",
                        t.gene_search_kmer_aa, 1 - t.gene_aa_min_identity + 0.20,
                        nt_coords=False, frame=frame, contig_nt_length=len(cseq_u),
                    )
                    for h in found:
                        h.domain_name = name
                        h.qstart += start
                        h.qend += start
                        h.query_length = len(query_aa)
                        h.query_coverage = (h.qend - h.qstart) / len(query_aa) if query_aa else 0.0
                        h.tool = "internal_gene_search"
                    hits.extend(found)
    hits.sort(key=lambda h: (h.identity, h.alignment_length), reverse=True)
    return _dedupe_hits(hits, t.gene_max_hits_per_query)


def parse_gff_features(path: str | Path) -> list[dict]:
    features: list[dict] = []
    with open(path) as fh:
        for line in fh:
            if not line or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            attrs = {}
            for item in parts[8].split(";"):
                if not item:
                    continue
                if "=" in item:
                    k, v = item.split("=", 1)
                elif " " in item:
                    k, v = item.split(" ", 1)
                else:
                    continue
                attrs[k.strip()] = v.strip().strip('"')
            try:
                gstart, gend = gff_to_internal(int(parts[3]), int(parts[4]))
            except ValueError:
                continue
            features.append({
                "seqid": parts[0],
                "type": parts[2].lower(),
                "start": gstart,
                "end": gend,
                "gff_start": int(parts[3]),
                "gff_end": int(parts[4]),
                "coord_system": "0-based-half-open",
                "strand": parts[6],
                "product": attrs.get("product") or attrs.get("Name") or attrs.get("gene") or "",
                "gene_id": attrs.get("ID") or attrs.get("locus_tag") or attrs.get("Name") or attrs.get("gene") or f"{parts[0]}:{parts[3]}-{parts[4]}",
                "attrs": attrs,
            })
    return features


def local_coverage_for_hits(depth_path: str | Path, hits: list[GeneSearchHit]) -> dict[str, dict]:
    needed: dict[str, list[tuple[int, int, str]]] = {}
    for hit in hits:
        key = f"{hit.query_id}:{hit.contig_id}:{hit.tstart}-{hit.tend}"
        needed.setdefault(hit.contig_id, []).append((hit.tstart, hit.tend, key))
    if not needed:
        return {}
    sums: dict[str, list[float]] = {k: [] for ranges in needed.values() for _, _, k in ranges}
    genome_depths: list[float] = []
    with open(depth_path) as fh:
        for line in fh:
            parts = line.rstrip().split("\t")
            if len(parts) < 3:
                continue
            contig, pos_s, depth_s = parts[0], parts[1], parts[2]
            try:
                pos = int(pos_s)
                depth = float(depth_s)
            except ValueError:
                continue
            genome_depths.append(depth)
            for start, end, key in needed.get(contig, []):
                if start < pos <= end:
                    sums.setdefault(key, []).append(depth)
    genome_mean = (sum(genome_depths) / len(genome_depths)) if genome_depths else None
    out: dict[str, dict] = {}
    for key, values in sums.items():
        local_mean = (sum(values) / len(values)) if values else None
        out[key] = {
            "local_mean_depth": local_mean,
            "genome_mean_depth": genome_mean,
            "relative_depth": (local_mean / genome_mean) if local_mean is not None and genome_mean else None,
            "positions_counted": len(values),
            "zero_positions": sum(1 for v in values if v == 0),
            "min_depth": min(values) if values else None,
            "coverage_discontinuity": bool(values) and (
                sum(1 for v in values if v == 0) > 0
                or (genome_mean is not None and min(values) < 0.1 * genome_mean)
            ),
        }
    return out


def _blast_available() -> dict[str, str]:
    import shutil
    found = {}
    for name in ("blastn", "tblastn", "blastx"):
        path = shutil.which(name)
        if path:
            found[name] = path
    return found


def _parse_blast_hits(text: str, search_kind: str, query_id: str, query_len: int, contig_lengths: dict[str, int]) -> list[GeneSearchHit]:
    hits: list[GeneSearchHit] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        sseqid = parts[1]
        pident = float(parts[2])
        length = int(parts[3])
        qlen = int(parts[4]) if len(parts) > 4 else query_len
        slen = int(parts[5]) if len(parts) > 5 else contig_lengths.get(sseqid, 0)
        qstart = int(parts[6])
        qend = int(parts[7])
        sstart = int(parts[8])
        send = int(parts[9])
        evalue = float(parts[10])
        strand: Literal["+", "-"] = "+" if sstart <= send else "-"
        tstart, tend = min(sstart, send) - 1, max(sstart, send)
        q0, q1 = min(qstart, qend) - 1, max(qstart, qend)
        ident = pident / 100.0
        qcov = (q1 - q0) / qlen if qlen else 0.0
        aln = length if search_kind == "nucleotide" else length * 3
        subj_cov = None
        if search_kind == "nucleotide" and slen:
            subj_cov = aln / slen
        elif slen:
            subj_cov = length / (slen if search_kind == "protein" else max(1, slen // 3))
        hits.append(
            GeneSearchHit(
                query_id=query_id,
                contig_id=sseqid,
                search_kind=search_kind,  # type: ignore[arg-type]
                qstart=q0,
                qend=q1,
                tstart=tstart,
                tend=tend,
                strand=strand,
                identity=ident,
                query_coverage=qcov,
                alignment_length=aln,
                query_length=qlen,
                contig_length=slen or contig_lengths.get(sseqid, 0),
                evalue=evalue,
                subject_coverage=subj_cov,
                tool="blast+",
            )
        )
    return hits


def search_targets_blast(
    targets: list[tuple[str, str]],
    contigs_fa: Path,
    out_dir: Path,
    contig_lengths: dict[str, int],
) -> tuple[list[GeneSearchHit], list[str]]:
    """BLAST+ local alignment when installed. Not an LLM inference."""
    import subprocess
    from tempfile import NamedTemporaryFile

    tools = _blast_available()
    if not tools:
        return [], []
    out_dir.mkdir(parents=True, exist_ok=True)
    hits: list[GeneSearchHit] = []
    commands: list[str] = []
    fmt = "6 qseqid sseqid pident length qlen slen qstart qend sstart send evalue bitscore"
    for qid, qseq in targets:
        qseq_u = qseq.upper()
        nt_query = is_nucleotide(qseq_u)
        with NamedTemporaryFile("w", suffix=".fa", delete=False) as fh:
            fh.write(f">{qid}\n{qseq_u}\n")
            qpath = Path(fh.name)
        try:
            if nt_query and "blastn" in tools:
                cmd = [tools["blastn"], "-query", str(qpath), "-subject", str(contigs_fa), "-task", "blastn",
                       "-evalue", "10", "-word_size", "11", "-dust", "no", "-soft_masking", "false",
                       "-outfmt", fmt, "-max_hsps", "20", "-max_target_seqs", "20"]
                p = subprocess.run(cmd, capture_output=True, text=True)
                commands.append(" ".join(cmd))
                if p.returncode == 0:
                    hits.extend(_parse_blast_hits(p.stdout, "nucleotide", qid, len(qseq_u), contig_lengths))
                aa = max((translate_frame(qseq_u, f) for f in range(3)), key=len).split("*")[0]
                if aa and "tblastn" in tools:
                    with NamedTemporaryFile("w", suffix=".faa", delete=False) as aa_fh:
                        aa_fh.write(f">{qid}\n{aa}\n")
                        aapath = Path(aa_fh.name)
                    try:
                        cmdt = [tools["tblastn"], "-query", str(aapath), "-subject", str(contigs_fa),
                                "-evalue", "1e-3", "-outfmt", fmt, "-max_hsps", "20", "-max_target_seqs", "20"]
                        pt = subprocess.run(cmdt, capture_output=True, text=True)
                        commands.append(" ".join(cmdt))
                        if pt.returncode == 0:
                            hits.extend(_parse_blast_hits(pt.stdout, "translated", qid, len(aa), contig_lengths))
                    finally:
                        aapath.unlink(missing_ok=True)
            elif not nt_query and "tblastn" in tools:
                cmd = [tools["tblastn"], "-query", str(qpath), "-subject", str(contigs_fa),
                       "-evalue", "1e-3", "-outfmt", fmt, "-max_hsps", "20", "-max_target_seqs", "20"]
                p = subprocess.run(cmd, capture_output=True, text=True)
                commands.append(" ".join(cmd))
                if p.returncode == 0:
                    aa_len = len(qseq_u.split("*")[0])
                    parsed = _parse_blast_hits(p.stdout, "translated", qid, aa_len, contig_lengths)
                    for h in parsed:
                        h.query_length = aa_len
                    hits.extend(parsed)
        finally:
            qpath.unlink(missing_ok=True)
    return hits, commands


def run_gene_search(targets_fa: Path, contigs_fa: Path, out_dir: Path, settings: Settings) -> ToolResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        targets = read_fasta(targets_fa)
        contigs = read_fasta(contigs_fa)
    except Exception as exc:
        return ToolResult(
            name="internal_gene_search",
            stage="target_gene",
            ok=False,
            error=str(exc),
            command=["internal_gene_search", str(targets_fa), str(contigs_fa)],
        )
    contig_lengths = {cid: len(seq) for cid, seq in contigs}
    tools = _blast_available()
    blast_hits, blast_cmds = search_targets_blast(targets, contigs_fa, out_dir, contig_lengths) if tools else ([], [])
    if tools:
        hits = blast_hits
        tool_name = "blast+"
        command = blast_cmds or ["blastn/tblastn"]
        if not hits:
            hits = search_targets(targets, contigs, settings)
            tool_name = "blast+_empty_then_internal"
            command = list(command) + ["internal_gene_search_fallback"]
    else:
        hits = search_targets(targets, contigs, settings)
        tool_name = "internal_gene_search"
        command = ["internal_gene_search", "--targets", str(targets_fa), "--contigs", str(contigs_fa)]
    hits.sort(key=lambda h: (h.query_coverage * h.identity, h.alignment_length), reverse=True)
    hits = annotate_edges(_dedupe_hits(hits, settings.thresholds.gene_max_hits_per_query), settings.thresholds.contig_edge_proximity_bp)
    hits_path = out_dir / "gene_search_hits.json"
    payload = [h.model_dump() for h in hits]
    hits_path.write_text(json.dumps(payload, indent=2))
    by_query: dict[str, int] = {}
    for h in hits:
        by_query[h.query_id] = by_query.get(h.query_id, 0) + 1
    return ToolResult(
        name=tool_name,
        stage="target_gene",
        ok=True,
        command=command if isinstance(command, list) else [command],
        outputs={"hits_json": str(hits_path), "targets": str(targets_fa), "contigs": str(contigs_fa)},
        metrics={
            "n_queries": len(targets),
            "n_contigs": len(contigs),
            "n_hits": len(hits),
            "hits_per_query": by_query,
            "hits": payload,
            "query_ids": [qid for qid, _ in targets],
            "query_lengths": {qid: len(seq) for qid, seq in targets},
            "search_backend": tool_name,
        },
    )


def neighborhood_for_hits(features: list[dict], hits: list[GeneSearchHit], window_bp: int = 5000) -> dict[str, dict]:
    out: dict[str, dict] = {}
    cds = [f for f in features if f["type"] in {"cds", "gene"}]
    for hit in hits:
        key = f"{hit.query_id}:{hit.contig_id}:{hit.tstart}-{hit.tend}"
        overlapping = []
        flanking = []
        for feat in cds:
            if feat["seqid"] != hit.contig_id:
                continue
            if not intervals_overlap(feat["start"], feat["end"], hit.tstart, hit.tend):
                if abs(feat["start"] - hit.tend) <= window_bp or abs(hit.tstart - feat["end"]) <= window_bp:
                    flanking.append({"start": feat["start"], "end": feat["end"], "product": feat["product"], "type": feat["type"]})
                continue
            overlapping.append({"start": feat["start"], "end": feat["end"], "product": feat["product"], "type": feat["type"]})
        out[key] = {
            "overlapping_features": overlapping[:8],
            "flanking_features": flanking[:8],
            "reference_synteny_available": False,
        }
    return out

