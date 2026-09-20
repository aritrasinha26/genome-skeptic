from __future__ import annotations

import re
import subprocess
from pathlib import Path

from genome_skeptic.models import ToolResult
from genome_skeptic.tools.base import available, run_command


def run_mapping(contigs: Path, r1: Path, r2: Path | None, out_dir: Path, threads: int) -> ToolResult:
    if not available("minimap2") or not available("samtools"):
        return ToolResult(name="read_mapping", stage="mapping", ok=False, error="minimap2 and samtools are required")
    out_dir.mkdir(parents=True, exist_ok=True)
    bam = out_dir / "reads_to_assembly.bam"
    stderr_path = out_dir / "mapping.stderr.log"
    mm_cmd = ["minimap2", "-ax", "sr", "-t", str(threads), str(contigs), str(r1)]
    if r2:
        mm_cmd.append(str(r2))
    sort_cmd = ["samtools", "sort", "-@", str(threads), "-o", str(bam)]
    try:
        with stderr_path.open("w") as err:
            p1 = subprocess.Popen(mm_cmd, stdout=subprocess.PIPE, stderr=err)
            p2 = subprocess.Popen(sort_cmd, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=err)
            if p1.stdout:
                p1.stdout.close()
            p2.communicate()
            rc1 = p1.wait()
            rc2 = p2.returncode
        if rc1 != 0 or rc2 != 0 or not bam.exists():
            return ToolResult(name="read_mapping", stage="mapping", ok=False, returncode=max(rc1, rc2), command=mm_cmd + ["|", *sort_cmd], stderr_path=str(stderr_path), error="mapping pipeline failed")
        subprocess.run(["samtools", "index", str(bam)], check=True)
        flagstat = subprocess.run(["samtools", "flagstat", str(bam)], capture_output=True, text=True, check=True).stdout
        mapped_match = re.search(r"(\d+) \+ \d+ mapped \(([0-9.]+)%", flagstat)
        mapping_rate = float(mapped_match.group(2)) / 100 if mapped_match else None
        depth_path = out_dir / "depth.tsv"
        with depth_path.open("w") as depth_out:
            subprocess.run(["samtools", "depth", "-a", str(bam)], stdout=depth_out, text=True, check=True)
        n = 0
        s = 0.0
        s2 = 0.0
        zero = 0
        with depth_path.open() as fh:
            for line in fh:
                try:
                    d = float(line.rstrip().split("\t")[2])
                except Exception:
                    continue
                n += 1
                s += d
                s2 += d * d
                if d == 0:
                    zero += 1
        mean = s / n if n else 0.0
        variance = max(0.0, s2 / n - mean * mean) if n else 0.0
        sd = variance ** 0.5
        cv = sd / mean if mean else None
        return ToolResult(
            name="read_mapping",
            stage="mapping",
            ok=True,
            command=mm_cmd + ["|", *sort_cmd],
            outputs={"bam": str(bam), "depth": str(depth_path)},
            metrics={
                "mapping_rate": mapping_rate,
                "mean_depth": mean,
                "depth_cv": cv,
                "zero_coverage_fraction": zero / n if n else None,
            },
        )
    except Exception as exc:
        return ToolResult(name="read_mapping", stage="mapping", ok=False, command=mm_cmd + ["|", *sort_cmd], stderr_path=str(stderr_path), error=str(exc))
