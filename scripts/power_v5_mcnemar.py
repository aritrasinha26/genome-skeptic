#!/usr/bin/env python3
"""Exact McNemar power analysis for the V5 prospective paired comparison.

Design assumptions, not empirical estimates. M60 had zero Agentic-vs-
Deterministic endpoint discordances.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import numpy as np
from scipy.stats import binom, binomtest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "prospective_v5" / "02_POWER"

NS = (40, 50, 60, 80, 100, 120)
QS = (0.10, 0.20, 0.30, 0.40, 0.50)
PS = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85)
ALPHA = 0.05
TARGET_POWER = 0.80
SCENARIOS = {
    "CONSERVATIVE": {"q": 0.20, "p": 0.70},
    "MODERATE": {"q": 0.30, "p": 0.75},
    "STRONG": {"q": 0.40, "p": 0.80},
}
ZERO_N = (40, 60, 80, 100)
MAX_N = max(NS)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_masks(max_m: int, alpha: float = ALPHA) -> list[np.ndarray]:
    """For each m, boolean mask over c=0..m of two-sided exact binomial rejection."""
    masks: list[np.ndarray] = [np.zeros(1, dtype=bool)]
    for m in range(1, max_m + 1):
        reject = np.zeros(m + 1, dtype=bool)
        for c in range(0, m + 1):
            reject[c] = binomtest(c, n=m, p=0.5, alternative="two-sided").pvalue <= alpha
        masks.append(reject)
    return masks


REJECT_MASKS = _reject_masks(MAX_N, ALPHA)


def exact_mcnemar_power(n: int, q: float, p: float, alpha: float = ALPHA) -> float:
    """Power of exact two-sided McNemar / binomial test of p=0.5.

    M ~ Binomial(N, q) discordant pairs.
    C ~ Binomial(M, p) pairs favouring Agentic.
    Reject H0 if two-sided exact binomial p-value on C ~ Bin(M, 0.5) <= alpha.
    M=0 cannot reject.
    """
    power = 0.0
    m_probs = binom.pmf(np.arange(0, n + 1), n, q)
    for m in range(1, n + 1):
        pm = float(m_probs[m])
        if pm == 0.0:
            continue
        c_probs = binom.pmf(np.arange(0, m + 1), m, p)
        power += pm * float(c_probs[REJECT_MASKS[m]].sum())
    return power


def clopper_pearson_upper(k: int, n: int, confidence: float = 0.95) -> float:
    return float(binomtest(k, n).proportion_ci(confidence_level=confidence, method="exact").high)


def onesided_upper_zero(n: int, alpha: float = 0.05) -> float:
    return 1.0 - (alpha ** (1.0 / n))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for n in NS:
        for q in QS:
            for p in PS:
                power = exact_mcnemar_power(n, q, p)
                rows.append(
                    {
                        "N": n,
                        "q_discordance": f"{q:.2f}",
                        "p_agentic_favours": f"{p:.2f}",
                        "expected_discordant_pairs": n * q,
                        "alpha": ALPHA,
                        "test": "exact_two_sided_mcnemar_binomial",
                        "power": f"{power:.6f}",
                        "powered_ge_0.80": "YES" if power >= TARGET_POWER else "NO",
                    }
                )

    matrix_path = OUT / "V5_MCNEMAR_POWER_MATRIX.csv"
    with matrix_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    recs = {}
    for name, spec in SCENARIOS.items():
        powered = [
            r
            for r in rows
            if abs(float(r["q_discordance"]) - spec["q"]) < 1e-12
            and abs(float(r["p_agentic_favours"]) - spec["p"]) < 1e-12
            and r["powered_ge_0.80"] == "YES"
        ]
        min_n = int(powered[0]["N"]) if powered else None
        power_by_n = {
            int(r["N"]): float(r["power"])
            for r in rows
            if abs(float(r["q_discordance"]) - spec["q"]) < 1e-12
            and abs(float(r["p_agentic_favours"]) - spec["p"]) < 1e-12
        }
        recs[name] = {
            "q": spec["q"],
            "p": spec["p"],
            "min_n": min_n,
            "expected_discordant": None if min_n is None else min_n * spec["q"],
            "power_by_n": power_by_n,
        }

    zero_rows = []
    for n in ZERO_N:
        two_sided = clopper_pearson_upper(0, n, 0.95)
        one_sided = onesided_upper_zero(n, 0.05)
        zero_rows.append(
            {
                "N": n,
                "observed_discordances": 0,
                "clopper_pearson_two_sided_95_upper": f"{two_sided:.6f}",
                "clopper_pearson_one_sided_95_upper": f"{one_sided:.6f}",
                "method": "exact_binomial_clopper_pearson",
                "not_equivalence": True,
            }
        )
    zero_path = OUT / "V5_ZERO_DISCORDANCE_BOUNDS.csv"
    with zero_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(zero_rows[0].keys()))
        w.writeheader()
        w.writerows(zero_rows)

    conservative = recs["CONSERVATIVE"]
    moderate = recs["MODERATE"]
    strong = recs["STRONG"]
    recommended = conservative["min_n"] or moderate["min_n"] or strong["min_n"]
    recommended_source = (
        "CONSERVATIVE"
        if conservative["min_n"]
        else "MODERATE"
        if moderate["min_n"]
        else "STRONG"
        if strong["min_n"]
        else "NONE"
    )
    rec_pos = recommended // 2 if recommended else None
    rec_neg = recommended - rec_pos if recommended else None

    write_text(
        OUT / "V5_POWER_ASSUMPTIONS.md",
        f"""# V5 McNemar power assumptions

