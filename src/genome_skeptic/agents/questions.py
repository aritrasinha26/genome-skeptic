ADVERSARIAL_QUESTIONS: dict[str, list[str]] = {
    "qc_clean": [
        "Could apparent quality issues come from chemistry, barcode mix-ups, or the wrong files rather than true sample quality?",
    ],
    "assembly_qc": [
        "Could genome-size and contig-count statistics be explained by contamination or mixed strains rather than a single isolate?",
    ],
    "mapping": [
        "Could a high mapping rate still hide unsupported contigs, collapsed repeats, or the wrong read set?",
    ],
    "completeness": [
        "Could completeness or contamination estimates be misleading for an unusual lineage or a mixed sample?",
    ],
    "annotation": [
        "Could gene-density look normal while many genes are truncated at contig edges?",
    ],
    "target_gene": [
        "Could a diverged homolog be missed by nucleotide search but still be present?",
        "Could the gene be truncated at a contig edge or split across contigs?",
        "If the gene appears detected, could the hit be a paralogue, a short domain, or a contaminant contig?",
        "Are catalytic residues, protein length, and neighborhood consistent with the intended gene?",
        "Does local gene order, orientation, and reciprocal-best-hit orthology agree with a trusted reference locus?",
        "If mapping exists, do clipped or mate-unmapped reads actually support a contig-edge truncation?",
        "Was contig taxonomy measured by a classifier, or is it being inferred from a reference label?",
        "Does the evidence only support 'not detected in this assembly', rather than 'absent from the organism'?",
        "Does 'supported' get treated as certainty even though optional tests remain?",
    ],
}
