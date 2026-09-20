"""Run the production DNA workflow with per-stage provenance.

Missing production tools are recorded as failures/unavailable dimensions.
Internal toy assemblers and internal QUAST substitutes are never used here.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from genome_skeptic.config import Settings, is_fast_pilot
from genome_skeptic.eval.production import assemble_with_spades
from genome_skeptic.models import ToolResult
from genome_skeptic.provenance import executable_version, sha256_file
from genome_skeptic.tools.annotation import run_annotation
from genome_skeptic.tools.base import available, run_command
from genome_skeptic.tools.checkm2 import run_checkm2
from genome_skeptic.tools.fastp import run_fastp
from genome_skeptic.tools.mapping import run_mapping


def _meminfo_kb() -> dict[str, int]:
    parsed: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        try:
            parsed[key] = int(rest.split()[0])
        except ValueError:
            continue
    return parsed


def select_fast_pilot_spades_resources(settings: Settings) -> tuple[int, int, dict]:
    """FAST_PILOT memory/threads. Does not change production isolate selection.

    Prefer ``-t 4 -m 8`` only when WSL has at least 12 GB. Otherwise the highest
    safe ``-m`` from live MemAvailable/MemTotal is used and reported. 6 GB is a
    target, not an invented allocation.
    """
    cpu = os.cpu_count() or 1
    prefer_t = max(1, int(settings.assembly.preferred_threads or 4))
    threads = 4 if cpu >= 4 else max(1, min(prefer_t, cpu))
    info: dict = {"profile": "fast_pilot", "nproc": cpu, "banner": settings.assembly.banner}
    try:
        raw = _meminfo_kb()
        total_kb = int(raw.get("MemTotal") or 0)
        avail_kb = int(raw.get("MemAvailable") or raw.get("MemFree") or 0)
        gib = 1024 * 1024
        total_gb = total_kb / gib
        avail_gb = avail_kb / gib
        safe = min(int(avail_gb) - 1, int(total_gb) - 1)
        if safe < 1:
            safe = max(1, int(avail_gb) if avail_gb >= 1 else 1)
        prefer_ram = float(settings.assembly.preferred_if_wsl_ram_gb or 12)
        prefer_m = int(settings.assembly.preferred_memory_gb or 8)
        min_m = int(settings.assembly.min_memory_gb or 6)
        used_preferred = False
        if total_gb >= prefer_ram and avail_gb >= (prefer_m + 2) and safe >= prefer_m:
            mem_gb = prefer_m
            threads = 4 if cpu >= 4 else max(1, cpu)
            used_preferred = True
        else:
            mem_gb = max(1, int(safe))
            if mem_gb < 5:
                threads = min(int(threads), 2)
        info.update({
            "mem_total_kb": total_kb,
            "mem_available_kb": avail_kb,
            "mem_total_gb": round(total_gb, 3),
            "mem_available_gb": round(avail_gb, 3),
            "highest_safe_memory_gb": int(safe),
            "min_memory_gb_requested": min_m,
            "preferred_memory_gb": prefer_m,
            "preferred_if_wsl_ram_gb": prefer_ram,
            "twelve_gb_available": bool(total_gb >= prefer_ram),
            "six_gb_safe": bool(safe >= min_m),
            "used_preferred_t4_m8": used_preferred,
            "selected_memory_gb": int(mem_gb),
            "selected_threads": int(threads),
            "note": (
                f"FAST_PILOT selected -t {threads} -m {mem_gb}. "
                + (
                    "Preferred -t 4 -m 8 because ≥12 GB was safely available to WSL."
                    if used_preferred
                    else (
                        f"12 GB was not safely available to WSL (MemTotal={total_gb:.2f} GB, "
                        f"MemAvailable={avail_gb:.2f} GB); 6 GB minimum was "
                        + ("safe" if safe >= min_m else "not safe")
                        + f"; using highest safe -m {mem_gb}"
                        + ("; threads capped at 2 because -m < 5 GB." if (not used_preferred and mem_gb < 5) else ".")
                    )
                )
            ),
        })
        return int(mem_gb), int(threads), info
    except Exception as exc:
        mem_gb = 3
        info.update({
            "error": str(exc),
            "selected_memory_gb": mem_gb,
            "selected_threads": threads,
            "fallback": True,
        })
        return mem_gb, threads, info


def select_spades_resources(settings: Settings) -> tuple[int, int, dict]:
    """Choose SPAdes ``-m`` / ``-t`` from live MemTotal and MemAvailable.

    Conservative: never exceed about MemAvailable-1 GB, never exceed 8 GB unless
    the VM actually has more than 8 GB. Does not change k-mer strategy. Extra
    threads raise peak RSS, so thread count stays at 2 unless the memory budget
    is at least 5 GB.
    """
    if is_fast_pilot(settings):
        return select_fast_pilot_spades_resources(settings)
    mem_gb = 4
    info: dict = {"fallback_memory_gb": mem_gb}
    try:
        raw = _meminfo_kb()
        total_kb = int(raw.get("MemTotal") or 0)
        avail_kb = int(raw.get("MemAvailable") or raw.get("MemFree") or 0)
        gib = 1024 * 1024
        total_gb = total_kb / gib
        avail_gb = avail_kb / gib
        hard_cap = 8 if total_gb < 9 else min(int(total_gb) - 1, 32)
        # int(avail)-1 turns 3.7 GiB into 2, which OOMs isolate K77. On a ~5 GB
        # WSL VM, 3 GB is the highest safe -m; 8 GB is impossible.
        from_avail = int(avail_gb) - 1
        if total_gb >= 4.5 and avail_gb >= 3.2:
            from_avail = max(from_avail, 3)
        from_total = int(total_gb) - 1
        candidate = min(hard_cap, from_total, from_avail)
        if candidate < 2:
            # Do not invent RAM. A 3.5 GB WSL VM cannot run -m 8.
            candidate = 2 if total_gb >= 2.5 and avail_gb >= 1.5 else max(1, int(avail_gb))
        mem_gb = max(1, int(candidate))
        info = {
            "mem_total_kb": total_kb,
            "mem_available_kb": avail_kb,
            "mem_total_gb": round(total_gb, 3),
            "mem_available_gb": round(avail_gb, 3),
            "hard_cap_gb": hard_cap,
            "selected_memory_gb": mem_gb,
            "eight_gb_possible": bool(total_gb >= 9 and avail_gb >= 9),
        }
    except Exception as exc:
        info = {"error": str(exc), "selected_memory_gb": mem_gb, "fallback": True}
    thread_cap = 2 if mem_gb < 5 else settings.project.threads
    threads = max(1, min(int(settings.project.threads), int(thread_cap)))
    info["selected_threads"] = threads
    return mem_gb, threads, info


def _checksum(path: Path | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    if p.is_file():
        return sha256_file(p)
    if p.is_dir():
        files = sorted(f for f in p.rglob("*") if f.is_file())
        if not files:
            return None
        h = hashlib.sha256()
        for f in files:
            h.update(str(f.relative_to(p)).encode())
            h.update(sha256_file(f).encode())
        return h.hexdigest()
    return None


def _stage(name: str, tool: str, cmd: list, result: ToolResult | None, inputs: dict, outputs: dict, t0: float, extra: dict | None = None) -> dict:
    in_sums = {k: _checksum(Path(v)) if v else None for k, v in inputs.items()}
    out_sums = {k: _checksum(Path(v)) if v else None for k, v in outputs.items()}
    evid = hashlib.sha256(f"{name}|{tool}|{in_sums}|{out_sums}".encode()).hexdigest()[:12]
    row = {
        "stage": name,
        "tool": tool,
        "version": executable_version(tool) if available(tool) else None,
        "command": cmd if cmd else (result.command if result else []),
        "exit_code": None if result is None else result.returncode,
        "ok": bool(result and result.ok),
        "error": None if result is None else result.error,
        "runtime_seconds": round(time.perf_counter() - t0, 3),
        "input_checksums": in_sums,
        "output_checksums": out_sums,
        "outputs": outputs,
        "parameters": extra or {},
        "evidence_ids": [f"E_PROD_{name}_{evid}"],
    }
    if result and result.metrics:
        row["metrics"] = result.metrics
    return row


def run_production_sequence(
    r1: Path,
    r2: Path | None,
    out_dir: Path,
    settings: Settings,
) -> dict:
    """FASTQ → FastQC → fastp → FastQC → SPAdes → QUAST → map → optional CheckM2/Bakta."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stages: list[dict] = []
    missing: list[str] = []
    failed: list[str] = []
    mem_gb, threads, resource_info = select_spades_resources(settings)
    asm_cfg = settings.assembly
    skip_fastqc = bool(asm_cfg.skip_fastqc)
    fastp_threads = 2 if is_fast_pilot(settings) and mem_gb < 5 else threads

    def need(exe: str, dimension: str) -> bool:
        if available(exe):
            return True
        missing.append(f"{dimension}: {exe} is not installed. Toy replacements were not used.")
        return False

    # FastQC before
    if skip_fastqc:
        stages.append(_stage(
            "fastqc_pre", "fastqc", [], None, {"r1": r1}, {}, time.perf_counter(),
            {"skipped": True, "reason": "FAST_PILOT runs fastp once; FastQC skipped"},
        ))
    elif need("fastqc", "qc_pre"):
        t0 = time.perf_counter()
        pre = out_dir / "fastqc_pre"
        cmd = ["fastqc", "--outdir", str(pre), str(r1)] + ([str(r2)] if r2 else [])
        res = run_command("fastqc", "qc_pre", cmd, pre)
        stages.append(_stage("fastqc_pre", "fastqc", cmd, res, {"r1": r1, "r2": r2}, {"dir": pre}, t0))
        if not res.ok:
            failed.append("fastqc_pre")
    else:
        stages.append(_stage("fastqc_pre", "fastqc", [], None, {"r1": r1}, {}, time.perf_counter(), {"unavailable": True}))

    clean_r1, clean_r2 = r1, r2
    if need("fastp", "qc_clean"):
        t0 = time.perf_counter()
        qc_dir = out_dir / "fastp"
        res = run_fastp(r1, r2, qc_dir, fastp_threads)
        outs = res.outputs or {}
        stages.append(_stage("fastp", "fastp", res.command, res, {"r1": r1, "r2": r2}, outs, t0))
        if res.ok and outs.get("clean_r1"):
            clean_r1 = Path(outs["clean_r1"])
            if outs.get("clean_r2"):
                clean_r2 = Path(outs["clean_r2"])
        else:
            failed.append("fastp")
            # Preserve the failure. Do not pretend reads were cleaned.
            clean_r1, clean_r2 = r1, r2
    else:
        stages.append(_stage("fastp", "fastp", [], None, {"r1": r1}, {}, time.perf_counter(), {"unavailable": True}))

    if skip_fastqc:
        stages.append(_stage(
            "fastqc_post", "fastqc", [], None, {"r1": clean_r1}, {}, time.perf_counter(),
            {"skipped": True, "reason": "FAST_PILOT runs fastp once; FastQC skipped"},
        ))
    elif need("fastqc", "qc_post"):
        t0 = time.perf_counter()
        post = out_dir / "fastqc_post"
        cmd = ["fastqc", "--outdir", str(post), str(clean_r1)] + ([str(clean_r2)] if clean_r2 else [])
        res = run_command("fastqc", "qc_post", cmd, post)
        stages.append(_stage("fastqc_post", "fastqc", cmd, res, {"r1": clean_r1, "r2": clean_r2}, {"dir": post}, t0))
        if not res.ok:
            failed.append("fastqc_post")

    assembly = None
    t0 = time.perf_counter()
    assembly, asm_info = assemble_with_spades(
        clean_r1, clean_r2, out_dir / "spades", threads, memory_gb=mem_gb,
        only_assembler=bool(asm_cfg.only_assembler),
        kmers=asm_cfg.kmers,
        careful=bool(asm_cfg.careful),
        isolate=bool(asm_cfg.isolate),
    )
    in_sums = {"r1": _checksum(clean_r1), "r2": _checksum(clean_r2)}
    spades_log = out_dir / "spades" / "spades.log"
    out_sums = {
        "contigs": _checksum(assembly) if assembly else None,
        "spades_log": _checksum(spades_log) if spades_log.exists() else None,
    }
    evid = hashlib.sha256(f"spades|{in_sums}|{out_sums}".encode()).hexdigest()[:12]
    if asm_cfg.only_assembler:
        mode = "only-assembler"
    elif asm_cfg.careful:
        mode = "careful"
    elif asm_cfg.isolate:
        mode = "isolate"
    else:
        mode = "default"
    stages.append({
        "stage": "spades",
        "tool": "spades.py",
        "version": executable_version("spades.py"),
        "command": asm_info.get("command") if isinstance(asm_info, dict) else [],
        "exit_code": 0 if assembly else 1,
        "ok": assembly is not None,
        "error": None if assembly else (asm_info or {}),
        "runtime_seconds": round(time.perf_counter() - t0, 3),
        "input_checksums": in_sums,
        "output_checksums": out_sums,
        "outputs": {
            "contigs": str(assembly) if assembly else None,
            "spades_log": str(spades_log) if spades_log.exists() else None,
        },
        "parameters": {
            "threads": threads,
            "mode": mode,
            "only_assembler": bool(asm_cfg.only_assembler),
            "kmers": asm_cfg.kmers,
            "careful": bool(asm_cfg.careful),
            "isolate": bool(asm_cfg.isolate),
            "intended_memory_gb": mem_gb,
            "resource_selection": resource_info,
            "fast_pilot": is_fast_pilot(settings),
        },
        "evidence_ids": [f"E_PROD_spades_{evid}"],
    })
    if assembly is None:
        failed.append("spades")
        return {
            "ok": False,
            "assembly": None,
            "mapping_sam": None,
            "mapping_bam": None,
            "depth_tsv": None,
            "gff": None,
            "proteins": None,
            "stages": stages,
            "missing": missing,
            "failed": failed,
            "spades_resources": resource_info,
        }

    if available("quast.py") or available("quast"):
        exe = "quast.py" if available("quast.py") else "quast"
        t0 = time.perf_counter()
        qdir = out_dir / "quast"
        cmd = [exe, str(assembly), "-o", str(qdir), "-t", str(threads)]
        res = run_command("quast", "assembly_qc", cmd, qdir)
        stages.append(_stage("quast", exe, cmd, res, {"contigs": assembly}, {"dir": qdir}, t0))
        if not res.ok:
            failed.append("quast")
    else:
        missing.append("quast: not installed. Internal FASTA stats were not substituted as QUAST.")
        stages.append(_stage("quast", "quast.py", [], None, {"contigs": assembly}, {}, time.perf_counter(), {"unavailable": True}))

    mapping_sam = None
    mapping_bam = None
    depth_tsv = None
    if available("minimap2") and available("samtools"):
        t0 = time.perf_counter()
        mdir = out_dir / "mapping"
        res = run_mapping(assembly, clean_r1, clean_r2, mdir, threads)
        stages.append(_stage("mapping", "minimap2", res.command, res, {"contigs": assembly, "r1": clean_r1}, res.outputs or {}, t0))
        if res.ok:
            mapping_bam = Path(res.outputs["bam"]) if res.outputs.get("bam") else None
            # Convert BAM to SAM if locus pipeline expects SAM
            if mapping_bam and mapping_bam.exists():
                sam = mdir / "mapped.sam"
                conv = run_command("samtools", "mapping", ["samtools", "view", "-h", "-o", str(sam), str(mapping_bam)], mdir)
                if conv.ok:
                    mapping_sam = sam
                depth_cand = mdir / "depth.tsv"
                if depth_cand.exists():
                    depth_tsv = depth_cand
        else:
            failed.append("mapping")
    else:
        missing.append("minimap2/samtools: mapping dimension unavailable.")
        stages.append(_stage("mapping", "minimap2", [], None, {"contigs": assembly}, {}, time.perf_counter(), {"unavailable": True}))

    gff = None
    proteins = None
    if available("checkm2") and settings.paths.checkm2_db:
        t0 = time.perf_counter()
        res = run_checkm2(assembly, out_dir / "checkm2", threads, settings.paths.checkm2_db)
        stages.append(_stage("checkm2", "checkm2", res.command, res, {"contigs": assembly}, res.outputs or {}, t0, {"database": settings.paths.checkm2_db}))
        if not res.ok:
            failed.append("checkm2")
    else:
        missing.append("checkm2: executable or database missing; completeness not treated as measured.")
        stages.append(_stage("checkm2", "checkm2", [], None, {"contigs": assembly}, {}, time.perf_counter(), {"unavailable": True}))

    if available("bakta") and settings.paths.bakta_db:
        t0 = time.perf_counter()
        res = run_annotation(assembly, out_dir / "bakta", threads, settings.paths.bakta_db)
        stages.append(_stage("bakta", "bakta", res.command, res, {"contigs": assembly}, res.outputs or {}, t0, {"database": settings.paths.bakta_db}))
        if res.ok:
            gff = Path(res.outputs["gff"]) if res.outputs.get("gff") else None
            proteins = Path(res.outputs["proteins"]) if res.outputs.get("proteins") else None
        else:
            failed.append("bakta")
    else:
        missing.append("bakta: executable or database missing; annotation not treated as measured.")
        stages.append(_stage("bakta", "bakta", [], None, {"contigs": assembly}, {}, time.perf_counter(), {"unavailable": True}))

    return {
        "ok": True,
        "assembly": str(assembly),
        "mapping_sam": str(mapping_sam) if mapping_sam else None,
        "mapping_bam": str(mapping_bam) if mapping_bam else None,
        "depth_tsv": str(depth_tsv) if depth_tsv else None,
        "gff": str(gff) if gff else None,
        "proteins": str(proteins) if proteins else None,
        "clean_r1": str(clean_r1),
        "clean_r2": str(clean_r2) if clean_r2 else None,
        "stages": stages,
        "missing": missing,
        "failed": failed,
        "spades_resources": resource_info,
    }