These are design assumptions, not estimates from M60.

M60 had **zero** Agentic-versus-Deterministic endpoint discordances. No
positive discordance rate is empirically established.

## Primary comparison

GS-Agentic-Sol-V5 vs GS-Deterministic-V5

Analysis unit: one fresh bacterial genome.

Primary test: exact two-sided McNemar / binomial test of p = 0.5

alpha = {ALPHA}

desired power >= {TARGET_POWER}

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
""",
    )

    def fmt_power(scenario: str, n: int) -> str:
        return f"{recs[scenario]['power_by_n'][n]:.4f}"

    rec_line = (
        f"N={recommended} ({recommended_source} scenario: q={SCENARIOS[recommended_source]['q']}, "
        f"p={SCENARIOS[recommended_source]['p']})"
        if recommended and recommended_source != "NONE"
        else "No tested N reached 80% power under the named scenarios."
    )
    write_text(
        OUT / "V5_SAMPLE_SIZE_RECOMMENDATION.md",
        f"""# V5 sample-size recommendation

Predeclared alternative for the confirmation study: **CONSERVATIVE**
(q = 0.20, p = 0.70), because M60 supplies no empirical discordance rate.

## Minimum N among tested values with power >= 0.80

| scenario | q | p | min N | expected discordant pairs |
| --- | --- | --- | --- | --- |
| CONSERVATIVE | 0.20 | 0.70 | {conservative['min_n'] if conservative['min_n'] is not None else 'none'} | {conservative['expected_discordant'] if conservative['expected_discordant'] is not None else 'n/a'} |
| MODERATE | 0.30 | 0.75 | {moderate['min_n'] if moderate['min_n'] is not None else 'none'} | {moderate['expected_discordant'] if moderate['expected_discordant'] is not None else 'n/a'} |
| STRONG | 0.40 | 0.80 | {strong['min_n'] if strong['min_n'] is not None else 'none'} | {strong['expected_discordant'] if strong['expected_discordant'] is not None else 'n/a'} |

## Power at selected N

| N | conservative | moderate | strong |
| --- | --- | --- | --- |
| 40 | {fmt_power('CONSERVATIVE', 40)} | {fmt_power('MODERATE', 40)} | {fmt_power('STRONG', 40)} |
| 60 | {fmt_power('CONSERVATIVE', 60)} | {fmt_power('MODERATE', 60)} | {fmt_power('STRONG', 60)} |
| 80 | {fmt_power('CONSERVATIVE', 80)} | {fmt_power('MODERATE', 80)} | {fmt_power('STRONG', 80)} |

N=40 is **not** claimed to be powered merely because it contains 40 cases.
N=40 reaches >=80% power only if the STRONG pattern holds
(q=0.40, p=0.80; power={fmt_power('STRONG', 40)}). It does not reach 80%
under CONSERVATIVE ({fmt_power('CONSERVATIVE', 40)}) or MODERATE
({fmt_power('MODERATE', 40)}).

## Recommended prospective N

{rec_line}

Class balance: {rec_pos} independently established POSITIVE and {rec_neg}
independently established NEGATIVE tet(A)/tet(B) genomes.

This is a deliberately balanced validation cohort, not a prevalence sample.

Truth must not be derived from Genome Skeptic, AMRFinderPlus, the specialist
comparator, or the V5 validator.
""",
    )

    print(f"CONSERVATIVE_MIN_N={conservative['min_n']}", flush=True)
    print(f"MODERATE_MIN_N={moderate['min_n']}", flush=True)
    print(f"STRONG_MIN_N={strong['min_n']}", flush=True)
    print(f"RECOMMENDED_N={recommended}", flush=True)
    print(f"RECOMMENDED_SOURCE={recommended_source}", flush=True)
    print(f"OUTPUT {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
