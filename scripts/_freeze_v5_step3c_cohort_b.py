#!/usr/bin/env python3
"""STEP 3C Cohort B: freeze sampling protocol only. Do not select genomes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation"

V5_FREEZE = "0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b"
INV_HASH = "b82969ad6e4e3e5a134ea831a0370d32b19612f9440b71d6ad8fbd03a3467e85"
CONTRACT = "d224b8b829b3a46c03e42aae324062b7ff72c75d2b6906a0cab45618818f9cb9"
EXCL_HASH = "205d468d98090bca51099785407d8df004cb97f04603bd93f5521e63484ddf80"
INPUT_HASH = "6d99f26208175a5f7a77017d3d99461ed4c75d333930622059ed01c9b18d0978"
CREATED = "2026-09-18T22:45:00+00:00"
SEED = 20260918

PROTOCOL = {
    "kind": "cohort_B_sampling_protocol",
    "created_utc": CREATED,
    "model": "qwen3:4b",
    "genome_skeptic_v5_freeze_hash": V5_FREEZE,
    "target_inventory_sha256": INV_HASH,
    "scoring_contract_sha256": CONTRACT,
    "provenance_exclusion_sha256": EXCL_HASH,
    "input_policy_sha256": INPUT_HASH,
    "scientific_logic_modified": False,
    "scoring_contract_modified": False,
    "genomes_selected": False,
    "external_truth_labels_generated": False,
    "genome_skeptic_executed": False,
    "purpose": "Prospectively define how an automated selector will later use external labels without exposing them to Genome Skeptic. No Cohort B genomes are chosen in STEP 3C.",
    "seed": SEED,
    "label_store": {
        "agent_visible": False,
        "location": "scorer_only / hidden; never copied into agent_visible FASTA, headers, sidecars, or prompts",
        "selector_may_read_labels": True,
        "genome_skeptic_may_read_labels": False,
    },
    "forbidden_as_genome_skeptic_inference_inputs": [
        "PGAP GFF/GTF",
        "GenBank feature tables",
        "AMRFinderPlus output",
        "AMRFinderPlus HMM profiles",
        "AMRFinderPlus reference sequences",
        "AMRFinderPlus curated thresholds",
        "AMRFinderPlus gene hierarchy rules",
        "MicroBIGG-E calls",
        "external gene names in sidecar metadata",
        "external reference labels",
        "eggNOG/OMA/NCBI-Gene-ortholog assignments",
    ],
    "when_labels_may_be_retrieved": "Only after Genome Skeptic predictions for that genome are SHA256-locked.",
    "ambiguous_never_silently_converted": True,
    "v5_orthology_resource_audit": {
        "v5_used": [
            "internal curated family member FASTA (UniProt/RefSeq proteins listed in family.yaml)",
            "star MSA + hmmbuild/hmmsearch of those internal members",
            "BLAST/internal gene_search homology",
            "optional FastTree placement when cheaper evidence is ambiguous",
            "internal reciprocal-best-hit against user-provided reference proteins (src/genome_skeptic/locus/orthology.py)",
            "documented Pfam/InterPro domain names on rpoB/rpoC yaml as architecture documentation, not Pfam HMMER scores from those databases",
        ],
        "v5_did_not_use": [
            "eggNOG / eggNOG-mapper",
            "OMA",
            "OrthoDB",
            "OrthoFinder precomputed datasets",
            "KEGG KO / Kofam",
            "COG/arCOG databases as an external gold standard",
            "NCBI Gene Orthologs API",
            "AMRFinderPlus HMMs, sequences, thresholds, hierarchy rules, or calls",
            "MicroBIGG-E",
        ],
        "audit_method": "repository grep of frozen V5 source, family yaml, and v5_freeze_manifest.json; no eggNOG/OMA/OrthoDB/KO callers exist in src/genome_skeptic",
        "independent_orthology_resources_permitted_as_post_hoc_labels_only": [
            "NCBI Gene Orthologs (NCBI Datasets gene ortholog summaries keyed from frozen seed protein accessions / frozen gene_ids)",
            "eggNOG 5.0 NOG/COG assignments computed independently after prediction lock",
        ],
        "pgap_gene_symbol_equality_is_not_orthology": True,
        "pgap_role": "corroborating evidence after lock, never a sole orthology standard and never a Genome Skeptic input",
    },
    "strata": {
        "tetA_tetracycline_efflux": {
            "primary_endpoint": "FAMILY",
            "independent_label_source": "AMRFinderPlus / MicroBIGG-E isolate-level presence calls after prediction lock",
            "do_not_use_amrfinderplus_hmms_sequences_or_thresholds_as_gs_inputs": True,
            "categories": {
                "POSITIVE": "independent AMRFinderPlus presence call of tet(A) OR tet(B), consistent with the frozen two-member family (P02982 TetA/TCR1 and P02980 Tn10 class B). Complete non-pseudo only.",
                "RELATED_BUT_NON_TARGET": [
                    "tet(C)",
                    "tet(D)",
                    "other tetracycline MFS classes not among the two frozen members",
                    "ABC tetA(*) subunits",
                    "tet_A_B_C_D parent-only without tet(A) or tet(B)",
                ],
                "NEGATIVE": "no tet(A), no tet(B), and no other complete frozen-member-equivalent tetracycline MFS efflux evidence under the frozen scoring-contract rules",
                "AMBIGUOUS": "pseudogene, partial, unrejoined fragments, parent-only unresolved class, or conflicting tet(A)/tet(B) assignment on one locus",
            },
            "sampling_after_this_protocol_is_frozen": {
                "n_POSITIVE_target": 8,
                "n_RELATED_BUT_NON_TARGET_target": 8,
                "n_NEGATIVE_target": 8,
                "n_AMBIGUOUS_in_scored_set": 0,
                "ambiguous_bin": "keep separately; never convert to POSITIVE, RELATED, or NEGATIVE",
                "exclude_provenance_exclusions": True,
                "selector_seed": SEED,
            },
        },
        "mfs_multidrug_efflux": {
            "primary_endpoint": "FAMILY",
            "status": "REQUIRES_ADJUDICATION",
            "reason": "No sufficiently independent family-level gold standard equals the frozen three-member competitor panel (MdfA+EmrB+Bcr). AMRFinderPlus has only related MFS_efflux/emrB nodes. PGAP gene-name union is not an independent family definition and is not orthology.",
            "do_not_invent_external_gold_standard": True,
            "do_not_force_binary_labels": True,
            "genomes_not_auto_selected_for_this_stratum": True,
        },
        "rnd_efflux": {
            "primary_endpoint": "FAMILY",
            "status": "REQUIRES_ADJUDICATION",
            "reason": "Frozen family is AcrB+AcrD. AMRFinderPlus catalogs acrB POINT alleles, not presence. PGAP acrB/acrD symbols are not an independent family-level gold standard.",
            "do_not_invent_external_gold_standard": True,
            "do_not_force_binary_labels": True,
            "do_not_use_amrfinderplus_point_alleles_as_presence_labels": True,
            "genomes_not_auto_selected_for_this_stratum": True,
        },
        "housekeeping_and_accessory_orthologues": {
            "targets": [
                "recA_recombinase",
                "tuf_EF_Tu",
                "lacZ_beta_galactosidase",
                "rpoB_RNAP_beta",
                "rpoC_RNAP_beta_prime",
            ],
            "procedure_defined_before_genome_selection": True,
            "independent_orthology_procedure": {
                "step_1": "After prediction lock, retrieve the NCBI Gene Ortholog group for each frozen seed protein (recA NP_417179.1; tuf NP_418240.1; lacZ NP_414878.1; rpoB NP_418414.1 / gene_id 948488; rpoC NP_418415.1 / gene_id 948489).",
                "step_2": "Independently map proteins of the locked genome to that ortholog group via NCBI Datasets Gene Orthologs. Optionally corroborate with eggNOG 5.0 NOG membership of the same seed proteins. Neither resource was used in V5 development.",
                "step_3": "Use RefSeq/PGAP gene symbols only as corroboration, never as the sole orthology decision.",
                "step_4": "If NCBI Gene Orthologs do not cover the taxon and eggNOG was not applied, do not infer absence; assign AMBIGUOUS or REQUIRES_ADJUDICATION.",
            },
            "categories": {
                "POSITIVE": "independent ortholog-group membership for the frozen target AND a complete non-pseudo CDS. For tuf_EF_Tu, presence is secondary; multiplicity uses the count of distinct complete ortholog-group intervals (tufA and tufB both count as EF-Tu copies).",
                "RELATED_BUT_NON_TARGET": "same superfamily/NOG neighborhood but not the seed ortholog group (e.g. radA vs recA; ebgA/bglX vs lacZ; rpoA vs rpoB; other RNAP subunits).",
                "NEGATIVE": "the independent ortholog resource was successfully applied to that genome and returned no member of the seed ortholog group and no complete corroborating CDS of that group.",
                "AMBIGUOUS": "PGAP gene-symbol match without ortholog-group assignment; ortholog-group hit that is pseudo/partial/unrejoined; conflicting NCBI-Gene vs eggNOG calls; taxon not covered by the ortholog resource.",
            },
            "sampling_after_this_protocol_is_frozen": {
                "per_target_n_POSITIVE_target": 6,
                "per_target_n_NEGATIVE_target": 6,
                "per_target_n_RELATED_BUT_NON_TARGET_target": 4,
                "n_AMBIGUOUS_in_scored_set": 0,
                "tuf_additional_multiplicity_stratum": "among POSITIVE genomes, prefer a mix of single-copy vs multi-copy EF-Tu interval counts using independent ortholog/PGAP interval counts after lock, without exposing those counts to Genome Skeptic",
                "rpoB_rpoC_architecture_stratum": "if independent annotation marks rpoBC fusion vs split vs canonical separate genes, record as LOCUS_ARCHITECTURE labels after lock; do not select genomes by peeking at those labels before this protocol is executed in a later step",
                "selector_seed": SEED,
                "exclude_provenance_exclusions": True,
            },
        },
    },
    "automated_selector_algorithm": {
        "not_executed_in_step_3c": True,
        "order": [
            "Read this frozen protocol and the frozen provenance exclusion list.",
            "Do not run Genome Skeptic and do not write agent-visible labels.",
            "Query public isolate-level AMRFinderPlus/MicroBIGG-E call tables for tet(A)/tet(B) and related tet genes only as selector-side labels.",
            "Query NCBI Gene Orthologs for housekeeping/accessory seeds only as selector-side labels.",
            "Assign POSITIVE / RELATED_BUT_NON_TARGET / NEGATIVE / AMBIGUOUS per the strata above.",
            "Leave AMBIGUOUS in an unscored bin; never convert.",
            "Skip mfs_multidrug_efflux and rnd_efflux auto-label strata (REQUIRES_ADJUDICATION).",
            "Drop every accession/taxid/organism in the frozen provenance exclusions.",
            "Within each remaining category, shuffle with seed 20260918 salted by target+category, then take the target N distinct species.",
            "Write cohort_B_genome_manifest.json with assembly metadata only in the agent-visible copy; store labels only in scorer_only.",
            "Download FASTA only after that later manifest is frozen; sanitize headers; then run frozen V5.",
        ],
    },
    "label_and_prediction_freeze_sequence": [
        "1. Freeze cohort manifest",
        "2. Download genome FASTA only",
        "3. Sanitize FASTA headers if annotation-bearing",
        "4. Run frozen Genome Skeptic V5",
        "5. Save all predictions, evidence IDs, confidence values and classifications",
        "6. Compute SHA256 of prediction output",
        "7. Mark predictions LOCKED",
        "8. Only after prediction lock: retrieve/reveal external annotations and reference labels",
        "9. Score according to the already-frozen scoring contract",
        "10. Preserve every disagreement. No rerunning an individual genome after its external label becomes known",
    ],
}


def main() -> None:
    dest = OUT / "cohort_B_sampling_protocol.json"
    dest.write_text(json.dumps(PROTOCOL, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    (OUT / "cohort_B_sampling_protocol.sha256.json").write_text(
        json.dumps({"file": "cohort_B_sampling_protocol.json", "sha256": digest}, indent=2) + "\n",
        encoding="utf-8",
    )
    a = OUT / "cohort_A_naturalistic_manifest.json"
    a_hash = hashlib.sha256(a.read_bytes()).hexdigest()
    (OUT / "cohort_A_naturalistic_manifest.sha256.json").write_text(
        json.dumps({"file": "cohort_A_naturalistic_manifest.json", "sha256": a_hash}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"cohort_A": a_hash, "cohort_B": digest}, indent=2))


if __name__ == "__main__":
    main()
