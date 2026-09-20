"""Scorer-side annotation truth. Never used to set agent search thresholds."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genome_skeptic.io_utils import read_fasta
from genome_skeptic.tools.gene_search import reverse_complement, translate_frame

ACCESSIONS = {
    "ecoli_k12": "NC_000913.3",
    "pao1": "NC_002516.2",
    "hpylori": "NC_000915.1",
    "salmonella_lt2": "NC_003197.2",
    "pputida_kt2440": "NC_002947.4",
    "staph_8325": "NC_007795.1",
}

ALLELE_SOURCE_GENOME = "ecoli_k12"


def sha256_seq(seq: str) -> str:
    return hashlib.sha256(seq.upper().encode("ascii")).hexdigest()


def parse_feature_table(text: str) -> list[dict]:
    """Parse an NCBI feature table. Gene names are inherited by the following CDS."""
    rows: list[dict] = []
    last_gene: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        parts = lines[i].split("\t")
        if len(parts) >= 3 and parts[2] and not lines[i].startswith("\t\t\t"):
            feat_type = parts[2]
            try:
                a, b = int(parts[0]), int(parts[1])
            except ValueError:
                i += 1
                continue
            strand = "+" if a <= b else "-"
            lo, hi = min(a, b), max(a, b)
            attrs: dict = {}
            i += 1
            while i < len(lines) and lines[i].startswith("\t\t\t"):
                kv = lines[i].strip().split("\t")
                if len(kv) >= 2:
                    attrs[kv[0]] = kv[1]
                elif kv:
                    attrs[kv[0]] = True
                i += 1
            rec = {
                "feature": feat_type,
                "start": lo,
                "end": hi,
                "strand": strand,
                "attrs": attrs,
            }
            if feat_type == "gene":
                last_gene = rec
            if feat_type == "CDS":
                rec["gene"] = attrs.get("gene") or (last_gene.get("attrs") or {}).get("gene")
                rec["locus_tag"] = attrs.get("locus_tag") or (last_gene.get("attrs") or {}).get("locus_tag")
                rec["db_xref"] = attrs.get("db_xref")
                rec["gene_db_xref"] = (last_gene.get("attrs") or {}).get("db_xref")
                rec["product"] = attrs.get("product")
                rec["protein_id"] = attrs.get("protein_id")
                rec["gene_length"] = hi - lo + 1
            rows.append(rec)
            continue
        i += 1
    return rows


def _product_is_rpob(product: str, gene: str | None) -> tuple[bool, bool]:
    g = (gene or "").strip()
    p = (product or "").lower()
    fusion = "beta/beta" in p or "beta / beta" in p
    if g == "rpoB":
        return True, fusion
    if fusion and "rna polymerase" in p:
        return True, True
    if "rna polymerase" not in p:
        return False, False
    beta = "subunit beta" in p or "beta subunit" in p or "beta chain" in p
    if not beta:
        return False, False
    if "beta'" in p.replace("beta/beta'", "") or "beta-prime" in p or "beta prime" in p:
        return False, False
    return True, False


def find_rpob_cds(features: list[dict]) -> dict | None:
    best = None
    for rec in features:
        if rec.get("feature") != "CDS":
            continue
        ok, fusion = _product_is_rpob(rec.get("product") or "", rec.get("gene"))
        if not ok:
            continue
        rec = dict(rec)
        rec["fusion"] = fusion
        rec["nucleotide_length"] = rec["end"] - rec["start"] + 1
        if fusion:
            return rec
        if rec.get("gene") == "rpoB":
            return rec
        best = rec
    return best


def extract_locus(genome_fa: Path, start: int, end: int, strand: str) -> str:
    records = list(read_fasta(genome_fa))
    if not records:
        raise FileNotFoundError(f"no FASTA records in {genome_fa}")
    seq = records[0][1]
    nt = seq[start - 1:end]
    if strand == "-":
        nt = reverse_complement(nt)
    return nt.upper()


def translate_cds(nt: str) -> str:
    aa = translate_frame(nt, 0)
    return aa.split("*")[0]


def clean_protein_id(raw: str | None) -> str | None:
    if not raw:
        return None
    if "ref|" in raw:
        return raw.split("ref|", 1)[1].split("|", 1)[0]
    return raw


def gene_id_from_xref(*raws: str | None) -> str | None:
    for raw in raws:
        if not raw:
            continue
        if "GeneID:" in raw:
            return raw.split("GeneID:", 1)[1].split()[0]
    return None


def annotate_genome(genome_id: str, genome_fa: Path, feature_table: Path, accession: str) -> dict:
    features = parse_feature_table(feature_table.read_text(encoding="utf-8", errors="replace"))
    cds = find_rpob_cds(features)
    if cds is None:
        return {
            "genome_id": genome_id,
            "accession": accession,
            "rpoB": None,
            "orthology": {
                "state": "unresolved",
                "reason": "no rpoB or RNA-polymerase-beta CDS found in trusted source annotation",
            },
        }
    nt = extract_locus(genome_fa, cds["start"], cds["end"], cds["strand"])
    aa = translate_cds(nt)
    fusion = bool(cds.get("fusion"))
    rec = {
        "genome_id": genome_id,
        "accession": accession,
        "gene": cds.get("gene") or ("rpoBC" if fusion else "rpoB"),
        "locus_tag": cds.get("locus_tag"),
        "gene_id": gene_id_from_xref(cds.get("db_xref"), cds.get("gene_db_xref")),
        "protein_id": clean_protein_id(cds.get("protein_id")),
        "product": cds.get("product"),
        "start": cds["start"],
        "end": cds["end"],
        "strand": cds["strand"],
        "nucleotide_length": len(nt),
        "protein_length": len(aa),
        "nucleotide_sha256": sha256_seq(nt),
        "protein_sha256": sha256_seq(aa),
        "fusion": fusion,
        "annotation_provenance": {
            "source": "NCBI RefSeq feature table",
            "accession": accession,
            "feature_table": str(feature_table),
            "source_genome": str(genome_fa),
            "coordinate_system": "1-based inclusive NCBI feature table",
        },
        "nucleotide": nt,
        "protein": aa,
        "orthology": {
            "state": "present",
            "assignment": "source_annotation_rpoB" if not fusion else "source_annotation_rpoB_rpoC_fusion",
            "independent_of_agent_threshold": True,
        },
    }
    return rec


def load_all_rpob(root: Path) -> dict[str, dict]:
    ann_dir = root / "benchmarks" / "semantics_v2" / "annotations"
    genomes_root = root / "benchmarks"
    locations = {
        "ecoli_k12": genomes_root / "real_genomes_fast_pilot_dev" / "hidden" / "genomes" / "ecoli_k12" / "source_genome.fa",
        "pao1": genomes_root / "real_genomes_fast_pilot_dev" / "hidden" / "genomes" / "pao1" / "source_genome.fa",
        "hpylori": genomes_root / "real_genomes_fast_pilot_dev" / "hidden" / "genomes" / "hpylori" / "source_genome.fa",
        "salmonella_lt2": genomes_root / "real_genomes_fast_pilot_held" / "hidden" / "genomes" / "salmonella_lt2" / "source_genome.fa",
        "pputida_kt2440": genomes_root / "real_genomes_fast_pilot_held" / "hidden" / "genomes" / "pputida_kt2440" / "source_genome.fa",
        "staph_8325": genomes_root / "real_genomes_fast_pilot_held" / "hidden" / "genomes" / "staph_8325" / "source_genome.fa",
    }
    out = {}
    for gid, acc in ACCESSIONS.items():
        ft = ann_dir / f"{gid}_{acc}.ft.txt"
        fa = locations[gid]
        out[gid] = annotate_genome(gid, fa, ft, acc)
    return out


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def _strip(obj):
        if isinstance(obj, dict):
            return {k: _strip(v) for k, v in obj.items() if k not in {"nucleotide", "protein"}}
        if isinstance(obj, list):
            return [_strip(v) for v in obj]
        return obj

    path.write_text(json.dumps(_strip(payload), indent=2))
