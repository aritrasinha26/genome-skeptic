from __future__ import annotations

import json
from pathlib import Path

import requests
import typer

from genome_skeptic.config import load_settings
from genome_skeptic.orchestrator import GenomeOrchestrator

app = typer.Typer(no_args_is_help=True, help="Agentic bacterial genome assembly and annotation with adversarial validation.")


@app.command()
def doctor(
    config: Path = typer.Option(None, exists=True, dir_okay=False),
    out: Path | None = typer.Option(None, help="Write production_stack.json here."),
    smoke: bool = typer.Option(False, help="Run tiny valid-input smoke tests before marking tools operational."),
):
    """Check local tools and emit a machine-readable production-stack manifest."""
    settings = load_settings(config)
    from genome_skeptic.eval.stack import run_all_smoke_tests, write_environment_manifest, write_production_stack
    smoke_rows = None
    if smoke:
        work = (out.parent if out else Path(".")) / "smoke_work"
        smoke_rows = run_all_smoke_tests(work)
    dest = out or Path("production_stack.json")
    payload = write_production_stack(dest, settings=settings, smoke=smoke_rows)
    write_environment_manifest(dest.parent / "environment_manifest.json")
    for t in payload["tools"]:
        flag = "OPERATIONAL" if t["operational"] else ("PRESENT" if t["available"] else "MISSING")
        extra = t.get("version") or t.get("executable_path") or ""
        typer.echo(f"{t['name']:12} {flag:12} {extra}")
        if t["database_required"] and not t.get("database_present"):
            typer.echo(f"{'':12} database not configured; this dimension remains unavailable.")
    if settings.llm.enabled:
        try:
            url = settings.llm.base_url.rstrip("/") + "/api/tags"
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            models = [m.get("name") for m in r.json().get("models", [])]
            typer.echo(f"Ollama       OK at {settings.llm.base_url}")
            typer.echo(f"Model        {'FOUND' if settings.llm.model in models else 'NOT FOUND'}: {settings.llm.model}")
        except Exception as exc:
            typer.echo(f"Ollama       UNAVAILABLE: {exc}")
    typer.echo(f"manifest     {dest}")


@app.command()
def run(
    r1: Path = typer.Option(..., exists=True, dir_okay=False),
    r2: Path | None = typer.Option(None, exists=True, dir_okay=False),
    out: Path = typer.Option(..., file_okay=False),
    config: Path | None = typer.Option(None, exists=True, dir_okay=False),
    targets: Path | None = typer.Option(None, exists=True, dir_okay=False, help="Optional FASTA of target genes for presence/non-detection reasoning."),
    references: Path | None = typer.Option(None, exists=True, dir_okay=False, help="Optional YAML of trusted related/reference genomes for locus validation."),
    organism: str | None = typer.Option(None, help="Optional declared organism identity supplied by the user, not measured taxonomy."),
    dry_run: bool = typer.Option(False, help="Validate inputs and show planned stages without running external tools."),
):
    """Run the DNA-only bacterial isolate workflow."""
    settings = load_settings(config)
    orchestrator = GenomeOrchestrator(settings, out)
    state = orchestrator.run(r1, r2, dry_run=dry_run, targets=targets, references=references, declared_organism=organism)
    typer.echo(json.dumps({
        "run_id": state.run_id,
        "stopped": state.stopped,
        "stop_reason": state.stop_reason,
        "report": str(out / "report.md"),
        "state": str(out / "run_state.json"),
    }, indent=2))


@app.command()
def evaluate(
    cases: Path = typer.Option(..., exists=True, file_okay=False, help="Directory of agent-visible benchmark cases."),
    truth: Path = typer.Option(..., exists=True, dir_okay=False, help="Hidden ground-truth manifest used only after claims are produced."),
    out: Path = typer.Option(..., file_okay=False),
    config: Path | None = typer.Option(None, exists=True, dir_okay=False),
):
    """Score target-gene reasoning against a hidden truth manifest. Separate from unit tests."""
    from genome_skeptic.eval.harness import evaluate_benchmark

    settings = load_settings(config)
    report = evaluate_benchmark(cases, truth, out, settings)
    typer.echo(json.dumps(report.as_json(), indent=2))


@app.command("generate-realworld")
def generate_realworld(out: Path = typer.Option(..., file_okay=False)):
    """Write isolated agent-visible FASTQ cases and a hidden truth manifest."""
    from genome_skeptic.eval.generate import write_realworld_benchmark

    root = write_realworld_benchmark(out)
    typer.echo(str(root / "agent_visible"))
    typer.echo(str(root / "hidden" / "truth.yaml"))


