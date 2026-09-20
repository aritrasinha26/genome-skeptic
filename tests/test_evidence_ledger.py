import pytest

from genome_skeptic.models import Claim, ClaimType, Evidence, EvidenceRelationType, RunState


def test_bind_claim_rejects_unknown_evidence_ids():
    state = RunState(run_id="t", out_dir=".", inputs={})
    state.evidence.append(Evidence(id="E001", stage="assembly_qc", kind="tool_result", summary="QUAST completed"))
    with pytest.raises(ValueError, match="Unknown evidence IDs"):
        state.bind_claim(Claim(
            claim_id="C001",
            claim_type=ClaimType.assembly_supported_for_annotation,
            statement="The assembly is sufficiently supported to proceed to gene annotation.",
            supporting_evidence_ids=["E999"],
        ))
    assert state.claims == []


def test_bind_claim_records_support_and_contradict_edges():
    state = RunState(run_id="t", out_dir=".", inputs={})
    state.evidence.append(Evidence(id="E001", stage="mapping", kind="tool_result", summary="mapping completed"))
    state.evidence.append(Evidence(id="E002", stage="mapping", kind="tool_result", summary="low mapping rate"))
    claim = state.bind_claim(Claim(
        claim_id="C001",
        claim_type=ClaimType.assembly_supported_for_annotation,
        statement="The assembly is sufficiently supported to proceed to gene annotation.",
        supporting_evidence_ids=["E001"],
        contradicting_evidence_ids=["E002"],
    ))
    kinds = {(r.source_id, r.target_id, r.kind) for r in state.relations}
    assert (claim.claim_id, "E001", EvidenceRelationType.supports) in kinds
    assert (claim.claim_id, "E002", EvidenceRelationType.contradicts) in kinds


def test_add_relation_cannot_point_at_missing_evidence():
    state = RunState(run_id="t", out_dir=".", inputs={})
    with pytest.raises(ValueError, match="unknown evidence"):
        state.add_relation("C001", "E001", EvidenceRelationType.supports)
