"""Tests for the three hidden-cost reporting sections added in the trade-cost-realism feature.

Covers:
  - _format_capital_efficiency_section  (Point 1: Cash Drag)
  - _format_feedback_stall_section       (Point 2: Feedback Threshold Stall)
  - _format_infrastructure_section       (Point 4: Infrastructure Break-Even)
"""
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing performance.py (same pattern as
# test_performance_costs.py — all listed modules get MagicMock()).
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
_freshly_stubbed: list[str] = []
for _mod in _PLAIN_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
        _freshly_stubbed.append(_mod)

_numpy_freshly_stubbed = False
if "numpy" not in sys.modules:
    import numpy as _np_real
    sys.modules["numpy"] = _np_real
    _numpy_freshly_stubbed = True

_config_freshly_stubbed = False
if "src.config" not in sys.modules:
    _cfg_mod = MagicMock()
    _cfg_mod.config.MIN_TRADE_PNL_THRESHOLD = 0.0
    _cfg_mod.config.LLM_DAILY_BUDGET_USD = 5.0
    sys.modules["src.config"] = _cfg_mod
    _config_freshly_stubbed = True

from src.workers.performance import (  # noqa: E402
    _format_capital_efficiency_section,
    _format_feedback_stall_section,
    _format_infrastructure_section,
)

# Remove freshly-installed stubs so they don't leak into other test modules.
# Exception: src.config stays because performance functions lazy-import it.
for _mod in _freshly_stubbed:
    del sys.modules[_mod]
if _numpy_freshly_stubbed:
    del sys.modules["numpy"]
# Do NOT remove src.config — lazy imports inside performance functions need it.


# ---------------------------------------------------------------------------
# Point 1 — Capital Efficiency / Cash Drag
# ---------------------------------------------------------------------------
class TestCapitalEfficiency:
    def test_full_cash_shows_high_drag(self):
        result = _format_capital_efficiency_section(open_trades=[], portfolio_value_usd=100_000)
        assert "Capital Efficiency" in result
        assert "0 open pos" in result
        # 100% cash × 4.5% risk-free ≈ 4.5%/yr opportunity cost
        assert "4.5%" in result

    def test_partial_deployment(self):
        trades = [{"entry_notional": 10_000}, {"entry_notional": 10_000}]
        result = _format_capital_efficiency_section(open_trades=trades, portfolio_value_usd=100_000)
        assert "20.0%" in result
        assert "2 open pos" in result
        # 80% idle × 4.5% = 3.6%
        assert "3.6%" in result

    def test_zero_portfolio_value_shows_fallback(self):
        trades = [{"entry_notional": 5_000}]
        result = _format_capital_efficiency_section(open_trades=trades, portfolio_value_usd=0)
        assert "unavailable" in result

    def test_efficiency_ratio_shown(self):
        # 5 positions × $10k on $100k portfolio = 50% deployed = 100% of theoretical max
        trades = [{"entry_notional": 10_000}] * 5
        result = _format_capital_efficiency_section(open_trades=trades, portfolio_value_usd=100_000)
        assert "100%" in result


# ---------------------------------------------------------------------------
# Point 2 — Feedback Loop / Threshold Stall
# ---------------------------------------------------------------------------
class TestFeedbackStall:
    def _make_redis(self, threshold=0.30, scale=1.0, state=None):
        r = MagicMock()
        r.get_feedback_entry_threshold.return_value = threshold
        r.get_feedback_regime_scale.return_value = scale
        r.get_feedback_state.return_value = state or {}
        return r

    def test_normal_state_shows_green(self):
        redis = self._make_redis(threshold=0.30)
        result = _format_feedback_stall_section(redis)
        assert "Feedback Loop" in result
        assert "Normal" in result or "✅" in result

    def test_elevated_threshold_shows_red(self):
        redis = self._make_redis(threshold=0.55, scale=0.64)
        result = _format_feedback_stall_section(redis)
        assert "ELEVATED" in result
        assert "0.55" in result

    def test_recovery_progress_shown(self):
        state = {"consecutive_wins": 3, "last_adjustment_ts": "2026-06-05T10:00:00+00:00"}
        redis = self._make_redis(threshold=0.50, state=state)
        result = _format_feedback_stall_section(redis)
        assert "3/" in result
        assert "2 more" in result

    def test_last_trigger_date_shown(self):
        state = {"last_adjustment_ts": "2026-06-01T08:00:00+00:00"}
        redis = self._make_redis(threshold=0.45, state=state)
        result = _format_feedback_stall_section(redis)
        assert "2026-06-01" in result


# ---------------------------------------------------------------------------
# Point 4 — Infrastructure Break-Even
# ---------------------------------------------------------------------------
class TestInfrastructureSection:
    def _make_pg(self, llm_30d=0.0):
        pg = MagicMock()
        pg.fetch_llm_budget_period.return_value = llm_30d
        return pg

    def test_shows_monthly_cost(self):
        result = _format_infrastructure_section(self._make_pg(llm_30d=70.0))
        assert "Infrastructure" in result
        assert "Monthly" in result
        assert "Break-even" in result

    def test_breakeven_at_10pct_return(self):
        # annual_fixed=1440, llm=0 → break-even at 10% = $14,400
        result = _format_infrastructure_section(self._make_pg(llm_30d=0.0))
        assert "14,400" in result

    def test_llm_cost_included_in_monthly(self):
        # monthly_fixed = 1440/12 = 120, llm = 100 → total = 220
        result = _format_infrastructure_section(self._make_pg(llm_30d=100.0))
        assert "220" in result