@app.command("generate-real-genomes")
def generate_real_genomes_cmd(
    out: Path = typer.Option(..., file_okay=False),
    split: str = typer.Option("development", help="development or held_out"),
    cache: Path = typer.Option(None, help="Directory for hidden downloaded genomes."),
    config: Path | None = typer.Option(None, exists=True, dir_okay=False),
    fast_pilot: bool = typer.Option(False, help="Use the FAST_PILOT 3+3 genome set and 25x clean coverage. Does not overwrite production cases."),
):
    """Download hidden RefSeq genomes and write isolated FASTQ cases."""
    from genome_skeptic.config import is_fast_pilot
    from genome_skeptic.eval.catalog import genomes_for
    from genome_skeptic.eval.fetch import fetch_genome
    from genome_skeptic.eval.real_genomes import write_real_genome_benchmark

    settings = load_settings(config)
    profile = "fast_pilot" if (fast_pilot or is_fast_pilot(settings)) else "production"
    cache_dir = cache or (out / "hidden" / "genomes")
    loaded = []
    failed = []
    for spec in genomes_for(split, profile=profile):
        meta = fetch_genome(spec, cache_dir / spec.genome_id)
        if meta.get("ok"):
            loaded.append((spec, Path(meta["fasta"]), meta))
        else:
            failed.append(meta)
    if not loaded:
        typer.echo(json.dumps({"ok": False, "failed": failed}, indent=2))
        raise typer.Exit(1)
    summary = write_real_genome_benchmark(out, loaded, split=split, profile=profile)
    summary["failed_downloads"] = failed
    typer.echo(json.dumps(summary, indent=2))


@app.command("evaluate-real-genomes")
def evaluate_real_genomes_cmd(
    visible: Path = typer.Option(..., exists=True, file_okay=False),
    truth: Path = typer.Option(..., exists=True, dir_okay=False),
    out: Path = typer.Option(..., file_okay=False),
    split: str = typer.Option(None),
    ablations: bool = typer.Option(True),
    config: Path | None = typer.Option(None, exists=True, dir_okay=False),
    only_cases: str = typer.Option(None, help="Comma-separated case IDs to run (e.g. dev_02,dev_06)."),
    merge_existing: bool = typer.Option(False, help="Merge this run into an existing report in --out."),
    reuse_assembly: bool = typer.Option(False, help="Skip production SPAdes when contigs.fasta already exists."),
    reuse_assembly_from: Path | None = typer.Option(None, help="Existing eval directory whose production/ assemblies should be reused."),
    write_fast_pilot_report: bool = typer.Option(True, help="Write FAST_PILOT_REPORT.md only if it does not already exist."),
):
    """Score production-stack systems and ablations. Does not use the toy assembler."""
    from genome_skeptic.config import is_fast_pilot
    from genome_skeptic.eval.evaluate_real import evaluate_real_genomes

    settings = load_settings(config)
    if is_fast_pilot(settings):
        ablations = False
    case_ids = [c.strip() for c in (only_cases or "").split(",") if c.strip()] or None
    report = evaluate_real_genomes(
        visible, truth, out, settings, run_ablations=ablations, split=split,
        only_cases=case_ids, merge_existing=merge_existing, reuse_assembly=reuse_assembly,
        reuse_assembly_from=reuse_assembly_from, write_fast_pilot_report=write_fast_pilot_report,
    )
    typer.echo(json.dumps({
        "report": str(out / "real_genome_report.md"),
        "limitations": report.get("limitations"),
        "systems": {k: v.get("overall") for k, v in report.get("systems", {}).items()},
    }, indent=2))


@app.command("evaluate-realworld")
def evaluate_realworld_cmd(
    visible: Path = typer.Option(..., exists=True, file_okay=False, help="Agent-visible cases (FASTQ, targets, permitted refs)."),
    truth: Path = typer.Option(..., exists=True, dir_okay=False, help="Hidden truth loaded only after claims."),
    out: Path = typer.Option(..., file_okay=False),
    config: Path | None = typer.Option(None, exists=True, dir_okay=False),
):
    """Compare conventional, falsification-disabled, and full Genome Skeptic systems."""
    from genome_skeptic.eval.realworld import evaluate_realworld

    settings = load_settings(config)
    report = evaluate_realworld(visible, truth, out, settings)
    typer.echo(json.dumps({"report": str(out / "realworld_report.md"), "highlights": len(report["highlights"]), "systems": {k: v["overall"] for k, v in report["systems"].items()}}, indent=2))


@app.command("production-stack")
def production_stack_cmd(
    out: Path = typer.Option(Path("production_stack.json")),
    smoke: bool = typer.Option(True, help="Run tiny valid-input smoke tests before marking tools operational."),
    config: Path | None = typer.Option(None, exists=True, dir_okay=False),
):
    """Write production_stack.json. Executable presence is not operational status."""
    doctor(config=config, out=out, smoke=smoke)


@app.command("freeze-heldout")
def freeze_heldout_cmd(
    out: Path = typer.Option(Path("heldout_freeze_manifest.json")),
    config: Path | None = typer.Option(None, exists=True, dir_okay=False),
):
    """Write a hashed freeze manifest. Call this after development inspection and before held-out."""
    from genome_skeptic.eval.freeze import write_freeze_manifest

    settings = load_settings(config)
    payload = write_freeze_manifest(out, settings)
    typer.echo(json.dumps({"path": str(out), "sha256": payload["sha256"]}, indent=2))


@app.command("model-test")
def model_test_cmd(
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="LLM config, e.g. config/qwen_external_v5.yaml"),
):
    """Call the configured real model. Does not invent responses or run genome benchmarks."""
    from genome_skeptic.eval.model_test import run_model_test

    settings = load_settings(config)
    report = run_model_test(settings)
    typer.echo(json.dumps(report, indent=2, default=str))
    if not report.get("passed"):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
