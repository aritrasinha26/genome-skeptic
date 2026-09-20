#!/usr/bin/env python3
"""STEP 3C Cohort A: metadata-only RefSeq assembly selection.

Does not inspect gene/protein annotations, AMRFinder, PGAP symbols,
GFF/GBFF, or protein FASTA. Does not run Genome Skeptic. Does not
download genome FASTA.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation"
CACHE = ROOT / "external_validation" / "_cache_assembly_summary_bacteria.txt"
SUMMARY_URL = "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/assembly_summary.txt"

SEED = 20260918
V5_FREEZE = "0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b"
INV_HASH = "b82969ad6e4e3e5a134ea831a0370d32b19612f9440b71d6ad8fbd03a3467e85"
CONTRACT = "d224b8b829b3a46c03e42aae324062b7ff72c75d2b6906a0cab45618818f9cb9"
EXCL_HASH = "205d468d98090bca51099785407d8df004cb97f04603bd93f5521e63484ddf80"
INPUT_HASH = "6d99f26208175a5f7a77017d3d99461ed4c75d333930622059ed01c9b18d0978"
CREATED = "2026-09-18T22:40:00+00:00"

# A priori taxonomic strata. Chosen for phylogenetic spread, not target genes.
GENERA = [
    {"genus": "Campylobacter", "phylum": "Campylobacterota", "class": "Campylobacteria", "gram": "negative"},
    {"genus": "Neisseria", "phylum": "Pseudomonadota", "class": "Betaproteobacteria", "gram": "negative"},
    {"genus": "Acinetobacter", "phylum": "Pseudomonadota", "class": "Gammaproteobacteria", "gram": "negative"},
    {"genus": "Burkholderia", "phylum": "Pseudomonadota", "class": "Betaproteobacteria", "gram": "negative"},
    {"genus": "Bacteroides", "phylum": "Bacteroidota", "class": "Bacteroidia", "gram": "negative"},
    {"genus": "Chlamydia", "phylum": "Chlamydiota", "class": "Chlamydiia", "gram": "negative"},
    {"genus": "Listeria", "phylum": "Bacillota", "class": "Bacilli", "gram": "positive"},
    {"genus": "Enterococcus", "phylum": "Bacillota", "class": "Bacilli", "gram": "positive"},
    {"genus": "Corynebacterium", "phylum": "Actinomycetota", "class": "Actinomycetes", "gram": "positive"},
    {"genus": "Clostridioides", "phylum": "Bacillota", "class": "Clostridia", "gram": "positive"},
]

COMPLETE_LEVELS = {"Complete Genome", "Chromosome"}
DRAFT_LEVELS = {"Scaffold", "Contig"}
RELEASE_CUTOFFS = ["2025-01-01", "2024-01-01", "2023-01-01"]

EXCLUDED_TAXIDS = {
    511145,  # E. coli MG1655
    208964,  # P. aeruginosa PAO1
    85962,   # H. pylori 26695
    224308,  # B. subtilis 168
    160488,  # P. putida KT2440
    93061,   # S. aureus NCTC 8325
    99287,   # S. Typhimurium LT2
    243277,  # V. cholerae N16961
    83332,   # M. tuberculosis H37Rv
    243274,  # T. maritima MSB8
    224324,  # A. aeolicus VF5
}
EXCLUDED_NUC = {
    "NC_000853.1", "NC_000913.3", "NC_000915.1", "NC_000918.1", "NC_000962.3",
    "NC_000964.3", "NC_002505.1", "NC_002516.2", "NC_002947.4", "NC_003197.2",
    "NC_003277.2", "NC_007795.1", "U00096.3",
}
EXCLUDED_GCF = {
    "GCF_000005845.2",  # MG1655
    "GCF_000006765.1",  # PAO1
    "GCF_000008525.1",  # H. pylori 26695
    "GCF_000009045.1",  # B. subtilis 168
    "GCF_000007565.2",  # P. putida KT2440
    "GCF_000013425.1",  # S. aureus NCTC 8325
    "GCF_000006945.2",  # S. Typhimurium LT2
    "GCF_000006745.1",  # V. cholerae N16961
    "GCF_000195955.2",  # M. tuberculosis H37Rv
    "GCF_000008545.1",  # T. maritima MSB8
    "GCF_000008605.1",  # A. aeolicus VF5
}
EXCLUDED_ORGANISM_MARKERS = (
    "k-12 substr. mg1655",
    "substr. mg1655",
    "pseudomonas aeruginosa pao1",
    "helicobacter pylori 26695",
    "subtilis subsp. subtilis str. 168",
    "putida kt2440",
    "nctc 8325",
    "typhimurium str. lt2",
    "el tor str. n16961",
    "tuberculosis h37rv",
    "thermotoga maritima",
    "aquifex aeolicus",
)

# Fields that would leak annotation content if used for selection.
FORBIDDEN_FIELDS = {
    "annotation_provider", "annotation_name", "annotation_date",
    "total_gene_count", "protein_coding_gene_count", "non_coding_gene_count",
}


def download_summary() -> Path:
    if CACHE.exists() and CACHE.stat().st_size > 1_000_000:
        return CACHE
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        SUMMARY_URL,
        headers={"User-Agent": "GenomeSkeptic-external-validation/metadata-only"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp, CACHE.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    return CACHE


def parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw or raw in {"na", "NA"}:
        return None
    try:
        y, m, d = raw.split("/")[0].split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def genus_of(organism: str) -> str:
    parts = (organism or "").replace("[", "").replace("]", "").split()
    if not parts:
        return ""
    if parts[0].lower() == "candidatus" and len(parts) > 1:
        return parts[1]
    return parts[0]


def is_excluded(row: dict) -> tuple[bool, str]:
    acc = row.get("assembly_accession") or ""
    if acc in EXCLUDED_GCF or acc.split(".")[0] in {x.split(".")[0] for x in EXCLUDED_GCF}:
        return True, "excluded_GCF_provenance"
    taxid = int(row["taxid"]) if (row.get("taxid") or "").isdigit() else -1
    if taxid in EXCLUDED_TAXIDS:
        return True, "excluded_taxid_provenance"
    organism = (row.get("organism_name") or "").lower()
    if any(m in organism for m in EXCLUDED_ORGANISM_MARKERS):
        return True, "excluded_organism_provenance"
    blob = " ".join(str(v) for v in row.values())
    if any(n in blob for n in EXCLUDED_NUC):
        return True, "excluded_nucleotide_accession"
    return False, ""


def eligible(row: dict, genus: str, levels: set[str], cutoff: date) -> bool:
    acc = row.get("assembly_accession") or ""
    if not acc.startswith("GCF_"):
        return False
    if (row.get("version_status") or "") != "latest":
        return False
    excl = (row.get("excluded_from_refseq") or "").strip()
    if excl and excl.lower() not in {"na", "n/a"}:
        return False
    if (row.get("genome_rep") or "") != "Full":
        return False
    if (row.get("assembly_level") or "") not in levels:
        return False
    if genus_of(row.get("organism_name") or "") != genus:
        return False
    rel = parse_date(row.get("seq_rel_date") or "")
    if rel is None or rel < cutoff:
        return False
    blocked, _ = is_excluded(row)
    if blocked:
        return False
    return True


def load_rows(path: Path) -> list[dict]:
    wanted = {g["genus"] for g in GENERA}
    cols = None
    rows = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if ln.startswith("#assembly_accession") or ln.startswith("# assembly_accession"):
                cols = ln.lstrip("#").strip().split("\t")
                continue
            if ln.startswith("#") or not ln.strip():
                continue
            if cols is None:
                continue
            parts = ln.rstrip("\n").split("\t")
            if len(parts) < 12:
                continue
            rec = {cols[i]: parts[i] if i < len(parts) else "" for i in range(len(cols))}
            if genus_of(rec.get("organism_name") or "") not in wanted:
                continue
            rows.append(rec)
    if cols is None:
        raise RuntimeError("assembly_summary header not found")
    return rows


def shuffle_stable(items: list[dict], salt: str) -> list[dict]:
    rng = random.Random(f"{SEED}:{salt}")
    ordered = sorted(items, key=lambda r: r.get("assembly_accession") or "")
    keyed = [(rng.random(), r["assembly_accession"], r) for r in ordered]
    keyed.sort()
    return [r for _, _, r in keyed]


def pick_distinct_species(pool: list[dict], n: int, used_species: set[str]) -> list[dict]:
    picked = []
    leftover = []
    for row in pool:
        sp = row.get("species_taxid") or row.get("taxid") or row.get("assembly_accession")
        if sp in used_species:
            leftover.append(row)
            continue
        picked.append(row)
        used_species.add(sp)
        if len(picked) >= n:
            break
    if len(picked) < n:
        for row in leftover:
            picked.append(row)
            if len(picked) >= n:
                break
    return picked


def select(rows: list[dict]) -> tuple[list[dict], dict]:
    selected = []
    strata_report = []
    for spec in GENERA:
        genus = spec["genus"]
        complete = []
        draft = []
        cutoff_used = None
        for cutoff_s in RELEASE_CUTOFFS:
            used_species: set[str] = set()
            cutoff = parse_date(cutoff_s)
            complete_pool = [r for r in rows if eligible(r, genus, COMPLETE_LEVELS, cutoff)]
            draft_pool = [r for r in rows if eligible(r, genus, DRAFT_LEVELS, cutoff)]
            complete_pool = shuffle_stable(complete_pool, f"{genus}:complete:{cutoff_s}")
            draft_pool = shuffle_stable(draft_pool, f"{genus}:draft:{cutoff_s}")
            c = pick_distinct_species(complete_pool, 2, used_species)
            d = pick_distinct_species(draft_pool, 1, used_species)
            if len(c) == 2 and len(d) == 1:
                complete, draft = c, d
                cutoff_used = cutoff_s
                break
        if cutoff_used is None or len(complete) != 2 or len(draft) != 1:
            raise RuntimeError(f"insufficient metadata-only assemblies for genus {genus}")
        for row, level_stratum in [(complete[0], "complete_or_chromosome"), (complete[1], "complete_or_chromosome"), (draft[0], "scaffold_or_contig")]:
            blocked, why = is_excluded(row)
            rec = {
                "assembly_accession": row.get("assembly_accession"),
                "gbrs_paired_asm": row.get("gbrs_paired_asm"),
                "organism": row.get("organism_name"),
                "taxonomy_id": int(row["taxid"]) if (row.get("taxid") or "").isdigit() else None,
                "species_taxid": int(row["species_taxid"]) if (row.get("species_taxid") or "").isdigit() else None,
                "genus": genus,
                "phylum": spec["phylum"],
                "class": spec["class"],
                "gram": spec["gram"],
                "assembly_level": row.get("assembly_level"),
                "release_date": row.get("seq_rel_date"),
                "contig_count": int(row["contig_count"]) if (row.get("contig_count") or "").isdigit() else None,
                "n50": int(row["contig_n50"]) if (row.get("contig_n50") or "").isdigit() else None,
                "n50_note": "contig_n50 is not a column in the NCBI bacteria assembly_summary.txt used for metadata-only selection",
                "genome_size": int(row["genome_size"]) if (row.get("genome_size") or "").isdigit() else None,
                "bioproject": row.get("bioproject") or None,
                "biosample": row.get("biosample") or None,
                "refseq_category": row.get("refseq_category") or None,
                "asm_name": row.get("asm_name") or None,
                "sampling_stratum": f"{genus}|{level_stratum}",
                "assembly_quality_stratum": level_stratum,
                "release_cutoff_applied": cutoff_used,
                "reason_eligible": (
                    "RefSeq GCF latest Full bacterial assembly; not provenance-excluded; "
                    f"genus stratum {genus}; quality {level_stratum}; "
                    f"seq_rel_date {row.get('seq_rel_date')} >= {cutoff_used}; "
                    "selected by seeded shuffle among distinct species_taxid."
                ),
                "in_provenance_exclusions": False,
                "provenance_exclusion_check": "passed" if not blocked else why,
                "target_labels_inspected": False,
                "annotations_downloaded": False,
                "genome_fasta_downloaded": False,
            }
            if blocked:
                raise RuntimeError(f"selected excluded assembly {row.get('assembly_accession')}: {why}")
            selected.append(rec)
        strata_report.append({
            "genus": genus,
            "release_cutoff_applied": cutoff_used,
            "n_selected": 3,
            "complete_or_chromosome": 2,
            "scaffold_or_contig": 1,
        })
    return selected, {"per_genus": strata_report}


def main() -> None:
    print("download assembly_summary metadata only", flush=True)
    path = download_summary()
    print("parse", path, "bytes", path.stat().st_size, flush=True)
    rows = load_rows(path)
    print("n_rows", len(rows), flush=True)
    selected, strata = select(rows)
    genera = sorted({r["genus"] for r in selected})
    levels = {}
    for r in selected:
        levels[r["assembly_level"]] = levels.get(r["assembly_level"], 0) + 1
    quality = {}
    for r in selected:
        quality[r["assembly_quality_stratum"]] = quality.get(r["assembly_quality_stratum"], 0) + 1
    grams = {}
    for r in selected:
        grams[r["gram"]] = grams.get(r["gram"], 0) + 1
    phyla = sorted({r["phylum"] for r in selected})
    manifest = {
        "kind": "cohort_A_naturalistic_manifest",
        "created_utc": CREATED,
        "model": "qwen3:4b",
        "genome_skeptic_v5_freeze_hash": V5_FREEZE,
        "target_inventory_sha256": INV_HASH,
        "scoring_contract_sha256": CONTRACT,
        "provenance_exclusion_sha256": EXCL_HASH,
        "input_policy_sha256": INPUT_HASH,
        "scientific_logic_modified": False,
        "scoring_contract_modified": False,
        "target_definitions_modified": False,
        "input_policy_modified": False,
        "provenance_exclusions_modified": False,
        "genome_skeptic_executed": False,
        "target_labels_inspected": False,
        "gene_annotations_inspected": False,
        "protein_annotations_inspected": False,
        "amrfinder_calls_inspected": False,
        "pgap_gene_symbols_inspected": False,
        "gff_gbff_inspected": False,
        "protein_fasta_inspected": False,
        "hmm_or_homology_searches_run": False,
        "genome_fasta_downloaded": False,
        "selection_metadata_only": True,
        "metadata_source": {
            "url": SUMMARY_URL,
            "note": "NCBI RefSeq bacteria assembly_summary.txt. Gene-count and annotation-provider columns were not used.",
            "forbidden_fields_not_used_for_selection": sorted(FORBIDDEN_FIELDS),
        },
        "sampling": {
            "method": "deterministic_stratified_genus_then_seeded_shuffle_of_distinct_species",
            "seed": SEED,
            "n_genera_target": 10,
            "n_assemblies_per_genus": 3,
            "n_complete_or_chromosome_per_genus": 2,
            "n_scaffold_or_contig_per_genus": 1,
            "release_date_preference": "prefer seq_rel_date >= 2025-01-01, else 2024-01-01, else 2023-01-01",
            "near_identical_strain_rule": "at most one assembly per species_taxid within a genus unless a stratum would otherwise be empty",
            "genera_chosen_a_priori_not_by_target_presence": True,
            "per_genus": strata["per_genus"],
        },
        "n_assemblies": len(selected),
        "n_genera": len(genera),
        "genera": genera,
        "taxonomic_distribution": {
            "genera": genera,
            "phyla": phyla,
            "gram": grams,
            "by_genus": {
                g: [r["assembly_accession"] for r in selected if r["genus"] == g]
                for g in genera
            },
        },
        "assembly_level_distribution": levels,
        "assembly_quality_stratum_distribution": quality,
        "n_provenance_excluded_selected": 0,
        "assemblies": selected,
        "label_freeze_sequence_predefined": [
            "Freeze cohort manifest",
            "Download genome FASTA only",
            "Sanitize FASTA headers if annotation-bearing",
            "Run frozen Genome Skeptic V5",
            "Save predictions, evidence IDs, confidence, classifications",
            "Compute SHA256 of prediction output",
            "Mark predictions LOCKED",
            "Only after prediction lock retrieve/reveal external annotations and reference labels",
            "Score according to the already-frozen scoring contract",
            "Preserve every disagreement; do not rerun a genome after its external label is known",
        ],
    }
    dest = OUT / "cohort_A_naturalistic_manifest.json"
    dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    print(json.dumps({
        "n": len(selected),
        "genera": genera,
        "levels": levels,
        "quality": quality,
        "sha256": digest,
        "seed": SEED,
        "accessions": [r["assembly_accession"] for r in selected],
    }, indent=2))


if __name__ == "__main__":
    main()
