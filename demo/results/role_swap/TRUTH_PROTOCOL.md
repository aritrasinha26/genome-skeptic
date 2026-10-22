# ROLE-SWAP TRUTH PROTOCOL — tetA (FROZEN AT STOP 2)

**Status:** Frozen before case selection.  
**Independence rule:** Truth must not use Genome Skeptic endpoint outputs, Sol,
Jev, the deterministic validator under evaluation, or any model being scored.

---

## BIOLOGICAL QUESTION

Is there a **genuine frozen tet(A)/tet(B) family member** in the assembly?

- POSITIVE = yes (family membership of P02980/P02982 class, not generic Tet resistance)
- NEGATIVE = no
- TRUTH_UNCERTAIN = cannot resolve confidently → do **not** force into POS/NEG

If fewer than 10+10 resolved cases remain after adjudication, draw additional
candidates under the frozen case-selection procedure until 10+10 resolve, or
STOP and report shortfall.

---

## TWO INDEPENDENT EVIDENCE ROUTES (tetA)

Canonical names (aligned with M60 truth methods):

### Route 1 — `target_vs_competitor_sequence_reference`

Recover candidate ORFs from the study assembly (independent of GS prediction
JSON). Compare against:

- Frozen tet(A)/tet(B) panel: UniProt P02980, P02982 and packaged
  `tetA_tetracycline_efflux` members
- Competing MFS / RND / non-target tet-class references from the frozen
  competitor packaging and/or curated specialist panels frozen at truth-source
  freeze time

A generic MFS match is **not** sufficient for POSITIVE.

### Route 2 — `independent_profile_or_phylogenetic_placement`

HMMER (or equivalent) placement on frozen tetA vs competitor profiles;
FastTree (or equivalent) when alignment succeeds and placement is borderline.

Remote HMM alone is **not** sufficient for POSITIVE.

---

## DECISION GATES (NUMERIC — MATCH M60 / V5 TRUTH GATES)

These are truth-adjudication gates. They intentionally overlap published GS
thresholds for the same biological question; that is acknowledged circularity
risk for endpoint *definition*, not permission to open GS predictions.

| Gate | Value |
|------|-------|
| Gene AA min identity | 0.60 |
| Gene AA min query coverage | 0.80 |
| Length ratio | 0.80–1.20 |
| Family competitive margin | 0.10 |
| Ambiguous band | 0.05 |
| HMM min gate model coverage | 0.20 |
| HMM domain-only max coverage | 0.45 |
| Sequence-decisive identity×coverage | ≥ 0.70 |
| Sequence-decisive competitor delta | ≥ 0.20 |

---

## ADJUDICATION RULES

1. Both routes POSITIVE → POSITIVE (if no hard conflict).
2. Both routes NEGATIVE → NEGATIVE.
3. Discordant routes → second pass over the **same** evidence records; if still
   unresolved → TRUTH_UNCERTAIN.
4. Borderline identity/coverage inside near-threshold bands without decisive
   architecture → TRUTH_UNCERTAIN.
5. Pseudogene / partial CDS matching target → TRUTH_UNCERTAIN (not POS, not NEG).
6. Other tet classes (tet(C), tetA(P), tet(M), …) without tet(A)/tet(B) family
   membership → NEGATIVE for this endpoint.
7. Competitor-preferred MFS/RND without tetA support → NEGATIVE.
8. Do not use AMRFinderPlus, PGAP gene symbols, or GS validator polarity as
   **truth**. Specialist databases may inform **candidate enrichment** during
   case selection only; final labels require Routes 1–2.

---

## ORDER OF OPERATIONS (BINDING)

1. Freeze this protocol (STOP 2) — **done at this phase**.
2. Select candidate assemblies under `ROLE_SWAP_CASE_SELECTION.md` without
   opening GS arm predictions.
3. Freeze truth **sources** (panels, HMMs, UniProt retrievals) with SHA256.
4. Run Routes 1–2 blinded to all study-arm predictions.
5. Lock `ROLE_SWAP_TRUTH.csv` + `ROLE_SWAP_TRUTH_LOCK.json`.
6. Only then proceed to INITIAL_EVIDENCE and arms (after STOP 3 clearance).

Flags required in truth lock sidecars:

- `gs_predictions_used_as_truth: false`
- `sol_used_as_truth: false`
- `jev_used_as_truth: false`
- `deterministic_validator_used_as_truth: false`
- `amrfinder_used_as_truth: false`
- `pgap_used_as_truth: false`

---

## PREFERRED EXTERNAL RESOURCES (NON-GS)

Use the strongest available independent route for each case. Prefer:

- Curated specialist AMR gene databases (CARD, ResFinder / similar) for
  enrichment and corroboration notes
- Manual evidence review against frozen panels
- Orthology / phylogenetic placement (Route 2)
- Independent annotation resources when available

Do not copy Genome Skeptic claim polarity into truth.

---

## KNOWN BIAS DISCLOSURE (NOT A RULE CHANGE)

Frozen V5 retains residual tetA false-negative risk on hard positives
(historical M60 positions 14, 19, 37, 41, 44 and related mechanism). This study
does **not** retune those rules. Residual FN risk is a disclosed property of the
frozen deterministic judge, not a selection criterion.
