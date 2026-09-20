#!/usr/bin/env python3
"""Cohort C metadata-only RefSeq assembly selection for Agentic V1 external validation.

Does not inspect gene/protein annotations, AMRFinder, PGAP symbols, GFF/GBFF,
protein FASTA, or target presence. Does not run Genome Skeptic. Does not
download genome FASTA. Does not modify Agentic V1 freeze files or Cohort A.
"""
from __future__ import annotations

import hashlib
import json
import random
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation_agentic"
CACHE_DIR = OUT / "_cache"
SUMMARY_CACHE = CACHE_DIR / "assembly_summary_bacteria.txt"
LINEAGE_CACHE = CACHE_DIR / "rankedlineage.dmp"
SUMMARY_URL = "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/assembly_summary.txt"
TAXDUMP_URL = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/new_taxdump.zip"
EXCL_PATH = ROOT / "external_validation" / "v5_reference_provenance_exclusions.json"
COHORT_A_PATH = ROOT / "external_validation" / "cohort_A_naturalistic_manifest.json"

SEED = 20260919
RELEASE_CUTOFF = date(2025, 1, 1)
N_COMPLETE = 7
N_DRAFT = 3
AGENTIC_FREEZE_ID = "GENOME_SKEPTIC_AGENTIC_V1"
AGENTIC_MANIFEST_SHA = "9ca874bb38efa073b2e0801f6f492e6bb1fdabd27ba2a225c70e559ba5bf8c54"
AGENTIC_SUMMARY_SHA = "e5cc95523e18c9472211bb89235ccb624bc6cbbbad0d0ba5f56fddb1e8f9b38e"
V5_FREEZE = "0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b"
UA = "GenomeSkeptic-external-validation/cohort-C-metadata-only"

COMPLETE_LEVELS = {"Complete Genome", "Chromosome"}
DRAFT_LEVELS = {"Scaffold", "Contig"}

COHORT_A_GENERA = {
    "Campylobacter",
    "Neisseria",
    "Acinetobacter",
    "Burkholderia",
    "Bacteroides",
    "Chlamydia",
    "Listeria",
    "Enterococcus",
    "Corynebacterium",
    "Clostridioides",
}

# Exact V5 development / calibration / held-out catalog genomes and family sources.
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
    "GCF_000005845.2",
    "GCF_000006765.1",
    "GCF_000008525.1",
    "GCF_000009045.1",
    "GCF_000007565.2",
    "GCF_000013425.1",
    "GCF_000006945.2",
    "GCF_000006745.1",
    "GCF_000195955.2",
    "GCF_000008545.1",
    "GCF_000008605.1",
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

FORBIDDEN_FIELDS = {
    "annotation_provider",
    "annotation_name",
    "annotation_date",
    "total_gene_count",
    "protein_coding_gene_count",
    "non_coding_gene_count",
}

ALLOWED_SELECTION_FIELDS = {
    "assembly_accession",
    "organism_name",
    "taxid",
    "species_taxid",
    "assembly_level",
    "seq_rel_date",
    "genome_size",
    "contig_count",
    "contig_n50",
    "scaffold_n50",
    "bioproject",
    "biosample",
    "version_status",
    "excluded_from_refseq",
    "genome_rep",
    "gbrs_paired_asm",
    "asm_name",
    "refseq_category",
    "ftp_path",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, min_bytes: int) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    req = Request(url, headers={"User-Agent": UA})
    print(f"download {url}", flush=True)
    with urlopen(req, timeout=600) as resp, tmp.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    tmp.replace(dest)
    return dest


