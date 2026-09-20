"""Agentic V4-dev tests. Frozen V3 tests are not modified."""
from pathlib import Path

import pytest

from genome_skeptic.agents.action_catalog_v4_dev import (
    INERT_ACTION_IDS,
    NOVELTY_DISCRIMINATING,
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
)
from genome_skeptic.agents.assembly_loop_v4_dev import (
    GROUNDING_MISSING,
    CURRENT_LACZ_LIMITATION,
    _validate_planner_v4_dev,
    run_skeptic_agentic_v4_dev,
    select_critic_action_v4_dev,
)
from genome_skeptic.agents.diagnostic_needs_v4_dev import (
    CONTAMINATION_UNRESOLVED,
    COPY_NUMBER_UNRESOLVED,
    FAMILY_IDENTITY_UNRESOLVED,
    ORTHOLOG_VS_PARALOG_UNRESOLVED,
    REMOTE_HOMOLOG_NOT_EXCLUDED,
    derive_diagnostic_needs_v4_dev,
)
from genome_skeptic.config import Settings
from genome_skeptic.models import AgentDecision, CriticReview, GeneSearchHit, TargetProfile
from genome_skeptic.validators.falsification import TargetMeasurements
from genome_skeptic.validators.locus_v4_dev import (
    _loci,
    assert_locus_count_invariant,
    cluster_loci,
    recover_hit_coordinates,
    repair_loci_v4,
)

GENE = "ATG" + ("CGTAGC") * 20 + "TAA"


def _profile(**kwargs) -> TargetProfile:
    data = {"query_id": "rpoB", "sequence": GENE}
    data.update(kwargs)
    return TargetProfile.model_validate(data)


def _hit(**kwargs) -> GeneSearchHit:
    data = {
        "query_id": "rpoB",
        "contig_id": "c1",
        "search_kind": "translated",
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


def _caps(**overrides) -> dict:
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
    caps.update(overrides)
    return caps


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

    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v4_dev.OllamaJSONClient", _Stub)
    return counts


def _run_sequenced(tmp_path, monkeypatch, planner_responses, critic_responses):
    assembly, targets = _write_case(tmp_path)
    counts = _sequenced_llm(monkeypatch, planner_responses, critic_responses)
    claims, _loci_out, prov = run_skeptic_agentic_v4_dev(assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"])
    return claims, prov, counts


def test_v4_missing_planner_evidence_ids_does_not_crash(tmp_path, monkeypatch):
    claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [], "requested_actions": ["__AVAILABLE__"]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert prov["planner_grounding_status"] == GROUNDING_MISSING
    assert prov["agent_failure"] is None
    assert counts["planner"] == 1
    assert claims[0].provenance.created_by == "deterministic_validator"


def test_v4_critic_still_runs_after_planner_grounding_failure(tmp_path, monkeypatch):
    _claims, prov, counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [], "requested_actions": ["__AVAILABLE__"]}],
        critic_responses=[{"evidence_ids": [_VALID], "verdict": "accept"}],
    )
    assert prov["planner_grounding_status"] == GROUNDING_MISSING
    assert prov["critic_invoked"] is True
    assert counts["critic"] >= 1
    assert prov["final_validator_ran"] is True


def test_v4_unregistered_action_still_rejected(tmp_path, monkeypatch):
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


def test_v4_llm_cannot_create_measurements():
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


def test_v4_final_validator_remains_deterministic(tmp_path, monkeypatch):
    claims, prov, _counts = _run_sequenced(
        tmp_path,
        monkeypatch,
        planner_responses=[{"evidence_ids": [_VALID], "requested_actions": ["__AVAILABLE__"]}],
        critic_responses=[{"evidence_ids": [_VALID]}],
    )
    assert prov["final_validator_ran"] is True
    assert claims[0].provenance.created_by == "deterministic_validator"
    assert prov["llm_measurement_entered_claim"] is False


