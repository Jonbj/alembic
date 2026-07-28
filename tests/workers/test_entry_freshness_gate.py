"""#150: the news_age_hours (published_at) entry-freshness gate must only apply to
symbols with no open position. Before this fix, the gate was applied inside the SQL
fetch itself (fetch_signals_for_cycle(..., news_age_hours=MAX_NEWS_AGE_HOURS)) — the
single query that feeds both new-entry ranking AND the decision to keep or close
already-open S4 positions. A held symbol whose only signal had gone stale on
published_at (but was still strongly positive and never contradicted) was excluded
before FIX-D (_preserve_stale_signals_for_open_positions) ever got a chance to
evaluate it, and got force-sold as "[no_signal]" (NOW, 2026-07-27 — see
docs/ALPHA_MISS_REPORT_2026-07-27.md §4).

_apply_entry_freshness_gate restores the docstring's own promise
(fetch_signals_for_cycle: "only the S4 entry path passes an explicit bound") by
applying the published_at gate in Python, after the fetch, only to symbols that are
NOT already held.
"""
from datetime import datetime, timedelta, timezone

from src.models.signals import SentimentResult

from src.workers.portfolio_scheduler import _apply_entry_freshness_gate


def _sig(symbol, published_at, score=0.5):
    return SentimentResult(
        symbol=symbol,
        score=score,
        confidence=0.8,
        reasoning="test",
        model_id="ensemble:test",
        generated_at=datetime.now(timezone.utc),
        published_at=published_at,
    )


def test_held_symbol_with_old_news_is_not_gated():
    """Core regression case: NOW-style — a held symbol's only signal has old
    published_at, but it must not be dropped by the entry-freshness gate (FIX-D
    downstream decides whether to keep it, based on generated_at/score/counter-signal)."""
    now = datetime.now(timezone.utc)
    old_news = now - timedelta(hours=69, minutes=40)  # NOW's actual gap, 2026-07-27
    signals = [_sig("NOW", published_at=old_news, score=0.81)]

    kept = _apply_entry_freshness_gate(
        signals, open_symbols={"NOW"}, news_age_hours=2.0, now_utc=now
    )

    assert [s.symbol for s in kept] == ["NOW"]


def test_non_held_symbol_with_old_news_is_still_gated():
    """A symbol with no open position keeps today's entry-freshness policy — old news
    must not qualify it as a new BUY candidate."""
    now = datetime.now(timezone.utc)
    old_news = now - timedelta(hours=3)
    signals = [_sig("PLTR", published_at=old_news, score=0.6)]

    kept = _apply_entry_freshness_gate(
        signals, open_symbols=set(), news_age_hours=2.0, now_utc=now
    )

    assert kept == []


def test_non_held_symbol_with_fresh_news_passes():
    now = datetime.now(timezone.utc)
    fresh_news = now - timedelta(minutes=30)
    signals = [_sig("PLTR", published_at=fresh_news, score=0.6)]

    kept = _apply_entry_freshness_gate(
        signals, open_symbols=set(), news_age_hours=2.0, now_utc=now
    )

    assert [s.symbol for s in kept] == ["PLTR"]


def test_legacy_signal_with_no_published_at_passes_regardless_of_held_status():
    """Matches the existing SQL semantics: published_at IS NULL always passes the
    gate (legacy rows / non-news signals), whether or not the symbol is held."""
    now = datetime.now(timezone.utc)
    signals = [_sig("XYZ", published_at=None, score=0.4)]

    kept = _apply_entry_freshness_gate(
        signals, open_symbols=set(), news_age_hours=2.0, now_utc=now
    )

    assert [s.symbol for s in kept] == ["XYZ"]


def test_news_age_hours_none_disables_the_gate_entirely():
    """news_age_hours=None means no event-time gate at all — matches
    fetch_signals_for_cycle's own default/no-bound semantics."""
    now = datetime.now(timezone.utc)
    old_news = now - timedelta(hours=100)
    signals = [_sig("PLTR", published_at=old_news, score=0.6)]

    kept = _apply_entry_freshness_gate(
        signals, open_symbols=set(), news_age_hours=None, now_utc=now
    )

    assert [s.symbol for s in kept] == ["PLTR"]


def test_mixed_batch_only_gates_non_held_symbols():
    now = datetime.now(timezone.utc)
    old_news = now - timedelta(hours=10)
    fresh_news = now - timedelta(minutes=10)
    signals = [
        _sig("NOW", published_at=old_news, score=0.81),   # held, old news → kept
        _sig("PLTR", published_at=old_news, score=0.6),   # not held, old news → dropped
        _sig("CRM", published_at=fresh_news, score=0.5),  # not held, fresh news → kept
    ]

    kept = _apply_entry_freshness_gate(
        signals, open_symbols={"NOW"}, news_age_hours=2.0, now_utc=now
    )

    assert {s.symbol for s in kept} == {"NOW", "CRM"}
