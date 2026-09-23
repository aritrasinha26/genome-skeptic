# ROLE_SWAP STOP 2

**STATUS: STOPPED BEFORE CASE SELECTION AND EXECUTION**

Study: `ROLE_SWAP_TETA_V5_WITHIN_TASK`  
Claim scope: **within-task tetA only**  
Scientific biology: **unchanged V5** (`GENOME_SKEPTIC_V5_VALIDATOR_REPAIR`)

## Locked at this stop

1. Protocol (`00_PROTOCOL/ROLE_SWAP_PROTOCOL.md`)
2. Truth rules (`00_PROTOCOL/ROLE_SWAP_TRUTH_PROTOCOL.md`)
3. Arms (`00_PROTOCOL/ROLE_SWAP_ARMS.md`)
4. Case-selection procedure (`00_PROTOCOL/ROLE_SWAP_CASE_SELECTION.md`) — procedure only
5. Scientific-core / validator / reference-panel / action-registry / planner /
   critic / model configuration hashes (`ROLE_SWAP_FREEZE_MANIFEST.json`)

## Explicitly NOT done

- No cases selected
- No assemblies downloaded for this study
- No INITIAL_EVIDENCE generated
- No Arm A–F execution
- No truth labels assigned
- No V5 biology modification
- No second biological target created

## Required confirmation to proceed to Phase 2

Explicit authorisation to:

1. Build and hash the exclusion manifest
2. Sample 20 fresh tetA candidates under the frozen selection procedure
3. Run independent truth Routes 1–2 and lock truth

Then halt again at STOP 3 before tool execution for study arms.
