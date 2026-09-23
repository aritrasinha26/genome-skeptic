# Reproducibility audit — Genome Skeptic role-swap study bundle

Audit date: 2026-09-23  
Bundle root: `paper_role_swap/`  
Recommended Git tag (not applied): `GENOME_SKEPTIC_ROLE_SWAP_PREPRINT`  
Primary path: **A — reproduce published analysis from locked outputs (no API calls)**

## Verdict

All reported prospective numerical claims in the manuscript were traced to locked artifacts in this bundle. Arm B final evidence hashes equal Arm D input hashes for **20/20** cases. No scientific source files were modified. No API keys or secret values are present (only environment-variable *names* in adapter/launch scripts).

## Files included

See `STUDY_MANIFEST.json` for the complete inventory (`n_copied` ≈ 440+ entries). Categories:

| Category | Bundle location | Original source |
| --- | --- | --- |
| Protocols | `protocol/` | `role_swap_cross_task/00_PROTOCOL/` |
| Freeze / Sol YAML / family defs | `config/frozen_config/` | `role_swap_cross_task/01_FREEZE/`, `prospective_v5/01_V5_FREEZE/`, `config/sol56_high_posthoc.yaml`, `src/genome_skeptic/data/target_families/` |
| Action registry dump | `config/action_registry/` | Serialized from frozen `action_catalog*.py` |
| Planner / critic / judge prompts | `config/prompts/` | `assembly_loop_v4_1_dev.py`, `decision_arms.py` |
| V5 scientific code | `scripts/measurement/src/...` | V5 freeze source list |
| Controllers (Sol, Jev, execution) | `scripts/controllers/` | `scripts/run_role_swap_execution.py`, `model_poc_v5/*` |
| Adjudication / judge | `scripts/adjudication/` | `decision_authority_poc/*`, V5 freeze / counterfactual scripts |
| Truth construction | `scripts/truth/` | `scripts/build_role_swap_teta_cohort.py` |
| Scoring / figures | `scripts/scoring/` | `score_role_swap_unblind.py`, `score_m60_reanalysis.py` |
| Prospective cases / truth / locks | `data/` | `role_swap_cross_task/02_CASES`, `03_TRUTH`, prediction lock |
| Arm B evidence + Arm D preds | `data/arm_b_final_evidence/`, `data/locked_predictions/` | Arms B/D locked outputs (compact; no full `GS_RUN`) |
| Accessions + SHA256 | `data/accessions_and_checksums.*` | Derived from caseset |
| Precursor cohort | `data/precursor_case_manifest.csv` | `manuscript_benchmark/M60_COHORT_MANIFEST.csv` |
| Scored results / stats | `results/` | `role_swap_cross_task/10_RESULTS/` |
| Precursor minimal | `results/precursor/` | M60 RESULTS, POSTHOC, ABLATION, SOL56 summary |
| Provenance | `provenance/` | freeze, execution, final, caseset, truth, prediction, prompt hashes |

## Original source paths (study root)

Prospective study root: `role_swap_cross_task/`  
Precursor root: `manuscript_benchmark/`  
Scientific freeze parent: `prospective_v5/01_V5_FREEZE/` (`GENOME_SKEPTIC_V5_VALIDATOR_REPAIR`)

## Omitted categories (intentional)

- Full per-case `GS_RUN/` trees (~275 MB of intermediate measurement outputs)
- `role_swap_cross_task/_work/` (FASTA downloads, caches, ~647 MB including `tetAB_ipg.txt`)
- Abandoned / exploratory experiments (annotator V1, FASTQ pipelines, D8/D12/D20, known-failure rescue, decision-authority PoC raw runs beyond reused adapters)
- Toy benchmarks, old notebooks, deprecated prompts, unused model experiments
- Virtual environments, `__pycache__`, temporary logs
- API keys / `.env` files / credential material
- Large HMM/DB caches beyond the small frozen family definition panels
- Genome assemblies (reconstruct via accession + SHA256)

## Missing dependencies / gaps

