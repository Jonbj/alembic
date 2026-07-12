"""P0-09 — Regime multiplier applied, not hardcoded to 1.0.

Problem: portfolio_scheduler._run_cycle_inner passes regime_mult=1.0 to
write_execution_decision() and open_trade() even when the RedisStore
holds a non-1.0 multiplier (e.g. 0.2 for high_vol, 0.5 for caution).

This means the execution_decisions and trades tables show the wrong
regime multiplier — analytics and audit logs are inaccurate — and
position sizing is NOT scaled by regime (the actual sizing calculation
may or may not use regime_mult, but the recorded value is wrong for sure).

Fix: _run_cycle_inner reads regime:current from Redis and passes the
actual multiplier to write_execution_decision() and open_trade().
Falls back to 0.2 (fail-conservative, matching execution.py) when the
key is absent.

Acceptance: test_regime_multiplier_applied passes.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest


def _regime_state_json(multiplier: float) -> str:
    return json.dumps({
        "regime": "caution" if multiplier == 0.5 else "high_vol",
        "multiplier": multiplier,
        "vix": 25.0,
        "yield_curve": -0.1,
        "spy_momentum": -2.0,
        "timestamp": "2026-06-19T09:00:00+00:00",
        "sources": [],
    })


class TestRegimeMultiplierRead:
    """_get_regime_multiplier_from_redis must read Redis and fallback correctly."""

    def test_reads_multiplier_from_redis(self):
        """When regime:current is set, return its multiplier field."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = _regime_state_json(0.5)
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.5)

    def test_falls_back_to_conservative_when_key_absent(self):
        """When regime:current is absent, return 0.2 (fail-conservative, not 1.0)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = None
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.2), (
            "When regime:current is absent, must use 0.2 (high_vol fallback), NOT 1.0. "
            "1.0 would mean 'full allocation' which is incorrect without a known regime."
        )

    def test_falls_back_when_redis_unreachable(self):
        """When Redis is unreachable, return 0.2 (fail-conservative)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = ConnectionError("down")
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.2)

    def test_falls_back_when_json_corrupt(self):
        """Corrupt JSON in regime:current → return 0.2 (fail-conservative)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = "{not valid json"
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.2)

    def test_high_vol_multiplier_02(self):
        """high_vol regime with multiplier=0.2 is read correctly."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = _regime_state_json(0.2)
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.2)

    def test_normal_multiplier_10(self):
        """Normal regime with multiplier=1.0 reads 1.0."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = json.dumps({
                "regime": "normal",
                "multiplier": 1.0,
                "vix": 15.0,
                "yield_curve": 0.3,
                "spy_momentum": 2.0,
                "timestamp": "2026-06-19T09:00:00+00:00",
                "sources": [],
            })
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(1.0)


class TestRegimeMultiplierAppliedToSizing:
    """regime_mult must scale BUY order notional in _submit_portfolio_orders (P0-09 follow-up)."""

    def _make_order(self, symbol="AAPL", qty=10.0, side="BUY"):
        from src.backtest.engine.types import Order, OrderSide
        from datetime import datetime, timezone
        side_enum = OrderSide.BUY if side == "BUY" else OrderSide.SELL
        return Order.market_order(
            ts=datetime(2026, 6, 19, 14, 0, tzinfo=timezone.utc),
            symbol=symbol,
            side=side_enum,
            qty=qty,
        )

    def _make_market(self, price=150.0, symbol="AAPL"):
        from src.backtest.engine.types import MarketSnapshot
        from datetime import datetime, timezone
        return MarketSnapshot(
            timestamp=datetime(2026, 6, 19, 14, 0, tzinfo=timezone.utc),
            prices={symbol: price},
            volumes={symbol: 1_000_000.0},
            adv_20d={symbol: 1_000_000.0},
        )

    def test_submit_portfolio_orders_accepts_regime_mult(self):
        """_submit_portfolio_orders must accept a regime_mult parameter."""
        import inspect
        from src.workers.portfolio_scheduler import _submit_portfolio_orders
        sig = inspect.signature(_submit_portfolio_orders)
        assert "regime_mult" in sig.parameters, (
            "_submit_portfolio_orders must accept a regime_mult parameter — "
            "P0-09: the regime multiplier must reduce position size in high-vol regimes"
        )

    def test_regime_mult_half_halves_notional(self):
        """regime_mult=0.5 must result in exactly half the notional vs regime_mult=1.0."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured_notionals: list[float] = []

        def capture_fn(order, notional_or_qty, _tc):
            captured_notionals.append(notional_or_qty)

        order = self._make_order("AAPL", qty=10.0)
        market = self._make_market(price=150.0)

        _submit_portfolio_orders(
            [order], MagicMock(), market,
            _submit_fn=capture_fn, regime_mult=0.5,
        )
        _submit_portfolio_orders(
            [order], MagicMock(), market,
            _submit_fn=capture_fn, regime_mult=1.0,
        )

        assert len(captured_notionals) == 2, "Expected 2 submitted orders"
        n_half, n_full = captured_notionals
        assert pytest.approx(n_half * 2, rel=1e-4) == n_full, (
            f"regime_mult=0.5 notional ({n_half}) must be exactly half of "
            f"regime_mult=1.0 notional ({n_full})"
        )

    def test_regime_mult_zero_point_two_reduces_notional(self):
        """regime_mult=0.2 (high_vol) must reduce notional to 20% of baseline."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured: list[float] = []

        def capture_fn(order, n, _tc):
            captured.append(n)

        order = self._make_order("AAPL", qty=10.0)
        market = self._make_market(price=100.0)

        _submit_portfolio_orders(
            [order], MagicMock(), market,
            _submit_fn=capture_fn, regime_mult=0.2,
        )
        _submit_portfolio_orders(
            [order], MagicMock(), market,
            _submit_fn=capture_fn, regime_mult=1.0,
        )

        n_reduced, n_full = captured
        assert pytest.approx(n_reduced / n_full, rel=1e-4) == 0.2, (
            f"regime_mult=0.2 must produce 20% of baseline notional. "
            f"Got {n_reduced} vs baseline {n_full}"
        )


class TestRegimeMultiplierWholeShare:
    """F5: regime_mult must scale whole-share (non-fractionable) BUY qty too.

    The fractionable path scales `notional` by regime_mult; the whole-share path
    must derive its qty from that same scaled notional, not from raw
    `order.quantity` — which silently bypassed regime_mult on mega-caps (whole-share
    names), leaking full-size deployment in risk-off regimes. Zero behavior change
    when regime_mult == 1.0.
    """

    def _make_order(self, symbol="BRK.A", qty=10.0):
        from src.backtest.engine.types import Order, OrderSide
        from datetime import datetime, timezone
        return Order.market_order(
            ts=datetime(2026, 6, 19, 14, 0, tzinfo=timezone.utc),
            symbol=symbol,
            side=OrderSide.BUY,
            qty=qty,
        )

    def _make_market(self, price=100.0, symbol="BRK.A"):
        from src.backtest.engine.types import MarketSnapshot
        from datetime import datetime, timezone
        return MarketSnapshot(
            timestamp=datetime(2026, 6, 19, 14, 0, tzinfo=timezone.utc),
            prices={symbol: price},
            volumes={symbol: 1_000_000.0},
            adv_20d={symbol: 1_000_000.0},
        )

    def _capture_whole_share_qty(self, regime_mult: float) -> int:
        """Run _submit_portfolio_orders for a non-fractionable BUY and return the
        whole-share qty passed to the broker's MarketOrderRequest."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        trading_client = MagicMock()
        captured: list = []

        def _capture(req):
            captured.append(req)
            return MagicMock(id="test-id")

        trading_client.submit_order.side_effect = _capture

        order = self._make_order(qty=10.0)
        market = self._make_market(price=100.0)

        # Disable the broker bracket leg so the plain MarketOrderRequest(qty=...)
        # path is exercised. stop_policy/nav/risk_cfg None → no stop-risk sizing.
        # config is a frozen pydantic instance, so patch the whole object; the only
        # attribute read on this code path is ALPACA_BRACKET_ENABLED.
        with patch("src.config.config") as mock_cfg:
            mock_cfg.ALPACA_BRACKET_ENABLED = False
            _submit_portfolio_orders(
                [order], trading_client, market,
                fractionable_symbols=set(),  # symbol NOT in set → whole-share path
                regime_mult=regime_mult,
                nav=None, risk_cfg=None, stop_policy=None,
            )

        assert captured, (
            f"whole-share BUY was not submitted (regime_mult={regime_mult}) — "
            "the order was silently skipped in _submit_portfolio_orders"
        )
        return int(captured[0].qty)

    def test_regime_mult_scales_whole_share_qty(self):
        """regime_mult=0.5 must halve whole-share qty vs regime_mult=1.0 (F5)."""
        qty_full = self._capture_whole_share_qty(1.0)
        qty_half = self._capture_whole_share_qty(0.5)
        assert qty_full == 10, (
            f"regime_mult=1.0 whole-share qty should be 10 (qty*regime=10*1.0), "
            f"got {qty_full}"
        )
        assert qty_half == 5, (
            f"regime_mult=0.5 whole-share qty should be 5 (qty*regime=10*0.5), "
            f"got {qty_half} — regime_mult is being bypassed on whole-share BUYs (F5)"
        )

    def test_regime_mult_one_is_identity_whole_share(self):
        """regime_mult=1.0 must leave whole-share qty unchanged (zero behavior change)."""
        qty = self._capture_whole_share_qty(1.0)
        assert qty == 10, (
            f"regime_mult=1.0 should submit full qty=10, got {qty}"
        )

    def test_regime_mult_zero_point_two_whole_share(self):
        """regime_mult=0.2 must reduce whole-share qty to 20% (floored at 1 share)."""
        # qty=10, price=100, regime=0.2 → notional=$200 → whole_qty=int(200/100)=2
        qty = self._capture_whole_share_qty(0.2)
        assert qty == 2, (
            f"regime_mult=0.2 whole-share qty should be 2 (10*0.2), got {qty}"
        )
