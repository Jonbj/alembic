"""Misura degli streak di copertura zero per ticker (#511)."""

from src.analysis.dossier.blind_set import build_blind_set


def _coverage(**per_ticker):
    return {"per_ticker": per_ticker}


def _ticker(raw: int, effective: int):
    return {
        "articoli_unici": raw,
        "effective_timely_articles": effective,
    }


def test_streak_separa_la_cecita_raw_da_quella_effective():
    """Un articolo non efficace interrompe solo lo streak raw.

    Il commento di #511 qualifica la lista: un ticker che lascia il set raw non
    e' per questo coperto in modo issuer-specific e tempestivo.
    """
    out = build_blind_set(
        _coverage(IBM=_ticker(0, 0), SAP=_ticker(1, 0), AAPL=_ticker(2, 1)),
        universe=["AAPL", "IBM", "SAP"],
        sedute=["2026-09-01", "2026-09-02", "2026-09-03"],
        dossier_storici={
            "2026-09-01": _coverage(
                IBM=_ticker(0, 0), SAP=_ticker(0, 0), AAPL=_ticker(0, 0)
            ),
            "2026-09-02": _coverage(
                IBM=_ticker(0, 0), SAP=_ticker(1, 0), AAPL=_ticker(1, 1)
            ),
        },
    )

    assert out["per_ticker"]["IBM"] == {
        "articoli_unici_giorno": 0,
        "effective_timely_articles_giorno": 0,
        "sedute_consecutive_zero_articoli": 3,
        "zero_articoli_streak_troncato_da": "finestra",
        "sedute_consecutive_zero_effective_timely": 3,
        "zero_effective_timely_streak_troncato_da": "finestra",
    }
    # SAP ha prodotto una riga nelle ultime due sedute, ma nessuna era
    # effective-timely: la misura non confonde il sollievo raw con la copertura.
    assert out["per_ticker"]["SAP"]["sedute_consecutive_zero_articoli"] == 0
    assert out["per_ticker"]["SAP"]["sedute_consecutive_zero_effective_timely"] == 3
    assert out["ticker_allerta_zero_articoli"] == []


def test_streak_non_attraversa_un_dossier_mancante_e_allerta_a_cinque_sedute():
    """Una seduta non misurata tronca lo streak; non e' una falsa copertura."""
    out = build_blind_set(
        _coverage(ASML=_ticker(0, 0)),
        universe=["ASML"],
        sedute=[
            "2026-08-27", "2026-08-31", "2026-09-01", "2026-09-02",
            "2026-09-03", "2026-09-04",
        ],
        dossier_storici={
            "2026-08-27": _coverage(ASML=_ticker(0, 0)),
            "2026-08-31": _coverage(ASML=_ticker(0, 0)),
            "2026-09-01": _coverage(ASML=_ticker(0, 0)),
            "2026-09-02": _coverage(ASML=_ticker(0, 0)),
            "2026-09-03": _coverage(ASML=_ticker(0, 0)),
        },
    )

    asml = out["per_ticker"]["ASML"]
    assert asml["sedute_consecutive_zero_articoli"] == 6
    assert asml["zero_articoli_streak_troncato_da"] == "finestra"
    assert out["ticker_allerta_zero_articoli"] == ["ASML"]

    missing = build_blind_set(
        _coverage(ASML=_ticker(0, 0)),
        universe=["ASML"],
        sedute=["2026-09-01", "2026-09-02", "2026-09-03"],
        dossier_storici={"2026-09-01": _coverage(ASML=_ticker(0, 0))},
    )
    assert missing["per_ticker"]["ASML"]["sedute_consecutive_zero_articoli"] == 1
    assert missing["per_ticker"]["ASML"]["zero_articoli_streak_troncato_da"] == "dossier_mancante"


def test_calendario_assente_non_inventa_uno_streak():
    out = build_blind_set(
        _coverage(ASML=_ticker(0, 0)),
        universe=["ASML"],
        sedute=[],
        dossier_storici={},
    )

    row = out["per_ticker"]["ASML"]
    assert row["sedute_consecutive_zero_articoli"] is None
    assert row["zero_articoli_streak_troncato_da"] == "calendario_sedute_non_disponibile"
    assert out["ticker_allerta_zero_articoli"] == []