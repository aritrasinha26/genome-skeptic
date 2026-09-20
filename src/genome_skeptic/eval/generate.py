"""Generate physically isolated real-world-style bacterial benchmark cases.

Agent-visible trees contain FASTQ, targets, declared organism, and permitted
references. Hidden trees contain the complete source genome, corruption labels,
simulation parameters, and the truth manifest. Case directories use opaque IDs
so Genome Skeptic never sees the corruption type in its inputs.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from genome_skeptic.eval.simulate import simulate_paired_reads
from genome_skeptic.eval.synthetic import _fa, _gff, _operon, _proteins, translate


def _unique_cds(seed: str, n_codons: int) -> str:
    """Non-periodic CDS so an eval de Bruijn assembler can traverse the gene."""
    import random
    rng = random.Random(seed)
    codons = []
    while len(codons) < n_codons:
        codon = "".join(rng.choice("ACGT") for _ in range(3))
        if codon in {"TAA", "TAG", "TGA"}:
            continue
        if codon == "ATG" and codons:
            continue
        codons.append(codon)
    return "ATG" + "".join(codons) + "TAA"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _mutate(seq: str, every: int = 12) -> str:
    trans = str.maketrans("ACGT", "CGTA")
    chars = list(seq)
    for i in range(3, len(chars) - 3, every):
        chars[i] = chars[i].translate(trans)
    return "".join(chars)


def _complete_genome() -> tuple[dict[str, str], dict[str, list[tuple[str, int, int, str]]], dict[str, str]]:
    genes_nt = {
        "dnaA": _unique_cds("dnaA", 36),
        "gyrA": _unique_cds("gyrA", 40),
        "rpoB": _unique_cds("rpoB", 42),
        "rpoC": _unique_cds("rpoC", 38),
        "rplK": _unique_cds("rplK", 32),
    }
    chrom, genes = _operon([(name, seq) for name, seq in genes_nt.items()])
    plasmid = "C" * 80 + _unique_cds("plasmid", 18) + "G" * 80
    return {"chromosome": chrom, "plasmid": plasmid}, {"chromosome": genes}, genes_nt


def _permitted_refs(dest: Path, genes_nt: dict[str, str]) -> None:
    seq, genes = _operon(list(genes_nt.items()))
    proteins = _proteins(genes_nt)
    proteins["rpoB_paralog"] = translate(_mutate(genes_nt["rpoB"], every=6))
    _write(dest / "ref.fa", _fa({"ref": seq}))
    _write(dest / "ref.gff", _gff("ref", genes))
    _write(dest / "ref.faa", _fa(proteins))
    _write(dest / "references.yaml", """references:
  - id: trusted_reference
    fasta: ref.fa
    gff: ref.gff
    proteins: ref.faa
    homologues:
      - id: rpoB
        clade: ortholog
      - id: rpoB_paralog
        clade: paralog
