from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    hard = "hard"


class Evidence(BaseModel):
    id: str
    stage: str
    kind: str
    summary: str
    values: dict[str, Any] = Field(default_factory=dict)
    source_path: str | None = None
    command: list[str] | None = None
    tool_version: str | None = None


class Anomaly(BaseModel):
    id: str
    stage: str
    severity: Severity
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    possible_explanations: list[str] = Field(default_factory=list)


class ClaimStatus(str, Enum):
    supported = "supported"
    weakened = "weakened"
    unresolved = "unresolved"
    rejected = "rejected"


class EvidenceRelationType(str, Enum):
    supports = "supports"
    contradicts = "contradicts"
    derived_from = "derived-from"
    tested_by = "tested-by"


class EvidenceRelation(BaseModel):
    source_id: str
    target_id: str
    kind: EvidenceRelationType
    note: str = ""


class GeneSearchHit(BaseModel):
    query_id: str
    contig_id: str
    search_kind: Literal["nucleotide", "translated", "protein", "domain"]
    qstart: int
    qend: int
    tstart: int
    tend: int
    strand: Literal["+", "-"]
    identity: float
    query_coverage: float
    alignment_length: int
    query_length: int
    contig_length: int
    near_contig_edge: bool = False
    possible_edge_truncation: bool = False
    edge_distance_bp: int = 0
    evalue: float | None = None
    subject_coverage: float | None = None
    tool: str = "internal_gene_search"
    domain_name: str | None = None
    orf_id: str | None = None


class GeneOrderItem(BaseModel):
    gene_id: str
    product: str
    start: int
    end: int
    strand: str
    is_target: bool = False
    contig: str | None = None


class OrthologueRecord(BaseModel):
    query_id: str
    subject_id: str
    identity: float
    query_coverage: float
    subject_coverage: float | None = None
    evalue: float | None = None
    reciprocal_best_hit: bool | None = None
    tool: str = "internal_gene_search"
    orientation: str | None = None


class LocusEvidence(BaseModel):
    target: str
    candidate_locus: dict[str, Any] | None = None
    reference_genome: str | None = None
    orthologues: list[OrthologueRecord] = Field(default_factory=list)
    gene_order: list[GeneOrderItem] = Field(default_factory=list)
    orientation: str | None = None
    distance: dict[str, Any] = Field(default_factory=dict)
    sequence_similarity: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class QueryDomain(BaseModel):
    name: str
    start: int
    end: int


class CatalyticResidue(BaseModel):
    position: int
    residue: str


class TargetType(str, Enum):
    exact_allele = "exact_allele"
    gene_orthologue = "gene_orthologue"
    protein_family = "protein_family"


class FamilyMember(BaseModel):
    protein_id: str
    species: str
    gene_id: str | None = None
    locus_tag: str | None = None
    length_aa: int = 0
    sequence: str = ""
    fusion_or_split: str = "canonical"
    domains: list[QueryDomain] = Field(default_factory=list)


