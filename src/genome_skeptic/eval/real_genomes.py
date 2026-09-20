"""Build isolated real-genome FASTQ cases. Corruption is applied to reads/samples."""
from __future__ import annotations

import random
import shutil
from pathlib import Path

import yaml

from genome_skeptic.config import Settings
from genome_skeptic.eval.catalog import PUBLIC_RPOB_SEED, GenomeSpec
from genome_skeptic.eval.simulate import simulate_paired_reads
from genome_skeptic.io_utils import read_fasta
from genome_skeptic.tools.gene_search import reverse_complement, search_targets


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _case_yaml(case_id: str, declared: str) -> str:
    return (
        f"id: {case_id}\n"
        "r1: reads_R1.fastq\n"
        "r2: reads_R2.fastq\n"
        "targets: targets.fa\n"
        f"declared_organism: {declared}\n"
        "references: references.yaml\n"
    )


def _empty_refs(dest: Path) -> None:
    _write(dest / "references.yaml", "references: []\n")


def _mix(a: Path, b: Path, dest: Path, frac_b: float = 1.0, seed: int = 3) -> None:
    rng = random.Random(seed)

    def recs(path: Path) -> list[str]:
        lines = path.read_text().splitlines()
        return ["\n".join(lines[i:i + 4]) for i in range(0, len(lines), 4) if i + 3 < len(lines)]

    ra, rb = recs(a), recs(b)
    keep = [r for r in rb if rng.random() < frac_b]
    dest.write_text("\n".join(ra + keep) + ("\n" if ra or keep else ""))


def _exact_present(genome_fa: Path, query: str) -> bool:
    q = query.upper()
    rc = reverse_complement(q)
    for _cid, seq in read_fasta(genome_fa):
        u = seq.upper()
        if q in u or rc in u:
            return True
    return False


def locate_target(
    genome_fa: Path,
    query: str,
    *,
    min_identity: float | None = None,
    min_coverage: float | None = None,
) -> dict | None:
    """Diagnostic helper. Requires identity AND coverage. Never defines biological truth."""
    settings = Settings()
    min_identity = settings.thresholds.gene_nt_min_identity if min_identity is None else min_identity
    min_coverage = settings.thresholds.gene_nt_min_query_coverage if min_coverage is None else min_coverage
    hits = search_targets([("query", query)], list(read_fasta(genome_fa)), settings)
    if not hits:
        return {
            "contig": None, "start": None, "end": None, "identity": None, "coverage": None,
            "present": False, "n_hits": 0,
            "min_identity": min_identity, "min_coverage": min_coverage,
        }
    best = max(hits, key=lambda h: h.identity * h.query_coverage)
    present = (best.identity or 0) >= min_identity and (best.query_coverage or 0) >= min_coverage
    return {
        "contig": best.contig_id,
        "start": min(best.tstart, best.tend),
        "end": max(best.tstart, best.tend),
        "identity": best.identity,
        "coverage": best.query_coverage,
        "alignment_length": best.alignment_length,
        "query_length": best.query_length,
        "search_kind": best.search_kind,
        "present": present,
        "n_hits": len(hits),
        "min_identity": min_identity,
        "min_coverage": min_coverage,
    }


def _anonymize_fasta(src: Path, dest: Path) -> tuple[Path, list[dict]]:
    """Rewrite headers so FASTQ names cannot leak hidden accessions."""
    records = list(read_fasta(src))
    dest.parent.mkdir(parents=True, exist_ok=True)
    mapping = []
    chunks = []
    for i, (cid, seq) in enumerate(records, 1):
        opaque = f"replicon_{i}"
        chunks.append(f">{opaque}\n{seq}")
        mapping.append({"opaque": opaque, "source_contig": cid, "length": len(seq)})
    dest.write_text("\n".join(chunks) + ("\n" if chunks else ""))
    return dest, mapping


