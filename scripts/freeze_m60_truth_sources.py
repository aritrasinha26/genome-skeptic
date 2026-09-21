#!/usr/bin/env python3
"""Freeze independent M60 truth resources BEFORE any case adjudication.

Does not open prediction payloads. Does not use AMRFinder, PGAP, GS arms,
D8/D12 labels, or D20.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from m60_truth_common import (  # noqa: E402
    CASE_RECORDS,
    EVIDENCE,
    EXPECTED_CORE,
    EXPECTED_GIT,
    FINAL,
    REVIEW,
    ROOT as REPO,
    SOURCE,
    TRUTH_ROOT,
    load_cohort_metadata,
    sha256_file,
    utc_now,
    verify_pre_truth_chain,
    write_fasta,
    write_json,
    write_sha256_sidecar,
)

BIN = Path(os.environ.get("M60_TRUTH_BIN", "/home/aritr/micromamba/envs/genome-skeptic-prod/bin"))
FASTA_ORIG = Path("/home/aritr/m60_work/fasta/original")
FAM_SRC = REPO / "src" / "genome_skeptic" / "data" / "target_families"
UA = "GenomeSkeptic-M60-independent-truth/phase3"

PACKAGED_FAMILIES = {
    "tetA_tetracycline_efflux": {"role": "target", "endpoint": "tetA"},
    "mfs_multidrug_efflux": {"role": "competitor", "endpoint": "tetA"},
    "rnd_efflux": {"role": "competitor", "endpoint": "tetA"},
    "rpoB_RNAP_beta": {"role": "target", "endpoint": "rpoB"},
    "rpoC_RNAP_beta_prime": {"role": "competitor", "endpoint": "rpoB"},
}

# Independent Swiss-Prot records (curated). Not M60 case proteins.
UNIPROT_TETA_TARGET = [
    ("P02982", "tetA", "target", "Tn10/plasmid class A TetA tetracycline MFS efflux"),
    ("P02980", "tetB", "target", "Tn10 class B TetB tetracycline MFS efflux"),
]
UNIPROT_TETA_COMPETITOR = [
    ("P0AEY8", "mdfA", "competitor", "E. coli MdfA MFS multidrug efflux"),
    ("P0AEJ0", "emrB", "competitor", "E. coli EmrB MFS multidrug efflux"),
    ("P28246", "bcr", "competitor", "E. coli Bcr MFS bicyclomycin/transport competitor"),
    ("P02983", "tetC", "competitor", "class C tetracycline MFS efflux; not tet(A)/tet(B)"),
    ("P0A0N4", "tetK", "competitor", "TetK tetracycline MFS efflux; not tet(A)/tet(B)"),
    ("P0A0N7", "tetL", "competitor", "TetL tetracycline MFS efflux; not tet(A)/tet(B)"),
    ("P31224", "acrB", "competitor", "E. coli AcrB RND efflux competitor"),
    ("P24177", "acrD", "competitor", "E. coli AcrD RND efflux competitor"),
]
UNIPROT_RPOB = [
    ("P0A8V2", "Escherichia coli", "reviewed E. coli RpoB"),
    ("P9WGY9", "Mycobacterium tuberculosis", "reviewed M. tuberculosis RpoB"),
    ("P37870", "Bacillus subtilis", "reviewed B. subtilis RpoB"),
    ("P21624", "Thermus aquaticus", "reviewed T. aquaticus RpoB"),
    ("P0A2Z6", "Helicobacter pylori", "reviewed H. pylori RpoB"),
    ("Q9WYB5", "Thermotoga maritima", "reviewed T. maritima RpoB"),
    ("P73442", "Synechocystis sp.", "reviewed Synechocystis RpoB"),
    ("O67077", "Aquifex aeolicus", "reviewed A. aeolicus RpoB"),
]
UNIPROT_RPOC = [
    ("P0A8T7", "Escherichia coli", "reviewed E. coli RpoC partner-family competitor"),
]


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def http_bytes(url: str, timeout: int = 60) -> bytes | None:
    req = Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(5):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:
            last = exc
            time.sleep(1.2 * (attempt + 1))
    print(f"WARN fetch failed {url}: {last}", file=sys.stderr)
    return None


def parse_fasta_bytes(data: bytes) -> list[tuple[str, str]]:
    recs = []
    header = None
    chunks: list[str] = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        if line.startswith(">"):
            if header is not None:
                recs.append((header, "".join(chunks)))
            header = line[1:].strip().split()[0]
            chunks = []
        else:
            chunks.append("".join(c for c in line.strip() if not c.isspace()))
    if header is not None:
        recs.append((header, "".join(chunks)))
    return recs


def fetch_uniprot(accession: str) -> dict | None:
    fasta = http_bytes(f"https://rest.uniprot.org/uniprotkb/{accession}.fasta")
    meta = http_bytes(f"https://rest.uniprot.org/uniprotkb/{accession}.json")
    if not fasta:
        return None
    recs = parse_fasta_bytes(fasta)
    if not recs:
        return None
    header, seq = recs[0]
    info = {}
    if meta:
        try:
            info = json.loads(meta.decode("utf-8"))
        except json.JSONDecodeError:
            info = {}
    org = None
    try:
        org = info["organism"]["scientificName"]
    except Exception:
        org = None
    reviewed = None
    try:
        reviewed = info.get("entryType")
    except Exception:
        reviewed = None
    return {
        "accession": accession,
        "header": header,
        "sequence": seq,
        "sequence_sha256": __import__("hashlib").sha256(seq.encode("ascii")).hexdigest(),
        "length_aa": len(seq),
        "organism": org,
        "entry_type": reviewed,
        "source": "UniProt REST uniprotkb/{accession}.fasta",
        "database": "UniProtKB",
        "retrieval_utc": utc_now(),
        "fasta_sha256": __import__("hashlib").sha256(fasta).hexdigest(),
    }


def copy_packaged_family(fid: str) -> dict:
    src = FAM_SRC / fid
    dest = SOURCE / "packaged_families" / fid
    dest.mkdir(parents=True, exist_ok=True)
    copied = {}
    for name in ("members.faa", "members.aln.faa", "family.yaml"):
        p = src / name
        if p.exists():
            out = dest / name
            shutil.copy2(p, out)
            copied[name] = sha256_file(out)
    return {"family_id": fid, "copied": copied, "dest": str(dest)}


def hmmbuild(aln: Path, hmm: Path, log_dir: Path) -> dict:
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(BIN / "hmmbuild"), "--amino", str(hmm), str(aln)]
    proc = run(cmd)
    (log_dir / "hmmbuild.stdout.log").write_text(proc.stdout or "", encoding="utf-8")
    (log_dir / "hmmbuild.stderr.log").write_text(proc.stderr or "", encoding="utf-8")
    ok = proc.returncode == 0 and hmm.exists()
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "ok": ok,
        "hmm_sha256": sha256_file(hmm) if hmm.exists() else None,
    }


def tool_versions() -> dict:
    out = {}
    for name in ("python", "hmmbuild", "hmmsearch", "diamond", "tblastn", "blastp", "FastTree"):
        exe = BIN / name
        if name == "python":
            proc = run([str(exe), "--version"])
        elif name in {"diamond"}:
            proc = run([str(exe), "version"])
        elif name in {"tblastn", "blastp"}:
            proc = run([str(exe), "-version"])
        elif name == "FastTree":
            proc = run([str(exe)])
        else:
            proc = run([str(exe), "-h"])
        text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip().splitlines()
        out[name] = {
            "path": str(exe),
            "exists": exe.exists(),
            "version_line": text[0] if text else None,
        }
    return out


def main() -> int:
    TRUTH_ROOT.mkdir(parents=True, exist_ok=True)
    for d in (SOURCE, EVIDENCE, CASE_RECORDS, REVIEW, FINAL):
        d.mkdir(parents=True, exist_ok=True)
        (d / ".keep").write_text("", encoding="utf-8")

    chain = verify_pre_truth_chain()
    write_json(TRUTH_ROOT / "PRE_TRUTH_CHAIN.json", chain)
    write_sha256_sidecar(TRUTH_ROOT / "PRE_TRUTH_CHAIN.json")
    (TRUTH_ROOT / "PREDICTIONS_LOCKED_BEFORE_TRUTH.txt").write_text("YES\n", encoding="utf-8")

    cases = load_cohort_metadata()
    m60_accessions = {c["accession"] for c in cases}

    packaged = []
    for fid, meta in PACKAGED_FAMILIES.items():
        row = copy_packaged_family(fid)
        row.update(meta)
        packaged.append(row)

    # Independent UniProt freeze
    uniprot_dir = SOURCE / "uniprot"
    uniprot_dir.mkdir(parents=True, exist_ok=True)
    uniprot_records = []

    def add_uniprot(acc: str, gene: str, role: str, note: str, endpoint: str, taxon: str | None = None):
        rec = fetch_uniprot(acc)
        if rec is None:
            uniprot_records.append(
                {
                    "accession": acc,
                    "gene": gene,
                    "role": role,
                    "endpoint": endpoint,
                    "status": "FETCH_FAILED",
                    "provenance_note": note,
                }
            )
            return
        rec.update(
            {
                "gene": gene,
                "role": role,
                "endpoint": endpoint,
                "taxon": taxon or rec.get("organism"),
                "target_or_competitor": role,
                "provenance_note": note,
                "m60_case_protein": False,
                "status": "OK",
            }
        )
        fa = uniprot_dir / f"{acc}.faa"
        write_fasta(fa, [(acc, rec["sequence"])])
        rec["file"] = str(fa.relative_to(TRUTH_ROOT)).replace("\\", "/")
        rec["file_sha256"] = sha256_file(fa)
        uniprot_records.append(rec)

    for acc, gene, role, note in UNIPROT_TETA_TARGET:
        add_uniprot(acc, gene, role, note, "tetA")
    for acc, gene, role, note in UNIPROT_TETA_COMPETITOR:
        add_uniprot(acc, gene, role, note, "tetA")
    for acc, taxon, note in UNIPROT_RPOB:
        add_uniprot(acc, "rpoB", "target", note, "rpoB", taxon=taxon)
    for acc, taxon, note in UNIPROT_RPOC:
        add_uniprot(acc, "rpoC", "competitor", note, "rpoB", taxon=taxon)

    # Combined independent panels (packaged + successfully fetched UniProt)
    def load_faa(path: Path) -> list[tuple[str, str]]:
        recs = []
        header = None
        chunks: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(">"):
                if header is not None:
                    recs.append((header, "".join(chunks)))
                header = line[1:].strip().split()[0]
                chunks = []
            else:
                chunks.append("".join(c for c in line if not c.isspace()))
        if header is not None:
            recs.append((header, "".join(chunks)))
        return recs

    tet_target = load_faa(SOURCE / "packaged_families" / "tetA_tetracycline_efflux" / "members.faa")
    tet_mfs = load_faa(SOURCE / "packaged_families" / "mfs_multidrug_efflux" / "members.faa")
    tet_rnd = load_faa(SOURCE / "packaged_families" / "rnd_efflux" / "members.faa")
    rpob = load_faa(SOURCE / "packaged_families" / "rpoB_RNAP_beta" / "members.faa")
    rpoc = load_faa(SOURCE / "packaged_families" / "rpoC_RNAP_beta_prime" / "members.faa")

    extra_tet_comp = []
    extra_rpob = []
    extra_rpoc = []
    for rec in uniprot_records:
        if rec.get("status") != "OK":
            continue
        item = (rec["accession"], rec["sequence"])
        if rec["endpoint"] == "tetA" and rec["role"] == "competitor" and rec["accession"] not in {x[0] for x in tet_mfs + tet_rnd}:
            extra_tet_comp.append(item)
        if rec["endpoint"] == "rpoB" and rec["role"] == "target" and rec["accession"] not in {x[0] for x in rpob}:
            extra_rpob.append(item)
        if rec["endpoint"] == "rpoB" and rec["role"] == "competitor":
            extra_rpoc.append(item)

    panels = SOURCE / "panels"
    panels.mkdir(parents=True, exist_ok=True)
    panel_hashes = {
        "tetA_target.faa": write_fasta(panels / "tetA_target.faa", tet_target),
        "tetA_competitors.faa": write_fasta(panels / "tetA_competitors.faa", tet_mfs + tet_rnd + extra_tet_comp),
        "rpoB_target.faa": write_fasta(panels / "rpoB_target.faa", rpob + extra_rpob),
        "rpoB_competitors.faa": write_fasta(panels / "rpoB_competitors.faa", rpoc + extra_rpoc),
    }

    hmm_dir = SOURCE / "hmm"
    hmm_dir.mkdir(parents=True, exist_ok=True)
    hmm_rows = {}
    for fid in PACKAGED_FAMILIES:
        aln = SOURCE / "packaged_families" / fid / "members.aln.faa"
        hmm = hmm_dir / f"{fid}.hmm"
        hmm_rows[fid] = hmmbuild(aln, hmm, hmm_dir / fid)

    # Copy M60 assemblies (original RefSeq nucleotide). Not prediction outputs.
    asm_dir = SOURCE / "assemblies"
    asm_dir.mkdir(parents=True, exist_ok=True)
    assemblies = []
    missing_fa = []
    for rec in cases:
        src = FASTA_ORIG / f"{rec['accession']}.fna"
        if not src.exists():
            missing_fa.append(rec["accession"])
            continue
        dest = asm_dir / f"{rec['accession']}.fna"
        shutil.copy2(src, dest)
        assemblies.append(
            {
                "accession": rec["accession"],
                "position": rec["position"],
                "case_id": rec["case_id"],
                "sha256": sha256_file(dest),
                "bytes": dest.stat().st_size,
                "source": str(src),
                "m60_case_used_as_reference": False,
            }
        )
    if missing_fa:
        raise SystemExit(f"missing original assemblies for {missing_fa}")
    if any(a["accession"] not in m60_accessions for a in assemblies):
        raise SystemExit("assembly accession not in frozen M60 cohort")

    allow = {
        "permitted_input_paths": [
            str(TRUTH_ROOT),
            str(SOURCE),
            str(EVIDENCE),
            str(CASE_RECORDS),
            str(REVIEW),
            str(FINAL),
            str(REPO / "manuscript_benchmark" / "M60_COHORT_MANIFEST.json"),
            str(REPO / "src" / "genome_skeptic" / "data" / "target_families"),
            str(FASTA_ORIG),
        ],
        "forbidden_path_parts": [
            "GS_AGENTIC",
            "GS_DETERMINISTIC",
            "GS_EXHAUSTIVE",
            "CONVENTIONAL prediction output",
            "AMRFINDERPLUS",
            "NCBI_REFSEQ_PGAP",
            "manuscript_benchmark/RUNS",
            "POSITION_LOCKS arm JSON",
            "external_validation_agentic_d20",
            "D8/D12 external truth labels",
        ],
        "prediction_payloads_opened": False,
    }
    write_json(SOURCE / "ALLOWED_INPUT_PATHS.json", allow)
    write_sha256_sidecar(SOURCE / "ALLOWED_INPUT_PATHS.json")

    decision_rules = {
        "source": "manuscript_benchmark/M60_PROTOCOL_V1_1.md",
        "tetA_endpoint": "presence of a genuine member of the frozen tet(A)/tet(B) target family",
        "rpoB_endpoint": "presence of a genuine bacterial rpoB orthologue",
        "truth_states": ["POSITIVE", "NEGATIVE", "TRUTH_UNCERTAIN"],
        "do_not_force_uncertain_to_negative": True,
        "do_not_manufacture_negative_rpob_for_class_balance": True,
        "amrfinder_is_not_truth": True,
        "pgap_is_not_truth": True,
        "gs_predictions_are_not_truth": True,
        "gates": {
            "gene_aa_min_identity": 0.60,
            "gene_aa_min_query_coverage": 0.80,
            "gene_length_ratio_min": 0.80,
            "gene_length_ratio_max": 1.20,
            "family_competitive_margin": 0.10,
            "family_competitive_ambiguous_band": 0.05,
            "hmm_min_gate_model_coverage": 0.20,
            "hmm_domain_only_max_model_coverage": 0.45,
            "sequence_decisive_identity_product": 0.70,
            "sequence_decisive_delta": 0.20,
        },
        "tetA_route_1": "target-vs-competitor sequence/reference comparison against frozen tet(A)/tet(B) and competing MFS/RND/tet-class panels",
        "tetA_route_2": "independent HMM profile placement; FastTree family placement when borderline",
        "rpoB_route_1": "full/near-full-length similarity to independently verified RpoB references",
        "rpoB_route_2": "RpoB vs RpoC HMM/profile placement; FastTree when borderline",
        "generic_MFS_insufficient": True,
        "remote_HMM_alone_insufficient": True,
        "two_independent_evidence_routes": True,
        "not_two_independent_reviewers": True,
    }

    manifest = {
        "kind": "M60_TRUTH_SOURCE_MANIFEST",
        "created_utc": utc_now(),
        "freeze_id": "GENOME_SKEPTIC_V4_1_MANUSCRIPT",
        "git_commit": EXPECTED_GIT,
        "scientific_core_hash": EXPECTED_CORE,
        "predictions_locked_before_truth": True,
        "prediction_payloads_opened": False,
        "amrfinder_used_as_truth": False,
        "pgap_used_as_truth": False,
        "d20_touched": False,
        "m60_cases_used_as_references": False,
        "n_cases": 60,
        "software_versions": tool_versions(),
        "packaged_families": packaged,
        "uniprot_records": [
            {
                k: v
                for k, v in rec.items()
                if k != "sequence"
            }
            for rec in uniprot_records
        ],
        "panel_sha256": panel_hashes,
        "hmm": hmm_rows,
        "assemblies": assemblies,
        "decision_rules": decision_rules,
        "do_not_alter_after_this_point": True,
    }
    man_path = SOURCE / "M60_TRUTH_SOURCE_MANIFEST.json"
    # also publish at TRUTH_M60 root as specified
    pub = TRUTH_ROOT / "M60_TRUTH_SOURCE_MANIFEST.json"
    write_json(man_path, manifest)
    shutil.copy2(man_path, pub)
    digest = write_sha256_sidecar(pub)
    write_sha256_sidecar(man_path)
    print(json.dumps({"truth_source_manifest_sha256": digest, "n_assemblies": len(assemblies), "uniprot_ok": sum(1 for r in uniprot_records if r.get("status") == "OK")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
