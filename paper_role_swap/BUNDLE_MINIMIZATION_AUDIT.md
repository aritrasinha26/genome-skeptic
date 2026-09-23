# Bundle minimization audit

Audit only — **no files were deleted or modified**.

Inventory scope: the **448** scientific/bundle files present before this audit document and `ESSENTIAL_FILE_LIST.txt` were written. Those two audit outputs are meta and excluded from the classification table.

## Method

Dependencies were traced from:

1. Actual file reads in `scripts/scoring/verify_locked_claims.py`
2. File I/O and figure `savefig` paths in `scripts/scoring/score_role_swap_unblind.py`
   (note: that script’s `ROOT` resolves to the parent of `scripts/`, expects
   `role_swap_cross_task/`, and is **not runnable against this bundle tree**)
3. Explicit path references in `README.md` and `REPRODUCIBILITY_AUDIT.md`
4. Provenance needed for manuscript numerical claims (locks, B↔D hashes, stats,
   follow-ups, latency/cost, precursor locked summaries)
5. SHA256 duplicate detection across the bundle

Primary reproducibility path = **locked outputs without new Sol/Jev API calls**.

## Summary counts

| Metric | Value |
| --- | ---: |
| Current file count | 448 |
| Current total size | 4885224 bytes (4.66 MiB) |
| ESSENTIAL | 179 (2.27 MiB) |
| SUPPORTING | 100 (2.03 MiB) |
| REDUNDANT | 169 (0.35 MiB) |
| UNSURE | 0 (0.00 MiB) |
| Estimated minimized size (ESSENTIAL+SUPPORTING) | 4513851 bytes (4.30 MiB) |

## Path-A executable dependency closure

`verify_locked_claims.py` reads exactly:

- `data/arm_b_vs_d_evidence_hashes.csv`
- `provenance/final_manifest.json`
- `results/controller_efficiency.csv`
- `results/statistics.json`
- `scripts/scoring/verify_locked_claims.py`

All other ESSENTIAL files are required for independent provenance / figure / table /
precursor claim verification beyond that single script.

## Safe-to-remove REDUNDANT sets

| Pattern | n | Example paths |
| --- | ---: | --- |
| Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 | 100 | `data/locked_predictions/A/RS01_prediction.json.sha256.json`, `data/locked_predictions/A/RS02_prediction.json.sha256.json`, `data/locked_predictions/A/RS03_prediction.json.sha256.json`, … (+97) |
| Arm B critic intermediate; identity claim uses final_state_hash only | 20 | `data/arm_b_final_evidence/RS01/critic_output.json`, `data/arm_b_final_evidence/RS02/critic_output.json`, `data/arm_b_final_evidence/RS03/critic_output.json`, … (+17) |
| Arm B planner intermediate; identity claim uses final_state_hash only | 20 | `data/arm_b_final_evidence/RS01/planner_output.json`, `data/arm_b_final_evidence/RS02/planner_output.json`, `data/arm_b_final_evidence/RS03/planner_output.json`, … (+17) |
| lacZ orthology assets unused by tet(A)/tet(B) manuscript experiments | 4 | `config/frozen_config/orthology_references/lacZ_beta_galactosidase/index.yaml`, `config/frozen_config/orthology_references/lacZ_beta_galactosidase/P00722.faa`, `config/frozen_config/orthology_references/lacZ_beta_galactosidase/P06864.faa`, … (+1) |
| PDF alternate of essential PNG render; prefer one canonical figure format | 4 | `results/figure_source_data/FIGURE1_architecture.pdf`, `results/figure_source_data/FIGURE2_balanced_accuracy.pdf`, `results/figure_source_data/FIGURE3_sol_authority_effect.pdf`, … (+1) |
| rpoB family panel not required to verify locked precursor claims (results already scored) | 3 | `config/frozen_config/target_families/rpoB_RNAP_beta/family.yaml`, `config/frozen_config/target_families/rpoB_RNAP_beta/members.aln.faa`, `config/frozen_config/target_families/rpoB_RNAP_beta/members.faa` |
| Non-study warmup/init helper; warmups recorded in provenance/warmups.json; not needed for path A | 2 | `scripts/controllers/model_poc_v5_init.py`, `scripts/controllers/run_warmups.py` |
| Bundle-assembly scratch summary; not used by verification/README claims | 1 | `_build_summary.json` |
| Byte-identical duplicate of canonical `config/frozen_config/V5_SCIENTIFIC_CORE_HASH.txt` | 1 | `config/frozen_config/ROLE_SWAP_SCIENTIFIC_CORE_HASH.txt` |
| JSON twin of essential accessions_and_checksums.csv | 1 | `data/accessions_and_checksums.json` |
| JSON twin of essential CSV used by verify_locked_claims.py | 1 | `data/arm_b_vs_d_evidence_hashes.json` |
| JSON twin of essential prospective_case_manifest.csv | 1 | `data/prospective_case_manifest.json` |
| Byte-identical duplicate of canonical `data/caseset_lock.json` | 1 | `provenance/caseset_lock.json` |
| Byte-identical duplicate of canonical `results/execution_manifest.json` | 1 | `provenance/execution_manifest.json` |
| Byte-identical duplicate of canonical `config/frozen_config/ROLE_SWAP_FREEZE_MANIFEST.json` | 1 | `provenance/freeze_manifest.json` |
| Byte-identical duplicate of canonical `config/frozen_config/ROLE_SWAP_FREEZE_MANIFEST.sha256` | 1 | `provenance/freeze_manifest.sha256` |
| Byte-identical duplicate of canonical `data/prediction_lock.json` | 1 | `provenance/prediction_lock.json` |
| Byte-identical duplicate of canonical `config/prompts/PROMPT_AND_MODEL_HASHES.json` | 1 | `provenance/prompt_hashes.json` |
| Byte-identical duplicate of canonical `data/truth_lock.json` | 1 | `provenance/truth_lock.json` |
| Byte-identical duplicate of canonical `results/controller_summary.csv` | 1 | `results/figure_source_data/fig_balanced_accuracy_source.csv` |
| Byte-identical duplicate of canonical `results/controller_efficiency.csv` | 1 | `results/figure_source_data/fig_controller_efficiency_source.csv` |
| Byte-identical duplicate of canonical `results/role_swap_summary.csv` | 1 | `results/figure_source_data/fig_role_swap_discordance_source.csv` |
| Byte-identical duplicate of canonical `results/case_level_results.csv` | 1 | `results/figure_source_data/table_case_level_source.csv` |