class TargetFamily(BaseModel):
    """Curated homolog set for gene_orthologue reasoning. Not a single reference protein."""

    family_id: str
    display_name: str = ""
    members: list[FamilyMember] = Field(default_factory=list)
    domain_architecture: list[str] = Field(default_factory=list)
    known_fusion_or_split: list[dict[str, Any]] = Field(default_factory=list)
    partner_families: list[str] = Field(default_factory=list)
    msa_provenance: dict[str, Any] = Field(default_factory=dict)
    hmm_provenance: dict[str, Any] = Field(default_factory=dict)
    phylo_provenance: dict[str, Any] = Field(default_factory=dict)
    forbidden_protein_ids: list[str] = Field(default_factory=list)
    competing_families: list[str] = Field(default_factory=list)
    family_class: str = ""

    @property
    def expected_length_aa(self) -> int | None:
        lengths = [m.length_aa or len(m.sequence) for m in self.members if (m.length_aa or m.sequence)]
        if not lengths:
            return None
        lengths.sort()
        return lengths[len(lengths) // 2]


class TargetProfile(BaseModel):
    query_id: str
    sequence: str
    target_type: TargetType | None = None
    expected_length_aa: int | None = None
    catalytic_residues: list[CatalyticResidue] = Field(default_factory=list)
    domains: list[QueryDomain] = Field(default_factory=list)
    expected_neighbors: list[str] = Field(default_factory=list)
    expected_taxonomy: str | None = None
    family_id: str | None = None
    family: TargetFamily | None = None


class LocusSegment(BaseModel):
    contig: str
    strand: str
    genomic_start: int
    genomic_end: int
    frame: int | None = None
    orf_id: str | None = None
    hmm_from: int | None = None
    hmm_to: int | None = None
    evalue: float | None = None
    score: float | None = None
    identity: float | None = None
    query_coverage: float | None = None
    near_contig_edge: bool = False


class LocusReconstruction(BaseModel):
    """Annotation-independent genomic locus built from DNA, not predicted proteins."""

    contig: str | None = None
    strand: str | None = None
    genomic_start: int | None = None
    genomic_end: int | None = None
    candidate_segments: list[LocusSegment] = Field(default_factory=list)
    frame: int | None = None
    profile_hmm_from: int | None = None
    profile_hmm_to: int | None = None
    sequence_identity: float | None = None
    protein_coverage: float | None = None
    hmm_coverage: float | None = None
    domain_order: list[int] = Field(default_factory=list)
    inter_segment_gaps: list[int] = Field(default_factory=list)
    stop_codons: list[dict[str, Any]] = Field(default_factory=list)
    frameshifts: list[dict[str, Any]] = Field(default_factory=list)
    contig_edge: bool = False
    local_depth: float | None = None
    annotation_agreement: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    architecture: str = "true_no_candidate"
    family_gate_passed: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)
    query_identity: float | None = None
    divergence: dict[str, Any] = Field(default_factory=dict)
    paralogue_record: dict[str, Any] | None = None
    secondary_loci: list[dict[str, Any]] = Field(default_factory=list)
    competitive_family: dict[str, Any] | None = None
    multiplicity: dict[str, Any] | None = None


class HypothesisNode(BaseModel):
    hypothesis_id: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    unavailable_evidence: list[str] = Field(default_factory=list)
    remaining_discriminating_tests: list[str] = Field(default_factory=list)
    required_unresolved_tests: list[str] = Field(default_factory=list)
    posterior_support: float | None = None
    relative_support: float = 0.0
    support_state: str = "unsupported"
    reason_for_support_state: str = ""
    distinguishing_tests: list[str] = Field(default_factory=list)
    notes: str = ""


class HypothesisGraph(BaseModel):
    target_id: str
    hypotheses: list[HypothesisNode] = Field(default_factory=list)
    leading: str | None = None
    runner_up: str | None = None
    stop_reason: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class DiagnosticAction(BaseModel):
    action_id: str
    required_inputs: list[str] = Field(default_factory=list)
    expected_output: str = ""
    cost_class: Literal["cheap", "moderate", "expensive"] = "moderate"
    approximate_cost: str = ""
    evidence_produced: list[str] = Field(default_factory=list)
    supports_hypotheses: list[str] = Field(default_factory=list)
    rejects_hypotheses: list[str] = Field(default_factory=list)
    informative_when: str = ""


class ClaimType(str, Enum):
    assembly_supported_for_annotation = "assembly_supported_for_annotation"
    annotation_internally_plausible = "annotation_internally_plausible"
    target_gene_detected = "target_gene_detected"
    target_gene_not_detected = "target_gene_not_detected"


class FalsificationResult(str, Enum):
    supports_claim = "supports_claim"
    weakens_claim = "weakens_claim"
    rejects_claim = "rejects_claim"
    inconclusive = "inconclusive"
    not_run = "not_run"


class FalsificationTest(BaseModel):
    test_id: str
    name: str
    hypothesis: str
    blocking: bool = True
    status: Literal["completed", "unresolved", "skipped"] = "skipped"
    result: FalsificationResult = FalsificationResult.not_run
    evidence_ids: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    limitation: str | None = None


class ClaimProvenance(BaseModel):
    created_by: str = "deterministic_validator"
    stage: str
    tool_names: list[str] = Field(default_factory=list)
    evidence_ledger_ids: list[str] = Field(default_factory=list)
    attack_plan_id: str | None = None
    notes: str = "LLM did not supply identity, coverage, E-values, domain hits, or catalytic residues."


