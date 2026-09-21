# V5 prospective analysis plan

Frozen before cohort selection. No Genome Skeptic predictions were used
to choose genomes or to define truth.

## Primary target

Genuine tet(A)/tet(B) family presence/absence.

rpoB is not used as a natural positive/negative specificity endpoint.

No second target is invented for this confirmation study.

## Primary comparison

GS-Agentic-Sol-V5 versus GS-Deterministic-V5

Analysis unit: one fresh bacterial genome.

Primary hypothesis: among discordant pairs, the probability that Agentic
is correct and Deterministic is wrong differs from 0.5.

Primary test: exact two-sided McNemar / binomial test

alpha = 0.05

## Sample-size rule

Exact McNemar power was computed before sampling.

Recommended N = 120 under the MODERATE design assumption
(q=0.30, p=0.75), the smallest tested N with power >= 0.80 under a named
scenario that can actually be powered in the 40–120 grid.

The CONSERVATIVE assumption (q=0.20, p=0.70) does not reach 80% power at
any tested N.

N=40 is not retained as a powered design.

## Class balance

60 independently established POSITIVE

60 independently established NEGATIVE

Deliberately balanced validation cohort, not a prevalence sample.

## Secondary comparisons

1. GS-Agentic-Sol-V5 versus GS-Exhaustive-V5
   (evidence-state differences, endpoint differences, accuracy, action count)

2. GS-Agentic-Sol-V5 versus GS-Agentic-Sol-Decision-Authority
   (identical final evidence state; only final authority differs)
   This arm is not used for the primary sample-size calculation.

## Uncertain-truth handling

Cases with curator-adjudicated UNCERTAIN truth are excluded from the
primary evaluable denominator. They are reported separately and are not
rescored as correct or incorrect.

## Performance reporting

Per target, with raw numerators and denominators:

- sensitivity
- specificity
- PPV
- NPV
- balanced accuracy
- MCC
- overall accuracy as secondary

Constant baselines: always NEGATIVE; always POSITIVE.

No pooled accuracy without class decomposition.

## Adaptivity metrics (frozen before predictions)

Descriptive only. No post-hoc “good adaptivity” threshold.

Planner:

- number of unique first actions
- first-action distribution
- Shannon entropy of first-action distribution
- action distribution conditional on DiagnosticNeed
- action distribution conditional on evidence-state class
- action distribution conditional on target (tetA only in this study)

Critic:

- accept rate
- challenge rate
- second-action distribution

## Decision-authority comparison

Same genome, same initial measurements, same Planner, same Critic, same
follow-up actions, same final TargetMeasurements.

Only final authority differs:

- repaired deterministic V5 validator
- GPT-5.6 Sol, outputting exactly one of
  target_gene_detected / target_gene_not_detected / unresolved
  plus evidence_ids_used and a brief rationale

Any evidence ID not present in TargetMeasurements invalidates the call.

Report: same-evidence-state cases, endpoint discordances, each direction
of unique correctness, exact McNemar where applicable.

## Convergence if zero endpoint discordances

If observed endpoint discordances = 0, report the exact Clopper-Pearson
95% upper bound on the population discordance probability. This is
descriptive and is not an equivalence test.

## Interpretation gates

Remain those specified in the V5 protocol (Scenarios A–E). No threshold,
prompt, rule, reference, or case replacement after unblinding.

Any later scientific change is V6.
