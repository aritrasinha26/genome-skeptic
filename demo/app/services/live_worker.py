"""Subprocess entry point for one live Genome Skeptic analysis.

Runs in its own process so the Streamlit server can enforce a wall-clock limit
and never shares interpreter state with the pipeline. Invokes the same V4.1
arm functions as ``scripts/run_m60_position.py``; nothing biological is
reimplemented here.

    python -m demo.app.services.live_worker --assembly A.fna --target rpoB_RNAP_beta \
        --arm GS_DETERMINISTIC_V4_1 --out WORKDIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

SUPPORTED_TARGETS = ("tetA_tetracycline_efflux", "rpoB_RNAP_beta")
ARMS = ("GS_DETERMINISTIC_V4_1", "GS_EXHAUSTIVE_V4_1", "GS_AGENTIC_V4_1")
AGENTIC_CONFIG = ROOT / "config" / "qwen_agentic_dev.yaml"
AGENTIC_URL_ENV = "GS_DEMO_AGENTIC_BASE_URL"


_DROP_KEYS = {"url", "base_url", "api_key", "config", "command", "output_file", "response_id"}


def scrub(obj, tmp_root: str):
    """Remove endpoint/credential fields and server paths from a payload returned to the browser."""
    if isinstance(obj, dict):
        return {k: scrub(v, tmp_root) for k, v in obj.items() if k not in _DROP_KEYS}
    if isinstance(obj, list):
        return [scrub(v, tmp_root) for v in obj]
    if isinstance(obj, str):
        out = obj.replace(tmp_root, "<work>")
        return out.replace(str(ROOT), "<app>")
    return obj


def write_target_fa(dest: Path, target: str) -> None:
    """Same query construction as scripts/run_m60_position.py:write_target_fa."""
    from genome_skeptic.families import load_family

    fam = load_family(target)
    if fam is None or not fam.members:
        raise RuntimeError(f"missing curated family {target}")
    member = max(fam.members, key=lambda m: len(m.sequence or ""))
    dest.write_text(
        f">{target} target_type=gene_orthologue family={target} length_aa={len(member.sequence or '')}\n"
        f"{member.sequence}\n",
        encoding="utf-8",
    )


def settings_for(arm: str):
    from genome_skeptic.config import Settings, load_settings

    if arm != "GS_AGENTIC_V4_1":
        s = Settings()
        s.llm.enabled = False
        return s
    base_url = os.environ.get(AGENTIC_URL_ENV, "").strip()
    if not base_url:
        raise RuntimeError(f"agentic arm requires {AGENTIC_URL_ENV}")
    s = load_settings(AGENTIC_CONFIG)
    for cfg in (s.llm, s.llm.planner, s.llm.critic):
        if cfg is not None:
            cfg.base_url = base_url
    return s


def run(assembly: Path, target: str, arm: str, out: Path) -> dict:
    from genome_skeptic.manuscript.arms import (
        run_gs_agentic_v4_1,
        run_gs_deterministic_v4_1,
        run_gs_exhaustive_v4_1,
    )
    from demo.app.services.core_check import compare_with_frozen

    runners = {
        "GS_DETERMINISTIC_V4_1": run_gs_deterministic_v4_1,
        "GS_EXHAUSTIVE_V4_1": run_gs_exhaustive_v4_1,
        "GS_AGENTIC_V4_1": run_gs_agentic_v4_1,
    }
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    target_fa = work / "target.fa"
    write_target_fa(target_fa, target)
    refs = out / "references.yaml"
    refs.write_text("references: []\n", encoding="utf-8")
    settings = settings_for(arm)
    core = compare_with_frozen()
    t0 = time.perf_counter()
    claims, _loci, provenance = runners[arm](
        assembly, target_fa, work, settings, references=refs, declared_organism=None, query_ids=[target]
    )
    seconds = round(time.perf_counter() - t0, 3)
    claim = claims[0].model_dump(mode="json") if claims else None

    def maybe(name: str):
        p = work / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    return {
        "ok": provenance.get("final_validator_ran") is True and not provenance.get("agent_failure"),
        "arm": arm,
        "target": target,
        "runtime_seconds": seconds,
        "core_check": core,
        "model": settings.llm.model if arm == "GS_AGENTIC_V4_1" else None,
        "record": {
            "provenance": provenance,
            "claim": claim,
            "evidence": maybe("evidence.json") or [],
            "planner_decision": maybe("planner_decision.json"),
            "critic_review": maybe("critic_review.json"),
            "model_call_log": maybe("call_log.json") or [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assembly", required=True, type=Path)
    ap.add_argument("--target", required=True, choices=SUPPORTED_TARGETS)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    result_path = args.out / "result.json"
    try:
        result = scrub(run(args.assembly, args.target, args.arm, args.out), str(args.out))
    except Exception as exc:  # reported to the UI as a short message; details stay in the temp dir
        import traceback

        (args.out / "worker_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        result = {"ok": False, "arm": args.arm, "target": args.target, "error": scrub(f"{type(exc).__name__}: {exc}"[:500], str(args.out))}
    result_path.write_text(json.dumps(result, default=str), encoding="utf-8")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
