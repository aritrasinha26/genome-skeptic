"""Production-stack inventory, smoke tests, and environment manifests.

An executable on PATH is not operational until a tiny valid-input smoke test
succeeds. Database-backed tools are not operational without a configured
database. Missing tools are reported; they are never replaced by toy code.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from genome_skeptic.provenance import executable_version, sha256_file
from genome_skeptic.tools.base import available, run_command

STACK_TOOLS = (
    "fastp", "fastqc", "spades.py", "quast.py", "minimap2", "samtools",
    "mmseqs", "diamond", "hmmsearch", "wgsim", "FastTree",
    "bakta", "checkm2", "kraken2", "sourmash",
)

DB_REQUIRED = {
    "bakta": True,
    "checkm2": True,
    "kraken2": True,
    "sourmash": True,
}


def _db_paths(settings=None) -> dict[str, str | None]:
    bakta = os.environ.get("BAKTA_DB")
    checkm = os.environ.get("CHECKM2DB")
    tax = os.environ.get("GENOME_SKEPTIC_TAXONOMY_DB")
    if settings is not None:
        bakta = bakta or settings.paths.bakta_db
        checkm = checkm or settings.paths.checkm2_db
        tax = tax or settings.paths.taxonomy_db
    return {"bakta": bakta, "checkm2": checkm, "kraken2": tax, "sourmash": tax}


def _db_ready(name: str, path: str | None) -> bool:
    if not path:
        return False
    p = Path(path)
    if not p.exists():
        return False
    if p.is_file():
        return p.stat().st_size > 0
    return any(p.iterdir())


def _db_provenance(path: str | None) -> dict:
    if not path:
        return {"path": None, "present": False}
    p = Path(path)
    meta = {"path": str(p), "present": p.exists()}
    prov = p / f"{p.name}_provenance.json" if p.is_dir() else p.with_suffix(p.suffix + ".provenance.json")
    alt = p.parent / f"{p.name}_provenance.json"
    for cand in (prov, alt, p / "download_provenance.json"):
        if cand.exists():
            try:
                meta.update(json.loads(cand.read_text()))
            except Exception:
                pass
            break
    if p.exists() and p.is_file():
        meta["checksum_sha256"] = sha256_file(p)
        meta["bytes"] = p.stat().st_size
    return meta


def inspect_tool(name: str, *, settings=None, smoke: dict | None = None) -> dict:
    path = shutil.which(name)
    version = executable_version(name) if path else None
    db_required = DB_REQUIRED.get(name, False)
    dbs = _db_paths(settings)
    db_path = dbs.get(name)
    db_ok = _db_ready(name, db_path) if db_required else True
    smoke_row = (smoke or {}).get(name) or {}
    available_exe = bool(path)
    operational = bool(available_exe and db_ok and smoke_row.get("ok"))
    if smoke is None:
        operational = False
    notes = []
    if not available_exe:
        notes.append("executable not on PATH; toy replacements were not used.")
    elif smoke is None:
        notes.append("smoke tests were not run; executable presence is not treated as operational.")
    elif not smoke_row.get("ok"):
        notes.append(smoke_row.get("error") or "smoke test did not pass")
    if db_required and not db_ok:
        notes.append("database not configured; this dimension remains unavailable.")
    return {
        "name": name,
        "version": version,
        "executable_path": path,
        "available": available_exe,
        "database_required": db_required,
        "database_path": db_path,
        "database_version": (_db_provenance(db_path).get("version") or _db_provenance(db_path).get("download_date")),
        "database_checksum_or_provenance": _db_provenance(db_path) if db_required else None,
        "database_present": db_ok if db_required else None,
        "operational": operational,
        "smoke": smoke_row or None,
        "notes": " ".join(notes) if notes else None,
    }


def _tiny_fasta(path: Path) -> Path:
    # Long enough for a tiny SPAdes assembly that QUAST can score.
    seq = (
        "ATGAAATTTGGTTGGTTCGGTTGGAAAGGTTGGAAACCGTGGAAAGGTATGCCGTGGTTC"
        "GGTAAAGGTTGGTTCAAAGGTAAAGCTGCTGCTGCTGCTGTTGGTGGTGGTGGTAAATAA"
    )
    path.write_text(f">tiny\n{seq * 40}\n")
    return path


def _tiny_fastq(r1: Path, r2: Path, fasta: Path) -> None:
    from genome_skeptic.eval.simulate import simulate_paired_internal
    simulate_paired_internal(
        fasta, r1, r2, coverage=20, read_len=50, insert=120,
        error_rate=0.0, seed=1, quality=35,
    )


def run_all_smoke_tests(work: Path) -> dict[str, dict]:
    work.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    fasta = _tiny_fasta(work / "tiny.fa")
    r1, r2 = work / "t_R1.fastq", work / "t_R2.fastq"
    _tiny_fastq(r1, r2, fasta)

    def record(name: str, ran: bool, ok: bool, error: str | None = None, extra: dict | None = None):
        if error is None or "exited with code" in str(error):
            # Prefer a tail of the tool log when the wrapper error is generic.
            pass
        results[name] = {"ran": ran, "ok": ok, "error": error, **(extra or {})}

    def fail_text(res) -> str | None:
        if res.ok:
            return None
        parts = [res.error] if res.error else []
        for p in (res.stderr_path, res.stdout_path):
            if not p:
                continue
            path = Path(p)
            if path.exists():
                tail = path.read_text(errors="replace").strip().splitlines()
                if tail:
                    parts.append(tail[-1][:300])
        return " | ".join(parts) if parts else "failed"

    if available("wgsim"):
        out = work / "wgsim"
        out.mkdir(exist_ok=True)
        cmd = ["wgsim", "-N", "40", "-1", "50", "-2", "50", str(fasta), str(out / "a.fq"), str(out / "b.fq")]
        res = run_command("wgsim", "smoke", cmd, out)
        record("wgsim", True, res.ok and (out / "a.fq").exists(), res.error)
    else:
        record("wgsim", False, False, "not installed")

    if available("fastp"):
        out = work / "fastp"
        cmd = ["fastp", "-i", str(r1), "-I", str(r2), "-o", str(out / "c1.fq"), "-O", str(out / "c2.fq"),
               "-j", str(out / "fastp.json"), "-h", str(out / "fastp.html")]
        res = run_command("fastp", "smoke", cmd, out)
        record("fastp", True, res.ok and (out / "c1.fq").exists(), res.error)
    else:
        record("fastp", False, False, "not installed")

    if available("fastqc"):
        out = work / "fastqc"
        res = run_command("fastqc", "smoke", ["fastqc", "--outdir", str(out), str(r1)], out)
        html = list(out.glob("*fastqc.html"))
        record("fastqc", True, res.ok and bool(html), res.error)
    else:
        record("fastqc", False, False, "not installed")

    contigs = None
    if available("spades.py"):
        out = work / "spades"
        cmd = ["spades.py", "-1", str(r1), "-2", str(r2), "-o", str(out), "-t", "1", "-m", "2", "--only-assembler"]
        res = run_command("spades", "smoke", cmd, out)
        for cand in (out / "contigs.fasta", out / "scaffolds.fasta"):
            if cand.exists() and cand.stat().st_size > 0:
                contigs = cand
                break
        record("spades.py", True, res.ok and contigs is not None, res.error, {"contigs": str(contigs) if contigs else None})
    else:
        record("spades.py", False, False, "not installed")

    if available("quast.py") or available("quast"):
        exe = "quast.py" if available("quast.py") else "quast"
        if contigs is None:
            record("quast.py", True, False, "no SPAdes contigs to QC; not substituting internal stats as QUAST")
        else:
            out = work / "quast"
            res = run_command("quast", "smoke", [
                exe, str(contigs), "-o", str(out), "-t", "1", "--min-contig", "100",
            ], out)
            record("quast.py", True, res.ok and bool(list(out.glob("report.*"))), res.error)
    else:
        record("quast.py", False, False, "not installed")

    if available("minimap2") and available("samtools") and contigs is not None:
        out = work / "map"
        out.mkdir(exist_ok=True)
        sam = out / "map.sam"
        bam = out / "map.bam"
        res = run_command("minimap2", "smoke", ["minimap2", "-ax", "sr", "-o", str(sam), str(contigs), str(r1), str(r2)], out)
        if res.ok:
            s1 = run_command("samtools", "smoke", ["samtools", "view", "-b", str(sam), "-o", str(out / "u.bam")], out)
            s2 = run_command("samtools", "smoke", ["samtools", "sort", str(out / "u.bam"), "-o", str(bam)], out)
            s3 = run_command("samtools", "smoke", ["samtools", "index", str(bam)], out)
            ok = s1.ok and s2.ok and s3.ok
            record("minimap2", True, ok, None if ok else "mapping/index pipeline failed")
            record("samtools", True, ok, None if ok else "mapping/index pipeline failed")
        else:
            record("minimap2", True, False, res.error)
            record("samtools", True, False, res.error)
    else:
        if "minimap2" not in results:
            record("minimap2", False, False, "not installed or no contigs")
        if "samtools" not in results:
            record("samtools", False, False, "not installed or no contigs")

    if available("mmseqs"):
        out = work / "mmseqs"
        out.mkdir(exist_ok=True)
        res = run_command("mmseqs", "smoke", [
            "mmseqs", "easy-search", str(fasta), str(fasta), str(out / "hits.m8"), str(out / "tmp"),
            "--threads", "1", "--search-type", "3", "--split-memory-limit", "512M", "-s", "1",
        ], out)
        record("mmseqs", True, res.ok and (out / "hits.m8").exists(), fail_text(res))
    else:
        record("mmseqs", False, False, "not installed")

    if available("diamond"):
        out = work / "diamond"
        out.mkdir(exist_ok=True)
        makedb = run_command("diamond", "smoke", ["diamond", "makedb", "--in", str(fasta), "-d", str(out / "db")], out)
        if makedb.ok:
            res = run_command("diamond", "smoke", [
                "diamond", "blastx", "-d", str(out / "db"), "-q", str(fasta), "-o", str(out / "hits.m8"),
            ], out)
            record("diamond", True, res.ok, res.error)
        else:
            record("diamond", True, False, makedb.error)
    else:
        record("diamond", False, False, "not installed")

    if available("hmmsearch") and available("hmmbuild"):
        out = work / "hmmer"
        out.mkdir(exist_ok=True)
        sto = out / "tiny.sto"
        seq = fasta.read_text().splitlines()[1]
        sto.write_text(f"# STOCKHOLM 1.0\ntiny1             {seq[:60]}\ntiny2             {seq[:60]}\n//\n")
        hmm = out / "tiny.hmm"
        b = run_command("hmmbuild", "smoke", ["hmmbuild", str(hmm), str(sto)], out)
        if b.ok:
            res = run_command("hmmsearch", "smoke", ["hmmsearch", str(hmm), str(fasta)], out)
            record("hmmsearch", True, res.ok, res.error)
        else:
            record("hmmsearch", True, False, b.error)
    else:
        record("hmmsearch", False, False, "not installed")

    if available("FastTree"):
        out = work / "fasttree"
        out.mkdir(exist_ok=True)
        aln = out / "tiny.fa"
        seq = fasta.read_text().splitlines()[1][:80]
        aln.write_text(f">a\n{seq}\n>b\n{seq}\n>c\n{seq}\n")
        res = run_command("FastTree", "smoke", ["FastTree", str(aln)], out)
        record("FastTree", True, res.ok, res.error)
    else:
        record("FastTree", False, False, "not installed")

    for name in ("bakta", "checkm2", "kraken2", "sourmash"):
        if not available(name):
            record(name, False, False, "not installed")
            continue
        dbs = _db_paths()
        if not _db_ready(name, dbs.get(name)):
            record(name, False, False, "database not configured; not treated as operational")
        else:
            record(name, False, False, "database present; full functional test deferred to production cases")
    return results


def build_production_stack(*, settings=None, smoke: dict | None = None) -> dict:
    tools = [inspect_tool(name, settings=settings, smoke=smoke) for name in STACK_TOOLS]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "tools": tools,
        "operational_count": sum(1 for t in tools if t["operational"]),
        "available_count": sum(1 for t in tools if t["available"]),
        "note": "operational requires a passing smoke test (and a database when required). Toy replacements are never used.",
    }


def write_production_stack(path: Path, *, settings=None, smoke: dict | None = None) -> dict:
    payload = build_production_stack(settings=settings, smoke=smoke)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return payload


def write_environment_manifest(path: Path) -> dict:
    tools = []
    for name in STACK_TOOLS + ("hmmbuild", "prodigal"):
        tools.append({
            "name": name,
            "path": shutil.which(name),
            "version": executable_version(name) if shutil.which(name) else None,
        })
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "conda_prefix": os.environ.get("CONDA_PREFIX"),
        "docker_env": os.environ.get("GENOME_SKEPTIC_ENV"),
        "tools": tools,
    }
    path.write_text(json.dumps(payload, indent=2))
    return payload
