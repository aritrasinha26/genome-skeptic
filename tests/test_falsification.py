from genome_skeptic.claims.state_machine import confidence_for, resolve_claim_status
from genome_skeptic.config import ExecutionConfig, Settings
from genome_skeptic.models import (
    CatalyticResidue,
    ClaimStatus,
    ClaimType,
    FalsificationResult,
    FalsificationTest,
    GeneSearchHit,
    QueryDomain,
    TargetProfile,
)
from genome_skeptic.tools.gene_search import search_targets
from genome_skeptic.validators.falsification import (
    TargetMeasurements,
    assert_claim_not_stronger_than_evidence,
    build_target_gene_claim,
)
from genome_skeptic.validators.homology import FORBIDDEN_ABSENCE_PHRASES


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
        "tstart": 80,
        "tend": 80 + len(GENE),
        "strand": "+",
        "identity": 1.0,
        "query_coverage": 1.0,
        "alignment_length": len(GENE),
        "query_length": len(GENE),
        "contig_length": 80 + len(GENE) + 80,
    }
    data.update(kwargs)
    return GeneSearchHit.model_validate(data)


def _settings(*, voi: bool = True) -> Settings:
    """Default Settings enable VOI pruning. Historical attack-plan ID tests
    inspect supporting tests that are not in the VOI diagnostic catalog, so
    those tests disable VOI in the harness only. Scientific thresholds are
    unchanged.
    """
    return Settings(execution=ExecutionConfig(enable_voi_policy=voi))


def _claim(hits, profile=None, settings=None, **meas):
    settings = settings or Settings()
    profile = profile or _profile()
    m = TargetMeasurements(query_id=profile.query_id, profile=profile, hits=hits, tools_run=["internal_gene_search"], **meas)
    claim, _anoms, tests = build_target_gene_claim(m, settings, ["E001"])
    assert_claim_not_stronger_than_evidence(claim)
    blob = (claim.statement + " " + claim.rationale).lower()
    assert all(p not in blob for p in FORBIDDEN_ABSENCE_PHRASES)
    assert claim.confidence < 0.95
    assert claim.falsification_tests
    assert claim.provenance.created_by == "deterministic_validator"
    return claim, tests


def test_state_machine_supported_is_not_certainty():
    tests = [
        FalsificationTest(test_id="a", name="a", hypothesis="h", blocking=True, status="completed", result=FalsificationResult.supports_claim),
        FalsificationTest(test_id="b", name="b", hypothesis="h", blocking=False, status="skipped", result=FalsificationResult.not_run),
    ]
    status = resolve_claim_status(tests)
    assert status == ClaimStatus.supported
    conf = confidence_for(status, tests, base=0.9, max_supported=0.85)
    assert conf <= 0.85


def test_fragmented_gene_does_not_claim_absence_or_full_detection():
    settings = Settings()
    left, right = GENE[:72], GENE[72:]
    hits = search_targets([("rpoB", GENE)], [("c1", "A" * 30 + left), ("c2", right + "C" * 30)], settings)
    claim, tests = _claim(hits, depth_available=False, annotation_available=False)
    assert claim.claim_type == ClaimType.target_gene_not_detected
    assert claim.status in {ClaimStatus.weakened, ClaimStatus.unresolved}
    assert "not detected in the current assembly" in claim.statement
    assert any("fragmentation" in t.test_id or "partial" in t.test_id or "nucleotide" in t.test_id for t in tests if t.result == FalsificationResult.weakens_claim)


def test_paralogue_weakens_detection():
    hits = [
        _hit(contig_id="c1"),
        _hit(contig_id="c2", tstart=10, tend=10 + len(GENE), contig_length=200),
    ]
    claim, tests = _claim(hits, contig_sequences={"c1": "A" * 80 + GENE + "C" * 80, "c2": "T" * 10 + GENE + "G" * 10})
    assert claim.claim_type == ClaimType.target_gene_detected
    assert claim.status == ClaimStatus.weakened
    para = next(t for t in tests if t.test_id.startswith("wrong_paralogue"))
    assert para.result == FalsificationResult.weakens_claim
    assert "functional" not in claim.statement.lower()


