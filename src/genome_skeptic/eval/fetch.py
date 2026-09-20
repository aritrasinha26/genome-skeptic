"""Download hidden source genomes. Accessions stay in scorer-side provenance."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from genome_skeptic.eval.catalog import GenomeSpec


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_genome(spec: GenomeSpec, dest_dir: Path, timeout: int = 60) -> dict:
    dest_dir.mkdir(parents=True, exist_ok=True)
    fasta = dest_dir / "source_genome.fa"
    meta_path = dest_dir / "download_provenance.json"
    if fasta.exists() and fasta.stat().st_size > 500:
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        meta.setdefault("checksum_sha256", _sha256(fasta))
        blob = fasta.read_text(errors="replace")
        missing_extra = [acc for acc in spec.extra_accessions if acc not in blob]
        if missing_extra:
            for extra in missing_extra:
                extra_url = (
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                    f"?db=nuccore&id={extra}&rettype=fasta&retmode=text"
                )
                try:
                    with urlopen(Request(extra_url, headers={"User-Agent": "GenomeSkeptic/eval (scientific benchmark)"}), timeout=timeout) as resp:
                        extra_text = resp.read().decode("utf-8", errors="replace")
                    if extra_text.lstrip().startswith(">"):
                        with fasta.open("a") as fh:
                            fh.write("\n" + extra_text.rstrip() + "\n")
                except Exception:
                    pass
            meta["checksum_sha256"] = _sha256(fasta)
            meta["bytes"] = fasta.stat().st_size
            meta_path.write_text(json.dumps({**meta, "ok": True, "fasta": str(fasta)}, indent=2))
        return {**meta, "ok": True, "fasta": str(fasta.resolve()), "cached": True}
    req = Request(spec.url, headers={"User-Agent": "GenomeSkeptic/eval (scientific benchmark)"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "accession": spec.accession, "url": spec.url}
    if not text.lstrip().startswith(">"):
        return {"ok": False, "error": "response was not FASTA", "accession": spec.accession}
    fasta.write_text(text)
    for extra in spec.extra_accessions:
        extra_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=nuccore&id={extra}&rettype=fasta&retmode=text"
        )
        try:
            with urlopen(Request(extra_url, headers={"User-Agent": "GenomeSkeptic/eval (scientific benchmark)"}), timeout=timeout) as resp:
                extra_text = resp.read().decode("utf-8", errors="replace")
            if extra_text.lstrip().startswith(">"):
                with fasta.open("a") as fh:
                    fh.write("\n" + extra_text.rstrip() + "\n")
        except Exception:
            pass
    meta = {
        "ok": True,
        "accession": spec.accession,
        "species": spec.species,
        "assembly_level": spec.assembly_level,
        "source": spec.source,
        "url": spec.url,
        "download_date": date.today().isoformat(),
        "checksum_sha256": _sha256(fasta),
        "bytes": fasta.stat().st_size,
        "fasta": str(fasta),
        "cached": False,
        "notes": spec.notes,
        "split": spec.split,
        "genome_id": spec.genome_id,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta
