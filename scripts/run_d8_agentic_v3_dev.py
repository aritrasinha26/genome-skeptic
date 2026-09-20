#!/usr/bin/env python3
"""One D8 DEVELOPMENT replay of genome_skeptic_agentic_v3.

D8 is an unblinded development set. This is not external validation.
Does not modify frozen V5, frozen Agentic V2, or any previous prediction files.
Does not read, execute, modify, or score D20.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.agents.assembly_loop_v3 import SYSTEM_NAME, run_skeptic_agentic_v3
from genome_skeptic.agents.providers import reset_call_log
from genome_skeptic.config import load_settings
from genome_skeptic.families import load_family
from genome_skeptic.io_utils import iter_fasta_records

D8 = ROOT / "external_validation_agentic_d8"
MANIFEST = D8 / "D8_MANIFEST.json"
TRUTH = D8 / "D8_EXTERNAL_TRUTH_LOCKED.json"
V5_LOCKED = D8 / "D8_V5_LOCKED.json"
OUT = ROOT / "dev_work" / "agentic_v3_d8_dev"
TARGETS_FA = D8 / "inputs" / "targets.fa"
EMPTY_REFS = D8 / "inputs" / "references.yaml"
WSL_OLLAMA = "http://172.17.32.1:11434/v1"
D20_POOL = ROOT / "external_validation_agentic_d20" / "candidate_pool_manifest.json"
D20_POOL_SHA = "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c"

# From the existing D8 post-hoc diagnostic: useful existing actions on V5-wrong cases.
USEFUL_ACTIONS = {
    3: {
        "search_target_proteins_mmseqs",
        "search_target_proteins_diamond",
        "search_target_domains_hmmer",
        "inspect_contig_edges_for_target",
    },
    4: {
        "competitive_family",
        "reciprocal_best_hit_search",
        "compare_locus_to_reference",
        "inspect_synteny_neighborhood_for_target",
    },
    5: {
        "search_target_proteins_mmseqs",
        "search_target_proteins_diamond",
        "search_target_domains_hmmer",
    },
    6: {
        "competitive_family",
        "reciprocal_best_hit_search",
        "compare_locus_to_reference",
        "inspect_synteny_neighborhood_for_target",
    },
    7: {"competitive_family"},
}
V5_WRONG = (3, 4, 5, 6, 7)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_d20_untouched(when: str) -> None:
    if not D20_POOL.exists():
        print(f"D20 pool missing at {when}; not opened", flush=True)
        return
    digest = sha256_file(D20_POOL)
    if digest != D20_POOL_SHA:
        raise SystemExit(f"D20 pool hash changed {when}: {digest}")


def _llm_reachable(url: str) -> bool:
    root = (url or "").rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    try:
        urllib.request.urlopen(root + "/api/tags", timeout=2)
        return True
    except Exception:
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


def write_targets() -> None:
    if TARGETS_FA.exists():
        return
    chunks = []
    for fid in ("rpoB_RNAP_beta", "tuf_EF_Tu", "lacZ_beta_galactosidase", "tetA_tetracycline_efflux"):
        fam = load_family(fid)
        member = max(fam.members, key=lambda m: len(m.sequence or ""))
        chunks.append(f">{fid} target_type=gene_orthologue family={fid} length_aa={len(member.sequence)}\n{member.sequence}\n")
    TARGETS_FA.parent.mkdir(parents=True, exist_ok=True)
    TARGETS_FA.write_text("".join(chunks), encoding="utf-8")
    if not EMPTY_REFS.exists():
        EMPTY_REFS.write_text("references: []\n", encoding="utf-8")


def write_one_target(dest: Path, query_id: str) -> None:
    chosen = [(header, seq) for seq_id, header, seq in iter_fasta_records(TARGETS_FA) if seq_id == query_id]
    if not chosen:
        raise SystemExit(f"missing target {query_id}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    header, seq = chosen[0]
    dest.write_text(f">{header}\n{seq}\n", encoding="utf-8")


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def polarity(claim_type: str | None) -> str:
    text = (claim_type or "").lower()
    if "not_detected" in text or "unresolved" in text:
        return "not_detected"
    if "detected" in text:
        return "detected"
    return text or "unknown"


def v5_correct(pos: int, v5_row: dict, truth) -> bool:
    endpoint = str(truth.get("endpoint") or "")
    truth_val = truth.get("truth")
    v5_type = v5_row.get("final_result") or v5_row.get("claim_type")
    v5_pol = polarity(v5_type)
    if endpoint == "EXACT_MULTIPLICITY":
        multi = ((v5_row.get("multiplicity") or {}) or {}).get("number_of_candidate_loci")
        if multi is None:
            multi = 0 if v5_pol == "not_detected" else None
        try:
            return int(multi) == int(truth_val)
        except Exception:
            return False
    want = "detected" if str(truth_val).upper() == "POSITIVE" else "not_detected"
    return v5_pol == want


def v3_correct(pos: int, row: dict, truth) -> bool:
    if not row.get("ok"):
        return False
    endpoint = str(truth.get("endpoint") or "")
    truth_val = truth.get("truth")
    pol = polarity(row.get("final_result"))
    if endpoint == "EXACT_MULTIPLICITY":
        n = ((row.get("multiplicity") or {}) or {}).get("number_of_candidate_loci")
        if n is None:
            n = ((row.get("m_final") or {}) or {}).get("n_loci")
        if n is None and pol == "not_detected":
            n = 0
        try:
            return int(n) == int(truth_val)
        except Exception:
            return False
    want = "detected" if str(truth_val).upper() == "POSITIVE" else "not_detected"
    return pol == want


def run_one(acc: str, target: str, assembly: Path, settings, organism: str | None, pos: int) -> dict:
    case_dir = OUT / "runs" / acc / target / SYSTEM_NAME
    case_dir.mkdir(parents=True, exist_ok=True)
    one = case_dir / "target.fa"
    write_one_target(one, target)
    print(f"AGENTIC V3 DEV pos={pos} {acc} {target}", flush=True)
    reset_call_log()
    t0 = time.perf_counter()
    try:
        claims, _loci, provenance = run_skeptic_agentic_v3(
            assembly,
            one,
            case_dir,
            settings,
            query_ids=[target],
            declared_organism=organism,
            references=EMPTY_REFS if EMPTY_REFS.exists() else None,
        )
        claim = claims[0] if claims else None
        m0 = ((provenance.get("measurement_state") or {}).get("m0") or {})
        m_final = ((provenance.get("measurement_state") or {}).get("m_final") or {})
        actions = provenance.get("actions_executed") or []
        ctype = claim.claim_type.value if claim is not None else None
        fam = load_json(case_dir / "family" / target / "family_evidence.json") or {}
        recon = fam.get("reconstruction") or {}
        multi = fam.get("multiplicity") or recon.get("multiplicity") or {}
        n_loci = multi.get("number_of_candidate_loci")
        if n_loci is None:
            n_loci = m_final.get("n_loci")
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": SYSTEM_NAME,
            "ok": provenance.get("agent_failure") is None and provenance.get("final_validator_ran") is True,
            "runtime_seconds": provenance.get("seconds") or round(time.perf_counter() - t0, 3),
            "planner_action": provenance.get("selected_action"),
            "planner_control_decision": provenance.get("control_decision"),
            "planner_grounding_status": provenance.get("planner_grounding_status"),
            "planner_control_failure": provenance.get("planner_control_failure"),
            "critic_action": provenance.get("critic_second_action"),
            "critic_invoked": provenance.get("critic_invoked"),
            "actions_executed": [a.get("action_id") if isinstance(a, dict) else a for a in actions],
            "action_results": [
                {
                    "action_id": a.get("action_id"),
                    "status": a.get("status"),
                    "requested_by": None,
                }
                for a in actions
                if isinstance(a, dict)
            ],
            "m0": {"hash": m0.get("hash"), "n_hits": m0.get("n_hits"), "n_loci": m0.get("n_loci")},
            "m_final": {
                "hash": m_final.get("hash"),
                "n_hits": m_final.get("n_hits"),
                "n_loci": n_loci if n_loci is not None else m_final.get("n_loci"),
            },
            "architecture": fam.get("architecture") or (claim.architecture_state if claim is not None else None),
            "multiplicity": {
                "number_of_candidate_loci": n_loci,
                "classification": multi.get("classification") if isinstance(multi, dict) else None,
            },
            "measurements_changed": provenance.get("measurements_changed_before_validation"),
            "ranked_candidate_actions": provenance.get("ranked_candidate_actions"),
            "diagnostic_needs_m0": provenance.get("diagnostic_needs_m0"),
            "agent_failure": provenance.get("agent_failure"),
            "final_validator_ran": provenance.get("final_validator_ran"),
            "final_result": ctype,
            "claim_class": claim.status.value if claim is not None else None,
            "confidence": claim.confidence if claim is not None else None,
            "statement": claim.statement if claim is not None else None,
            "model_call_count": provenance.get("model_call_count"),
        }
        for step, executed in zip(provenance.get("measurement_trajectory") or [], row["action_results"]):
            executed["requested_by"] = step.get("requested_by")
            executed["status"] = step.get("status")
    except Exception as exc:
        row = {
            "assembly_accession": acc,
            "target": target,
            "system": SYSTEM_NAME,
            "ok": False,
            "agent_failure": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "runtime_seconds": round(time.perf_counter() - t0, 3),
        }
        print(f"FAIL V3 {acc} {target}: {exc}", flush=True)
    (case_dir / "v3_dev_case.json").write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        f"V3 DEV DONE pos={pos} ok={row.get('ok')} action={row.get('planner_action')} "
        f"critic={row.get('critic_action')} fail={row.get('agent_failure')}",
        flush=True,
    )
    return row


def main() -> int:
    assert_d20_untouched("start")
    v5_lock = json.loads(V5_LOCKED.read_text(encoding="utf-8"))
    truth_lock = json.loads(TRUTH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = sorted(manifest["cases"], key=lambda r: (r["execution_hash"], r["assembly_accession"]))
    truth_by_pos = {int(r["execution_position"]): r for r in truth_lock.get("cases") or truth_lock.get("truth") or []}
    if not truth_by_pos:
        # D8_EXTERNAL_TRUTH_LOCKED.json uses "cases" or a predictions-like list
        blob = truth_lock.get("records") or truth_lock.get("predictions") or []
        for r in blob:
            pos = int(r.get("execution_position") or r.get("pos") or 0)
            if pos:
                truth_by_pos[pos] = r
    v5_by_pos = {}
    for r in v5_lock.get("predictions") or []:
        # recover position from accession+target against manifest
        for rec in cases:
            if rec["assembly_accession"] == r.get("assembly_accession") and rec["target"] == r.get("target"):
                v5_by_pos[int(rec["execution_position"])] = r
                break
    write_targets()
    settings = load_settings(ROOT / "config" / "qwen_agentic_dev.yaml")
    remap = _fix_llm_host(settings)
    print("OLLAMA_REMAP", remap, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for rec in cases:
        acc = rec["assembly_accession"]
        target = rec["target"]
        pos = int(rec["execution_position"])
        src = ROOT / rec["solver_fasta"]
        if not src.exists():
            raise SystemExit(f"missing D8 FASTA {src}")
        if sha256_file(src) != rec["fasta_sha256"]:
            raise SystemExit(f"FASTA changed {acc}")
        rows.append(run_one(acc, target, src, settings, rec.get("organism"), pos))
    # join truth/v5
    table = []
    completed = 0
    useful = 0
    corrections = []
    degradations = []
    engineering = []
    for rec, row in zip(cases, rows):
        pos = int(rec["execution_position"])
        truth = truth_by_pos.get(pos) or {}
        v5 = v5_by_pos.get(pos) or {}
        v5_ok = v5_correct(pos, v5, truth)
        v3_ok = v3_correct(pos, row, truth)
        executed = set(row.get("actions_executed") or [])
        useful_hit = bool(executed & USEFUL_ACTIONS.get(pos, set()))
        if row.get("ok"):
            completed += 1
        else:
            engineering.append(f"pos {pos}: {row.get('agent_failure')}")
        if pos in V5_WRONG and useful_hit:
            useful += 1
        if (not v5_ok) and v3_ok:
            corrections.append(pos)
        if v5_ok and not v3_ok:
            degradations.append(pos)
        who = "none"
        if row.get("planner_action") and row.get("critic_action"):
            who = "planner+critic"
        elif row.get("planner_action"):
            who = "planner"
        elif row.get("critic_action"):
            who = "critic"
        table.append(
            {
                "pos": pos,
                "accession": rec["assembly_accession"],
                "target": rec["target"],
                "completed": bool(row.get("ok")),
                "useful_action_executed": useful_hit,
                "planner_action": row.get("planner_action"),
                "critic_action": row.get("critic_action"),
                "action_source": who,
                "m0": row.get("m0"),
                "m_final": row.get("m_final"),
                "final_result": row.get("final_result"),
                "v5_result": v5.get("final_result") or v5.get("claim_class"),
                "truth": truth.get("truth"),
                "v3_correct": v3_ok,
                "v5_correct": v5_ok,
                "runtime": row.get("runtime_seconds"),
                "agent_failure": row.get("agent_failure"),
                "grounding": row.get("planner_grounding_status"),
                "diagnostic_needs_m0": row.get("diagnostic_needs_m0"),
            }
        )
    report = {
        "kind": "D8_AGENTIC_V3_DEVELOPMENT",
        "not_external_validation": True,
        "system": SYSTEM_NAME,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(table),
        "completion": completed,
        "useful_action_executed_on_v5_wrong": useful,
        "corrections": corrections,
        "degradations": degradations,
        "engineering_failures": engineering,
        "cases": table,
        "d20_touched": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "D8_V3_DEV_RESULTS.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    lines = [
        "# D8 Agentic V3 development replay",
        "",
        "Not external validation. Frozen V2/V5 prediction files were not modified.",
        "",
        "| Pos | Accession | Target | Done | Useful? | Planner | Critic | m0 n_hits | m_final n_hits | V3 | V5 | Truth | Runtime | Failure |",
        "|---:|---|---|---|---|---|---|---:|---:|---|---|---|---:|---|",
    ]
    for r in table:
        lines.append(
            f"| {r['pos']} | {r['accession']} | {r['target']} | "
            f"{'yes' if r['completed'] else 'no'} | {'yes' if r['useful_action_executed'] else 'no'} | "
            f"{r['planner_action'] or '—'} | {r['critic_action'] or '—'} | "
            f"{(r['m0'] or {}).get('n_hits')} | {(r['m_final'] or {}).get('n_hits')} | "
            f"{r['final_result']} | {r['v5_result']} | {r['truth']} | {r['runtime']} | {r['agent_failure'] or ''} |"
        )
    lines.extend(
        [
            "",
            f"D8 DEVELOPMENT COMPLETION: {completed} / 8",
            f"USEFUL ACTION EXECUTED UNDER V3: {useful} / 5",
            f"D8 V3 DEVELOPMENT CORRECTIONS: {corrections or 'none'}",
            f"D8 V3 DEVELOPMENT DEGRADATIONS: {degradations or 'none'}",
            f"ENGINEERING FAILURES: {engineering or 'none'}",
            "D20 TOUCHED: NO",
        ]
    )
    (OUT / "D8_V3_DEV_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"completion": completed, "useful": useful, "corrections": corrections, "degradations": degradations}, indent=2), flush=True)
    assert_d20_untouched("end")
    print("D20 TOUCHED: NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
