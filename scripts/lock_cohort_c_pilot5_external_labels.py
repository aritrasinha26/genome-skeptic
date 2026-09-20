#!/usr/bin/env python3
"""Write and hash Cohort C pilot5 external labels. Does not read predictions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "external_validation_agentic"
DEST = OUT / "cohort_C_pilot5_external_labels_locked.jsonl"

LABELS = [
    {
        "frozen_execution_position": 1,
        "assembly": "GCF_055394735.1",
        "organism": "Desulfatiglans parachlorophenolica",
        "taxid": 1261393,
        "biosample": "SAMD00887385",
        "target": "rpoB_RNAP_beta",
        "reference_class": "POSITIVE",
        "reference_source": (
            "NCBI Gene Orthologs seed rpoB NP_418414.1 / gene_id 948488; "
            "eggNOG 5.0 NOG COG0085 of UniProt P0A8V2; "
            "independent post-lock phmmer of the frozen seed against all proteins of this assembly; "
            "PGAP gene symbol used only as corroboration"
        ),
        "reference_identifiers": [
            "seed_protein:NP_418414.1",
            "seed_gene_id:948488",
            "eggnog5_seed_NOG:COG0085",
            "WP_464229829.1",
            "locus_tag:ACZ500_RS23400",
            "pgap_symbol:rpoB",
        ],
        "short_rationale": (
            "NCBI Gene Orthologs does not index taxid 1261393, and eggNOG 5 precomputed bacterial members "
            "do not include this taxid. Independent mapping of all proteins of GCF_055394735.1 to the frozen "
            "seed NP_418414.1 (eggNOG 5 COG0085) by phmmer produced a complete non-pseudo hit WP_464229829.1 "
            "(E=0, seed coverage 8-1340/1342, protein length 1370). PGAP symbol rpoB corroborates. "
            "A second weaker DNA-directed RNA polymerase subunit beta protein (WP_464232666.1, domain-partial) "
            "is related but not required for the POSITIVE call."
        ),
        "pgap_used_as_sole_truth": False,
        "other_cohort_C_cases_inspected": False,
    },
    {
        "frozen_execution_position": 2,
        "assembly": "GCF_055394735.1",
        "organism": "Desulfatiglans parachlorophenolica",
        "taxid": 1261393,
        "biosample": "SAMD00887385",
        "target": "tuf_EF_Tu",
        "reference_class": "POSITIVE",
        "reference_source": (
            "NCBI Gene Orthologs for authentic E. coli tufA gene_id 947838 / NP_417798.1 / UniProt P0CE47; "
            "eggNOG 5.0 NOG COG0050; independent post-lock phmmer of tufA against all proteins of this assembly; "
            "PGAP gene symbol used only as corroboration. "
            "The written V5 protocol listed NP_418240.1 as the tuf seed; the current NCBI record for NP_418240.1 "
            "is not EF-Tu, so labels follow the named target tuf_EF_Tu and NCBI tufA/EF-Tu orthology."
        ),
        "reference_identifiers": [
            "seed_protein:NP_417798.1",
            "seed_gene_id:947838",
            "seed_symbol:tufA",
            "uniprot:P0CE47",
            "eggnog5_seed_NOG:COG0050",
            "WP_464229820.1",
            "locus_tag:ACZ500_RS23355",
            "locus_tag:ACZ500_RS23420",
            "pgap_symbol:tuf",
        ],
        "short_rationale": (
            "NCBI Gene Orthologs does not index taxid 1261393. Independent phmmer of authentic tufA NP_417798.1 "
            "(eggNOG 5 COG0050) against all proteins of this assembly found complete non-pseudo EF-Tu "
            "WP_464229820.1 (E=7.5e-208, seed coverage 1-393/394, protein length 397). PGAP annotates two "
            "complete tuf loci with that same protein accession. selB and other translational GTPases are "
            "related but not the seed ortholog."
        ),
        "pgap_used_as_sole_truth": False,
        "other_cohort_C_cases_inspected": False,
    },
    {
        "frozen_execution_position": 3,
        "assembly": "GCF_055394735.1",
        "organism": "Desulfatiglans parachlorophenolica",
        "taxid": 1261393,
        "biosample": "SAMD00887385",
        "target": "lacZ_beta_galactosidase",
        "reference_class": "NEGATIVE",
        "reference_source": (
            "NCBI Gene Orthologs seed lacZ NP_414878.1 / gene_id 945006; "
            "eggNOG 5.0 NOG COG3250 of UniProt P00722; "
            "independent post-lock phmmer of the frozen seed against all proteins of this assembly; "
            "PGAP used only as corroboration"
        ),
        "reference_identifiers": [
            "seed_protein:NP_414878.1",
            "seed_gene_id:945006",
            "eggnog5_seed_NOG:COG3250",
            "uniprot:P00722",
        ],
        "short_rationale": (
            "NCBI Gene Orthologs does not index taxid 1261393, and eggNOG 5 precomputed members do not include "
            "this taxid. The independent ortholog mapping was still applied: phmmer of frozen lacZ seed "
            "NP_414878.1 (eggNOG 5 COG3250) against all proteins of this assembly at E<=1e-5 returned no hits. "
            "PGAP has no lacZ symbol and no beta-galactosidase product. Glycoside hydrolase families 5/9/94 are "
            "present and are not the lacZ/GH2 seed ortholog group."
        ),
        "pgap_used_as_sole_truth": False,
        "other_cohort_C_cases_inspected": False,
    },
    {
        "frozen_execution_position": 4,
        "assembly": "GCF_055394735.1",
        "organism": "Desulfatiglans parachlorophenolica",
        "taxid": 1261393,
        "biosample": "SAMD00887385",
        "target": "tetA_tetracycline_efflux",
        "reference_class": "NEGATIVE",
        "reference_source": (
            "AMRFinderPlus external call as published on this RefSeq assembly "
            "(PGAP AMR gene annotation uses AMRFinderPlus); "
            "frozen positive family = tet(A) OR tet(B)"
        ),
        "reference_identifiers": [],
        "short_rationale": (
            "NCBI Datasets annotation_report searches for symbols tetA/tetB and text tet(A), tet(B), and "
            "tetracycline returned no features. The RefSeq GBFF contains no AMRFinderPlus string and no "
            "tet(A)/tet(B)/tetracycline-efflux gene. Competing RND/MATE/CDF efflux proteins are present "
            "without tet(A) or tet(B) and are true negatives for this frozen two-member family, not tet(C) "
            "RELATED_BUT_NON_TARGET calls."
        ),
        "pgap_used_as_sole_truth": False,
        "other_cohort_C_cases_inspected": False,
    },
    {
        "frozen_execution_position": 5,
        "assembly": "GCF_055378285.1",
        "organism": "Desulfurispirillum alkaliphilum",
        "taxid": 393030,
        "biosample": "SAMD00887306",
        "target": "rpoB_RNAP_beta",
        "reference_class": "POSITIVE",
        "reference_source": (
            "NCBI Gene Orthologs seed rpoB NP_418414.1 / gene_id 948488; "
            "eggNOG 5.0 NOG COG0085 of UniProt P0A8V2; "
            "independent post-lock phmmer of the frozen seed against all proteins of this assembly; "
            "PGAP gene symbol used only as corroboration"
        ),
        "reference_identifiers": [
            "seed_protein:NP_418414.1",
            "seed_gene_id:948488",
            "eggnog5_seed_NOG:COG0085",
            "WP_464280409.1",
            "locus_tag:ACZ46I_RS07535",
            "pgap_symbol:rpoB",
        ],
        "short_rationale": (
            "NCBI Gene Orthologs does not index taxid 393030, and eggNOG 5 precomputed bacterial members "
            "do not include this taxid. Independent phmmer of frozen seed NP_418414.1 against all proteins "
            "of GCF_055378285.1 produced complete non-pseudo hit WP_464280409.1 (E=0, score 1585, length 1347, "
            "seed coverage spanning 10-1339/1342). PGAP symbol rpoB corroborates. rpoC is present as a related "
            "RNAP subunit and is not this target."
        ),
        "pgap_used_as_sole_truth": False,
        "other_cohort_C_cases_inspected": False,
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> None:
    if [r["frozen_execution_position"] for r in LABELS] != [1, 2, 3, 4, 5]:
        raise SystemExit("positions")
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in LABELS]
    DEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    digest = sha256_file(DEST)
    sidecar = OUT / "cohort_C_pilot5_external_labels_locked.sha256.json"
    sidecar.write_text(
        json.dumps(
            {
                "file": "cohort_C_pilot5_external_labels_locked.jsonl",
                "sha256": digest,
                "hashed_utc": datetime.now(timezone.utc).isoformat(),
                "hashed_before_prediction_comparison": True,
                "n_cases": 5,
                "other_cohort_C_cases_inspected": False,
                "prediction_files_not_used_to_assign_labels": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("LABELS_LOCKED", digest)


if __name__ == "__main__":
    main()
