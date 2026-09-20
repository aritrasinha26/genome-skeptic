"""Three analysis systems on the same agent-visible inputs."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from genome_skeptic.claims.followups import recommended_followups
from genome_skeptic.config import Settings
from genome_skeptic.eval.assemble import assemble_reads
from genome_skeptic.eval.isolation import assert_agent_accessible
from genome_skeptic.isolation import assert_agent_accessible as _agent
from genome_skeptic.locus.pipeline import analyze_targets_on_assembly
from genome_skeptic.models import Claim, ClaimProvenance, ClaimStatus, ClaimType
from genome_skeptic.tools.base import available, run_command
from genome_skeptic.tools.gene_search import run_gene_search
from genome_skeptic.validators.gene_target import hits_from_metrics
from genome_skeptic.validators.homology import strong_hit
from genome_skeptic.targets import load_target_profiles


def assemble_case(r1: Path, r2: Path | None, out_dir: Path) -> Path:
    _agent(r1)
    _agent(r2)
    out_dir.mkdir(parents=True, exist_ok=True)
    return assemble_reads(r1, r2, out_dir / "contigs.fa")


def maybe_map_reads(assembly: Path, r1: Path, r2: Path | None, out_dir: Path) -> Path | None:
    """Map reads when minimap2 is installed. Never invent alignments."""
    _agent(assembly)
    _agent(r1)
    _agent(r2)
    if not available("minimap2"):
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    sam = out_dir / "mapped.sam"
    cmd = ["minimap2", "-ax", "sr", "-o", str(sam), str(assembly), str(r1)]
    if r2 and r2.exists():
        cmd.append(str(r2))
    result = run_command("minimap2", "mapping", cmd, out_dir)
    if result.ok and sam.exists() and sam.stat().st_size > 0:
        return sam
    return None


def run_conventional(assembly: Path, targets: Path, out_dir: Path, settings: Settings) -> list[Claim]:
    """Standard homology pipeline: identity/coverage call scoped to the assembly.

    This is ordinary bioinformatics practice, not a deliberately weak baseline.
    It does not run Genome Skeptic falsification tests.
    """
    assert_agent_accessible(assembly)
    assert_agent_accessible(targets)
    out_dir.mkdir(parents=True, exist_ok=True)
    search = run_gene_search(targets, assembly, out_dir / "search", settings)
    hits = hits_from_metrics(search.metrics) if search.ok else []
    claims = []
    min_id = settings.thresholds.gene_nt_min_identity
    min_cov = settings.thresholds.gene_nt_min_query_coverage
    for profile in load_target_profiles(str(targets)):
        qh = [h for h in hits if h.query_id == profile.query_id]
        detected = any(strong_hit(h, settings, profile.target_type) for h in qh)
        if detected:
            statement = (
                f"A homolog of target gene '{profile.query_id}' was detected in the assembly "
                f"(identity ≥ {min_id:.0%}, query coverage ≥ {min_cov:.0%})."
            )
            claim_type = ClaimType.target_gene_detected
            status = ClaimStatus.supported
            conf = 0.90
            rationale = "Standard nucleotide homology thresholds were met. Adversarial falsification was not run."
        else:
            statement = (
                f"No homolog of target gene '{profile.query_id}' was detected in the assembly "
                f"at identity ≥ {min_id:.0%} and query coverage ≥ {min_cov:.0%}."
            )
            claim_type = ClaimType.target_gene_not_detected
            status = ClaimStatus.supported
            conf = 0.70
            rationale = "No hit met standard homology thresholds. This is a search result for the current assembly, not an organism-level absence claim."
        claims.append(Claim(
            claim_id=f"C_target_{profile.query_id}",
            claim_type=claim_type,
            statement=statement,
            status=status,
            confidence=conf,
            evidence_completeness=0.15,
            rationale=rationale,
            provenance=ClaimProvenance(created_by="conventional_pipeline", stage="target_gene"),
        ))
    return claims


def run_skeptic(
    assembly: Path,
    targets: Path,
    out_dir: Path,
    settings: Settings,
    *,
    references: Path | None,
    enable_falsification: bool,
    gff: Path | None = None,
    proteins: Path | None = None,
    declared_organism: str | None = None,
    mapping_sam: Path | None = None,
    depth_tsv: Path | None = None,
) -> tuple[list[Claim], list]:
    cfg = deepcopy(settings)
    cfg.execution.enable_falsification = enable_falsification
    return analyze_targets_on_assembly(
        targets=targets,
        assembly=assembly,
        settings=cfg,
        assembly_gff=gff,
        proteins=proteins,
        references_yaml=references,
        out_dir=out_dir,
        declared_organism=declared_organism,
        mapping_sam=mapping_sam,
        depth_tsv=depth_tsv,
    )[:2]


def followups_for(claims: list[Claim]) -> list[str]:
    return recommended_followups(claims)


def run_dummy_cautious(targets: Path) -> list[Claim]:
    """Trivial baseline: always assembly-scoped non-detection with generic caution. No homology."""
    claims = []
    for profile in load_target_profiles(str(targets)):
        claims.append(Claim(
            claim_id=f"C_target_{profile.query_id}",
            claim_type=ClaimType.target_gene_not_detected,
            statement=f"Target gene '{profile.query_id}' was not detected in the current assembly.",
            status=ClaimStatus.weakened,
            confidence=0.46,
            evidence_completeness=0.63,
            rationale="Dummy cautious baseline with no biological reasoning. Non-detection is scoped to the current assembly.",
            provenance=ClaimProvenance(created_by="dummy_cautious_baseline", stage="target_gene"),
        ))
    return claims


def run_naive_confident(assembly: Path, targets: Path, out_dir: Path, settings: Settings) -> list[Claim]:
    """Reckless baseline: convert homology threshold calls into organism-level present/absent."""
    assert_agent_accessible(assembly)
    assert_agent_accessible(targets)
    out_dir.mkdir(parents=True, exist_ok=True)
    search = run_gene_search(targets, assembly, out_dir / "search", settings)
    hits = hits_from_metrics(search.metrics) if search.ok else []
    claims = []
    for profile in load_target_profiles(str(targets)):
        qh = [h for h in hits if h.query_id == profile.query_id]
        detected = any(strong_hit(h, settings, profile.target_type) for h in qh)
        if detected:
            statement = f"Target gene '{profile.query_id}' is present in the isolate."
            claim_type = ClaimType.target_gene_detected
            rationale = "Naive confident baseline treated a homology threshold call as organism-level presence."
        else:
            statement = f"Target gene '{profile.query_id}' is absent from the organism."
            claim_type = ClaimType.target_gene_not_detected
            rationale = "Naive confident baseline treated a homology threshold miss as organism-level absence."
        claims.append(Claim(
            claim_id=f"C_target_{profile.query_id}",
            claim_type=claim_type,
            statement=statement,
            status=ClaimStatus.supported,
            confidence=0.99,
            evidence_completeness=0.15,
            rationale=rationale,
            provenance=ClaimProvenance(created_by="naive_confident_baseline", stage="target_gene"),
        ))
    return claims
