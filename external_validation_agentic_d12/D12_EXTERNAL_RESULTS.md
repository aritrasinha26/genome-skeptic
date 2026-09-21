# D12 external results

Prospective blinded twelve-case external benchmark (`V3_D12_EXTERNAL`).
n = 12 is small. Wilson 95% intervals are descriptive only. No superiority claim is made.
Predictions were not regenerated. V3 was not modified. D20 was not accessed.

## Lock verification

| File | SHA256 | Result |
|---|---|---|
| `D12_MANIFEST.json` | `54b477d3cf8197ffa73d7ffb2e94ffe4a993b861565a3266085d33ae68b0546f` | MATCH |
| `D12_CONVENTIONAL_LOCKED.json` | `9cd5657a0e24e877f20f3ad83ec34d495231c1d0f2897336861999d9f4082f57` | MATCH |
| `D12_V5_LOCKED.json` | `66652425bbdff574f91c9da19876c02f7a684653a9096f65bd44a95745dfead4` | MATCH |
| `D12_AGENTIC_V3_LOCKED.json` | `64a2dd3365805d68f431f487d9aebd7cb685466096d1710d67d962895c3cc25c` | MATCH |
| `D12_EXTERNAL_TRUTH_LOCKED.json` | `88692ec927f0c40d9911a8dc95f809912c7a22da1fc6f64eef68e68d652819f6` | LOCKED before prediction join |

Confirmed before truth assignment: 12 Conventional, 12 V5, 12 Agentic V3 records. Agentic completion 12/12.

## Target-specific scored endpoints (V5 vs Agentic V3)

| Pos | Target | V5 scored endpoint | Agentic V3 scored endpoint | Identical |
|---:|---|---|---|---|
| 1 | `tetA_tetracycline_efflux` | DETECTED | DETECTED | YES |
| 2 | `rpoB_RNAP_beta` | DETECTED | DETECTED | YES |
| 3 | `tetA_tetracycline_efflux` | DETECTED | DETECTED | YES |
| 4 | `rpoB_RNAP_beta` | DETECTED | DETECTED | YES |
| 5 | `lacZ_beta_galactosidase` | DETECTED | DETECTED | YES |
| 6 | `tuf_EF_Tu` | MULTIPLICITY=0 | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | YES |
| 7 | `lacZ_beta_galactosidase` | DETECTED | DETECTED | YES |
| 8 | `lacZ_beta_galactosidase` | DETECTED | DETECTED | YES |
| 9 | `tuf_EF_Tu` | MULTIPLICITY=0 | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | YES |
| 10 | `rpoB_RNAP_beta` | DETECTED | DETECTED | YES |
| 11 | `tetA_tetracycline_efflux` | DETECTED | DETECTED | YES |
| 12 | `tuf_EF_Tu` | MULTIPLICITY=0 | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | YES |

TARGET-SPECIFIC ENDPOINTS IDENTICAL: **12 / 12**
DIFFERENT ENDPOINT CASES: none

tetA is scored as FAMILY presence/absence (tet(A) or tet(B) only).
rpoB and lacZ are scored as orthologous-gene presence/absence.
tuf is scored as exact multiplicity of distinct genuine EF-Tu loci.
The Agentic V3 lock file does not store `multiplicity`; tuf Agentic scores use polarity fallback (NOT_DETECTED → 0, DETECTED → 1) unless a multiplicity field is present.

## External truth (independent of predictions)

| Pos | Accession | Target | Endpoint | Truth |
|---:|---|---|---|---|
| 1 | GCF_060416925.1 | tetA_tetracycline_efflux | FAMILY_PRESENCE_ABSENCE | **NEGATIVE** |
| 2 | GCF_057626335.1 | rpoB_RNAP_beta | ORTHOLOGOUS_GENE_PRESENCE_ABSENCE | **POSITIVE** |
| 3 | GCF_053795755.1 | tetA_tetracycline_efflux | FAMILY_PRESENCE_ABSENCE | **NEGATIVE** |
| 4 | GCF_047943045.1 | rpoB_RNAP_beta | ORTHOLOGOUS_GENE_PRESENCE_ABSENCE | **POSITIVE** |
| 5 | GCF_058596135.1 | lacZ_beta_galactosidase | ORTHOLOGOUS_GENE_PRESENCE_ABSENCE | **POSITIVE** |
| 6 | GCF_059683705.1 | tuf_EF_Tu | EXACT_MULTIPLICITY | **1** |
| 7 | GCF_048585425.2 | lacZ_beta_galactosidase | ORTHOLOGOUS_GENE_PRESENCE_ABSENCE | **NEGATIVE** |
| 8 | GCF_046562475.1 | lacZ_beta_galactosidase | ORTHOLOGOUS_GENE_PRESENCE_ABSENCE | **POSITIVE** |
| 9 | GCF_052955985.1 | tuf_EF_Tu | EXACT_MULTIPLICITY | **2** |
| 10 | GCF_050871785.1 | rpoB_RNAP_beta | ORTHOLOGOUS_GENE_PRESENCE_ABSENCE | **POSITIVE** |
| 11 | GCF_054055795.1 | tetA_tetracycline_efflux | FAMILY_PRESENCE_ABSENCE | **NEGATIVE** |
| 12 | GCF_049340285.1 | tuf_EF_Tu | EXACT_MULTIPLICITY | **0** |