| Item | Status |
| --- | --- |
| Genome FASTA files | Omitted by design; retrieval instructions provided |
| Full `GS_RUN` measurement dumps | Omitted; not required for path A scoring from locked predictions |
| Live OpenAI / TypeSafe credentials | Not included (correct); required only for path B |
| Production bioinformatics binaries (diamond, HMMER, …) | Required only for path B / truth rebuild; not for locked scoring |
| Manuscript Word/PDF figure layout polish | Study FIGURE1–4 and precursor PNGs included; final journal layout may differ slightly from study numbering |
| Exact manuscript Figure 2 composite | Precursor source panels included; if the preprint used a hand-composed multi-panel figure, regenerate from `results/precursor/` + listed PNGs |

## Manuscript numerical claims — traceability

| Claim | Traced to | Status |
| --- | --- | --- |
| 20 genomes, 10 POS / 10 NEG | `data/prospective_truth.csv`, `results/statistics.json` | Traced |
| Arm B 18/20 | `results/statistics.json`, `results/controller_summary.csv` | Traced |
| Arm D 11/20 | same | Traced |
| 0 corrections / 7 degradations | `results/statistics.json` `b_vs_d` | Traced |
| 9 ABSENT→UNRESOLVED | `results/statistics.json` transitions; `results/role_swap_summary.csv` | Traced |
| McNemar *P* = 0.015625 | `results/statistics.json` | Traced |
| Paired diff −0.35; CI −0.55…−0.15 | `results/statistics.json` `paired_bootstrap_D_minus_B` | Traced |
| Follow-ups 57 / 39 / 74 | `results/controller_efficiency.csv` | Traced |
| Sol median latency 10.28 s; Jev 2.22 s | `results/controller_efficiency.csv` | Traced |
| Identical evidence B→D 20/20 | `data/arm_b_vs_d_evidence_hashes.csv`; prediction lock comparisons | Traced |
| Precursor: policy changed, endpoints same; 8 shared errors; 2 defects frozen before prospective | `results/precursor/*` | Traced (minimal set) |

Quick check (path A):

```bash
python paper_role_swap/scripts/scoring/verify_locked_claims.py
```

## Integrity checks performed

1. **SHA256 of copied scientific/result files** — `shutil.copy2` byte-identical to originals; `STUDY_MANIFEST.json` records digests.
2. **No scientific file modified** — originals under `role_swap_cross_task/`, `manuscript_benchmark/`, `src/` untouched; bundle is additive.
3. **Secrets** — no embedded API key values; adapters read `OPENAI_API_KEY` / `TYPESAFE_API_KEY` from the environment. Launch script references a local keyfile *path* only.
4. **Numerical claims** — verified against `results/statistics.json` and efficiency CSV (see table).
5. **Arm B ↔ Arm D evidence hashes** — 20/20 identical (`hashes_equal=True`).
6. **Bundle size** — ~5 MB, hundreds of compact files; no large development trees.

## Path A vs Path B

| Path | What it does | APIs |
| --- | --- | --- |
| **A (primary)** | Re-read locks; verify claims; inspect evidence hashes; use published stats/figures | None |
| **B (optional)** | Re-execute measurement / Sol / Jev via full repo scripts | Required |

Path B must not overwrite files in this bundle.

## Result that cannot currently be reproduced from the bundle alone

- **End-to-end re-measurement of genomes** without retrieving FASTAs and restoring the full production tool stack / package import layout expected by `run_role_swap_execution.py` (scripts still point at the full-repo `ROOT`). For manuscript claims, this is unnecessary: use path A.
- **Bitwise regeneration of scientific_core hash** requires the exact frozen family/orthology trees in their original package paths; the relevant files are copied under `config/frozen_config/` and `scripts/measurement/`, but hash recomputation should be run from the full repository checkout pinned to the V5 freeze commit.

## Conclusion

The bundle is sufficient to reproduce the **published analysis** of the role-swap manuscript from locked artifacts, including controller comparison numbers, identical-evidence role-swap statistics, precursor interpretive claims, and figure/table source data. Model-dependent re-execution remains optional and external to this bundle.
