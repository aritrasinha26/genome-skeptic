"""Agentic V3 control-flow tests. Frozen V2 tests are not modified."""
from pathlib import Path

import pytest

from genome_skeptic.agents.action_catalog_v3 import (
    INERT_ACTION_IDS,
    executable_actions_before_ranking,
    rank_candidate_actions,
)
from genome_skeptic.agents.action_contract import (
    ABSTAIN_UNRESOLVED,
    FINALIZE_WITH_CURRENT_EVIDENCE,
    ActionResult,
    ActionStatus,
    MeasurementPatch,
    PatchRejected,
    apply_action_result,
    measurement_fingerprint,
)
from genome_skeptic.agents.assembly_loop_v3 import (
    GROUNDING_MISSING,
    _validate_planner_v3,
    run_skeptic_agentic_v3,
    select_critic_action_v3,
)
from genome_skeptic.agents.diagnostic_needs import (
    CONTAMINATION_UNRESOLVED,
    COPY_NUMBER_UNRESOLVED,
    FAMILY_IDENTITY_UNRESOLVED,
    REMOTE_HOMOLOG_NOT_EXCLUDED,
    derive_diagnostic_needs,
)
from genome_skeptic.config import Settings
from genome_skeptic.models import AgentDecision, CriticReview, GeneSearchHit, TargetProfile
from genome_skeptic.validators.falsification import TargetMeasurements

GENE = "ATG" + ("CGTAGC") * 20 + "TAA"


def _profile(**kwargs) -> TargetProfile:
    data = {"query_id": "rpoB", "sequence": GENE}
    data.update(kwargs)
    return TargetProfile.model_validate(data)


def _hit(**kwargs) -> GeneSearchHit:
    data = {
        "query_id": "rpoB",
        "contig_id": "c1",
        "search_kind": "nucleotide",
        "qstart": 0,
        "qend": len(GENE),
        "tstart": 500,
        "tend": 500 + len(GENE),
        "strand": "+",
        "identity": 0.95,
        "query_coverage": 0.98,
        "alignment_length": len(GENE),
        "query_length": len(GENE),
        "contig_length": 2000,
    }
    data.update(kwargs)
    return GeneSearchHit.model_validate(data)


def _measurements(hits=None, **kwargs) -> TargetMeasurements:
    profile = _profile()
    return TargetMeasurements(query_id=profile.query_id, profile=profile, hits=list(hits or []), **kwargs)


def _fit_schema(schema, data: dict):
    payload = dict(data)
    if "disconfirming_tests" in payload and "requested_action" not in payload:
        tests = payload.get("disconfirming_tests") or []
        payload["requested_action"] = tests[0] if tests else None
    if "failure_modes" in payload and "failure_mode" not in payload:
        modes = payload.get("failure_modes") or []
        payload["failure_mode"] = modes[0] if modes else None
    if "requested_actions" in payload and "requested_action" not in payload:
        acts = payload.get("requested_actions") or []
        payload["requested_action"] = acts[0] if acts else None
    alts = payload.get("alternative_explanations") or []
    if alts:
        payload.setdefault("leading_hypothesis", alts[0])
        if len(alts) > 1:
            payload.setdefault("alternative_hypothesis", alts[1])
    dec = payload.get("decision")
    action = payload.get("requested_action")
    if dec in {"continue", "rerun"}:
        payload["decision"] = "investigate"
    elif dec in {"ask_human", "stop"}:
        payload["decision"] = "abstain"
    if action == FINALIZE_WITH_CURRENT_EVIDENCE:
        payload["decision"] = "finalize"
    elif action == ABSTAIN_UNRESOLVED and payload.get("decision") not in {"investigate", "finalize", "abstain"}:
        payload["decision"] = "abstain"
    if payload.get("decision") not in {"investigate", "finalize", "abstain", "accept", "challenge", None}:
        payload["decision"] = "investigate"
    fields = getattr(schema, "model_fields", payload)
    return schema.model_validate({k: v for k, v in payload.items() if k in fields})


