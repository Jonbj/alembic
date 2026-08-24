"""#285 — contesto evento, regime, tema e microstruttura del dossier."""

from datetime import datetime, timezone

import pytest

from src.analysis.dossier.event_context import (
    CATALYST_TYPES,
    REGIME_TYPES,
    THEME_TYPES,
    build_event_market_context,
)


UTC = timezone.utc


def _bar(close_prec, close, *, volume=None, adv_20d=None):
    return {
        "open": close_prec,
        "high": max(close_prec, close),
        "low": min(close_prec, close),
        "close_prec": close_prec,
        "close": close,
        "volume": volume,
        "adv_20d": adv_20d,
    }


def _build(**overrides):
    inputs = {
        "data": "2026-08-12",
        "candidates": [{"symbol": "NVDA", "return": 0.10}],
        "daily_bars": {
            "NVDA": _bar(100.0, 110.0, volume=2_000_000, adv_20d=1_000_000),
            "SPY": _bar(500.0, 510.0),
            "SOXX": _bar(300.0, 315.0),
        },
        "sector_by_ticker": {"NVDA": "semis"},
        "articles": [{
            "ticker": "NVDA",
            "title": "Chipmakers rally after broad AI demand outlook",
            "canonical_article_id": "content:macro-ai",
            "relevance": "SECTOR_MACRO",
        }],
        "corporate_events": [],
        "regime_observations": [{
            "observed_at": datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
            "multiplier": 0.7,
            "source": "execution_decisions.regime_mult",
        }],
        "vix_observation": {
            "value": 23.4,
            "observed_on": "2026-08-12",
            "source": "FRED:VIXCLS",
        },
        "intraday_bars": {"NVDA": [
            {"timestamp": datetime(2026, 8, 12, 14, 30, tzinfo=UTC), "volume": 600_000},
            {"timestamp": datetime(2026, 8, 12, 14, 35, tzinfo=UTC), "volume": 400_000},
        ]},
        "nbbo_quotes": {"NVDA": {
            "timestamp": datetime(2026, 8, 12, 14, 37, tzinfo=UTC),
            "bid_price": 109.90,
            "ask_price": 110.10,
            "bid_size": 8,
            "ask_size": 6,
            "source": "Alpaca Market Data API / SIP quotes",
        }},
        "halt_events": [],
    }
    inputs.update(overrides)
    return build_event_market_context(**inputs)


def test_return_residuali_usano_spy_e_mapping_settore_deterministico():
    out = _build()
    row = out["per_symbol"]["NVDA"]

    assert row["sector"] == "semis"
    assert row["sector_etf"] == "SOXX"
    assert row["returns"]["symbol"] == pytest.approx(0.10)
    assert row["returns"]["spy"] == pytest.approx(0.02)
    assert row["returns"]["sector_etf"] == pytest.approx(0.05)
    assert row["returns"]["residual_vs_spy"] == pytest.approx(0.08)
    assert row["returns"]["residual_vs_sector"] == pytest.approx(0.05)
    assert row["returns"]["model"] == "beta_1_arithmetic_v1"


def test_enum_evento_regime_tema_e_missingness_sono_espliciti():
    known = _build()["per_symbol"]["NVDA"]
    assert known["catalyst"]["type"] == "MACRO"
    assert known["regime"]["type"] == "SIDEWAYS"
    assert known["theme"]["type"] == "AI_SEMIS"

    unknown = _build(
        candidates=[{"symbol": "ZZZ", "return": 0.04}],
        daily_bars={"ZZZ": _bar(100.0, 104.0), "SPY": _bar(500.0, 505.0)},
        sector_by_ticker={},
        articles=[],
        regime_observations=[],
        vix_observation=None,
        intraday_bars={},
        nbbo_quotes={},
    )["per_symbol"]["ZZZ"]
    assert unknown["catalyst"]["type"] == "UNKNOWN"
    assert unknown["regime"]["type"] == "UNKNOWN"
    assert unknown["theme"]["type"] == "UNKNOWN"
    assert unknown["sector"] is None
    assert unknown["returns"]["residual_vs_sector"] is None
    assert "sector_mapping_missing" in unknown["missingness"]
    assert "vix_missing" in unknown["missingness"]
    assert set(CATALYST_TYPES) >= {known["catalyst"]["type"], unknown["catalyst"]["type"]}
    assert set(REGIME_TYPES) >= {known["regime"]["type"], unknown["regime"]["type"]}
    assert set(THEME_TYPES) >= {known["theme"]["type"], unknown["theme"]["type"]}


