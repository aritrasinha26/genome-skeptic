#!/usr/bin/env python3
"""D8 mini external cohort: metadata-only 8-case selection + FASTA lock.

Separate from D20. Does not write into external_validation_agentic_d20/.
Does not inspect gene annotations or external truth.
Does not modify frozen scientific source.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from select_and_download_d20 import (  # noqa: E402
    COMPLETE_LEVELS,
    DRAFT_LEVELS,
    CACHE,
    COHORT_A_PATH,
    COHORT_C_PATH,
    eligible_row,
    ensure_lineage,
    ensure_summary,
    fetch_genome_fasta,
    load_accessions,
    load_exclusion_accessions,
    load_genera_from_manifest,
    load_lineage,
    load_rows,
    quality_bucket,
    sanitize_fasta,
    sha256_file,
    taxonomy_for,
    verify_freeze,
)

OUT = ROOT / "external_validation_agentic_d8"
D20_POOL = ROOT / "external_validation_agentic_d20" / "candidate_pool_manifest.json"
SEED = "20260920"
TARGETS = [
    "rpoB_RNAP_beta",
    "tuf_EF_Tu",
    "lacZ_beta_galactosidase",
    "tetA_tetracycline_efflux",
]
N_COMPLETE = 1
N_DRAFT = 1
EXPECTED_D20_POOL = "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c"
EXPECTED_DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"


def sampling_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"D8_MINI|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def execution_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"D8_EXECUTION|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def species_key(tax: dict) -> str:
    if tax.get("species_taxid"):
        return f"taxid:{tax['species_taxid']}"
    return f"name:{(tax.get('species') or '').lower()}"


def main() -> None:
    freeze = verify_freeze()
    print("FREEZE_OK", freeze["manifest_sha256"], flush=True)
    d20_sha = sha256_file(D20_POOL)
    if d20_sha != EXPECTED_D20_POOL:
        raise SystemExit(f"D20 pool hash mismatch (read-only check): {d20_sha}")
    d20 = json.loads(D20_POOL.read_text(encoding="utf-8"))
    d20_acc = {c["assembly_accession"] for c in d20["candidates"]}
    d20_acc |= {a.split(".")[0] for a in list(d20_acc)}
    d20_genera = {c.get("genus") for c in d20["candidates"] if c.get("genus")}

    OUT.mkdir(parents=True, exist_ok=True)
    orig_dir = OUT / "inputs" / "original"
    solver_dir = OUT / "inputs" / "solver"
    orig_dir.mkdir(parents=True, exist_ok=True)
    solver_dir.mkdir(parents=True, exist_ok=True)

    cohort_a_acc = load_accessions(COHORT_A_PATH)
    cohort_c_acc = load_accessions(COHORT_C_PATH)
    blocked_acc = set(cohort_a_acc) | set(cohort_c_acc) | d20_acc
    prior_genera = load_genera_from_manifest(COHORT_A_PATH) | load_genera_from_manifest(COHORT_C_PATH) | d20_genera
    excl_acc = load_exclusion_accessions()

    summary = ensure_summary()
    lineage = load_lineage(ensure_lineage())
    rows = [r for r in load_rows(summary) if eligible_row(r, blocked_acc, excl_acc)]
    print(f"eligible_metadata_rows {len(rows)}", flush=True)
    annotated = []
    for row in rows:
        tax = taxonomy_for(row, lineage)
        if tax["genus"] and tax["species"]:
            annotated.append((row, tax))

    used_acc: set[str] = set()
    used_species: set[str] = set()
    used_genera: set[str] = set()
    failures: list[dict] = []
    selected: list[dict] = []

    def try_download(row: dict, tax: dict, target: str) -> dict | None:
        acc = row["assembly_accession"]
        orig_path = orig_dir / f"{acc}.fna"
        solver_path = solver_dir / f"{acc}.fna"
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            if orig_path.exists() and orig_path.stat().st_size > 1000:
                text = orig_path.read_text(encoding="utf-8", errors="replace")
                source = "reused_local_original"
            else:
                data, source = fetch_genome_fasta(acc, row.get("ftp_path") or "")
                text = data.decode("utf-8", errors="replace")
                orig_path.write_text(text, encoding="utf-8")
            sanitized = sanitize_fasta(text)
            if sanitized.count(">") < 1:
                raise RuntimeError("sanitized fasta empty")
            solver_path.write_text(sanitized, encoding="utf-8")
        except Exception as exc:
            failures.append({"assembly_accession": acc, "target": target, "reason": f"{type(exc).__name__}: {exc}", "sampling_hash": sampling_hash(target, acc)})
            print(f"FAIL {acc} {target} {exc}", flush=True)
            return None
        rec = {
            "assembly_accession": acc,
            "organism": row.get("organism_name"),
            "genus": tax["genus"],
            "species": tax["species"],
            "taxonomy_id": tax["taxonomy_id"],
            "species_taxid": tax["species_taxid"],
            "phylum": tax["phylum"],
            "class": tax["class"],
            "order": tax["order"],
            "family": tax["family"],
            "target": target,
            "release_date": row.get("seq_rel_date"),
            "assembly_level": row.get("assembly_level"),
            "assembly_quality": quality_bucket(row.get("assembly_level") or ""),
            "refseq_status": row.get("version_status"),
            "genome_size": int(row["genome_size"]) if (row.get("genome_size") or "").isdigit() else None,
            "contig_count": int(row["contig_count"]) if (row.get("contig_count") or "").isdigit() else None,
            "ftp_path": row.get("ftp_path") or None,
            "fasta_source": source,
            "original_fasta": str(orig_path.relative_to(ROOT)).replace("\\", "/"),
            "original_fasta_bytes": orig_path.stat().st_size,
            "original_fasta_sha256": sha256_file(orig_path),
            "solver_fasta": str(solver_path.relative_to(ROOT)).replace("\\", "/"),
            "solver_fasta_bytes": solver_path.stat().st_size,
            "fasta_sha256": sha256_file(solver_path),
            "download_timestamp_utc": stamp,
            "headers_sanitized": True,
            "sanitization_rule": "opaque contig_N identifiers; product/gene/organism-function text stripped",
            "sampling_hash": sampling_hash(target, acc),
            "execution_hash": execution_hash(target, acc),
            "gff_downloaded": False,
            "gbff_downloaded": False,
            "protein_fasta_downloaded": False,
            "amrfinder_downloaded": False,
            "annotations_inspected": False,
            "external_labels_opened": False,
            "avoided_prior_cohort_genus": tax["genus"] not in prior_genera,
            "in_d20_pool": False,
        }
        print(f"OK {acc} {target} {tax['genus']} {row.get('assembly_level')}", flush=True)
        time.sleep(0.2)
        return rec

    def fill(target: str, levels: set[str], n: int) -> list[dict]:
        ranked = sorted(
            ((row, tax) for row, tax in annotated if (row.get("assembly_level") or "") in levels),
            key=lambda rt: (sampling_hash(target, rt[0]["assembly_accession"]), rt[0]["assembly_accession"]),
        )
        picked: list[dict] = []

        def accept(row: dict, tax: dict, prefer_new_genus: bool, avoid_prior: bool) -> bool:
            acc = row["assembly_accession"]
            if acc in used_acc or acc.split(".")[0] in used_acc:
                return False
            if species_key(tax) in used_species:
                return False
            if prefer_new_genus and tax["genus"] in used_genera:
                return False
            if avoid_prior and tax["genus"] in prior_genera:
                return False
            return True

        def drain(prefer_new_genus: bool, avoid_prior: bool) -> None:
            for row, tax in ranked:
                if len(picked) >= n:
                    return
                if not accept(row, tax, prefer_new_genus, avoid_prior):
                    continue
                rec = try_download(row, tax, target)
                if rec is None:
                    used_acc.add(row["assembly_accession"])
                    continue
                used_acc.add(rec["assembly_accession"])
                used_acc.add(rec["assembly_accession"].split(".")[0])
                used_species.add(species_key(tax))
                used_genera.add(tax["genus"])
                picked.append(rec)

        drain(True, True)
        drain(True, False)
        drain(False, False)
        if len(picked) < n:
            raise SystemExit(f"could not fill {target} {sorted(levels)} need={n} got={len(picked)}")
        return picked

    for target in TARGETS:
        print(f"SELECT {target}", flush=True)
        selected.extend(fill(target, COMPLETE_LEVELS, N_COMPLETE))
        selected.extend(fill(target, DRAFT_LEVELS, N_DRAFT))

    selected.sort(key=lambda r: (r["execution_hash"], r["assembly_accession"]))
    for i, rec in enumerate(selected, start=1):
        rec["execution_position"] = i

    payload = {
        "kind": "D8_MANIFEST",
        "name": "D8_MINI_EXTERNAL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V2_D20",
        "agentic_freeze_manifest_sha256": freeze["manifest_sha256"],
        "model": "qwen3:4b",
        "model_digest": EXPECTED_DIGEST,
        "seed": SEED,
        "sampling_hash_formula": 'SHA256("D8_MINI|20260920|<target>|<assembly_accession>")',
        "execution_hash_formula": 'SHA256("D8_EXECUTION|20260920|<target>|<assembly_accession>")',
        "release_cutoff": "2025-01-01",
        "n_cases": len(selected),
        "target_counts": dict(defaultdict(int, {t: sum(1 for r in selected if r["target"] == t) for t in TARGETS})),
        "assembly_quality_counts": {
            "complete_or_chromosome": sum(1 for r in selected if r["assembly_quality"] == "complete_or_chromosome"),
            "scaffold_or_contig": sum(1 for r in selected if r["assembly_quality"] == "scaffold_or_contig"),
        },
        "n_unique_genomes": len({r["assembly_accession"] for r in selected}),
        "n_unique_species": len({r["species"] for r in selected}),
        "n_unique_genera": len({r["genus"] for r in selected}),
        "d20_pool_excluded": True,
        "d20_candidate_pool_sha256": d20_sha,
        "d20_directory_modified": False,
        "external_labels_opened": False,
        "gene_content_used_for_selection": False,
        "challenge_enriched": False,
        "v5_used_for_selection": False,
        "ambiguity_score_used": False,
        "download_failures_skipped": failures,
        "cases": selected,
    }
    json_path = OUT / "D8_MANIFEST.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    csv_path = OUT / "D8_MANIFEST.csv"
    fields = [
        "execution_position", "assembly_accession", "organism", "genus", "species", "target",
        "release_date", "assembly_level", "assembly_quality", "fasta_sha256", "sampling_hash",
        "execution_hash", "solver_fasta",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for rec in selected:
            w.writerow(rec)
    for path in (json_path, csv_path):
        digest = sha256_file(path)
        (OUT / f"{path.name}.sha256.json").write_text(
            json.dumps({"file": path.name, "sha256": digest, "hashed_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(path.name, digest, flush=True)
    print("N", len(selected), "GENERA", payload["n_unique_genera"], "SPECIES", payload["n_unique_species"], flush=True)


if __name__ == "__main__":
    main()
