"""Convert locked Genome Skeptic records into structures the UI can render.

Every value returned here is copied from a recorded field. When a field was not
recorded, the helpers return ``NOT_AVAILABLE`` instead of guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NOT_AVAILABLE = "Not available"
NOT_EVALUATED = "Not evaluated"

TARGET_INFO: dict[str, dict[str, str]] = {
    "tetA_tetracycline_efflux": {
        "short": "tetA",
        "display": "Tetracycline efflux pump TetA/TetB (MFS transporter)",
        "endpoint": (
            "tet(A)/tet(B) family identity: not generic tetracycline resistance and not any MFS transporter "
            "(M60 protocol §8)."
        ),
        "competitors": "MFS multidrug efflux and RND efflux families",
    },
    "rpoB_RNAP_beta": {
        "short": "rpoB",
        "display": "RNA polymerase subunit beta (RpoB)",
        "endpoint": (
            "Full-length RNA polymerase beta orthologue: not a domain-only hit and not a different polymerase "
            "subunit (M60 protocol §8)."
        ),
        "competitors": "RNA polymerase beta-prime (rpoC) as partner/competitor family",
    },
}

ARM_LABELS = {
    "GS_DETERMINISTIC_V4_1": "GS-Deterministic (fixed follow-up policy, no LLM)",
    "GS_AGENTIC_V4_1": "GS-Agentic (LLM planner + critic choose follow-ups)",
    "GS_EXHAUSTIVE_V4_1": "GS-Exhaustive (every eligible follow-up, no LLM)",
}

STATUS_GLOSS = {
    "supported": "The executed attack plan found no successful disproof. This is a claim state, not certainty.",
    "weakened": "At least one completed falsification test weakened the claim.",
    "unresolved": "A blocking falsification test could not be completed.",
    "rejected": "A completed falsification test rejected the claim.",
}

CLAIM_TYPE_LABEL = {
    "target_gene_detected": "Detected",
    "target_gene_not_detected": "Not detected",
}

ENDPOINT_LABEL = {"POSITIVE": "Present", "NEGATIVE": "Absent", "UNRESOLVED": "Unresolved"}

TRUTH_GLOSS = {
    "POSITIVE": "Independent adjudication: target present",
    "NEGATIVE": "Independent adjudication: target absent",
    "TRUTH_UNCERTAIN": "Independent adjudication could not resolve truth; excluded from accuracy",
}

ACTION_GLOSS = {
    "inspect_contig_edges_for_target": "Recompute whether hits sit at a contig edge (possible truncation).",
    "inspect_hit_contig_contamination": "Compare GC content of the hit contig with the genome (possible contaminant).",
    "competitive_family": "Score the candidate against competing protein families (e.g. other MFS/RND efflux pumps).",
    "search_target_proteins_mmseqs": "Protein-level search of predicted ORFs with MMseqs2.",
    "search_target_proteins_diamond": "Protein-level search of predicted ORFs with DIAMOND.",
    "search_target_domains_hmmer": "Profile-HMM domain search with HMMER.",
    "discriminate_ortholog_references": "Compare the candidate with an independent orthology reference set.",
    "inspect_paralogue_copies": "Cluster hits into loci to look for paralogous copies.",
    "inspect_catalytic_residues": "Report catalytic residues declared on the profile.",
    "search_target_genes_nucleotide": "Nucleotide search of the assembly (BLAST).",
    "search_target_genes_translated": "Translated search of the assembly (tBLASTn).",
}


def label_or_na(value: Any) -> str:
    if value is None or value == "" or value == []:
        return NOT_AVAILABLE
    return str(value)


def target_short(target: str) -> str:
    return TARGET_INFO.get(target, {}).get("short", target)


def endpoint_label(pred: str | None) -> str:
    if not pred:
        return NOT_AVAILABLE
    return ENDPOINT_LABEL.get(pred, pred)


def correctness_label(flag: str | None, evaluable: bool) -> str:
    if not evaluable:
        return NOT_EVALUATED
    if flag == "True":
        return "Correct"
    if flag == "False":
        return "Incorrect"
    return NOT_AVAILABLE


def biological_question(case: dict[str, Any]) -> str:
    info = TARGET_INFO.get(case["target"])
    name = info["display"] if info else case["target"]
    return (
        f"Is a genuine {name} gene present in the public RefSeq assembly {case['accession']} "
        f"({case['organism']})?"
    )


def evidence_by_id(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {e["id"]: e for e in evidence or [] if isinstance(e, dict) and e.get("id")}


def find_evidence(evidence: list[dict[str, Any]], summary_prefix: str) -> dict[str, Any] | None:
    for e in evidence or []:
        if str(e.get("summary", "")).startswith(summary_prefix):
            return e
    return None


# ---------------------------------------------------------------------------
# Arm comparison
# ---------------------------------------------------------------------------

def arm_comparison(trace: dict[str, Any]) -> list[dict[str, Any]]:
    case = trace["case"]
    ev = bool(case.get("evaluable"))
    spec_tool = case.get("specialist_tool") or "Specialist"
    spec_name = {
        "AMRFinderPlus": "AMRFinderPlus 4.2.7 (specialist comparator)",
        "NCBI_RefSeq_PGAP": "NCBI RefSeq/PGAP annotation (specialist comparator)",
    }.get(spec_tool, spec_tool)
    rows = [
        ("Conventional homology baseline (≥80% identity and coverage)", "conventional", None),
        (spec_name, "specialist", None),
        (ARM_LABELS["GS_DETERMINISTIC_V4_1"], "gs_det", "GS_DETERMINISTIC_V4_1"),
        (ARM_LABELS["GS_AGENTIC_V4_1"], "gs_agent", "GS_AGENTIC_V4_1"),
        (ARM_LABELS["GS_EXHAUSTIVE_V4_1"], "gs_exh", "GS_EXHAUSTIVE_V4_1"),
    ]
    out = []
    for label, key, arm in rows:
        rec = (trace["arms"].get(arm) or {}) if arm else {}
        claim = rec.get("claim")
        locked = rec.get("locked")
        executed = (rec.get("provenance") or {}).get("actions_executed")
        out.append(
            {
                "System": label,
                "Endpoint": endpoint_label(case.get(f"{key}_pred")),
                "Correct vs truth": correctness_label(case.get(f"{key}_correct"), ev),
                "Claim status": label_or_na(claim.get("status") if claim else None),
                "Evidence score": claim.get("confidence") if claim else None,
                "Follow-up analyses": len(executed) if isinstance(executed, list) else None,
                "Runtime (s)": _float_or_none(locked.get("runtime_seconds")) if locked else None,
            }
        )
    return out


def _int_or_none(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v: Any) -> float | None:
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Inside the annotation engine: step-by-step trace
# ---------------------------------------------------------------------------

KIND_MEASUREMENT = "Raw biological evidence (deterministic tool)"
KIND_RANKER = "Deterministic action ranking"
KIND_MODEL = "Model-generated interpretation (LLM planner)"
KIND_CRITIC = "Critic assessment (LLM critic)"
KIND_DECISION = "Final system decision (deterministic validator)"
KIND_CONTEXT = "Question under test"


@dataclass
class EngineStep:
    number: int
    kind: str
    title: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)


def engine_steps(trace: dict[str, Any], arm: str = "GS_AGENTIC_V4_1") -> list[EngineStep]:
    case = trace["case"]
    rec = trace["arms"][arm]
    prov = rec.get("provenance") or {}
    claim = rec.get("claim") or {}
    evidence = rec.get("evidence") or []
    ev = evidence_by_id(evidence)
    steps: list[EngineStep] = []

    def add(kind: str, title: str, summary: str, details: dict[str, Any] | None = None, ids: list[str] | None = None):
        steps.append(EngineStep(len(steps) + 1, kind, title, summary, details or {}, list(ids or [])))

    add(
        KIND_CONTEXT,
        "Biological question",
        biological_question(case),
        {"Exact endpoint": TARGET_INFO.get(case["target"], {}).get("endpoint", NOT_AVAILABLE)},
    )

    before = prov.get("evidence_ids_before_action") or []
    hits_ev = find_evidence(evidence, "Homology hits")
    tools = (hits_ev or {}).get("values", {}).get("tools_run") or []
    unavailable = (hits_ev or {}).get("values", {}).get("tools_unavailable") or []
    add(
        KIND_MEASUREMENT,
        "Initial measurements (m0)",
        f"Shared initial measurement ran {', '.join(tools) if tools else NOT_AVAILABLE}. "
        f"Recorded as evidence {', '.join(before) if before else NOT_AVAILABLE}.",
        {
            "Evidence records": [{"id": i, "summary": ev.get(i, {}).get("summary", NOT_AVAILABLE)} for i in before],
            "Instruments unavailable in this run": unavailable or ["none recorded"],
            "Locus reconstruction (m0)": prov.get("locus_stages_m0") or NOT_AVAILABLE,
        },
        before,
    )

    needs = prov.get("diagnostic_needs_m0") or []
    ranked = prov.get("ranked_candidate_actions") or []
    add(
        KIND_RANKER,
        "Open diagnostic needs and eligible follow-up tests",
        (
            f"{len(needs)} open diagnostic need(s): "
            + (", ".join(n.get("need", "?") for n in needs) if needs else "none")
            + f". {len(ranked)} registered action(s) offered: "
            + (", ".join(r.get("action_id", "?") for r in ranked) if ranked else "none")
            + "."
        ),
        {
            "Diagnostic needs (m0)": needs or NOT_AVAILABLE,
            "Ranked candidate actions": [
                {
                    "action_id": r.get("action_id"),
                    "what it does": ACTION_GLOSS.get(r.get("action_id"), NOT_AVAILABLE),
                    "tests need": ", ".join(r.get("tests") or []),
                    "priority_score": r.get("priority_score"),
                }
                for r in ranked
            ]
            or NOT_AVAILABLE,
            "Actions excluded as inert": prov.get("inert_actions") or NOT_AVAILABLE,
        },
    )

    actions = prov.get("actions_executed") or []
    if arm == "GS_AGENTIC_V4_1":
        planner = rec.get("planner_decision") or {}
        call_log = rec.get("model_call_log") or []
        planner_call = next((c for c in call_log if c.get("request_type") == "PlannerDecision"), {})
        add(
            KIND_MODEL,
            "Planner selects a follow-up test",
            (
                f"Planner ({prov.get('model_name') or NOT_AVAILABLE}) requested "
                f"{', '.join(planner.get('requested_actions') or []) or NOT_AVAILABLE}. "
                f"Recorded rationale: “{planner.get('rationale') or NOT_AVAILABLE}”"
            ),
            {
                "Decision": planner.get("decision") or NOT_AVAILABLE,
                "Alternative explanations named": planner.get("alternative_explanations") or [],
                "Evidence IDs cited by planner": planner.get("evidence_ids") or [],
                "Grounding status (were cited evidence IDs valid and present?)": prov.get("planner_grounding_status")
                or NOT_AVAILABLE,
                "Schema-valid JSON": planner_call.get("schema_valid", NOT_AVAILABLE),
                "Model latency (s)": planner_call.get("elapsed_seconds", NOT_AVAILABLE),
                "Prompt SHA256": prov.get("prompt_hash") or NOT_AVAILABLE,
            },
            planner.get("evidence_ids") or [],
        )
    elif actions:
        add(
            KIND_RANKER,
            "Policy selects follow-up tests",
            f"{ARM_LABELS.get(arm, arm)} executed {len(actions)} follow-up(s) without a language model.",
        )

    first_actions = actions[:1] if arm == "GS_AGENTIC_V4_1" else actions
    for a in first_actions:
        steps.append(_action_step(len(steps) + 1, a, ev))

    if arm == "GS_AGENTIC_V4_1":
        critic = rec.get("critic_review") or {}
        challenge = prov.get("critic_challenge") or {}
        verdict = challenge.get("verdict") or critic.get("verdict")
        add(
            KIND_CRITIC,
            "Critic reviews the plan and the new evidence",
            (
                f"Verdict: {verdict or NOT_AVAILABLE}. "
                f"Recorded rationale: “{critic.get('rationale') or challenge.get('rationale') or NOT_AVAILABLE}”"
            ),
            {
                "Evidence IDs cited by critic": critic.get("evidence_ids") or [],
                "Failure modes named": critic.get("failure_modes") or challenge.get("failure_modes") or [],
                "Disconfirming tests proposed": critic.get("disconfirming_tests")
                or challenge.get("disconfirming_tests")
                or [],
                "Second action triggered": prov.get("critic_second_action") or "none",
                "Why": prov.get("critic_second_action_reason") or NOT_AVAILABLE,
            },
            critic.get("evidence_ids") or [],
        )
        for a in actions[1:]:
            steps.append(_action_step(len(steps) + 1, a, ev, requested_by="critic"))

    ms = prov.get("measurement_state") or {}
    tests = claim.get("falsification_tests") or []
    completed = [t for t in tests if t.get("status") == "completed"]
    add(
        KIND_DECISION,
        "Deterministic validator issues the claim",
        (
            f"{CLAIM_TYPE_LABEL.get(claim.get('claim_type'), label_or_na(claim.get('claim_type')))}; "
            f"status '{label_or_na(claim.get('status'))}'. "
            f"{len(completed)} of {len(tests)} falsification tests completed. "
            f"The validator consumed the final measurement state "
            f"({'yes' if prov.get('validator_consumed_measurement_hash') else NOT_AVAILABLE}); "
            f"language-model text entered the claim: "
            f"{'no' if prov.get('llm_measurement_entered_claim') is False else label_or_na(prov.get('llm_measurement_entered_claim'))}."
        ),
        {
            "Statement": claim.get("statement") or NOT_AVAILABLE,
            "Status meaning": STATUS_GLOSS.get(claim.get("status"), NOT_AVAILABLE),
            "Evidence score (uncalibrated)": claim.get("confidence"),
            "Evidence completeness": claim.get("evidence_completeness"),
            "Architecture": claim.get("architecture_state") or NOT_AVAILABLE,
            "Measurement hash m0 → final": f"{(ms.get('m0') or {}).get('hash', '?')[:12]} → "
            f"{(ms.get('m_final') or {}).get('hash', '?')[:12]}",
            "Validator rationale": claim.get("rationale") or NOT_AVAILABLE,
        },
        claim.get("supporting_evidence_ids") or [],
    )
    return steps


def _action_step(number: int, a: dict[str, Any], ev: dict[str, dict[str, Any]], requested_by: str | None = None) -> EngineStep:
    aid = a.get("action_id", "?")
    who = f" (requested by {requested_by})" if requested_by else ""
    return EngineStep(
        number,
        KIND_MEASUREMENT,
        f"Registered tool runs: {aid}{who}",
        (
            f"{ACTION_GLOSS.get(aid, '')} Result: {a.get('status', NOT_AVAILABLE)}"
            f" — {a.get('status_reason') or a.get('summary') or ''}"
        ).strip(),
        {
            "Updated measurement fields": a.get("updated_measurement_fields") or [],
            "New measurements": a.get("n_new_measurements"),
            "Limitation": a.get("limitation") or "none recorded",
            "Evidence records": [
                {"id": i, "summary": ev.get(i, {}).get("summary", NOT_AVAILABLE)} for i in a.get("evidence_ids") or []
            ],
        },
        list(a.get("evidence_ids") or []),
    )


# ---------------------------------------------------------------------------
# Evidence explorer
# ---------------------------------------------------------------------------

def hits_table(trace: dict[str, Any], arm: str = "GS_AGENTIC_V4_1") -> list[dict[str, Any]]:
    evidence = trace["arms"][arm].get("evidence") or []
    hits_ev = find_evidence(evidence, "Homology hits")
    rows = []
    for h in (hits_ev or {}).get("values", {}).get("hits") or []:
        rows.append(
            {
                "Evidence ID": hits_ev["id"],
                "Tool": h.get("tool") or NOT_AVAILABLE,
                "Search": h.get("search_kind") or NOT_AVAILABLE,
                "Contig": h.get("contig_id"),
                "Start": h.get("tstart"),
                "End": h.get("tend"),
                "Strand": h.get("strand"),
                "Identity": _round(h.get("identity")),
                "Query coverage": _round(h.get("query_coverage")),
                "E-value": h.get("evalue"),
                "Near contig edge": h.get("near_contig_edge"),
            }
        )
    return rows


def member_hits_table(trace: dict[str, Any], arm: str = "GS_AGENTIC_V4_1") -> list[dict[str, Any]]:
    fam = find_evidence(trace["arms"][arm].get("evidence") or [], "Family orthology")
    rows = []
    for h in (fam or {}).get("values", {}).get("member_hit_summaries") or []:
        rows.append(
            {
                "Evidence ID": fam["id"],
                "Reference protein": h.get("query_id"),
                "Identity": _round(h.get("identity")),
                "Query coverage": _round(h.get("query_coverage")),
                "E-value": h.get("evalue"),
                "Contig": h.get("contig_id"),
                "Start": h.get("tstart"),
                "End": h.get("tend"),
            }
        )
    return rows


def family_summary(trace: dict[str, Any], arm: str = "GS_AGENTIC_V4_1") -> dict[str, Any] | None:
    fam = find_evidence(trace["arms"][arm].get("evidence") or [], "Family orthology")
    if not fam:
        return None
    v = fam.get("values", {})
    m = v.get("metrics") or {}
    return {
        "Evidence ID": fam["id"],
        "Family": v.get("family_id"),
        "Architecture": v.get("architecture"),
        "Evidence hierarchy reached": v.get("hierarchy") or [],
        "Supports orthologue": v.get("supports_orthologue"),
        "Domain-only": v.get("domain_only"),
        "Fusion / split / fragmented / paralogue": {
            k: (v.get(k) or {}).get("state") for k in ("fusion", "split", "fragmented", "paralogue")
        },
        "Best HMM": v.get("best_hmm") or NOT_AVAILABLE,
        "Metrics": m,
        "Limitations": v.get("limitations") or [],
    }


def attack_plan_rows(claim: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    for t in (claim or {}).get("falsification_tests") or []:
        rows.append(
            {
                "Test": t.get("name"),
                "Hypothesis that would disprove the claim": t.get("hypothesis"),
                "Blocking": t.get("blocking"),
                "Status": t.get("status"),
                "Result": t.get("result"),
                "Limitation": t.get("limitation") or "",
            }
        )
    return rows


def conflicts(trace: dict[str, Any]) -> dict[str, Any]:
    """Disagreements and open questions recorded for a case."""
    case = trace["case"]
    claim = trace["arms"]["GS_AGENTIC_V4_1"].get("claim") or {}
    preds = {
        "Conventional": case.get("conventional_pred"),
        "Specialist": case.get("specialist_pred"),
        "GS-Deterministic": case.get("gs_det_pred"),
        "GS-Agentic": case.get("gs_agent_pred"),
        "GS-Exhaustive": case.get("gs_exh_pred"),
    }
    distinct = sorted({p for p in preds.values() if p})
    remediation = trace.get("amrfinder_remediation")
    rem_changed = bool(remediation and remediation.get("binary_call") != remediation.get("old_call"))
    return {
        "systems_disagree": len(distinct) > 1,
        "predictions": preds,
        "alternative_explanations": claim.get("alternative_explanations") or [],
        "unavailable_tests": claim.get("unavailable_tests") or [],
        "unresolved_tests": claim.get("unresolved_tests") or [],
        "truth_status": case.get("truth_status"),
        "amrfinder_remediation_changed_call": rem_changed,
        "amrfinder_remediation": remediation,
    }


def _round(v: Any, nd: int = 3) -> Any:
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


# ---------------------------------------------------------------------------
# Index views
# ---------------------------------------------------------------------------

def index_table(index: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for c in index:
        rows.append(
            {
                "Position": c["position"],
                "Organism": c["organism"],
                "Accession": c["accession"],
                "Target": target_short(c["target"]),
                "Stratum": c["stratum"],
                "Truth": c["truth"],
                "GS-Agentic endpoint": endpoint_label(c.get("gs_agent_pred")),
                "GS-Agentic vs truth": correctness_label(c.get("gs_agent_correct"), c.get("evaluable", False)),
                "Claim status": label_or_na(c.get("agent_claim_status")),
                "Evidence score": c.get("agent_confidence"),
                "Architecture": label_or_na(c.get("agent_architecture")),
                "Planner action": label_or_na(c.get("planner_action")),
                "Critic verdict": label_or_na(c.get("critic_verdict")),
                "Conventional": endpoint_label(c.get("conventional_pred")),
                "Specialist": endpoint_label(c.get("specialist_pred")),
            }
        )
    return rows


def case_option_label(c: dict[str, Any]) -> str:
    return (
        f"#{c['position']:02d} · {target_short(c['target'])} · {c['organism']} "
        f"({c['accession']}) · truth {c['truth']}"
    )
