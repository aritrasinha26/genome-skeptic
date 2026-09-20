from pathlib import Path

from genome_skeptic.config import LLMConfig, Settings
from genome_skeptic.models import (
    AgentDecision,
    Anomaly,
    ClaimStatus,
    ClaimType,
    CriticReview,
    Evidence,
    RunState,
    Severity,
    TargetProfile,
)
from genome_skeptic.orchestrator import GenomeOrchestrator
from genome_skeptic.tools.gene_search import run_gene_search, search_targets
from genome_skeptic.validators.gene_target import FORBIDDEN_ABSENCE_PHRASES, evaluate_target_gene, hits_from_metrics
from genome_skeptic.validators.homology import strong_hit


GENE = "ATG" + ("CGTAGC") * 20 + "TAA"


def _write_fa(path: Path, records: dict[str, str]) -> Path:
    path.write_text("".join(f">{name}\n{seq}\n" for name, seq in records.items()))
    return path


def _ids() -> dict[str, str]:
    return {
        "tool": "E001",
        "nucleotide": "E002",
        "translated": "E003",
        "partial": "E004",
        "edge": "E005",
        "coverage": "E006",
        "neighborhood": "E007",
    }


def _ledger_for_ids(eids: dict[str, str]) -> RunState:
    state = RunState(run_id="t", out_dir=".", inputs={})
    for eid in eids.values():
        state.evidence.append(Evidence(id=eid, stage="target_gene", kind="disconfirming_test", summary=eid))
    return state


def test_two_queries_are_not_starved_by_hit_cap(tmp_path: Path):
    settings = Settings()
    long_q = "ATG" + ("CGTAGC") * 40 + "TAA"
    other = "ATGAAACCCGGGTTTAAACCCGGGTTTAAA"
    targets = _write_fa(tmp_path / "targets.fa", {"a": long_q, "b": other})
    contigs = _write_fa(tmp_path / "contigs.fa", {"c1": "A" * 40 + long_q + "C" * 40 + other + "G" * 40})
    result = run_gene_search(targets, contigs, tmp_path / "out", settings)
    hits = hits_from_metrics(result.metrics)
    assert any(h.query_id == "a" for h in hits)
    assert any(h.query_id == "b" for h in hits)
    settings = Settings()
    targets = _write_fa(tmp_path / "targets.fa", {"rpoB": GENE})
    contigs = _write_fa(tmp_path / "contigs.fa", {"c1": "A" * 80 + GENE + "C" * 80})
    result = run_gene_search(targets, contigs, tmp_path / "out", settings)
    assert result.ok
    hits = hits_from_metrics(result.metrics)
    assert hits
    assert any(h.query_id == "rpoB" and h.search_kind == "nucleotide" and h.query_coverage >= 0.8 for h in hits)
    eids = _ids()
    claim, _anoms = evaluate_target_gene(
        "rpoB", hits, settings, eids, limitations=[],
        profile=TargetProfile(query_id="rpoB", sequence=GENE),
        contig_sequences={"c1": "A" * 80 + GENE + "C" * 80},
    )
    assert claim.claim_type == ClaimType.target_gene_detected
    assert claim.status == ClaimStatus.supported
    assert claim.confidence < 0.95
    assert claim.falsification_tests
    assert "detected in the current assembly" in claim.statement
    lowered = (claim.statement + claim.rationale).lower()
    assert all(p not in lowered for p in FORBIDDEN_ABSENCE_PHRASES)
    state = _ledger_for_ids(eids)
    state.bind_claim(claim)
    assert not state.unknown_evidence_ids(claim.supporting_evidence_ids)


def test_edge_truncated_gene_stays_unresolved():
    settings = Settings()
    hits = search_targets([("rpoB", GENE)], [("c1", "G" * 40 + GENE[:48])], settings)
    claim, anoms = evaluate_target_gene(
        "rpoB", hits, settings, _ids(), limitations=["no reference synteny database is configured"]
    )
    assert claim.status in {ClaimStatus.unresolved, ClaimStatus.weakened}
    assert any("edge" in a.id or "partial" in a.id or "falsify" in a.id for a in anoms) or any(
        t.test_id.startswith("contig_edge_truncation") for t in claim.falsification_tests
    )
    lowered = (claim.statement + " " + claim.rationale).lower()
    assert all(p not in lowered for p in FORBIDDEN_ABSENCE_PHRASES)


