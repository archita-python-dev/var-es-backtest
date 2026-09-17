import numpy as np
import pytest
from scipy import stats

from var_backtest import models


def test_empirical_var_es_on_known_losses():
    losses = np.arange(1, 101, dtype=float)  # 1..100
    (var, es), = models.empirical_var_es(losses, [0.95]).values()
    assert var == pytest.approx(np.quantile(losses, 0.95))
    assert es == pytest.approx(losses[losses >= var].mean())
    assert es >= var


def test_historical_uses_portfolio_returns():
    rets = np.array([[0.01, -0.03], [-0.02, 0.00], [0.00, 0.02]])
    w = np.array([0.5, 0.5])
    port_losses = -(rets @ w)
    out = models.historical(rets, w, [0.9])
    assert out[0.9][0] == pytest.approx(np.quantile(port_losses, 0.9))


def test_parametric_matches_closed_form():
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0005, 0.01, size=(1000, 3))
    w = np.array([0.2, 0.3, 0.5])
    mu = rets.mean(0) @ w
    sigma = np.sqrt(w @ np.cov(rets, rowvar=False) @ w)
    var, es = models.parametric_normal(rets, w, [0.99])[0.99]
    assert var == pytest.approx(-mu + sigma * stats.norm.ppf(0.99))
    assert es == pytest.approx(-mu + sigma * stats.norm.pdf(stats.norm.ppf(0.99)) / 0.01)


def test_monte_carlo_near_normal_when_tails_are_thin():
    """With normal data the fitted df hits the upper bound and MC should land close to parametric."""
    rng = np.random.default_rng(1)
    rets = rng.normal(0, 0.01, size=(2000, 5))
    w = np.full(5, 0.2)
    mc, df = models.monte_carlo_t(rets, w, [0.95], 200_000, np.random.default_rng(2), (3.0, 1000.0))
    param = models.parametric_normal(rets, w, [0.95])
    assert df > 30
    assert mc[0.95][0] == pytest.approx(param[0.95][0], rel=0.03)


def test_monte_carlo_fat_tails_raise_99_es():
    rng = np.random.default_rng(3)
    rets = stats.t.rvs(3, size=(2000, 4), random_state=rng) * 0.006
    w = np.full(4, 0.25)
    mc, df = models.monte_carlo_t(rets, w, [0.99], 100_000, np.random.default_rng(4))
    param = models.parametric_normal(rets, w, [0.99])
    assert df < 10
    assert mc[0.99][1] > param[0.99][1]


def test_monte_carlo_is_reproducible_with_seed():
    rets = np.random.default_rng(5).normal(0, 0.01, size=(500, 3))
    w = np.full(3, 1 / 3)
    a = models.monte_carlo_t(rets, w, [0.95], 5000, np.random.default_rng(42))
    b = models.monte_carlo_t(rets, w, [0.95], 5000, np.random.default_rng(42))
    assert a == b