### Exact removable directories / globs

- `data/locked_predictions/*/*.sha256.json` (100 files)
- `data/arm_b_final_evidence/*/planner_output.json` (20)
- `data/arm_b_final_evidence/*/critic_output.json` (20)
- `results/figure_source_data/*.pdf` (4)
- `results/figure_source_data/fig_*_source.csv` and `table_case_level_source.csv` (4)
- Duplicate provenance copies: `provenance/{prediction,caseset,truth}_lock.json`,
  `provenance/execution_manifest.json`, `provenance/freeze_manifest*`, `provenance/prompt_hashes.json`
- `data/arm_b_vs_d_evidence_hashes.json`, `data/accessions_and_checksums.json`,
  `data/prospective_case_manifest.json`
- `config/frozen_config/orthology_references/lacZ_beta_galactosidase/`
- `config/frozen_config/target_families/rpoB_RNAP_beta/`
- `_build_summary.json`
- `scripts/controllers/run_warmups.py`, `scripts/controllers/model_poc_v5_init.py`

## Files whose removal would break reproducibility

Do **not** remove ESSENTIAL files, including:

- `results/statistics.json`, `results/controller_efficiency.csv`, `results/controller_summary.csv`,
  `results/case_level_results.csv`, `results/role_swap_summary.csv`
- `data/arm_b_vs_d_evidence_hashes.csv` plus `data/arm_b_final_evidence/*/ARM_B_LOCKED_EVIDENCE_STATE.json`
  and `data/locked_predictions/{B,D}/*_prediction.json` (independent B↔D identity + endpoints)
- `data/locked_predictions/{A,C,F}/*_prediction.json` (controller endpoint identity claims)
- `data/prediction_lock.json`, `data/caseset_lock.json`, `data/truth_lock.json`,
  `data/prospective_case_manifest.csv`, `data/prospective_truth.csv`
- `provenance/final_manifest.json` (+ sha256 / hash check)
- Figure PNGs under `results/figure_source_data/` and precursor locked summaries
- Prompt texts + `PROMPT_AND_MODEL_HASHES.json`, freeze manifests, action registry
- `scripts/scoring/verify_locked_claims.py`, `README.md`, `STUDY_MANIFEST.json`

