# CURRENT_LACZ_LIMITATION

Recorded for Agentic V3 before any fresh external benchmark.
This is not a target-specific patch and must remain visible.

```
CURRENT_LACZ_LIMITATION:
No frozen deterministic instrument currently distinguishes true LacZ
orthology from relevant competing beta-galactosidase families when
reference/GFF/orthology resources are absent.
```

## Why this remains a toolbox gap

- Packaged `lacZ_beta_galactosidase` declares no `competing_families`.
- `competitive_family` therefore has no curated competitor family to score.
- Reciprocal-best-hit, synteny, and reference-locus actions require
  reference proteins and/or GFF, which are absent in the empty-reference
  external protocol.
- No generic glycosyl-hydrolase / competing beta-galactosidase family is
  packaged as a frozen instrument.

Do not add a lacZ-specific hack to close this gap. Close it only with a
generic family-identity or orthology instrument that would apply to any
target with the same missing competitor/reference resources.
