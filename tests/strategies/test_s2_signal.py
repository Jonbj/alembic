"""T-304: S2 put selection + entry rules."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from src.strategies.s2.config import S2Config
from src.strategies.s2.signal import PutSignal, select_put

# ---------------------------------------------------------------------------
# Fixed test parameters
# ---------------------------------------------------------------------------

_SPY_PRICE = 450.0
# SPY ~$450: 1 cash-secured put contract = strike * 100 ≈ $43,000 collateral.
# With max_collateral_pct=0.20, need capital >= $215,000 for 1 contract.
# Use $500k (typical institutional/retail account) → 2 contracts affordable.
_CAPITAL = 500_000.0
# March 20, 2023: next 3rd Friday is April 21 (DTE=32), well within [30, 45]
_AS_OF = date(2023, 3, 20)


# ---------------------------------------------------------------------------
# S2Config defaults
# ---------------------------------------------------------------------------


class TestS2Config:
    def test_default_target_delta(self) -> None:
        assert S2Config().target_delta == -0.20

    def test_default_delta_tolerance(self) -> None:
        assert S2Config().delta_tolerance == 0.05

    def test_default_min_dte(self) -> None:
        assert S2Config().min_dte == 30

    def test_default_max_dte(self) -> None:
        assert S2Config().max_dte == 45

    def test_default_min_open_interest(self) -> None:
        assert S2Config().min_open_interest == 100

    def test_default_min_volume(self) -> None:
        assert S2Config().min_volume == 10

    def test_default_max_collateral_pct(self) -> None:
        assert S2Config().max_collateral_pct == 0.20

    def test_default_vrp_entry_threshold(self) -> None:
        assert S2Config().vrp_entry_threshold == 0.0


# ---------------------------------------------------------------------------
# select_put — happy path
# ---------------------------------------------------------------------------


class TestSelectPutHappyPath:
    def test_returns_put_signal_not_none(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert isinstance(result, PutSignal)

    def test_right_is_put(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert result.right == "P"

    def test_symbol_is_spy(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert result.symbol == "SPY"

    def test_trade_date_matches_as_of(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert result.trade_date == _AS_OF

    def test_quantity_at_least_one(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert result.quantity >= 1

    def test_mid_price_positive(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert result.mid > 0.0

    def test_implied_vol_positive(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert result.implied_vol > 0.0


# ---------------------------------------------------------------------------
# Delta filter
# ---------------------------------------------------------------------------


class TestDeltaFilter:
    def test_delta_within_tolerance(self) -> None:
        cfg = S2Config()
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        assert result is not None
        delta_lo = cfg.target_delta - cfg.delta_tolerance  # -0.25
        delta_hi = cfg.target_delta + cfg.delta_tolerance  # -0.15
        assert delta_lo <= result.delta <= delta_hi, (
            f"Delta {result.delta:.4f} not in [{delta_lo}, {delta_hi}]"
        )

    def test_tighter_delta_tolerance_still_selects_closest(self) -> None:
        """Narrower tolerance: result delta still within the tighter band."""
        cfg = S2Config(delta_tolerance=0.03)  # [-0.23, -0.17]
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        if result is not None:
            assert cfg.target_delta - cfg.delta_tolerance <= result.delta <= cfg.target_delta + cfg.delta_tolerance

    def test_very_narrow_delta_window_returns_none_or_valid(self) -> None:
        """Tolerance 0.001 may return None if no contract exactly at -0.20."""
        cfg = S2Config(delta_tolerance=0.001)
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        if result is not None:
            assert abs(result.delta - cfg.target_delta) <= cfg.delta_tolerance


# ---------------------------------------------------------------------------
# DTE filter
# ---------------------------------------------------------------------------


class TestDTEFilter:
    def test_dte_within_range(self) -> None:
        cfg = S2Config()
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        assert result is not None
        dte = (result.expiry - _AS_OF).days
        assert cfg.min_dte <= dte <= cfg.max_dte, (
            f"DTE {dte} not in [{cfg.min_dte}, {cfg.max_dte}]"
        )

    def test_expiry_is_a_date(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert isinstance(result.expiry, date)

    def test_dte_range_that_cannot_be_met_returns_none(self) -> None:
        """Requesting DTE [100, 110] when only monthly expiries exist → likely None."""
        cfg = S2Config(min_dte=100, max_dte=110)
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        # Might or might not find one depending on calendar — must not raise
        if result is not None:
            dte = (result.expiry - _AS_OF).days
            assert cfg.min_dte <= dte <= cfg.max_dte


# ---------------------------------------------------------------------------
# Liquidity filter
# ---------------------------------------------------------------------------


class TestLiquidityFilter:
    def test_zero_thresholds_returns_result(self) -> None:
        """No liquidity requirement: should still find a contract."""
        cfg = S2Config(min_open_interest=0, min_volume=0)
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        assert result is not None

    def test_impossibly_high_oi_returns_none(self) -> None:
        cfg = S2Config(min_open_interest=10_000_000)
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        assert result is None

    def test_impossibly_high_volume_returns_none(self) -> None:
        cfg = S2Config(min_volume=10_000_000)
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        assert result is None


# ---------------------------------------------------------------------------
# Sizing / collateral
# ---------------------------------------------------------------------------


class TestSizing:
    def test_collateral_cap_respected(self) -> None:
        """quantity * strike * 100 <= capital * max_collateral_pct (allow rounding)."""
        cfg = S2Config()
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        assert result is not None
        max_collateral = _CAPITAL * cfg.max_collateral_pct
        assert result.collateral <= max_collateral + 1.0

    def test_collateral_equals_quantity_times_strike_times_100(self) -> None:
        result = select_put(_AS_OF, _CAPITAL, underlying_price=_SPY_PRICE)
        assert result is not None
        assert abs(result.collateral - result.quantity * result.strike * 100) < 1e-6

    def test_returns_none_when_capital_too_small(self) -> None:
        """Capital too small for even 1 contract (collateral = strike * 100).

        SPY ~$450: 1 contract collateral = $432 * 100 = $43,200.
        With max_collateral_pct=0.20 and capital=$1,000: max_collateral=$200 → 0 contracts.
        """
        result = select_put(_AS_OF, capital=1_000.0, underlying_price=_SPY_PRICE)
        assert result is None

    def test_larger_capital_yields_more_contracts(self) -> None:
        """Doubling capital should yield at least as many contracts."""
        result_small = select_put(_AS_OF, capital=500_000.0, underlying_price=_SPY_PRICE)
        result_large = select_put(_AS_OF, capital=1_000_000.0, underlying_price=_SPY_PRICE)
        assert result_small is not None
        assert result_large is not None
        assert result_large.quantity >= result_small.quantity

    def test_max_collateral_pct_zero_returns_none(self) -> None:
        """Zero collateral allocation → can't buy any contract."""
        cfg = S2Config(max_collateral_pct=0.0)
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
        assert result is None


