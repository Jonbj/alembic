"""#134: does the sleeve's trade sequence have the serial dependence that a
loss-feedback ratchet needs to be justified at all? Pure-function tests."""
import pytest

from scripts.ratchet_reachability import serial_dependence


def test_streaky_sequence_has_positive_autocorrelation_and_few_runs():
    # Blocks of wins then losses: losses beget losses — the premise F8 assumes.
    seq = [1.0] * 10 + [-1.0] * 10 + [1.0] * 10 + [-1.0] * 10
    d = serial_dependence(seq)
    assert d["lag1_autocorr"] > 0.5
    assert d["runs"] < d["runs_expected"]
    assert d["runs_z"] < -1.96
    assert d["verdict"] == "streaky"


def test_alternating_sequence_is_mean_reverting():
    seq = [1.0, -1.0] * 20
    d = serial_dependence(seq)
    assert d["lag1_autocorr"] < -0.5
    assert d["runs"] > d["runs_expected"]
    assert d["verdict"] == "mean-reverting"


def test_independent_sequence_shows_no_dependence():
    # Deterministic pseudo-random signs with no structure at lag 1.
    import random

    random.seed(7)
    seq = [random.choice([1.0, -1.0]) for _ in range(400)]
    d = serial_dependence(seq)
    assert abs(d["lag1_autocorr"]) < 0.15
    assert d["verdict"] == "no detectable dependence"


def test_significance_band_scales_with_sample_size():
    small = serial_dependence([1.0, -1.0] * 5)
    large = serial_dependence([1.0, -1.0] * 200)
    assert small["significance_band"] > large["significance_band"]


def test_all_wins_has_no_runs_statistic_but_still_scores_autocorrelation():
    # Varying magnitudes, all positive: the runs test needs both signs, but the
    # autocorrelation is still well defined and must carry the verdict alone.
    seq = [1.0, 2.0, 1.5, 2.5, 1.2, 2.2, 1.8, 2.8, 1.1, 2.1] * 2
    d = serial_dependence(seq)
    assert d["runs_z"] is None, "runs test undefined without both signs"
    assert d["lag1_autocorr"] is not None
    assert d["verdict"] in {"streaky", "mean-reverting", "no detectable dependence"}


def test_too_short_is_inconclusive():
    d = serial_dependence([1.0, -1.0])
    assert d["verdict"] == "insufficient data"
    assert d["lag1_autocorr"] is None


def test_constant_series_does_not_divide_by_zero():
    d = serial_dependence([0.0] * 10)
    assert d["lag1_autocorr"] is None
    assert d["verdict"] == "insufficient data"


def test_win_rate_and_n_are_reported():
    d = serial_dependence([1.0, 1.0, -1.0, -1.0, 1.0, -1.0])
    assert d["n"] == 6
    assert d["win_rate"] == pytest.approx(0.5)


# --- the cross-sectional confound -----------------------------------------

from scripts.ratchet_reachability import daily_aggregate, same_day_neighbour_share


def _o(day, pnl, budget=100.0):
    return {"day": day, "net_pnl": pnl, "budget": budget}


def test_daily_aggregate_collapses_same_day_exits_into_one_observation():
    obs = [_o("d1", -10.0), _o("d1", -10.0), _o("d1", -10.0), _o("d2", 30.0)]
    assert daily_aggregate(obs) == pytest.approx([-0.1, 0.3])


def test_daily_aggregate_is_budget_weighted_not_an_average_of_ratios():
    # A big loser on a big budget must not be diluted by a tiny winner.
    obs = [_o("d1", -100.0, budget=1000.0), _o("d1", 10.0, budget=10.0)]
    assert daily_aggregate(obs) == pytest.approx([(-100.0 + 10.0) / 1010.0])


def test_daily_aggregate_skips_rows_without_a_risk_budget():
    obs = [_o("d1", -10.0, budget=0.0), _o("d1", -10.0, budget=100.0)]
    assert daily_aggregate(obs) == pytest.approx([-0.1])


def test_daily_aggregate_is_ordered_by_day():
    obs = [_o("d3", 30.0), _o("d1", -10.0), _o("d2", 20.0)]
    assert daily_aggregate(obs) == pytest.approx([-0.1, 0.2, 0.3])


def test_same_day_share_detects_a_cross_sectional_sequence():
    assert same_day_neighbour_share(["d1", "d1", "d1", "d2"]) == pytest.approx(2 / 3)
    assert same_day_neighbour_share(["d1", "d2", "d3"]) == 0.0
    assert same_day_neighbour_share(["d1"]) is None


def test_a_one_bad_day_cluster_looks_streaky_per_trade_but_not_per_day():
    """The confound, end to end: five simultaneous losses then five wins the
    next day read as two long streaks per trade, and as two observations
    per day — which is what they actually are."""
    obs = [_o("d1", -10.0) for _ in range(5)] + [_o("d2", 10.0) for _ in range(5)]
    per_trade = serial_dependence([o["net_pnl"] / o["budget"] for o in obs])
    per_day = serial_dependence(daily_aggregate(obs))
    assert per_trade["verdict"] == "streaky"
    assert per_day["n"] == 2
    assert per_day["verdict"] == "insufficient data"