def test_no_homology_is_not_organism_absence():
    settings = Settings()
    claim, anoms = evaluate_target_gene(
        "rpoB",
        [],
        settings,
        _ids(),
        limitations=[
            "local coverage test requires a candidate locus; no homologous window was identified",
            "no reference synteny database is configured",
        ],
    )
    assert claim.status in {ClaimStatus.unresolved, ClaimStatus.supported}
    assert "not detected in the current assembly" in claim.statement
    assert not anoms
    lowered = (claim.statement + " " + claim.rationale).lower()
    assert all(p not in lowered for p in FORBIDDEN_ABSENCE_PHRASES)
    assert "missing from the organism" in claim.rationale


def test_clean_negative_without_limitations_still_not_organism_absence():
    settings = Settings()
    claim, _ = evaluate_target_gene("rpoB", [], settings, _ids(), limitations=[])
    assert "not detected in the current assembly" in claim.statement
    assert all(p not in (claim.statement + " " + claim.rationale).lower() for p in FORBIDDEN_ABSENCE_PHRASES)


def test_fragmented_hits_keep_claim_unresolved():
    settings = Settings()
    left = GENE[:72]
    right = GENE[72:]
    hits = search_targets([("rpoB", GENE)], [("c1", "A" * 30 + left), ("c2", right + "C" * 30)], settings)
    claim, anoms = evaluate_target_gene("rpoB", hits, settings, _ids(), limitations=[])
    if not any(strong_hit(h, settings) for h in hits):
        assert claim.status in {ClaimStatus.unresolved, ClaimStatus.weakened}
        assert any("fragmented" in a.id or "partial" in a.id or "falsify" in a.id for a in anoms) or any(
            "fragment" in t.test_id for t in claim.falsification_tests if t.result.value == "weakens_claim"
        )


def test_hard_gate_overrides_model_continue(tmp_path: Path):
    orch = GenomeOrchestrator(Settings(llm=LLMConfig(enabled=False)), tmp_path)
    state = RunState(run_id="t", out_dir=str(tmp_path), inputs={})
    state.anomalies.append(Anomaly(
        id="high_contamination_hard",
        stage="completeness",
        severity=Severity.hard,
        message="Estimated contamination is 15.0%",
    ))
    decision = AgentDecision(decision="continue", rationale="looks fine", evidence_ids=[], confidence=0.9)
    critic = CriticReview(verdict="accept", rationale="ok")
    assert orch._maybe_stop_after_review(state, "completeness", decision, critic)
    assert state.stopped
    assert "Hard validation gate" in (state.stop_reason or "")


def test_critic_challenge_stops_continuation(tmp_path: Path):
    orch = GenomeOrchestrator(Settings(llm=LLMConfig(enabled=False)), tmp_path)
    state = RunState(run_id="t", out_dir=str(tmp_path), inputs={})
    decision = AgentDecision(decision="continue", rationale="proceed", evidence_ids=[])
    critic = CriticReview(verdict="challenge", rationale="mapping is missing", failure_modes=["no read-back mapping"])
    assert orch._maybe_stop_after_review(state, "mapping", decision, critic)
    assert state.stopped
    assert "challenged" in (state.stop_reason or "").lower()


def test_dry_run_plans_target_gene_stage(tmp_path: Path):
    r1 = tmp_path / "r1.fastq"
    r1.write_text("@r1\nACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIII\n")
    targets = _write_fa(tmp_path / "targets.fa", {"rpoB": GENE})
    orch = GenomeOrchestrator(Settings(llm=LLMConfig(enabled=False)), tmp_path / "run")
    state = orch.run(r1, dry_run=True, targets=targets)
    plan = [e for e in state.evidence if e.kind == "dry_run"]
    assert plan
    assert "target gene reasoning" in plan[0].values["planned_stages"]
    assert "claim falsification engine" in plan[0].values["planned_stages"]
    assert not state.stopped
