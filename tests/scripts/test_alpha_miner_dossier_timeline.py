"""Wiring del dossier alpha-miss verso timeline DB, barre SIP e ordini (#277)."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import scripts.alpha_miner_dossier as dossier


UTC = timezone.utc


def _fake_psql(query):
    if "article_coverage_279" in query:
        return []
    # #244: la query dei segnali fa join+sottoquery su news_log, quindi va
    # riconosciuta PRIMA del conteggio news, altrimenti il match e' ambiguo.
    if "FROM sentiment_signals" in query:
        return [["AAA", "14:10", "0.60", "f", "org_lookup", "AAA beats on revenue", "1"]]
    if "FROM news_log" in query:
        return [["AAA", "1"]]
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

    assert payload["schema_version"] == "2.7"
    assert payload["provenienza_dati"]["timeline"]["first_seen_at"] == (
        "news_log.raw_ingested_at"
    )
    assert payload["provenienza_dati"]["timeline"]["ingested_at"] == (
        "news_log.fetched_at"
    )
    assert "signed" in payload["provenienza_dati"]["timeline"]["latenze_secondi"]
    assert payload["provenienza_dati"]["intraday"]["timeframe"] == "5Min"

    row = payload["timeline"][0]
    assert row["signal_id"] == 7
    assert row["stages"]["eligible_cycle_at"]["timestamp"].endswith("14:15:00+00:00")
    assert row["stages"]["order_submitted_at"]["timestamp"].endswith("14:15:02+00:00")
    assert row["stages"]["filled_at"]["actual_price"] == 105.75
    assert row["latenze_secondi"]["scored_to_eligible_cycle"] == 300.0
    assert row["latenze_secondi"]["scored_to_filled"] == 303.0


def test_mapping_sql_usa_timestamp_persistiti_e_primo_ordine_separato():
    db_row = [[
        "7", "AAA", "3", "0.6", "f",
        "2026-08-12 14:02:00+00", "2026-08-12 14:04:00+00",
        "2026-08-12 14:05:00+00", "2026-08-12 14:10:00+00",
        "11", "2026-08-12 14:15:00+00", "order-1", "9",
    ]]

    with patch.object(dossier, "_psql", return_value=db_row) as psql:
        event = dossier._timeline_eventi(date(2026, 8, 12))[0]

    query = psql.call_args.args[0]
    assert "nl.raw_ingested_at" in query
    assert "tick_time >= ss.generated_at" in query
    assert "order_id IS NOT NULL" in query
    assert event["first_seen_at"] == datetime(2026, 8, 12, 14, 4, tzinfo=UTC)
    assert event["eligible_cycle_at"] == datetime(2026, 8, 12, 14, 15, tzinfo=UTC)
    assert event["order_id"] == "order-1"


def test_acquisizione_intraday_richiede_sip_5min_e_include_ore_estese():
    index = pd.MultiIndex.from_tuples(
        [("AAA", datetime(2026, 8, 12, 11, 0, tzinfo=UTC))],
        names=["symbol", "timestamp"],
    )
    frame = pd.DataFrame(
        [{"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.5}],
        index=index,
    )
    response = SimpleNamespace(df=frame)

    with (
        patch.dict(
            "os.environ", {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
        ),
        patch("alpaca.data.historical.StockHistoricalDataClient") as client_cls,
    ):
        client_cls.return_value.get_stock_bars.return_value = response
        bars, cutoff = dossier._barre_intraday(
            ["AAA"],
            date(2026, 8, 12),
            datetime(2026, 8, 11, 15, 2, tzinfo=UTC),
        )

    request = client_cls.return_value.get_stock_bars.call_args.args[0]
    assert request.timeframe.amount == 5
    assert request.feed.value == "sip"
    # alpaca-py normalizza i datetime request in UTC naive prima del trasporto.
    assert request.start == datetime(2026, 8, 11, 15, 2)
    assert cutoff == datetime(2026, 8, 13, 0, 0, tzinfo=UTC)  # 20:00 NY
    assert bars["AAA"][0]["open"] == 99.0


def test_dettagli_ordini_usano_timestamp_e_fill_reali_del_broker():
    order = SimpleNamespace(
        submitted_at=datetime(2026, 8, 12, 14, 15, 2, tzinfo=UTC),
        filled_at=datetime(2026, 8, 12, 14, 15, 3, tzinfo=UTC),
        filled_avg_price="105.75",
        filled_qty="2.5",
    )
    fake_config = SimpleNamespace(
        ALPACA_API_KEY="key", ALPACA_SECRET_KEY="secret", ALPACA_PAPER_MODE=True
    )

    with (
        patch("src.config.config", fake_config),
        patch("alpaca.trading.client.TradingClient") as client_cls,
    ):
        client_cls.return_value.get_order_by_id.return_value = order
        out = dossier._dettagli_ordini(["order-1"])

    assert out["order-1"]["submitted_at"] == order.submitted_at
    assert out["order-1"]["filled_at"] == order.filled_at
    assert out["order-1"]["filled_avg_price"] == 105.75
    assert out["order-1"]["filled_qty"] == 2.5
    client_cls.assert_called_once_with("key", "secret", paper=True)


def test_errore_lookup_ordine_resta_missingness_esplicita():
    fake_config = SimpleNamespace(
        ALPACA_API_KEY="key", ALPACA_SECRET_KEY="secret", ALPACA_PAPER_MODE=True
    )
    with (
        patch("src.config.config", fake_config),
        patch("alpaca.trading.client.TradingClient") as client_cls,
    ):
        client_cls.return_value.get_order_by_id.side_effect = RuntimeError("not found")
        out = dossier._dettagli_ordini(["order-404"])

    assert out["order-404"]["filled_at"] is None
    assert out["order-404"]["lookup_error"] == "RuntimeError: not found"
