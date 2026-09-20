from __future__ import annotations

import csv
import os
from pathlib import Path

from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def run_checkm2(contigs: Path, out_dir: Path, threads: int, db_path: str | None = None) -> ToolResult:
    if not available("checkm2"):
        return ToolResult(name="checkm2", stage="completeness", ok=False, error="checkm2 not found")
    cmd = ["checkm2", "predict", "--threads", str(threads), "--input", str(contigs), "--output-directory", str(out_dir)]
    env = os.environ.copy()
    if db_path:
        env["CHECKM2DB"] = db_path
    result = run_command("checkm2", "completeness", cmd, out_dir, env=env)
    report = out_dir / "quality_report.tsv"
    if result.ok and report.exists():
        with report.open() as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        if rows:
            row = rows[0]
            def f(key: str):
                try:
                    return float(row.get(key, ""))
                except Exception:
                    return None
            result.metrics.update({
                "completeness": f("Completeness"),
                "contamination": f("Contamination"),
            })
            result.outputs["quality_report"] = str(report)
    return result
