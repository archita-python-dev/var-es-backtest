"""Statistical backtests for VaR breaches."""

from __future__ import annotations

import numpy as np
from scipy import stats
from scipy.special import xlogy


def kupiec_pof(breaches: int, days: int, level: float) -> tuple[float, float]:
    """Kupiec proportion-of-failures test.

    Null hypothesis: the true breach rate equals 1 - level. Returns (LR statistic, p-value);
    a p-value below 0.05 means the number of breaches is inconsistent with the confidence level.
    """
    p = 1 - level
    x, n = breaches, days
    rate = x / n
    log_l0 = xlogy(n - x, 1 - p) + xlogy(x, p)
    log_l1 = xlogy(n - x, 1 - rate) + xlogy(x, rate)
    lr = float(max(-2 * (log_l0 - log_l1), 0.0))
    return lr, float(stats.chi2.sf(lr, df=1))


def christoffersen_independence(breach_flags: np.ndarray) -> tuple[float, float]:
    """Christoffersen test that breaches are not clustered in time.

    Null hypothesis: whether today is a breach does not depend on yesterday. A low p-value
    means breaches bunch together, i.e. the model reacts too slowly to a change in volatility.
    Returns (nan, nan) when there are no breaches (nothing to test).
    """
    flags = np.asarray(breach_flags, dtype=int)
    if flags.sum() == 0:
        return float("nan"), float("nan")
    prev, curr = flags[:-1], flags[1:]
    n00 = int(np.sum((prev == 0) & (curr == 0)))
    n01 = int(np.sum((prev == 0) & (curr == 1)))
    n10 = int(np.sum((prev == 1) & (curr == 0)))
    n11 = int(np.sum((prev == 1) & (curr == 1)))

    pi01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)

    log_l0 = xlogy(n00 + n10, 1 - pi) + xlogy(n01 + n11, pi)
    log_l1 = xlogy(n00, 1 - pi01) + xlogy(n01, pi01) + xlogy(n10, 1 - pi11) + xlogy(n11, pi11)
    lr = float(max(-2 * (log_l0 - log_l1), 0.0))
    return lr, float(stats.chi2.sf(lr, df=1))


def traffic_light(breaches: int, days: int, level: float) -> str:
    """Basel traffic-light zone from the cumulative binomial probability of the breach count.

    Basel defines the zones for 99% VaR over 250 days (green 0-4, yellow 5-9, red 10+);
    the same probability cut-offs (95% and 99.99%) are applied here to every confidence level.
    """
    cumulative = round(float(stats.binom.cdf(breaches, days, 1 - level)), 4)
    if cumulative < 0.95:
        return "Green"
    if cumulative < 0.9999:
        return "Yellow"
    return "Red"