def test_single_conserved_domain_is_not_full_gene_detection():
    settings = Settings()
    aa_len = 80
    profile = _profile(domains=[QueryDomain(name="d1", start=0, end=40), QueryDomain(name="d2", start=40, end=aa_len)], expected_length_aa=aa_len)
    nt_half = GENE[: len(GENE) // 2]
    hits = search_targets([("rpoB", GENE)], [("c1", "A" * 40 + nt_half)], settings)
    domain_hit = _hit(
        search_kind="domain",
        qstart=0,
        qend=40,
        identity=0.95,
        query_coverage=40 / 126,
        alignment_length=120,
        domain_name="d1",
        query_length=len(GENE),
    )
    claim, tests = _claim(hits + [domain_hit], profile=profile, depth_available=False, annotation_available=False)
    assert claim.claim_type != ClaimType.target_gene_detected or claim.status != ClaimStatus.supported
    assert claim.status in {ClaimStatus.weakened, ClaimStatus.unresolved, ClaimStatus.rejected}
    assert "not detected" in claim.statement or claim.status != ClaimStatus.supported


def test_contig_end_gene_stays_weaker_than_presence():
    settings = Settings()
    hits = search_targets([("rpoB", GENE)], [("c1", "G" * 40 + GENE[:48])], settings)
    claim, tests = _claim(hits, depth_available=False, annotation_available=False)
    assert claim.status in {ClaimStatus.weakened, ClaimStatus.unresolved}
    assert any(t.test_id.startswith("contig_edge_truncation") and t.result == FalsificationResult.weakens_claim for t in tests)
    assert "absent from the organism" not in (claim.statement + claim.rationale).lower()


def test_contaminant_contig_weakens_detection():
    hits = [_hit(contig_id="contaminant")]
    key = f"rpoB:contaminant:{hits[0].tstart}-{hits[0].tend}"
    claim, tests = _claim(
        hits,
        settings=_settings(voi=False),
        coverage_by_hit={key: {"relative_depth": 0.08, "local_mean_depth": 2.0, "genome_mean_depth": 25.0}},
        depth_available=True,
        contig_gc={"contaminant": 0.72, "c1": 0.50},
        genome_gc=0.50,
        checkm_contamination=12.0,
    )
    assert claim.claim_type == ClaimType.target_gene_detected
    assert claim.status == ClaimStatus.weakened
    ids = {t.test_id.split(":")[0]: t.result for t in tests}
    assert ids["contamination"] == FalsificationResult.weakens_claim
    assert ids["abnormal_contig_coverage"] == FalsificationResult.weakens_claim
    assert "isolate carries" not in claim.statement.lower()


def test_divergent_homolog_found_only_by_protein_search():
    hits = [_hit(search_kind="translated", identity=0.70, query_coverage=0.88, alignment_length=120, qend=42, query_length=42)]
    claim, tests = _claim(hits, depth_available=False, annotation_available=False)
    assert not any(h.search_kind == "nucleotide" for h in hits)
    assert "absent" not in claim.statement.lower()
    if claim.claim_type == ClaimType.target_gene_detected:
        assert claim.status in {ClaimStatus.supported, ClaimStatus.weakened, ClaimStatus.unresolved}
    else:
        div = next(t for t in tests if t.test_id.startswith("divergent_homologues"))
        assert div.result in {FalsificationResult.weakens_claim, FalsificationResult.rejects_claim}
        assert claim.status in {ClaimStatus.weakened, ClaimStatus.rejected, ClaimStatus.unresolved}


def test_clean_assembly_lacking_target_is_assembly_level_only():
    claim, tests = _claim(
        [],
        profile=_profile(expected_neighbors=["rpoA", "rpoC"]),
        neighborhood_by_hit={"_assembly": {"products": ["rpoA", "rpoC"]}},
        annotation_available=True,
        depth_available=True,
        proteins_available=True,
    )
    assert claim.claim_type == ClaimType.target_gene_not_detected
    assert claim.status == ClaimStatus.supported
    assert claim.confidence <= 0.65
    assert "not detected in the current assembly" in claim.statement
    assert "missing from the organism" in claim.rationale
    assert all(t.status == "completed" for t in tests if t.blocking)


def test_missing_catalytic_residues_weaken_detection():
    mutated = GENE[:12] + "GCC" + GENE[15:]
    contig = "A" * 80 + mutated + "C" * 80
    hits = [_hit()]
    profile = _profile(catalytic_residues=[CatalyticResidue(position=4, residue="S")])
    claim, tests = _claim(
        hits,
        profile=profile,
        settings=_settings(voi=False),
        contig_sequences={"c1": contig},
    )
    cat = next(t for t in tests if t.test_id.startswith("missing_catalytic_residues"))
    assert cat.status == "completed"
    assert cat.result == FalsificationResult.weakens_claim
    assert claim.status == ClaimStatus.weakened
    assert claim.confidence < 0.95
