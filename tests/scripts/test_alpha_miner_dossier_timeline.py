"""Wiring del dossier alpha-miss verso timeline DB, barre SIP e ordini (#277)."""

from datetime import date, datetime, timezone
from unittest.mock import patch

import scripts.alpha_miner_dossier as dossier


UTC = timezone.utc


def _fake_psql(query):
    if "FROM news_log" in query:
        return [["AAA", "1"]]
    if "FROM sentiment_signals" in query:
        return [["AAA", "14:10", "0.60", "f"]]
    return []


def test_dossier_espone_schema_provenienza_e_timeline_end_to_end():
    daily = {
        "AAA": {
            "open": 105.0,
            "high": 112.0,
            "low": 103.0,
            "close": 110.0,
            "close_prec": 100.0,
        }
    }
    intraday = {"AAA": [{
        "timestamp": datetime(2026, 8, 12, 14, 20, tzinfo=UTC),
        "open": 106.0,
        "high": 112.0,
        "low": 104.0,
        "close": 110.0,
    }]}
    events = [{
        "symbol": "AAA",
        "signal_id": 7,
        "news_log_id": 3,
        "score": 0.6,
        "fallback": False,
        "published_at": datetime(2026, 8, 12, 14, 2, tzinfo=UTC),
        "first_seen_at": datetime(2026, 8, 12, 14, 4, tzinfo=UTC),
        "ingested_at": datetime(2026, 8, 12, 14, 5, tzinfo=UTC),
        "scored_at": datetime(2026, 8, 12, 14, 10, tzinfo=UTC),
        "eligible_cycle_at": datetime(2026, 8, 12, 14, 15, tzinfo=UTC),
        "order_id": "order-1",
        "trade_id": 9,
    }]
    orders = {"order-1": {
        "submitted_at": datetime(2026, 8, 12, 14, 15, 2, tzinfo=UTC),
        "filled_at": datetime(2026, 8, 12, 14, 15, 3, tzinfo=UTC),
        "filled_avg_price": 105.75,
        "lookup_error": None,
    }}
    cutoff = datetime(2026, 8, 12, 23, 59, tzinfo=UTC)

    with (
        patch.object(dossier, "_psql", side_effect=_fake_psql),
        patch.object(dossier, "_barre", return_value=daily),
        patch.object(dossier, "_soglia_gate_s4", return_value=0.30),
        patch.object(dossier, "_timeline_eventi", return_value=events, create=True),
        patch.object(
            dossier, "_barre_intraday", return_value=(intraday, cutoff), create=True
        ),
        patch.object(dossier, "_dettagli_ordini", return_value=orders, create=True),
    ):
        payload = dossier.costruisci_dossier(date(2026, 8, 12), ["AAA"])

    assert payload["schema_version"] == "2.0"
    assert payload["provenienza_dati"]["timeline"]["first_seen_at"] == (
        "news_log.raw_ingested_at"
    )
    assert payload["provenienza_dati"]["timeline"]["ingested_at"] == (
        "news_log.fetched_at"
    )
    assert payload["provenienza_dati"]["intraday"]["timeframe"] == "5Min"

    row = payload["timeline"][0]
    assert row["signal_id"] == 7
    assert row["stages"]["eligible_cycle_at"]["timestamp"].endswith("14:15:00+00:00")
    assert row["stages"]["order_submitted_at"]["timestamp"].endswith("14:15:02+00:00")
    assert row["stages"]["filled_at"]["actual_price"] == 105.75
