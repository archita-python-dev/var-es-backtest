import numpy as np
import pytest
from scipy import stats

from var_backtest import models
from var_backtest.models import (EwmaCovariance, HistoricalSimulation, MonteCarloStudentT, ParametricNormal,
                                 ParametricStudentTEwma, WindowMoments)


def moments_for(returns, weights, lam=0.94, burn_in=30):
    ewma = EwmaCovariance(returns, lam=lam, burn_in=burn_in)
    return WindowMoments(returns, weights, ewma_cov=ewma.at(len(returns) - 1),
                         ewma_vol=ewma.portfolio_vol(weights))


def test_empirical_var_es_on_known_losses():
    losses = np.arange(1, 101, dtype=float)
    (var, es), = models.empirical_var_es(losses, [0.95]).values()
    assert var == pytest.approx(np.quantile(losses, 0.95))
    assert es == pytest.approx(losses[losses >= var].mean())
    assert es >= var


def test_historical_uses_portfolio_returns():
    rets = np.array([[0.01, -0.03], [-0.02, 0.00], [0.00, 0.02]])
    w = np.array([0.5, 0.5])
    out, _ = HistoricalSimulation().estimate(WindowMoments(rets, w), (0.9,))
    assert out[0.9][0] == pytest.approx(np.quantile(-(rets @ w), 0.9))


def test_parametric_matches_closed_form():
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0005, 0.01, size=(1000, 3))
    w = np.array([0.2, 0.3, 0.5])
    mu = rets.mean(0) @ w
    sigma = np.sqrt(w @ np.cov(rets, rowvar=False) @ w)
    out, _ = ParametricNormal().estimate(WindowMoments(rets, w), (0.99,))
    var, es = out[0.99]
    assert var == pytest.approx(-mu + sigma * stats.norm.ppf(0.99))
    assert es == pytest.approx(-mu + sigma * stats.norm.pdf(stats.norm.ppf(0.99)) / 0.01)


def test_window_moments_portfolio_sigma_matches_portfolio_series():
    rng = np.random.default_rng(3)
    rets = rng.normal(0, 0.01, size=(500, 4))
    w = np.full(4, 0.25)
    m = WindowMoments(rets, w)
    assert m.portfolio_sigma == pytest.approx(m.portfolio_returns.std(ddof=1), rel=1e-12)
    assert m.cov is m.cov  # cached: built once per day, then reused by every model


class TestStudentTClosedForm:
    def test_matches_simulation(self):
        """Closed-form t VaR/ES should match a large simulation of the same distribution."""
        mu, sigma, df, a = 0.0004, 0.012, 5.0, 0.99
        out = models.student_t_var_es(mu, sigma, df, [a])
        draws = mu + sigma * np.sqrt((df - 2) / df) * stats.t.rvs(df, size=2_000_000,
                                                                  random_state=np.random.default_rng(1))
        sim = models.empirical_var_es(-draws, [a])
        assert out[a][0] == pytest.approx(sim[a][0], rel=0.01)
        assert out[a][1] == pytest.approx(sim[a][1], rel=0.02)

    def test_fatter_tails_than_normal_at_99(self):
        t_var, t_es = models.student_t_var_es(0.0, 0.01, 4.0, [0.99])[0.99]
        z = stats.norm.ppf(0.99)
        assert t_var > 0.01 * z
        assert t_es > 0.01 * stats.norm.pdf(z) / 0.01

    def test_high_df_converges_to_normal(self):
        t_var, _ = models.student_t_var_es(0.0, 0.01, 500.0, [0.99])[0.99]
        assert t_var == pytest.approx(0.01 * stats.norm.ppf(0.99), rel=0.02)


class TestDegreesOfFreedom:
    def test_moment_estimate_recovers_simulated_df(self):
        draws = stats.t.rvs(6, size=200_000, random_state=np.random.default_rng(2))
        assert models.fit_t_df_moments(draws, (3.0, 60.0)) == pytest.approx(6.0, rel=0.25)

    def test_normal_data_gives_the_upper_bound(self):
        draws = np.random.default_rng(4).normal(size=50_000)
        assert models.fit_t_df_moments(draws, (3.0, 30.0)) == 30.0

    def test_moments_and_mle_broadly_agree_on_fat_tails(self):
        draws = stats.t.rvs(4, size=20_000, random_state=np.random.default_rng(5))
        by_moments = models.fit_t_df_moments(draws, (3.0, 30.0))
        by_mle = models.fit_t_df_mle(draws, (3.0, 30.0))
        assert abs(by_moments - by_mle) < 2.0


