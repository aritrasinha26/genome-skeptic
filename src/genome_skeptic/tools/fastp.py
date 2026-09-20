from __future__ import annotations

import json
from pathlib import Path

from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def run_fastp(r1: Path, r2: Path | None, out_dir: Path, threads: int) -> ToolResult:
    if not available("fastp"):
        return ToolResult(name="fastp", stage="qc_clean", ok=False, error="fastp not found")
    clean_r1 = out_dir / "clean_R1.fastq.gz"
    clean_r2 = out_dir / "clean_R2.fastq.gz"
    json_path = out_dir / "fastp.json"
    html_path = out_dir / "fastp.html"
    cmd = ["fastp", "-i", str(r1), "-o", str(clean_r1), "-w", str(threads), "-j", str(json_path), "-h", str(html_path)]
    if r2:
        cmd += ["-I", str(r2), "-O", str(clean_r2), "--detect_adapter_for_pe"]
    result = run_command("fastp", "qc_clean", cmd, out_dir)
    if result.ok and json_path.exists():
        raw = json.loads(json_path.read_text())
        before = raw.get("summary", {}).get("before_filtering", {})
        after = raw.get("summary", {}).get("after_filtering", {})
        result.metrics.update({
            "before_total_reads": before.get("total_reads"),
            "after_total_reads": after.get("total_reads"),
            "before_total_bases": before.get("total_bases"),
            "after_total_bases": after.get("total_bases"),
            "q20_rate": after.get("q20_rate"),
            "q30_rate": after.get("q30_rate"),
            "gc_content": after.get("gc_content"),
            "read1_mean_length": after.get("read1_mean_length"),
            "read2_mean_length": after.get("read2_mean_length"),
        })
        result.outputs = {
            "clean_r1": str(clean_r1),
            "fastp_json": str(json_path),
            "fastp_html": str(html_path),
        }
        if r2:
            result.outputs["clean_r2"] = str(clean_r2)
    return result
