from pathlib import Path

from genome_skeptic.config import Settings
from genome_skeptic.families import load_family
from genome_skeptic.models import ClaimStatus, ClaimType, GeneSearchHit, TargetProfile, TargetType
from genome_skeptic.validators.family_orthology import FamilyEvidence, classify_family_orthology, family_detects_orthologue
from genome_skeptic.validators.homology import strong_hit
from genome_skeptic.claims.confidence import confidence_for_target_type
from genome_skeptic.eval.calibration import BIN_EDGES, apply_calibrated_confidence, fit_calibration
from genome_skeptic.tools.gene_search import extract_orfs


ROOT = Path(__file__).resolve().parents[1]


def test_family_excludes_hidden_benchmark_proteins():
    family = load_family("rpoB_RNAP_beta")
    assert family is not None
    ids = {m.protein_id for m in family.members}
    assert "NP_418414.1" in ids
    forbidden = {
        "NP_252960.1", "WP_000037869.1", "NP_463022.1", "WP_003255495.1",
        "YP_499096.2", "NP_387988.1",
    }
    assert not (ids & forbidden)
    assert len(family.members) >= 5
    species = " ".join(m.species.lower() for m in family.members)
    assert "helicobacter" not in species
    assert "pylori" not in species
    assert "salmonella" not in species


def test_no_species_name_hardcode_in_orthology_code():
    src = (ROOT / "src" / "genome_skeptic" / "validators" / "family_orthology.py").read_text(encoding="utf-8").lower()
    conf = (ROOT / "src" / "genome_skeptic" / "claims" / "confidence.py").read_text(encoding="utf-8").lower()
    assert "pylori" not in src
    assert "helicobacter" not in src
    assert "pylori" not in conf
    assert "if species" not in src


def test_domain_only_hmm_is_not_full_orthologue():
    settings = Settings()
    profile = TargetProfile(query_id="rpoB", sequence="M" * 80, target_type=TargetType.gene_orthologue, family_id="rpoB_RNAP_beta")
    ev = FamilyEvidence(
        family_id="rpoB_RNAP_beta",
        architecture="domain_only",
        domain_only=True,
        supports_orthologue=False,
        best_hmm={"full_evalue": 1e-20, "model_coverage": 0.22, "n_domains": 1, "full_score": 80.0},
        metrics={"hmm_model_coverage": 0.22, "domain_only": True, "n_supporting_members": 0, "reference_set_agreement": 0.0},
    )
    assert family_detects_orthologue(profile, [], settings, ev) is False
    domain_hit = GeneSearchHit(
        query_id="rpoB", contig_id="c1", search_kind="domain",
        qstart=0, qend=40, tstart=10, tend=130, strand="+",
        identity=0.95, query_coverage=0.25, alignment_length=120,
        query_length=200, contig_length=400, domain_name="RNAP_beta",
    )
    assert strong_hit(domain_hit, settings, TargetType.gene_orthologue) is False


def test_pairwise_identity_does_not_reject_family_hmm_orthologue():
    settings = Settings()
    family = load_family("rpoB_RNAP_beta")
    weak = GeneSearchHit(
        query_id="rpoB", contig_id="c1", search_kind="translated",
        qstart=0, qend=1300, tstart=10, tend=3920, strand="+",
        identity=0.46, query_coverage=0.99, alignment_length=3900,
        query_length=1342, contig_length=9000,
    )
    assert strong_hit(weak, settings, TargetType.gene_orthologue) is False
    ev = FamilyEvidence(
        family_id="rpoB_RNAP_beta",
        member_hits=[weak],
        architecture="fusion",
        fusion={"supported": True, "state": "fusion", "additional_sequence_known_family": True, "orf_length_aa": 2890},
        best_hmm={"full_evalue": 1e-80, "model_coverage": 0.92, "query_coverage": 0.45, "n_domains": 6, "full_score": 400.0,
                  "domains": [{"hmm_from": 1, "hmm_to": 1200}]},
        metrics={"hmm_model_coverage": 0.92, "n_supporting_members": 3, "reference_set_agreement": 0.4,
                 "best_member_identity": 0.46, "best_member_coverage": 0.99, "hierarchy": ["profile_hmm_family_match"]},
    )
    classify_family_orthology(ev, family, settings, query_hits=[weak])
    assert ev.supports_orthologue is True
    profile = TargetProfile(query_id="rpoB", sequence="M", target_type=TargetType.gene_orthologue)
    assert family_detects_orthologue(profile, [weak], settings, ev) is True


def test_extract_orfs_keeps_coordinates():
    from genome_skeptic.tools.gene_search import extract_orfs
    aa = "M" + "A" * 100 + "W"
    # reverse translate roughly via repeating AAA lysine... use ATG + GCT*100 + TGG TAA
    nt = "ATG" + "GCT" * 100 + "TGGTAA"
    orfs = extract_orfs([("c1", "A" * 30 + nt + "C" * 30)], min_aa=50)
    assert any(o["length_aa"] >= 100 and o["contig_id"] == "c1" for o in orfs)


