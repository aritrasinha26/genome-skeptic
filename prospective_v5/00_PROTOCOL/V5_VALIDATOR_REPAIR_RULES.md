# V5 validator repair — BEFORE / AFTER rule logic

DEVELOPMENT / POST-HOC
NOT VALIDATION

M60 was used only as development evidence because its truth and errors are
already known. These rules are the minimum decision-layer correction of the
two independently verified defects. No search tools, reference panels,
prompts, action registry, follow-up limits, or scientific measurements were
changed. No iterative score tuning was performed.

## Defect A — tet(A) family-state polarity / decisiveness

### Verified mechanism

`discriminate_family` can write `target_family_supported` and also append
`best competing family did not pass the family gate and is not treated as
an alternative identity` when a weak competitor fails the family gate.

`family_identity_is_decisive` then treated that same string as a conflict
and compared `_DECISIVE_IDENTITY_PRODUCT` (0.70) to
`target_family_sequence_coverage` alone, not to the identity-product the
discriminator already uses (`identity × coverage`).

`refine_weak_family_classification` therefore rewrote
`target_family_supported` → `ambiguous_family`.
`family_detects_orthologue` treats `ambiguous_family` as a hard negative,
and pairwise identity cannot restore presence.

Locked M60 case 13: target score 0.9839, identity 0.99751, coverage 0.941,
competitors failed the gate, final class `ambiguous_family`, endpoint
NEGATIVE.

### BEFORE

```
if classification == competing_family_preferred: decisive
if classification != target_family_supported: not decisive
if coverage < 0.70: not decisive
if any conflict contains "did not pass the family gate": not decisive
else: decisive
```

### AFTER

```
if classification == competing_family_preferred: decisive
if classification != target_family_supported: not decisive
if (stored identity × coverage) < 0.70: not decisive
else: decisive
```

A competitor that failed the family gate is not evidence against the
target. The 0.70 comparison is the identity-product, using identity
already stored on the competitive blob or the parent reconstruction.

## Defect B — rpoB representation conflict

### Verified mechanism

Locked M60 case 48 stores two profile-coverage values on the same ORF:

- `reconstruction.hmm_coverage` = 0.4038 (chain-union)
- `best_hmm.model_coverage` = 0.8845 (ORF-level profile; score 1610.5)

`classify_architecture` consumed only the reconstruction value. Because
0.4038 ≤ `hmm_domain_only_max_model_coverage` (0.45), architecture became
`domain_only`. The reconstruction override then forced
`supports_orthologue=False` despite `exact_strong_homolog` and strong
profile/homology evidence.

### BEFORE

```
hmm_cov = reconstruction.hmm_coverage
if 0 < hmm_cov <= 0.45 and not frameshift/edge/multi-contig:
    architecture = domain_only
```

### AFTER

```
hmm_cov = reconstruction.hmm_coverage
if best_hmm.model_coverage exists on the same ORF:
    hmm_cov = max(reconstruction.hmm_coverage, best_hmm.model_coverage)
# existing architecture rules unchanged
```

The stored chain-union measurement is not rewritten. Architecture
classification simply does not prefer the lower same-ORF reconstruction
value.

## What was not changed

- search tools, HMM instruments, reference panels
- LLM prompts, action registry, follow-up limits
- scientific measurement generation
- unrelated thresholds
- M60 locks, truth, results, Sol ablation, forensic outputs
