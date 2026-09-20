from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from genome_skeptic.models import ToolResult
from genome_skeptic.provenance import executable_version


def available(executable: str) -> bool:
    return shutil.which(executable) is not None


def run_command(name: str, stage: str, cmd: list[str], out_dir: Path, env: dict | None = None) -> ToolResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = out_dir / f"{name}.stdout.log"
    stderr_path = out_dir / f"{name}.stderr.log"
    try:
        with stdout_path.open("w") as out, stderr_path.open("w") as err:
            p = subprocess.run(cmd, stdout=out, stderr=err, text=True, env=env)
        return ToolResult(
            name=name,
            stage=stage,
            ok=p.returncode == 0,
            returncode=p.returncode,
            command=cmd,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            metrics={"version": executable_version(cmd[0])},
            error=None if p.returncode == 0 else f"{name} exited with code {p.returncode}",
        )
    except Exception as exc:
        return ToolResult(
            name=name,
            stage=stage,
            ok=False,
            returncode=-1,
            command=cmd,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            error=str(exc),
        )
