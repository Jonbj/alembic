"""Timeline point-in-time e metriche intraday del dossier alpha-miss (#277)."""

from datetime import datetime, timezone

import pytest

from src.analysis.dossier.timeline import build_timeline, session_summary


UTC = timezone.utc


def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 12, hour, minute, tzinfo=UTC)


def _bar(hour: int, minute: int, open_: float, high: float, low: float, close: float):
    return {
        "timestamp": _ts(hour, minute),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }


def _daily():
    return {
        "open": 105.0,
        "high": 112.0,
        "low": 103.0,
        "close": 110.0,
        "close_prec": 100.0,
    }


def test_primo_prezzo_successivo_non_usa_la_barra_in_corso():
    """Alle 14:02 la barra 14:00 contiene futuro: il primo open PIT e' 14:05."""
    events = [{
        "symbol": "AAA",
        "signal_id": 7,
        "news_log_id": 3,
        "score": 0.6,
        "fallback": False,
        "published_at": _ts(14, 2),
        "first_seen_at": None,
        "ingested_at": None,
        "scored_at": _ts(14, 6),
        "eligible_cycle_at": None,
        "order_submitted_at": None,
        "filled_at": None,
        "fill_price": None,
    }]
    bars = {"AAA": [
        _bar(14, 0, 101.0, 106.0, 100.0, 105.0),
        _bar(14, 5, 106.0, 108.0, 105.0, 107.0),
        _bar(14, 10, 108.0, 111.0, 107.0, 110.0),
    ]}

    row = build_timeline(events, {"AAA"}, bars, {"AAA": _daily()}, _ts(23, 59))[0]

    published = row["stages"]["published_at"]
    assert published["bar_timestamp"] == "2026-08-12T14:05:00+00:00"
    assert published["price"] == 106.0
    assert published["price_source"] == "alpaca_sip_5min.open"


def test_quote_gap_intraday_e_mfe_mae_sono_deterministiche():
    events = [{
        "symbol": "AAA",
        "signal_id": 7,
        "news_log_id": 3,
        "score": 0.6,
        "fallback": False,
        "published_at": _ts(14, 5),
        "first_seen_at": None,
        "ingested_at": None,
        "scored_at": None,
        "eligible_cycle_at": None,
        "order_submitted_at": None,
        "filled_at": None,
        "fill_price": None,
    }]
    bars = {"AAA": [
        _bar(14, 5, 106.0, 108.0, 104.0, 107.0),
        _bar(14, 10, 107.0, 112.0, 103.0, 110.0),
    ]}

    row = build_timeline(events, {"AAA"}, bars, {"AAA": _daily()}, _ts(23, 59))[0]
    stage = row["stages"]["published_at"]

    assert row["movimento"]["gap_return"] == pytest.approx(0.05)
    assert row["movimento"]["intraday_return"] == pytest.approx(5 / 105)
    assert stage["quota_movimento_totale"] == pytest.approx(0.6)
    assert stage["quota_movimento_intraday"] == pytest.approx(0.2)
    assert stage["mfe"] == pytest.approx(112 / 106 - 1)
    assert stage["mae"] == pytest.approx(103 / 106 - 1)


def test_cutoff_impedisce_di_leggere_barre_e_stadi_futuri():
    events = [{
        "symbol": "AAA",
        "signal_id": 7,
        "news_log_id": None,
        "score": 0.2,
        "fallback": True,
        "published_at": _ts(14, 2),
        "first_seen_at": None,
        "ingested_at": None,
        "scored_at": _ts(14, 10),
        "eligible_cycle_at": None,
        "order_submitted_at": None,
        "filled_at": None,
        "fill_price": None,
    }]
    bars = {"AAA": [
        _bar(14, 0, 101.0, 102.0, 100.0, 101.0),
        _bar(14, 5, 103.0, 104.0, 102.0, 103.0),
    ]}

    row = build_timeline(events, {"AAA"}, bars, {"AAA": _daily()}, _ts(14, 4))[0]

    assert row["stages"]["published_at"]["price"] is None
    assert row["stages"]["published_at"]["missing_reason"] == "no_bar_before_cutoff"
    assert row["stages"]["scored_at"]["missing_reason"] == "stage_after_cutoff"


def test_missingness_esplicita_e_stub_per_mover_senza_segnale():
    rows = build_timeline([], {"AAA"}, {"AAA": []}, {"AAA": _daily()}, _ts(23, 59))

    assert len(rows) == 1
    assert rows[0]["kind"] == "mover_without_signal"
    assert rows[0]["stages"]["published_at"]["timestamp"] is None
    assert rows[0]["stages"]["published_at"]["missing_reason"] == "timestamp_not_recorded"
    assert set(rows[0]["stages"]) == {
        "published_at",
        "first_seen_at",
        "ingested_at",
        "scored_at",
        "eligible_cycle_at",
        "order_submitted_at",
        "filled_at",
    }


def test_fill_espone_prezzo_reale_senza_sostituire_il_primo_bar_successivo():
    events = [{
        "symbol": "AAA",
        "signal_id": 7,
        "news_log_id": 3,
        "score": 0.6,
        "fallback": False,
        "published_at": None,
        "first_seen_at": None,
        "ingested_at": None,
        "scored_at": None,
        "eligible_cycle_at": None,
        "order_submitted_at": None,
        "filled_at": _ts(14, 2),
        "fill_price": 105.75,
    }]
    bars = {"AAA": [_bar(14, 5, 106.0, 108.0, 105.0, 107.0)]}

    row = build_timeline(events, set(), bars, {"AAA": _daily()}, _ts(23, 59))[0]
    fill = row["stages"]["filled_at"]

    assert fill["price"] == 106.0
    assert fill["actual_price"] == 105.75
    assert fill["actual_price_source"] == "alpaca_order.filled_avg_price"


def test_session_summary_distingue_premarket_regular_e_afterhours():
    bars = [
        _bar(11, 0, 99.0, 100.0, 98.0, 100.0),   # 07:00 New York
        _bar(14, 0, 105.0, 106.0, 104.0, 106.0),  # 10:00 New York
        _bar(21, 0, 110.0, 112.0, 109.0, 111.0),  # 17:00 New York
    ]

    out = session_summary(bars)

    assert out["premarket"]["available"] is True
    assert out["regular"]["available"] is True
    assert out["afterhours"]["available"] is True
    assert out["premarket"]["bars"] == 1
    assert out["afterhours"]["return"] == pytest.approx(111 / 110 - 1)