def write_real_genome_benchmark(
    root: Path,
    genomes: list[tuple[GenomeSpec, Path, dict]],
    *,
    split: str,
    require_production_simulator: bool = True,
    profile: str = "production",
) -> dict:
    """Simulate genuine paired-end reads from complete hidden genomes.

    Agent-visible FASTQ is generated from anonymized replicons. The complete
    source FASTA never enters the analysis working directory.
    """
    visible = root / "agent_visible"
    hidden = root / "hidden"
    if visible.exists():
        shutil.rmtree(visible)
    sim_dir = hidden / "simulation"
    if sim_dir.exists():
        shutil.rmtree(sim_dir)
    cases: dict = {}
    n = 0
    fast_pilot = (profile or "").strip().lower() == "fast_pilot"
    clean_coverage = 25 if fast_pilot else 20
    low_coverage = 8
    include_low_coverage = not fast_pilot
    include_contamination = not fast_pilot
    clean_label = f"clean_{int(clean_coverage)}x"

    def add(label: str, fasta: Path, sim_kwargs: dict, truth: dict, declared: str, target: str) -> str:
        nonlocal n
        n += 1
        case_id = f"{split[:3]}_{n:02d}"
        vdir = visible / case_id
        hdir = hidden / "simulation" / case_id
        r1, r2, params = simulate_paired_reads(
            fasta, hdir / "reads_raw",
            read_len=sim_kwargs.get("read_len", 150),
            insert=sim_kwargs.get("insert", 350),
            require_production_simulator=require_production_simulator,
            **{k: v for k, v in sim_kwargs.items() if k not in {"read_len", "insert", "require_production_simulator"}},
        )
        dest_r1, dest_r2 = vdir / "reads_R1.fastq", vdir / "reads_R2.fastq"
        dest_r1.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(r1, dest_r1)
        shutil.copy2(r2, dest_r2)
        _write(vdir / "targets.fa", f">rpoB\n{target}\n")
        _empty_refs(vdir)
        _write(vdir / "case.yaml", _case_yaml(case_id, declared))
        _write(hdir / "simulation_provenance.yaml", yaml.safe_dump(params, sort_keys=False))
        truth = dict(truth)
        truth["label"] = label
        truth["split"] = split
        truth["simulation"] = {k: params.get(k) for k in ("simulator", "seed", "coverage", "read_len", "insert", "error_rate", "adapter_rate", "coverage_profile", "end_quality_drop", "command")}
        cases[case_id] = (vdir, truth)
        return case_id

    prepared = []
    for spec, fa, prov in genomes:
        dest_src = hidden / "genomes" / spec.genome_id / "source_genome.fa"
        dest_src.parent.mkdir(parents=True, exist_ok=True)
        try:
            if Path(fa).resolve() != dest_src.resolve():
                shutil.copy2(fa, dest_src)
                src_for_sim = dest_src
            else:
                src_for_sim = Path(fa)
        except OSError:
            src_for_sim = Path(fa)
        anon, mapping = _anonymize_fasta(src_for_sim, hidden / "genomes" / spec.genome_id / "sim_source.fa")
        prepared.append((spec, fa, prov, anon, mapping))

    for spec, fa, prov, anon, mapping in prepared:
        declared = spec.species.split()[0] + " " + spec.species.split()[1]
        exact = _exact_present(Path(fa), PUBLIC_RPOB_SEED)
        add(clean_label, anon, {"coverage": clean_coverage, "seed": 40 + n, "read_len": 150, "insert": 350, "error_rate": 0.01}, {
            "genome_id": spec.genome_id,
            "true_organism": spec.species,
            "split": split,
            "corruption": "none",
            "targets": {"rpoB": {
                "present": exact, "clean": True, "uncertainty_required": False,
                "target_type": "exact_allele", "truth_state": "resolved",
                "provenance": {"rule": "exact_nucleotide_string_in_source_genome", "query": "PUBLIC_RPOB_SEED_deprecated"},
            }},
            "acceptable_action_classes": ["continue"],
            "replicon_map": mapping,
        }, declared, PUBLIC_RPOB_SEED)

    if include_low_coverage:
        spec, fa, prov, anon, mapping = prepared[0]
        present = _exact_present(Path(fa), PUBLIC_RPOB_SEED)
        declared = spec.species.split()[0] + " " + spec.species.split()[1]
        add("low_coverage", anon, {"coverage": low_coverage, "seed": 41, "read_len": 150, "insert": 350, "error_rate": 0.01}, {
            "genome_id": spec.genome_id,
            "true_organism": spec.species,
            "split": split,
            "corruption": "low_coverage",
            "targets": {"rpoB": {"present": present, "fragmented": True, "uncertainty_required": True, "target_type": "exact_allele", "truth_state": "resolved"}},
            "acceptable_action_classes": ["inspect_paired_end_support", "try_alternative_assembler", "inspect_contig_ends", "inspect_coverage"],
        }, declared, PUBLIC_RPOB_SEED)

    if include_contamination and len(prepared) >= 2:
        spec_a, fa_a, _p_a, anon_a, _m_a = prepared[0]
        spec_b, _fa_b, _p_b, anon_b, _m_b = prepared[1]
        declared_a = spec_a.species.split()[0] + " " + spec_a.species.split()[1]
        present_a = _exact_present(Path(fa_a), PUBLIC_RPOB_SEED)
        case_id = add("cross_species_contamination", anon_a, {"coverage": clean_coverage, "seed": 50, "read_len": 150, "insert": 350}, {
            "genome_id": spec_a.genome_id,
            "true_organism": spec_a.species,
            "split": split,
            "corruption": "cross_species_contamination",
            "targets": {"rpoB": {"present": present_a, "contaminant": True, "uncertainty_required": True, "target_type": "exact_allele", "truth_state": "resolved"}},
            "acceptable_action_classes": ["investigate_contamination", "classify_taxonomy"],
        }, declared_a, PUBLIC_RPOB_SEED)
        fr1, fr2, _ = simulate_paired_reads(
            anon_b, hidden / "simulation" / case_id / "foreign",
            coverage=8, seed=51, read_len=150, insert=350,
            require_production_simulator=require_production_simulator,
        )
        _mix(visible / case_id / "reads_R1.fastq", fr1, visible / case_id / "reads_R1.fastq")
        _mix(visible / case_id / "reads_R2.fastq", fr2, visible / case_id / "reads_R2.fastq")

    hidden_truth = {"cases": {cid: spec for cid, (_v, spec) in cases.items()}}
    _write(hidden / "truth.yaml", yaml.safe_dump(hidden_truth, sort_keys=False))
    _write(hidden / "README.txt", (
        "Scorer-only real-genome truth. Never pass to Genome Skeptic.\n"
        "Reads are simulated from the complete hidden genome with anonymized FASTA headers.\n"
        "Assemblies are not edited. Corruption is applied at the read/sample level.\n"
    ))
    catalog_hidden = [
        {"genome_id": spec.genome_id, "accession": spec.accession, "species": spec.species,
         "assembly_level": spec.assembly_level, "source": spec.source, "url": spec.url,
         "download": prov, "notes": spec.notes, "plasmids": spec.plasmids,
         "extra_accessions": list(spec.extra_accessions)}
        for spec, _fa, prov in genomes
    ]
    _write(hidden / "genome_catalog.yaml", yaml.safe_dump(catalog_hidden, sort_keys=False))
    return {
        "root": str(root),
        "n_cases": len(cases),
        "split": split,
        "kind": "fast_pilot_real_genome" if fast_pilot else "production_real_genome",
        "profile": "fast_pilot" if fast_pilot else "production",
        "banner": "FAST PILOT - NOT FINAL BENCHMARK" if fast_pilot else None,
        "clean_coverage": clean_coverage,
        "low_coverage": low_coverage,
        "note": (
            "FAST PILOT - NOT FINAL BENCHMARK. Scores must not be mixed with the full production benchmark."
            if fast_pilot else None
        ),
    }
