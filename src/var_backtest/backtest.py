"""Rolling-window backtest: forecast each test day using only the preceding window, then compare."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import models
from .stats import christoffersen_independence, kupiec_pof, traffic_light

log = logging.getLogger(__name__)

METHODS = ("Historical", "Parametric (Normal)", "Monte Carlo (Student-t)")


@dataclass
class BacktestResult:
    daily: pd.DataFrame          # one row per (date, method, confidence level)
    runtime: dict[str, float]    # total seconds per method over the whole test period
    t_df: pd.Series              # fitted Student-t degrees of freedom per test day


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
    mc_df_bounds: tuple[float, float] = (3.0, 30.0),
) -> BacktestResult:
    test_dates = returns.loc[test_start:test_end].index
    if len(test_dates) == 0:
        raise ValueError("no trading days in the test period")

    values = returns.to_numpy()
    index = returns.index
    rng = np.random.default_rng(mc_seed)
    runtime = dict.fromkeys(METHODS, 0.0)
    rows, t_df = [], {}

    for date in test_dates:
        # Window = returns strictly before the forecast date: no same-day information leaks in.
        start = date - pd.DateOffset(months=window_months)
        window = values[(index >= start) & (index < date)]

        estimates = {}
        tic = time.perf_counter()
        estimates["Historical"] = models.historical(window, weights, levels)
        runtime["Historical"] += time.perf_counter() - tic

        tic = time.perf_counter()
        estimates["Parametric (Normal)"] = models.parametric_normal(window, weights, levels)
        runtime["Parametric (Normal)"] += time.perf_counter() - tic

        tic = time.perf_counter()
        estimates["Monte Carlo (Student-t)"], t_df[date] = models.monte_carlo_t(
            window, weights, levels, mc_simulations, rng, mc_df_bounds)
        runtime["Monte Carlo (Student-t)"] += time.perf_counter() - tic

        actual_pnl = aum * float(returns.loc[date].to_numpy() @ weights)
        for method, by_level in estimates.items():
            for level, (var, es) in by_level.items():
                var_usd, es_usd = aum * var, aum * es
                rows.append({
                    "date": date, "method": method, "confidence": level,
                    "window_start": index[(index >= start)][0], "window_days": len(window),
                    "var_usd": var_usd, "es_usd": es_usd, "actual_pnl_usd": actual_pnl,
                    "breach": -actual_pnl > var_usd,
                })

    log.info("Backtested %d days from %s to %s", len(test_dates), test_dates[0].date(), test_dates[-1].date())
    return BacktestResult(daily=pd.DataFrame(rows), runtime=runtime, t_df=pd.Series(t_df, name="t_df"))


def summarise(result: BacktestResult, levels: tuple[float, ...]) -> pd.DataFrame:
    """One row per method and confidence level: forecasts, breaches and test outcomes."""
    rows = []
    for method in METHODS:
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
    order = [f"{m} {round(c * 100)}%" for m in METHODS for c in sorted(d["confidence"].unique())]
    return table[order].astype(int)


def exceptions(result: BacktestResult) -> pd.DataFrame:
    hit = result.daily[result.daily["breach"]].copy()
    hit["actual_loss_usd"] = -hit["actual_pnl_usd"]
    hit["excess_over_var_usd"] = hit["actual_loss_usd"] - hit["var_usd"]
    cols = ["date", "method", "confidence", "var_usd", "es_usd", "actual_loss_usd", "excess_over_var_usd"]
    return hit[cols].sort_values(["date", "method", "confidence"]).reset_index(drop=True)
