"""Tests for hidden-cost reporting sections in the weekly performance report.

Covers:
  - _format_capital_efficiency_section  (Point 1: Cash Drag)
  - _format_feedback_stall_section       (Point 2: Feedback Threshold Stall)
  - _format_infrastructure_section       (Point 4: Infrastructure Break-Even)
  - _format_regime_section               (Point 6: Regime Multiplier Drag)
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
    sys.modules["src.config"] = MagicMock()
    _config_freshly_stubbed = True
# Set required attributes when we installed a MagicMock stub.
# Skip when the real (frozen pydantic) Config is already loaded.
try:
    sys.modules["src.config"].config.MIN_TRADE_PNL_THRESHOLD = 0.0
    sys.modules["src.config"].config.LLM_DAILY_BUDGET_USD = 5.0
except Exception:
    pass

from src.workers.performance import (  # noqa: E402
    _format_capital_efficiency_section,
    _format_feedback_stall_section,
    _format_infrastructure_section,
    _format_regime_section,
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
    def _make_redis(self, threshold=0.30, state=None):
        r = MagicMock()
        r.get_feedback_entry_threshold.return_value = threshold
        r.get_feedback_state.return_value = state or {}
        return r

    def test_normal_state_shows_green(self):
        redis = self._make_redis(threshold=0.30)
        result = _format_feedback_stall_section(redis)
        assert "Feedback Loop" in result
        assert "Normal" in result or "✅" in result

    def test_elevated_threshold_shows_red(self):
        redis = self._make_redis(threshold=0.55)
        result = _format_feedback_stall_section(redis)
        assert "ELEVATED" in result
        assert "0.55" in result

    def test_recovery_progress_shown(self):
        # recovery_win_streak is 3 (config/trading.yaml loss_feedback), so 1 win leaves 2 more needed.
        state = {"consecutive_wins": 1, "last_adjustment_ts": "2026-06-05T10:00:00+00:00"}
        redis = self._make_redis(threshold=0.50, state=state)
        result = _format_feedback_stall_section(redis)
        assert "1/" in result
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


# ---------------------------------------------------------------------------
# Point 6 — Regime Multiplier Drag
# ---------------------------------------------------------------------------
class TestRegimeSection:
    def _make_redis(self, regime="bull", multiplier=1.0, confidence=0.85):
        state = MagicMock()
        state.regime = regime
        state.multiplier = multiplier
        state.confidence = confidence
        r = MagicMock()
        r.get_regime.return_value = state
        r._r.get.return_value = None
        return r

    def test_bull_regime_shows_full_deployment(self):
        result = _format_regime_section(self._make_redis("bull", 1.0))
        assert "Regime" in result
        assert "bull" in result
        assert "×1.0" in result

    def test_high_vol_shows_80pct_discount(self):
        result = _format_regime_section(self._make_redis("high_vol", 0.2))
        assert "high_vol" in result
        assert "×0.2" in result
        # 80% withheld
        assert "80%" in result

    def test_no_regime_data_shows_fallback(self):
        redis = MagicMock()
        redis.get_regime.return_value = None
        result = _format_regime_section(redis)
        assert "No regime data" in result or "regime worker" in result

    def test_portfolio_value_used_for_dollar_ceiling(self):
        redis = self._make_redis("sideways", 0.7)
        redis._r.get.return_value = None
        result = _format_regime_section(redis, portfolio_value_usd=100_000)
        # ceiling = 0.10 × 0.7 × 5 × 100k = $35,000
        assert "35,000" in result
