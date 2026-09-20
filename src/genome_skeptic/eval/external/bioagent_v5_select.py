"""Prospective BioAgent Bench compatibility for frozen Genome Skeptic V5.

Inspects solver-visible metadata only. Does not download results, read
solution scripts, or score tasks. Tool presence alone is not support.
"""
from __future__ import annotations

from typing import Any

# Frozen V5 already performs and interprets: bacterial-isolate read QC (fastp),
# assembly (SPAdes), mapping, completeness, annotation, target-gene/family
# homology+HMM, competitive family discrimination, locus multiplicity,
# architecture, isolate contig taxonomy / contamination, mapping breaks,
# synteny and reciprocal hits against a reference for a nominated target.
# It does not: DESeq2, scRNA-seq, human germline calling, COG co-evolution
# clustering, experimental-evolution SNP calling, OTU community tables,
# transcript quantification, or viral metagenome species tables.

CLASSIFICATIONS: dict[str, dict[str, str]] = {
    "alzheimer-mouse": {
        "compatibility": "UNSUPPORTED",
        "rationale": "Requires mouse bulk-RNA differential expression and KEGG pathway comparison. Frozen V5 has no DE/pathway registered analysis.",
    },
    "comparative-genomics": {
        "compatibility": "PARTIALLY_SUPPORTED",
        "rationale": "Bacterial FASTA/GFF and gene-family/orthology are in V5 scope, but the required COG co-evolution clustering with KEGG-KO consensus CSV is not a V5 action or claim.",
    },
    "cystic-fibrosis": {
        "compatibility": "UNSUPPORTED",
        "rationale": "Human Mendelian variant identification with ClinVar annotation. Frozen V5 does not call or interpret human germline variants.",
    },
    "deseq": {
        "compatibility": "UNSUPPORTED",
        "rationale": "RNA-seq differential expression (DESeq2) with log2FoldChange/pvalue/padj. Expression analysis is absent from frozen V5.",
    },
    "evolution": {
        "compatibility": "PARTIALLY_SUPPORTED",
        "rationale": "E. coli WGS/mapping/annotation overlap V5, but the required shared-line SNP/impact table is not produced by any registered V5 action.",
    },
    "giab": {
        "compatibility": "UNSUPPORTED",
        "rationale": "Human exome germline variant calling vs GIAB. Human variant calling is absent from frozen V5.",
    },
    "metagenomics": {
        "compatibility": "PARTIALLY_SUPPORTED",
        "rationale": "Bacterial taxonomic reasoning exists for isolate contig contamination, but V5 cannot emit the required two-sample OTU relative-abundance table.",
    },
    "single-cell": {
        "compatibility": "UNSUPPORTED",
        "rationale": "Human scRNA-seq clustering, cell-type ID, and within-cluster DE. Single-cell analysis is absent from frozen V5.",
    },
    "transcript-quant": {
        "compatibility": "UNSUPPORTED",
        "rationale": "RNA-seq transcript quantification to exact simulated counts. Transcript expression is absent from frozen V5.",
    },
    "viral-metagenomics": {
        "compatibility": "UNSUPPORTED",
        "rationale": "Fecal viral contig assembly and viral species table. Frozen V5 does not perform or interpret viral metagenome species identification.",
    },
}


def visible_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    downloads = raw.get("download_urls") or {}
    data_files = [row.get("filename") for row in (downloads.get("data") or []) if isinstance(row, dict)]
    reference_files = [row.get("filename") for row in (downloads.get("reference_data") or []) if isinstance(row, dict)]
    return {
        "task_id": raw.get("task_id"),
        "name": raw.get("name"),
        "description": raw.get("description"),
        "task_prompt": raw.get("task_prompt"),
        "input_artifact_filenames": data_files,
        "reference_artifact_filenames": reference_files,
        "results_inspected": False,
    }


def classify_bioagent_task(raw: dict[str, Any]) -> dict[str, Any]:
    visible = visible_metadata(raw)
    task_id = str(visible["task_id"])
    spec = CLASSIFICATIONS.get(task_id)
    if spec is None:
        compatibility = "UNSUPPORTED"
        rationale = "Task ID is not in the frozen V5 BioAgent capability map; not rewritten into a Genome Skeptic task."
    else:
        compatibility = spec["compatibility"]
        rationale = spec["rationale"]
    return {
        **visible,
        "compatibility": compatibility,
        "capability_rationale": rationale,
        "tool_availability_alone_not_sufficient": True,
        "answers_inspected": False,
        "solution_scripts_inspected": False,
        "results_downloaded": False,
        "executed": False,
        "scored": False,
    }