def _write_case(tmp_path: Path) -> tuple[Path, Path]:
    from genome_skeptic.eval.synthetic import DNAA, RPOB, RPOC, _fa, _operon

    seq, _genes = _operon([("dnaA", DNAA), ("rpoB", RPOB), ("rpoC", RPOC)])
    assembly = tmp_path / "assembly.fa"
    assembly.write_text(_fa({"c1": seq}))
    targets = tmp_path / "targets.fa"
    targets.write_text(f">rpoB\n{RPOB}\n")
    return assembly, targets


def _action_from_payload(payload: dict) -> str:
    rows = payload.get("available_actions") or []
    if rows:
        return rows[0]["action_id"]
    return FINALIZE_WITH_CURRENT_EVIDENCE


_VALID = "__VALID__"


def _sequenced_llm(monkeypatch, planner_responses, critic_responses):
    counts = {"planner": 0, "critic": 0}

    def _pick(queue, key):
        spec = queue[min(counts[key], len(queue) - 1)]
        counts[key] += 1
        return dict(spec)

    def _resolve(spec, payload):
        out = dict(spec)
        if out.get("evidence_ids") == [_VALID]:
            out["evidence_ids"] = [payload["valid_evidence_ids"][0]]
        if out.get("requested_actions") == ["__AVAILABLE__"]:
            out["requested_actions"] = [_action_from_payload(payload)]
            out["requested_action"] = out["requested_actions"][0]
        if out.get("requested_action") == "__AVAILABLE__":
            out["requested_action"] = _action_from_payload(payload)
            out["requested_actions"] = [out["requested_action"]]
        return out

    class _Stub:
        def __init__(self, cfg):
            self.cfg = cfg

        def ask_json(self, system, payload, schema):
            if schema.__name__ in {"AgentDecision", "PlannerDecision"}:
                base = {"decision": "continue", "rationale": "stub", "alternative_explanations": ["true_presence"]}
                return _fit_schema(schema, {**base, **_resolve(_pick(planner_responses, "planner"), payload)})
            base = {"verdict": "accept", "rationale": "stub"}
            return _fit_schema(schema, {**base, **_resolve(_pick(critic_responses, "critic"), payload)})

    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v3.OllamaJSONClient", _Stub)
    return counts


def _run_sequenced(tmp_path, monkeypatch, planner_responses, critic_responses):
    assembly, targets = _write_case(tmp_path)
    counts = _sequenced_llm(monkeypatch, planner_responses, critic_responses)
    claims, _loci, prov = run_skeptic_agentic_v3(assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"])
    return claims, prov, counts


def test_missing_planner_evidence_ids_does_not_crash_an_investigation_action(tmp_path, monkeypatch):
    claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [], "requested_actions": ["__AVAILABLE__"]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert prov["planner_grounding_status"] == GROUNDING_MISSING
    assert prov["agent_failure"] is None
    assert counts["planner"] == 1
    assert prov["selected_action"] or prov["control_decision"]
    if prov["selected_action"]:
        assert prov["measurement_trajectory"]
        assert prov["measurement_trajectory"][0]["requested_by"] == "planner"
    assert claims[0].provenance.created_by == "deterministic_validator"


def test_critic_still_runs_after_planner_grounding_failure(tmp_path, monkeypatch):
    _claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [], "requested_actions": ["__AVAILABLE__"]}],
        critic_responses=[{"evidence_ids": [_VALID], "verdict": "accept"}],
    )
    assert prov["planner_grounding_status"] == GROUNDING_MISSING
    assert prov["critic_invoked"] is True
    assert counts["critic"] >= 1
    assert "CriticReview" in str(prov.get("call_graph"))
    assert prov["final_validator_ran"] is True
    assert prov["silent_deterministic_fallback"] is False


def test_critic_failure_after_grounding_failure_fails_closed(tmp_path, monkeypatch):
    claims, prov, _counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [], "requested_actions": ["__AVAILABLE__"]}],
        critic_responses=[{"evidence_ids": [], "rationale": "no citation"}],
    )
    assert prov["planner_grounding_status"] == GROUNDING_MISSING
    assert prov["critic_invoked"] is True
    assert prov["agent_failure"] is not None
    assert "critic failed after planner" in prov["agent_failure"]
    assert prov["final_validator_ran"] is False
    assert claims[0].confidence == 0.0


