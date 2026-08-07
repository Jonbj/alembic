"""Day-2 execution fixes — signal expiry guard + constraint block logging.

Covers two fixes diagnosed from controlled-paper Day-2 run (2026-06-24):

FIX-D (signal expiry guard): AMD BUY signal generated at 15:16 UTC expired at
  19:16 UTC (max_signal_age_hours=4). At 19:22 UTC the portfolio saw weight=0
  for AMD (stale signal dropped) → portfolio_sell, triggering a 90-min roundtrip
  loss. Root cause: signal expiry ≠ counter-signal. A position should only close
  on a fresh negative signal or stop-loss breach, not because no new news arrived.
  Fix: preserve positive stale signals for open positions when no counter-signal exists.

FIX-E (constraint block log): when ≥1 signals pass the feedback gate but all are
  eliminated by portfolio constraints (e.g., only 1 symbol → 100% weight → violates
  max_single_asset_pct=10%), the cycle logs "0 final orders" with no explanation.
  Fix: emit a CONSTRAINT_BLOCK warning that names the fired constraints and the
  minimum symbol count needed for diversification.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.models.signals import SentimentResult


# ─────────────────────────── helpers ───────────────────────────

def _make_signal(symbol: str, score: float, age_hours: float = 5.0) -> SentimentResult:
    """Return a SentimentResult with generated_at set to ``age_hours`` ago."""
    return SentimentResult(
        symbol=symbol,
        score=score,
        confidence=0.8,
        reasoning="test",
        model_id="test-model",
        generated_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
    )


def _make_cycle_result(
    orders_before: int,
    final_orders: list,
    constraints_fired: list | None = None,
):
    return SimpleNamespace(
        orders_before_constraints=orders_before,
        orders_after_constraints=len(final_orders),
        final_orders=final_orders,
        constraints_fired=constraints_fired or [],
        strategies_run=[],
        symbol_strategies={},
        orders_per_strategy={},
    )


# ─────────────────── FIX-D: stale signal preservation ───────────────────────


class TestPreserveStaleSignalsForOpenPositions:
    """_preserve_stale_signals_for_open_positions() unit tests."""

    def test_preserves_positive_stale_signal_when_open_position_no_counter(self):
        """Core case: stale positive signal + open position + no counter → preserved."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        stale = [_make_signal("AMD", score=0.45)]
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=stale,
            open_symbols={"AMD"},
        )
        syms = [s.symbol for s in result]
        assert "AMD" in syms, (
            "AMD stale signal should be preserved when open position exists and no counter-signal"
        )

    def test_does_not_preserve_when_no_open_position(self):
        """No open position → stale signal is discarded as before."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        stale = [_make_signal("AMD", score=0.45)]
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=stale,
            open_symbols=set(),  # AMD not in open positions
        )
        syms = [s.symbol for s in result]
        assert "AMD" not in syms, (
            "AMD stale signal must not be preserved when there is no open position for it"
        )

    def test_does_not_preserve_when_fresh_counter_signal_exists(self):
        """Fresh negative signal for same symbol → use fresh, don't re-add stale."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        fresh = [_make_signal("AMD", score=-0.30, age_hours=1.0)]  # counter-signal
        stale = [_make_signal("AMD", score=0.45, age_hours=5.0)]
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=fresh,
            stale_signals=stale,
            open_symbols={"AMD"},
        )
        # Should have exactly one AMD entry (the fresh counter-signal)
        amd_signals = [s for s in result if s.symbol == "AMD"]
        assert len(amd_signals) == 1
        assert amd_signals[0].score == pytest.approx(-0.30), (
            "Only the fresh counter-signal should remain; stale positive must not be re-added"
        )

    def test_does_not_preserve_negative_stale_signal(self):
        """Bearish stale signal (score < 0) is never preserved regardless of open position."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        stale = [_make_signal("AMD", score=-0.40)]
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=stale,
            open_symbols={"AMD"},
        )
        syms = [s.symbol for s in result]
        assert "AMD" not in syms, (
            "Bearish stale signal must not be preserved (no long position to protect)"
        )

    def test_does_not_preserve_zero_score_stale_signal(self):
        """Zero-score stale signal is not preserved (neutral ≠ bullish)."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        stale = [_make_signal("AMD", score=0.0)]
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=stale,
            open_symbols={"AMD"},
        )
        syms = [s.symbol for s in result]
        assert "AMD" not in syms

    def test_fresh_signals_always_included(self):
        """Fresh signals pass through unchanged regardless of stale logic."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        fresh = [
            _make_signal("NVDA", score=0.60, age_hours=1.0),
            _make_signal("TSM", score=0.55, age_hours=2.0),
        ]
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=fresh,
            stale_signals=[],
            open_symbols=set(),
        )
        assert len(result) == 2
        assert {s.symbol for s in result} == {"NVDA", "TSM"}

    def test_multiple_stale_only_open_position_ones_preserved(self):
        """Multiple stale signals: only those with open positions are preserved."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        stale = [
            _make_signal("AMD", score=0.50),   # open position → preserve
            _make_signal("CAT", score=0.40),   # no open position → discard
            _make_signal("TSM", score=0.35),   # open position → preserve
        ]
        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=stale,
            open_symbols={"AMD", "TSM"},
        )
        syms = {s.symbol for s in result}
        assert "AMD" in syms
        assert "TSM" in syms
        assert "CAT" not in syms

    def test_empty_inputs_returns_empty(self):
        """Empty inputs → empty output."""
        from src.workers.portfolio_scheduler import _preserve_stale_signals_for_open_positions

        result = _preserve_stale_signals_for_open_positions(
            fresh_signals=[],
            stale_signals=[],
            open_symbols=set(),
        )
        assert result == []


