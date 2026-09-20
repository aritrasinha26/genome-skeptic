#!/usr/bin/env python3
"""Download genomic nucleotide FASTA only for Cohort C; sanitize headers.

Does not download GFF, GBFF, protein FASTA, CDS, RNA, feature tables, or AMRFinder.
Must run only after cohort_C_manifest.json has been hashed.
Does not modify Agentic V1 freeze files or Cohort A.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation_agentic"
ORIG = OUT / "cohort_C_inputs" / "original"
SOLVER = OUT / "cohort_C_inputs" / "solver"
MANIFEST = OUT / "cohort_C_manifest.json"
MANIFEST_HASH = OUT / "cohort_C_manifest.sha256.json"
UA = "GenomeSkeptic-external-validation/cohort-C-solver-fasta-only"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize_fasta(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith(">"):
            ident = line[1:].strip().split()[0]
            lines.append(">" + ident)
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")


def download_genome_fasta(acc: str) -> bytes:
    url = (
        "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/"
        f"{acc}/download?include_annotation_type=GENOME_FASTA"
    )
    last = None
    for attempt in range(5):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=180) as resp:
                blob = resp.read()
            if blob[:2] != b"PK":
                raise RuntimeError(f"not a zip for {acc}: {blob[:80]!r}")
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                names = [n for n in zf.namelist() if n.endswith(".fna") or n.endswith(".fasta")]
                genomic = [n for n in names if "genomic" in n.lower() or n.endswith(".fna")]
                pick = genomic[0] if genomic else (names[0] if names else None)
                if pick is None:
                    raise RuntimeError(f"no fasta in zip for {acc}: {zf.namelist()[:20]}")
                return zf.read(pick)
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last)


def main() -> None:
    if not MANIFEST_HASH.exists():
        raise SystemExit("cohort_C_manifest.json was not hashed before download")
    lock = json.loads(MANIFEST_HASH.read_text(encoding="utf-8"))
    actual = sha256_file(MANIFEST)
    if actual != lock.get("sha256"):
        raise SystemExit(f"manifest hash mismatch: {actual} != {lock.get('sha256')}")
    cohort = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ORIG.mkdir(parents=True, exist_ok=True)
    SOLVER.mkdir(parents=True, exist_ok=True)
    rows = []
    for rec in cohort["assemblies"]:
        acc = rec["assembly_accession"]
        orig_path = ORIG / f"{acc}.fna"
        solver_path = SOLVER / f"{acc}.fna"
        print("fasta", acc, flush=True)
        if not orig_path.exists() or orig_path.stat().st_size < 1000:
            data = download_genome_fasta(acc)
            text = data.decode("utf-8", errors="replace")
            orig_path.write_text(text, encoding="utf-8")
        else:
            text = orig_path.read_text(encoding="utf-8", errors="replace")
        sanitized = sanitize_fasta(text)
        solver_path.write_text(sanitized, encoding="utf-8")
        rows.append({
            "assembly_accession": acc,
            "organism": rec.get("organism"),
            "genus": rec.get("genus"),
            "phylum": rec.get("phylum"),
            "assembly_level": rec.get("assembly_level"),
            "original_fasta": str(orig_path.relative_to(ROOT)).replace("\\", "/"),
            "original_fasta_sha256": sha256_file(orig_path),
            "solver_fasta": str(solver_path.relative_to(ROOT)).replace("\\", "/"),
            "solver_fasta_sha256": sha256_file(solver_path),
            "headers_sanitized": True,
            "gff_downloaded": False,
            "gbff_downloaded": False,
            "protein_fasta_downloaded": False,
            "cds_fasta_downloaded": False,
            "amrfinder_downloaded": False,
        })
        time.sleep(0.35)
    payload = {
        "kind": "cohort_C_input_manifest",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "cohort_manifest_sha256": actual,
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V1",
        "agentic_freeze_manifest_sha256": "9ca874bb38efa073b2e0801f6f492e6bb1fdabd27ba2a225c70e559ba5bf8c54",
        "n_assemblies": len(rows),
        "solver_inputs_only": True,
        "annotations_downloaded": False,
        "external_labels_opened": False,
        "genomes": rows,
    }
    dest = OUT / "cohort_C_input_manifest.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = sha256_file(dest)
    (OUT / "cohort_C_input_manifest.sha256.json").write_text(
        json.dumps(
            {
                "file": "cohort_C_input_manifest.json",
                "sha256": digest,
                "hashed_utc": datetime.now(timezone.utc).isoformat(),
                "hashed_before_execution": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("INPUT_MANIFEST", digest, flush=True)


if __name__ == "__main__":
    main()
