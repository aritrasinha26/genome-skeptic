# Genome assembly retrieval

Assemblies are **not** bundled. Reconstruct from NCBI RefSeq accessions and verify SHA256.

Primary table: `accessions_and_checksums.csv`.

## Example (NCBI Datasets CLI)

```bash
datasets download genome accession GCF_047713185.1 --include genome
```

After download, compute SHA256 of the `.fna` / genomic FASTA and compare to `assembly_sha256`.
Do not proceed with a model-dependent re-run unless every accession matches.