class TestEwmaCovariance:
    def test_snapshot_ignores_its_own_day_and_later(self):
        rng = np.random.default_rng(6)
        rets = rng.normal(0, 0.01, size=(300, 3))
        shocked = rets.copy()
        shocked[200:] = -0.3  # a crash from day 200 onwards
        a, b = EwmaCovariance(rets, burn_in=50), EwmaCovariance(shocked, burn_in=50)
        np.testing.assert_allclose(a.at(200), b.at(200))
        assert b.at(205)[0, 0] > a.at(205)[0, 0]  # after the shock, it has reacted

    def test_portfolio_vol_matches_one_dimensional_recursion(self):
        rng = np.random.default_rng(7)
        rets = rng.normal(0, 0.01, size=(400, 5))
        w = np.full(5, 0.2)
        lam, burn = 0.94, 40
        vol = EwmaCovariance(rets, lam=lam, burn_in=burn).portfolio_vol(w)

        port = rets @ w
        var = float(w @ np.cov(rets[:burn], rowvar=False) @ w)
        expected = []
        for r in port:
            expected.append(np.sqrt(var))
            var = lam * var + (1 - lam) * r ** 2
        np.testing.assert_allclose(vol, expected, rtol=1e-10)

    def test_reacts_faster_than_the_sample_covariance(self):
        rng = np.random.default_rng(8)
        calm = rng.normal(0, 0.005, size=(600, 2))
        storm = rng.normal(0, 0.05, size=(10, 2))
        rets = np.vstack([calm, storm])
        w = np.full(2, 0.5)
        m = moments_for(rets, w, burn_in=60)
        assert m.ewma_sigma > 3 * m.portfolio_sigma


class TestParametricStudentTEwma:
    def test_raises_var_after_a_volatility_jump(self):
        rng = np.random.default_rng(9)
        calm = rng.normal(0, 0.004, size=(800, 3))
        rets = np.vstack([calm, rng.normal(0, 0.04, size=(10, 3))])
        w = np.full(3, 1 / 3)
        m = moments_for(rets, w, burn_in=60)
        t_ewma, extra = ParametricStudentTEwma().estimate(m, (0.99,))
        normal, _ = ParametricNormal().estimate(m, (0.99,))
        assert t_ewma[0.99][0] > normal[0.99][0]
        assert 3.0 <= extra["t_df"] <= 30.0

    def test_es_exceeds_var_at_every_level(self):
        rng = np.random.default_rng(10)
        rets = stats.t.rvs(5, size=(900, 4), random_state=rng) * 0.006
        w = np.full(4, 0.25)
        out, _ = ParametricStudentTEwma().estimate(moments_for(rets, w), (0.95, 0.97, 0.99))
        for level in (0.95, 0.97, 0.99):
            assert out[level][1] > out[level][0]


class TestMonteCarlo:
    def test_close_to_parametric_when_tails_are_thin(self):
        rng = np.random.default_rng(11)
        rets = rng.normal(0, 0.01, size=(2000, 5))
        w = np.full(5, 0.2)
        m = WindowMoments(rets, w)
        mc, extra = MonteCarloStudentT(200_000, (3.0, 1000.0)).estimate(m, (0.95,), np.random.default_rng(12))
        param, _ = ParametricNormal().estimate(m, (0.95,))
        assert extra["t_df"] > 30
        assert mc[0.95][0] == pytest.approx(param[0.95][0], rel=0.03)

    def test_fat_tails_raise_99_es(self):
        rng = np.random.default_rng(13)
        rets = stats.t.rvs(3, size=(2000, 4), random_state=rng) * 0.006
        w = np.full(4, 0.25)
        m = WindowMoments(rets, w)
        mc, extra = MonteCarloStudentT(100_000).estimate(m, (0.99,), np.random.default_rng(14))
        param, _ = ParametricNormal().estimate(m, (0.99,))
        assert extra["t_df"] < 10
        assert mc[0.99][1] > param[0.99][1]

    def test_reproducible_with_the_same_seed(self):
        rets = np.random.default_rng(15).normal(0, 0.01, size=(500, 3))
        m = WindowMoments(rets, np.full(3, 1 / 3))
        model = MonteCarloStudentT(5000)
        a = model.estimate(m, (0.95,), np.random.default_rng(42))
        b = model.estimate(m, (0.95,), np.random.default_rng(42))
        assert a == b

    def test_agrees_with_the_closed_form_student_t(self):
        """A linear portfolio of multivariate-t assets is univariate t, so the two should match."""
        rng = np.random.default_rng(16)
        rets = stats.t.rvs(6, size=(1500, 6), random_state=rng) * 0.008
        w = np.full(6, 1 / 6)
        m = WindowMoments(rets, w)
        mc, extra = MonteCarloStudentT(400_000).estimate(m, (0.99,), np.random.default_rng(17))
        closed = models.student_t_var_es(m.portfolio_mean, m.portfolio_sigma, extra["t_df"], [0.99])
        assert mc[0.99][0] == pytest.approx(closed[0.99][0], rel=0.03)
        assert mc[0.99][1] == pytest.approx(closed[0.99][1], rel=0.05)
