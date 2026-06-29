"""Tests for _fresh_signal_protected_symbols (anti-stale-ranker-sell guard).

Root cause: when S4 CrossSectionalRanker requires min_stocks=2 positive-strength
candidates but only 1 exists (e.g. the 2nd signal passing the abs(score) gate is
negative → strength=score×confidence<0 → skipped), the ranker returns {} weights.
The orchestrator then generates a SELL for all held positions, even those whose
buy signal is still valid (fresh, above threshold, positive).
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone


def _make_signal(symbol: str, score: float, generated_at=None):
    sig = MagicMock()
    sig.symbol = symbol
    sig.score = score
    sig.generated_at = generated_at or datetime(2026, 6, 29, 16, 18, tzinfo=timezone.utc)
    return sig


def test_fresh_positive_signal_protects_symbol():
    """Simbolo con segnale fresco positivo sopra soglia → protetto da SELL."""
    from src.workers.portfolio_scheduler import _fresh_signal_protected_symbols

    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_cycle.return_value = [_make_signal("MS", 0.425)]

    result = _fresh_signal_protected_symbols({"MS"}, mock_pg, entry_threshold=0.35, max_age_hours=4)

    assert "MS" in result


def test_below_threshold_signal_does_not_protect():
    """Segnale fresco ma troppo debole (< soglia) → nessuna protezione."""
    from src.workers.portfolio_scheduler import _fresh_signal_protected_symbols

    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_cycle.return_value = [_make_signal("GS", 0.004)]

    result = _fresh_signal_protected_symbols({"GS"}, mock_pg, entry_threshold=0.35, max_age_hours=4)

    assert "GS" not in result


def test_negative_signal_does_not_protect():
    """Segnale negativo → nessuna protezione (long-only: reversione bearish = exit corretto)."""
    from src.workers.portfolio_scheduler import _fresh_signal_protected_symbols

    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_cycle.return_value = [_make_signal("MU", -0.42)]

    result = _fresh_signal_protected_symbols({"MU"}, mock_pg, entry_threshold=0.35, max_age_hours=4)

    assert "MU" not in result


def test_no_signal_in_window_does_not_protect():
    """Nessun segnale nel DB per il simbolo → nessuna protezione."""
    from src.workers.portfolio_scheduler import _fresh_signal_protected_symbols

    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_cycle.return_value = []

    result = _fresh_signal_protected_symbols({"NVDA"}, mock_pg, entry_threshold=0.35, max_age_hours=4)

    assert "NVDA" not in result


def test_empty_candidates_skips_db_call():
    """Nessun candidato → nessuna query DB (ottimizzazione early-exit)."""
    from src.workers.portfolio_scheduler import _fresh_signal_protected_symbols

    mock_pg = MagicMock()

    result = _fresh_signal_protected_symbols(set(), mock_pg, entry_threshold=0.35, max_age_hours=4)

    assert result == set()
    mock_pg.fetch_signals_for_cycle.assert_not_called()


def test_most_recent_signal_wins_when_multiple():
    """Con più segnali per lo stesso simbolo viene usato il più recente."""
    from src.workers.portfolio_scheduler import _fresh_signal_protected_symbols

    old_sig = _make_signal("AAPL", 0.8, datetime(2026, 6, 29, 14, 0, tzinfo=timezone.utc))
    new_sig = _make_signal("AAPL", 0.1, datetime(2026, 6, 29, 17, 0, tzinfo=timezone.utc))

    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_cycle.return_value = [old_sig, new_sig]

    # Il segnale più recente è 0.1 < soglia 0.35 → non protetto
    result = _fresh_signal_protected_symbols({"AAPL"}, mock_pg, entry_threshold=0.35, max_age_hours=4)

    assert "AAPL" not in result


def test_pg_error_returns_empty_fail_open():
    """Errore DB → empty set (fail-open: meglio SELL che blocco indefinito su errore)."""
    from src.workers.portfolio_scheduler import _fresh_signal_protected_symbols

    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_cycle.side_effect = Exception("DB timeout")

    result = _fresh_signal_protected_symbols({"MS"}, mock_pg, entry_threshold=0.35, max_age_hours=4)

    assert result == set()


def test_multiple_symbols_mixed_result():
    """Più simboli: solo quelli con segnale positivo >= soglia vengono protetti."""
    from src.workers.portfolio_scheduler import _fresh_signal_protected_symbols

    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_cycle.return_value = [
        _make_signal("MS", 0.425),   # protetto
        _make_signal("GS", 0.004),   # NON protetto
        _make_signal("MU", -0.418),  # NON protetto (negativo)
    ]

    result = _fresh_signal_protected_symbols({"MS", "GS", "MU"}, mock_pg, entry_threshold=0.35, max_age_hours=4)

    assert "MS" in result
    assert "GS" not in result
    assert "MU" not in result
