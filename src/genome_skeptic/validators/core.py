from __future__ import annotations

from genome_skeptic.config import Settings
from genome_skeptic.models import Anomaly, Severity


def validate_fastp(metrics: dict, settings: Settings) -> list[Anomaly]:
    out: list[Anomaly] = []
    q30 = metrics.get("q30_rate")
    before = metrics.get("before_total_reads")
    after = metrics.get("after_total_reads")
    if q30 is not None and q30 < settings.thresholds.min_q30_rate:
        out.append(Anomaly(
            id="qc_low_q30",
            stage="qc_clean",
            severity=Severity.warning,
            message=f"Post-cleaning Q30 rate is low: {q30:.3f}",
            possible_explanations=["poor run quality", "aggressive read deterioration", "incorrect quality encoding or unusual platform"],
        ))
    if before and after:
        retained = after / before
        if retained < settings.thresholds.min_post_trim_read_fraction:
            out.append(Anomaly(
                id="qc_heavy_read_loss",
                stage="qc_clean",
                severity=Severity.warning,
                message=f"Only {retained:.1%} of reads were retained after cleaning",
                possible_explanations=["adapter contamination", "low-quality library", "overly aggressive trimming"],
            ))
    return out


def validate_assembly(metrics: dict, settings: Settings) -> list[Anomaly]:
    t = settings.thresholds
    out: list[Anomaly] = []
    total = metrics.get("total_bp")
    contigs = metrics.get("contigs")
    n50 = metrics.get("n50_bp")
    if total is not None and total < t.bacterial_genome_min_bp:
        out.append(Anomaly(id="assembly_too_small", stage="assembly_qc", severity=Severity.hard,
                           message=f"Assembly is only {total:,} bp, below the configured bacterial-isolate range",
                           possible_explanations=["failed assembly", "insufficient reads", "wrong input files"]))
    if total is not None and total > t.bacterial_genome_max_bp:
        out.append(Anomaly(id="assembly_too_large", stage="assembly_qc", severity=Severity.warning,
                           message=f"Assembly is {total:,} bp, above the configured bacterial-isolate range",
                           possible_explanations=["mixed culture", "contamination", "duplicated assembly", "unusual organism" ]))
    if contigs is not None and contigs > t.max_contigs_soft:
        out.append(Anomaly(id="assembly_fragmented", stage="assembly_qc", severity=Severity.warning,
                           message=f"Assembly has {contigs} contigs",
                           possible_explanations=["low coverage", "repeats", "contamination", "short-read limitations", "poor read quality"]))
    if n50 is not None and n50 < t.min_n50_soft_bp:
        out.append(Anomaly(id="assembly_low_n50", stage="assembly_qc", severity=Severity.warning,
                           message=f"N50 is only {n50:,} bp",
                           possible_explanations=["fragmentation", "mixed population", "insufficient coverage"]))
    return out


def validate_mapping(metrics: dict, settings: Settings) -> list[Anomaly]:
    out: list[Anomaly] = []
    rate = metrics.get("mapping_rate")
    zero = metrics.get("zero_coverage_fraction")
    cv = metrics.get("depth_cv")
    if rate is not None and rate < settings.thresholds.min_mapping_rate_soft:
        out.append(Anomaly(id="mapping_low_rate", stage="mapping", severity=Severity.warning,
                           message=f"Only {rate:.1%} of reads map back to the assembly",
                           possible_explanations=["missing sequence", "contamination", "poor assembly", "wrong read set"]))
    if zero is not None and zero > 0.01:
        out.append(Anomaly(id="mapping_zero_coverage", stage="mapping", severity=Severity.warning,
                           message=f"{zero:.1%} of assembly positions have zero read coverage",
                           possible_explanations=["unsupported contigs", "assembly artifact", "mapping limitations"]))
    if cv is not None and cv > 1.0:
        out.append(Anomaly(id="mapping_heterogeneous_depth", stage="mapping", severity=Severity.warning,
                           message=f"Coverage is highly heterogeneous, depth CV={cv:.2f}",
                           possible_explanations=["plasmids", "repeats", "contamination", "copy-number variation", "assembly collapse"]))
    return out


def validate_completeness(metrics: dict, settings: Settings) -> list[Anomaly]:
    out: list[Anomaly] = []
    c = metrics.get("completeness")
    x = metrics.get("contamination")
    if c is not None and c < settings.thresholds.min_completeness_soft:
        out.append(Anomaly(id="low_completeness", stage="completeness", severity=Severity.warning,
                           message=f"Estimated completeness is {c:.1f}%",
                           possible_explanations=["fragmented assembly", "insufficient coverage", "unusual lineage", "wrong bin/genome"]))
    if x is not None and x > settings.thresholds.max_contamination_hard:
        out.append(Anomaly(id="high_contamination_hard", stage="completeness", severity=Severity.hard,
                           message=f"Estimated contamination is {x:.1f}%",
                           possible_explanations=["mixed culture", "cross-sample contamination", "assembly/binning error"]))
    elif x is not None and x > settings.thresholds.max_contamination_soft:
        out.append(Anomaly(id="high_contamination", stage="completeness", severity=Severity.warning,
                           message=f"Estimated contamination is {x:.1f}%",
                           possible_explanations=["mixed culture", "cross-sample contamination", "duplicated marker regions"]))
    return out


def count_gff_features(path: str) -> dict:
    cds = 0
    genes = 0
    rrna = 0
    trna = 0
    with open(path) as fh:
        for line in fh:
            if not line or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            typ = parts[2].lower()
            if typ == "cds":
                cds += 1
            elif typ == "gene":
                genes += 1
            elif typ == "rrna":
                rrna += 1
            elif typ == "trna":
                trna += 1
    return {"cds": cds, "genes": genes, "rrna": rrna, "trna": trna}


def validate_annotation(annotation_metrics: dict, assembly_metrics: dict, settings: Settings) -> list[Anomaly]:
    out: list[Anomaly] = []
    total = assembly_metrics.get("total_bp")
    cds = annotation_metrics.get("cds") or annotation_metrics.get("genes")
    if total and cds:
        density = cds / (total / 1000)
        annotation_metrics["gene_density_per_kb"] = density
        if density < settings.thresholds.min_gene_density_per_kb_soft or density > settings.thresholds.max_gene_density_per_kb_soft:
            out.append(Anomaly(id="annotation_gene_density", stage="annotation", severity=Severity.warning,
                               message=f"Predicted coding density is unusual: {density:.2f} CDS/kb",
                               possible_explanations=["annotation failure", "fragmented or contaminated assembly", "non-bacterial input", "unusual biology"]))
    return out