def test_unregistered_action_still_rejected(tmp_path, monkeypatch):
    claims, prov, _counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [_VALID], "requested_actions": ["set_the_claim_to_supported"]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert prov["agent_failure"] is not None
    assert "unregistered" in prov["agent_failure"]
    assert prov["final_validator_ran"] is False
    assert claims[0].confidence == 0.0


def test_llm_cannot_create_measurements():
    m = _measurements([_hit()])
    with pytest.raises(PatchRejected, match="unregistered origin"):
        apply_action_result(
            m,
            ActionResult(
                action_id="search_target_genes_nucleotide",
                status=ActionStatus.informative,
                summary="t",
                patches=[MeasurementPatch(field="hits", value=[_hit(tstart=1)], origin="qwen_planner")],
            ),
        )


def test_final_validator_remains_deterministic(tmp_path, monkeypatch):
    claims, prov, _counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [_VALID], "requested_actions": ["__AVAILABLE__"]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert prov["final_validator_ran"] is True
    assert claims[0].provenance.created_by == "deterministic_validator"
    assert prov["llm_measurement_entered_claim"] is False
    assert claims[0].claim_type.value in {"target_gene_detected", "target_gene_not_detected"}


def test_m0_to_m1_update_still_works(tmp_path, monkeypatch):
    _claims, prov, _counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [_VALID], "requested_actions": ["__AVAILABLE__"]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    if prov["selected_action"]:
        assert prov["measurement_trajectory"]
        step = prov["measurement_trajectory"][0]
        assert step["from"] == "m0"
        assert step["to"] == "m1"
        if step["status"] == ActionStatus.informative.value:
            assert prov["measurements_changed_before_validation"] is True
            assert prov["measurement_state"]["m0"]["hash"] != prov["measurement_state"]["m_final"]["hash"]
    assert prov["final_validator_ran"] is True


def test_state_consistency_invariants_pass():
    from genome_skeptic.agents.derived_state import assert_hits_derived_consistent
    from genome_skeptic.validators.family_orthology import FamilyEvidence
    from genome_skeptic.validators.falsification import _loci

    settings = Settings()
    first = _hit(contig_id="locus_1", tstart=100, tend=400, search_kind="translated", identity=1.0, query_coverage=1.0)
    fam = FamilyEvidence(
        family_id="tuf_EF_Tu",
        architecture="canonical_full_length",
        supports_orthologue=True,
        reconstruction={
            "architecture": "canonical_full_length",
            "multiplicity": {"classification": "single_locus", "number_of_candidate_loci": 1},
        },
        paralogue={"state": "single_locus", "supported": False},
        metrics={"multiplicity_classification": "single_locus"},
    )
    m = _measurements(
        [first],
        family_evidence=fam,
        contig_sequences={"locus_1": "A" * 2000, "locus_2": "C" * 2000},
    )
    second = _hit(
        contig_id="locus_2",
        tstart=100,
        tend=400,
        search_kind="translated",
        identity=0.9276,
        query_coverage=1.0,
        tool="hmmer_nominated_alignment",
    )
    result = apply_action_result(
        m,
        ActionResult(
            action_id="search_target_domains_hmmer",
            status=ActionStatus.informative,
            summary="t",
            patches=[MeasurementPatch(field="hits", value=[second], origin="hmm_orf_search")],
        ),
        settings=settings,
    )
    assert result.status is ActionStatus.informative
    assert len(_loci(m.hits, settings)) == 2
    assert_hits_derived_consistent(m, settings)


