"""#285 — wiring delle fonti read-only nel dossier giornaliero."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import scripts.alpha_miner_dossier as dossier


UTC = timezone.utc


def _fake_psql(query):
    if "FROM sentiment_signals ss LEFT JOIN news_log" in query:
        return [["NVDA", "14:10", "0.60", "f", "source_metadata", "AI demand outlook", "2", "7"]]
    if "SELECT ticker, count(*) FROM news_log" in query:
        return [["NVDA", "1"]]
    return []


def test_dossier_24_collega_benchmark_calendario_regime_e_microstruttura():
    daily = {
        "NVDA": {
            "open": 105.0, "high": 112.0, "low": 103.0, "close": 110.0,
            "close_prec": 100.0, "volume": 2_000_000, "adv_20d": 1_000_000,
        },
        "SPY": {"open": 501.0, "high": 511.0, "low": 500.0, "close": 510.0, "close_prec": 500.0},
        "SOXX": {"open": 302.0, "high": 316.0, "low": 301.0, "close": 315.0, "close_prec": 300.0},
    }
    intraday = {"NVDA": [{
        "timestamp": datetime(2026, 8, 12, 14, 20, tzinfo=UTC),
        "open": 106.0, "high": 112.0, "low": 104.0, "close": 110.0,
        "volume": 1_000_000,
    }]}
    coverage_rows = [{
        "news_log_id": 3,
        "signal_id": 7,
        "ticker": "NVDA",
        "title": "Chipmakers rally after broad AI demand outlook",
        "body_snippet": "Chipmakers rally after broad AI demand outlook",
        "url": "https://wire.example/ai",
        "source": "wire",
        "published_at": datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        "first_seen_at": datetime(2026, 8, 12, 12, 1, tzinfo=UTC),
        "content_hash": "a" * 64,
        "extraction_method": "source_metadata",
        "score": 0.60,
        "ground_truth_relevance": "sector",
        "ground_truth_tickers": [],
        "issuer_terms": ["Nvidia", "NVDA"],
    }]
    cutoff = datetime(2026, 8, 13, 0, 0, tzinfo=UTC)
    quote = {
        "NVDA": {
            "timestamp": datetime(2026, 8, 12, 14, 22, tzinfo=UTC),
            "bid_price": 109.9,
            "ask_price": 110.1,
            "bid_size": 10,
            "ask_size": 8,
            "source": "Alpaca Market Data API / SIP quotes",
        }
    }

    with (
        patch.object(dossier, "_psql", side_effect=_fake_psql),
        patch.object(dossier, "_barre", return_value=daily) as bars_loader,
        patch.object(dossier, "_article_coverage_rows", return_value=coverage_rows),
        patch.object(dossier, "_soglia_gate_s4", return_value=0.30),
        patch.object(dossier, "_timeline_eventi", return_value=[]),
        patch.object(dossier, "_barre_intraday", return_value=(intraday, cutoff)),
        patch.object(dossier, "_dettagli_ordini", return_value={}),
        patch.object(dossier, "_sector_by_ticker", return_value={"NVDA": "semis"}),
        patch.object(dossier, "_regime_observations", return_value=[{
            "observed_at": datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
            "multiplier": 0.7,
            "source": "execution_decisions.regime_mult",
        }]),
        patch.object(dossier, "_vix_observation", return_value={
            "value": 23.4, "observed_on": "2026-08-12", "source": "FRED:VIXCLS",
        }),
        patch.object(dossier, "_corporate_calendar", return_value=[{
            "symbol": "NVDA", "event_type": "earnings",
            "event_date": "2026-08-12", "source": "FMP earnings-calendar",
        }]),
        patch.object(dossier, "_nbbo_at_cycles", return_value=quote) as nbbo_loader,
        patch.object(dossier, "_halt_events", return_value=[]),
    ):
        out = dossier.costruisci_dossier(
            date(2026, 8, 12), ["NVDA"], fetch_remote_context=True
        )

    requested_symbols = set(bars_loader.call_args.args[0])
    assert {"NVDA", "SPY", "SOXX", "XLY", "XLC", "XLI", "XLB"} <= requested_symbols
    nbbo_cycles = nbbo_loader.call_args.args[0]
    assert nbbo_cycles["NVDA"]["at"] == datetime(2026, 8, 12, 14, 22, tzinfo=UTC)
    assert nbbo_cycles["NVDA"]["source"] == dossier.ELIGIBLE_SOURCE_SEGNALE
    assert out["schema_version"] == "2.4"
    assert out["provenienza_dati"]["event_market_context"]["version"] == (
        "event_market_context_v1"
    )

    row = out["event_market_context"]["per_symbol"]["NVDA"]
    assert row["returns"]["residual_vs_spy"] == pytest.approx(0.08)
    assert row["returns"]["residual_vs_sector"] == pytest.approx(0.05)
    assert row["catalyst"]["type"] == "EARNINGS"
    assert row["regime"]["type"] == "SIDEWAYS"
    assert row["regime"]["vix"] == 23.4
    assert row["microstructure"]["bar_based"]["basis"] == "BAR_5MIN"
    assert row["microstructure"]["nbbo"]["basis"] == "NBBO"
    assert out["event_market_context"]["statistics"] == {
        "raw_opportunities": 1,
        "independent_clusters": 1,
        "counting_rule": "one independent unit per deterministic cluster",
    }


def test_barre_daily_calcolano_adv_solo_su_20_sedute_precedenti():
    timestamps = pd.bdate_range(end="2026-08-12", periods=21, tz=UTC)
    index = pd.MultiIndex.from_tuples(
        [("NVDA", timestamp.to_pydatetime()) for timestamp in timestamps],
        names=["symbol", "timestamp"],
    )
    frame = pd.DataFrame(
        [
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0 + i,
                "volume": 1_000 + i,
            }
            for i in range(21)
        ],
        index=index,
    )

    with (
        patch.dict("os.environ", {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}),
        patch("alpaca.data.historical.StockHistoricalDataClient") as client_cls,
    ):
        client_cls.return_value.get_stock_bars.return_value = SimpleNamespace(df=frame)
        out = dossier._barre(["NVDA"], date(2026, 8, 12))

    assert out["NVDA"]["volume"] == 1_020
    assert out["NVDA"]["adv_20d"] == pytest.approx(sum(range(1_000, 1_020)) / 20)
    assert out["NVDA"]["adv_20d_observations"] == 20


def test_nbbo_usa_prima_quota_sip_dopo_il_ciclo_eleggibile():
    at = datetime(2026, 8, 12, 14, 22, tzinfo=UTC)
    index = pd.MultiIndex.from_tuples(
        [("NVDA", datetime(2026, 8, 12, 14, 22, 1, tzinfo=UTC))],
        names=["symbol", "timestamp"],
    )
    frame = pd.DataFrame(
        [{"bid_price": 109.9, "ask_price": 110.1, "bid_size": 8, "ask_size": 6}],
        index=index,
    )

    with (
        patch.dict("os.environ", {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}),
        patch("alpaca.data.historical.StockHistoricalDataClient") as client_cls,
    ):
        client_cls.return_value.get_stock_quotes.return_value = SimpleNamespace(df=frame)
        out = dossier._nbbo_at_cycles(
            {"NVDA": {"at": at, "source": dossier.ELIGIBLE_SOURCE_SEGNALE}},
            datetime(2026, 8, 13, 0, 0, tzinfo=UTC),
        )

    request = client_cls.return_value.get_stock_quotes.call_args.args[0]
    assert request.feed.value == "sip"
    assert request.limit == 1
    assert request.start == at.replace(tzinfo=None)
    assert out["NVDA"]["timestamp"] == datetime(2026, 8, 12, 14, 22, 1, tzinfo=UTC)
    assert out["NVDA"]["bid_price"] == 109.9


def test_vix_storico_sceglie_ultima_osservazione_non_successiva_al_giorno():
    response = SimpleNamespace(
        text="observation_date,VIXCLS\n2026-08-10,22.1\n2026-08-11,.\n2026-08-12,23.4\n",
        raise_for_status=lambda: None,
    )
    with (
        patch.dict("os.environ", {"FRED_API_KEY": ""}),
        patch("httpx.get", return_value=response) as get,
    ):
        out = dossier._vix_observation(date(2026, 8, 12))

    assert out == {"value": 23.4, "observed_on": "2026-08-12", "source": "FRED:VIXCLS"}
    assert get.call_args.kwargs["params"]["coed"] == "2026-08-12"


def test_regime_legge_moltiplicatore_persistito_senza_interpolarlo():
    with patch.object(
        dossier,
        "_psql",
        return_value=[["2026-08-12 19:00:00+00", "0.7"]],
    ) as psql:
        out = dossier._regime_observations(date(2026, 8, 12))

    assert out[0]["multiplier"] == 0.7
    assert out[0]["source"] == "execution_decisions.regime_mult"
    assert "regime_mult IS NOT NULL" in psql.call_args.args[0]


def test_calendario_senza_credenziali_dichiara_fonti_mancanti():
    with patch.dict(
        "os.environ",
        {"FMP_API_KEY": "", "ALPACA_API_KEY": "", "ALPACA_SECRET_KEY": ""},
    ):
        out = dossier._corporate_calendar(date(2026, 8, 12), ["NVDA"])

    assert out == {
        "events": [],
        "sources_succeeded": [],
        "complete": False,
        "missingness": [
            "earnings_calendar_unavailable",
            "corporate_actions_calendar_unavailable",
        ],
    }


def test_soli_benchmark_non_mascherano_watchlist_senza_barre():
    only_benchmark = {
        "SPY": {
            "open": 500.0,
            "high": 510.0,
            "low": 499.0,
            "close": 505.0,
            "close_prec": 500.0,
        }
    }
    with (
        patch.object(dossier, "_barre", return_value=only_benchmark),
        patch.object(dossier, "_sector_by_ticker", return_value={}),
    ):
        with pytest.raises(SystemExit, match="nessuna barra per l'intera watchlist"):
            dossier.costruisci_dossier(date(2026, 8, 12), ["ZZZ"])