def test_target_type_confidence_is_not_universal():
    allele = confidence_for_target_type(
        ClaimStatus.supported, [], target_type=TargetType.exact_allele,
        homology_support=0.99, not_detected=False, max_supported=0.85, identity=0.995, coverage=0.99,
    )
    ortho = confidence_for_target_type(
        ClaimStatus.weakened, [], target_type=TargetType.gene_orthologue,
        homology_support=0.45, not_detected=False, max_supported=0.85,
        family_metrics={"best_member_identity": 0.46, "best_member_coverage": 0.99, "hmm_model_coverage": 0.9,
                        "hmm_full_evalue": 1e-50, "reference_set_agreement": 0.4, "architecture": "fusion",
                        "hierarchy": ["profile_hmm_family_match"]},
    )
    family = confidence_for_target_type(
        ClaimStatus.supported, [], target_type=TargetType.protein_family,
        homology_support=0.30, not_detected=False, max_supported=0.85,
        family_metrics={"hmm_model_coverage": 0.35, "hmm_full_evalue": 1e-8, "hmm_n_domains": 1},
    )
    assert allele != ortho != family
    assert allele > ortho


def test_calibration_frozen_on_development_bins():
    pairs = [
        {"target_type": "gene_orthologue", "confidence": 0.82, "correct": 1},
        {"target_type": "gene_orthologue", "confidence": 0.81, "correct": 0},
        {"target_type": "gene_orthologue", "confidence": 0.22, "correct": 0},
        {"target_type": "exact_allele", "confidence": 0.84, "correct": 1},
    ]
    model = fit_calibration(pairs)
    assert model["held_out_used_to_fit"] is False
    assert model["fit_split"] == "development"
    mapped = apply_calibrated_confidence(0.81, model, "gene_orthologue")
    assert 0.0 <= mapped <= 1.0
    assert len(BIN_EDGES) == 11


def test_adjacent_operon_is_not_fusion():
    from genome_skeptic.validators.family_orthology import _architecture

    settings = Settings()
    family = load_family("rpoB_RNAP_beta")
    orf_rpob = {
        "orf_id": "c1:100-4100:+", "contig_id": "c1", "start": 100, "end": 4100,
        "strand": "+", "length_aa": 1333, "near_contig_edge": False,
    }
    orf_long = {
        "orf_id": "c1:5000-10154:+", "contig_id": "c1", "start": 5000, "end": 10154,
        "strand": "+", "length_aa": 1718, "near_contig_edge": False,
    }
    member_hits = [
        GeneSearchHit(
            query_id="NP_418414.1", contig_id="c1", search_kind="translated",
            qstart=0, qend=1342, tstart=100, tend=4100, strand="+",
            identity=0.99, query_coverage=0.99, alignment_length=4000,
            query_length=1342, contig_length=20000,
        )
    ]
    partner_hits = [
        GeneSearchHit(
            query_id="NP_418415.1", contig_id="c1", search_kind="translated",
            qstart=0, qend=1400, tstart=4200, tend=8400, strand="+",
            identity=0.76, query_coverage=0.96, alignment_length=4200,
            query_length=1407, contig_length=20000,
        )
    ]
    hmm_by = {
        "c1:100-4100:+": {
            "target_id": "c1:100-4100:+",
            "full_evalue": 1e-80,
            "full_score": 1000,
            "model_coverage": 0.99,
            "query_coverage": 0.99,
            "n_domains": 1,
            "query_length": 1333,
            "domains": [{"hmm_from": 1, "hmm_to": 1200}],
        }
    }
    arch, fusion, *_ = _architecture(
        family=family,
        member_hits=member_hits,
        hmm_by_target=hmm_by,
        partner_hmm={},
        partner_hits=partner_hits,
        orfs=[orf_rpob, orf_long],
        settings=settings,
    )
    assert fusion.get("supported") is False
    assert arch != "fusion"


def test_same_orf_partner_is_fusion():
    from genome_skeptic.validators.family_orthology import _architecture

    settings = Settings()
    family = load_family("rpoB_RNAP_beta")
    orf = {
        "orf_id": "c1:100-8800:+", "contig_id": "c1", "start": 100, "end": 8800,
        "strand": "+", "length_aa": 2900, "near_contig_edge": False,
    }
    member_hits = [
        GeneSearchHit(
            query_id="NP_418414.1", contig_id="c1", search_kind="translated",
            qstart=0, qend=1342, tstart=100, tend=4126, strand="+",
            identity=0.46, query_coverage=0.99, alignment_length=4000,
            query_length=1342, contig_length=12000,
        )
    ]
    partner_hits = [
        GeneSearchHit(
            query_id="NP_418415.1", contig_id="c1", search_kind="translated",
            qstart=0, qend=1400, tstart=4126, tend=8400, strand="+",
            identity=0.55, query_coverage=0.66, alignment_length=4200,
            query_length=1407, contig_length=12000,
        )
    ]
    hmm_by = {
        "c1:100-8800:+": {
            "target_id": "c1:100-8800:+",
            "full_evalue": 1e-80,
            "full_score": 400,
            "model_coverage": 0.92,
            "query_coverage": 0.45,
            "n_domains": 6,
            "query_length": 2900,
            "domains": [{"hmm_from": 1, "hmm_to": 1200}],
        }
    }
    arch, fusion, *_ = _architecture(
        family=family,
        member_hits=member_hits,
        hmm_by_target=hmm_by,
        partner_hmm={},
        partner_hits=partner_hits,
        orfs=[orf],
        settings=settings,
    )
    assert fusion.get("supported") is True
    assert arch == "fusion"
    src = (ROOT / "src" / "genome_skeptic" / "validators" / "family_orthology.py").read_text(encoding="utf-8").lower()
    assert "pylori" not in src