Truth assignment used NCBI Gene Orthologs where indexed, independent post-lock phmmer of frozen/authentic seeds against each proteome, and NCBI RefSeq/PGAP AMR gene calls (AMRFinderPlus/NCBIfam-AMRFinder) for tet(A)/tet(B) only. tet(C) was not counted. PGAP names were corroboration only.

## Case-level results

| Pos | Accession | Target | Truth | Conventional | Conv correct? | V5 | V5 correct? | Agentic | Agentic correct? | Agentic completed? |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | GCF_060416925.1 | `tetA_tetracycline_efflux` | **NEGATIVE** | NOT_DETECTED | yes | DETECTED | no | DETECTED | no | yes |
| 2 | GCF_057626335.1 | `rpoB_RNAP_beta` | **POSITIVE** | NOT_DETECTED | no | DETECTED | yes | DETECTED | yes | yes |
| 3 | GCF_053795755.1 | `tetA_tetracycline_efflux` | **NEGATIVE** | NOT_DETECTED | yes | DETECTED | no | DETECTED | no | yes |
| 4 | GCF_047943045.1 | `rpoB_RNAP_beta` | **POSITIVE** | NOT_DETECTED | no | DETECTED | yes | DETECTED | yes | yes |
| 5 | GCF_058596135.1 | `lacZ_beta_galactosidase` | **POSITIVE** | NOT_DETECTED | no | DETECTED | yes | DETECTED | yes | yes |
| 6 | GCF_059683705.1 | `tuf_EF_Tu` | **1** | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | no | MULTIPLICITY=0 | no | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | no | yes |
| 7 | GCF_048585425.2 | `lacZ_beta_galactosidase` | **NEGATIVE** | NOT_DETECTED | yes | DETECTED | no | DETECTED | no | yes |
| 8 | GCF_046562475.1 | `lacZ_beta_galactosidase` | **POSITIVE** | NOT_DETECTED | no | DETECTED | yes | DETECTED | yes | yes |
| 9 | GCF_052955985.1 | `tuf_EF_Tu` | **2** | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | no | MULTIPLICITY=0 | no | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | no | yes |
| 10 | GCF_050871785.1 | `rpoB_RNAP_beta` | **POSITIVE** | NOT_DETECTED | no | DETECTED | yes | DETECTED | yes | yes |
| 11 | GCF_054055795.1 | `tetA_tetracycline_efflux` | **NEGATIVE** | NOT_DETECTED | yes | DETECTED | no | DETECTED | no | yes |
| 12 | GCF_049340285.1 | `tuf_EF_Tu` | **0** | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | yes | MULTIPLICITY=0 | yes | MULTIPLICITY=0 (lock omitted multiplicity; inferred from polarity) | yes | yes |

tuf cases are scored on exact multiplicity. Conventional has no copy-number field; `not_detected` is scored as multiplicity 0.

## Primary results

- Externally evaluable: **12 / 12**
- TRUTH_UNCERTAIN: **0**
- Conventional: **5 / 12** (accuracy 0.417; Wilson 95% CI 0.193–0.680)
- Deterministic V5: **6 / 12** (accuracy 0.500; Wilson 95% CI 0.254–0.746)
- Agentic V3 end-to-end: **6 / 12** (accuracy 0.500; Wilson 95% CI 0.254–0.746)
- Agentic completion: **12 / 12**

In this prospective blinded twelve-case external benchmark, Agentic V3 achieved 6/12 correct compared with 6/12 for V5 and 5/12 for the conventional baseline.

## Paired V5 vs Agentic V3

- A (both correct) = 6: pos 2, pos 4, pos 5, pos 8, pos 10, pos 12
- B (V5 correct, Agentic incorrect) = 0: none
- C (V5 incorrect, Agentic correct) = 0: none
- D (both incorrect) = 6: pos 1, pos 3, pos 6, pos 7, pos 9, pos 11

- V5 ERRORS CORRECTED BY AGENTIC = C = **0**
- V5 CORRECT CALLS DEGRADED BY AGENTIC = B = **0**
- NET CORRECTIONS = C − B = **0**

Agentic V3 corrected 0 V5 errors and degraded 0 V5-correct cases.
exact McNemar not applicable (0 discordant pairs); exploratory n=12.

## Dual-error cases

- pos 1 `GCF_060416925.1` / `tetA_tetracycline_efflux` class=VALIDATOR_DECISION_LIMIT
- pos 3 `GCF_053795755.1` / `tetA_tetracycline_efflux` class=VALIDATOR_DECISION_LIMIT
- pos 6 `GCF_059683705.1` / `tuf_EF_Tu` class=VALIDATOR_DECISION_LIMIT
- pos 7 `GCF_048585425.2` / `lacZ_beta_galactosidase` class=MISSING_SCIENTIFIC_INSTRUMENT
- pos 9 `GCF_052955985.1` / `tuf_EF_Tu` class=VALIDATOR_DECISION_LIMIT
- pos 11 `GCF_054055795.1` / `tetA_tetracycline_efflux` class=VALIDATOR_DECISION_LIMIT

See `D12_ERROR_ANALYSIS.md`.

This n=12 benchmark does not establish general genome-wide performance.