# ─────────────────── FIX-E: constraint block logging ────────────────────────


class TestLogConstraintBlockIfNeeded:
    """_log_constraint_block_if_needed() unit tests."""

    def test_logs_warning_when_all_orders_eliminated_by_constraints(self, caplog):
        """Core case: strategy produced orders but constraints killed them all."""
        from src.workers.portfolio_scheduler import _log_constraint_block_if_needed

        result = _make_cycle_result(
            orders_before=1,
            final_orders=[],
            constraints_fired=["SINGLE_ASSET_CAP"],
        )
        risk_cfg = {"max_single_asset_pct": 0.10}

        with caplog.at_level(logging.WARNING, logger="src.workers.portfolio_scheduler"):
            _log_constraint_block_if_needed(result, risk_cfg)

        assert any("CONSTRAINT_BLOCK" in r.message for r in caplog.records), (
            "Expected CONSTRAINT_BLOCK warning when all pre-constraint orders are eliminated"
        )

    def test_warning_names_fired_constraints(self, caplog):
        """Log message must include the name of the fired constraint."""
        from src.workers.portfolio_scheduler import _log_constraint_block_if_needed

        result = _make_cycle_result(
            orders_before=2,
            final_orders=[],
            constraints_fired=["SINGLE_ASSET_CAP", "MAX_EXPOSURE"],
        )
        with caplog.at_level(logging.WARNING, logger="src.workers.portfolio_scheduler"):
            _log_constraint_block_if_needed(result, {"max_single_asset_pct": 0.10})

        full = " ".join(r.message for r in caplog.records)
        assert "SINGLE_ASSET_CAP" in full or "MAX_EXPOSURE" in full

    def test_warning_mentions_minimum_symbol_count(self, caplog):
        """Log must hint at the minimum number of symbols required for diversification."""
        from src.workers.portfolio_scheduler import _log_constraint_block_if_needed

        result = _make_cycle_result(orders_before=1, final_orders=[])
        risk_cfg = {"max_single_asset_pct": 0.10}  # needs ≥10 symbols

        with caplog.at_level(logging.WARNING, logger="src.workers.portfolio_scheduler"):
            _log_constraint_block_if_needed(result, risk_cfg)

        full = " ".join(r.message for r in caplog.records)
        assert "10" in full, (
            "Log should mention 10 (= 1 / 0.10 max_single_asset_pct) as minimum symbol count"
        )

    def test_no_log_when_no_orders_before_constraints(self, caplog):
        """If strategy produced 0 orders, constraint block is irrelevant — no log."""
        from src.workers.portfolio_scheduler import _log_constraint_block_if_needed

        result = _make_cycle_result(orders_before=0, final_orders=[])
        with caplog.at_level(logging.WARNING, logger="src.workers.portfolio_scheduler"):
            _log_constraint_block_if_needed(result, {"max_single_asset_pct": 0.10})

        assert not any("CONSTRAINT_BLOCK" in r.message for r in caplog.records), (
            "CONSTRAINT_BLOCK must not fire when strategy itself produced no orders"
        )

    def test_no_log_when_some_orders_survive_constraints(self, caplog):
        """If at least one order survived constraints, do not log CONSTRAINT_BLOCK."""
        from src.workers.portfolio_scheduler import _log_constraint_block_if_needed

        mock_order = MagicMock()
        result = _make_cycle_result(orders_before=3, final_orders=[mock_order])
        with caplog.at_level(logging.WARNING, logger="src.workers.portfolio_scheduler"):
            _log_constraint_block_if_needed(result, {"max_single_asset_pct": 0.10})

        assert not any("CONSTRAINT_BLOCK" in r.message for r in caplog.records)


