"""P2-05 Execution Edge Cases — TDD tests.

Covers:
  A) Idempotency fail-closed on Redis unavailable (_get_fired_signal_ids → None)
  B) Net exposure cap wired from trading.yaml into ConstraintEnforcer
  C) Submission filter: S4 BUY excluded when idempotency skip is active
  D) Broker reject triggers _on_broker_reject callback
  E) Safety confirmations: missing price, bracket failure
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.backtest.engine.types import OrderSide, OrderType
from src.portfolio.types import CombinedOrder


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_order(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    qty: float = 10.0,
    strategy_id: str = "S1",
) -> CombinedOrder:
    return CombinedOrder(
        order_id=f"oid-{symbol}",
        timestamp=datetime(2026, 6, 21, 14, 0, tzinfo=timezone.utc),
        symbol=symbol,
        side=side,
        quantity=qty,
        order_type=OrderType.MARKET,
        strategy_id=strategy_id,
        allocation_weight=0.3,
    )


def _make_market(prices: dict | None = None):
    from src.backtest.engine.types import MarketSnapshot
    prices = prices or {"SPY": 100.0}
    return MarketSnapshot(
        timestamp=datetime(2026, 6, 21, 14, 0, tzinfo=timezone.utc),
        prices=prices,
        volumes={sym: 1_000_000.0 for sym in prices},
        adv_20d={sym: 1_000_000.0 for sym in prices},
    )


# ── P2-05-A: _get_fired_signal_ids fail-closed ───────────────────────────────


class TestGetFiredSignalIds:
    def test_returns_none_on_redis_connection_error(self):
        """P2-05-A: Redis unreachable → returns None (fail-closed sentinel)."""
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = ConnectionError("Redis down")
            from src.workers.portfolio_scheduler import _get_fired_signal_ids
            result = _get_fired_signal_ids("2026-06-21", "redis://localhost")
        assert result is None

    def test_returns_none_on_redis_timeout(self):
        """P2-05-A: Redis timeout → returns None (fail-closed sentinel)."""
        import redis as _redis_mod
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = _redis_mod.exceptions.TimeoutError("timeout")
            from src.workers.portfolio_scheduler import _get_fired_signal_ids
            result = _get_fired_signal_ids("2026-06-21", "redis://localhost")
        assert result is None

    def test_returns_set_of_int_on_success(self):
        """P2-05-A: Redis works → returns set[int] of fired signal IDs."""
        mock_r = MagicMock()
        mock_r.smembers.return_value = {b"101", b"202", b"303"}
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_r
            from src.workers.portfolio_scheduler import _get_fired_signal_ids
            result = _get_fired_signal_ids("2026-06-21", "redis://localhost")
        assert isinstance(result, set)
        assert result == {101, 202, 303}

    def test_returns_empty_set_when_key_absent(self):
        """P2-05-A: Key not in Redis (first run of day) → empty set, NOT None."""
        mock_r = MagicMock()
        mock_r.smembers.return_value = set()
        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_r
            from src.workers.portfolio_scheduler import _get_fired_signal_ids
            result = _get_fired_signal_ids("2026-06-21", "redis://localhost")
        assert result == set()
        assert result is not None


# ── P2-05-A: _apply_idempotency_filter ───────────────────────────────────────


class TestApplyIdempotencyFilter:
    def test_removes_buy_for_skipped_symbol(self):
        """Fail-closed: S4 BUY for a skipped symbol is excluded."""
        from src.workers.portfolio_scheduler import _apply_idempotency_filter
        orders = [_make_order("AAPL", OrderSide.BUY, strategy_id="S4")]
        result = _apply_idempotency_filter(orders, skip_syms={"AAPL"})
        assert result == []

    def test_keeps_sell_for_skipped_symbol(self):
        """SELL orders are not affected by the idempotency skip (only BUYs are filtered)."""
        from src.workers.portfolio_scheduler import _apply_idempotency_filter
        orders = [_make_order("AAPL", OrderSide.SELL, strategy_id="S4")]
        result = _apply_idempotency_filter(orders, skip_syms={"AAPL"})
        assert len(result) == 1

    def test_keeps_non_skipped_buy(self):
        """BUY for a symbol NOT in skip_syms is not filtered out."""
        from src.workers.portfolio_scheduler import _apply_idempotency_filter
        orders = [
            _make_order("AAPL", OrderSide.BUY),
            _make_order("SPY", OrderSide.BUY),
        ]
        result = _apply_idempotency_filter(orders, skip_syms={"AAPL"})
        assert len(result) == 1
        assert result[0].symbol == "SPY"

    def test_empty_skip_set_returns_all_orders(self):
        """Empty skip set → all orders pass through unchanged."""
        from src.workers.portfolio_scheduler import _apply_idempotency_filter
        orders = [
            _make_order("AAPL", OrderSide.BUY),
            _make_order("SPY", OrderSide.SELL),
        ]
        result = _apply_idempotency_filter(orders, skip_syms=set())
        assert result == orders


# ── P2-05-B: _load_risk_config ────────────────────────────────────────────────


class TestLoadRiskConfig:
    def test_reads_max_portfolio_exposure_from_yaml(self):
        """P2-05-B: reads risk.max_portfolio_exposure from trading.yaml."""
        from src.workers.portfolio_scheduler import _load_risk_config
        cfg = _load_risk_config()
        assert "max_portfolio_exposure" in cfg
        assert isinstance(cfg["max_portfolio_exposure"], float)
        assert 0.0 < cfg["max_portfolio_exposure"] <= 1.0

    def test_reads_max_single_asset_pct_from_yaml(self):
        """P2-05-B: reads risk.max_position_pct as max_single_asset_pct."""
        from src.workers.portfolio_scheduler import _load_risk_config
        cfg = _load_risk_config()
        assert "max_single_asset_pct" in cfg
        assert isinstance(cfg["max_single_asset_pct"], float)
        assert 0.0 < cfg["max_single_asset_pct"] <= 1.0

    def test_returns_safe_defaults_when_file_missing(self):
        """P2-05-B: trading.yaml missing → returns safe hardcoded defaults."""
        from src.workers.portfolio_scheduler import _load_risk_config
        with patch("builtins.open", side_effect=FileNotFoundError("not found")):
            cfg = _load_risk_config()
        assert cfg["max_portfolio_exposure"] == 0.50
        assert cfg["max_single_asset_pct"] == 0.10

    def test_custom_values_override_defaults(self, tmp_path):
        """P2-05-B: non-default YAML values are returned correctly."""
        import yaml
        from src.workers.portfolio_scheduler import _TRADING_YAML
        fake_yaml = tmp_path / "trading.yaml"
        fake_yaml.write_text(yaml.dump({
            "risk": {"max_portfolio_exposure": 0.30, "max_position_pct": 0.05}
        }))
        with patch("src.workers.portfolio_scheduler._TRADING_YAML", fake_yaml):
            from src.workers.portfolio_scheduler import _load_risk_config
            cfg = _load_risk_config()
        assert cfg["max_portfolio_exposure"] == 0.30
        assert cfg["max_single_asset_pct"] == 0.05


# ── P2-05-D: Broker reject callback ──────────────────────────────────────────


class TestBrokerRejectCallback:
    def test_on_broker_reject_called_when_submit_raises(self):
        """P2-05-D: _on_broker_reject callback is invoked when submit_fn raises."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [_make_order("SPY", OrderSide.BUY, qty=10.0)]
        market = _make_market(prices={"SPY": 100.0})
        rejected = []

        def mock_submit(order, notional, client):
            raise RuntimeError("margin insufficient")

        _submit_portfolio_orders(
            orders, MagicMock(), market,
            _submit_fn=mock_submit,
            _on_broker_reject=lambda sym, side, exc: rejected.append((sym, side, str(exc))),
        )

        assert len(rejected) == 1
        assert rejected[0][0] == "SPY"
        assert "margin insufficient" in rejected[0][2]

    def test_rejected_order_not_in_submitted_list(self):
        """P2-05-D: rejected order is not appended to the submitted list."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [_make_order("SPY", OrderSide.BUY, qty=10.0)]
        market = _make_market(prices={"SPY": 100.0})

        submitted = _submit_portfolio_orders(
            orders, MagicMock(), market,
            _submit_fn=lambda o, n, c: (_ for _ in ()).throw(RuntimeError("rejected")),
        )
        assert len(submitted) == 0

    def test_reject_on_first_does_not_stop_second(self):
        """P2-05-D: broker reject on one symbol does not abort the remaining orders."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [
            _make_order("SPY", OrderSide.BUY, qty=10.0),
            _make_order("QQQ", OrderSide.BUY, qty=5.0),
        ]
        market = _make_market(prices={"SPY": 100.0, "QQQ": 100.0})
        call_count = 0

        def mock_submit(order, notional, client):
            nonlocal call_count
            call_count += 1
            if order.symbol == "SPY":
                raise RuntimeError("SPY rejected")

        submitted = _submit_portfolio_orders(orders, MagicMock(), market, _submit_fn=mock_submit)
        assert len(submitted) == 1
        assert submitted[0]["symbol"] == "QQQ"


