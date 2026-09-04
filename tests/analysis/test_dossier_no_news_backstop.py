"""#409 — osservabilita' dei catalizzatori alternativi sui ticker NO_NEWS."""

from __future__ import annotations

import pytest

from src.analysis.dossier.no_news_backstop import build_no_news_backstop


def _bar(*, volume: int | None, adv_20d: float | None) -> dict:
    return {"volume": volume, "adv_20d": adv_20d}


def _build(**overrides) -> dict:
    inputs = {
        "universe": ["NVO", "ERIC", "RDDT", "QUIET", "AAPL"],
        "returns": {
            "NVO": 0.0371,
            "ERIC": -0.0308,
            "RDDT": -0.0436,
            "QUIET": 0.004,
            "AAPL": 0.01,
        },
        "news_counts": {"AAPL": 3},
        "sector_by_ticker": {
            "NVO": "healthcare",
            "ERIC": "telecom",
            "RDDT": "media",
            "QUIET": "telecom",
            "AAPL": "tech",
        },
        "daily_bars": {
            "NVO": _bar(volume=1_080_000, adv_20d=1_000_000),
            "ERIC": _bar(volume=2_250_000, adv_20d=1_000_000),
            "RDDT": _bar(volume=400_000, adv_20d=1_000_000),
            "QUIET": _bar(volume=900_000, adv_20d=1_000_000),
            "AAPL": _bar(volume=1_200_000, adv_20d=1_000_000),
        },
        "corporate_events": {
            "events": [{
                "symbol": "NVO",
                "event_type": "cash_dividends",
                "event_date": "2026-08-25",
                "source": "Alpaca Corporate Actions API",
            }],
            "sources_succeeded": [
                "FMP earnings-calendar",
                "Alpaca Corporate Actions API",
            ],
            "complete": True,
            "missingness": [],
        },
        "mover_threshold": 0.03,
    }
    inputs.update(overrides)
    return build_no_news_backstop(**inputs)


def test_popolazione_zero_news_include_mover_e_controllo_non_mover():
    out = _build()

    assert [row["symbol"] for row in out["per_symbol"]] == [
        "ERIC",
        "NVO",
        "QUIET",
        "RDDT",
    ]
    assert out["population"] == {
        "zero_news": 4,
        "movers": 3,
        "non_movers": 1,
        "return_missing": 0,
    }


def test_calendario_diventa_marker_osservazionale_senza_produrre_segnali():
    out = _build()
    nvo = next(row for row in out["per_symbol"] if row["symbol"] == "NVO")

    assert nvo["observed_catalysts"] == ["CALENDAR"]
    assert nvo["calendar"]["status"] == "OBSERVED"
    assert nvo["calendar"]["event_types"] == ["cash_dividends"]
    assert nvo["calendar"]["sources"] == ["Alpaca Corporate Actions API"]
    assert out["calendar_observation"] == {
        "mover_observed": 1,
        "mover_population": 3,
        "mover_rate": pytest.approx(1 / 3),
        "non_mover_observed": 0,
        "non_mover_population": 1,
        "non_mover_rate": 0.0,
    }
    assert "signal" not in nvo


def test_volume_eod_resta_descrittivo_e_non_viene_travestito_da_segnale_pit():
    out = _build()
    rows = {row["symbol"]: row for row in out["per_symbol"]}

    assert rows["ERIC"]["volume"]["surprise"] == pytest.approx(1.25)
    assert rows["RDDT"]["volume"]["surprise"] == pytest.approx(-0.60)
    assert out["volume_observation"]["mover_median"] == pytest.approx(0.08)
    assert out["volume_observation"]["non_mover_median"] == pytest.approx(-0.10)
    assert out["volume_observation"]["temporal_validity"] == "POST_HOC_EOD"
    assert out["volume_observation"]["valid_for_signal_evaluation"] is False
    assert "threshold" not in out["volume_observation"]
    assert all("above_threshold" not in row["volume"] for row in rows.values())


def test_copertura_raw_per_settore_rende_visibili_anche_gli_zero_su_n():
    out = _build()

    assert out["per_sector"]["healthcare"] == {
        "ticker_universe": 1,
        "ticker_with_news": 0,
        "ticker_zero_news": 1,
        "raw_news_coverage_rate": 0.0,
        "zero_news_movers": 1,
        "calendar_observed_zero_news": 1,
    }
    assert out["per_sector"]["tech"]["raw_news_coverage_rate"] == 1.0
    assert out["per_sector"]["telecom"]["ticker_zero_news"] == 2


def test_calendario_parziale_non_certifica_assenza_di_eventi():
    out = _build(corporate_events={
        "events": [],
        "sources_succeeded": ["Alpaca Corporate Actions API"],
        "complete": False,
        "missingness": ["earnings_calendar_unavailable"],
    })

    assert {
        row["calendar"]["status"] for row in out["per_symbol"]
    } == {"UNKNOWN"}
    assert out["calendar_observation"]["mover_rate"] is None
    assert out["calendar_observation"]["non_mover_rate"] is None