# ─────────── FIX-F: informative reason for stale-expiry SELL orders ─────────


class TestReasonForZeroWeightSell:
    """_reason_for_zero_weight_sell() unit tests.

    FIX-F (Day-3): "Portfolio rebalance: weight 0.0%" logged for CAT/TSM sells
    gave no indication of *why* the weight dropped to zero. Root cause was S4
    signal expiry overnight (20.3h > 4h max_age). The helper generates a reason
    string that surfaces the expiry fact so the decision log is actionable.
    """

    def test_expired_signal_includes_age_in_reason(self):
        """Core case: stale signal DISCARDED for age → reason mentions expiry and age.

        #184: "expired" is now claimed only when the cycle says it discarded the
        signal for age (disposition STALE_DROPPED), never inferred from the clock.
        """
        from src.portfolio.exit_classification import STALE_DROPPED
        from src.workers.portfolio_scheduler import _reason_for_zero_weight_sell

        gen_at = datetime.now(timezone.utc) - timedelta(hours=20.3)
        last_signal = {"generated_at": gen_at, "score": 0.60}
        reason = _reason_for_zero_weight_sell(
            "CAT", last_signal, max_age_hours=4, disposition=STALE_DROPPED
        )

        assert "expired" in reason.lower() or "expir" in reason.lower(), (
            "Reason must mention signal expiry when signal is older than max_age_hours"
        )
        assert "20" in reason, "Reason must include approximate age (hours)"

    def test_expired_signal_mentions_max_age(self):
        """Reason must show both actual age and the configured max_age threshold."""
        from src.workers.portfolio_scheduler import _reason_for_zero_weight_sell

        gen_at = datetime.now(timezone.utc) - timedelta(hours=20.3)
        reason = _reason_for_zero_weight_sell(
            "CAT", {"generated_at": gen_at, "score": 0.60}, max_age_hours=4
        )
        assert "4" in reason, "Reason must include max_age_hours threshold (4)"

    def test_no_signal_gives_informative_fallback(self):
        """When no DB signal exists for the symbol, reason must not be generic 'weight 0.0%'."""
        from src.workers.portfolio_scheduler import _reason_for_zero_weight_sell

        reason = _reason_for_zero_weight_sell("XYZ", last_signal=None, max_age_hours=4)
        assert "no" in reason.lower() or "unknown" in reason.lower(), (
            "When no signal found, reason must say so explicitly (not just 'weight 0.0%')"
        )

    def test_fresh_signal_zero_weight_shows_score(self):
        """If signal is fresh but weight still 0 (e.g. score below min_score), show the score."""
        from src.workers.portfolio_scheduler import _reason_for_zero_weight_sell

        gen_at = datetime.now(timezone.utc) - timedelta(hours=1.0)  # fresh
        reason = _reason_for_zero_weight_sell(
            "AAPL", {"generated_at": gen_at, "score": 0.05}, max_age_hours=4
        )
        # Should not say "expired" (signal is fresh)
        assert "expired" not in reason.lower(), (
            "Must not claim signal is expired when age < max_age_hours"
        )
        # Should include the score
        assert "0.05" in reason or "score" in reason.lower(), (
            "Reason should include the signal score when signal is fresh"
        )

    def test_reason_does_not_say_generic_portfolio_rebalance_for_expired(self):
        """Expired signal must not produce the old generic reason."""
        from src.workers.portfolio_scheduler import _reason_for_zero_weight_sell

        gen_at = datetime.now(timezone.utc) - timedelta(hours=20)
        reason = _reason_for_zero_weight_sell(
            "CAT", {"generated_at": gen_at, "score": 0.60}, max_age_hours=4
        )
        assert reason != "Portfolio rebalance: weight 0.0%.", (
            "Expired signal must produce a more specific reason than the old generic text"
        )


# ─── #60: structured exit_mechanism classification for weight-0 SELLs ──────