# ── P2-05-E: Safety path confirmations ───────────────────────────────────────


class TestSafetyPathConfirmations:
    def test_buy_blocked_when_price_missing(self):
        """Existing safety: BUY is skipped when price is not in market snapshot."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [_make_order("AAPL", OrderSide.BUY, qty=10.0)]
        market = _make_market(prices={})  # no price for AAPL

        submitted = _submit_portfolio_orders(
            orders, MagicMock(), market, _submit_fn=lambda o, n, c: None
        )
        assert len(submitted) == 0

    def test_sell_proceeds_without_price(self):
        """Existing safety: SELL orders do not require a price in market snapshot."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [_make_order("AAPL", OrderSide.SELL, qty=10.0)]
        market = _make_market(prices={})  # no price needed for SELL

        submitted = _submit_portfolio_orders(
            orders, MagicMock(), market, _submit_fn=lambda o, n, c: None
        )
        assert len(submitted) == 1

    def test_bracket_failure_leaves_no_submitted_entry(self):
        """Existing safety: when bracket submit raises, the order is not recorded."""
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [_make_order("SPY", OrderSide.BUY, qty=10.0)]
        market = _make_market(prices={"SPY": 450.0})

        def mock_submit(order, notional, client):
            raise RuntimeError("bracket not supported for this symbol")

        submitted = _submit_portfolio_orders(orders, MagicMock(), market, _submit_fn=mock_submit)
        assert len(submitted) == 0