""")


def _case_yaml(case_id: str, declared: str) -> str:
    return (
        f"id: {case_id}\n"
        "r1: reads_R1.fastq\n"
        "r2: reads_R2.fastq\n"
        "targets: targets.fa\n"
        f"declared_organism: {declared}\n"
        "references: references.yaml\n"
    )


def _mix_fastq(a: Path, b: Path, dest: Path, keep_b_frac: float, seed: int = 3) -> None:
    import random
    rng = random.Random(seed)

    def records(path: Path) -> list[str]:
        text = path.read_text().splitlines()
        return ["\n".join(text[i:i + 4]) for i in range(0, len(text), 4) if i + 3 < len(text)]

    ra, rb = records(a), records(b)
    keep = [rec for rec in rb if rng.random() < keep_b_frac]
    dest.write_text("\n".join(ra + keep) + ("\n" if ra or keep else ""))


def write_realworld_benchmark(root: Path) -> Path:
    visible = root / "agent_visible"
    hidden = root / "hidden"
    genomes, gene_map, genes_nt = _complete_genome()
    rpoB = genes_nt["rpoB"]
    source_fa = hidden / "genomes" / "source_genome.fa"
    _write(source_fa, _fa(genomes))
    _write(hidden / "genomes" / "source.gff", _gff("chromosome", gene_map["chromosome"]))

    rpo_genes = [g for g in gene_map["chromosome"] if g[0] == "rpoB"][0]
    rpo_start = rpo_genes[1]
    chrom = genomes["chromosome"]

    cases = []
    n = 0

    def add(label: str, fasta: Path, sim_kwargs: dict, truth: dict, declared: str = "Escherichia coli") -> str:
        nonlocal n
        n += 1
        case_id = f"case_{n:02d}"
        vdir = visible / case_id
        hdir = hidden / "simulation" / case_id
        r1, r2, params = simulate_paired_reads(fasta, hdir / "reads_raw", **sim_kwargs)
        dest_r1 = vdir / "reads_R1.fastq"
        dest_r2 = vdir / "reads_R2.fastq"
        dest_r1.parent.mkdir(parents=True, exist_ok=True)
        dest_r1.write_text(r1.read_text())
        dest_r2.write_text(r2.read_text())
        _write(vdir / "targets.fa", f">rpoB neighbors=dnaA,rpoC\n{rpoB}\n")
        _permitted_refs(vdir, genes_nt)
        _write(vdir / "case.yaml", _case_yaml(case_id, declared))
        _write(hdir / "simulation_provenance.yaml", yaml.safe_dump(params, sort_keys=False))
        truth = dict(truth)
        truth["label"] = label
        cases.append((case_id, truth, params))
        return case_id

    add("clean_short_read", source_fa, {"coverage": 18, "seed": 11}, {
        "targets": {"rpoB": {"present": True, "uncertainty_required": False}},
        "expected_next_action": "continue_pipeline",
        "expected_actions": [],
        "corruption": "none",
    })
    add("low_coverage", source_fa, {"coverage": 3, "seed": 12}, {
        "targets": {"rpoB": {"present": True, "fragmented": True, "uncertainty_required": True}},
        "expected_next_action": "repeat_assembly_after_diagnosing_fragmentation",
        "expected_actions": ["inspect_read_supported_breaks", "repeat_assembly_after_diagnosing_fragmentation"],
        "corruption": "low_coverage",
    })
    add("uneven_coverage", source_fa, {"coverage": 16, "coverage_profile": "uneven", "seed": 13}, {
        "targets": {"rpoB": {"present": True, "uncertainty_required": True}},
        "expected_next_action": "investigate_coverage_anomalies",
        "expected_actions": ["investigate_coverage_anomalies"],
        "corruption": "uneven_coverage",
    })
    add("adapter_quality_degradation", source_fa, {"coverage": 16, "adapter_rate": 0.35, "quality": 12, "seed": 14}, {
        "targets": {"rpoB": {"present": True, "uncertainty_required": True}},
        "expected_next_action": "repeat_cleaning_with_reviewed_parameters",
        "expected_actions": ["repeat_cleaning_with_reviewed_parameters"],
        "corruption": "adapter_quality",
    })

    bac = hidden / "genomes" / "bacillus_analogue.fa"
    _write(bac, _fa({"foreign": "G" * 400 + "ATG" + ("GGGCCC") * 24 + "TAA" + "C" * 400}))
    cross_id = add("cross_species_contamination", source_fa, {"coverage": 14, "seed": 15}, {
        "targets": {"rpoB": {"present": True, "contaminant": True, "uncertainty_required": True}},
        "expected_next_action": "investigate_contamination",
        "expected_actions": ["investigate_contamination", "classify_contig_taxonomy"],
        "corruption": "cross_species_contamination",
    })
    fr1, fr2, _ = simulate_paired_reads(bac, hidden / "simulation" / cross_id / "foreign", coverage=8, seed=99)
    _mix_fastq(visible / cross_id / "reads_R1.fastq", fr1, visible / cross_id / "reads_R1.fastq", 1.0)
    _mix_fastq(visible / cross_id / "reads_R2.fastq", fr2, visible / cross_id / "reads_R2.fastq", 1.0)

    strain = hidden / "genomes" / "related_strain.fa"
    _write(strain, _fa({"chromosome": _mutate(chrom, every=9), "plasmid": genomes["plasmid"]}))
    strain_id = add("closely_related_strain_contamination", source_fa, {"coverage": 14, "seed": 16}, {
        "targets": {"rpoB": {"present": True, "contaminant": True, "uncertainty_required": True}},
        "expected_next_action": "investigate_contamination",
        "expected_actions": ["investigate_contamination"],
        "corruption": "related_strain_contamination",
    })
    sr1, sr2, _ = simulate_paired_reads(strain, hidden / "simulation" / strain_id / "strain", coverage=5, seed=17)
    _mix_fastq(visible / strain_id / "reads_R1.fastq", sr1, visible / strain_id / "reads_R1.fastq", 1.0)
    _mix_fastq(visible / strain_id / "reads_R2.fastq", sr2, visible / strain_id / "reads_R2.fastq", 1.0)

    plasmid_hi = hidden / "genomes" / "high_copy.fa"
    recs = {"chromosome": chrom}
    for i in range(8):
        recs[f"plasmid_{i}"] = genomes["plasmid"]
    _write(plasmid_hi, _fa(recs))
    add("high_copy_plasmid", plasmid_hi, {"coverage": 20, "seed": 18}, {
        "targets": {"rpoB": {"present": True, "uncertainty_required": False}},
        "expected_next_action": "investigate_coverage_anomalies",
        "expected_actions": ["investigate_coverage_anomalies"],
        "corruption": "high_copy_plasmid",
    })

    para_fa = hidden / "genomes" / "paralogues.fa"
    extra = chrom + "N" * 80 + rpoB + "N" * 80
    _write(para_fa, _fa({"chromosome": extra, "plasmid": genomes["plasmid"]}))
    add("target_paralogues", para_fa, {"coverage": 16, "seed": 19}, {
        "targets": {"rpoB": {"present": True, "paralogue": True, "uncertainty_required": True}},
        "expected_next_action": "inspect_paralogue_copies",
        "expected_actions": ["inspect_paralogue_copies", "place_target_among_homologues"],
        "corruption": "paralogues",
    })

    repeat = "ACGTACGT" * 40
    near = chrom[:rpo_start] + repeat + chrom[rpo_start:]
    rep_fa = hidden / "genomes" / "repeat.fa"
    _write(rep_fa, _fa({"chromosome": near}))
    add("target_near_repeat", rep_fa, {"coverage": 16, "seed": 20}, {
        "targets": {"rpoB": {"present": True, "fragmented": True, "uncertainty_required": True}},
        "expected_next_action": "repeat_assembly_after_diagnosing_fragmentation",
        "expected_actions": ["inspect_read_supported_breaks"],
        "corruption": "target_near_repeat",
    })

    add("target_fragmented", source_fa, {
        "coverage": 16, "seed": 21,
        "drop_windows": [("chromosome", rpo_start + 20, rpo_start + 80)],
    }, {
        "targets": {"rpoB": {"present": True, "fragmented": True, "uncertainty_required": True}},
        "expected_next_action": "inspect_read_supported_breaks",
        "expected_actions": ["inspect_read_supported_breaks", "repeat_assembly_after_diagnosing_fragmentation"],
        "corruption": "fragmented_target",
    })
    add("target_contig_break", source_fa, {
        "coverage": 16, "seed": 22,
        "drop_windows": [("chromosome", max(0, rpo_start - 10), rpo_start + 30)],
    }, {
        "targets": {"rpoB": {"present": True, "fragmented": True, "uncertainty_required": True}},
        "expected_next_action": "inspect_read_supported_breaks",
        "expected_actions": ["inspect_read_supported_breaks"],
        "corruption": "contig_break",
    })

    div = hidden / "genomes" / "divergent.fa"
    _write(div, _fa({"chromosome": chrom.replace(rpoB, _mutate(rpoB, every=6))}))
    add("divergent_homologue", div, {"coverage": 16, "seed": 23}, {
        "targets": {"rpoB": {"present": True, "uncertainty_required": True}},
        "expected_next_action": "search_target_genes_translated",
        "expected_actions": ["search_target_genes_translated", "search_target_proteins_mmseqs"],
        "corruption": "divergent_homologue",
    })

    absent = hidden / "genomes" / "absence.fa"
    _write(absent, _fa({"chromosome": chrom.replace(rpoB, "A" * len(rpoB))}))
    add("genuine_absence", absent, {"coverage": 16, "seed": 24}, {
        "targets": {"rpoB": {"present": False, "overclaim_forbidden": True}},
        "expected_next_action": "continue_pipeline",
        "expected_actions": [],
        "corruption": "genuine_absence",
    })
    add("incorrect_organism_identity", source_fa, {"coverage": 16, "seed": 25}, {
        "targets": {"rpoB": {"present": True, "contaminant": False, "uncertainty_required": True}},
        "expected_next_action": "classify_contig_taxonomy",
        "expected_actions": ["classify_contig_taxonomy"],
        "corruption": "incorrect_organism_identity",
        "true_organism": "Escherichia coli",
    }, declared="Bacillus cereus")

    truth = {"cases": {}}
    for case_id, spec, params in cases:
        entry = dict(spec)
        entry["simulation"] = {
            "seed": params.get("seed"),
            "simulator": params.get("simulator"),
            "coverage": params.get("coverage"),
            "read_len": params.get("read_len"),
            "insert": params.get("insert"),
            "error_rate": params.get("error_rate"),
            "adapter_rate": params.get("adapter_rate"),
            "coverage_profile": params.get("coverage_profile"),
            "drop_windows": params.get("drop_windows"),
            "command": params.get("command"),
        }
        truth["cases"][case_id] = entry
    _write(hidden / "truth.yaml", yaml.safe_dump(truth, sort_keys=False))
    _write(hidden / "README.txt", "Scorer-only. Never pass this directory to Genome Skeptic.\n")
    return root
