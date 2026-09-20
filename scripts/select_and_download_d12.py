#!/usr/bin/env python3
"""V3_D12_EXTERNAL: metadata-only 24-genome candidate pool + FASTA lock.

6 genomes per target (prefer 4 complete/chromosome, 2 scaffold/contig).
Excludes D8, D20 candidate pool, prior external/development cohorts, frozen
reference/source genomes, and catalog/capability source genomes.

Does not inspect gene annotations or truth. Does not write into D20.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from d12_common import (  # noqa: E402
    CURRENT_LACZ_LIMITATION,
    EXPECTED_DIGEST,
    FREEZE_ID,
    N_POOL_COMPLETE,
    N_POOL_DRAFT,
    OUT,
    SEED,
    TARGETS,
    assert_d20_untouched,
    blocked_accessions_and_genera,
    pool_sampling_hash,
    sha256_file,
    verify_v3_freeze,
    write_sha256_sidecar,
)
from select_and_download_d20 import (  # noqa: E402
    CACHE,
    COMPLETE_LEVELS,
    DRAFT_LEVELS,
    eligible_row,
    ensure_lineage,
    ensure_summary,
    fetch_genome_fasta,
    load_lineage,
    load_rows,
    quality_bucket,
    sanitize_fasta,
    taxonomy_for,
)


def species_key(tax: dict) -> str:
    if tax.get("species_taxid"):
        return f"taxid:{tax['species_taxid']}"
    return f"name:{(tax.get('species') or '').lower()}"


def main() -> None:
    freeze = verify_v3_freeze()
    print("V3_FREEZE_OK", freeze["manifest_sha256"], flush=True)
    d20_sha = assert_d20_untouched("pool_construction_start")
    OUT.mkdir(parents=True, exist_ok=True)
    orig_dir = OUT / "inputs" / "original"
    solver_dir = OUT / "inputs" / "solver"
    orig_dir.mkdir(parents=True, exist_ok=True)
    solver_dir.mkdir(parents=True, exist_ok=True)

    blocked_acc, prior_genera, exclusion_note = blocked_accessions_and_genera()
    excl_acc = blocked_acc
    print(f"blocked_accessions {len(blocked_acc)} prior_genera {len(prior_genera)}", flush=True)

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
            failures.append(
                {
                    "assembly_accession": acc,
                    "target": target,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "sampling_hash": pool_sampling_hash(target, acc),
                }
            )
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
            "sampling_hash": pool_sampling_hash(target, acc),
            "gff_downloaded": False,
            "gbff_downloaded": False,
            "protein_fasta_downloaded": False,
            "amrfinder_downloaded": False,
            "annotations_inspected": False,
            "external_labels_opened": False,
            "avoided_prior_cohort_genus": tax["genus"] not in prior_genera,
            "in_d20_pool": False,
            "in_d8": False,
        }
        print(f"OK {acc} {target} {tax['genus']} {row.get('assembly_level')}", flush=True)
        time.sleep(0.2)
        return rec

    def fill(target: str, levels: set[str], n: int, label: str) -> list[dict]:
        ranked = sorted(
            ((row, tax) for row, tax in annotated if (row.get("assembly_level") or "") in levels),
            key=lambda rt: (pool_sampling_hash(target, rt[0]["assembly_accession"]), rt[0]["assembly_accession"]),
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
                rec["pool_stratum"] = label
                picked.append(rec)

        drain(True, True)
        drain(True, False)
        drain(False, False)
        return picked

    for target in TARGETS:
        print(f"SELECT {target}", flush=True)
        complete = fill(target, COMPLETE_LEVELS, N_POOL_COMPLETE, "complete_or_chromosome")
        draft = fill(target, DRAFT_LEVELS, N_POOL_DRAFT, "scaffold_or_contig")
        if len(complete) < N_POOL_COMPLETE:
            need = N_POOL_COMPLETE - len(complete)
            print(f"FALLBACK complete->draft {target} need={need}", flush=True)
            complete.extend(fill(target, DRAFT_LEVELS, need, "scaffold_or_contig_fallback"))
        if len(draft) < N_POOL_DRAFT:
            need = N_POOL_DRAFT - len(draft)
            print(f"FALLBACK draft->complete {target} need={need}", flush=True)
            draft.extend(fill(target, COMPLETE_LEVELS, need, "complete_or_chromosome_fallback"))
        picked = complete + draft
        if len(picked) != (N_POOL_COMPLETE + N_POOL_DRAFT):
            raise SystemExit(f"could not fill {target}: {len(picked)}")
        selected.extend(picked)

    selected.sort(key=lambda r: (r["target"], r["sampling_hash"], r["assembly_accession"]))
    counts = defaultdict(int)
    quality = defaultdict(int)
    for rec in selected:
        counts[rec["target"]] += 1
        quality[rec["assembly_quality"]] += 1

    payload = {
        "kind": "D12_CANDIDATE_POOL_MANIFEST",
        "name": "V3_D12_EXTERNAL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": FREEZE_ID,
        "agentic_freeze_manifest_sha256": freeze["manifest_sha256"],
        "model": "qwen3:4b",
        "model_digest": EXPECTED_DIGEST,
        "seed": SEED,
        "sampling_hash_formula": 'SHA256("V3_D12_POOL|20260920|<target>|<assembly_accession>")',
        "selection_tie_break_formula": 'SHA256("V3_D12_EXTERNAL|20260920|<target>|<assembly_accession>")',
        "execution_hash_formula": 'SHA256("V3_D12_EXECUTION|20260920|<target>|<assembly_accession>")',
        "release_cutoff": "2025-01-01",
        "n_candidates": len(selected),
        "target_counts": dict(counts),
        "assembly_quality_counts": dict(quality),
        "n_unique_genomes": len({r["assembly_accession"] for r in selected}),
        "n_unique_species": len({r["species"] for r in selected}),
        "n_unique_genera": len({r["genus"] for r in selected}),
        "pool_design": {"per_target": 6, "prefer_complete_or_chromosome": 4, "prefer_scaffold_or_contig": 2},
        "d8_excluded": True,
        "d20_pool_excluded": True,
        "d20_candidate_pool_sha256": d20_sha,
        "d20_directory_modified": False,
        "prior_external_development_cohorts_excluded": True,
        "frozen_reference_source_genomes_excluded": True,
        "controlled_capability_source_genomes_excluded": True,
        "external_labels_opened": False,
        "gene_content_used_for_selection": False,
        "agentic_v3_executed": False,
        "current_lacz_limitation": CURRENT_LACZ_LIMITATION,
        "lacz_not_downweighted_for_missing_competing_family_instrument": True,
        "exclusion_note": exclusion_note,
        "download_failures_skipped": failures,
        "candidates": selected,
    }
    json_path = OUT / "D12_CANDIDATE_POOL.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    csv_path = OUT / "D12_CANDIDATE_POOL.csv"
    fields = [
        "assembly_accession",
        "organism",
        "genus",
        "species",
        "target",
        "release_date",
        "assembly_level",
        "assembly_quality",
        "pool_stratum",
        "fasta_sha256",
        "sampling_hash",
        "solver_fasta",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for rec in selected:
            w.writerow(rec)
    refs = OUT / "inputs" / "references.yaml"
    if not refs.exists():
        refs.write_text("references: []\n", encoding="utf-8")
    for path in (json_path, csv_path):
        digest = write_sha256_sidecar(path, {"hashed_before_v5_prescreen": True})
        print(path.name, digest, flush=True)
    assert_d20_untouched("pool_construction_end")
    print("N", len(selected), "GENERA", payload["n_unique_genera"], "SPECIES", payload["n_unique_species"], flush=True)


if __name__ == "__main__":
    main()
