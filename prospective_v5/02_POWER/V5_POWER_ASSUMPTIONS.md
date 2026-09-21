# V5 McNemar power assumptions

These are design assumptions, not estimates from M60.

M60 had **zero** Agentic-versus-Deterministic endpoint discordances. No
positive discordance rate is empirically established.

## Primary comparison

GS-Agentic-Sol-V5 vs GS-Deterministic-V5

Analysis unit: one fresh bacterial genome.

Primary test: exact two-sided McNemar / binomial test of p = 0.5

alpha = 0.05

desired power >= 0.8

## Model

M ~ Binomial(N, q) discordant pairs

C | M=m ~ Binomial(m, p)

H0: among discordant pairs, P(Agentic correct and Deterministic wrong) = 0.5

Power is the probability of rejecting H0, averaged over M.

## Scenarios

| name | q | p | meaning |
| --- | --- | --- | --- |
| CONSERVATIVE | 0.20 | 0.70 | 20% discordance; 70% of discordances favour Agentic |
| MODERATE | 0.30 | 0.75 | 30% discordance; 75% favour Agentic |
| STRONG | 0.40 | 0.80 | 40% discordance; 80% favour Agentic |

The Decision-Authority arm is a prespecified secondary comparison and is
not used for this sample-size calculation.
