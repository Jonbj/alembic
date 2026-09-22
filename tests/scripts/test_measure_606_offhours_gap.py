"""Guardie della misura confermativa sul gap fuori orario (#606)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import scripts.measure_606_offhours_gap as m


ET = ZoneInfo("America/New_York")


def _sedute(giorni: list[date]) -> list[dict]:
    return [
        {
            "data": giorno,
            "apertura": datetime.combine(giorno, time(9, 30), tzinfo=ET),
            "chiusura": datetime.combine(giorno, time(16, 0), tzinfo=ET),
        }
        for giorno in giorni
    ]


def test_popolazione_deduplica_con_la_regola_di_produzione_e_tronca_embargo():
    sedute = _sedute([date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9)])
    pubblicata = datetime.combine(date(2026, 7, 7), time(18), tzinfo=ET)
    segnali = [
        {
            "symbol": "NVDA", "score": 0.5, "fallback": True,
            "published_at": pubblicata, "generated_at": pubblicata + timedelta(hours=2),
        },
        {
            "symbol": "NVDA", "score": 0.2, "fallback": False,
            "published_at": pubblicata, "generated_at": pubblicata + timedelta(hours=1),
        },
        {
            "symbol": "AAPL", "score": 0.5, "fallback": False,
            "published_at": datetime.combine(date(2026, 7, 8), time(18), tzinfo=ET),
            "generated_at": datetime.combine(date(2026, 7, 8), time(19), tzinfo=ET),
        },
    ]

    scelti, scarti = m.costruisci_popolazione(
        segnali, sedute, datetime.combine(date(2026, 7, 9), time(0), tzinfo=ET)
    )

    assert [s["symbol"] for s in scelti] == ["NVDA"]
    assert scelti[0]["fallback"] is False
    assert scarti["oltre_taglio_embargo"] == 1


def test_fetch_barre_giornaliere_fallito_aborta_invece_di_ridurre_il_campione():
    class Client:
        def get_stock_bars(self, request):
            raise RuntimeError("subscription does not permit querying recent SIP data")

    with pytest.raises(m.MisuraAbortita, match="barre giornaliere non recuperabili"):
        m.scarica_barre_giornaliere(
            Client(), ["AAPL", "SPY"], date(2026, 7, 1), date(2026, 7, 2)
        )


def test_media_t_pesa_le_sedute_non_il_numero_di_eventi():
    risultato = m.media_t({
        date(2026, 7, 1): [0.10] * 100,
        date(2026, 7, 2): [0.00],
        date(2026, 7, 3): [0.00],
        date(2026, 7, 6): [0.00],
    })

    assert risultato["n_giornate"] == 4
    assert risultato["n_eventi"] == 103
    assert risultato["media_bp"] == pytest.approx(250.0)
    assert risultato["effetto_rilevabile_a_t3_bp"] > 0


def test_verdetto_non_pubblica_l_effetto_prima_di_80_giornate():
    risultato = {
        "n_giornate": m.GIORNATE_RICHIESTE - 1,
        "n_eventi": 250,
        "media_bp": 56.0,
        "t": 4.0,
        "effetto_rilevabile_a_t3_bp": 20.0,
    }

    verdetto = m.verdetto(risultato)

    assert verdetto["esito"] == "INSUFFICIENT_N"
    assert verdetto["effetto_osservato_bp"] is None
    assert verdetto["t"] is None
    assert verdetto["effetto_rilevabile_a_t3_bp"] == pytest.approx(20.0)


def test_artefatto_pre_80_non_pubblica_neppure_l_outcome_secondario():
    risultato = {
        "popolazione": {"sedute": m.GIORNATE_RICHIESTE - 1},
        "gap_eccesso": {
            "n_giornate": m.GIORNATE_RICHIESTE - 1,
            "n_eventi": 250,
            "media_bp": 56.0,
            "t": 4.0,
            "effetto_rilevabile_a_t3_bp": 20.0,
        },
        "intraday_eccesso": {
            "n_giornate": m.GIORNATE_RICHIESTE - 1,
            "n_eventi": 250,
            "media_bp": -30.0,
            "t": -4.0,
            "effetto_rilevabile_a_t3_bp": 10.0,
        },
    }

    assert "secondario_intraday_eccesso" not in m.artefatto(risultato)


def test_verdetto_pass_fail_solo_con_campione_e_potenza_sufficienti():
    base = {
        "n_giornate": m.GIORNATE_RICHIESTE,
        "n_eventi": 250,
        "media_bp": 56.0,
        "effetto_rilevabile_a_t3_bp": 20.0,
    }
    assert m.verdetto({**base, "t": 3.0})["esito"] == "PASS"
    assert m.verdetto({**base, "t": -3.0})["esito"] == "FAIL"
    assert m.verdetto({**base, "t": 2.9})["esito"] == "INSUFFICIENT_N"
    assert m.verdetto({**base, "t": 3.0, "media_bp": 10.0})["esito"] == "INSUFFICIENT_N"


def test_taglio_embargo_e_tre_giorni_prima_di_ora():
    ora = datetime(2026, 7, 12, 15, tzinfo=timezone.utc)
    assert m.taglio_embargo(ora) == datetime(2026, 7, 9, 15, tzinfo=timezone.utc)
