import numpy as np
import pytest

from var_backtest.stats import christoffersen_independence, kupiec_pof, traffic_light


def test_kupiec_accepts_expected_breach_count():
    _, p = kupiec_pof(breaches=5, days=500, level=0.99)
    assert p == pytest.approx(1.0)


def test_kupiec_rejects_far_too_many_breaches():
    _, p = kupiec_pof(breaches=15, days=250, level=0.99)
    assert p < 0.01


def test_kupiec_handles_zero_breaches():
    lr, p = kupiec_pof(breaches=0, days=250, level=0.99)
    assert np.isfinite(lr) and 0 < p <= 1


@pytest.mark.parametrize("breaches, zone", [(0, "Green"), (4, "Green"), (5, "Yellow"), (9, "Yellow"), (10, "Red")])
def test_traffic_light_matches_basel_table(breaches, zone):
    assert traffic_light(breaches, 250, 0.99) == zone


def test_independence_flags_clustered_breaches():
    flags = np.zeros(250, dtype=int)
    flags[60:66] = 1  # six breaches in a row
    _, p = christoffersen_independence(flags)
    assert p < 0.01


def test_independence_accepts_spread_out_breaches():
    flags = np.zeros(250, dtype=int)
    flags[[20, 70, 120, 170, 220]] = 1
    _, p = christoffersen_independence(flags)
    assert p > 0.05


def test_independence_without_breaches_is_nan():
    _, p = christoffersen_independence(np.zeros(250))
    assert np.isnan(p)
