"""Prospective BixBench compatibility classifier for frozen Genome Skeptic V5.

Uses only answer-blind metadata. Does not inspect ideal answers, results,
hypotheses, distractors, or grader output. Does not add Genome Skeptic
scientific functionality.
"""
from __future__ import annotations

import json
from pathlib import Path

# Frozen V5 can: bacterial-isolate QC/assembly/mapping/annotation, gene/family
# homology+HMM, competitive family discrimination, locus multiplicity,
# architecture, contig taxonomy. It cannot run BixBench notebooks or
# arbitrary R/Python analyses.

UNSUPPORTED_METHOD = (
    "rna-seq", "rnaseq", "deseq", "enrichgo", "clusterprofiler", "gencode",
    "transcriptom", "single-cell", "single cell", "scrna", "seurat", "kallisto",
    "salmon quant", "star alignment",
    "proteomic", "metabolom", "mass spec",
    "imaging", "swarming", "circularity", "colony",
    "histolog", "cryo-em", "docking",
    "deseq2", "padj", "logfold", "volcano",
    "logistic regression", "ordinal logistic", "chi-square", "chisquare",
    "mann-whitney", "odds ratio", "spline",
    "phykit", "clipkit", "treeness", "parsimony informative",
    "eukaryota_odb10", "busco analysis",
    "gatk", "haplotypecaller", "trimmomatic", "bwa-mem",
    "covid-19", "vaccination", "camrelizumab",
    "fibroblast", "t cell", "neutrophil",
)

PARTIAL_METHOD = (
    "whole genome sequencing", "wgs", "snp analysis", "antimicrobial resistance",
    "mapping", "coverage depth", "trimmed reads", "variant",
    "phylogenetics", "evolutionary analysis", "single-copy ortholog",
)

SUPPORTED_METHOD = (
    "bacterial isolate", "prokaryotic genome assembl", "spades",
    "bakta", "prokka annotation", "checkm", "quast n50",
    "hmmsearch", "family hmm", "competitive family",
    "gene presence in this assembly", "target gene detection",
    "bacterial orthologue", "locus architecture", "contig taxonomy",
)


def _blob(task: dict) -> str:
    cats = task.get("categories") or []
    if isinstance(cats, str):
        cats = [cats]
    return " ".join(
        [
            str(task.get("question_id") or ""),
            str(task.get("question") or ""),
            " ".join(str(c) for c in cats),
            str(task.get("evaluation_mode") or ""),
        ]
    ).lower()


def classify_bixbench_task(task: dict) -> dict:
    blob = _blob(task)
    cats = task.get("categories") or []
    if isinstance(cats, str):
        cats = [cats]
    eval_mode = task.get("evaluation_mode")
    if any(tok in blob for tok in UNSUPPORTED_METHOD):
        status = "UNSUPPORTED"
        reason = (
            "Original task requires methods or data types frozen Genome Skeptic V5 "
            "does not implement (notebook analysis, RNA-seq, phylogenetics stats, "
            "variant calling, imaging, clinical regression, or similar)."
        )
    elif any(tok in blob for tok in SUPPORTED_METHOD) and not any(
        tok in blob for tok in UNSUPPORTED_METHOD
    ):
        status = "SUPPORTED"
        reason = (
            "Question is a bacterial isolate gene/genome measurement that frozen "
            "Genome Skeptic V5 already computes."
        )
    elif any(tok in blob for tok in PARTIAL_METHOD):
        status = "PARTIALLY_SUPPORTED"
        reason = (
            "Genomics-adjacent (WGS/mapping/AMR/phylogeny) but the original asked "
            "statistic is not an existing Genome Skeptic V5 output; supporting it "
            "would require adding tools or rewriting the task."
        )
    else:
        status = "UNSUPPORTED"
        reason = (
            "Task cannot be mapped onto frozen Genome Skeptic V5 bacterial "
            "isolate / gene-orthologue capabilities without adding scientific "
            "functionality or rewriting the question."
        )
    return {
        "question_id": task.get("question_id"),
        "capsule_uuid": task.get("capsule_uuid"),
        "short_id": task.get("short_id"),
        "categories": cats,
        "evaluation_mode": eval_mode,
        "dataset_folder": task.get("dataset_folder") or task.get("data_folder"),
        "compatibility": status,
        "compatibility_rationale": reason,
        "deterministic_verifier": eval_mode in {"str_verifier", "range_verifier"},
        "prompt_rewritten": False,
        "answers_inspected": False,
    }


def load_answerblind(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def select_supported(classified: list[dict], limit: int = 5) -> list[dict]:
    supported = [r for r in classified if r["compatibility"] == "SUPPORTED"]
    supported.sort(key=lambda r: (not r["deterministic_verifier"], str(r["question_id"])))
    return supported[:limit]
