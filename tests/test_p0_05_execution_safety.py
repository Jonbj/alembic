"""P0-05 — Execution Safety Contract.

Problems:
1. Pyramiding: _submit_portfolio_orders has no guard against submitting a BUY
   when an open DB trade already exists for that symbol.
   Result: META×17, IWM×16, AZN×14 simultaneous open positions.

2. Stop-loss not enforced: ALPACA_BRACKET_ENABLED defaults to False, so bracket
   orders (which carry the stop-loss leg) are never submitted.
   Result: unlimited downside exposure on every open position.

Fixes:
1. _submit_portfolio_orders gains `open_trade_symbols` parameter: BUY orders for
   symbols in that set are skipped (logged at WARNING level).
2. ALPACA_BRACKET_ENABLED defaults to True so every BUY carries a stop-loss leg.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ─── helpers (mirror test_portfolio_scheduler.py) ──────────────────────────────

def _make_combined_order(symbol, side, qty=10.0, alloc_weight=0.05):
    order = MagicMock()
    order.symbol = symbol
    order.side = side
    order.quantity = qty
    order.allocation_weight = alloc_weight
    return order


def _make_market(prices=None):
    market = MagicMock()
    market.prices = prices or {"SPY": 450.0, "QQQ": 380.0, "META": 520.0, "AAPL": 195.0}
    return market


# ─── P0-05-A: duplicate BUY guard ──────────────────────────────────────────────

class TestSkipDuplicateBuy:
    """BUY orders for symbols with existing open DB trades must be skipped."""

    def test_skip_buy_when_symbol_has_open_trade(self):
        """BUY for META is dropped when META is in open_trade_symbols."""
        from src.backtest.engine.types import OrderSide
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [_make_combined_order("META", OrderSide.BUY, qty=10.0)]
        market = _make_market()

        submitted_calls: list[str] = []
        submitted = _submit_portfolio_orders(
            orders,
            MagicMock(),
            market,
            _submit_fn=lambda o, n, c: submitted_calls.append(o.symbol),
            open_trade_symbols={"META"},
        )

        assert len(submitted) == 0, "BUY for META must be skipped — open trade exists"
        assert "META" not in submitted_calls

    def test_buy_allowed_when_no_open_trade(self):
        """BUY for AAPL is submitted when AAPL has no open trade."""
        from src.backtest.engine.types import OrderSide
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [_make_combined_order("AAPL", OrderSide.BUY, qty=5.0)]
        market = _make_market()

        submitted = _submit_portfolio_orders(
            orders,
            MagicMock(),
            market,
            _submit_fn=lambda o, n, c: None,
            open_trade_symbols=set(),
        )

        assert len(submitted) == 1

    def test_open_trade_symbols_default_allows_all(self):
        """When open_trade_symbols is None (not passed), all BUYs proceed."""
        from src.backtest.engine.types import OrderSide
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [
            _make_combined_order("SPY", OrderSide.BUY, qty=10.0),
            _make_combined_order("QQQ", OrderSide.BUY, qty=5.0),
        ]
        market = _make_market()

        submitted = _submit_portfolio_orders(
            orders,
            MagicMock(),
            market,
            _submit_fn=lambda o, n, c: None,
        )

        assert len(submitted) == 2

    def test_sell_not_affected_by_open_trade_guard(self):
        """SELL orders are never blocked by open_trade_symbols — guard is BUY-only."""
        from src.backtest.engine.types import OrderSide
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [_make_combined_order("META", OrderSide.SELL, qty=10.0)]
        market = _make_market()

        submitted = _submit_portfolio_orders(
            orders,
            MagicMock(),
            market,
            _submit_fn=lambda o, n, c: None,
            open_trade_symbols={"META"},  # META in open set, but this is a SELL
        )

        assert len(submitted) == 1, "SELL for META must not be blocked by open_trade_symbols"

    def test_mixed_batch_only_skips_open_symbols(self):
        """In a mixed batch, only BUY orders for open symbols are skipped."""
        from src.backtest.engine.types import OrderSide
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        orders = [
            _make_combined_order("META", OrderSide.BUY, qty=10.0),   # skip — open
            _make_combined_order("AAPL", OrderSide.BUY, qty=5.0),    # submit — no open trade
            _make_combined_order("SPY",  OrderSide.SELL, qty=8.0),   # submit — sell always ok
        ]
        market = _make_market()
        submitted_syms: list[str] = []

        submitted = _submit_portfolio_orders(
            orders,
            MagicMock(),
            market,
            _submit_fn=lambda o, n, c: submitted_syms.append(o.symbol),
            open_trade_symbols={"META"},
        )

        assert len(submitted) == 2
        assert "META" not in submitted_syms
        assert "AAPL" in submitted_syms
        assert "SPY" in submitted_syms


# ─── P0-05-B: stop-loss on every BUY ──────────────────────────────────────────

class TestStopLossDefault:
    """ALPACA_BRACKET_ENABLED must default to True — every BUY needs a stop-loss leg."""

    def test_bracket_enabled_defaults_to_true(self):
        """ALPACA_BRACKET_ENABLED must default to True (no explicit env var)."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ALPACA_BRACKET_ENABLED", None)
            from src.config import Config
            cfg = Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
            )
        assert cfg.ALPACA_BRACKET_ENABLED is True, (
            "ALPACA_BRACKET_ENABLED must default to True so every BUY carries a stop-loss. "
            "P0-05 requires stop-loss on all new positions. "
            "Set ALPACA_BRACKET_ENABLED=false only for deliberate paper-mode override."
        )

    def test_bracket_can_be_disabled_explicitly(self):
        """ALPACA_BRACKET_ENABLED=false must be respected when set explicitly."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ALPACA_BRACKET_ENABLED": "false"}):
            from src.config import Config
            cfg = Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
            )
        assert cfg.ALPACA_BRACKET_ENABLED is False
