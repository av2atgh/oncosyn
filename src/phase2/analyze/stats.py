"""Statistical helpers for the analyze stage (scipy-backed).

Kept small and dependency-localized so the estimators are unit-testable and the
rest of analyze reads cleanly.
"""
from __future__ import annotations

from math import prod, sqrt

from scipy import stats


def pooled_rate(n_events: int, n_at_risk: int, ci: float = 0.95) -> tuple[float, float, float]:
    """Bayesian Beta posterior mean + credible interval for a response rate.

    Jeffreys prior Beta(0.5, 0.5); posterior Beta(events+0.5, non-events+0.5).
    Returns (mean, ci_low, ci_high) as fractions.
    """
    a = n_events + 0.5
    b = (n_at_risk - n_events) + 0.5
    mean = a / (a + b)
    lo = (1 - ci) / 2
    return mean, float(stats.beta.ppf(lo, a, b)), float(stats.beta.ppf(1 - lo, a, b))


def bliss_expected(rates: list[float]) -> float:
    """Bliss-independence expected combination response: 1 - prod(1 - r)."""
    return 1.0 - prod(1.0 - r for r in rates)


def bliss_expected_ci(
    components: list[tuple[float, int]], ci: float = 0.95
) -> tuple[float, float, float]:
    """Expected combination ORR with a delta-method CI.

    components: list of (rate, n) for each single agent. Var(rate)=r(1-r)/n;
    propagated through q = 1 - prod(1-r_i) via partials dq/dr_i = prod_{j!=i}(1-r_j).
    Returns (expected, ci_low, ci_high), clipped to [0, 1].
    """
    rates = [r for r, _ in components]
    q = bliss_expected(rates)
    surv = [1.0 - r for r in rates]
    var = 0.0
    for i, (r, n) in enumerate(components):
        if n <= 0:
            continue
        partial = prod(surv[j] for j in range(len(surv)) if j != i)
        var += (partial ** 2) * (r * (1.0 - r) / n)
    z = stats.norm.ppf(1 - (1 - ci) / 2)
    half = z * sqrt(var)
    return q, max(0.0, q - half), min(1.0, q + half)


def binom_test_two_sided(n_events: int, n_at_risk: int, p_null: float) -> float:
    """Two-sided exact binomial test of observed responses vs a null rate."""
    p_null = min(1.0, max(0.0, p_null))
    return float(stats.binomtest(n_events, n_at_risk, p_null,
                                 alternative="two-sided").pvalue)
