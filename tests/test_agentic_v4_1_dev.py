"""GENOME_SKEPTIC_V4_1_DEV tests. Frozen V3/V4-dev tests are not modified."""
from pathlib import Path

import pytest

from genome_skeptic.agents.action_catalog_v4_1_dev import (
    INERT_ACTION_IDS,
    NOVELTY_DISCRIMINATING,
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
from genome_skeptic.agents.assembly_loop_v4_1_dev import (
    GROUNDING_MISSING,
    _validate_planner_v4_1_dev,
    run_skeptic_agentic_v4_1_dev,
    select_critic_action_v4_1_dev,
)
from genome_skeptic.agents.diagnostic_needs_v4_1_dev import (
    COPY_NUMBER_UNRESOLVED,
    FAMILY_IDENTITY_UNRESOLVED,
    ORTHOLOG_VS_PARALOG_UNRESOLVED,
    derive_diagnostic_needs_v4_1_dev,
    family_identity_is_decisive,
)
from genome_skeptic.config import Settings
from genome_skeptic.models import AgentDecision, CriticReview, GeneSearchHit, TargetProfile
from genome_skeptic.validators.falsification import TargetMeasurements
from genome_skeptic.validators.locus_stages_v4_1_dev import (
    _loci,
    accept_candidates,
    assert_locus_count_invariant,
    collapse_multiplicity,
    reconstruct_loci,
    repair_loci_v4_1,
)
from genome_skeptic.validators.ortholog_references import (
    COMPETING_FAMILY_PREFERRED,
    TARGET_FAMILY_SUPPORTED,
    UNRESOLVED_CANDIDATE,
    discriminate_ortholog_references,
    load_ortholog_reference_set,
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
        "ortholog_reference_set": False,
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


def test_zero_true_loci():
    settings = Settings()
    assert _loci([], settings) == []
    m = _measurements([])
    summary = repair_loci_v4_1(m, settings)
    assert summary["n_loci"] == 0


def test_one_divergent_full_length_locus():
    settings = Settings()
    hits = [
        _hit(
            query_id="MEMBER1",
            contig_id="c1",
            tstart=581483,
            tend=581945,
            identity=0.532,
            query_coverage=0.806,
            tool="family_member_search",
            orf_id="orf_divergent",
        )
    ]
    accepted = accept_candidates(hits, settings, target_query_id="tuf_EF_Tu")
    assert len(accepted) == 1
    assert settings.thresholds.multiplicity_min_identity == 0.85
    assert accepted[0].identity < 0.85
    loci = _loci(hits, settings, target_query_id="tuf_EF_Tu")
    assert len(loci) == 1


def test_two_divergent_full_length_loci():
    settings = Settings()
    hits = [
        _hit(query_id="M1", contig_id="c1", tstart=389151, tend=389691, identity=0.394, query_coverage=0.927, orf_id="orfA"),
        _hit(query_id="M2", contig_id="c1", tstart=2051790, tend=2052270, identity=0.416, query_coverage=0.832, orf_id="orfB"),
    ]
    assert all(h.identity < 0.85 for h in hits)
    assert len(_loci(hits, settings, target_query_id="tuf_EF_Tu")) == 2


def test_duplicate_blast_mmseqs_hmm_hits_collapse_to_one_orf():
    settings = Settings()
    hits = [
        _hit(contig_id="c1", tstart=100, tend=400, identity=0.9, query_coverage=0.9, tool="mmseqs", orf_id="orfA"),
        _hit(contig_id="c1", tstart=100, tend=400, identity=0.88, query_coverage=0.91, tool="diamond", orf_id="orfA"),
        _hit(contig_id="c1", tstart=110, tend=390, identity=0.87, query_coverage=0.88, tool="hmmer_nominated_alignment", orf_id="orfA"),
    ]
    accepted = accept_candidates(hits, settings, target_query_id="rpoB")
    loci = collapse_multiplicity(reconstruct_loci(accepted, settings))
    assert len(loci) == 1


def test_overlapping_representations_of_same_locus():
    settings = Settings()
    hits = [
        _hit(contig_id="c1", tstart=100, tend=400, identity=0.92, query_coverage=0.95, orf_id="orf1"),
        _hit(contig_id="c1", tstart=120, tend=380, identity=0.80, query_coverage=0.70, orf_id="orf1_overlap"),
        _hit(contig_id="c1", tstart=90, tend=410, identity=0.70, query_coverage=0.99, orf_id="orf1_span"),
    ]
    assert len(_loci(hits, settings, target_query_id="rpoB")) == 1


def test_two_genuinely_separate_orfs():
    settings = Settings()
    hits = [
        _hit(contig_id="c1", tstart=100, tend=400, identity=0.9, query_coverage=0.9, orf_id="orfA"),
        _hit(contig_id="c1", tstart=5000, tend=5300, identity=0.88, query_coverage=0.91, orf_id="orfB"),
    ]
    assert len(_loci(hits, settings, target_query_id="rpoB")) == 2


def test_unrelated_homologous_decoy_hits_are_not_loci():
    settings = Settings()
    hits = [
        _hit(query_id="DECOY", contig_id="c1", tstart=10, tend=400, identity=0.20, query_coverage=0.90, orf_id="decoy"),
        _hit(query_id="SHORT", contig_id="c1", tstart=800, tend=860, identity=0.375, query_coverage=0.25, orf_id="short"),
    ]
    accepted = accept_candidates(hits, settings, target_query_id="tuf_EF_Tu")
    assert accepted == []
    assert _loci(hits, settings, target_query_id="tuf_EF_Tu") == []


def test_fragmented_candidate_evidence_is_not_counted():
    settings = Settings()
    hits = [
        _hit(contig_id="c1", tstart=100, tend=130, identity=0.90, query_coverage=0.07, alignment_length=30, orf_id="frag1"),
        _hit(contig_id="c1", tstart=200, tend=230, identity=0.88, query_coverage=0.08, alignment_length=30, orf_id="frag2"),
    ]
    assert accept_candidates(hits, settings, target_query_id="rpoB") == []
    assert _loci(hits, settings, target_query_id="rpoB") == []


def test_locus_count_invariant_after_repair():
    from genome_skeptic.validators.family_orthology import FamilyEvidence

    settings = Settings()
    member = _hit(
        query_id="MEMBER1",
        contig_id="c2",
        tstart=800,
        tend=1200,
        identity=0.45,
        query_coverage=0.85,
        tool="family_member_search",
        orf_id="c2:800-1200:+",
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
            "sequence_identity": 0.45,
            "protein_coverage": 0.85,
            "multiplicity": {"classification": "single_locus", "number_of_candidate_loci": 0},
        },
    )
    fragments = [_hit(contig_id="c1", tstart=10, tend=40, identity=0.4, query_coverage=0.07, alignment_length=30)]
    m = _measurements(fragments, family_evidence=fam, contig_sequences={"c1": "A" * 2000, "c2": "C" * 2000})
    summary = repair_loci_v4_1(m, settings)
    assert summary["n_loci"] == 1
    assert_locus_count_invariant(m, settings)
    assert fam.reconstruction["multiplicity"]["number_of_candidate_loci"] == 1
    assert fam.reconstruction["multiplicity"]["number_of_candidate_loci"] == len(
        _loci(accept_candidates(m.hits, settings, target_query_id=m.query_id), settings, target_query_id=m.query_id)
    )


def test_does_not_use_multiplicity_min_identity_for_counting():
    source = Path(__file__).resolve().parents[1] / "src" / "genome_skeptic" / "validators" / "locus_stages_v4_1_dev.py"
    text = source.read_text(encoding="utf-8")
    assert "thresholds.multiplicity_min_identity" not in text
    assert "0.85" not in text


def test_teta_non_decisive_family_support_still_unresolved():
    from genome_skeptic.validators.family_orthology import FamilyEvidence

    competitive = {
        "classification": "target_family_supported",
        "target_family_sequence_coverage": 0.08,
        "conflicting_evidence": ["best competing family did not pass the family gate"],
    }
    assert family_identity_is_decisive(competitive) is False
    fam = FamilyEvidence(
        family_id="tetA_tetracycline_efflux",
        architecture="divergent_full_length",
        supports_orthologue=True,
        reconstruction={"architecture": "divergent_full_length", "competitive_family": competitive},
    )
    m = _measurements([_hit()], family_evidence=fam, contig_sequences={"c1": "A" * 2000})
    needs = derive_diagnostic_needs_v4_1_dev(m, _caps())
    assert FAMILY_IDENTITY_UNRESOLVED in needs
    ranked = rank_candidate_actions(needs, _caps(), frozenset({"nucleotide_gene_search", "translated_gene_search"}), m)
    ids = [row["action_id"] for row in ranked]
    assert ids[0] == "competitive_family"
    homology = {"search_target_domains_hmmer", "search_target_proteins_mmseqs", "search_target_proteins_diamond"}
    if homology & set(ids):
        assert ids.index("competitive_family") < min(ids.index(h) for h in homology if h in ids)
    row = next(r for r in ranked if r["action_id"] == "competitive_family")
    assert row["decision_relevance"][FAMILY_IDENTITY_UNRESOLVED] == NOVELTY_DISCRIMINATING


def test_teta_positions_route_to_competitive_family_without_ortholog_set():
    from genome_skeptic.validators.family_orthology import FamilyEvidence

    for _pos in (1, 3, 11):
        fam = FamilyEvidence(
            family_id="tetA_tetracycline_efflux",
            reconstruction={
                "competitive_family": {
                    "classification": "target_family_supported",
                    "target_family_sequence_coverage": 0.08,
                    "conflicting_evidence": ["best competing family did not pass the family gate"],
                }
            },
        )
        m = _measurements([_hit()], family_evidence=fam, contig_sequences={"c1": "A" * 2000})
        needs = derive_diagnostic_needs_v4_1_dev(m, _caps(ortholog_reference_set=False))
        ranked = rank_candidate_actions(
            needs, _caps(ortholog_reference_set=False), frozenset({"nucleotide_gene_search", "translated_gene_search"}), m
        )
        assert ranked[0]["action_id"] == "competitive_family"


def test_lacz_reference_set_is_independent_and_hashed():
    refs = load_ortholog_reference_set("lacZ_beta_galactosidase")
    assert {ref.protein_id for ref in refs} == {"P00722", "P06864", "P19668"}
    assert any(ref.is_true for ref in refs)
    assert any(ref.is_competing for ref in refs)
    for ref in refs:
        assert ref.source.startswith("UniProt")
        assert len(ref.sequence_sha256) == 64


def test_lacz_true_orthologue_is_target_family_supported():
    refs = {ref.protein_id: ref for ref in load_ortholog_reference_set("lacZ_beta_galactosidase")}
    ev = discriminate_ortholog_references(
        family_id="lacZ_beta_galactosidase",
        candidate_aa=refs["P00722"].sequence,
        settings=Settings(),
    )
    assert ev.classification == TARGET_FAMILY_SUPPORTED
    assert ev.validator_classification == "target_family_supported"


def test_lacz_competing_ebga_is_competing_family_preferred():
    refs = {ref.protein_id: ref for ref in load_ortholog_reference_set("lacZ_beta_galactosidase")}
    ev = discriminate_ortholog_references(
        family_id="lacZ_beta_galactosidase",
        candidate_aa=refs["P06864"].sequence,
        settings=Settings(),
    )
    assert ev.classification == COMPETING_FAMILY_PREFERRED


def test_lacz_competing_bgab_is_competing_family_preferred():
    refs = {ref.protein_id: ref for ref in load_ortholog_reference_set("lacZ_beta_galactosidase")}
    ev = discriminate_ortholog_references(
        family_id="lacZ_beta_galactosidase",
        candidate_aa=refs["P19668"].sequence,
        settings=Settings(),
    )
    assert ev.classification == COMPETING_FAMILY_PREFERRED


def test_lacz_unrelated_sequence_is_unresolved():
    ev = discriminate_ortholog_references(
        family_id="lacZ_beta_galactosidase",
        candidate_aa="MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKRQTLGQHDFSAGEGLYTHMKALRPDEDRLSPLHSVYVDQWDWERVMGDGERQFSTLKSTVEAIWAGIKATEAAVSEEFGLAPFLPDQIHFVHSQELLSRYKDLPVGREIENLHLETFARLQ",
        settings=Settings(),
    )
    assert ev.classification == UNRESOLVED_CANDIDATE


def test_lacz_need_routes_to_ortholog_reference_action():
    m = _measurements([_hit()], contig_sequences={"c1": "A" * 2000})
    caps = _caps(competing_families=False, ortholog_reference_set=True, similarity_tools=False, hmmer=False)
    needs = derive_diagnostic_needs_v4_1_dev(m, caps)
    assert FAMILY_IDENTITY_UNRESOLVED in needs or ORTHOLOG_VS_PARALOG_UNRESOLVED in needs
    ranked = rank_candidate_actions(needs, caps, frozenset({"nucleotide_gene_search", "translated_gene_search"}), m)
    ids = [row["action_id"] for row in ranked]
    assert ids[0] == "competitive_ortholog_references"


def test_llm_cannot_write_copy_number_or_identity():
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


def test_v41_planner_control_flow_preserved(tmp_path, monkeypatch):
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
    monkeypatch.setattr("genome_skeptic.agents.assembly_loop_v4_1_dev.OllamaJSONClient", _Stub)
    claims, _loci_out, prov = run_skeptic_agentic_v4_1_dev(assembly, targets, tmp_path / "out", Settings(), query_ids=["rpoB"])
    payload = seen["PlannerDecision"]
    assert "valid_evidence_ids" in payload
    assert "available_actions" in payload
    assert "diagnostic_needs" in payload
    assert "constraints" in payload
    assert prov["final_validator_ran"] is True
    assert claims[0].provenance.created_by == "deterministic_validator"
    assert prov["llm_measurement_entered_claim"] is False
    assert set(INERT_ACTION_IDS).isdisjoint({row["action_id"] for row in payload["available_actions"]})


def test_v41_unregistered_action_rejected():
    decision = AgentDecision.model_validate(
        {
            "decision": "continue",
            "rationale": "r",
            "evidence_ids": ["E001"],
            "requested_actions": ["invent_a_score"],
        }
    )
    choice, grounding, control, fatal = _validate_planner_v4_1_dev(decision, {"E001"}, {"competitive_family"})
    assert fatal is not None
    assert "unregistered" in fatal
    assert choice is None


def test_v41_critic_cannot_force_unranked_action():
    critic = CriticReview.model_validate(
        {
            "verdict": "challenge",
            "rationale": "r",
            "evidence_ids": ["E001"],
            "disconfirming_tests": ["inspect_paralogue_copies"],
        }
    )
    action, reason = select_critic_action_v4_1_dev(critic, ["search_target_proteins_mmseqs"], [])
    assert action is None
    assert "remain" in reason
