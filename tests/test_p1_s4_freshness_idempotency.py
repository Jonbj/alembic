"""P1-S4-FRESHNESS-IDEMPOTENCY — Freshness gate and idempotency key for S4 signals.

Problem (forensic report 2026-06-17):
- S4 uses signals up to 24h old; trades on 2-day-old news confirmed in forensics.
- Same signal_id fires BUY in multiple consecutive 15-min cycles → pyramiding.

Fix:
  A) Freshness gate: _filter_stale_signals rejects signals older than max_signal_age_hours
     (default 4h, configurable in S4Config). Stale signals produce SIGNAL_STALE_SKIP
     audit rows.
  B) Idempotency: _get_fired_signal_ids / _mark_signal_fired track fired signal_ids in
     a per-session-date Redis set (key: s4:fired_signals:<YYYY-MM-DD>, TTL 30h).
     Duplicate signals produce SIGNAL_DUPLICATE_SKIP audit rows.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from src.models.signals import SentimentResult


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_signal(symbol: str, age_hours: float, score: float = 0.5) -> SentimentResult:
    """Build a SentimentResult with generated_at = now - age_hours."""
    now = datetime.now(timezone.utc)
    return SentimentResult(
        symbol=symbol,
        score=score,
        confidence=0.8,
        reasoning="test",
        model_id="finbert",
        ensemble_std=0.0,
        fallback_used=False,
        generated_at=now - timedelta(hours=age_hours),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Group A — Freshness gate
# ─────────────────────────────────────────────────────────────────────────────

class TestS4FreshnessGate:
    """_filter_stale_signals must split signals into (fresh, stale) by age."""

    def test_fresh_signal_passes_gate(self):
        """Signal 2h old with max_age=4h is fresh — must not be filtered out."""
        from src.workers.portfolio_scheduler import _filter_stale_signals

        fresh_signal = _make_signal("AAPL", age_hours=2.0)
        now = datetime.now(timezone.utc)
        fresh, stale = _filter_stale_signals([fresh_signal], max_age_hours=4, now_utc=now)

        assert fresh_signal in fresh, "2h-old signal must survive the 4h gate"
        assert fresh_signal not in stale

    def test_stale_signal_blocked_by_gate(self):
        """Signal 5h old with max_age=4h must be filtered out."""
        from src.workers.portfolio_scheduler import _filter_stale_signals

        stale_signal = _make_signal("AAPL", age_hours=5.0)
        now = datetime.now(timezone.utc)
        fresh, stale = _filter_stale_signals([stale_signal], max_age_hours=4, now_utc=now)

        assert stale_signal not in fresh, "5h-old signal must be blocked by the 4h gate"
        assert stale_signal in stale

    def test_mixed_signals_only_fresh_survive(self):
        """With max_age=4h: 1h and 3h signals pass; 6h signal is dropped."""
        from src.workers.portfolio_scheduler import _filter_stale_signals

        s1 = _make_signal("AAPL", 1.0)
        s2 = _make_signal("MSFT", 3.0)
        s3 = _make_signal("NVDA", 6.0)
        now = datetime.now(timezone.utc)
        fresh, stale = _filter_stale_signals([s1, s2, s3], max_age_hours=4, now_utc=now)

        assert s1 in fresh
        assert s2 in fresh
        assert s3 not in fresh
        assert s3 in stale
        assert len(fresh) == 2
        assert len(stale) == 1

    def test_all_stale_returns_empty_fresh_list(self):
        """When all signals are stale, fresh list is empty."""
        from src.workers.portfolio_scheduler import _filter_stale_signals

        signals = [_make_signal(sym, 10.0) for sym in ("AAPL", "MSFT", "NVDA")]
        now = datetime.now(timezone.utc)
        fresh, stale = _filter_stale_signals(signals, max_age_hours=4, now_utc=now)

        assert fresh == [], "All stale → fresh list must be empty"
        assert len(stale) == 3

    def test_max_signal_age_hours_is_configurable(self):
        """max_age_hours=1 rejects a 90-min-old signal."""
        from src.workers.portfolio_scheduler import _filter_stale_signals

        sig = _make_signal("AAPL", age_hours=1.5)
        now = datetime.now(timezone.utc)
        fresh, stale = _filter_stale_signals([sig], max_age_hours=1, now_utc=now)

        assert sig not in fresh, "1.5h-old signal must be blocked by max_age=1h"
        assert sig in stale

    def test_negative_age_treated_as_zero_not_stale(self):
        """Signal with generated_at slightly in the future (clock skew) must not be stale."""
        from src.workers.portfolio_scheduler import _filter_stale_signals

        future_signal = _make_signal("AAPL", age_hours=-0.1)  # 6 min in future
        now = datetime.now(timezone.utc)
        fresh, stale = _filter_stale_signals([future_signal], max_age_hours=4, now_utc=now)

        assert future_signal in fresh, "Clock-skew (slightly future) signal must not be treated as stale"
        assert future_signal not in stale

    def test_s4_config_has_max_signal_age_hours_field(self):
        """S4Config must expose max_signal_age_hours with a non-zero default."""
        from src.strategies.s4.config import S4Config

        cfg = S4Config()
        assert hasattr(cfg, "max_signal_age_hours"), (
            "S4Config must have max_signal_age_hours field for P1-S4-FRESHNESS-IDEMPOTENCY"
        )
        assert cfg.max_signal_age_hours > 0, "max_signal_age_hours default must be > 0"


# ─────────────────────────────────────────────────────────────────────────────
# Group B — Idempotency gate
# ─────────────────────────────────────────────────────────────────────────────

class TestS4IdempotencyGate:
    """Fired signal_ids must be tracked per session date in Redis."""

    def test_unfired_signal_id_not_in_empty_set(self):
        """get_fired_signal_ids returns empty set when no signals have been fired yet."""
        from src.workers.portfolio_scheduler import _get_fired_signal_ids

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.smembers.return_value = set()
            mock_cls.from_url.return_value = inst

            fired = _get_fired_signal_ids("2026-06-19", "redis://localhost:6379/0")

        assert fired == set(), "Empty Redis set → no fired signal_ids"

    def test_previously_fired_signal_id_appears_in_set(self):
        """get_fired_signal_ids returns the IDs already in the Redis set."""
        from src.workers.portfolio_scheduler import _get_fired_signal_ids

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.smembers.return_value = {b"42", b"99"}
            mock_cls.from_url.return_value = inst

            fired = _get_fired_signal_ids("2026-06-19", "redis://localhost:6379/0")

        assert 42 in fired
        assert 99 in fired

    def test_mark_signal_fired_adds_to_redis_set(self):
        """_mark_signal_fired must call SADD on the session key."""
        from src.workers.portfolio_scheduler import _mark_signal_fired

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            mock_cls.from_url.return_value = inst

            _mark_signal_fired(42, "2026-06-19", "redis://localhost:6379/0")

        inst.sadd.assert_called_once_with("s4:fired_signals:2026-06-19", 42)

    def test_mark_signal_fired_sets_ttl_on_key(self):
        """_mark_signal_fired must set TTL (≤ 30h) on the session key so it auto-expires."""
        from src.workers.portfolio_scheduler import _mark_signal_fired

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            mock_cls.from_url.return_value = inst

            _mark_signal_fired(42, "2026-06-19", "redis://localhost:6379/0")

        # expire should be called with the key and a TTL in seconds ≤ 30*3600
        assert inst.expire.called, "_mark_signal_fired must call Redis EXPIRE"
        _key, ttl = inst.expire.call_args[0]
        assert _key == "s4:fired_signals:2026-06-19"
        assert 0 < ttl <= 30 * 3600, f"TTL must be ≤ 30h (108000s), got {ttl}"

    def test_idempotency_redis_unreachable_returns_none(self):
        """P2-05-A: When Redis is unreachable, _get_fired_signal_ids returns None (fail-closed sentinel).

        None signals the caller to treat all S4 BUY signals as already-fired, preventing
        duplicate BUYs when idempotency state cannot be verified.
        """
        from src.workers.portfolio_scheduler import _get_fired_signal_ids

        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = ConnectionError("down")

            fired = _get_fired_signal_ids("2026-06-19", "redis://localhost:6379/0")

        assert fired is None, "Redis unreachable must return None (fail-closed), not empty set"

    def test_idempotency_redis_unreachable_mark_does_not_raise(self):
        """When Redis is unreachable, _mark_signal_fired must not raise — logs warning only."""
        from src.workers.portfolio_scheduler import _mark_signal_fired

        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = ConnectionError("down")

            # Must not raise
            _mark_signal_fired(42, "2026-06-19", "redis://localhost:6379/0")

    def test_session_key_format_uses_date(self):
        """Redis key must be s4:fired_signals:<YYYY-MM-DD>."""
        from src.workers.portfolio_scheduler import _mark_signal_fired

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            mock_cls.from_url.return_value = inst

            _mark_signal_fired(7, "2026-06-19", "redis://localhost:6379/0")

        sadd_key = inst.sadd.call_args[0][0]
        assert sadd_key == "s4:fired_signals:2026-06-19", (
            f"Expected 's4:fired_signals:2026-06-19', got '{sadd_key}'"
        )

    def test_different_session_dates_use_different_keys(self):
        """Signals from two different session dates are tracked under different Redis keys."""
        from src.workers.portfolio_scheduler import _mark_signal_fired

        calls = []

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.sadd.side_effect = lambda key, val: calls.append(key)
            mock_cls.from_url.return_value = inst

            _mark_signal_fired(1, "2026-06-18", "redis://localhost:6379/0")
            _mark_signal_fired(1, "2026-06-19", "redis://localhost:6379/0")

        assert "s4:fired_signals:2026-06-18" in calls
        assert "s4:fired_signals:2026-06-19" in calls
        assert calls[0] != calls[1], "Different dates must produce different Redis keys"


# ─────────────────────────────────────────────────────────────────────────────
# Group C — Weekend / long-gap signal preservation (FIX-D extended)
# ─────────────────────────────────────────────────────────────────────────────

class TestWeekendSignalPreservation:
    """Regression guard: signals from Friday must survive Monday's portfolio cycle.

    Root cause (2026-06-29): signals_lookback_hours=24 meant fetch_signals_for_cycle
    returned empty for signals 65h old (Fri→Mon). FIX-D (_preserve_stale_signals_for_open_positions)
    never ran because there was nothing to preserve, triggering a mass-sell of all positions.
    Fix: signals_lookback_hours must be >= 96 so weekend signals enter the stale list.
    """

    def test_s4_config_signals_lookback_hours_covers_weekend(self):
        """signals_lookback_hours must be >= 96h to cover the longest market closure gap.

        A US 3-day weekend (Friday close 21:00 UTC → Tuesday open 13:30 UTC) is ~88h.
        The lookback window must exceed this gap so Friday signals reach the stale-preservation
        logic on Monday/Tuesday morning.
        """
        from src.strategies.s4.config import S4Config

        cfg = S4Config()
        assert cfg.signals_lookback_hours >= 96, (
            f"signals_lookback_hours={cfg.signals_lookback_hours} is too short to cover "
            f"a weekend gap (need >= 96h). Weekend signals aged ~65-88h are invisible "
            f"to fetch_signals_for_cycle, causing FIX-D preservation to never run → mass-sell."
        )

    def test_weekend_stale_positive_signal_preserved_for_open_position(self):
        """A 65h-old positive signal (Friday→Monday gap) is preserved when the symbol has an open position."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        friday_signal = _make_signal("TSLA", age_hours=65.0, score=0.7)
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=[friday_signal],
            open_symbols={"TSLA"},
        )

        assert friday_signal in result, (
            "65h-old positive signal for an open position must be preserved — "
            "signal expiry over the weekend is not a counter-signal."
        )

    def test_weekend_stale_negative_signal_not_preserved(self):
        """A stale negative signal (score < 0) must NOT be preserved — it IS a counter-signal."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        bearish_signal = _make_signal("TSLA", age_hours=65.0, score=-0.3)
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=[bearish_signal],
            open_symbols={"TSLA"},
        )

        assert bearish_signal not in result, (
            "Stale negative signal must NOT be preserved — negative score means bearish, "
            "which IS a reason to exit the position."
        )

    def test_weekend_stale_signal_not_preserved_when_fresh_counter_signal_exists(self):
        """A stale bullish signal must NOT be preserved when a fresh counter-signal (same symbol) exists."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        stale_bullish = _make_signal("TSLA", age_hours=65.0, score=0.7)
        fresh_bearish = _make_signal("TSLA", age_hours=1.0, score=-0.4)

        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[fresh_bearish],
            stale_signals=[stale_bullish],
            open_symbols={"TSLA"},
        )

        assert stale_bullish not in result, (
            "When a fresh signal already exists for the symbol, the stale one must NOT be "
            "re-added — the fresh signal takes precedence."
        )
        assert fresh_bearish in result, "Fresh counter-signal must remain in the result."

    def test_weekend_stale_signal_not_preserved_for_symbol_without_open_position(self):
        """A stale signal for a symbol without an open position must NOT be preserved."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        stale_signal = _make_signal("NVDA", age_hours=65.0, score=0.9)
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=[stale_signal],
            open_symbols={"TSLA"},  # NVDA not in open positions
        )

        assert stale_signal not in result, (
            "Stale signal for a symbol without an open position must NOT be preserved — "
            "no existing position to protect."
        )

    def test_weekend_mixed_portfolio_preserves_open_positions_only(self):
        """Realistic scenario: 4 open positions over weekend, only open ones preserved."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        tsla = _make_signal("TSLA", 65.0, score=0.8)   # open, bullish → preserve
        tsm  = _make_signal("TSM",  65.0, score=0.6)   # open, bullish → preserve
        avgo = _make_signal("AVGO", 65.0, score=0.5)   # open, bullish → preserve
        nvda = _make_signal("NVDA", 65.0, score=-0.1)  # open, but score<=0 → do NOT preserve

        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=[tsla, tsm, avgo, nvda],
            open_symbols={"TSLA", "TSM", "AVGO", "NVDA"},
        )

        assert tsla in result, "TSLA bullish stale signal must be preserved"
        assert tsm  in result, "TSM bullish stale signal must be preserved"
        assert avgo in result, "AVGO bullish stale signal must be preserved"
        assert nvda not in result, "NVDA score<=0 — must NOT be preserved even with open position"
        assert len(result) == 3
