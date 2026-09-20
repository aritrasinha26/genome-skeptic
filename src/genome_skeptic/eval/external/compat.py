"""Task compatibility for external genomics-agent benchmarks.

Unsupported domains are not rewritten into easier Genome Skeptic tasks.
"""
from __future__ import annotations

UNSUPPORTED_TOKENS = (
    "rna-seq", "rnaseq", "single-cell", "single cell", "scrna", "transcriptom",
    "deseq", "seurat", "star alignment", "kallisto", "salmon quant",
    "proteomic", "metabolom", "imaging", "histolog", "cryo-em",
)
PARTIAL_TOKENS = (
    "metagenom", "variant call", "vcf", "gatk", "giab", "exome", "human genome",
    "phylogen", "iq-tree", "multiple sequence alignment",
)
SUPPORTED_TOKENS = (
    "comparative genom", "bacterial", "prokaryot", "gene presence", "gene detection",
    "homology", "blastn", "ortholog", "genome assembl", "isolate", "fasta gene",
    "antimicrobial", "amr gene", "plasmid gene",
)


def classify_task(name: str, prompt: str = "", tags: list[str] | None = None) -> dict:
    blob = " ".join([name or "", prompt or "", " ".join(tags or [])]).lower()
    if any(tok in blob for tok in UNSUPPORTED_TOKENS):
        status = "unsupported"
        reason = "outside Genome Skeptic bacterial isolate / gene-orthologue scope"
    elif any(tok in blob for tok in SUPPORTED_TOKENS):
        status = "supported"
        reason = "bacterial/genome-analysis gene or homology task"
    elif any(tok in blob for tok in PARTIAL_TOKENS):
        status = "partially_supported"
        reason = "genomics-adjacent but not Genome Skeptic's gene-orthologue claim engine"
    else:
        status = "unsupported"
        reason = "task domain could not be mapped onto Genome Skeptic without rewriting the prompt"
    return {
        "task": name,
        "compatibility": status,
        "reason": reason,
        "scored_as_genome_skeptic": status == "supported",
        "prompt_rewritten": False,
    }
