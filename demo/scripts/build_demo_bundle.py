#!/usr/bin/env python3
"""Build the redistributable demo bundle from locked Genome Skeptic records.

Reads only frozen/locked artifacts already in the repository (M60 manuscript
benchmark, role-swap study, D8/D12 mini-benchmarks). Writes a compact copy under
``demo/results/`` that the Streamlit app can load without the git-ignored run
trees, local databases, or model services.

Nothing is recomputed, re-scored, or re-labelled. Local filesystem paths,
network endpoints and API response identifiers are removed. Every source file
is listed with its SHA256 in ``demo/results/BUNDLE_MANIFEST.json``.

Usage (from the repository root, with the git-ignored RUNS tree present):

    python demo/scripts/build_demo_bundle.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MB = ROOT / "manuscript_benchmark"
RUNS = MB / "RUNS"
LOCKS = MB / "POSITION_LOCKS"
RS = ROOT / "paper_role_swap"
OUT = ROOT / "demo" / "results"

GS_ARMS = ("GS_DETERMINISTIC_V4_1", "GS_AGENTIC_V4_1", "GS_EXHAUSTIVE_V4_1")
FROZEN_CORE_HASH = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"
FROZEN_GIT = "8f66868850a98494778966bd729b88a6fc2952eb"

DROP_KEYS = {
    "url",
    "output_file",
    "config",
    "command",
    "amrfinder_database_directory",
    "database_directory",
    "response_id",
    "pricing_source",
    "source_path",
}
_PATH_PATTERNS = (
    re.compile(r"/mnt/c/Users/[^\s\"']+"),
    re.compile(r"/home/[A-Za-z0-9_.-]+/[^\s\"']*"),
    re.compile(r"[A-Za-z]:\\\\?Users\\\\?[^\s\"']+"),
)
_ENDPOINT = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b")

_sources: dict[str, dict[str, Any]] = {}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def register(path: Path, used_for: str) -> None:
    key = rel(path)
    if key not in _sources:
        _sources[key] = {"path": key, "sha256": sha256_file(path), "bytes": path.stat().st_size, "used_for": set()}
    _sources[key]["used_for"].add(used_for)


def sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items() if k not in DROP_KEYS}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, str):
        text = obj
        for pat in _PATH_PATTERNS:
            text = pat.sub("<local-path>", text)
        return _ENDPOINT.sub("<local-endpoint>", text)
    return obj


def load_json(path: Path, used_for: str) -> Any:
    register(path, used_for)
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path, used_for: str) -> list[dict[str, str]]:
    register(path, used_for)
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_fasta_text(path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    header, seq = None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            if header is not None:
                records.append({"header": header, "sequence": "".join(seq)})
            header, seq = line[1:].strip(), []
        elif line.strip():
            seq.append(line.strip())
    if header is not None:
        records.append({"header": header, "sequence": "".join(seq)})
    return records


def write_json(path: Path, obj: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str)
    else:
        text = json.dumps(obj, indent=1, ensure_ascii=False, default=str)
    path.write_text(text + "\n", encoding="utf-8")


def copy_file(src: Path, dest_rel: str, used_for: str) -> None:
    register(src, used_for)
    dest = OUT / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix in {".md", ".csv", ".json", ".txt"}:
        text = src.read_text(encoding="utf-8")
        if src.suffix == ".json":
            text = json.dumps(sanitize(json.loads(text)), indent=1, ensure_ascii=False) + "\n"
        else:
            text = sanitize(text)
        dest.write_text(text, encoding="utf-8")
    else:
        shutil.copyfile(src, dest)


def run_dir(position: int, accession: str, target: str, system: str) -> Path:
    return RUNS / f"position_{position:02d}" / accession / target / system


def maybe_json(path: Path, used_for: str) -> Any:
    return sanitize(load_json(path, used_for)) if path.exists() else None


PROVENANCE_KEEP = (
    "system",
    "follow_up_policy",
    "planner_invoked",
    "critic_invoked",
    "model_name",
    "prompt_hash",
    "response_hash",
    "critic_prompt_hash",
    "critic_response_hash",
    "cited_evidence_ids",
    "critic_cited_evidence_ids",
    "selected_action",
    "control_decision",
    "critic_challenge",
    "critic_second_action",
    "critic_second_action_reason",
    "agent_failure",
    "final_validator_ran",
    "planner_grounding_status",
    "planner_defects",
    "critic_defects",
    "actions_executed",
    "measurement_trajectory",
    "measurements_changed_before_validation",
    "validator_consumed_measurement_hash",
    "validator_consumed_m0",
    "silent_deterministic_fallback",
    "llm_measurement_entered_claim",
    "locus_stages_m0",
    "locus_stages_m_final",
    "evidence_ids_before_action",
    "available_inputs",
    "diagnostic_needs_m0",
    "diagnostic_needs_after_action1",
    "diagnostic_needs_m_final",
    "ranked_candidate_actions",
    "actions_exposed_to_planner",
    "baseline_work_already_done",
    "inert_actions",
    "remaining_actions_for_critic",
    "measurement_state",
    "informative_action_count",
    "action_status_counts",
    "model_call_count",
    "planner_model_call_count",
    "critic_model_call_count",
    "repair_count",
    "planner_seconds",
    "critic_seconds",
    "llm_seconds",
    "preferred_hypothesis",
    "final_claim_state",
    "call_graph",
    "evidence_ids",
    "seconds",
)


def gs_arm_record(position: int, accession: str, target: str, system: str) -> dict[str, Any]:
    d = run_dir(position, accession, target, system)
    tag = f"m60_trace:{system}"
    lock = sanitize(load_json(LOCKS / f"position_{position:02d}" / f"{system}.json", f"m60_lock:{system}"))
    prov_raw = maybe_json(d / "agentic_provenance.json", tag) or {}
    claims = maybe_json(d / "claims.json", tag) or []
    record: dict[str, Any] = {
        "locked": lock,
        "provenance": {k: prov_raw.get(k) for k in PROVENANCE_KEEP if k in prov_raw},
        "claim": claims[0] if claims else None,
        "evidence": maybe_json(d / "evidence.json", tag) or [],
        "locus_evidence": maybe_json(d / "locus_evidence.json", tag),
    }
    if system == "GS_AGENTIC_V4_1":
        record["planner_decision"] = maybe_json(d / "planner_decision.json", tag)
        record["critic_review"] = maybe_json(d / "critic_review.json", tag)
        record["model_call_log"] = maybe_json(d / "call_log.json", tag) or []
    return record


def sequences_for(position: int, accession: str, target: str) -> dict[str, Any]:
    d = run_dir(position, accession, target, "GS_AGENTIC_V4_1")
    out: dict[str, Any] = {"query_protein": None, "candidate_protein": None}
    tfa = d / "target.fa"
    if tfa.exists():
        register(tfa, "m60_sequence:query")
        recs = read_fasta_text(tfa)
        if recs:
            out["query_protein"] = {
                **recs[0],
                "origin": (
                    "Longest member of the frozen curated family for this target "
                    "(scripts/run_m60_position.py:write_target_fa). This is the query, not the genome."
                ),
            }
    cand = d / "family" / target / "competitive" / "target" / "candidate.faa"
    if cand.exists():
        register(cand, "m60_sequence:candidate")
        recs = read_fasta_text(cand)
        if recs:
            out["candidate_protein"] = {
                **recs[0],
                "origin": (
                    "Candidate protein translated by Genome Skeptic from the reconstructed locus in the "
                    "public RefSeq assembly (GS-Agentic run, competitive-family step)."
                ),
            }
    return out


def specialist_record(position: int, accession: str, target: str) -> dict[str, Any] | None:
    for name in ("AMRFINDERPLUS", "NCBI_REFSEQ_PGAP"):
        p = LOCKS / f"position_{position:02d}" / f"{name}.json"
        if p.exists():
            rec = {"system": name, "locked": sanitize(load_json(p, f"m60_lock:{name}"))}
            pg = run_dir(position, accession, target, name) / "pgap_comparator.json"
            if pg.exists():
                rec["pgap_comparator"] = sanitize(load_json(pg, "m60_trace:NCBI_REFSEQ_PGAP"))
            return rec
    return None


def conventional_record(position: int, accession: str, target: str) -> dict[str, Any]:
    d = run_dir(position, accession, target, "CONVENTIONAL")
    claims = maybe_json(d / "claims.json", "m60_trace:CONVENTIONAL") or []
    return {
        "locked": sanitize(load_json(LOCKS / f"position_{position:02d}" / "CONVENTIONAL.json", "m60_lock:CONVENTIONAL")),
        "claim": claims[0] if claims else None,
        "hits": maybe_json(d / "search" / "gene_search_hits.json", "m60_trace:CONVENTIONAL"),
    }


def build_m60() -> list[dict[str, Any]]:
    final_rows = load_csv(MB / "RESULTS_M60" / "M60_FINAL_CASE_LEVEL_RESULTS.csv", "m60_scoring")
    cohort = {r["case_id"]: r for r in load_csv(MB / "M60_COHORT_MANIFEST.csv", "m60_cohort")}
    truth = {r["case_id"]: r for r in load_csv(MB / "TRUTH_M60" / "M60_TRUTH_FINAL_CASE_LEVEL.csv", "m60_truth")}
    remediation = {
        int(r["position"]): r
        for r in load_csv(MB / "COMPARATOR_REMEDIATION" / "AMRFINDER_REMEDIATION_CASE_LEVEL.csv", "m60_amr_remediation")
    }
    index: list[dict[str, Any]] = []
    for row in final_rows:
        pos = int(row["position"])
        acc, target, cid = row["accession"], row["target"], row["case_id"]
        meta = cohort[cid]
        arms = {s: gs_arm_record(pos, acc, target, s) for s in GS_ARMS}
        agent = arms["GS_AGENTIC_V4_1"]
        agent_claim = agent["claim"] or {}
        prov = agent["provenance"]
        case = {
            "position": pos,
            "case_id": cid,
            "accession": acc,
            "organism": meta["organism"],
            "target": target,
            "stratum": row["stratum"],
            "assembly_level": meta["assembly_level"],
            "genome_size": int(meta["genome_size"]) if meta.get("genome_size") else None,
            "release_date": meta.get("release_date"),
            "ambiguity_score": meta.get("ambiguity_score") or None,
            "truth": row["truth"],
            "truth_status": row["truth_status"],
            "evaluable": row["evaluable"] == "True",
        }
        for key in (
            "conventional_pred", "conventional_correct", "specialist_pred", "specialist_correct", "specialist_tool",
            "gs_det_pred", "gs_det_correct", "gs_agent_pred", "gs_agent_correct", "gs_exh_pred", "gs_exh_correct",
            "agent_actions", "exhaustive_actions", "agent_runtime", "exhaustive_runtime",
        ):
            case[key] = row[key]
        case.update(
            {
                "agent_claim_type": agent_claim.get("claim_type"),
                "agent_claim_status": agent_claim.get("status"),
                "agent_confidence": agent_claim.get("confidence"),
                "agent_evidence_completeness": agent_claim.get("evidence_completeness"),
                "agent_homology_support": agent_claim.get("homology_support"),
                "agent_architecture": agent_claim.get("architecture_state"),
                "planner_action": prov.get("selected_action"),
                "critic_verdict": (prov.get("critic_challenge") or {}).get("verdict"),
                "critic_second_action": prov.get("critic_second_action"),
                "model": agent["locked"].get("model"),
            }
        )
        trace = {
            "case": case,
            "truth": sanitize(truth.get(cid)),
            "sequences": sequences_for(pos, acc, target),
            "arms": arms,
            "conventional": conventional_record(pos, acc, target),
            "specialist": specialist_record(pos, acc, target),
            "amrfinder_remediation": remediation.get(pos),
            "frozen_system": {
                "system_version": agent["locked"].get("system_version"),
                "git_commit": agent["locked"].get("git_commit"),
                "scientific_core_hash": agent["locked"].get("scientific_core_hash"),
                "tool_versions": agent["locked"].get("tool_versions"),
                "database_versions": agent["locked"].get("database_versions"),
            },
        }
        assert trace["frozen_system"]["git_commit"] == FROZEN_GIT, cid
        assert trace["frozen_system"]["scientific_core_hash"] == FROZEN_CORE_HASH, cid
        write_json(OUT / "m60" / "cases" / f"position_{pos:02d}.json", trace, compact=True)
        index.append(case)
    index.sort(key=lambda r: r["position"])
    write_json(OUT / "m60" / "case_index.json", index)
    return index


M60_TABLES = {
    "RESULTS_M60/M60_FINAL_SYSTEM_SUMMARY.csv": "m60/tables/system_summary.csv",
    "RESULTS_M60/M60_TARGET_SPECIFIC_RESULTS.csv": "m60/tables/target_specific.csv",
    "RESULTS_M60/M60_STRATUM_RESULTS.csv": "m60/tables/stratum.csv",
    "RESULTS_M60/M60_EFFICIENCY_RESULTS.csv": "m60/tables/efficiency.csv",
    "RESULTS_M60/M60_AGENT_MECHANISMS.csv": "m60/tables/agent_mechanisms.csv",
    "RESULTS_M60/M60_AGENT_VS_DETERMINISTIC.csv": "m60/tables/agent_vs_deterministic.csv",
    "RESULTS_M60/M60_AGENT_VS_EXHAUSTIVE.csv": "m60/tables/agent_vs_exhaustive.csv",
    "RESULTS_M60/M60_ERROR_TAXONOMY.csv": "m60/tables/error_taxonomy.csv",
    "RESULTS_M60/M60_FINAL_RESULTS.md": "m60/docs/M60_FINAL_RESULTS.md",
    "RESULTS_M60/M60_FINAL_INTEGRITY_STATEMENT.md": "m60/docs/M60_FINAL_INTEGRITY_STATEMENT.md",
    "REANALYSIS_R1/M60_CONSTANT_BASELINE.csv": "m60/tables/constant_baseline.csv",
    "REANALYSIS_R1/M60_CLASS_DECOMPOSED.csv": "m60/tables/class_decomposed.csv",
    "REANALYSIS_R1/M60_PREDICTION_DEGENERACY.csv": "m60/tables/prediction_degeneracy.csv",
    "REANALYSIS_R1/M60_REANALYSIS_SUMMARY.md": "m60/docs/M60_REANALYSIS_SUMMARY.md",
    "POSTHOC_ERROR_ANALYSIS/POSTHOC_MANUSCRIPT_INTERPRETATION.md": "m60/docs/POSTHOC_MANUSCRIPT_INTERPRETATION.md",
    "POSTHOC_ERROR_ANALYSIS/POSTHOC_ROOT_CAUSE_SUMMARY.csv": "m60/tables/posthoc_root_cause.csv",
    "ABLATION_VALIDATOR_R1/ABLATION_VALIDATOR_R1_SUMMARY.md": "m60/docs/ABLATION_VALIDATOR_R1_SUMMARY.md",
    "COMPARATOR_REMEDIATION/AMRFINDER_REMEDIATION_CASE_LEVEL.csv": "m60/tables/amrfinder_remediation.csv",
    "TRUTH_M60/M60_TRUTH_METHODS.md": "m60/docs/M60_TRUTH_METHODS.md",
    "M60_PROTOCOL.md": "m60/docs/M60_PROTOCOL.md",
}

ROLE_SWAP_FILES = {
    "results/controller_summary.csv": "role_swap/controller_summary.csv",
    "results/controller_efficiency.csv": "role_swap/controller_efficiency.csv",
    "results/case_level_results.csv": "role_swap/case_level_results.csv",
    "results/statistics.json": "role_swap/statistics.json",
    "results/ROLE_SWAP_FINAL_RESULTS.md": "role_swap/ROLE_SWAP_FINAL_RESULTS.md",
    "results/precursor/SOL56_M60_SUMMARY.json": "role_swap/SOL56_M60_SUMMARY.json",
    "results/precursor/POSTHOC_MODEL_INVARIANCE.md": "role_swap/POSTHOC_MODEL_INVARIANCE.md",
    "protocol/ARM_DEFINITIONS.md": "role_swap/ARM_DEFINITIONS.md",
    "protocol/TRUTH_PROTOCOL.md": "role_swap/TRUTH_PROTOCOL.md",
    "data/prospective_case_manifest.csv": "role_swap/prospective_case_manifest.csv",
}

DEV_FILES = {
    "external_validation_agentic_d8/D8_SYSTEM_SUMMARY.csv": "development/d8_system_summary.csv",
    "external_validation_agentic_d8/D8_CASE_LEVEL_RESULTS.csv": "development/d8_case_level.csv",
    "external_validation_agentic_d8/D8_EXTERNAL_RESULTS.md": "development/D8_EXTERNAL_RESULTS.md",
    "external_validation_agentic_d12/D12_SYSTEM_SUMMARY.csv": "development/d12_system_summary.csv",
    "external_validation_agentic_d12/D12_CASE_LEVEL_RESULTS.csv": "development/d12_case_level.csv",
    "external_validation_agentic_d12/D12_EXTERNAL_RESULTS.md": "development/D12_EXTERNAL_RESULTS.md",
}


def build_role_swap_judge_records() -> None:
    """Arm D (LLM as final judge) structured outputs; arm B kept for pairing."""
    out: dict[str, Any] = {}
    for arm in ("B", "D"):
        for p in sorted((RS / "data" / "locked_predictions" / arm).glob("RS*_prediction.json")):
            rec = sanitize(load_json(p, f"role_swap_prediction:{arm}"))
            out.setdefault(rec["case_id"], {})[arm] = rec
    write_json(OUT / "role_swap" / "arm_b_d_predictions.json", out, compact=True)


# Examples are chosen from the locked records; each entry lists the facts that the
# builder re-checks so the written rationale cannot silently drift from the data.
EXAMPLES = [
    {
        "id": "strong_evidence",
        "title": "Strong evidence: divergent but full-length rpoB orthologue",
        "position": 2,
        "category": "Supported annotation",
        "expect": {"truth": "POSITIVE", "gs_agent_pred": "POSITIVE", "conventional_pred": "NEGATIVE"},
        "why": (
            "Independent truth is POSITIVE and all three Genome Skeptic arms detect rpoB. The conventional "
            "nucleotide-identity baseline misses it because a fixed 80% identity / 80% coverage rule does not "
            "fit a divergent orthologue. The family HMM and multi-member protein search carry the call."
        ),
    },
    {
        "id": "uncertain_truth",
        "title": "Unresolvable truth: rpoB in a reduced Wolbachia genome",
        "position": 3,
        "category": "Uncertain / not evaluable",
        "expect": {"truth": "TRUTH_UNCERTAIN", "gs_agent_pred": "POSITIVE", "specialist_pred": "NEGATIVE"},
        "why": (
            "Independent adjudicators could not resolve truth (best reference similarity 0.475), so the case is "
            "excluded from accuracy. Genome Skeptic and the RefSeq/PGAP comparator disagree. The case shows why "
            "19 of 60 M60 cases were reported separately rather than forced into a correct/incorrect label."
        ),
    },
    {
        "id": "validator_rejects_hit",
        "title": "Verification overrides a homology hit, and is wrong",
        "position": 13,
        "category": "Rejected annotation (error)",
        "expect": {"truth": "POSITIVE", "conventional_pred": "POSITIVE", "gs_agent_pred": "NEGATIVE"},
        "why": (
            "The conventional baseline reported tetA (identity and coverage at least 80%). All three Genome Skeptic "
            "arms returned 'not detected'; independent truth is POSITIVE. Post-hoc analysis attributed the shared "
            "tetA errors to frozen family-state rules (refine_weak_family_classification relabels the competitive "
            "result as ambiguous_family, which the validator treats as a hard negative). A one-iteration "
            "counterfactual patch recovered this case; the repaired adjudicator was frozen as V5 after M60. "
            "It is shown because skepticism can also cause errors."
        ),
    },
    {
        "id": "critic_second_action",
        "title": "Critic challenges the planner and requests a second test",
        "position": None,
        "category": "Critic intervention",
        "expect": {"critic_second_action_present": True},
        "why": (
            "This is the only M60 case in which the critic did not accept the planner's plan and triggered a "
            "second registered measurement. The final endpoint still came from the deterministic validator and "
            "matched GS-Deterministic, as in all 60 cases."
        ),
    },
]


def build_examples(index: list[dict[str, Any]]) -> None:
    by_pos = {c["position"]: c for c in index}
    critic_cases = [c for c in index if c.get("critic_second_action")]
    out = []
    for ex in EXAMPLES:
        ex = dict(ex)
        if ex["id"] == "critic_second_action":
            if len(critic_cases) != 1:
                raise SystemExit(f"expected exactly one critic second-action case, found {len(critic_cases)}")
            ex["position"] = critic_cases[0]["position"]
            ex["expect"] = {}
        case = by_pos[ex["position"]]
        for k, v in ex.pop("expect").items():
            if case.get(k) != v:
                raise SystemExit(f"example {ex['id']}: expected {k}={v!r}, locked record has {case.get(k)!r}")
        ex["case_id"] = case["case_id"]
        out.append(ex)
    write_json(OUT / "examples.json", out)


def build_frozen_core_reference() -> None:
    """Frozen component and per-file hashes, so live runs can be compared to the M60 core."""
    manifest = load_json(MB / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json", "frozen_core_reference")
    env = load_json(MB / "M60_ENVIRONMENT.json", "frozen_core_reference")
    core = {k: v for k, v in manifest["scientific_core"].items() if k not in {"family_dir", "ortholog_dir"}}
    assert env["freeze_verification"]["scientific_core_hash"] == FROZEN_CORE_HASH
    assets = env["hashed_assets"]
    write_json(
        OUT / "m60" / "frozen_core_reference.json",
        {
            "git_commit": FROZEN_GIT,
            "scientific_core_hash": FROZEN_CORE_HASH,
            "components": core,
            "family_definition_files": {f["path"]: f["sha256"] for f in assets["src_target_families"]["files"]},
            "orthology_reference_files": {f["path"]: f["sha256"] for f in assets["orthology_references"]["files"]},
        },
    )


def git_head() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None


def main() -> int:
    if not RUNS.exists():
        raise SystemExit("manuscript_benchmark/RUNS is missing; the bundle can only be rebuilt on the original workstation")
    if OUT.exists():
        for sub in ("m60", "role_swap", "development"):
            shutil.rmtree(OUT / sub, ignore_errors=True)
    index = build_m60()
    build_frozen_core_reference()
    for src, dest in M60_TABLES.items():
        copy_file(MB / src, dest, "m60_summary")
    for src, dest in ROLE_SWAP_FILES.items():
        copy_file(RS / src, dest, "role_swap")
    build_role_swap_judge_records()
    for src, dest in DEV_FILES.items():
        copy_file(ROOT / src, dest, "development_minibenchmarks")
    build_examples(index)
    sources = sorted(
        ({**v, "used_for": sorted(v["used_for"])} for v in _sources.values()), key=lambda r: r["path"]
    )
    manifest = {
        "kind": "GENOME_SKEPTIC_DEMO_BUNDLE",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "builder": "demo/scripts/build_demo_bundle.py",
        "repository_head_at_build": git_head(),
        "frozen_m60_system": {"git_commit": FROZEN_GIT, "scientific_core_hash": FROZEN_CORE_HASH},
        "n_m60_cases": len(index),
        "transformations": [
            "selected fields copied from locked JSON/CSV records without recomputation",
            f"removed keys: {sorted(DROP_KEYS)}",
            "replaced local filesystem paths with <local-path> and IP endpoints with <local-endpoint>",
        ],
        "not_included": [
            "genome assemblies (public RefSeq; retrieve by accession)",
            "HMM profiles, BLAST/HMMER raw outputs, and per-tool logs",
            "model prompts beyond the recorded hashes",
        ],
        "sources": sources,
    }
    write_json(OUT / "BUNDLE_MANIFEST.json", manifest)
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"cases={len(index)} sources={len(sources)} bundle_bytes={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
