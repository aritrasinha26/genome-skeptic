#!/usr/bin/env python3
from pathlib import Path
from genome_skeptic.config import load_settings
from genome_skeptic.eval.evaluate_real import evaluate_real_genomes

ROOT = Path(__file__).resolve().parents[1]
settings = load_settings(ROOT / "config" / "fast_pilot.yaml")
print("start hel_02 only", flush=True)
r = evaluate_real_genomes(
    ROOT / "benchmarks/real_genomes_fast_pilot_held/agent_visible",
    ROOT / "benchmarks/real_genomes_fast_pilot_held/hidden/truth.yaml",
    ROOT / "benchmarks/orthology_v3/analysis_held",
    settings=settings,
    run_ablations=False,
    reuse_assembly=True,
    write_fast_pilot_report=False,
    print_prescore_table=True,
    split="held_out",
    reuse_assembly_from=ROOT / "benchmarks/real_genomes_fast_pilot_held_eval",
    only_cases=["hel_02"],
)
print("ok", (r.get("systems") or {}).get("genome_skeptic", {}).get("overall"), flush=True)