def download_rankedlineage() -> Path:
    if LINEAGE_CACHE.exists() and LINEAGE_CACHE.stat().st_size > 1_000_000:
        return LINEAGE_CACHE
    zip_path = download(TAXDUMP_URL, CACHE_DIR / "new_taxdump.zip", 1_000_000)
    print("extract rankedlineage.dmp", flush=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        pick = next((n for n in names if n.endswith("rankedlineage.dmp") or n == "rankedlineage.dmp"), None)
        if pick is None:
            raise RuntimeError(f"rankedlineage.dmp missing from taxdump: {names[:20]}")
        data = zf.read(pick)
    LINEAGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LINEAGE_CACHE.write_bytes(data)
    return LINEAGE_CACHE


def load_lineage(path: Path) -> dict[int, dict]:
    """taxid -> {species, genus, family, order, class, phylum, kingdom, domain, tax_name}"""
    out: dict[int, dict] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            parts = [p.strip() for p in ln.rstrip("\n").split("|")]
            if len(parts) < 10:
                continue
            try:
                taxid = int(parts[0])
            except ValueError:
                continue
            out[taxid] = {
                "tax_name": parts[1],
                "species": parts[2],
                "genus": parts[3],
                "family": parts[4],
                "order": parts[5],
                "class": parts[6],
                "phylum": parts[7],
                "kingdom": parts[8],
                "domain": parts[9],
            }
    return out


def parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw or raw.lower() in {"na", "n/a"}:
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


def load_cohort_a_accessions() -> set[str]:
    payload = json.loads(COHORT_A_PATH.read_text(encoding="utf-8"))
    accs = set()
    for rec in payload.get("assemblies") or []:
        acc = rec.get("assembly_accession")
        if acc:
            accs.add(acc)
            accs.add(acc.split(".")[0])
    return accs


def load_exclusion_accessions() -> set[str]:
    payload = json.loads(EXCL_PATH.read_text(encoding="utf-8"))
    accs = set(EXCLUDED_GCF)
    for rec in payload.get("excluded_source_reference_genomes") or []:
        acc = rec.get("accession") or ""
        if acc:
            accs.add(acc)
        for extra in rec.get("extra_accessions") or []:
            accs.add(extra)
    for acc in payload.get("excluded_nucleotide_accessions") or []:
        accs.add(acc)
    return accs


def is_excluded(row: dict, cohort_a: set[str], excl_acc: set[str]) -> tuple[bool, str]:
    acc = row.get("assembly_accession") or ""
    stem = acc.split(".")[0]
    if acc in cohort_a or stem in cohort_a:
        return True, "cohort_A_accession"
    genus = genus_of(row.get("organism_name") or "")
    if genus in COHORT_A_GENERA:
        return True, "cohort_A_genus"
    if acc in excl_acc or stem in excl_acc or acc in EXCLUDED_GCF or stem in {x.split(".")[0] for x in EXCLUDED_GCF}:
        return True, "excluded_GCF_provenance"
    taxid = int(row["taxid"]) if (row.get("taxid") or "").isdigit() else -1
    if taxid in EXCLUDED_TAXIDS:
        return True, "excluded_taxid_provenance"
    organism = (row.get("organism_name") or "").lower()
    if any(m in organism for m in EXCLUDED_ORGANISM_MARKERS):
        return True, "excluded_organism_provenance"
    # Nucleotide accession check uses only identifier fields, not annotation columns.
    ident_blob = " ".join(
        str(row.get(k) or "")
        for k in ("assembly_accession", "gbrs_paired_asm", "asm_name", "organism_name", "ftp_path")
    )
    if any(n in ident_blob for n in EXCLUDED_NUC):
        return True, "excluded_nucleotide_accession"
    return False, ""


def eligible(row: dict, levels: set[str], cohort_a: set[str], excl_acc: set[str]) -> bool:
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
    rel = parse_date(row.get("seq_rel_date") or "")
    if rel is None or rel < RELEASE_CUTOFF:
        return False
    genus = genus_of(row.get("organism_name") or "")
    if not genus or genus.lower() in {"bacterium", "bacteria", "uncultured"}:
        return False
    blocked, _ = is_excluded(row, cohort_a, excl_acc)
    if blocked:
        return False
    return True


def load_rows(path: Path) -> list[dict]:
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
            rec = {cols[i]: parts[i] if i < len(parts) else "" for i in range(len(cols))}
            rows.append(rec)
    if cols is None:
        raise RuntimeError("assembly_summary header not found")
    return rows


def shuffle_stable(items: list, salt: str, key_fn) -> list:
    rng = random.Random(f"{SEED}:{salt}")
    ordered = sorted(items, key=lambda x: str(key_fn(x)))
    keyed = [(rng.random(), str(key_fn(x)), x) for x in ordered]
    keyed.sort()
    return [x for _, _, x in keyed]


def taxonomy_for(row: dict, lineage: dict[int, dict]) -> dict:
    taxid = int(row["taxid"]) if (row.get("taxid") or "").isdigit() else None
    spid = int(row["species_taxid"]) if (row.get("species_taxid") or "").isdigit() else None
    info = {}
    if taxid in lineage:
        info = lineage[taxid]
    elif spid in lineage:
        info = lineage[spid]
    genus = info.get("genus") or genus_of(row.get("organism_name") or "")
    phylum = info.get("phylum") or "Unknown"
    klass = info.get("class") or "Unknown"
    if not phylum:
        phylum = "Unknown"
    if not klass:
        klass = "Unknown"
    return {
        "taxonomy_id": taxid,
        "species_taxid": spid,
        "genus": genus,
        "phylum": phylum,
        "class": klass,
        "order": info.get("order") or None,
        "family": info.get("family") or None,
        "domain": info.get("domain") or None,
    }


def as_record(row: dict, tax: dict, stratum: str) -> dict:
    n50_raw = row.get("contig_n50") or row.get("scaffold_n50") or ""
    n50 = int(n50_raw) if str(n50_raw).isdigit() else None
    return {
        "assembly_accession": row.get("assembly_accession"),
        "gbrs_paired_asm": row.get("gbrs_paired_asm") or None,
        "organism": row.get("organism_name"),
        "taxonomy_id": tax["taxonomy_id"],
        "species_taxid": tax["species_taxid"],
        "genus": tax["genus"],
        "phylum": tax["phylum"],
        "class": tax["class"],
        "order": tax["order"],
        "family": tax["family"],
        "domain": tax["domain"],
        "assembly_level": row.get("assembly_level"),
        "release_date": row.get("seq_rel_date"),
        "contig_count": int(row["contig_count"]) if (row.get("contig_count") or "").isdigit() else None,
        "n50": n50,
        "n50_note": (
            "contig_n50/scaffold_n50 taken from assembly_summary if present; "
            "not used as a selection ranking key"
        ),
        "genome_size": int(row["genome_size"]) if (row.get("genome_size") or "").isdigit() else None,
        "bioproject": row.get("bioproject") or None,
        "biosample": row.get("biosample") or None,
        "refseq_category": row.get("refseq_category") or None,
        "asm_name": row.get("asm_name") or None,
        "sampling_stratum": f"{tax['genus']}|{stratum}",
        "assembly_quality_stratum": stratum,
        "release_cutoff_applied": "2025-01-01",
        "reason_eligible": (
            "RefSeq GCF latest Full bacterial assembly; not provenance-excluded; "
            "not Cohort A accession or genus; "
            f"quality {stratum}; seq_rel_date {row.get('seq_rel_date')} >= 2025-01-01; "
            "one genome per genus; selected by seeded phylum-greedy shuffle."
        ),
        "in_provenance_exclusions": False,
        "target_labels_inspected": False,
        "annotations_downloaded": False,
        "genome_fasta_downloaded": False,
        "gene_content_used_for_selection": False,
    }


def pick_one_per_genus(rows: list[dict], lineage: dict[int, dict], salt: str, stratum: str) -> dict[str, dict]:
    by_genus: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        tax = taxonomy_for(row, lineage)
        genus = tax["genus"]
        if not genus:
            continue
        by_genus[genus].append(row)
    chosen: dict[str, dict] = {}
    for genus, pool in by_genus.items():
        shuffled = shuffle_stable(pool, f"{salt}:{genus}", lambda r: r.get("assembly_accession") or "")
        used_species: set[str] = set()
        pick = None
        leftover = []
        for row in shuffled:
            sp = row.get("species_taxid") or row.get("taxid") or row.get("assembly_accession")
            if sp in used_species:
                leftover.append(row)
                continue
            pick = row
            break
        if pick is None and leftover:
            pick = leftover[0]
        if pick is None:
            continue
        tax = taxonomy_for(pick, lineage)
        tax["genus"] = genus
        chosen[genus] = as_record(pick, tax, stratum)
    return chosen


def pick_stratum(
    genus_map: dict[str, dict],
    n: int,
    salt: str,
    forbidden_genera: set[str],
    already_phyla: set[str],
) -> list[dict]:
    items = [(g, rec) for g, rec in genus_map.items() if g not in forbidden_genera]
    by_phylum: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for g, rec in items:
        by_phylum[rec["phylum"]].append((g, rec))
    phyla = shuffle_stable(list(by_phylum.keys()), f"{salt}:phyla", lambda p: p)
    selected: list[dict] = []
    used: set[str] = set()

    def take_from_phyla(phylum_list: list[str], skip_seen_phyla: bool) -> None:
        for p in phylum_list:
            if len(selected) >= n:
                return
            if skip_seen_phyla and p in already_phyla:
                continue
            gens = shuffle_stable(by_phylum[p], f"{salt}:genus:{p}", lambda x: x[0])
            for g, rec in gens:
                if g in used:
                    continue
                selected.append(rec)
                used.add(g)
                break

    take_from_phyla(phyla, skip_seen_phyla=True)
    take_from_phyla(phyla, skip_seen_phyla=False)
    if len(selected) < n:
        raise RuntimeError(f"insufficient genera for {salt}: got {len(selected)} need {n}")
    return selected[:n]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cohort_a = load_cohort_a_accessions()
    excl_acc = load_exclusion_accessions()
    print("download assembly_summary metadata only", flush=True)
    summary = download(SUMMARY_URL, SUMMARY_CACHE, 1_000_000)
    print("download rankedlineage taxonomy metadata only", flush=True)
    lineage_path = download_rankedlineage()
    print("parse", summary, "bytes", summary.stat().st_size, flush=True)
    rows = load_rows(summary)
    lineage = load_lineage(lineage_path)
    print("n_summary_rows", len(rows), "n_lineage", len(lineage), flush=True)

    complete_rows = [r for r in rows if eligible(r, COMPLETE_LEVELS, cohort_a, excl_acc)]
    draft_rows = [r for r in rows if eligible(r, DRAFT_LEVELS, cohort_a, excl_acc)]
    print("n_eligible_complete", len(complete_rows), "n_eligible_draft", len(draft_rows), flush=True)

    complete_map = pick_one_per_genus(complete_rows, lineage, "complete", "complete_or_chromosome")
    draft_map = pick_one_per_genus(draft_rows, lineage, "draft", "scaffold_or_contig")
    print("n_complete_genera", len(complete_map), "n_draft_genera", len(draft_map), flush=True)

    complete_sel = pick_stratum(complete_map, N_COMPLETE, "select_complete", set(), set())
    used_genera = {r["genus"] for r in complete_sel}
    used_phyla = {r["phylum"] for r in complete_sel}
    draft_sel = pick_stratum(draft_map, N_DRAFT, "select_draft", used_genera, used_phyla)
    selected = complete_sel + draft_sel
    selected = sorted(selected, key=lambda r: (r["assembly_quality_stratum"], r["genus"], r["assembly_accession"]))

    genera = sorted({r["genus"] for r in selected})
    phyla = sorted({r["phylum"] for r in selected})
    levels: dict[str, int] = {}
    quality: dict[str, int] = {}
    for r in selected:
        levels[r["assembly_level"]] = levels.get(r["assembly_level"], 0) + 1
        quality[r["assembly_quality_stratum"]] = quality.get(r["assembly_quality_stratum"], 0) + 1

    if len(selected) != 10:
        raise RuntimeError(f"expected 10 assemblies, got {len(selected)}")
    if len(genera) != 10:
        raise RuntimeError(f"expected 10 genera, got {genera}")
    if quality.get("complete_or_chromosome") != 7 or quality.get("scaffold_or_contig") != 3:
        raise RuntimeError(f"quality stratum mismatch: {quality}")
    if len(phyla) < 5:
        print("WARNING: fewer than 5 phyla feasible after exclusions", phyla, flush=True)

    manifest = {
        "kind": "cohort_C_manifest",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": AGENTIC_FREEZE_ID,
        "agentic_freeze_manifest_sha256": AGENTIC_MANIFEST_SHA,
        "agentic_freeze_summary_sha256": AGENTIC_SUMMARY_SHA,
        "genome_skeptic_v5_freeze_hash": V5_FREEZE,
        "model": "qwen3:4b",
        "model_digest": "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
        "scientific_logic_modified": False,
        "agentic_freeze_modified": False,
        "cohort_A_modified": False,
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
        "independent_of_v5_development": True,
        "independent_of_cohort_A": True,
        "gene_content_used_for_selection": False,
        "metadata_source": {
            "assembly_summary_url": SUMMARY_URL,
            "taxonomy_url": TAXDUMP_URL,
            "taxonomy_file": "rankedlineage.dmp",
            "note": (
                "NCBI RefSeq bacteria assembly_summary.txt plus NCBI rankedlineage.dmp. "
                "Gene-count and annotation-provider columns were not used for eligibility or ranking. "
                "N50 was recorded if present and was not used as a ranking key."
            ),
            "forbidden_fields_not_used_for_selection": sorted(FORBIDDEN_FIELDS),
            "allowed_selection_fields": sorted(ALLOWED_SELECTION_FIELDS),
        },
        "sampling": {
            "method": (
                "deterministic_phylum_greedy_one_genome_per_genus_"
                "seeded_shuffle_of_eligible_2025_refseq_gcf"
            ),
            "seed": SEED,
            "n_genera": 10,
            "n_assemblies": 10,
            "n_complete_or_chromosome": N_COMPLETE,
            "n_scaffold_or_contig": N_DRAFT,
            "release_cutoff": "2025-01-01",
            "one_genome_per_genus": True,
            "near_identical_strain_rule": "at most one assembly per species_taxid within a genus",
            "genera_not_chosen_by_target_presence": True,
            "phylum_diversity_target": "at least 5 bacterial phyla if feasible",
            "excluded_cohort_A_genera": sorted(COHORT_A_GENERA),
        },
        "targets_locked": [
            "rpoB_RNAP_beta",
            "tuf_EF_Tu",
            "lacZ_beta_galactosidase",
            "tetA_tetracycline_efflux",
        ],
        "n_assemblies": len(selected),
        "n_genera": len(genera),
        "n_biological_cases": 40,
        "genera": genera,
        "taxonomic_distribution": {
            "genera": genera,
            "phyla": phyla,
            "n_phyla": len(phyla),
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
            "Freeze cohort C manifest and hash it",
            "Download genomic nucleotide FASTA only",
            "Sanitize FASTA headers if annotation-bearing",
            "Hash input manifest",
            "Run Agentic V1, deterministic V5, and frozen conventional baseline",
            "Lock predictions and execution manifest",
            "STOP before opening external labels or scoring",
        ],
    }
    dest = OUT / "cohort_C_manifest.json"
    dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = sha256_file(dest)
    sidecar = OUT / "cohort_C_manifest.sha256.json"
    sidecar.write_text(
        json.dumps(
            {
                "file": "cohort_C_manifest.json",
                "sha256": digest,
                "hashed_utc": datetime.now(timezone.utc).isoformat(),
                "hashed_before_genome_analysis": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "n": len(selected),
                "genera": genera,
                "phyla": phyla,
                "levels": levels,
                "quality": quality,
                "sha256": digest,
                "seed": SEED,
                "accessions": [
                    {"accession": r["assembly_accession"], "genus": r["genus"], "phylum": r["phylum"], "level": r["assembly_level"]}
                    for r in selected
                ],
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