Do **not** auto-remove SUPPORTING files (protocols, JUDGE_PACKETs, historical scripts,
tetA family panels, truth source freeze) without a separate scientific decision.

## Proposed minimized target structure

```
paper_role_swap/
├── README.md
├── STUDY_MANIFEST.json
├── REPRODUCIBILITY_AUDIT.md
├── protocol/                    # ROLE_SWAP, TRUTH, CASE_SELECTION, ARMS, PHASE0
├── config/
│   ├── frozen_config/           # freeze manifests, Sol YAML, env, tetA family panels
│   ├── action_registry/
│   └── prompts/                 # planner/critic/judge + PROMPT_AND_MODEL_HASHES.json
├── scripts/
│   ├── scoring/                 # verify_locked_claims.py (+ historical unblind/m60 scripts)
│   ├── controllers/             # sol/jev adapters + historical run script (SUPPORTING)
│   ├── adjudication/            # decision_arms, evidence_packet, V5 freeze scripts
│   ├── truth/                   # build_role_swap_teta_cohort.py
│   ├── measurement/             # frozen V5 sources (SUPPORTING transparency)
│   └── figures/README.md
├── data/
│   ├── prospective_case_manifest.csv, prospective_truth.csv/.json
│   ├── caseset_lock.json, truth_lock.json, prediction_lock.json
│   ├── accessions_and_checksums.csv, GENOME_RETRIEVAL.md
│   ├── arm_b_vs_d_evidence_hashes.csv
│   ├── arm_b_final_evidence/RS*/{ARM_B_LOCKED_EVIDENCE_STATE,JUDGE_PACKET}.json
│   ├── locked_predictions/{A,B,C,D,F}/RS*_prediction.json   # no .sha256 sidecars
│   ├── precursor_*, exclusion/diversity/overlap audits, truth_* manifests
│   └── truth_source_freeze/     # tetA HMM/panels
├── results/
│   ├── statistics.json, controller_*.csv, case_level_results.csv, role_swap_summary.csv
│   ├── execution_manifest.json, ROLE_SWAP_FINAL_RESULTS.md, preunblind_*
│   ├── figure_source_data/      # PNG only + precursor PNGs
│   └── precursor/               # locked M60/posthoc/ablation summaries
└── provenance/
    ├── final_manifest.json/.sha256, final_hash_check.json
    ├── unblind_audit.md, execution_integrity.md
    ├── truth_access_audit.json, warmups.json
    # (no duplicate copies of data/ locks)
```

## Per-file classification

