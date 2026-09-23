# ROLE_SWAP STOP 3

**STATUS: COHORT + TRUTH LOCKED. STOPPED BEFORE ARM EXECUTION.**

Study: `ROLE_SWAP_TETA_V5_WITHIN_TASK`

## Completed

- Exclusion manifest built and audited (212 unique accessions)
- Fresh candidate pool screened (65 genomes)
- Independent Routes 1–2 truth assigned
- Final 20-case cohort locked (10 POSITIVE + 10 NEGATIVE)
- Prediction input written without truth
- Path guard: `scripts/role_swap_prediction_path_guard.py`
- Preflight V5 hash check: PASS

## Explicitly NOT done

- No INITIAL_EVIDENCE for study arms
- No Arm A–F execution
- No Sol / Jev calls
- No scoring / accuracy

## Locks

- CASESET LOCK: `02_CASES/ROLE_SWAP_CASESET_LOCK.json`
- TRUTH LOCK: `03_TRUTH/ROLE_SWAP_TRUTH_LOCK.json`

Await explicit authorisation before role-swap arm execution.
