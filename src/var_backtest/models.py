"""One-day VaR and Expected Shortfall models.

All models work in *loss-return* units: a result of 0.021 means a 2.1% loss of portfolio value.
Each returns {confidence_level: (var, es)}.

Portfolio returns use simple (not log) returns: with fixed weights, the portfolio's simple
return is exactly the weighted sum of the stocks' simple returns, so no approximation is needed.

Every model for a given forecast day reads its inputs from one shared `WindowMoments`, so the
sample covariance matrix is built once per day rather than once per model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import cached_property
from typing import Iterable

import numpy as np
from scipy import stats

RiskEstimates = dict[float, tuple[float, float]]

DF_BOUNDS = (3.0, 30.0)  # Student-t needs df > 2 for finite variance; above ~30 it is a normal


# --- shared inputs ----------------------------------------------------------------------------
class WindowMoments:
    """Inputs for a single forecast day, computed once and reused by every model.

    The sample covariance is the expensive piece (a 1,240 x 100 matrix product), so it is built
    lazily and cached here. The EWMA covariance is supplied by `EwmaCovariance`, which rolls it
    forward across the whole backtest in one pass instead of rebuilding it per day.
    """

    def __init__(self, returns: np.ndarray, weights: np.ndarray,
                 ewma_cov: np.ndarray | None = None, ewma_vol: np.ndarray | None = None):
        self.returns = returns          # window of daily stock returns, oldest first
        self.weights = weights
        self._ewma_cov = ewma_cov       # EWMA covariance as at the forecast day
        self._ewma_vol = ewma_vol       # trailing EWMA portfolio vol for each window day

    @cached_property
    def portfolio_returns(self) -> np.ndarray:
        return self.returns @ self.weights

    @cached_property
    def losses(self) -> np.ndarray:
        return -self.portfolio_returns

    @cached_property
    def mean(self) -> np.ndarray:
        return self.returns.mean(axis=0)

    @cached_property
    def cov(self) -> np.ndarray:
        return np.cov(self.returns, rowvar=False)

    @cached_property
    def portfolio_mean(self) -> float:
        return float(self.mean @ self.weights)

    @cached_property
    def portfolio_sigma(self) -> float:
        """Portfolio volatility from the sample covariance: sqrt(w' Sigma w)."""
        return float(np.sqrt(self.weights @ self.cov @ self.weights))

    @property
    def ewma_cov(self) -> np.ndarray:
        if self._ewma_cov is None:
            raise ValueError("no EWMA covariance supplied for this day")
        return self._ewma_cov

    @cached_property
    def ewma_sigma(self) -> float:
        """Portfolio volatility from the EWMA covariance: recent days carry more weight."""
        return float(np.sqrt(self.weights @ self.ewma_cov @ self.weights))

    @cached_property
    def standardised_returns(self) -> np.ndarray:
        """Window returns divided by the EWMA volatility of their own day.

        Dividing out the volatility of the time leaves residuals whose remaining fat tails are
        what the Student-t degrees of freedom should describe.
        """
        if self._ewma_vol is None:
            raise ValueError("no EWMA volatility series supplied for this day")
        vol = np.where(self._ewma_vol > 0, self._ewma_vol, np.nan)
        z = self.portfolio_returns / vol
        return z[np.isfinite(z)]


class EwmaCovariance:
    """RiskMetrics EWMA covariance, rolled forward once across the whole sample.

    Sigma_t = lam * Sigma_(t-1) + (1 - lam) * r_(t-1) r_(t-1)'

    Each forecast day reads the matrix as it stood *before* that day's return, so no future
    information enters. Seeded with the covariance of the first `burn_in` days.
    """

    def __init__(self, returns: np.ndarray, lam: float = 0.94, burn_in: int = 60):
        if not 0 < lam < 1:
            raise ValueError("EWMA lambda must be between 0 and 1")
        self.lam = lam
        n_days, n_assets = returns.shape
        burn_in = min(burn_in, n_days)

        self._snapshots = np.empty((n_days, n_assets, n_assets))
        cov = np.cov(returns[:burn_in], rowvar=False)
        for t in range(n_days):
            self._snapshots[t] = cov                       # state before day t's return is seen
            r = returns[t][:, None]
            cov = lam * cov + (1 - lam) * (r @ r.T)

    def at(self, index: int) -> np.ndarray:
        return self._snapshots[index]

    def portfolio_vol(self, weights: np.ndarray) -> np.ndarray:
        """Trailing EWMA portfolio volatility for every day, as sqrt(w' Sigma_t w)."""
        var = np.einsum("i,tij,j->t", weights, self._snapshots, weights)
        return np.sqrt(np.maximum(var, 0.0))


# --- tail estimation --------------------------------------------------------------------------
def fit_t_df_moments(x: np.ndarray, bounds: tuple[float, float] = DF_BOUNDS) -> float:
    """Degrees of freedom from excess kurtosis: k = 6 / (df - 4), so df = 6 / k + 4.

    Much cheaper than maximum likelihood, which needs a numerical optimiser on every window.
    Thin-tailed samples (k <= 0) get the upper bound, which behaves like a normal distribution.
    """
    k = float(stats.kurtosis(x, fisher=True, bias=False))
    df = 6.0 / k + 4.0 if k > 0 else bounds[1]
    return float(np.clip(df, *bounds))


def fit_t_df_mle(x: np.ndarray, bounds: tuple[float, float] = DF_BOUNDS) -> float:
    """Maximum-likelihood degrees of freedom. More accurate, far slower than the moment estimate."""
    df, _, _ = stats.t.fit(x)
    return float(np.clip(df, *bounds))


def student_t_var_es(mu: float, sigma: float, df: float, levels: Iterable[float]) -> RiskEstimates:
    """Closed-form VaR and ES for a Student-t with mean `mu` and standard deviation `sigma`.

    The t is rescaled by sqrt((df - 2) / df) so its standard deviation is exactly sigma; the
    ES formula is the standard tail expectation of a Student-t.
    """
    scale = sigma * np.sqrt((df - 2) / df)
    out = {}
    for a in levels:
        q = stats.t.ppf(a, df)
        var = -mu + scale * q
        tail = stats.t.pdf(q, df) * (df + q ** 2) / ((df - 1) * (1 - a))
        out[a] = (float(var), float(-mu + scale * tail))
    return out


def empirical_var_es(losses: np.ndarray, levels: Iterable[float]) -> RiskEstimates:
    """VaR is the loss quantile; ES is the average of losses at or beyond it."""
    out = {}
    for a in levels:
        var = float(np.quantile(losses, a))
        out[a] = (var, float(losses[losses >= var].mean()))
    return out


def _cholesky(cov: np.ndarray) -> np.ndarray:
    """Cholesky factor, adding a tiny diagonal jitter if the sample covariance is near-singular."""
    jitter = 0.0
    for _ in range(6):
        try:
            return np.linalg.cholesky(cov + jitter * np.eye(len(cov)))
        except np.linalg.LinAlgError:
            jitter = max(jitter * 10, 1e-10)
    raise np.linalg.LinAlgError("covariance matrix is not positive definite")


# --- models -----------------------------------------------------------------------------------
class RiskModel(ABC):
    """A one-day VaR/ES model. `diagnostics` holds anything worth reporting, e.g. fitted df."""

    name: str
    needs_ewma: bool = False

    @abstractmethod
    def estimate(self, moments: WindowMoments, levels: tuple[float, ...],
                 rng: np.random.Generator | None = None) -> tuple[RiskEstimates, dict]:
        ...


class HistoricalSimulation(RiskModel):
    """Revalue today's portfolio on every day of the estimation window."""

    name = "Historical"

    def estimate(self, moments, levels, rng=None):
        return empirical_var_es(moments.losses, levels), {}


class ParametricNormal(RiskModel):
    """Variance-covariance method: portfolio return ~ Normal(w'mu, w'Sigma w)."""

    name = "Parametric (Normal)"

    def estimate(self, moments, levels, rng=None):
        mu, sigma = moments.portfolio_mean, moments.portfolio_sigma
        out = {}
        for a in levels:
            z = stats.norm.ppf(a)
            out[a] = (-mu + sigma * z, -mu + sigma * stats.norm.pdf(z) / (1 - a))
        return out, {}


class ParametricStudentTEwma(RiskModel):
    """Student-t tails on an EWMA volatility, in closed form.

    Two changes from the normal model, aimed at its two known failures:
    - EWMA volatility reacts to a shock within days instead of being diluted by a 59-month average.
    - Student-t tails admit extreme days at something like their real frequency.
    """

    name = "Parametric (t + EWMA)"
    needs_ewma = True

    def __init__(self, df_bounds: tuple[float, float] = DF_BOUNDS):
        self.df_bounds = df_bounds

    def estimate(self, moments, levels, rng=None):
        df = fit_t_df_moments(moments.standardised_returns, self.df_bounds)
        estimates = student_t_var_es(moments.portfolio_mean, moments.ewma_sigma, df, levels)
        return estimates, {"t_df": df, "ewma_sigma": moments.ewma_sigma}


class MonteCarloStudentT(RiskModel):
    """Simulate all stocks jointly from a multivariate Student-t, then revalue the portfolio.

    The t keeps the sample mean and covariance but produces extreme days more often than a
    normal, controlled by degrees of freedom fitted to the window (by moments, not by MLE).
    """

    name = "Monte Carlo (Student-t)"

    def __init__(self, n_sims: int = 10_000, df_bounds: tuple[float, float] = DF_BOUNDS,
                 df_method: str = "moments"):
        self.n_sims = n_sims
        self.df_bounds = df_bounds
        self.df_method = df_method

    def _fit_df(self, x: np.ndarray) -> float:
        if self.df_method == "mle":
            return fit_t_df_mle(x, self.df_bounds)
        return fit_t_df_moments(x, self.df_bounds)

    def estimate(self, moments, levels, rng=None):
        if rng is None:
            raise ValueError("Monte Carlo needs a random generator")
        mu, cov = moments.mean, moments.cov
        df = self._fit_df(moments.portfolio_returns)

        chol = _cholesky(cov)
        z = rng.standard_normal((self.n_sims, len(mu))) @ chol.T
        mixing = np.sqrt(rng.chisquare(df, self.n_sims) / df)
        # Scale so the simulated covariance equals the sample covariance (a raw t has variance df/(df-2)).
        sims = mu + np.sqrt((df - 2) / df) * z / mixing[:, None]
        return empirical_var_es(-(sims @ moments.weights), levels), {"t_df": df}


def default_models(mc_simulations: int, df_bounds: tuple[float, float] = DF_BOUNDS,
                   mc_df_method: str = "moments") -> list[RiskModel]:
    return [
        HistoricalSimulation(),
        ParametricNormal(),
        ParametricStudentTEwma(df_bounds),
        MonteCarloStudentT(mc_simulations, df_bounds, mc_df_method),
    ]
