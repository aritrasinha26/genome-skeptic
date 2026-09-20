from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    organism_mode: str = "bacterial_isolate"
    threads: int = 8


class LLMRoleConfig(BaseModel):
    """Optional planner/critic overlay. Unset fields inherit from llm."""

    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    timeout_seconds: int | None = None
    thinking: bool | None = None
    keep_alive: str | None = None
    max_output_tokens: int | None = None


class LLMConfig(BaseModel):
    enabled: bool = True
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "qwen3:8b"
    temperature: float = 0.1
    timeout_seconds: int = 180
    api_key: str | None = None
    thinking: bool | None = False
    keep_alive: str | None = "30m"
    max_output_tokens: int | None = 256
    planner: LLMRoleConfig | None = None
    critic: LLMRoleConfig | None = None

    def for_role(self, role: str) -> "LLMConfig":
        overlay = getattr(self, role, None)
        data = self.model_dump(exclude={"planner", "critic"})
        if overlay is not None:
            for key, value in overlay.model_dump().items():
                if value is not None:
                    data[key] = value
        return LLMConfig(**data)


class PathConfig(BaseModel):
    bakta_db: str | None = None
    checkm2_db: str | None = None
    hmm_db: str | None = None
    references: str | None = None
    taxonomy_db: str | None = None
    family_dir: str | None = None


class ThresholdConfig(BaseModel):
    min_q30_rate: float = 0.75
    min_post_trim_read_fraction: float = 0.70
    bacterial_genome_min_bp: int = 500_000
    bacterial_genome_max_bp: int = 15_000_000
    max_contigs_soft: int = 300
    min_n50_soft_bp: int = 20_000
    min_mapping_rate_soft: float = 0.90
    min_completeness_soft: float = 90.0
    max_contamination_soft: float = 5.0
    max_contamination_hard: float = 10.0
    min_gene_density_per_kb_soft: float = 0.60
    max_gene_density_per_kb_soft: float = 1.40
    gene_nt_min_identity: float = 0.80
    gene_nt_min_query_coverage: float = 0.80
    gene_aa_min_identity: float = 0.60
    gene_aa_min_query_coverage: float = 0.80
    allele_min_identity: float = 0.99
    allele_min_query_coverage: float = 0.95
    gene_partial_min_nt_bp: int = 60
    gene_partial_min_aa: int = 20
    contig_edge_proximity_bp: int = 300
    gene_search_kmer_nt: int = 8
    gene_search_kmer_aa: int = 3
    gene_max_hits_per_query: int = 20
    gene_length_ratio_min: float = 0.80
    gene_length_ratio_max: float = 1.20
    gene_paralogue_min_loci: int = 2
    gene_paralogue_min_coverage: float = 0.50
    gene_coverage_weaken_below: float = 0.90
    gene_domain_short_coverage: float = 0.50
    gene_relative_depth_low: float = 0.50
    gene_relative_depth_high: float = 2.50
    gene_gc_outlier: float = 0.15
    max_claim_confidence: float = 0.85
    max_not_detected_confidence: float = 0.65
    synteny_flank_genes: int = 2
    synteny_spacing_fold: float = 3.0
    orthologue_min_identity: float = 0.50
    orthologue_min_coverage: float = 0.70
    break_edge_window_bp: int = 80
    break_clip_rate: float = 0.15
    break_mate_unmapped_rate: float = 0.20
    # Family/HMM thresholds are a priori biological cutoffs, not held-out-tuned scores.
    hmm_full_evalue_max: float = 1e-10
    hmm_model_coverage_orthologue: float = 0.70
    hmm_domain_only_max_model_coverage: float = 0.45
    family_member_min_identity: float = 0.35
    family_member_min_coverage: float = 0.70
    family_min_supporting_members: int = 2
    fusion_length_ratio_min: float = 1.35
    fusion_partner_evalue_max: float = 1e-5
    split_max_intergenic_bp: int = 200
    orf_min_aa: int = 80
    locus_window_bp: int = 12000
    locus_orf_min_aa: int = 30
    hmm_min_gate_model_coverage: float = 0.20
    hmm_unresolved_model_coverage: float = 0.55
    family_competitive_margin: float = 0.10
    family_competitive_ambiguous_band: float = 0.05
    multiplicity_min_identity: float = 0.85
    multiplicity_min_coverage: float = 0.70


class ExecutionConfig(BaseModel):
    stop_on_hard_gate: bool = True
    keep_intermediates: bool = True
    allow_model_to_choose_actions: bool = True
    enable_falsification: bool = True
    enable_synteny: bool = True
    enable_mapping_breaks: bool = True
    enable_orthology: bool = True
    enable_family_orthology: bool = True
    enable_locus_reconstruction: bool = True
    enable_hypothesis_graph: bool = True
    enable_voi_policy: bool = True
    enable_phylogeny: bool = True
    enable_critic: bool = True
    apply_completeness_to_confidence: bool = True


class AssemblyConfig(BaseModel):
    """Runtime assembly/QC profile. Does not change claim or scoring rules.

    Default values preserve the full-production isolate stack. FAST_PILOT is opt-in.
    """

    profile: str = "production"
    skip_fastqc: bool = False
    only_assembler: bool = False
    kmers: str | None = None
    careful: bool = False
    isolate: bool = True
    min_memory_gb: int = 6
    preferred_memory_gb: int = 8
    preferred_threads: int = 4
    preferred_if_wsl_ram_gb: int = 12
    clean_coverage: float = 25.0
    low_coverage: float = 8.0
    include_low_coverage_case: bool = False
    include_contamination_case: bool = False
    banner: str = "FAST PILOT - NOT FINAL BENCHMARK"


class Settings(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    assembly: AssemblyConfig = Field(default_factory=AssemblyConfig)


def load_settings(path: str | Path | None) -> Settings:
    if path is None:
        return Settings()
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text()) or {}
    settings = Settings.model_validate(raw)
    from genome_skeptic.isolation import assert_agent_accessible
    for key, value in settings.paths.model_dump().items():
        if value:
            assert_agent_accessible(value, role=f"config.paths.{key}")
    return settings


def is_fast_pilot(settings: Settings | None) -> bool:
    if settings is None:
        return False
    return (settings.assembly.profile or "").strip().lower() == "fast_pilot"
