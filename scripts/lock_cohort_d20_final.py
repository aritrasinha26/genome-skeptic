#!/usr/bin/env python3
"""Gate 1 Steps 3–4: preregistered ambiguity score and final D20 lock.

Uses only frozen V5 solver-derived measurements. No Agentic V2. No truth.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genome_skeptic.config import Settings, load_settings
from genome_skeptic.models import GeneSearchHit, TargetType
from genome_skeptic.validators.homology import strong_hit

OUT = ROOT / "external_validation_agentic_d20"
POOL = OUT / "candidate_pool_manifest.json"
RUNS = OUT / "v5_prescreen"
EXPECTED_POOL = "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c"
EXPECTED_FREEZE = "736bd2bdc34b1967a429602903f26ebfa5cdb031c6787a7f0ebf77926517c696"
SEED = "20260920"
TARGETS = [
    "rpoB_RNAP_beta",
    "tuf_EF_Tu",
    "lacZ_beta_galactosidase",
    "tetA_tetracycline_efflux",
]
ARCH_SET = {
    "close_paralogue",
    "divergent_full_length",
    "domain_only",
    "fusion",
    "biological_split",
    "assembly_fragmented",
}
AMBIGUOUS_MULTI = {
    "ambiguous",
    "unresolved",
    "uncertain",
    "multi_locus_uncertain",
    "copy_number_ambiguous",
    "possible_paralogues",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def execution_hash(target: str, acc: str) -> str:
    return hashlib.sha256(f"D20_EXECUTION|{SEED}|{target}|{acc}".encode("utf-8")).hexdigest()


def as_hit(raw: dict) -> GeneSearchHit | None:
    if not isinstance(raw, dict):
        return None
    try:
        return GeneSearchHit.model_validate(raw)
    except Exception:
        pass
    mapping = {
        "query_id": raw.get("query_id") or raw.get("query") or "",
        "contig_id": raw.get("contig_id") or raw.get("contig") or "",
        "search_kind": raw.get("search_kind") or raw.get("kind") or "translated",
        "identity": float(raw.get("identity") or 0),
        "query_coverage": float(raw.get("query_coverage") or raw.get("coverage") or 0),
        "qstart": int(raw.get("qstart") or 0),
        "qend": int(raw.get("qend") or 0),
        "tstart": int(raw.get("tstart") or 0),
        "tend": int(raw.get("tend") or 0),
        "near_contig_edge": bool(raw.get("near_contig_edge")),
        "possible_edge_truncation": bool(raw.get("possible_edge_truncation")),
        "edge_distance_bp": raw.get("edge_distance_bp"),
        "tool": raw.get("tool"),
    }
    try:
        return GeneSearchHit.model_validate(mapping)
    except Exception:
        return None


def relevant_hits(hits: list[GeneSearchHit]) -> list[GeneSearchHit]:
    aa = [h for h in hits if h.search_kind in {"translated", "protein"}]
    return aa or list(hits)


def best_hit(hits: list[GeneSearchHit]) -> GeneSearchHit | None:
    if not hits:
        return None
    return max(hits, key=lambda h: (h.query_coverage * h.identity, h.alignment_length or 0))


def score_case(snap: dict, settings: Settings) -> dict:
    raw_hits = snap.get("hits") or []
    if isinstance(raw_hits, dict):
        raw_hits = raw_hits.get("hits") or []
    hits = [h for h in (as_hit(x) for x in raw_hits) if h is not None]
    rel = relevant_hits(hits)
    best = best_hit(rel)
    fam = snap.get("family_evidence") or {}
    recon = fam.get("reconstruction") or {}
    multi = snap.get("multiplicity") or recon.get("multiplicity") or {}
    architecture = (snap.get("architecture") or fam.get("architecture") or recon.get("architecture") or "") or ""
    components = []

    id_thr = settings.thresholds.gene_aa_min_identity
    cov_thr = settings.thresholds.gene_aa_min_query_coverage

    n_strong = sum(1 for h in rel if strong_hit(h, settings, TargetType.gene_orthologue))
    if hits and n_strong == 0:
        components.append(
            {
                "points": 2,
                "rule": "candidate_hit_without_strong_hit_gate",
                "source": {"n_hits": len(hits), "n_strong": n_strong},
            }
        )
    else:
        components.append({"points": 0, "rule": "candidate_hit_without_strong_hit_gate", "source": {"n_hits": len(hits), "n_strong": n_strong}})

    ident = None if best is None else float(best.identity)
    if ident is not None and abs(ident - id_thr) <= 0.10:
        components.append({"points": 2, "rule": "identity_near_orthologue_threshold", "source": {"identity": ident, "threshold": id_thr}})
    else:
        components.append({"points": 0, "rule": "identity_near_orthologue_threshold", "source": {"identity": ident, "threshold": id_thr}})

    cov = None if best is None else float(best.query_coverage)
    if cov is not None and abs(cov - cov_thr) <= 0.15:
        components.append({"points": 2, "rule": "coverage_near_orthologue_threshold", "source": {"query_coverage": cov, "threshold": cov_thr}})
    else:
        components.append({"points": 0, "rule": "coverage_near_orthologue_threshold", "source": {"query_coverage": cov, "threshold": cov_thr}})

    if architecture in ARCH_SET:
        components.append({"points": 2, "rule": "challenge_architecture", "source": {"architecture": architecture}})
    else:
        components.append({"points": 0, "rule": "challenge_architecture", "source": {"architecture": architecture}})

    supports = fam.get("supports_orthologue")
    if supports is None:
        supports = snap.get("supports_orthologue")
    homology_detected = n_strong > 0
    claim_detected = (snap.get("final_result") or "") == "target_gene_detected"
    disagree = False
    if supports is not None and bool(supports) != bool(homology_detected):
        disagree = True
    if supports is not None and bool(supports) != bool(claim_detected):
        disagree = True
    cf = recon.get("competitive_family") or fam.get("competitive_family") or snap.get("competitive_family") or {}
    cf_class = cf.get("classification") if isinstance(cf, dict) else None
    competing = cf_class in {"competing_family_preferred", "ambiguous_family"}
    if isinstance(cf, dict) and cf.get("best_competing_family") and cf_class not in {None, "target_family_supported"}:
        competing = True
    if disagree or competing:
        components.append(
            {
                "points": 2,
                "rule": "candidate_vs_family_disagreement_or_competing_family",
                "source": {
                    "supports_orthologue": supports,
                    "homology_detected": homology_detected,
                    "claim_detected": claim_detected,
                    "competitive_family_classification": cf_class,
                    "best_competing_family": cf.get("best_competing_family") if isinstance(cf, dict) else None,
                    "disagree": disagree,
                    "competing": competing,
                },
            }
        )
    else:
        components.append(
            {
                "points": 0,
                "rule": "candidate_vs_family_disagreement_or_competing_family",
                "source": {
                    "supports_orthologue": supports,
                    "homology_detected": homology_detected,
                    "claim_detected": claim_detected,
                    "competitive_family_classification": cf_class,
                    "disagree": disagree,
                    "competing": competing,
                },
            }
        )

    n_loci = multi.get("number_of_candidate_loci")
    classification = (multi.get("classification") or "") if isinstance(multi, dict) else ""
    multi_ambig = False
    if isinstance(n_loci, int) and n_loci > 1:
        multi_ambig = True
    if str(classification).lower() in AMBIGUOUS_MULTI:
        multi_ambig = True
    components.append(
        {
            "points": 1 if multi_ambig else 0,
            "rule": "multiplicity_ambiguous_or_multiple_loci",
            "source": {"number_of_candidate_loci": n_loci, "classification": classification},
        }
    )

    edge = False
    for h in rel:
        if h.near_contig_edge or h.possible_edge_truncation:
            edge = True
            break
    components.append(
        {
            "points": 1 if edge else 0,
            "rule": "contig_edge_or_possible_truncation",
            "source": {
                "any_near_edge": any(h.near_contig_edge for h in rel),
                "any_possible_edge_truncation": any(h.possible_edge_truncation for h in rel),
            },
        }
    )

    tests = snap.get("falsification_tests") or []
    incomplete_cats = []
    for t in tests:
        tid = str(t.get("test_id") or "")
        cat = tid.split(":")[0] if tid else ""
        status = (t.get("status") or "").lower()
        result = (t.get("result") or "").lower()
        incomplete = status in {"skipped", "unresolved", "incomplete", "missing"} or result in {"not_run"}
        if cat and incomplete:
            if cat not in incomplete_cats:
                incomplete_cats.append(cat)
    fal_pts = min(2, len(incomplete_cats))
    components.append(
        {
            "points": fal_pts,
            "rule": "missing_or_incomplete_falsification_category",
            "source": {"incomplete_categories": incomplete_cats, "capped_at": 2},
        }
    )

    claim_class = (snap.get("claim_class") or "").lower()
    weak = claim_class in {"weakened", "unresolved"}
    components.append({"points": 1 if weak else 0, "rule": "v5_claim_weakened_or_unresolved", "source": {"claim_class": claim_class}})

    total = sum(int(c["points"]) for c in components)
    return {"ambiguity_score": total, "components": components}


def main() -> None:
    freeze = ROOT / "agentic_freeze" / "GENOME_SKEPTIC_AGENTIC_V2_D20_manifest.json"
    if sha256_file(freeze) != EXPECTED_FREEZE:
        raise SystemExit("freeze hash mismatch")
    if sha256_file(POOL) != EXPECTED_POOL:
        raise SystemExit("candidate pool hash mismatch")
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    settings = load_settings(ROOT / "config" / "qwen_external_v5.yaml")
    cases = []
    for rec in pool["candidates"]:
        acc = rec["assembly_accession"]
        target = rec["target"]
        snap_path = RUNS / acc / target / "v5_case.json"
        if not snap_path.exists():
            raise SystemExit(f"missing V5 snapshot {acc} {target}")
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        scored = score_case(snap, settings)
        cases.append({**rec, **snap, **scored})

    amb_path = OUT / "candidate_ambiguity_scores.json"
    amb_blob = {
        "kind": "d20_candidate_ambiguity_scores",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(cases),
        "score_modified_after_inspection": False,
        "external_labels_opened": False,
        "cases": [
            {
                "assembly_accession": c["assembly_accession"],
                "target": c["target"],
                "genus": c.get("genus"),
                "species": c.get("species"),
                "assembly_quality": c.get("assembly_quality"),
                "sampling_hash": c["sampling_hash"],
                "ambiguity_score": c["ambiguity_score"],
                "components": c["components"],
                "m0_hash": c.get("m0_hash"),
                "v5_claim_class": c.get("claim_class"),
                "v5_architecture": c.get("architecture"),
            }
            for c in cases
        ],
    }
    amb_path.write_text(json.dumps(amb_blob, indent=2) + "\n", encoding="utf-8")

    protocol = {
        "kind": "D20_SELECTION_PROTOCOL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V2_D20",
        "agentic_freeze_manifest_sha256": EXPECTED_FREEZE,
        "candidate_pool_manifest_sha256": EXPECTED_POOL,
        "seed": SEED,
        "ambiguity_score_preregistered": True,
        "ambiguity_rules": [
            {"points": 2, "rule": "candidate hit exists but no hit satisfies the frozen strong-hit gate"},
            {"points": 2, "rule": "best relevant identity within ±0.10 of frozen orthologue identity threshold"},
            {"points": 2, "rule": "best relevant query coverage within ±0.15 of frozen coverage threshold"},
            {"points": 2, "rule": "architecture in close_paralogue/divergent_full_length/domain_only/fusion/biological_split/assembly_fragmented"},
            {"points": 2, "rule": "candidate vs family/orthology disagreement or competing-family interpretation"},
            {"points": 1, "rule": "more than one candidate locus or multiplicity/copy-number ambiguous"},
            {"points": 1, "rule": "relevant hit near contig edge or possible_edge_truncation"},
            {"points": "+1 per missing/incomplete falsification category, max +2"},
            {"points": 1, "rule": "V5 final claim class weakened or unresolved"},
        ],
        "identity_threshold": settings.thresholds.gene_aa_min_identity,
        "coverage_threshold": settings.thresholds.gene_aa_min_query_coverage,
        "within_target_complete_n": 3,
        "within_target_draft_n": 2,
        "tie_break": "original deterministic sampling hash ascending",
        "genus_rule": "prefer 20 distinct genera; if collision, take next-highest ambiguity candidate",
        "execution_order": 'SHA256("D20_EXECUTION|20260920|<target>|<assembly_accession>") ascending',
        "score_modified_after_inspection": False,
        "external_labels_opened": False,
    }

    by_target: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        by_target[case["target"]].append(case)

    selected: list[dict] = []
    replacements: list[dict] = []

    def ranked(pool_cases: list[dict]) -> list[dict]:
        return sorted(pool_cases, key=lambda c: (-int(c["ambiguity_score"]), c["sampling_hash"], c["assembly_accession"]))

    remaining: dict[tuple[str, str], list[dict]] = {}
    tentative: list[dict] = []
    for target in TARGETS:
        pool_cases = by_target[target]
        complete = [c for c in pool_cases if c.get("assembly_quality") == "complete_or_chromosome"]
        draft = [c for c in pool_cases if c.get("assembly_quality") == "scaffold_or_contig"]
        for label, rows, n in (
            ("complete_or_chromosome", complete, 3),
            ("scaffold_or_contig", draft, 2),
        ):
            order = ranked(rows)
            if len(order) < n:
                raise SystemExit(f"underfilled {target} {label}: {len(order)}/{n}")
            picked = order[:n]
            remaining[(target, label)] = order[n:]
            for i, cand in enumerate(picked, start=1):
                cand["selection_rank"] = i
                cand["selection_stratum"] = label
            tentative.extend(picked)

    def rank_key(c: dict) -> tuple:
        return (-int(c["ambiguity_score"]), c["sampling_hash"], c["assembly_accession"])

    changed = True
    while changed:
        changed = False
        by_genus: dict[str, list[dict]] = defaultdict(list)
        for cand in tentative:
            genus = cand.get("genus") or ""
            if genus:
                by_genus[genus].append(cand)
        for genus, group in by_genus.items():
            if len(group) < 2:
                continue
            keep = sorted(group, key=rank_key)[0]
            for loser in sorted(group, key=rank_key)[1:]:
                slot = (loser["target"], loser["selection_stratum"])
                used = {(c.get("genus") or "") for c in tentative if c["assembly_accession"] != loser["assembly_accession"]}
                replacement = None
                for cand in remaining.get(slot, []):
                    g = cand.get("genus") or ""
                    if g and g in used:
                        continue
                    if cand["assembly_accession"] in {x["assembly_accession"] for x in tentative}:
                        continue
                    replacement = cand
                    break
                if replacement is None:
                    continue
                remaining[slot] = [c for c in remaining.get(slot, []) if c["assembly_accession"] != replacement["assembly_accession"]]
                replacements.append(
                    {
                        "target": loser["target"],
                        "stratum": loser["selection_stratum"],
                        "reason": "genus_collision_replaced_with_next_highest_ambiguity",
                        "replaced": loser["assembly_accession"],
                        "replaced_genus": genus,
                        "chosen": replacement["assembly_accession"],
                        "chosen_genus": replacement.get("genus"),
                        "replaced_ambiguity": loser["ambiguity_score"],
                        "chosen_ambiguity": replacement["ambiguity_score"],
                    }
                )
                tentative = [c for c in tentative if c["assembly_accession"] != loser["assembly_accession"]]
                replacement["selection_stratum"] = loser["selection_stratum"]
                tentative.append(replacement)
                changed = True
                break
            if changed:
                break

    leftover_genera: dict[str, list[str]] = defaultdict(list)
    for cand in tentative:
        leftover_genera[cand.get("genus") or ""].append(cand["assembly_accession"])
    for genus, accs in leftover_genera.items():
        if genus and len(accs) > 1:
            replacements.append(
                {
                    "reason": "genus_collision_could_not_be_avoided_without_underfilling_quota",
                    "genus": genus,
                    "accessions": accs,
                }
            )

    by_slot: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for cand in tentative:
        by_slot[(cand["target"], cand["selection_stratum"])].append(cand)
    selected = []
    for target in TARGETS:
        for label, n in (("complete_or_chromosome", 3), ("scaffold_or_contig", 2)):
            rows = ranked(by_slot[(target, label)])
            if len(rows) != n:
                raise SystemExit(f"final underfill {target} {label}: {len(rows)}/{n}")
            for i, cand in enumerate(rows, start=1):
                cand["selection_rank"] = i
                cand["selection_stratum"] = label
            selected.extend(rows)

    selected.sort(key=lambda c: (execution_hash(c["target"], c["assembly_accession"]), c["assembly_accession"]))
    for i, rec in enumerate(selected, start=1):
        rec["execution_position"] = i
        rec["execution_hash"] = execution_hash(rec["target"], rec["assembly_accession"])
        rec["frozen_v5_prediction_reference"] = str((RUNS / rec["assembly_accession"] / rec["target"] / "v5_case.json").relative_to(ROOT)).replace("\\", "/")

    protocol["genus_replacements"] = replacements
    proto_path = OUT / "D20_SELECTION_PROTOCOL.json"
    proto_path.write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")

    final_rows = []
    v5_locked = []
    for rec in selected:
        final_rows.append(
            {
                "execution_position": rec["execution_position"],
                "assembly_accession": rec["assembly_accession"],
                "organism": rec.get("organism"),
                "genus": rec.get("genus"),
                "species": rec.get("species"),
                "target": rec["target"],
                "release_date": rec.get("release_date"),
                "assembly_level": rec.get("assembly_level"),
                "assembly_quality": rec.get("assembly_quality"),
                "fasta_sha256": rec.get("fasta_sha256"),
                "sampling_hash": rec.get("sampling_hash"),
                "execution_hash": rec["execution_hash"],
                "ambiguity_score": rec["ambiguity_score"],
                "ambiguity_score_components": rec["components"],
                "selection_rank": rec["selection_rank"],
                "selection_stratum": rec["selection_stratum"],
                "frozen_v5_prediction_reference": rec["frozen_v5_prediction_reference"],
                "frozen_m0_hash": rec.get("m0_hash"),
                "v5_final_result": rec.get("final_result"),
                "v5_claim_class": rec.get("claim_class"),
                "v5_confidence": rec.get("confidence"),
                "v5_architecture": rec.get("architecture"),
            }
        )
        v5_locked.append(
            {
                "execution_position": rec["execution_position"],
                "assembly_accession": rec["assembly_accession"],
                "target": rec["target"],
                "fasta_sha256": rec.get("fasta_sha256"),
                "m0_hash": rec.get("m0_hash"),
                "final_result": rec.get("final_result"),
                "claim_class": rec.get("claim_class"),
                "confidence": rec.get("confidence"),
                "architecture": rec.get("architecture"),
                "multiplicity": rec.get("multiplicity"),
                "homology_support": rec.get("homology_support"),
                "orthology_class": rec.get("orthology_class"),
                "statement": rec.get("statement"),
                "falsification_tests": rec.get("falsification_tests"),
                "runtime_seconds": rec.get("runtime_seconds"),
                "prediction_reference": rec["frozen_v5_prediction_reference"],
            }
        )

    final_manifest = {
        "kind": "D20_FINAL_MANIFEST",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V2_D20",
        "agentic_freeze_manifest_sha256": EXPECTED_FREEZE,
        "candidate_pool_manifest_sha256": EXPECTED_POOL,
        "n_final_cases": len(final_rows),
        "target_counts": {t: sum(1 for r in final_rows if r["target"] == t) for t in TARGETS},
        "assembly_quality_counts": {
            "complete_or_chromosome": sum(1 for r in final_rows if r["assembly_quality"] == "complete_or_chromosome"),
            "scaffold_or_contig": sum(1 for r in final_rows if r["assembly_quality"] == "scaffold_or_contig"),
        },
        "n_unique_genomes": len({r["assembly_accession"] for r in final_rows}),
        "n_unique_species": len({r["species"] for r in final_rows}),
        "n_unique_genera": len({r["genus"] for r in final_rows}),
        "external_labels_opened": False,
        "agentic_v2_executed": False,
        "planner_called": False,
        "critic_called": False,
        "conventional_executed": False,
        "cases": final_rows,
    }
    final_json = OUT / "D20_FINAL_MANIFEST.json"
    final_json.write_text(json.dumps(final_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    final_csv = OUT / "D20_FINAL_MANIFEST.csv"
    fields = [
        "execution_position", "assembly_accession", "organism", "genus", "species", "target",
        "release_date", "assembly_level", "fasta_sha256", "sampling_hash", "ambiguity_score",
        "selection_rank", "frozen_m0_hash",
    ]
    with final_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in final_rows:
            w.writerow(row)

    v5_path = OUT / "D20_V5_PREDICTIONS_LOCKED.json"
    v5_blob = {
        "kind": "D20_V5_PREDICTIONS_LOCKED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(v5_locked),
        "frozen_agentic_version": "GENOME_SKEPTIC_AGENTIC_V2_D20",
        "do_not_regenerate": True,
        "predictions": v5_locked,
    }
    v5_path.write_text(json.dumps(v5_blob, indent=2, default=str) + "\n", encoding="utf-8")

    hashes = {}
    for path in (proto_path, final_json, final_csv, v5_path):
        digest = sha256_file(path)
        hashes[path.name] = digest
        (OUT / f"{path.name}.sha256.json").write_text(
            json.dumps({"file": path.name, "sha256": digest, "hashed_utc": datetime.now(timezone.utc).isoformat()}, indent=2)
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "n_final": len(final_rows),
        "unique_genomes": final_manifest["n_unique_genomes"],
        "unique_species": final_manifest["n_unique_species"],
        "unique_genera": final_manifest["n_unique_genera"],
        "quality": final_manifest["assembly_quality_counts"],
        "targets": final_manifest["target_counts"],
        "hashes": hashes,
    }, indent=2))


if __name__ == "__main__":
    main()