def test_inert_actions_are_excluded_from_ranked_candidates():
    caps = {
        "assembly": True,
        "targets": True,
        "hits": True,
        "query_protein": True,
        "similarity_tools": True,
        "hmmer": True,
        "competing_families": False,
        "references": False,
        "gff": False,
        "depth_tsv": False,
        "mapping_sam": False,
        "taxonomy_db": False,
        "protein_fasta": True,
        "catalytic_residues": False,
        "phylogenetic_placement": False,
    }
    m = _measurements([_hit()], contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs(m, caps)
    ranked = rank_candidate_actions(needs, caps, frozenset({"nucleotide_gene_search", "translated_gene_search"}), m)
    ids = [row["action_id"] for row in ranked]
    assert "inspect_paralogue_copies" not in ids
    assert "inspect_catalytic_residues" not in ids
    assert set(INERT_ACTION_IDS).isdisjoint(ids)
    assert len(ranked) <= max(3, len(needs))


def test_unresolved_competitive_classification_still_is_a_family_identity_need():
    from genome_skeptic.validators.family_orthology import FamilyEvidence

    caps = {
        "assembly": True,
        "targets": True,
        "hits": True,
        "query_protein": True,
        "similarity_tools": False,
        "hmmer": False,
        "competing_families": True,
        "references": False,
        "gff": False,
        "depth_tsv": False,
        "mapping_sam": False,
        "taxonomy_db": False,
        "protein_fasta": False,
        "catalytic_residues": False,
        "phylogenetic_placement": False,
    }
    fam = FamilyEvidence(
        family_id="tetA_tetracycline_efflux",
        architecture="true_no_candidate",
        supports_orthologue=False,
        reconstruction={"architecture": "true_no_candidate", "competitive_family": {"classification": "unresolved_candidate"}},
    )
    m = _measurements([_hit()], family_evidence=fam, contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs(m, caps)
    assert FAMILY_IDENTITY_UNRESOLVED in needs
    ranked = rank_candidate_actions(needs, caps, frozenset({"nucleotide_gene_search", "translated_gene_search"}), m)
    assert "competitive_family" in [row["action_id"] for row in ranked]
    before = executable_actions_before_ranking(
        needs, caps, frozenset({"nucleotide_gene_search", "translated_gene_search"}), m
    )
    assert "competitive_family" in [row["action_id"] for row in before]


def test_diagnostic_needs_are_generic_and_do_not_use_truth():
    caps = {
        "assembly": True,
        "targets": True,
        "hits": True,
        "query_protein": True,
        "similarity_tools": True,
        "hmmer": True,
        "competing_families": True,
        "references": False,
        "gff": False,
        "depth_tsv": False,
        "mapping_sam": False,
        "taxonomy_db": False,
        "protein_fasta": True,
        "catalytic_residues": False,
        "phylogenetic_placement": False,
    }
    m = _measurements([_hit()], contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs(m, caps)
    assert REMOTE_HOMOLOG_NOT_EXCLUDED in needs
    assert FAMILY_IDENTITY_UNRESOLVED in needs
    assert CONTAMINATION_UNRESOLVED in needs
    assert COPY_NUMBER_UNRESOLVED in needs
    ranked = rank_candidate_actions(needs, caps, frozenset({"nucleotide_gene_search", "translated_gene_search"}), m)
    ids = [row["action_id"] for row in ranked]
    assert "competitive_family" in ids
    homology = {"search_target_domains_hmmer", "search_target_proteins_mmseqs", "search_target_proteins_diamond"}
    assert homology & set(ids)
    executable = executable_actions_before_ranking(
        needs, caps, frozenset({"nucleotide_gene_search", "translated_gene_search"}), m
    )
    executable_ids = {row["action_id"] for row in executable}
    assert "competitive_family" in executable_ids
    assert "competitive_family" in ids, "dedicated family instrument must not be ranked out before the planner"


def test_validate_planner_allows_empty_evidence_ids_for_a_live_action():
    decision = AgentDecision.model_validate(
        {
            "decision": "continue",
            "rationale": "r",
            "evidence_ids": [],
            "requested_actions": ["search_target_proteins_mmseqs"],
        }
    )
    choice, grounding, control, fatal = _validate_planner_v3(
        decision, {"E001"}, {"search_target_proteins_mmseqs"}
    )
    assert fatal is None
    assert control is None
    assert choice == "search_target_proteins_mmseqs"
    assert grounding == GROUNDING_MISSING


def test_critic_cannot_force_an_action_outside_remaining_options():
    critic = CriticReview.model_validate(
        {
            "verdict": "challenge",
            "rationale": "r",
            "evidence_ids": ["E001"],
            "disconfirming_tests": ["inspect_paralogue_copies"],
        }
    )
    action, reason = select_critic_action_v3(critic, ["search_target_proteins_mmseqs"], [])
    assert action is None
    assert "remain" in reason


def test_planner_payload_shows_at_most_three_ranked_actions(tmp_path, monkeypatch):
    seen = {}

    class _Stub:
        def __init__(self, cfg):
            self.cfg = cfg

        def ask_json(self, system, payload, schema):
            seen.setdefault(schema.__name__, payload)
            if schema.__name__ in {"AgentDecision", "PlannerDecision"}:
                return _fit_schema(
                    schema,
                    {
                        "decision": "continue",
                        "rationale": "stub",
                        "evidence_ids": [payload["valid_evidence_ids"][0]],
                        "requested_actions": [_action_from_payload(payload)],
                    },
                )
            return _fit_schema(
                schema, {"verdict": "accept", "rationale": "stub", "evidence_ids": [payload["valid_evidence_ids"][0]]}
            )

    assembly, targets = _write_case(tmp_path)
    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v3.OllamaJSONClient", _Stub)
    _claims, _loci, prov = run_skeptic_agentic_v3(assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"])
    payload = seen["PlannerDecision"]
    needs = payload["diagnostic_needs"]
    offered = {row["action_id"] for row in payload["available_actions"]}
    assert len(payload["available_actions"]) <= max(3, len(needs))
    assert "inspect_paralogue_copies" not in offered
    from genome_skeptic.agents.action_catalog_v3 import V3_META

    executable_ids = {
        row["action_id"] if isinstance(row, dict) else row
        for row in (prov.get("executable_actions_before_ranking") or [])
    }
    for row in needs:
        covering = [
            action
            for action in payload["available_actions"]
            if row["need"] in (action.get("matched_needs") or action.get("tests") or [])
        ]
        if covering:
            continue
        dropped_relevant = [
            aid
            for aid in (executable_ids - offered)
            if aid in V3_META and row["need"] in V3_META[aid].tests
        ]
        assert not dropped_relevant, (
            f"DiagnosticNeed {row['need']} had live action(s) {dropped_relevant} filtered before the planner"
        )
    critic_payload = seen["CriticDecision"]
    assert "remaining_actions" in critic_payload
    assert "diagnostic_needs" in payload
    assert prov["planner_estimated_tokens"]


def test_copy_number_unresolved_until_orf_search_excludes_additional_copies():
    caps = {
        "assembly": True,
        "targets": True,
        "hits": True,
        "query_protein": True,
        "similarity_tools": True,
        "hmmer": True,
        "competing_families": False,
        "references": False,
        "gff": False,
        "depth_tsv": False,
        "mapping_sam": False,
        "taxonomy_db": False,
        "protein_fasta": True,
        "catalytic_residues": False,
        "phylogenetic_placement": False,
    }
    m = _measurements([_hit()], contig_gc={"c1": 0.5}, genome_gc=0.5, contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs(m, caps)
    assert COPY_NUMBER_UNRESOLVED in needs
    ranked = rank_candidate_actions(needs, caps, frozenset({"nucleotide_gene_search", "translated_gene_search"}), m)
    ids = [row["action_id"] for row in ranked]
    assert {"search_target_domains_hmmer", "search_target_proteins_mmseqs", "search_target_proteins_diamond"} & set(ids)
    m_done = _measurements(
        [_hit(tool="mmseqs")],
        tools_run=["internal_gene_search", "mmseqs"],
        contig_gc={"c1": 0.5},
        genome_gc=0.5,
        contig_sequences={"c1": "A" * 2000},
    )
    needs_done = derive_diagnostic_needs(m_done, caps)
    assert COPY_NUMBER_UNRESOLVED not in needs_done
    assert REMOTE_HOMOLOG_NOT_EXCLUDED not in needs_done
