"""Test cost analysis section in trade P&L report."""
import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub out heavy dependencies that are not needed for the pure-formatting
# function under test.  These must be inserted BEFORE importing performance.
#
# Important: numpy stub must have bool_ as a real type so that pytest.approx
# (used in other test modules in the same session) does not break.
# ---------------------------------------------------------------------------
_PLAIN_STUBS = [
    "httpx",
    "psycopg2",
    "psycopg2.extras",
    "celery",
    "celery.utils.log",
    "src.notifications.telegram",
    "src.performance.drift",
    "src.performance.ic",
    "src.performance.postmortem",
    "src.performance.weights",
    "src.store.pg_store",
    "src.store.redis_store",
    "src.workers.celery_app",
    "src.workers.execution",
    "src.models.performance",
]
for _mod in _PLAIN_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# numpy: stub with bool_ as a real type so pytest.approx doesn't choke
if "numpy" not in sys.modules:
    _np_mock = MagicMock()
    _np_mock.bool_ = bool   # pytest.approx uses isinstance(val, np.bool_)
    sys.modules["numpy"] = _np_mock

# src.config: stub only if not already loaded (pydantic not available in CI)
if "src.config" not in sys.modules:
    _cfg_mod = MagicMock()
    _cfg_mod.config.MIN_TRADE_PNL_THRESHOLD = 0.0
    sys.modules["src.config"] = _cfg_mod

from src.workers.performance import _format_trade_metrics_section as _format_trade_pnl_section  # noqa: E402


class TestCostAnalysisSection:
    def _full_summary(self):
        return {
            "total_trades": 10,
            "win_rate": 0.60,
            "avg_gross_pnl": 25.0,
            "avg_slippage_est": 3.5,
            "avg_net_pnl": 21.5,
            "total_gross_pnl": 250.0,
            "total_net_pnl": 215.0,
            "total_notional": 50_000.0,
            "avg_hold_minutes": 90.0,
            "trades_per_week": 5.0,
            "return_on_notional": 0.0043,
            "slippage_pct_of_gross": 0.14,
            "avg_cost_bps": 6.5,
            "total_cost_usd": 35.0,
            "avg_spread_cost_bps": 5.0,
            "avg_impact_cost_bps": 0.8,
            "cost_drag_pct": 0.0007,
        }

    def test_cost_section_present_when_data_available(self):
        result = _format_trade_pnl_section(self._full_summary())
        assert "Cost Analysis" in result
        assert "6.5" in result      # avg_cost_bps
        assert "35" in result       # total_cost_usd (rounded)

    def test_cost_section_shows_annualized_drag(self):
        result = _format_trade_pnl_section(self._full_summary())
        assert "bps/yr" in result or "annuali" in result.lower() or "drag" in result.lower()

    def test_cost_section_absent_message_when_no_cost_data(self):
        """Pre-019 trades have avg_cost_bps=0 — show N/A note."""
        summary = self._full_summary()
        summary["avg_cost_bps"] = 0.0
        summary["total_cost_usd"] = 0.0
        result = _format_trade_pnl_section(summary)
        assert "Cost Analysis" in result
        # Either "no cost data" or similar
        assert "no cost" in result.lower() or "n/a" in result.lower() or "pre-" in result.lower()
