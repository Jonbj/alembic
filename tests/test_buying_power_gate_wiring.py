"""Scheduler observability and BUY-path wiring for the buying-power gate."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _make_order(symbol="AAPL", qty=10.0):
    from src.backtest.engine.types import Order, OrderSide

    return Order.market_order(
        ts=datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc),
        symbol=symbol,
        side=OrderSide.BUY,
        qty=qty,
    )


def _make_market(price=100.0, symbol="AAPL"):
    from src.backtest.engine.types import MarketSnapshot

    return MarketSnapshot(
        timestamp=datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc),
        prices={symbol: price},
        volumes={symbol: 1_000_000.0},
        adv_20d={symbol: 1_000_000.0},
    )


def _ts():
    return datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)


def _suppress_cooldowns(monkeypatch):
    monkeypatch.setattr(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols",
        lambda _url: set(),
    )
    monkeypatch.setattr(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols",
        lambda _url: set(),
    )


class TestGateDecisionWriter:
    def test_writes_a_signal_linked_decision(self, monkeypatch):
        from src.workers.portfolio_scheduler import (
            _write_buying_power_gate_decision,
        )

        captured = {}

        class FakeStore:
            def write_execution_decision(self, **kwargs):
                captured.update(kwargs)
                return 1

            def close(self):
                pass

        monkeypatch.setattr("src.store.pg_store.PostgreSQLStore", FakeStore)

        _write_buying_power_gate_decision(
            ts=_ts(),
            symbol="AAPL",
            signal_id=42,
            regime_mult=0.7,
            decision="BUY_POWER_CAP",
            reason="capped delta=$500.00",
        )

        assert captured == {
            "tick_time": _ts(),
            "symbol": "AAPL",
            "signal_id": 42,
            "score": 0.0,
            "regime_mult": 0.7,
            "ema_pass": True,
            "decision": "BUY_POWER_CAP",
            "reason": "capped delta=$500.00",
        }

    def test_swallows_store_failure(self, monkeypatch):
        from src.workers.portfolio_scheduler import (
            _write_buying_power_gate_decision,
        )

        class BrokenStore:
            def __init__(self):
                raise RuntimeError("DB down")

        monkeypatch.setattr("src.store.pg_store.PostgreSQLStore", BrokenStore)

        _write_buying_power_gate_decision(
            ts=_ts(),
            symbol="AAPL",
            signal_id=None,
            regime_mult=1.0,
            decision="BUY_POWER_SHADOW",
            reason="would cap",
        )


class TestAccountDebugLine:
    def test_includes_multiplier(self):
        from src.workers.portfolio_scheduler import _account_debug_line

        assert _account_debug_line(10000.0, 5000.0, 10000.0, 2.0) == (
            "Account: equity=10000.00, cash=5000.00, "
            "buying_power=10000.00, multiplier=2.0"
        )

    def test_marks_unavailable_buying_power(self):
        from src.workers.portfolio_scheduler import _account_debug_line

        assert "buying_power=unavailable" in _account_debug_line(
            10000.0, 5000.0, None, 1.0
        )


class TestBuyingPowerGateWiring:
    def test_cap_reduces_fractionable_notional(self, monkeypatch):
        _suppress_cooldowns(monkeypatch)
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._fire_alert", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision",
            lambda *args, **kwargs: None,
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured = []
        _submit_portfolio_orders(
            [_make_order()],
            MagicMock(),
            _make_market(),
            _submit_fn=lambda _order, notional, _client: captured.append(notional),
            buying_power=500.0,
            notifier=MagicMock(),
            cycle_ts=_ts(),
            gate_mode="cap",
        )

        assert captured == [pytest.approx(500.0)]

    def test_shadow_preserves_notional_and_emits_observability(self, monkeypatch):
        _suppress_cooldowns(monkeypatch)
        alerts = []
        decisions = []
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._fire_alert",
            lambda *args, **kwargs: alerts.append(args),
        )
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision",
            lambda *args, **kwargs: decisions.append((args, kwargs)),
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured = []
        _submit_portfolio_orders(
            [_make_order()],
            MagicMock(),
            _make_market(),
            _submit_fn=lambda _order, notional, _client: captured.append(notional),
            buying_power=500.0,
            notifier=MagicMock(),
            cycle_ts=_ts(),
            signal_ids={"AAPL": 42},
            gate_mode="shadow",
        )

        assert captured == [pytest.approx(1000.0)]
        assert len(alerts) == 1
        assert decisions[0][1]["decision"] == "BUY_POWER_SHADOW"
        assert decisions[0][1]["signal_id"] == 42

    def test_zero_buying_power_skips_buy_and_records_it(self, monkeypatch):
        _suppress_cooldowns(monkeypatch)
        decisions = []
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._fire_alert", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision",
            lambda *args, **kwargs: decisions.append((args, kwargs)),
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured = []
        submitted = _submit_portfolio_orders(
            [_make_order()],
            MagicMock(),
            _make_market(),
            _submit_fn=lambda _order, notional, _client: captured.append(notional),
            buying_power=0.0,
            notifier=MagicMock(),
            cycle_ts=_ts(),
            gate_mode="shadow",
        )

        assert captured == []
        assert submitted == []
        assert decisions[0][1]["decision"] == "SKIP_BUY_POWER"

    def test_pass_has_no_side_effects(self, monkeypatch):
        _suppress_cooldowns(monkeypatch)
        alerts = []
        decisions = []
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._fire_alert",
            lambda *args, **kwargs: alerts.append(args),
        )
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision",
            lambda *args, **kwargs: decisions.append((args, kwargs)),
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured = []
        _submit_portfolio_orders(
            [_make_order()],
            MagicMock(),
            _make_market(),
            _submit_fn=lambda _order, notional, _client: captured.append(notional),
            buying_power=2000.0,
            notifier=MagicMock(),
            cycle_ts=_ts(),
            gate_mode="cap",
        )

        assert captured == [pytest.approx(1000.0)]
        assert alerts == []
        assert decisions == []

    def test_gate_is_inactive_for_legacy_callers_without_buying_power(
        self, monkeypatch
    ):
        _suppress_cooldowns(monkeypatch)
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured = []
        _submit_portfolio_orders(
            [_make_order()],
            MagicMock(),
            _make_market(),
            _submit_fn=lambda _order, notional, _client: captured.append(notional),
        )

        assert captured == [pytest.approx(1000.0)]

    def test_cap_uses_rounded_whole_share_quantity(self, monkeypatch):
        _suppress_cooldowns(monkeypatch)
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._fire_alert", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision",
            lambda *args, **kwargs: None,
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        trading_client = MagicMock()
        trading_client.submit_order.return_value.id = "order-1"
        submitted = _submit_portfolio_orders(
            [_make_order(qty=10.0)],
            trading_client,
            _make_market(price=150.0),
            fractionable_symbols=set(),
            buying_power=500.0,
            notifier=MagicMock(),
            cycle_ts=_ts(),
            gate_mode="cap",
        )

        assert len(submitted) == 1
        assert trading_client.submit_order.call_args.args[0].qty == 3

    def test_cap_skips_whole_share_when_one_share_is_unaffordable(
        self, monkeypatch
    ):
        _suppress_cooldowns(monkeypatch)
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._fire_alert", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision",
            lambda *args, **kwargs: None,
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        trading_client = MagicMock()
        submitted = _submit_portfolio_orders(
            [_make_order(qty=10.0)],
            trading_client,
            _make_market(price=150.0),
            fractionable_symbols=set(),
            buying_power=100.0,
            notifier=MagicMock(),
            cycle_ts=_ts(),
            gate_mode="cap",
        )

        assert submitted == []
        trading_client.submit_order.assert_not_called()
