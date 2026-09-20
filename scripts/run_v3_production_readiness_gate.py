#!/usr/bin/env python3
"""Agentic V3 production-readiness gate.

Runs in the Linux/WSL production environment. Does not rerun D8, inspect D20,
retrieve new truth, change biological thresholds, or create a fresh benchmark.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.action_catalog_v3 import live_actions_for_need  # noqa: E402
from genome_skeptic.agents.action_contract import ActionStatus, apply_action_result, measurement_fingerprint  # noqa: E402
from genome_skeptic.agents.assembly_loop import _LoopState  # noqa: E402
from genome_skeptic.agents.assembly_loop_v2 import (  # noqa: E402
    BASELINE_WORK,
    _V2Run,
    _act_competitive_family,
    _act_hmmer,
    _act_protein_search,
    capabilities_for,
)
from genome_skeptic.agents.assembly_loop_v3 import run_skeptic_agentic_v3  # noqa: E402
from genome_skeptic.agents.diagnostic_needs import (  # noqa: E402
    COPY_NUMBER_UNRESOLVED,
    DIAGNOSTIC_NEEDS,
    FAMILY_IDENTITY_UNRESOLVED,
    ORTHOLOG_VS_PARALOG_UNRESOLVED,
    REMOTE_HOMOLOG_NOT_EXCLUDED,
    derive_diagnostic_needs,
)
from genome_skeptic.config import Settings, load_settings  # noqa: E402
from genome_skeptic.families import load_family  # noqa: E402
from genome_skeptic.models import GeneSearchHit, TargetProfile, TargetType  # noqa: E402
from genome_skeptic.tools.hmmer import hmmer_tools_available  # noqa: E402
from genome_skeptic.tools.similarity import similarity_tools_available  # noqa: E402
from genome_skeptic.validators.family_orthology import FamilyEvidence  # noqa: E402
from genome_skeptic.validators.falsification import TargetMeasurements, _loci, build_target_gene_claim  # noqa: E402

OUT = ROOT / "dev_work" / "agentic_v3_production_gate"
WSL_OLLAMA = "http://172.17.32.1:11434/v1"
LACZ_LIMITATION = (
    "No frozen deterministic instrument currently distinguishes true LacZ "
    "orthology from relevant competing beta-galactosidase families when "
    "reference/GFF/orthology resources are absent."
)
HOMOLOGY_ACTIONS = {
    "search_target_domains_hmmer",
    "search_target_proteins_mmseqs",
    "search_target_proteins_diamond",
}
CURRENT_LACZ_LIMITATION = True


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _llm_reachable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or 80
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _fix_llm_host(settings) -> str | None:
    url = settings.llm.base_url or ""
    if "localhost" not in url and "127.0.0.1" not in url:
        return None
    if _llm_reachable(url):
        return None
    settings.llm.base_url = WSL_OLLAMA
    if settings.llm.planner is not None:
        settings.llm.planner.base_url = WSL_OLLAMA
    if settings.llm.critic is not None:
        settings.llm.critic.base_url = WSL_OLLAMA
    return WSL_OLLAMA


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _which_version(exe: str) -> dict:
    path = shutil.which(exe)
    row = {"executable": exe, "available": bool(path), "path": path, "version": None}
    if not path:
        return row
    probes = {
        "hmmsearch": [[path, "-h"]],
        "hmmbuild": [[path, "-h"]],
        "mmseqs": [[path, "version"], [path, "-h"]],
        "diamond": [[path, "version"], [path, "--version"]],
        "blastp": [[path, "-version"]],
        "python": [[path, "--version"]],
    }
    for cmd in probes.get(exe, [[path, "--version"], [path, "-h"]]):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                row["version"] = stripped[:200]
                return row
    return row


def _family_assets() -> dict:
    family_root = SRC / "genome_skeptic" / "data" / "target_families"
    families = {}
    if family_root.exists():
        for fam_dir in sorted(p for p in family_root.iterdir() if p.is_dir()):
            yaml_path = fam_dir / "family.yaml"
            if not yaml_path.exists():
                continue
            fam = load_family(fam_dir.name)
            families[fam_dir.name] = {
                "family_yaml": str(yaml_path),
                "members_faa": (fam_dir / "members.faa").exists(),
                "members_aln": (fam_dir / "members.aln.faa").exists(),
                "n_members": len(fam.members) if fam else 0,
                "competing_families": list(fam.competing_families or []) if fam else [],
            }
    return {
        "family_dir": str(family_root),
        "family_dir_exists": family_root.exists(),
        "n_families": len(families),
        "families": families,
        "taxonomy_db": None,
        "note": "HMMER models are built by hmmbuild from packaged MSAs at first use; MMseqs/DIAMOND search query vs assembly ORFs and do not require an external NR database.",
    }


def probe_environment() -> dict:
    python_row = _which_version("python")
    python_row["sys_executable"] = sys.executable
    python_row["sys_version"] = sys.version
    env = {
        "platform": platform.platform(),
        "python": python_row,
        "hmmsearch": _which_version("hmmsearch"),
        "hmmbuild": _which_version("hmmbuild"),
        "mmseqs": _which_version("mmseqs"),
        "diamond": _which_version("diamond"),
        "blastp": _which_version("blastp"),
        "hmmer_tools_available": hmmer_tools_available(),
        "similarity_tools_available": similarity_tools_available(),
        "assets": _family_assets(),
    }
    env["hmmer_available"] = bool(env["hmmsearch"]["available"] and env["hmmbuild"]["available"])
    env["mmseqs_available"] = bool(env["mmseqs"]["available"])
    env["diamond_available"] = bool(env["diamond"]["available"])
    env["blast_available"] = bool(env["blastp"]["available"])
    env["similarity_search_available"] = env["mmseqs_available"] or env["diamond_available"]
    return env


def _hit() -> GeneSearchHit:
    seq = "ATG" + ("CGTAGC" * 20) + "TAA"
    return GeneSearchHit.model_validate(
        {
            "query_id": "probe",
            "contig_id": "c1",
            "search_kind": "translated",
            "qstart": 0,
            "qend": len(seq),
            "tstart": 500,
            "tend": 500 + len(seq),
            "strand": "+",
            "identity": 0.95,
            "query_coverage": 0.98,
            "alignment_length": len(seq),
            "query_length": len(seq),
            "contig_length": 2000,
            "tool": "internal_gene_search",
        }
    )


def _measurements(family_id: str, *, competing_cls: str | None = None) -> TargetMeasurements:
    aa = "M" + ("ACDEFGHIKLMNPQRSTVWY" * 20)
    profile = TargetProfile(
        query_id=family_id,
        sequence=aa,
        target_type=TargetType.gene_orthologue,
        family_id=family_id,
    )
    recon = {"architecture": "canonical_full_length"}
    if competing_cls is not None:
        recon["competitive_family"] = {"classification": competing_cls}
    fam = FamilyEvidence(
        family_id=family_id,
        architecture="canonical_full_length",
        supports_orthologue=True,
        reconstruction=recon,
    )
    hit = _hit()
    hit.query_id = family_id
    return TargetMeasurements(
        query_id=family_id,
        profile=profile,
        hits=[hit],
        contig_sequences={"c1": "A" * 2000},
        contig_gc={"c1": 0.5},
        genome_gc=0.5,
        family_evidence=fam,
        tools_run=["internal_gene_search"],
    )


def action_availability_audit(env: dict) -> dict:
    hmmer = env["hmmer_available"]
    similarity = env["similarity_search_available"]
    performed = BASELINE_WORK
    rows = {}
    specs = {
        REMOTE_HOMOLOG_NOT_EXCLUDED: _measurements("rpoB_RNAP_beta"),
        COPY_NUMBER_UNRESOLVED: _measurements("tuf_EF_Tu"),
        FAMILY_IDENTITY_UNRESOLVED: _measurements("tetA_tetracycline_efflux", competing_cls="unresolved_candidate"),
        ORTHOLOG_VS_PARALOG_UNRESOLVED: _measurements("rpoB_RNAP_beta"),
    }
    for need, measurements in specs.items():
        caps = {
            "assembly": True,
            "targets": True,
            "hits": True,
            "query_protein": True,
            "similarity_tools": similarity,
            "hmmer": hmmer,
            "competing_families": need == FAMILY_IDENTITY_UNRESOLVED,
            "references": need == ORTHOLOG_VS_PARALOG_UNRESOLVED,
            "gff": need == ORTHOLOG_VS_PARALOG_UNRESOLVED,
            "depth_tsv": False,
            "mapping_sam": False,
            "taxonomy_db": False,
            "protein_fasta": True,
            "catalytic_residues": False,
            "phylogenetic_placement": False,
        }
        live = live_actions_for_need(need, caps, performed, measurements)
        rows[need] = {
            "live_actions": live,
            "hmmer_or_similarity": bool(set(live) & HOMOLOGY_ACTIONS),
            "competitive_family": "competitive_family" in live,
            "reciprocal_or_orthology": bool(
                set(live)
                & {
                    "reciprocal_best_hit_search",
                    "compare_locus_to_reference",
                    "inspect_gene_order_against_reference",
                    "inspect_synteny_neighborhood_for_target",
                }
            ),
        }
    required = {
        REMOTE_HOMOLOG_NOT_EXCLUDED: rows[REMOTE_HOMOLOG_NOT_EXCLUDED]["hmmer_or_similarity"],
        COPY_NUMBER_UNRESOLVED: rows[COPY_NUMBER_UNRESOLVED]["hmmer_or_similarity"],
        FAMILY_IDENTITY_UNRESOLVED: rows[FAMILY_IDENTITY_UNRESOLVED]["competitive_family"],
        ORTHOLOG_VS_PARALOG_UNRESOLVED: rows[ORTHOLOG_VS_PARALOG_UNRESOLVED]["reciprocal_or_orthology"],
    }
    return {"per_need": rows, "required": required, "pass": all(required.values()), "llm_called": False}


def run_unit_tests() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_agentic_v3.py", "-q", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    return {
        "returncode": proc.returncode,
        "pass": proc.returncode == 0,
        "stdout_tail": text[-4000:],
    }


def make_state(settings: Settings, assembly: Path, targets: Path, out_dir: Path, contig_seqs: dict[str, str]) -> _LoopState:
    state = _LoopState(
        settings=settings,
        assembly=assembly,
        targets=targets,
        out_dir=out_dir,
        declared_organism=None,
        mapping_sam=None,
        depth_tsv=None,
        assembly_gff=None,
        proteins_path=None,
        references_yaml=None,
    )
    state.contig_seqs = dict(contig_seqs)
    return state


def _routing_record(provenance: dict) -> dict:
    executed = provenance.get("actions_executed") or []
    claim = None
    claims_path = None
    return {
        "diagnostic_needs": provenance.get("diagnostic_needs_m0"),
        "executable_actions_before_ranking": [
            row["action_id"] if isinstance(row, dict) else row
            for row in (provenance.get("executable_actions_before_ranking") or [])
        ],
        "ranked_actions": [row["action_id"] for row in (provenance.get("ranked_candidate_actions") or [])],
        "actions_exposed_to_planner": provenance.get("actions_exposed_to_planner")
        or provenance.get("available_actions")
        or [],
        "planner_action": provenance.get("selected_action") or provenance.get("control_decision"),
        "critic_action": provenance.get("critic_second_action"),
        "action_executed": [row.get("action_id") for row in executed],
        "ActionResult": executed,
        "m0_hash": ((provenance.get("measurement_state") or {}).get("m0") or {}).get("hash"),
        "m_final_hash": ((provenance.get("measurement_state") or {}).get("m_final") or {}).get("hash"),
        "final_validator_result": {
            "ran": provenance.get("final_validator_ran"),
            "agent_failure": provenance.get("agent_failure"),
        },
        "planner_grounding_status": provenance.get("planner_grounding_status"),
        "critic_invoked": provenance.get("critic_invoked"),
        "claim": claim,
        "claims_path": claims_path,
    }


def _informative(executed: list) -> bool:
    return any(str(row.get("status") or "").upper() == ActionStatus.informative.value for row in executed)


def _relevant_offered(exposed: list[str], relevant: set[str]) -> bool:
    return bool(set(exposed) & relevant)


def _filtered_before_planner(executable: list[str], exposed: list[str], relevant: set[str]) -> bool:
    live_relevant = set(executable) & relevant
    return bool(live_relevant) and not (live_relevant & set(exposed))


def run_capability_case(
    *,
    name: str,
    expected_need: str,
    relevant_actions: set[str],
    m0: TargetMeasurements,
    assembly: Path,
    targets: Path,
    settings: Settings,
    out: Path,
    probe: dict,
) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    dump_json(out / "m0.json", measurement_fingerprint(m0))
    dump_json(out / "action_probe.json", probe)

    claims, _loci_out, provenance = run_skeptic_agentic_v3(
        assembly,
        targets,
        out / "genome_skeptic_agentic_v3",
        settings,
        query_ids=[m0.query_id],
        initial_measurements=m0,
    )
    routing = _routing_record(provenance)
    if claims:
        routing["final_validator_result"] = {
            "ran": provenance.get("final_validator_ran"),
            "agent_failure": provenance.get("agent_failure"),
            "claim_type": claims[0].claim_type.value if claims[0].claim_type else None,
            "status": claims[0].status.value if claims[0].status else None,
            "confidence": claims[0].confidence,
            "created_by": claims[0].provenance.created_by if claims[0].provenance else None,
            "statement": claims[0].statement,
        }
    dump_json(out / "routing.json", routing)
    dump_json(out / "provenance.json", {k: v for k, v in provenance.items() if k != "actions_executed"})

    needs = [row["need"] for row in (routing["diagnostic_needs"] or [])]
    offered = _relevant_offered(routing["actions_exposed_to_planner"], relevant_actions)
    filtered = _filtered_before_planner(
        routing["executable_actions_before_ranking"],
        routing["actions_exposed_to_planner"],
        relevant_actions,
    )
    informative = _informative(routing["ActionResult"])
    probe_ok = str(probe.get("action_status") or "").upper() == ActionStatus.informative.value
    need_ok = expected_need in needs
    row = {
        "name": name,
        "expected_need": expected_need,
        "need_present": need_ok,
        "needs": needs,
        "relevant_actions": sorted(relevant_actions),
        "routing": routing,
        "relevant_action_offered": offered,
        "relevant_action_filtered_before_planner": filtered,
        "informative_action_executed": informative,
        "probe_informative": probe_ok,
        "probe": probe,
        "pass": need_ok and offered and (not filtered) and informative and probe_ok and provenance.get("agent_failure") is None,
    }
    dump_json(out / "case.json", row)
    print(
        f"{name} need={need_ok} offered={offered} filtered={filtered} informative={informative} probe={probe_ok}",
        flush=True,
    )
    return row


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = load_settings(ROOT / "config" / "qwen_agentic_dev.yaml")
    remap = _fix_llm_host(settings)
    if remap:
        print(f"WSL_OLLAMA_REMAP {remap}", flush=True)

    env = probe_environment()
    dump_json(OUT / "environment.json", env)
    print("HMMER", env["hmmer_available"], env["hmmsearch"]["path"], env["hmmsearch"]["version"], flush=True)
    print("MMSEQS", env["mmseqs_available"], env["mmseqs"]["path"], env["mmseqs"]["version"], flush=True)
    print("DIAMOND", env["diamond_available"], env["diamond"]["path"], env["diamond"]["version"], flush=True)
    print("BLAST", env["blast_available"], env["blastp"]["path"], env["blastp"]["version"], flush=True)
    print("PYTHON", env["python"]["sys_executable"], env["python"]["sys_version"].splitlines()[0], flush=True)

    if not env["hmmer_available"] or not env["similarity_search_available"]:
        report = {
            "gate_pass": False,
            "stop_reason": "required production executables missing; fix PATH/environment only",
            "environment": env,
            "d8_rerun": False,
            "d20_touched": False,
            "current_lacz_limitation": LACZ_LIMITATION,
        }
        dump_json(OUT / "GATE_REPORT.json", report)
        _print_final(report)
        return 1

    tests = run_unit_tests()
    dump_json(OUT / "unit_tests.json", tests)
    print("V3_TESTS", "PASS" if tests["pass"] else "FAIL", flush=True)
    if not tests["pass"]:
        print(tests["stdout_tail"], flush=True)

    audit = action_availability_audit(env)
    dump_json(OUT / "action_availability_audit.json", audit)
    print("ACTION_AUDIT", "PASS" if audit["pass"] else "FAIL", json.dumps(audit["required"]), flush=True)

    tet_mod = _load_module("v3_teta_cap", ROOT / "dev_work" / "agentic_capability_tetA_mfs" / "run_capability.py")
    rt_mod = _load_module(
        "v3_rpob_tuf_cap",
        ROOT / "dev_work" / "agentic_capability_divergent_rpob_tuf_copies" / "run_capability_tests.py",
    )

    cases = {}

    tet_dir = OUT / "teta_mfs"
    m0_tet, tet_asm, tet_tgt = tet_mod.build_fixture(tet_dir / "fixture")
    tet_state = make_state(settings, tet_asm, tet_tgt, tet_dir / "probe", m0_tet.contig_sequences)
    tet_run = _V2Run(state=tet_state)
    tet_run.capabilities = capabilities_for(tet_state, m0_tet)
    tet_probe_m = copy.deepcopy(m0_tet)
    tet_result = apply_action_result(tet_probe_m, _act_competitive_family(tet_run, tet_probe_m, "competitive_family"))
    tet_claim = build_target_gene_claim(copy.deepcopy(tet_probe_m), settings, ["E_m0"])[0]
    tet_probe = {
        "action_id": "competitive_family",
        "action_status": tet_result.status.value,
        "status_reason": tet_result.status_reason,
        "fields_changed": sorted({u.field for u in tet_result.applied if u.n_new}),
        "classification": (getattr(tet_probe_m.family_evidence, "reconstruction", None) or {})
        .get("competitive_family", {})
        .get("classification"),
        "validator_result": tet_claim.claim_type.value,
        "hash_changed": measurement_fingerprint(m0_tet)["hash"] != measurement_fingerprint(tet_probe_m)["hash"],
    }
    cases["teta"] = run_capability_case(
        name="teta_mfs",
        expected_need=FAMILY_IDENTITY_UNRESOLVED,
        relevant_actions={"competitive_family"},
        m0=m0_tet,
        assembly=tet_asm,
        targets=tet_tgt,
        settings=settings,
        out=tet_dir,
        probe=tet_probe,
    )

    rpob_dir = OUT / "divergent_rpob"
    m0_r, r_asm, r_tgt, _meta_r = rt_mod.build_test_a(rpob_dir / "fixture", settings)
    r_state = make_state(settings, r_asm, r_tgt, rpob_dir / "probe", m0_r.contig_sequences)
    r_run = _V2Run(state=r_state)
    r_run.capabilities = capabilities_for(r_state, m0_r)
    r_probe_m = copy.deepcopy(m0_r)
    r_before = measurement_fingerprint(r_probe_m)
    r_result = apply_action_result(r_probe_m, _act_hmmer(r_run, r_probe_m, "search_target_domains_hmmer"))
    if r_result.status is not ActionStatus.informative:
        r_probe_m = copy.deepcopy(m0_r)
        r_result = apply_action_result(r_probe_m, _act_protein_search(r_run, r_probe_m, "search_target_proteins_mmseqs"))
        r_action_id = "search_target_proteins_mmseqs"
    else:
        r_action_id = "search_target_domains_hmmer"
    r_after = measurement_fingerprint(r_probe_m)
    r_probe = {
        "action_id": r_action_id,
        "action_status": r_result.status.value,
        "status_reason": r_result.status_reason,
        "n_hits_before": r_before["n_hits"],
        "n_hits_after": r_after["n_hits"],
        "hash_changed": r_before["hash"] != r_after["hash"],
        "fields_changed": sorted({u.field for u in r_result.applied if u.n_new}),
    }
    cases["rpob"] = run_capability_case(
        name="divergent_rpob",
        expected_need=REMOTE_HOMOLOG_NOT_EXCLUDED,
        relevant_actions=set(HOMOLOGY_ACTIONS),
        m0=m0_r,
        assembly=r_asm,
        targets=r_tgt,
        settings=settings,
        out=rpob_dir,
        probe=r_probe,
    )

    tuf_dir = OUT / "hidden_tuf"
    m0_t, t_asm, t_tgt, _meta_t = rt_mod.build_test_b(tuf_dir / "fixture", settings)
    t_state = make_state(settings, t_asm, t_tgt, tuf_dir / "probe", m0_t.contig_sequences)
    t_run = _V2Run(state=t_state)
    t_run.capabilities = capabilities_for(t_state, m0_t)
    t_probe_m = copy.deepcopy(m0_t)
    n_loci_before = len(_loci(t_probe_m.hits, settings))
    t_result = apply_action_result(t_probe_m, _act_hmmer(t_run, t_probe_m, "search_target_domains_hmmer"))
    t_action_id = "search_target_domains_hmmer"
    if t_result.status is not ActionStatus.informative or len(_loci(t_probe_m.hits, settings)) <= n_loci_before:
        t_probe_m = copy.deepcopy(m0_t)
        t_result = apply_action_result(t_probe_m, _act_protein_search(t_run, t_probe_m, "search_target_proteins_mmseqs"))
        t_action_id = "search_target_proteins_mmseqs"
    t_probe = {
        "action_id": t_action_id,
        "action_status": t_result.status.value,
        "status_reason": t_result.status_reason,
        "n_loci_before": n_loci_before,
        "n_loci_after": len(_loci(t_probe_m.hits, settings)),
        "n_hits_after": len(t_probe_m.hits),
        "fields_changed": sorted({u.field for u in t_result.applied if u.n_new}),
        "hash_changed": measurement_fingerprint(m0_t)["hash"] != measurement_fingerprint(t_probe_m)["hash"],
    }
    cases["tuf"] = run_capability_case(
        name="hidden_tuf",
        expected_need=COPY_NUMBER_UNRESOLVED,
        relevant_actions=set(HOMOLOGY_ACTIONS),
        m0=m0_t,
        assembly=t_asm,
        targets=t_tgt,
        settings=settings,
        out=tuf_dir,
        probe=t_probe,
    )

    freeze = None
    gate_pass = (
        tests["pass"]
        and audit["pass"]
        and env["hmmer_available"]
        and env["similarity_search_available"]
        and all(case["pass"] for case in cases.values())
        and CURRENT_LACZ_LIMITATION
    )
    if gate_pass:
        freeze_mod = _load_module("freeze_agentic_v3_external", ROOT / "scripts" / "freeze_agentic_v3_external.py")
        freeze_main = freeze_mod.main

        freeze = freeze_main(
            {
                "environment": {
                    "hmmer_available": env["hmmer_available"],
                    "mmseqs_available": env["mmseqs_available"],
                    "diamond_available": env["diamond_available"],
                    "python": env["python"]["sys_executable"],
                },
                "unit_tests_pass": tests["pass"],
                "action_audit_pass": audit["pass"],
                "capability_pass": {name: case["pass"] for name, case in cases.items()},
                "current_lacz_limitation": LACZ_LIMITATION,
                "d8_rerun": False,
                "d20_touched": False,
            }
        )

    report = {
        "gate_pass": gate_pass,
        "environment": env,
        "unit_tests": {"pass": tests["pass"], "returncode": tests["returncode"]},
        "action_availability_audit": audit,
        "cases": {name: {k: v for k, v in case.items() if k != "routing"} | {"routing": case["routing"]} for name, case in cases.items()},
        "current_lacz_limitation": LACZ_LIMITATION,
        "freeze": freeze,
        "d8_rerun": False,
        "d20_touched": False,
        "written_utc": datetime.now(timezone.utc).isoformat(),
    }
    dump_json(OUT / "GATE_REPORT.json", report)
    _print_final(report)
    return 0 if gate_pass else 1


def _print_final(report: dict) -> None:
    env = report.get("environment") or {}
    tests = report.get("unit_tests") or {}
    cases = report.get("cases") or {}
    teta = cases.get("teta") or {}
    rpob = cases.get("rpob") or {}
    tuf = cases.get("tuf") or {}
    lines = [
        "V3 TESTS:",
        "PASS" if tests.get("pass") else ("FAIL" if tests else "NOT RUN"),
        "",
        "HMMER AVAILABLE:",
        "YES" if env.get("hmmer_available") else "NO",
        "",
        "MMSEQS AVAILABLE:",
        "YES" if env.get("mmseqs_available") else "NO",
        "",
        "DIAMOND AVAILABLE:",
        "YES" if env.get("diamond_available") else "NO",
        "",
        "TETA COMPETITIVE ACTION OFFERED:",
        "YES" if teta.get("relevant_action_offered") else "NO",
        "",
        "RPOB REMOTE-HOMOLOGY ACTION OFFERED:",
        "YES" if rpob.get("relevant_action_offered") else "NO",
        "",
        "TUF MULTIPLICITY ACTION OFFERED:",
        "YES" if tuf.get("relevant_action_offered") else "NO",
        "",
        "TETA INFORMATIVE ACTION EXECUTED:",
        "YES" if teta.get("informative_action_executed") else "NO",
        "",
        "RPOB INFORMATIVE ACTION EXECUTED:",
        "YES" if rpob.get("informative_action_executed") else "NO",
        "",
        "TUF INFORMATIVE ACTION EXECUTED:",
        "YES" if tuf.get("informative_action_executed") else "NO",
        "",
        "LACZ CURRENT TOOLBOX GAP:",
        "YES",
        "",
        "READY TO FREEZE V3:",
        "YES" if report.get("gate_pass") else "NO",
        "",
        "D8 RERUN:",
        "NO",
        "",
        "D20 TOUCHED:",
        "NO",
        "",
        "STOP.",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "FINAL_PRINT.txt").write_text(text, encoding="utf-8")
    print("\n" + text, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