| path | category | safely_removable | depends | reason |
| --- | --- | --- | --- | --- |
| `README.md` | ESSENTIAL | False | README reproduction / audit | Bundle documentation / inventory required for reproduction narrative |
| `REPRODUCIBILITY_AUDIT.md` | ESSENTIAL | False | README reproduction / audit | Bundle documentation / inventory required for reproduction narrative |
| `STUDY_MANIFEST.json` | ESSENTIAL | False | README reproduction / audit | Bundle documentation / inventory required for reproduction narrative |
| `_build_summary.json` | REDUNDANT | True | none (duplicate/superseded) | Bundle-assembly scratch summary; not used by verification/README claims |
| `config/action_registry/ACTION_REGISTRY.json` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/frozen_config/ROLE_SWAP_FREEZE_CHECK.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/ROLE_SWAP_FREEZE_MANIFEST.json` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/frozen_config/ROLE_SWAP_FREEZE_MANIFEST.sha256` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/frozen_config/ROLE_SWAP_PREFLIGHT_HASH_CHECK.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/ROLE_SWAP_SCIENTIFIC_CORE_HASH.txt` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `config/frozen_config/V5_SCIENTIFIC_CORE_HASH.txt` |
| `config/frozen_config/ROLE_SWAP_STOP2.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/ROLE_SWAP_STOP3.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/V5_ALIGNMENT.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/V5_FREEZE_MANIFEST.json` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/frozen_config/V5_SCIENTIFIC_CORE_HASH.txt` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/frozen_config/environment.yml` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/frozen_config/environment_manifest.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/orthology_references/lacZ_beta_galactosidase/P00722.faa` | REDUNDANT | True | none (duplicate/superseded) | lacZ orthology assets unused by tet(A)/tet(B) manuscript experiments |
| `config/frozen_config/orthology_references/lacZ_beta_galactosidase/P06864.faa` | REDUNDANT | True | none (duplicate/superseded) | lacZ orthology assets unused by tet(A)/tet(B) manuscript experiments |
| `config/frozen_config/orthology_references/lacZ_beta_galactosidase/P19668.faa` | REDUNDANT | True | none (duplicate/superseded) | lacZ orthology assets unused by tet(A)/tet(B) manuscript experiments |
| `config/frozen_config/orthology_references/lacZ_beta_galactosidase/index.yaml` | REDUNDANT | True | none (duplicate/superseded) | lacZ orthology assets unused by tet(A)/tet(B) manuscript experiments |
| `config/frozen_config/pyproject.toml` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/frozen_config/sol56_high_posthoc.yaml` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/frozen_config/target_families/index.yaml` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/mfs_multidrug_efflux/family.yaml` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/mfs_multidrug_efflux/members.aln.faa` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/mfs_multidrug_efflux/members.faa` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/rnd_efflux/family.yaml` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/rnd_efflux/members.aln.faa` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/rnd_efflux/members.faa` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/rpoB_RNAP_beta/family.yaml` | REDUNDANT | True | none (duplicate/superseded) | rpoB family panel not required to verify locked precursor claims (results already scored) |
| `config/frozen_config/target_families/rpoB_RNAP_beta/members.aln.faa` | REDUNDANT | True | none (duplicate/superseded) | rpoB family panel not required to verify locked precursor claims (results already scored) |
| `config/frozen_config/target_families/rpoB_RNAP_beta/members.faa` | REDUNDANT | True | none (duplicate/superseded) | rpoB family panel not required to verify locked precursor claims (results already scored) |
| `config/frozen_config/target_families/tetA_tetracycline_efflux/family.yaml` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/tetA_tetracycline_efflux/members.aln.faa` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/frozen_config/target_families/tetA_tetracycline_efflux/members.faa` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `config/prompts/CRITIC_PROMPT.txt` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/prompts/JUDGE_PROMPT.txt` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/prompts/PLANNER_PROMPT.txt` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `config/prompts/PROMPT_AND_MODEL_HASHES.json` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `data/GENOME_RETRIEVAL.md` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `data/accessions_and_checksums.csv` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `data/accessions_and_checksums.json` | REDUNDANT | True | none (duplicate/superseded) | JSON twin of essential accessions_and_checksums.csv |
| `data/arm_b_final_evidence/RS01/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS01/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS01/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS01/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS02/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS02/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS02/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS02/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS03/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS03/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS03/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS03/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS04/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS04/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS04/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS04/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS05/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS05/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS05/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS05/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS06/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS06/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS06/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS06/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS07/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS07/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS07/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS07/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS08/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS08/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS08/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS08/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS09/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS09/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS09/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS09/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS10/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS10/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS10/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS10/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS11/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS11/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS11/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS11/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS12/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS12/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS12/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS12/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS13/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS13/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS13/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS13/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS14/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS14/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS14/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS14/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS15/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS15/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS15/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS15/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS16/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS16/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS16/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS16/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS17/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS17/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS17/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS17/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS18/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS18/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS18/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS18/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS19/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS19/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS19/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS19/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS20/ARM_B_LOCKED_EVIDENCE_STATE.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Raw Arm B final_state_hash source for independent B↔D identity check |
| `data/arm_b_final_evidence/RS20/JUDGE_PACKET.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/arm_b_final_evidence/RS20/critic_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B critic intermediate; identity claim uses final_state_hash only |
| `data/arm_b_final_evidence/RS20/planner_output.json` | REDUNDANT | True | none (duplicate/superseded) | Arm B planner intermediate; identity claim uses final_state_hash only |
| `data/arm_b_vs_d_evidence_hashes.csv` | ESSENTIAL | False | verify_locked_claims.py; manuscript numerical claims | Direct input/output of verify_locked_claims.py |
| `data/arm_b_vs_d_evidence_hashes.json` | REDUNDANT | True | none (duplicate/superseded) | JSON twin of essential CSV used by verify_locked_claims.py |
| `data/arm_e_full_authority_index.csv` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/caseset_lock.json` | ESSENTIAL | False | provenance / README reproduction | Locked study artifact / pin for provenance |
| `data/diversity_audit.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/exclusion_audit.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/exclusion_manifest.csv` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/locked_predictions/A/RS01_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS01_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS02_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS02_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS03_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS03_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS04_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS04_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS05_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS05_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS06_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS06_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS07_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS07_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS08_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS08_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS09_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS09_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS10_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS10_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS11_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS11_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS12_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS12_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS13_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS13_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS14_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS14_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS15_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS15_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS16_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS16_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS17_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS17_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS18_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS18_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS19_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS19_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/A/RS20_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/A/RS20_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS01_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS01_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS02_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS02_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS03_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS03_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS04_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS04_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS05_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS05_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS06_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS06_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS07_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS07_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS08_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS08_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS09_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS09_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS10_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS10_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS11_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS11_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS12_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS12_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS13_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS13_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS14_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS14_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS15_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS15_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS16_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS16_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS17_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS17_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS18_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS18_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS19_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS19_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/B/RS20_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/B/RS20_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS01_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS01_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS02_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS02_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS03_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS03_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS04_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS04_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS05_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS05_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS06_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS06_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS07_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS07_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS08_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS08_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS09_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS09_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS10_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS10_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS11_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS11_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS12_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS12_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS13_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS13_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS14_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS14_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS15_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS15_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS16_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS16_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS17_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS17_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS18_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS18_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS19_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS19_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/C/RS20_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/C/RS20_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS01_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS01_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS02_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS02_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS03_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS03_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS04_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS04_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS05_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS05_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS06_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS06_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS07_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS07_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS08_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS08_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS09_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS09_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS10_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS10_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS11_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS11_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS12_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS12_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS13_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS13_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS14_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS14_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS15_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS15_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS16_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS16_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS17_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS17_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS18_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS18_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS19_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS19_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/D/RS20_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/D/RS20_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS01_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS01_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS02_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS02_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS03_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS03_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS04_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS04_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS05_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS05_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS06_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS06_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS07_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS07_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS08_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS08_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS09_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS09_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS10_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS10_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS11_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS11_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS12_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS12_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS13_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS13_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS14_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS14_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS15_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS15_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS16_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS16_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS17_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS17_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS18_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS18_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS19_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS19_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/locked_predictions/F/RS20_prediction.json` | ESSENTIAL | False | B↔D identity / controller comparison provenance | Locked per-arm prediction required to re-derive endpoints/stats without API |
| `data/locked_predictions/F/RS20_prediction.json.sha256.json` | REDUNDANT | True | none (duplicate/superseded) | Per-file SHA sidecar; hashes already in data/prediction_lock.json file_sha256 |
| `data/overlap_audit.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/precursor_case_manifest.csv` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `data/precursor_protocol.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/prediction_input.csv` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `data/prediction_lock.json` | ESSENTIAL | False | provenance / README reproduction | Locked study artifact / pin for provenance |
| `data/prospective_case_manifest.csv` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `data/prospective_case_manifest.json` | REDUNDANT | True | none (duplicate/superseded) | JSON twin of essential prospective_case_manifest.csv |
| `data/prospective_truth.csv` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `data/prospective_truth.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_evidence_manifest.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_independence_audit.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_lock.json` | ESSENTIAL | False | provenance / README reproduction | Locked study artifact / pin for provenance |
| `data/truth_source_freeze/hmm/mfs_multidrug_efflux.hmm` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_source_freeze/hmm/rnd_efflux.hmm` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_source_freeze/hmm/tetA_tetracycline_efflux.hmm` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_source_freeze/panels/tetA_competitors.faa` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_source_freeze/panels/tetA_target.faa` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_source_manifest.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `data/truth_stop3_integrity.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `protocol/ARM_DEFINITIONS.md` | ESSENTIAL | False | provenance / README reproduction | Manuscript figure/table source or rendered figure |
| `protocol/CASE_SELECTION.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `protocol/PHASE0_TARGET_AUDIT.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `protocol/ROLE_SWAP_PROTOCOL.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `protocol/TRUTH_PROTOCOL.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `provenance/caseset_lock.json` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `data/caseset_lock.json` |
| `provenance/execution_integrity.md` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `provenance/execution_manifest.json` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `results/execution_manifest.json` |
| `provenance/final_hash_check.json` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `provenance/final_manifest.json` | ESSENTIAL | False | verify_locked_claims.py; manuscript numerical claims | Direct input/output of verify_locked_claims.py |
| `provenance/final_manifest.sha256` | ESSENTIAL | False | verify_locked_claims.py; manuscript numerical claims | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `provenance/freeze_manifest.json` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `config/frozen_config/ROLE_SWAP_FREEZE_MANIFEST.json` |
| `provenance/freeze_manifest.sha256` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `config/frozen_config/ROLE_SWAP_FREEZE_MANIFEST.sha256` |
| `provenance/prediction_lock.json` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `data/prediction_lock.json` |
| `provenance/prompt_hashes.json` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `config/prompts/PROMPT_AND_MODEL_HASHES.json` |
| `provenance/truth_access_audit.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `provenance/truth_lock.json` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `data/truth_lock.json` |
| `provenance/unblind_audit.md` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `provenance/warmups.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `results/ROLE_SWAP_FINAL_RESULTS.md` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `results/case_level_results.csv` | ESSENTIAL | False | README §10 figures/tables | Manuscript figure/table source or rendered figure |
| `results/controller_efficiency.csv` | ESSENTIAL | False | verify_locked_claims.py; manuscript numerical claims | Direct input/output of verify_locked_claims.py |
| `results/controller_summary.csv` | ESSENTIAL | False | README §10 figures/tables | Manuscript figure/table source or rendered figure |
| `results/execution_manifest.json` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `results/figure_source_data/FIGURE1_architecture.pdf` | REDUNDANT | True | none (duplicate/superseded) | PDF alternate of essential PNG render; prefer one canonical figure format |
| `results/figure_source_data/FIGURE1_architecture.png` | ESSENTIAL | False | README §10 figures/tables | Manuscript figure/table source or rendered figure |
| `results/figure_source_data/FIGURE2_balanced_accuracy.pdf` | REDUNDANT | True | none (duplicate/superseded) | PDF alternate of essential PNG render; prefer one canonical figure format |
| `results/figure_source_data/FIGURE2_balanced_accuracy.png` | ESSENTIAL | False | README §10 figures/tables | Manuscript figure/table source or rendered figure |
| `results/figure_source_data/FIGURE3_sol_authority_effect.pdf` | REDUNDANT | True | none (duplicate/superseded) | PDF alternate of essential PNG render; prefer one canonical figure format |
| `results/figure_source_data/FIGURE3_sol_authority_effect.png` | ESSENTIAL | False | README §10 figures/tables | Manuscript figure/table source or rendered figure |
| `results/figure_source_data/FIGURE4_controller_efficiency.pdf` | REDUNDANT | True | none (duplicate/superseded) | PDF alternate of essential PNG render; prefer one canonical figure format |
| `results/figure_source_data/FIGURE4_controller_efficiency.png` | ESSENTIAL | False | verify_locked_claims.py; manuscript numerical claims | Manuscript figure/table source or rendered figure |
| `results/figure_source_data/fig_balanced_accuracy_source.csv` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `results/controller_summary.csv` |
| `results/figure_source_data/fig_controller_efficiency_source.csv` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `results/controller_efficiency.csv` |
| `results/figure_source_data/fig_role_swap_discordance_source.csv` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `results/role_swap_summary.csv` |
| `results/figure_source_data/precursor_FIGURE2_agent_vs_det.png` | ESSENTIAL | False | README §10 figures/tables | Manuscript figure/table source or rendered figure |
| `results/figure_source_data/precursor_FIGURE5_followup_efficiency.png` | ESSENTIAL | False | README §10 figures/tables | Manuscript figure/table source or rendered figure |
| `results/figure_source_data/table_case_level_source.csv` | REDUNDANT | True | none (duplicate/superseded) | Byte-identical duplicate of canonical `results/case_level_results.csv` |
| `results/precursor/ABLATION_VALIDATOR_R1_RECOVERY.csv` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/ABLATION_VALIDATOR_R1_SUMMARY.md` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/M60_AGENT_VS_DETERMINISTIC.csv` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/M60_EFFICIENCY_RESULTS.csv` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/M60_FINAL_CASE_LEVEL_RESULTS.csv` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/M60_FINAL_RESULTS.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `results/precursor/M60_REANALYSIS_SUMMARY.md` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/POSTHOC_ERROR_CASES.csv` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/POSTHOC_MANUSCRIPT_INTERPRETATION.md` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/POSTHOC_MODEL_INVARIANCE.md` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/POSTHOC_ROOT_CAUSE_SUMMARY.csv` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/SOL56_M60_SCORING.csv` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/precursor/SOL56_M60_SUMMARY.json` | ESSENTIAL | False | README §6 precursor claims | Locked precursor artifact cited for manuscript precursor claims |
| `results/preunblind_behaviour.csv` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `results/preunblind_comparisons.json` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `results/role_swap_summary.csv` | ESSENTIAL | False | README §10 figures/tables | Manuscript figure/table source or rendered figure |
| `results/statistics.json` | ESSENTIAL | False | verify_locked_claims.py; manuscript numerical claims | Direct input/output of verify_locked_claims.py |
| `scripts/adjudication/decision_arms.py` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `scripts/adjudication/evidence_packet.py` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `scripts/adjudication/freeze_v5_validator_repair.py` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `scripts/adjudication/run_validator_counterfactual.py` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `scripts/controllers/freeze.py` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `scripts/controllers/jev_adapter.py` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `scripts/controllers/launch_role_swap_execution_wsl.sh` | SUPPORTING | False | README §6–9 | README-referenced historical path-B/full-repo script; not executable for path A from bundle alone |
| `scripts/controllers/leakage.py` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `scripts/controllers/model_poc_v5_init.py` | REDUNDANT | True | none (duplicate/superseded) | Non-study warmup/init helper; warmups recorded in provenance/warmups.json; not needed for path A |
| `scripts/controllers/role_swap_prediction_path_guard.py` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `scripts/controllers/run_role_swap_execution.py` | SUPPORTING | False | README §6–9 | README-referenced historical path-B/full-repo script; not executable for path A from bundle alone |
| `scripts/controllers/run_warmups.py` | REDUNDANT | True | none (duplicate/superseded) | Non-study warmup/init helper; warmups recorded in provenance/warmups.json; not needed for path A |
| `scripts/controllers/sol_adapter.py` | ESSENTIAL | False | provenance / README reproduction | Required for path-A verification, tables, figures, or provenance of manuscript claims |
| `scripts/figures/README.md` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |
| `scripts/measurement/src/genome_skeptic/agents/action_catalog.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/agents/action_catalog_v4_1_dev.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/agents/action_contract.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/agents/assembly_loop.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/agents/assembly_loop_v4_1_dev.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/agents/diagnostic_needs.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/agents/diagnostic_needs_v4_1_dev.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/agents/diagnostic_needs_v4_dev.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/agents/providers.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/claims/action_policy.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/claims/attack_plan.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/config.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/families.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/manuscript/arms.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/models.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/competitive_family.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/falsification.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/family_orthology.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/homology.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/locus_multiplicity.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/locus_reconstruction.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/locus_stages_v4_1_dev.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/locus_v4_dev.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/src/genome_skeptic/validators/ortholog_references.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/measurement/tests/test_v5_validator_repair.py` | SUPPORTING | False | methods transparency / V5 freeze hash constituents | Frozen V5 scientific/measurement source copied for methods transparency; not imported by path-A verifier; path-B re-run needs full repository checkout |
| `scripts/scoring/launch_role_swap_unblind_wsl.sh` | SUPPORTING | False | README §6–9 | README-referenced historical path-B/full-repo script; not executable for path A from bundle alone |
| `scripts/scoring/score_m60_reanalysis.py` | SUPPORTING | False | README §6–9 | README-referenced historical path-B/full-repo script; not executable for path A from bundle alone |
| `scripts/scoring/score_role_swap_unblind.py` | SUPPORTING | False | README §9–10 (historical regeneration path) | Historical figure/table generator; hard-codes ROOT→role_swap_cross_task/ and is not runnable against this bundle layout. Published outputs already present under results/ |
| `scripts/scoring/verify_locked_claims.py` | ESSENTIAL | False | verify_locked_claims.py | Only in-bundle executable claim verifier (path A) |
| `scripts/truth/build_role_swap_teta_cohort.py` | SUPPORTING | False | README methods / provenance narrative | Protocol, freeze gate, audit, or historical execution script for scientific transparency |

## Machine-readable summary

```json
{
  "n_files": 448,
  "total_bytes": 4885224,
  "counts": {
    "REDUNDANT": 169,
    "ESSENTIAL": 179,
    "SUPPORTING": 100,
    "UNSURE": 0
  },
  "bytes_by_category": {
    "REDUNDANT": 371373,
    "ESSENTIAL": 2382189,
    "SUPPORTING": 2131662,
    "UNSURE": 0
  },
  "minimized_bytes_essential_plus_supporting": 4513851,
  "n_essential_file_list": 279
}
```