def test_v4_family_uncertainty_routes_to_competitive_family():
    from genome_skeptic.validators.family_orthology import FamilyEvidence

    fam = FamilyEvidence(
        family_id="example_family",
        architecture="divergent_full_length",
        supports_orthologue=True,
        reconstruction={
            "architecture": "divergent_full_length",
            "competitive_family": {
                "classification": "target_family_supported",
                "target_family_sequence_coverage": 0.08,
                "conflicting_evidence": ["best competing family did not pass the family gate"],
            },
        },
    )
    m = _measurements([_hit()], family_evidence=fam, contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs_v4_dev(m, _caps())
    assert FAMILY_IDENTITY_UNRESOLVED in needs
    ranked = rank_candidate_actions(needs, _caps(), frozenset({"nucleotide_gene_search", "translated_gene_search"}), m)
    ids = [row["action_id"] for row in ranked]
    assert ids[0] == "competitive_family"
    homology = {"search_target_domains_hmmer", "search_target_proteins_mmseqs", "search_target_proteins_diamond"}
    if homology & set(ids):
        assert ids.index("competitive_family") < min(ids.index(h) for h in homology if h in ids)
    row = next(r for r in ranked if r["action_id"] == "competitive_family")
    assert row["decision_relevance"][FAMILY_IDENTITY_UNRESOLVED] == NOVELTY_DISCRIMINATING


def test_v4_copy_number_uncertainty_routes_to_multiplicity_actions():
    m = _measurements([_hit()], contig_gc={"c1": 0.5}, genome_gc=0.5, contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs_v4_dev(m, _caps(competing_families=False))
    assert COPY_NUMBER_UNRESOLVED in needs
    ranked = rank_candidate_actions(
        needs, _caps(competing_families=False), frozenset({"nucleotide_gene_search", "translated_gene_search"}), m
    )
    ids = [row["action_id"] for row in ranked]
    copy_actions = {"search_target_domains_hmmer", "search_target_proteins_mmseqs", "search_target_proteins_diamond"}
    assert copy_actions & set(ids)
    if "inspect_hit_contig_contamination" in ids:
        first_copy = min(ids.index(a) for a in copy_actions if a in ids)
        assert first_copy < ids.index("inspect_hit_contig_contamination")


def test_v4_ortholog_uncertainty_routes_to_orthology_actions():
    m = _measurements([_hit()], contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs_v4_dev(m, _caps(references=True, competing_families=False, similarity_tools=False, hmmer=False))
    assert ORTHOLOG_VS_PARALOG_UNRESOLVED in needs
    ranked = rank_candidate_actions(
        needs,
        _caps(references=True, competing_families=False, similarity_tools=False, hmmer=False),
        frozenset({"nucleotide_gene_search", "translated_gene_search"}),
        m,
    )
    ids = [row["action_id"] for row in ranked]
    assert "reciprocal_best_hit_search" in ids or "compare_locus_to_reference" in ids


def test_v4_unregistered_actions_rejected_by_planner_validator():
    decision = AgentDecision.model_validate(
        {
            "decision": "continue",
            "rationale": "r",
            "evidence_ids": ["E001"],
            "requested_actions": ["invent_a_score"],
        }
    )
    choice, grounding, control, fatal = _validate_planner_v4_dev(decision, {"E001"}, {"competitive_family"})
    assert fatal is not None
    assert "unregistered" in fatal
    assert choice is None


def test_v4_critic_cannot_force_unranked_action():
    critic = CriticReview.model_validate(
        {
            "verdict": "challenge",
            "rationale": "r",
            "evidence_ids": ["E001"],
            "disconfirming_tests": ["inspect_paralogue_copies"],
        }
    )
    action, reason = select_critic_action_v4_dev(critic, ["search_target_proteins_mmseqs"], [])
    assert action is None
    assert "remain" in reason


def test_v4_inert_actions_excluded():
    m = _measurements([_hit()], contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs_v4_dev(m, _caps())
    ranked = rank_candidate_actions(needs, _caps(), frozenset({"nucleotide_gene_search", "translated_gene_search"}), m)
    ids = [row["action_id"] for row in ranked]
    assert set(INERT_ACTION_IDS).isdisjoint(ids)


def test_locus_zero_copies():
    settings = Settings()
    m = _measurements([])
    repair_loci_v4(m, settings)
    assert _loci(m.hits, settings) == []


def test_locus_one_copy():
    settings = Settings()
    hits = [_hit(contig_id="c1", tstart=100, tend=400, identity=0.9, query_coverage=0.9, orf_id="c1:100-400:+")]
    assert len(_loci(hits, settings)) == 1


def test_locus_two_distinct_copies():
    settings = Settings()
    hits = [
        _hit(contig_id="c1", tstart=100, tend=400, identity=0.9, query_coverage=0.9, orf_id="c1:100-400:+"),
        _hit(contig_id="c1", tstart=5000, tend=5300, identity=0.88, query_coverage=0.91, orf_id="c1:5000-5300:+"),
    ]
    assert len(_loci(hits, settings)) == 2


def test_locus_duplicate_hits_from_multiple_tools_collapse():
    settings = Settings()
    hits = [
        _hit(contig_id="c1", tstart=100, tend=400, identity=0.9, query_coverage=0.9, tool="mmseqs", orf_id="orfA"),
        _hit(contig_id="c1", tstart=110, tend=390, identity=0.85, query_coverage=0.88, tool="hmmer_nominated_alignment", orf_id="orfA"),
    ]
    recovered = [recover_hit_coordinates(h) for h in hits]
    assert len(cluster_loci(recovered, settings)) == 1


def test_locus_fragmented_overlapping_representations_do_not_duplicate():
    settings = Settings()
    hits = [
        _hit(contig_id="c1", tstart=100, tend=400, identity=0.92, query_coverage=0.95),
        _hit(contig_id="c1", tstart=120, tend=380, identity=0.80, query_coverage=0.70),
        _hit(contig_id="c1", tstart=90, tend=410, identity=0.70, query_coverage=0.99),
    ]
    assert len(_loci(hits, settings)) == 1


def test_locus_count_invariant_holds_after_repair():
    from genome_skeptic.validators.family_orthology import FamilyEvidence

    settings = Settings()
    member = _hit(
        query_id="MEMBER1",
        contig_id="c2",
        tstart=800,
        tend=1200,
        identity=0.55,
        query_coverage=0.85,
        tool="family_member_search",
    )
    fam = FamilyEvidence(
        family_id="example_family",
        architecture="divergent_full_length",
        member_hits=[member],
        reconstruction={
            "architecture": "divergent_full_length",
            "contig": "c2",
            "genomic_start": 800,
            "genomic_end": 1200,
            "strand": "+",
            "sequence_identity": 0.55,
            "protein_coverage": 0.85,
            "multiplicity": {"classification": "single_locus", "number_of_candidate_loci": 0},
        },
    )
    fragments = [
        _hit(contig_id="c1", tstart=10, tend=40, identity=0.4, query_coverage=0.07, alignment_length=30),
    ]
    m = _measurements(fragments, family_evidence=fam, contig_sequences={"c1": "A" * 2000, "c2": "C" * 2000})
    repair_loci_v4(m, settings)
    n = len(_loci(m.hits, settings, target_query_id=m.query_id))
    assert n == 1
    assert_locus_count_invariant(m, settings)
    assert fam.reconstruction["multiplicity"]["number_of_candidate_loci"] == n


def test_lacz_limitation_retained():
    assert "LacZ" in CURRENT_LACZ_LIMITATION
    assert "reference/GFF/orthology" in CURRENT_LACZ_LIMITATION


def test_v4_planner_payload_preserves_grounding_contract(tmp_path, monkeypatch):
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
    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v4_dev.OllamaJSONClient", _Stub)
    _claims, _loci_out, prov = run_skeptic_agentic_v4_dev(assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"])
    payload = seen["PlannerDecision"]
    assert "valid_evidence_ids" in payload
    assert "available_actions" in payload
    assert "diagnostic_needs" in payload
    assert "constraints" in payload
    assert "inspect_paralogue_copies" not in {row["action_id"] for row in payload["available_actions"]}
    assert prov["planner_estimated_tokens"]
