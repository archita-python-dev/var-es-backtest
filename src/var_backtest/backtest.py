"""Rolling-window backtest: forecast each test day using only the preceding window, then compare."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .models import DF_BOUNDS, EwmaCovariance, RiskModel, WindowMoments, default_models
from .stats import christoffersen_independence, kupiec_pof, traffic_light

log = logging.getLogger(__name__)

METHODS = tuple(m.name for m in default_models(1))
SHARED_INPUTS = "Shared inputs (mean, covariance)"


@dataclass
class BacktestResult:
    daily: pd.DataFrame                 # one row per (date, method, confidence level)
    runtime: dict[str, float]           # summed seconds per method over the whole test period
    diagnostics: pd.DataFrame           # per-day fitted parameters, e.g. Student-t df
    wall_seconds: float = 0.0           # elapsed time for the whole loop, threads included
    workers: int = 1
    shared_seconds: float = 0.0         # time spent building inputs every model shares
    extras: dict = field(default_factory=dict)

    @property
    def t_df(self) -> pd.Series:
        """Monte Carlo degrees of freedom per day, kept for reporting."""
        mc = self.diagnostics[self.diagnostics["method"] == "Monte Carlo (Student-t)"]
        return mc.set_index("date")["t_df"]


def run_backtest(
    returns: pd.DataFrame,
    weights: np.ndarray,
    aum: float,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    window_months: int,
    levels: tuple[float, ...],
    mc_simulations: int,
    mc_seed: int,
    mc_df_bounds: tuple[float, float] = DF_BOUNDS,
    ewma_lambda: float = 0.94,
    mc_df_method: str = "moments",
    workers: int = 1,
    models: list[RiskModel] | None = None,
    timing_sample: int = 40,
) -> BacktestResult:
    test_dates = returns.loc[test_start:test_end].index
    if len(test_dates) == 0:
        raise ValueError("no trading days in the test period")

    values = returns.to_numpy()
    index = returns.index
    models = models or default_models(mc_simulations, mc_df_bounds, mc_df_method)

    # Built once for the whole run: rolling it forward day by day costs one pass, while rebuilding
    # it inside each window would repeat the same recursion 250 times.
    tic = time.perf_counter()
    ewma = EwmaCovariance(values, lam=ewma_lambda) if any(m.needs_ewma for m in models) else None
    ewma_vol = ewma.portfolio_vol(weights) if ewma else None
    ewma_seconds = time.perf_counter() - tic

    # One independent seed per day, so results are identical whether days run in parallel or not.
    seeds = np.random.SeedSequence(mc_seed).spawn(len(test_dates))
    starts = index.searchsorted(test_dates - pd.DateOffset(months=window_months), side="left")
    ends = index.searchsorted(test_dates, side="left")  # strictly before the forecast day

    def forecast_day(i: int) -> tuple[list[dict], list[dict], dict[str, float], float]:
        date, lo, hi = test_dates[i], starts[i], ends[i]
        rng = np.random.default_rng(seeds[i])

        shared_tic = time.perf_counter()
        moments = WindowMoments(
            values[lo:hi], weights,
            ewma_cov=ewma.at(hi) if ewma else None,
            ewma_vol=ewma_vol[lo:hi] if ewma_vol is not None else None,
        )
        # Force the shared inputs now so their cost is attributed here, not to whichever model
        # happens to touch them first.
        moments.portfolio_returns, moments.mean, moments.cov
        shared = time.perf_counter() - shared_tic

        rows, diag, timings = [], [], {}
        actual_pnl = aum * float(values[hi] @ weights)
        for model in models:
            tic = time.perf_counter()
            estimates, extra = model.estimate(moments, levels, rng)
            timings[model.name] = time.perf_counter() - tic
            if extra:
                diag.append({"date": date, "method": model.name, **extra})
            for level, (var, es) in estimates.items():
                rows.append({
                    "date": date, "method": model.name, "confidence": level,
                    "window_start": index[lo], "window_days": hi - lo,
                    "var_usd": aum * var, "es_usd": aum * es, "actual_pnl_usd": actual_pnl,
                    "breach": -actual_pnl > aum * var,
                })
        return rows, diag, timings, shared

    wall_tic = time.perf_counter()
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(forecast_day, range(len(test_dates))))
    else:
        results = [forecast_day(i) for i in range(len(test_dates))]
    wall = time.perf_counter() - wall_tic

    rows = [r for day in results for r in day[0]]
    diagnostics = [d for day in results for d in day[1]]
    runtime = {m.name: sum(day[2][m.name] for day in results) for m in models}
    shared_seconds = sum(day[3] for day in results) + ewma_seconds
    timed_serially = False

    if workers > 1 and timing_sample:
        # Timers inside a thread also count time spent waiting for the other threads, which makes
        # every model look slower than it is. Re-time a sample of days serially and scale up, so the
        # per-model figures stay comparable while the wall clock still reflects the thread pool.
        sample = np.unique(np.linspace(0, len(test_dates) - 1, min(timing_sample, len(test_dates))).astype(int))
        timed = [forecast_day(i) for i in sample]
        scale = len(test_dates) / len(sample)
        runtime = {m.name: sum(day[2][m.name] for day in timed) * scale for m in models}
        shared_seconds = sum(day[3] for day in timed) * scale + ewma_seconds
        timed_serially = True

    log.info("Backtested %d days from %s to %s in %.1fs wall time (%d worker%s)",
             len(test_dates), test_dates[0].date(), test_dates[-1].date(), wall,
             workers, "" if workers == 1 else "s")
    return BacktestResult(
        daily=pd.DataFrame(rows).sort_values(["date", "method", "confidence"]).reset_index(drop=True),
        runtime=runtime,
        diagnostics=pd.DataFrame(diagnostics),
        wall_seconds=wall,
        workers=workers,
        shared_seconds=shared_seconds,
        extras={"model_cost_timed_serially": timed_serially, "timing_sample_days": timing_sample},
    )


def summarise(result: BacktestResult, levels: tuple[float, ...]) -> pd.DataFrame:
    """One row per method and confidence level: forecasts, breaches and test outcomes."""
    rows = []
    for method in result.daily["method"].unique():
        for level in levels:
            d = result.daily[(result.daily["method"] == method) & (result.daily["confidence"] == level)]
            days, breaches = len(d), int(d["breach"].sum())
            hit = d[d["breach"]]
            _, kupiec_p = kupiec_pof(breaches, days, level)
            _, indep_p = christoffersen_independence(d["breach"].to_numpy())
            rows.append({
                "Method": method,
                "Confidence": f"{level:.0%}",
                "Avg VaR ($)": d["var_usd"].mean(),
                "Avg ES ($)": d["es_usd"].mean(),
                "Runtime, all days (s)": result.runtime[method],
                "Test days": days,
                "Breaches": breaches,
                "Expected breaches": days * (1 - level),
                "Kupiec p-value": kupiec_p,
                "Breach count OK (p>=0.05)": "Yes" if kupiec_p >= 0.05 else "No",
                "Clustering p-value": indep_p,
                "Basel zone": traffic_light(breaches, days, level),
                "Avg ES on breach days ($)": hit["es_usd"].mean() if breaches else np.nan,
                "Avg loss on breach days ($)": -hit["actual_pnl_usd"].mean() if breaches else np.nan,
                "Actual loss / forecast ES": (-hit["actual_pnl_usd"] / hit["es_usd"]).mean() if breaches else np.nan,
            })
    return pd.DataFrame(rows)


def monthly_breaches(result: BacktestResult) -> pd.DataFrame:
    d = result.daily.assign(
        month=result.daily["date"].dt.to_period("M").astype(str),
        column=result.daily["method"] + " " + (result.daily["confidence"] * 100).round().astype(int).astype(str) + "%",
    )
    table = d.pivot_table(index="month", columns="column", values="breach", aggfunc="sum")
    methods = [m for m in METHODS if m in set(d["method"])]
    order = [f"{m} {round(c * 100)}%" for m in methods for c in sorted(d["confidence"].unique())]
    return table[order].astype(int)


def exceptions(result: BacktestResult) -> pd.DataFrame:
    hit = result.daily[result.daily["breach"]].copy()
    hit["actual_loss_usd"] = -hit["actual_pnl_usd"]
    hit["excess_over_var_usd"] = hit["actual_loss_usd"] - hit["var_usd"]
    cols = ["date", "method", "confidence", "var_usd", "es_usd", "actual_loss_usd", "excess_over_var_usd"]
    return hit[cols].sort_values(["date", "method", "confidence"]).reset_index(drop=True)
