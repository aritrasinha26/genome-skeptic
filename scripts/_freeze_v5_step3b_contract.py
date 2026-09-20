#!/usr/bin/env python3
"""STEP 3B: freeze scoring contract, provenance exclusions, and input policy.

Does not select isolates, inspect per-isolate labels, run Genome Skeptic,
or modify V5 scientific logic.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation"

V5_FREEZE = "0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b"
INV_HASH = "b82969ad6e4e3e5a134ea831a0370d32b19612f9440b71d6ad8fbd03a3467e85"
OVL_HASH = "1ce6e871e1bf20441e54c76bc6bbe90f7066201574ffcaaef6cde8095fbcbc59"
CREATED = "2026-09-18T22:30:00+00:00"
MODEL = "qwen3:4b"

COMMON = {
    "genome_skeptic_v5_freeze_hash": V5_FREEZE,
    "target_inventory_sha256": INV_HASH,
    "external_reference_overlap_sha256": OVL_HASH,
    "created_utc": CREATED,
    "model": MODEL,
    "scientific_logic_modified": False,
    "isolates_selected": False,
    "per_isolate_labels_inspected": False,
    "genome_skeptic_executed": False,
}

AMBIGUOUS_GLOBAL = (
    "AMBIGUOUS cases must not silently become positives or negatives. "
    "They are excluded from sensitivity/specificity/precision/F1/MCC/FPR/FNR "
    "denominators and reported in the ambiguous rate."
)

PSEUDOGENE = (
    "If the independent annotation marks a matching locus as a pseudogene "
    "(pseudo=true, /pseudo, or interrupted CDS), the case is AMBIGUOUS for "
    "presence/absence. It is not a true positive and not a true negative."
)
PARTIAL = (
    "A partial CDS (incomplete, partial=true, or coverage below a complete "
    "protein) matching the target is AMBIGUOUS for presence/absence. "
    "Do not count as TP or TN."
)
FRAGMENTED = (
    "Fragments on separate contigs that the independent annotation does not "
    "join into one complete gene are AMBIGUOUS. If the independent annotation "
    "reconstructs one complete gene from fragments, score presence as for a "
    "complete locus. Genome Skeptic locus reconstruction is evaluated under "
    "locus metrics, not by forcing fragments into TP/TN."
)
DUPLICATE = (
    "Multiple complete matching loci: presence/absence remains TP if at least "
    "one complete target locus exists. Copy number is scored only on the "
    "multiplicity endpoint using distinct genomic intervals, not collapsed names."
)
BROAD_FAMILY = (
    "A broad-family-only external annotation (superfamily, parent hierarchy "
    "node, or generic product name without a member-gene assignment) is "
    "RELATED_BUT_NON_TARGET when the parent is a known related family, else "
    "AMBIGUOUS. It is never a silent TP or TN."
)


def label_block(**kwargs):
    base = {
        "true_positive": kwargs["true_positive"],
        "true_negative": kwargs["true_negative"],
        "related_but_non_target": kwargs["related_but_non_target"],
        "ambiguous": kwargs["ambiguous"],
        "pseudogenes": PSEUDOGENE,
        "partial_genes": PARTIAL,
        "fragmented_loci": FRAGMENTED,
        "duplicate_loci": DUPLICATE,
        "broad_family_only_external_annotations": BROAD_FAMILY,
        "ambiguous_must_not_become_positive_or_negative": True,
    }
    extra = kwargs.get("extra")
    if extra:
        base.update(extra)
    return base


TETA_EVIDENCE = {
    "frozen_family_id": "tetA_tetracycline_efflux",
    "index_alias": "tetA",
    "display_name": "tetracycline efflux TetA (mobile/plasmid-associated)",
    "family_class": "mfs_transporter",
    "biological_property": "mobile_plasmid_associated",
    "n_frozen_members": 2,
    "frozen_members": [
        {
            "protein_id": "P02980",
            "family_yaml_species_label": "Tn10 TetA class B",
            "length_aa": 401,
            "source": "data/target_families/tetA_tetracycline_efflux/family.yaml",
        },
        {
            "protein_id": "P02982",
            "family_yaml_species_label": "TetA/TCR1 tetracycline efflux",
            "length_aa": 399,
            "source": "data/target_families/tetA_tetracycline_efflux/family.yaml",
        },
    ],
    "competing_families": ["mfs_multidrug_efflux", "rnd_efflux"],
    "not_tetA_only": True,
    "not_tetA_tetB_tetC_superfamily": True,
    "tetC_not_a_frozen_member": True,
    "fetch_script_listed_P0A334_TetA_class_C_but_absent_from_frozen_family_yaml": True,
    "fetch_script_path": "scripts/fetch_v5_families.py",
    "v5_target_type_used_in_controls": "gene_orthologue",
    "calibration_also_has_protein_family_case": "cal5_cal_tetA_protein_family",
    "models_TargetFamily_docstring": "Curated homolog set for gene_orthologue reasoning. Not a single reference protein.",
    "conclusion": (
        "The frozen target is an explicitly defined two-member tetracycline MFS "
        "efflux family whose seeds are UniProt P02980 (Tn10 TetA class B) and "
        "P02982 (TetA/TCR1). It is not specifically tet(A). It is not the NCBI "
        "tet_A_B_C_D / Tet(A)/Tet(B)/Tet(C) superfamily, because Tet(C) is not a "
        "frozen member. tet(B) is a family member of this frozen target, not an "
        "exact-gene synonym of tet(A)."
    ),
}


TARGETS = [
    {
        "target": "tetA_tetracycline_efflux",
        "frozen_interpretation": (
            "Explicitly defined two-member tetracycline MFS efflux family "
            "(P02980 Tn10 TetA class B + P02982 TetA/TCR1). Not tet(A)-only. "
            "Not Tet(A)/Tet(B)/Tet(C)."
        ),
        "tetA_resolution": "two_member_family_class_B_and_TetA_TCR1",
        "evidence": TETA_EVIDENCE,
        "primary_endpoint": "FAMILY",
        "secondary_endpoints": ["ORTHOLOGOUS_GENE"],
        "v5_target_type": "gene_orthologue",
        "pgap_insufficient_as_reference_standard": True,
        "pgap_insufficiency_reason": (
            "PGAP gene-name equality to tetA is an exact-symbol label, not the "
            "frozen two-member family. A tetB-only annotation would be missed "
            "or wrongly treated as non-target if tetA text equality were required. "
            "Generic tetracycline-resistance product names are not class-resolved. "
            "AMRFinderPlus tet(A) or tet(B) presence definitions are the FAMILY "
            "reference after predictions are frozen. tet(C) is RELATED_BUT_NON_TARGET."
        ),
        "proposed_external_label_source": "AMRFinderPlus presence genes tet(A) and tet(B) after freeze; PGAP tetA/tetB symbols only as a secondary symbol check, never as orthology",
        "label_rules": label_block(
            true_positive=(
                "Independent post-hoc presence of NCBI tet(A) (matching frozen "
                "member P02982) OR tet(B) (matching frozen member P02980) as a "
                "complete non-pseudo gene. FAMILY TP if either member is present. "
                "tet(A) and tet(B) are not scored as the same EXACT_GENE."
            ),
            true_negative=(
                "Independent annotation has no tet(A), no tet(B), and no other "
                "complete frozen-member-equivalent tetracycline MFS efflux gene. "
                "Competing MFS/RND transporters without tet(A)/tet(B) are TN for "
                "this family (and RELATED_BUT_NON_TARGET for classification)."
            ),
            related_but_non_target=(
                "tet(C), tet(D), tet_A_B_C_D parent-only, ABC tetA(*) subunits, "
                "MFS multidrug efflux (mdfA/emrB/bcr), RND (acrB/acrD), and other "
                "tetracycline MFS classes not among the two frozen members."
            ),
            ambiguous=(
                "Parent-only tet_A_B_C_D without a child gene; PGAP product "
                "'tetracycline efflux MFS transporter' without tetA/tetB symbol; "
                "pseudogene; partial; unrejoined fragments; conflicting tet(A) vs "
                "tet(B) class assignment on one locus."
            ),
            extra={
                "tetB_vs_tetA": (
                    "tet(B) is a frozen family member (P02980) so it is FAMILY-TP. "
                    "It is not treated as exact-gene equivalent to tet(A)."
                )
            },
        ),
    },
    {
        "target": "mfs_multidrug_efflux",
        "frozen_interpretation": (
            "Competitor panel family of non-TetA MFS multidrug efflux proteins "
            "MdfA (P0AEY8), EmrB (P0AEJ0), and Bcr (P28246). Index alias mdfA "
            "does not reduce the family to MdfA alone."
        ),
        "evidence": {
            "display_name": "MFS multidrug efflux (non-TetA competitors)",
            "family_class": "mfs_transporter",
            "biological_property": "membrane_transporter_competing_families",
            "members": ["P0AEY8", "P0AEJ0", "P28246"],
            "competing_families": ["tetA_tetracycline_efflux"],
            "source": "data/target_families/mfs_multidrug_efflux/family.yaml",
        },
        "primary_endpoint": "FAMILY",
        "secondary_endpoints": ["ORTHOLOGOUS_GENE"],
        "v5_target_type": "gene_orthologue",
        "pgap_insufficient_as_reference_standard": True,
        "pgap_insufficiency_reason": (
            "No single PGAP gene symbol equals this three-member competitor panel. "
            "Textual mdfA equality is not family membership and is not orthology. "
            "A union of mdfA/emrB/bcr symbols may label family presence after freeze, "
            "with generic 'MFS transporter' product names AMBIGUOUS."
        ),
        "proposed_external_label_source": "RefSeq/PGAP member-gene symbols mdfA OR emrB OR bcr after freeze; AMRFinderPlus MFS_efflux/emrB only as related-family check",
        "label_rules": label_block(
            true_positive="Complete non-pseudo PGAP/RefSeq gene symbol mdfA or emrB or bcr matching the frozen member set.",
            true_negative="None of mdfA, emrB, or bcr as complete genes, and no frozen-member-equivalent MFS multidrug efflux.",
            related_but_non_target="tet(A)/tet(B) tetracycline MFS, other MFS families, AMRFinderPlus MFS_efflux parent without a frozen member, E. coli-unrelated bcrA/B/C SMR/ABC proteins.",
            ambiguous="Generic MFS/multidrug-efflux product without a member gene symbol; pseudogene; partial; unrejoined fragments.",
        ),
    },
    {
        "target": "rnd_efflux",
        "frozen_interpretation": (
            "AcrB-like RND efflux family whose frozen members are E. coli AcrB "
            "(P31224) and AcrD (P24177). Not exact-gene acrB. MdtC (P0AE06) was "
            "listed in the fetch script but is not a frozen member."
        ),
        "evidence": {
            "display_name": "RND family efflux (AcrB-like)",
            "family_class": "rnd_transporter",
            "members": ["P31224", "P24177"],
            "competing_families": ["tetA_tetracycline_efflux", "mfs_multidrug_efflux"],
            "source": "data/target_families/rnd_efflux/family.yaml",
        },
        "primary_endpoint": "FAMILY",
        "secondary_endpoints": ["ORTHOLOGOUS_GENE"],
        "v5_target_type": "gene_orthologue",
        "pgap_insufficient_as_reference_standard": True,
        "pgap_insufficiency_reason": (
            "PGAP acrB or acrD gene-name equality is member-level, not orthology, "
            "and not a named RND superfamily. AMRFinderPlus catalogs acrB POINT "
            "alleles, which are not presence labels."
        ),
        "proposed_external_label_source": "RefSeq/PGAP acrB OR acrD gene symbols after freeze. Do not use AMRFinderPlus POINT alleles.",
        "label_rules": label_block(
            true_positive="Complete non-pseudo PGAP/RefSeq acrB or acrD.",
            true_negative="No complete acrB or acrD.",
            related_but_non_target="Other RND pumps (mdtC, acrF, mexB, etc.), MFS competitors, tetA family. AMRFinderPlus acrB POINT is not a presence TP.",
            ambiguous="Generic RND/HAE1 product without acrB/acrD; pseudogene; partial; unrejoined fragments.",
        ),
    },
    {
        "target": "recA_recombinase",
        "frozen_interpretation": (
            "RecA recombinase orthologue family (highly conserved, typically "
            "single-copy housekeeping), not an exact MG1655 allele. Frozen members "
            "are NP_417179.1, NP_214765.1, NP_228245.1, NP_213126.1."
        ),
        "evidence": {
            "display_name": "RecA recombinase (single-copy housekeeping)",
            "biological_property": "highly_conserved_single_copy_housekeeping",
            "members": ["NP_417179.1", "NP_214765.1", "NP_228245.1", "NP_213126.1"],
            "source": "data/target_families/recA_recombinase/family.yaml",
        },
        "primary_endpoint": "ORTHOLOGOUS_GENE",
        "secondary_endpoints": ["MULTIPLICITY"],
        "v5_target_type": "gene_orthologue",
        "pgap_insufficient_as_reference_standard": True,
        "pgap_insufficiency_reason": (
            "PGAP gene symbol recA is a name, not an orthology proof. Distant "
            "recA-like recombinases and radA must not be treated as RecA by text match."
        ),
        "proposed_external_label_source": "RefSeq/PGAP recA gene symbol as a presence-symbol label after freeze, with recA-like names RELATED/AMBIGUOUS; not an orthology standard",
        "label_rules": label_block(
            true_positive="Complete non-pseudo RefSeq/PGAP gene symbol recA.",
            true_negative="No recA gene symbol and no RecA product.",
            related_but_non_target="radA, recA2, recN, other recombinases labeled recA-like.",
            ambiguous="Product 'recombinase RecA family' without gene=recA; pseudogene; partial; unrejoined fragments.",
        ),
    },
    {
        "target": "tuf_EF_Tu",
        "frozen_interpretation": (
            "Elongation factor Tu family, including multi-copy paralogues tufA/tufB. "
            "Frozen members start from MG1655 tufA (NP_418240.1) plus distant EF-Tu "
            "proteins. The family is EF-Tu, not exact-gene tufA. Distinctive frozen "
            "property is multiplicity of near-identical copies."
        ),
        "evidence": {
            "display_name": "elongation factor Tu (multi-copy paralogues tufA/tufB)",
            "biological_property": "multi_copy_genuine_paralogues",
            "members": ["NP_418240.1", "NP_216072.1", "NP_228108.1", "NP_213616.1"],
            "v5_control": "ctrl_multi_near_identical",
            "source": "data/target_families/tuf_EF_Tu/family.yaml",
        },
        "primary_endpoint": "MULTIPLICITY",
        "secondary_endpoints": ["ORTHOLOGOUS_GENE"],
        "v5_target_type": "gene_orthologue",
        "pgap_insufficient_as_reference_standard": True,
        "pgap_insufficiency_reason": (
            "PGAP tuf/tufA/tufB symbols can count copies after freeze but do not "
            "establish orthology. Collapsed assemblies can undercount relative to PGAP."
        ),
        "proposed_external_label_source": "RefSeq/PGAP distinct tuf/tufA/tufB CDS intervals after freeze as copy-number labels, not as orthology",
        "label_rules": label_block(
            true_positive="Presence secondary: at least one complete tuf/tufA/tufB. Multiplicity TP: predicted copy number equals the number of distinct complete PGAP tuf/tufA/tufB intervals.",
            true_negative="Presence secondary: no tuf/tufA/tufB. Multiplicity TN is not used; undercall/overcall rates are used instead.",
            related_but_non_target="tufS, tsf, other GTPase translation factors, fusA.",
            ambiguous="Gene symbol tuf without interval count; pseudogene copies; partial copies; unrejoined fragments. Ambiguous copy counts are excluded from exact-agreement denominators.",
        ),
    },
    {
        "target": "lacZ_beta_galactosidase",
        "frozen_interpretation": (
            "Accessory LacZ beta-galactosidase orthologue family, often absent. "
            "Frozen members NP_414878.1, WP_000241775.1, WP_004084538.1. Not every "
            "beta-galactosidase."
        ),
        "evidence": {
            "display_name": "beta-galactosidase LacZ (accessory, absent from many strains)",
            "biological_property": "accessory_absent_from_many_strains",
            "members": ["NP_414878.1", "WP_000241775.1", "WP_004084538.1"],
            "source": "data/target_families/lacZ_beta_galactosidase/family.yaml",
        },
        "primary_endpoint": "ORTHOLOGOUS_GENE",
        "secondary_endpoints": ["FAMILY"],
        "v5_target_type": "gene_orthologue",
        "pgap_insufficient_as_reference_standard": True,
        "pgap_insufficiency_reason": (
            "PGAP gene=lacZ is a presence symbol, not orthology. Other "
            "beta-galactosidases (ebgA, bglX, lacZ-family products without lacZ) "
            "are not the frozen target."
        ),
        "proposed_external_label_source": "RefSeq/PGAP gene symbol lacZ after freeze as a presence-symbol label, not orthology",
        "label_rules": label_block(
            true_positive="Complete non-pseudo gene symbol lacZ.",
            true_negative="No lacZ gene symbol.",
            related_but_non_target="ebgA, bglX, and other beta-galactosidases without gene=lacZ.",
            ambiguous="Product 'beta-galactosidase' without gene=lacZ; pseudogene; partial; unrejoined fragments.",
        ),
    },
    {
        "target": "rpoB_RNAP_beta",
        "frozen_interpretation": (
            "Bacterial RNA polymerase subunit beta (RpoB) orthologue family "
            "(seven frozen proteins), with documented fusion/split architecture "
            "involving partner rpoC. Not an exact MG1655 allele. Not AMRFinderPlus "
            "rifampin POINT alleles."
        ),
        "evidence": {
            "display_name": "bacterial RNA polymerase subunit beta (RpoB)",
            "n_members": 7,
            "partner_families": ["rpoC_RNAP_beta_prime"],
            "known_fusion_or_split": True,
            "source": "data/target_families/rpoB_RNAP_beta/family.yaml",
        },
        "primary_endpoint": "ORTHOLOGOUS_GENE",
        "secondary_endpoints": ["LOCUS_ARCHITECTURE"],
        "v5_target_type": "gene_orthologue",
        "pgap_insufficient_as_reference_standard": True,
        "pgap_insufficiency_reason": (
            "PGAP gene=rpoB is not orthology. Fused rpoBC products may lack a "
            "simple rpoB symbol. AMRFinderPlus rpoB POINT mutations are not presence."
        ),
        "proposed_external_label_source": "RefSeq/PGAP rpoB (and fused rpoBC products) after freeze as presence/architecture labels, not orthology; never AMRFinderPlus POINT",
        "label_rules": label_block(
            true_positive="Complete non-pseudo rpoB, or a documented rpoB-rpoC fusion polypeptide annotated as such.",
            true_negative="No rpoB and no rpoBC fusion.",
            related_but_non_target="rpoA, rpoC as a substitute for rpoB, rpoD, AMRFinderPlus rpoB POINT-only records.",
            ambiguous="Generic RNA polymerase beta product without rpoB; split adjacent ORFs without a complete annotation; pseudogene; partial; unrejoined fragments.",
        ),
    },
    {
        "target": "rpoC_RNAP_beta_prime",
        "frozen_interpretation": (
            "Bacterial RNA polymerase subunit beta-prime (RpoC) partner family "
            "(NP_418415.1, NP_215182.1). Not a substitute rpoB definition."
        ),
        "evidence": {
            "display_name": "bacterial RNA polymerase subunit beta-prime (RpoC)",
            "role": "partner family for fusion tests; not a substitute rpoB definition",
            "members": ["NP_418415.1", "NP_215182.1"],
            "source": "data/target_families/rpoC_RNAP_beta_prime/family.yaml",
        },
        "primary_endpoint": "ORTHOLOGOUS_GENE",
        "secondary_endpoints": ["LOCUS_ARCHITECTURE"],
        "v5_target_type": "gene_orthologue",
        "pgap_insufficient_as_reference_standard": True,
        "pgap_insufficiency_reason": (
            "PGAP gene=rpoC is not orthology. Fused rpoBC may omit a separate rpoC. "
            "AMRFinderPlus rpoC POINT mutations are not presence."
        ),
        "proposed_external_label_source": "RefSeq/PGAP rpoC (and fused rpoBC products) after freeze; never AMRFinderPlus POINT",
        "label_rules": label_block(
            true_positive="Complete non-pseudo rpoC, or a documented rpoB-rpoC fusion polypeptide.",
            true_negative="No rpoC and no rpoBC fusion.",
            related_but_non_target="rpoB as a substitute for rpoC, other RNAP subunits, AMRFinderPlus rpoC POINT-only records.",
            ambiguous="Generic RNA polymerase beta-prime product without rpoC; pseudogene; partial; unrejoined fragments.",
        ),
    },
]


METRICS = {
    "no_headline_accuracy_across_biologically_different_targets": True,
    "report_per_target_before_any_pooled_result": True,
    "ambiguous_excluded_from_presence_denominators": True,
    "presence_absence_applicable_when_primary_or_secondary_is_presence": {
        "applies_to_targets": [
            "tetA_tetracycline_efflux",
            "mfs_multidrug_efflux",
            "rnd_efflux",
            "recA_recombinase",
            "tuf_EF_Tu",
            "lacZ_beta_galactosidase",
            "rpoB_RNAP_beta",
            "rpoC_RNAP_beta_prime",
        ],
        "metrics": [
            "sensitivity",
            "specificity",
            "precision",
            "F1",
            "MCC",
            "false_positive_rate",
            "false_negative_rate",
        ],
        "definitions": {
            "sensitivity": "TP / (TP + FN)",
            "specificity": "TN / (TN + FP)",
            "precision": "TP / (TP + FP)",
            "F1": "2 * precision * sensitivity / (precision + sensitivity)",
            "MCC": "Matthews correlation coefficient on TP,TN,FP,FN",
            "false_positive_rate": "FP / (FP + TN)",
            "false_negative_rate": "FN / (FN + TP)",
        },
        "related_but_non_target_handling": (
            "RELATED_BUT_NON_TARGET predicted as the target family/gene is FP "
            "for presence and also counted in related-but-nontarget FPR. "
            "RELATED_BUT_NON_TARGET correctly rejected is not TN of the target; "
            "it is a correct rejection under classification metrics."
        ),
    },
    "locus_family_classification": {
        "applies_to_targets": [
            "tetA_tetracycline_efflux",
            "mfs_multidrug_efflux",
            "rnd_efflux",
            "rpoB_RNAP_beta",
            "rpoC_RNAP_beta_prime",
        ],
        "metrics": [
            "exact_classification_accuracy",
            "related_but_nontarget_false_positive_rate",
            "ambiguous_rate",
        ],
        "definitions": {
            "exact_classification_accuracy": (
                "Fraction of non-ambiguous cases whose predicted family/architecture "
                "matches the frozen target vs competitor vs absent vs related-non-target."
            ),
            "related_but_nontarget_false_positive_rate": (
                "Fraction of RELATED_BUT_NON_TARGET reference cases predicted as the target."
            ),
            "ambiguous_rate": "n_ambiguous / n_cases",
        },
    },
    "multiplicity": {
        "applies_to_targets": ["tuf_EF_Tu", "recA_recombinase"],
        "metrics": ["exact_copy_number_agreement", "undercall_rate", "overcall_rate"],
        "definitions": {
            "exact_copy_number_agreement": (
                "Fraction of non-ambiguous cases where predicted distinct-locus "
                "count equals the independent complete-CDS interval count."
            ),
            "undercall_rate": "predicted_n < reference_n",
            "overcall_rate": "predicted_n > reference_n",
        },
    },
    "confidence": {
        "applies_to": "all_frozen_targets",
        "metrics": ["Brier_score", "ECE", "overconfidence_rate"],
        "note": "Use Genome Skeptic numeric confidence vs binary non-ambiguous outcome. relative_support is not a calibrated probability.",
    },
    "falsification": {
        "applies_to": "all_frozen_targets",
        "metrics": [
            "n_initial_interpretations_changed_after_contradictory_evidence",
            "correct_rejection_rate",
            "unresolved_rate",
        ],
    },
}


CONTRACT = {
    "kind": "v5_external_scoring_contract",
    **COMMON,
    "anti_leakage": AMBIGUOUS_GLOBAL,
    "pgap_gene_name_equality_is_not_orthology": True,
    "n_frozen_targets": 8,
    "tetA_final_interpretation": TETA_EVIDENCE["conclusion"],
    "targets": TARGETS,
    "metrics": METRICS,
    "pgap_insufficient_as_reference_standard": [t["target"] for t in TARGETS if t["pgap_insufficient_as_reference_standard"]],
}


FROZEN_MEMBERS = [
    "P02980", "P02982",
    "P0AEY8", "P0AEJ0", "P28246",
    "P31224", "P24177",
    "NP_417179.1", "NP_214765.1", "NP_228245.1", "NP_213126.1",
    "NP_418240.1", "NP_216072.1", "NP_228108.1", "NP_213616.1",
    "NP_414878.1", "WP_000241775.1", "WP_004084538.1",
    "NP_418414.1", "NP_215181.1", "WP_004081508.1", "WP_010871995.1",
    "WP_243759718.1", "WP_506804874.1", "WP_010881267.1",
    "NP_418415.1", "NP_215182.1",
]
FORBIDDEN = [
    "NP_252960.1", "WP_000037869.1", "NP_463022.1", "WP_003255495.1",
    "YP_499096.2", "NP_387988.1", "NP_387989.1",
]
CONSTRUCTION_ATTEMPT_NOT_FROZEN = [
    "P0A334",
    "P0AE06",
    "AAA87452.1",
    "WP_000048591.1",
    "WP_001301208.1",
]

CATALOG_GENOMES = [
    {"genome_id": "ecoli_k12", "accession": "NC_000913.3", "role": "development_and_family_source", "species": "Escherichia coli str. K-12 substr. MG1655", "source": "src/genome_skeptic/eval/catalog.py"},
    {"genome_id": "pao1", "accession": "NC_002516.2", "role": "development", "species": "Pseudomonas aeruginosa PAO1", "source": "src/genome_skeptic/eval/catalog.py"},
    {"genome_id": "hpylori", "accession": "NC_000915.1", "role": "development", "species": "Helicobacter pylori 26695", "source": "src/genome_skeptic/eval/catalog.py"},
    {"genome_id": "bsubtilis", "accession": "NC_000964.3", "role": "development", "species": "Bacillus subtilis subsp. subtilis str. 168", "source": "src/genome_skeptic/eval/catalog.py"},
    {"genome_id": "pputida_kt2440", "accession": "NC_002947.4", "role": "held_out_internal", "species": "Pseudomonas putida KT2440", "source": "src/genome_skeptic/eval/catalog.py"},
    {"genome_id": "staph_8325", "accession": "NC_007795.1", "role": "held_out_internal", "species": "Staphylococcus aureus subsp. aureus NCTC 8325", "source": "src/genome_skeptic/eval/catalog.py"},
    {"genome_id": "salmonella_lt2", "accession": "NC_003197.2", "role": "held_out_internal", "species": "Salmonella enterica subsp. enterica serovar Typhimurium str. LT2", "source": "src/genome_skeptic/eval/catalog.py", "extra_accessions": ["NC_003277.2"]},
    {"genome_id": "vcholerae_chr1", "accession": "NC_002505.1", "role": "held_out_internal", "species": "Vibrio cholerae O1 biovar El Tor str. N16961 chromosome I", "source": "src/genome_skeptic/eval/catalog.py"},
]
HOMOLOG_SOURCE_GENOMES = [
    {"genome_id": "mtb_h37rv", "accession": "NC_000962.3", "role": "family_homolog_source", "species": "Mycobacterium tuberculosis H37Rv", "linked_proteins": ["NP_214765.1", "NP_216072.1", "NP_215181.1", "NP_215182.1"], "note": "Inferred from frozen NP_ member records named H37Rv; candidate external labels were not inspected."},
    {"genome_id": "tmaritima_msb8", "accession": "NC_000853.1", "role": "family_homolog_source", "species": "Thermotoga maritima", "linked_proteins": ["NP_228245.1", "NP_228108.1"], "note": "Inferred from frozen NP_ member records named Thermotoga maritima; candidate external labels were not inspected."},
    {"genome_id": "aaeolicus_vf5", "accession": "NC_000918.1", "role": "family_homolog_source", "species": "Aquifex aeolicus", "linked_proteins": ["NP_213126.1", "NP_213616.1"], "note": "Inferred from frozen NP_ member records named Aquifex aeolicus; candidate external labels were not inspected."},
]
NAMED_STRAINS_NO_FROZEN_GENOME_ACCESSION = [
    {"species": "Synechocystis sp.", "linked_proteins": ["WP_010871995.1"], "note": "WP accession is not genome-unique; exclude the protein, not all Synechocystis isolates."},
    {"species": "Deinococcus radiodurans", "linked_proteins": ["WP_243759718.1"], "note": "WP accession is not genome-unique; exclude the protein, not all D. radiodurans isolates."},
    {"species": "Streptococcus pyogenes", "linked_proteins": ["WP_506804874.1"], "note": "WP accession is not genome-unique; exclude the protein, not all S. pyogenes isolates."},
    {"species": "Shigella flexneri", "linked_proteins": ["WP_000241775.1"], "note": "WP accession is not genome-unique; exclude the protein."},
    {"species": "Klebsiella pneumoniae", "linked_proteins": ["WP_004084538.1"], "note": "WP accession is not genome-unique; exclude the protein."},
]

NUC_ACCESSIONS = []
for g in CATALOG_GENOMES:
    NUC_ACCESSIONS.append(g["accession"])
    NUC_ACCESSIONS.extend(g.get("extra_accessions") or [])
NUC_ACCESSIONS.append("U00096.3")  # MG1655 synonym of NC_000913.3
for g in HOMOLOG_SOURCE_GENOMES:
    NUC_ACCESSIONS.append(g["accession"])
NUC_ACCESSIONS = sorted(set(NUC_ACCESSIONS))

PROTEIN_EXCL = sorted(set(FROZEN_MEMBERS + FORBIDDEN + CONSTRUCTION_ATTEMPT_NOT_FROZEN))
N_GENOMES = len(CATALOG_GENOMES) + len(HOMOLOG_SOURCE_GENOMES)

EXCLUSIONS = {
    "kind": "v5_reference_provenance_exclusions",
    **COMMON,
    "audit_only": True,
    "candidate_external_genome_labels_inspected": False,
    "purpose": "Exact genomes and sequences used to construct or tune frozen V5 target resources must not enter the external test cohort.",
    "n_source_reference_genomes_excluded": N_GENOMES,
    "n_nucleotide_accessions_excluded": len(NUC_ACCESSIONS),
    "n_sequence_protein_accessions_excluded": len(PROTEIN_EXCL),
    "excluded_source_reference_genomes": CATALOG_GENOMES + HOMOLOG_SOURCE_GENOMES,
    "excluded_nucleotide_accessions": NUC_ACCESSIONS,
    "excluded_protein_accessions": {
        "frozen_family_members": FROZEN_MEMBERS,
        "forbidden_fast_pilot_hidden_genome_proteins": FORBIDDEN,
        "construction_attempt_not_frozen_members": CONSTRUCTION_ATTEMPT_NOT_FROZEN,
        "all": PROTEIN_EXCL,
    },
    "named_source_strains_without_frozen_genome_accession": NAMED_STRAINS_NO_FROZEN_GENOME_ACCESSION,
    "synthetic_internal_benchmarks": {
        "exclude_as_external_cohort": True,
        "note": "V5/V4.1 synthetic calibration loci and controls are not external genomes.",
        "paths": [
            "benchmarks/v5/calibration_loci",
            "benchmarks/v5/controls",
            "benchmarks/v4_1/calibration_loci",
            "src/genome_skeptic/eval/v5_controls.py",
            "src/genome_skeptic/eval/calibration_v5.py",
            "src/genome_skeptic/eval/calibration_v4.py",
        ],
    },
    "divergence_and_calibration_resources": {
        "note": "Divergence/LOGO calibration used development genomes and synthetic loci only. Held-out catalog genomes were not used to fit, but they remain excluded from the external cohort because they were internal evaluation genomes.",
        "files": [
            "src/genome_skeptic/validators/divergence.py",
            "calibration_v5.json",
            "src/genome_skeptic/eval/calibration_v5.py",
        ],
    },
    "competitive_family_resources": [
        "data/target_families/tetA_tetracycline_efflux",
        "data/target_families/mfs_multidrug_efflux",
        "data/target_families/rnd_efflux",
    ],
    "transposon_proteins_not_complete_genomes": ["P02980", "P02982"],
}


INPUT_POLICY = {
    "kind": "v5_external_input_policy",
    **COMMON,
    "policy": "Genome Skeptic may receive only solver-appropriate sequence inputs required by frozen V5.",
    "permitted_inference_inputs": [
        "nucleotide assembly FASTA with sanitized headers",
        "optional paired FASTQ if a future run uses the frozen V5 isolate stack (not required for STEP 3B)",
        "frozen V5 target family identifiers (tetA_tetracycline_efflux and the other seven)",
        "frozen internal family members, MSAs, and hmmbuild profiles already inside V5",
        "declared organism string only if stripped of gene names and external labels",
    ],
    "forbidden_inference_inputs": [
        "PGAP GFF/GTF annotations",
        "GenBank feature annotations",
        "AMRFinderPlus output",
        "AMRFinderPlus HMM profiles",
        "AMRFinderPlus reference sequences",
        "AMRFinderPlus curated thresholds",
        "AMRFinderPlus gene hierarchy rules",
        "MicroBIGG-E calls",
        "external gene names embedded in sidecar metadata",
        "external reference labels",
        "scorer-only truth manifests",
        "hidden source genomes",
        "unsanitized FASTA headers that contain functional annotations",
    ],
    "fasta_header_sanitization": {
        "required": True,
        "rule": "Replace headers with opaque replicon/contig identifiers (e.g. contig_1). Strip product, gene, protein, AMR, and organism-function text.",
        "existing_internal_precedent": "src/genome_skeptic/eval/real_genomes.py::_anonymize_fasta",
    },
    "when_external_labels_may_be_used": "Only after Genome Skeptic predictions are frozen, as post-hoc reference labels.",
    "amrfinderplus_and_pgap_are_not_solver_inputs": True,
}


def dump(name: str, obj: dict) -> str:
    path = OUT / name
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / f"{path.stem}.sha256.json").write_text(
        json.dumps({"file": name, "sha256": digest}, indent=2) + "\n",
        encoding="utf-8",
    )
    return digest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    h1 = dump("v5_external_scoring_contract.json", CONTRACT)
    h2 = dump("v5_reference_provenance_exclusions.json", EXCLUSIONS)
    h3 = dump("v5_external_input_policy.json", INPUT_POLICY)
    summary = {
        "scoring_contract_sha256": h1,
        "provenance_exclusions_sha256": h2,
        "input_policy_sha256": h3,
        "n_source_reference_genomes_excluded": N_GENOMES,
        "n_sequence_protein_accessions_excluded": len(PROTEIN_EXCL),
        "pgap_insufficient": [t["target"] for t in TARGETS],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