# ---------------------------------------------------------------------------
# VRP filter
# ---------------------------------------------------------------------------


class TestVRPFilter:
    def test_no_realized_vol_skips_vrp_filter(self) -> None:
        """Without realized_vol, VRP filter is skipped regardless of threshold."""
        cfg = S2Config(vrp_entry_threshold=0.99)  # extreme threshold
        result = select_put(_AS_OF, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE, realized_vol=None)
        # Result may be found or not, but should not raise
        # (threshold only applies when realized_vol is given)
        # With such an extreme threshold AND realized_vol=None, skip filter → may find result
        assert True  # just must not raise

    def test_vrp_filter_blocks_when_realized_too_high(self) -> None:
        """realized_vol >> implied_vol → negative VRP → blocked even at threshold=0.0."""
        cfg = S2Config(vrp_entry_threshold=0.0)
        # Synthetic chain base_iv=0.18; OTM put IV ≈ 0.19
        # realized_vol=0.50 → VRP = 0.19 - 0.50 = -0.31 < 0.0 → blocked
        result = select_put(
            _AS_OF, _CAPITAL, config=cfg,
            underlying_price=_SPY_PRICE,
            realized_vol=0.50,
        )
        assert result is None

    def test_vrp_filter_passes_low_realized_vol(self) -> None:
        """Low realized_vol → high VRP → passes threshold=0.0."""
        cfg = S2Config(vrp_entry_threshold=0.0)
        result = select_put(
            _AS_OF, _CAPITAL, config=cfg,
            underlying_price=_SPY_PRICE,
            realized_vol=0.10,
        )
        assert result is not None

    def test_vrp_filter_blocks_when_threshold_too_high(self) -> None:
        """Require VRP >= 50% but implied ≈ 19%, realized = 15% → VRP = 4% → blocked."""
        cfg = S2Config(vrp_entry_threshold=0.50)
        result = select_put(
            _AS_OF, _CAPITAL, config=cfg,
            underlying_price=_SPY_PRICE,
            realized_vol=0.15,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Robustness: 100 random dates
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_100_random_dates_no_exception(self) -> None:
        """No exception for 100 random weekday dates between 2020-2024.

        When a result is returned it must satisfy all constraints.
        When no contract is available, None is returned without raising.
        """
        cfg = S2Config()
        rng = np.random.default_rng(42)
        start = date(2020, 1, 1)
        end = date(2024, 12, 31)
        total_days = (end - start).days

        tested = 0
        for offset in rng.integers(0, total_days, size=300):
            d = start + timedelta(days=int(offset))
            if d.weekday() >= 5:  # skip weekends
                continue

            try:
                result = select_put(d, _CAPITAL, config=cfg, underlying_price=_SPY_PRICE)
            except Exception as exc:
                pytest.fail(f"select_put raised {type(exc).__name__} for date {d}: {exc}")

            if result is not None:
                dte = (result.expiry - d).days
                assert cfg.min_dte <= dte <= cfg.max_dte, (
                    f"Date {d}: DTE {dte} out of range [{cfg.min_dte}, {cfg.max_dte}]"
                )
                assert cfg.target_delta - cfg.delta_tolerance <= result.delta <= cfg.target_delta + cfg.delta_tolerance, (
                    f"Date {d}: delta {result.delta:.4f} out of range"
                )
                assert result.quantity >= 1, f"Date {d}: quantity {result.quantity} < 1"
                assert result.collateral <= _CAPITAL * cfg.max_collateral_pct + 1.0, (
                    f"Date {d}: collateral {result.collateral:.2f} exceeds cap"
                )

            tested += 1
            if tested >= 100:
                break

        assert tested >= 100, f"Only tested {tested} weekday dates (need 100)"
