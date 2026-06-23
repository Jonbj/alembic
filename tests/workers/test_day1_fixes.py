"""Day-1 execution fixes — capital deployment + churn + stop-loss.

Covers three fixes diagnosed from the controlled-paper Day-1 run:

FIX-A (capital utilization): regime:current is absent because the regime worker
  only writes it when both the FRED macro fetch AND the Ollama ensemble succeed.
  When absent, sizing collapsed to a flat ×0.2 regardless of market calm. A
  deterministic VIX fallback (from macro:vix:latest) now sizes risk-proportionally.

FIX-B (over-trading): the hold-minimum was 30 min vs a 15-min cycle cadence,
  allowing buy→sell→buy roundtrips. Raised to 90 min and made configurable.

FIX-C (stop-loss): notional/fractional BUYs cannot carry an Alpaca bracket, so
  positions had no stop. A synthetic per-cycle stop-loss force-closes breaches.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────── FIX-A: regime VIX fallback ───────────────────────────

def _redis_mock(values: dict):
    inst = MagicMock()
    inst.get.side_effect = lambda key: values.get(key)
    return inst


class TestVixFallbackMultiplier:
    def test_calm_vix_full_size(self):
        from src.workers.portfolio_scheduler import _vix_fallback_multiplier
        assert _vix_fallback_multiplier(15.0) == pytest.approx(1.0)

    def test_elevated_vix(self):
        from src.workers.portfolio_scheduler import _vix_fallback_multiplier
        assert _vix_fallback_multiplier(25.0) == pytest.approx(0.7)

    def test_stressed_vix(self):
        from src.workers.portfolio_scheduler import _vix_fallback_multiplier
        assert _vix_fallback_multiplier(35.0) == pytest.approx(0.4)

    def test_panic_vix_floor(self):
        from src.workers.portfolio_scheduler import _vix_fallback_multiplier
        assert _vix_fallback_multiplier(45.0) == pytest.approx(0.2)

    def test_unknown_vix_floor(self):
        from src.workers.portfolio_scheduler import _vix_fallback_multiplier
        assert _vix_fallback_multiplier(None) == pytest.approx(0.2)

    def test_boundary_20_is_elevated(self):
        from src.workers.portfolio_scheduler import _vix_fallback_multiplier
        # VIX == 20 is NOT < 20 → elevated bucket
        assert _vix_fallback_multiplier(20.0) == pytest.approx(0.7)


class TestRegimeMultiplierVixFallback:
    def test_absent_regime_uses_vix_calm(self):
        """regime:current absent + VIX 15 → ×1.0 (not the ×0.2 floor)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.return_value = _redis_mock(
                {"regime:current": None, "macro:vix:latest": "15.0"}
            )
            result = _get_regime_multiplier_from_redis("redis://x")
        assert result == pytest.approx(1.0)

    def test_absent_regime_uses_vix_stressed(self):
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.return_value = _redis_mock(
                {"regime:current": None, "macro:vix:latest": "35.0"}
            )
            result = _get_regime_multiplier_from_redis("redis://x")
        assert result == pytest.approx(0.4)

    def test_absent_regime_and_vix_floor(self):
        """Both absent → ×0.2 (fail-conservative, preserves prior behavior)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.return_value = _redis_mock(
                {"regime:current": None, "macro:vix:latest": None}
            )
            result = _get_regime_multiplier_from_redis("redis://x")
        assert result == pytest.approx(0.2)

    def test_present_regime_takes_priority(self):
        """When regime:current is present, its LLM multiplier wins (VIX ignored)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis
        payload = json.dumps({"regime": "bull", "multiplier": 1.0})
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.return_value = _redis_mock(
                {"regime:current": payload, "macro:vix:latest": "45.0"}
            )
            result = _get_regime_multiplier_from_redis("redis://x")
        assert result == pytest.approx(1.0)

    def test_corrupt_vix_value_floor(self):
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.return_value = _redis_mock(
                {"regime:current": None, "macro:vix:latest": "not-a-number"}
            )
            result = _get_regime_multiplier_from_redis("redis://x")
        assert result == pytest.approx(0.2)


# ─────────────────────────── FIX-C: synthetic stop-loss ───────────────────────────

class _Pos:
    def __init__(self, symbol, qty=1.0):
        self.symbol = symbol
        self.qty = qty


class _Mkt:
    def __init__(self, prices):
        self.prices = prices


class TestStopLossBreachedSymbols:
    def test_breach_below_threshold(self):
        from src.workers.portfolio_scheduler import _stop_loss_breached_symbols
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")], {"AAPL": 100.0}, _Mkt({"AAPL": 97.0}), 0.02
        )
        assert out == {"AAPL"}

    def test_no_breach_above_threshold(self):
        from src.workers.portfolio_scheduler import _stop_loss_breached_symbols
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")], {"AAPL": 100.0}, _Mkt({"AAPL": 99.0}), 0.02
        )
        assert out == set()

    def test_boundary_is_breach(self):
        from src.workers.portfolio_scheduler import _stop_loss_breached_symbols
        # price exactly at entry*(1-stop) counts as breached
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")], {"AAPL": 100.0}, _Mkt({"AAPL": 98.0}), 0.02
        )
        assert out == {"AAPL"}

    def test_missing_entry_price_skipped(self):
        from src.workers.portfolio_scheduler import _stop_loss_breached_symbols
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")], {}, _Mkt({"AAPL": 1.0}), 0.02
        )
        assert out == set()

    def test_missing_market_price_skipped(self):
        from src.workers.portfolio_scheduler import _stop_loss_breached_symbols
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")], {"AAPL": 100.0}, _Mkt({}), 0.02
        )
        assert out == set()

    def test_zero_stop_pct_disables(self):
        from src.workers.portfolio_scheduler import _stop_loss_breached_symbols
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")], {"AAPL": 100.0}, _Mkt({"AAPL": 1.0}), 0.0
        )
        assert out == set()

    def test_non_numeric_price_skipped(self):
        """Robust to MagicMock prices (heavily-mocked integration tests)."""
        from src.workers.portfolio_scheduler import _stop_loss_breached_symbols
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")], {"AAPL": 100.0}, _Mkt({"AAPL": MagicMock()}), 0.02
        )
        assert out == set()

    def test_only_breached_symbols_returned(self):
        from src.workers.portfolio_scheduler import _stop_loss_breached_symbols
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL"), _Pos("MSFT")],
            {"AAPL": 100.0, "MSFT": 100.0},
            _Mkt({"AAPL": 90.0, "MSFT": 100.0}),
            0.02,
        )
        assert out == {"AAPL"}


# ─────────────────────────── FIX-B + config plumbing ───────────────────────────

class TestConfigPlumbing:
    def test_hold_minimum_default_raised(self):
        from src.workers.portfolio_scheduler import _get_hold_minimum_minutes
        # trading.yaml now sets execution.hold_minimum_minutes: 90
        assert _get_hold_minimum_minutes() == 90

    def test_hold_minimum_exceeds_cycle_cadence(self):
        """Anti-churn invariant: hold must exceed the 15-min cycle cadence."""
        from src.workers.portfolio_scheduler import _get_hold_minimum_minutes
        assert _get_hold_minimum_minutes() > 15

    def test_risk_config_exposes_stop_loss(self):
        from src.workers.portfolio_scheduler import _load_risk_config
        cfg = _load_risk_config()
        assert "stop_loss" in cfg
        assert cfg["stop_loss"] == pytest.approx(0.02)