class TestClassifyZeroWeightExit:
    """_classify_zero_weight_exit() — structured tag alongside the free-text reason.

    #60: buckets so #61's anti-whipsaw measurement doesn't need to parse free text.
    #184: the bucket comes from the disposition the cycle recorded for the signal,
    so these tests pass one. The age-only variants are gone: they encoded the very
    inference that mislabelled the 2026-08-05 exits — see
    tests/workers/test_exit_mechanism_observed.py.
    """

    def test_no_signal_returns_no_signal_mechanism(self):
        from src.workers.portfolio_scheduler import _classify_zero_weight_exit

        mechanism = _classify_zero_weight_exit(None, max_age_hours=4)

        assert mechanism == "no_signal"

    def test_stale_signal_returns_expired_mechanism(self):
        from src.portfolio.exit_classification import STALE_DROPPED
        from src.workers.portfolio_scheduler import _classify_zero_weight_exit

        gen_at = datetime.now(timezone.utc) - timedelta(hours=20.3)
        mechanism = _classify_zero_weight_exit(
            {"generated_at": gen_at, "score": 0.60}, max_age_hours=4,
            disposition=STALE_DROPPED,
        )

        assert mechanism == "expired"

    def test_fresh_weak_signal_returns_whipsaw_mechanism(self):
        from src.portfolio.exit_classification import FRESH
        from src.workers.portfolio_scheduler import _classify_zero_weight_exit

        gen_at = datetime.now(timezone.utc) - timedelta(hours=1.0)
        mechanism = _classify_zero_weight_exit(
            {"generated_at": gen_at, "score": 0.05}, max_age_hours=4, disposition=FRESH
        )

        assert mechanism == "whipsaw"

    def test_age_alone_never_decides_the_mechanism(self):
        """#184: the max_age boundary lives in _filter_stale_signals, not here.

        Same 20h-old signal, two dispositions, two labels — the clock contributes
        nothing.
        """
        from src.portfolio.exit_classification import FRESH, STALE_DROPPED
        from src.workers.portfolio_scheduler import _classify_zero_weight_exit

        old = {"generated_at": datetime.now(timezone.utc) - timedelta(hours=20.3),
               "score": 0.10}

        assert _classify_zero_weight_exit(old, 4, disposition=STALE_DROPPED) == "expired"
        assert _classify_zero_weight_exit(old, 4, disposition=FRESH) == "whipsaw"


class TestReasonForZeroWeightSellTags:
    """#60: each branch of _reason_for_zero_weight_sell carries a structured tag prefix."""

    def test_no_signal_reason_tagged(self):
        from src.workers.portfolio_scheduler import _reason_for_zero_weight_sell

        reason = _reason_for_zero_weight_sell("XYZ", last_signal=None, max_age_hours=4)

        assert reason.startswith("[no_signal]")

    def test_expired_reason_tagged(self):
        from src.portfolio.exit_classification import STALE_DROPPED
        from src.workers.portfolio_scheduler import _reason_for_zero_weight_sell

        gen_at = datetime.now(timezone.utc) - timedelta(hours=20.3)
        reason = _reason_for_zero_weight_sell(
            "CAT", {"generated_at": gen_at, "score": 0.60}, max_age_hours=4,
            disposition=STALE_DROPPED,
        )

        assert reason.startswith("[expired]")

    def test_whipsaw_reason_tagged(self):
        from src.portfolio.exit_classification import FRESH
        from src.workers.portfolio_scheduler import _reason_for_zero_weight_sell

        gen_at = datetime.now(timezone.utc) - timedelta(hours=1.0)
        reason = _reason_for_zero_weight_sell(
            "AAPL", {"generated_at": gen_at, "score": 0.05}, max_age_hours=4,
            disposition=FRESH,
        )

        assert reason.startswith("[whipsaw]")


# ─── #72: origin-aware exit tag for non-S4 weight-0 SELLs ───────────────────
#
# #60's classifier (_classify_zero_weight_exit) only ever checks the S4
# sentiment-signals table, so it ALWAYS tags a non-S4-origin position
# [no_signal] — trivially true (an S1 position never had an S4 signal) but
# misleading, and it over-counts [no_signal] in #61's flip-decision
# measurement. Real incident: SBUX trades 348/360 (2026-07-17), verified S1
# momentum entries, tagged [no_signal] by the S4-only classifier.


class TestReasonForNonS4WeightDrop:
    def test_tags_s1_origin_with_s1_weight_drop(self):
        from src.workers.portfolio_scheduler import _reason_and_mechanism_for_non_s4_weight_drop

        mechanism, reason = _reason_and_mechanism_for_non_s4_weight_drop("SBUX", "S1", "0.0%")

        assert mechanism == "s1_weight_drop"
        assert reason.startswith("[s1_weight_drop]")
        assert "S1" in reason

    def test_tag_is_origin_aware_not_hardcoded_to_s1(self):
        """Generalizes to any future non-S4 strategy id, not just S1."""
        from src.workers.portfolio_scheduler import _reason_and_mechanism_for_non_s4_weight_drop

        mechanism, reason = _reason_and_mechanism_for_non_s4_weight_drop("SPY", "S2", "0.0%")

        assert mechanism == "s2_weight_drop"
        assert reason.startswith("[s2_weight_drop]")