def test_calendario_corporate_prevale_sulla_classificazione_lessicale():
    out = _build(
        articles=[{
            "ticker": "NVDA",
            "title": "Nvidia shares move before the open",
            "canonical_article_id": "content:generic",
            "relevance": "ISSUER_SPECIFIC",
        }],
        corporate_events=[{
            "symbol": "NVDA",
            "event_type": "earnings",
            "event_date": "2026-08-12",
            "source": "FMP earnings-calendar",
        }],
    )
    row = out["per_symbol"]["NVDA"]
    assert row["catalyst"]["type"] == "EARNINGS"
    assert row["corporate_calendar"]["status"] == "OBSERVED"
    assert row["corporate_calendar"]["events"][0]["source"] == "FMP earnings-calendar"


def test_opportunita_macro_stesso_tema_contano_come_un_cluster_indipendente():
    candidates = [
        {"symbol": "NVDA", "return": 0.10},
        {"symbol": "AMD", "return": 0.08},
        {"symbol": "JPM", "return": 0.04},
    ]
    articles = [
        {"ticker": "NVDA", "title": "AI stocks rally after macro data", "canonical_article_id": "content:ai", "relevance": "SECTOR_MACRO"},
        {"ticker": "AMD", "title": "AI stocks rally after macro data", "canonical_article_id": "content:ai", "relevance": "SECTOR_MACRO"},
        {"ticker": "JPM", "title": "JPMorgan raises guidance", "canonical_article_id": "content:jpm", "relevance": "ISSUER_SPECIFIC"},
    ]
    out = _build(
        candidates=candidates,
        daily_bars={
            "NVDA": _bar(100.0, 110.0), "AMD": _bar(100.0, 108.0),
            "JPM": _bar(100.0, 104.0), "SPY": _bar(500.0, 510.0),
            "SOXX": _bar(300.0, 315.0), "XLF": _bar(40.0, 40.4),
        },
        sector_by_ticker={"NVDA": "semis", "AMD": "semis", "JPM": "financials"},
        articles=articles,
        intraday_bars={},
        nbbo_quotes={},
    )

    assert out["statistics"]["raw_opportunities"] == 3
    assert out["statistics"]["independent_clusters"] == 2
    ai_cluster = next(c for c in out["clusters"] if c["member_symbols"] == ["AMD", "NVDA"])
    assert ai_cluster["independent_units"] == 1
    assert ai_cluster["correlation_basis"] == "shared_canonical_article_and_theme"


def test_microstruttura_separa_barre_e_nbbo_con_provenienza():
    row = _build()["per_symbol"]["NVDA"]["microstructure"]

    assert row["bar_based"]["basis"] == "BAR_5MIN"
    assert row["bar_based"]["session_volume"] == 1_000_000
    assert row["bar_based"]["adv_20d"] == 1_000_000
    assert row["bar_based"]["volume_adv_ratio"] == pytest.approx(1.0)
    assert row["bar_based"]["volume_surprise"] == pytest.approx(0.0)
    assert row["bar_based"]["provenance"]["timeframe"] == "5Min"

    assert row["nbbo"]["basis"] == "NBBO"
    assert row["nbbo"]["spread"] == pytest.approx(0.20)
    assert row["nbbo"]["spread_bps"] == pytest.approx(0.20 / 110.0 * 10_000)
    assert "SIP quotes" in row["nbbo"]["provenance"]["source"]
    assert row["halt"]["status"] == "UNKNOWN"
    assert row["halt"]["missing_reason"] == "authoritative_halt_feed_unavailable"