class Claim(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str
    claim_type: ClaimType
    statement: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    falsification_tests: list[FalsificationTest] = Field(default_factory=list)
    completed_tests: list[str] = Field(default_factory=list)
    unresolved_tests: list[str] = Field(default_factory=list)
    unavailable_tests: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.unresolved
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    raw_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    calibrated_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    homology_support: float | None = Field(default=None, ge=0.0, le=1.0)
    orthology_class: str | None = None
    architecture_state: str | None = None
    provenance: ClaimProvenance = Field(default_factory=lambda: ClaimProvenance(stage="unspecified"))
    rationale: str = ""

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and "claim_id" not in data and "id" in data:
            data = dict(data)
            data["claim_id"] = data.pop("id")
        return data

    @model_validator(mode="after")
    def _sync_test_lists(self) -> Claim:
        if not self.falsification_tests:
            return self
        self.completed_tests = [t.test_id for t in self.falsification_tests if t.status == "completed"]
        self.unresolved_tests = [t.test_id for t in self.falsification_tests if t.status == "unresolved"]
        self.unavailable_tests = [t.test_id for t in self.falsification_tests if t.status == "skipped"]
        return self

    @computed_field
    @property
    def id(self) -> str:
        return self.claim_id

    @property
    def disconfirming_tests(self) -> list[str]:
        return [t.name for t in self.falsification_tests]


class ToolResult(BaseModel):
    name: str
    stage: str
    ok: bool
    returncode: int = 0
    command: list[str] = Field(default_factory=list)
    stdout_path: str | None = None
    stderr_path: str | None = None
    outputs: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AgentDecision(BaseModel):
    decision: Literal["continue", "rerun", "stop", "ask_human"]
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    requested_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PlannerDecision(BaseModel):
    """Compact planner JSON for Agentic V2. Mapped onto AgentDecision after parsing."""

    decision: Literal["investigate", "finalize", "abstain"]
    leading_hypothesis: str | None = None
    alternative_hypothesis: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    requested_action: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str


class CriticReview(BaseModel):
    verdict: Literal["accept", "challenge"]
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    disconfirming_tests: list[str] = Field(default_factory=list)


class CriticDecision(BaseModel):
    """Compact critic JSON for Agentic V2. Mapped onto CriticReview after parsing."""

    verdict: Literal["accept", "challenge"]
    evidence_ids: list[str] = Field(default_factory=list)
    requested_action: str | None = None
    failure_mode: str | None = None
    rationale: str


class RunState(BaseModel):
    run_id: str
    out_dir: str
    inputs: dict[str, str]
    evidence: list[Evidence] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    relations: list[EvidenceRelation] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    decisions: list[AgentDecision] = Field(default_factory=list)
    critic_reviews: list[CriticReview] = Field(default_factory=list)
    locus_evidence: list[LocusEvidence] = Field(default_factory=list)
    stopped: bool = False
    stop_reason: str | None = None

    def evidence_map(self) -> dict[str, Evidence]:
        return {e.id: e for e in self.evidence}

    def unknown_evidence_ids(self, ids: list[str]) -> list[str]:
        known = self.evidence_map()
        return [eid for eid in ids if eid not in known]

    def require_evidence_ids(self, ids: list[str]) -> list[str]:
        unknown = self.unknown_evidence_ids(ids)
        if unknown:
            raise ValueError(f"Unknown evidence IDs cited: {unknown}")
        return list(ids)

    def add_relation(self, source_id: str, target_id: str, kind: EvidenceRelationType, note: str = "") -> EvidenceRelation:
        if target_id not in self.evidence_map():
            raise ValueError(f"Cannot relate {source_id} to unknown evidence {target_id}")
        rel = EvidenceRelation(source_id=source_id, target_id=target_id, kind=kind, note=note)
        self.relations.append(rel)
        return rel

    def bind_claim(self, claim: Claim) -> Claim:
        claim.supporting_evidence_ids = self.require_evidence_ids(claim.supporting_evidence_ids)
        claim.contradicting_evidence_ids = self.require_evidence_ids(claim.contradicting_evidence_ids)
        for test in claim.falsification_tests:
            if test.evidence_ids:
                test.evidence_ids = self.require_evidence_ids(test.evidence_ids)
        cited = list(dict.fromkeys(claim.supporting_evidence_ids + claim.contradicting_evidence_ids))
        claim.provenance.evidence_ledger_ids = list(dict.fromkeys(cited + claim.provenance.evidence_ledger_ids))
        for eid in claim.supporting_evidence_ids:
            self.add_relation(claim.claim_id, eid, EvidenceRelationType.supports)
        for eid in claim.contradicting_evidence_ids:
            self.add_relation(claim.claim_id, eid, EvidenceRelationType.contradicts)
        for test in claim.falsification_tests:
            for eid in test.evidence_ids:
                self.add_relation(claim.claim_id, eid, EvidenceRelationType.tested_by, note=test.test_id)
        self.claims.append(claim)
        return claim

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2))
