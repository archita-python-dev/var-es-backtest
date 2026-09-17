"""One-day VaR and Expected Shortfall models.

All functions work in *loss-return* units: a result of 0.021 means a 2.1% loss of portfolio value.
Each returns {confidence_level: (var, es)}.

Portfolio returns use simple (not log) returns: with fixed weights, the portfolio's simple
return is exactly the weighted sum of the stocks' simple returns, so no approximation is needed.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
from scipy import stats

RiskEstimates = dict[float, tuple[float, float]]


def empirical_var_es(losses: np.ndarray, levels: Iterable[float]) -> RiskEstimates:
    """VaR is the loss quantile; ES is the average of losses at or beyond it."""
    out = {}
    for a in levels:
        var = float(np.quantile(losses, a))
        out[a] = (var, float(losses[losses >= var].mean()))
    return out


def historical(window_returns: np.ndarray, weights: np.ndarray, levels: Iterable[float]) -> RiskEstimates:
    """Revalue today's portfolio on every day of the estimation window."""
    return empirical_var_es(-(window_returns @ weights), levels)


def parametric_normal(window_returns: np.ndarray, weights: np.ndarray, levels: Iterable[float]) -> RiskEstimates:
    """Variance-covariance method: portfolio return ~ Normal(w'mu, w'Sigma w)."""
    mu = window_returns.mean(axis=0) @ weights
    sigma = float(np.sqrt(weights @ np.cov(window_returns, rowvar=False) @ weights))
    out = {}
    for a in levels:
        z = stats.norm.ppf(a)
        out[a] = (-mu + sigma * z, -mu + sigma * stats.norm.pdf(z) / (1 - a))
    return out


def fit_t_df(portfolio_returns: np.ndarray, bounds: tuple[float, float]) -> float:
    """Maximum-likelihood Student-t degrees of freedom for the portfolio's return history."""
    df, _, _ = stats.t.fit(portfolio_returns)
    return float(np.clip(df, *bounds))


def monte_carlo_t(
    window_returns: np.ndarray,
    weights: np.ndarray,
    levels: Iterable[float],
    n_sims: int,
    rng: np.random.Generator,
    df_bounds: tuple[float, float] = (3.0, 30.0),
) -> tuple[RiskEstimates, float]:
    """Simulate all stocks jointly from a multivariate Student-t, then revalue the portfolio.

    The t distribution keeps the historical means and covariance but produces extreme days
    more often than a normal distribution, controlled by the degrees of freedom (fitted daily).
    Returns the estimates and the fitted degrees of freedom.
    """
    mu = window_returns.mean(axis=0)
    cov = np.cov(window_returns, rowvar=False)
    df = fit_t_df(window_returns @ weights, df_bounds)

    chol = _cholesky(cov)
    z = rng.standard_normal((n_sims, len(mu))) @ chol.T
    mixing = np.sqrt(rng.chisquare(df, n_sims) / df)
    # Scale so the simulated covariance equals the sample covariance (a raw t has variance df/(df-2)).
    sims = mu + np.sqrt((df - 2) / df) * z / mixing[:, None]
    return empirical_var_es(-(sims @ weights), levels), df


def _cholesky(cov: np.ndarray) -> np.ndarray:
    """Cholesky factor, adding a tiny diagonal jitter if the sample covariance is near-singular."""
    jitter = 0.0
    for _ in range(6):
        try:
            return np.linalg.cholesky(cov + jitter * np.eye(len(cov)))
        except np.linalg.LinAlgError:
            jitter = max(jitter * 10, 1e-10)
    raise np.linalg.LinAlgError("covariance matrix is not positive definite")
