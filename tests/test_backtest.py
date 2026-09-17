import numpy as np
import pandas as pd
import pytest

from var_backtest.backtest import METHODS, monthly_breaches, run_backtest, summarise
from var_backtest.weights import market_cap_weights

LEVELS = (0.95, 0.99)


@pytest.fixture
def synthetic_returns():
    dates = pd.bdate_range("2019-01-01", "2020-03-31")
    rng = np.random.default_rng(7)
    return pd.DataFrame(rng.normal(0, 0.01, size=(len(dates), 4)), index=dates, columns=list("ABCD"))


def _run(returns, **overrides):
    kwargs = dict(weights=np.full(4, 0.25), aum=1e9, test_start=pd.Timestamp("2020-01-01"),
                  test_end=pd.Timestamp("2020-03-31"), window_months=12, levels=LEVELS,
                  mc_simulations=2000, mc_seed=1)
    kwargs.update(overrides)
    return run_backtest(returns, **kwargs)


def test_window_excludes_forecast_date_and_rolls(synthetic_returns):
    result = _run(synthetic_returns)
    d = result.daily
    assert (d["window_start"] < d["date"]).all()
    first, last = d["date"].min(), d["date"].max()
    assert d.loc[d["date"] == first, "window_start"].iloc[0] >= first - pd.DateOffset(months=12)
    assert d.loc[d["date"] == last, "window_start"].iloc[0] > d.loc[d["date"] == first, "window_start"].iloc[0]


def test_no_look_ahead(synthetic_returns):
    """Changing a test-day return must not change that day's forecast."""
    base = _run(synthetic_returns).daily
    shocked = synthetic_returns.copy()
    target = pd.Timestamp("2020-02-03")
    shocked.loc[target] = -0.2
    after = _run(shocked).daily
    cols = ["var_usd", "es_usd"]
    b = base[base["date"] == target][cols].to_numpy()
    a = after[after["date"] == target][cols].to_numpy()
    np.testing.assert_allclose(a, b)
    assert after[(after["date"] == target)]["breach"].all()


def test_output_shape_and_breach_definition(synthetic_returns):
    result = _run(synthetic_returns)
    days = synthetic_returns.loc["2020-01-01":"2020-03-31"].shape[0]
    assert len(result.daily) == days * len(METHODS) * len(LEVELS)
    d = result.daily
    assert (d["breach"] == (-d["actual_pnl_usd"] > d["var_usd"])).all()
    assert (d["es_usd"] >= d["var_usd"]).all()


def test_summary_has_one_row_per_method_and_level(synthetic_returns):
    result = _run(synthetic_returns)
    summary = summarise(result, LEVELS)
    assert len(summary) == len(METHODS) * len(LEVELS)
    assert (summary["Breaches"] == [result.daily[(result.daily.method == m) & (result.daily.confidence == c)].breach.sum()
                                    for m in METHODS for c in LEVELS]).all()
    assert monthly_breaches(result).to_numpy().sum() == result.daily["breach"].sum()


def test_market_cap_weights_sum_to_one():
    w = market_cap_weights(pd.Series({"A": 10.0, "B": 30.0}), pd.Series({"A": 5.0, "B": 5.0}))
    assert w.sum() == pytest.approx(1.0)
    assert w["B"] == pytest.approx(0.75)
