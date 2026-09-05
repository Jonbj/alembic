"""Wiring della copertura lato uscita nel dossier (#324).

Il punto cieco che il wiring deve chiudere: una posizione detenuta in perdita marcata
non compare fra i `candidati_miss` (li' entrano solo i mover NON in portafoglio), quindi
le sue zero righe di `news_log` non erano contate da nulla. Dopo il wiring la stessa
seduta produce sia il candidato d'ingresso sia la riga lato uscita.

Misura read-only: nessun ordine cambiato, nessuna soglia di strategia toccata.
"""

from datetime import date, datetime, timezone
from unittest.mock import patch

import scripts.alpha_miner_dossier as dossier

UTC = timezone.utc


def _fake_psql(query):
    """Risponde alle query minime che il dossier fa per questo test."""
    if "FROM s4_candidate_population" in query:
        return []
    if "FROM trades WHERE entry_time >=" in query:
        return []
    if "FROM trades WHERE exit_time >=" in query:
        return []
    if "SELECT DISTINCT symbol FROM trades" in query:
        return [["GE"]]
    # posizioni vive all'open RTH
    if "FROM trades WHERE entry_time <" in query:
        return [["71", "GE", "S1", "10", "100.0",
                 "2026-07-22T14:00:00+00:00", "", "", ""]]
    if "GROUP BY 1,2,3" in query:
        # ticker, seduta, fonte, righe: GE ha notizie solo il 14, non dal 17
        return [["GE", "2026-08-14", "alpaca_benzinga", "3"]]
    if "FROM news_log" in query and "GROUP BY 1" in query:
        return [["CRM", "4"]]
    if "article_coverage_279" in query:
        return []
    if "FROM sentiment_signals" in query:
        return []
    if "information_schema.columns" in query:
        return []
    return []


DAILY = {
    "GE": {"open": 99.0, "high": 99.5, "low": 93.0, "close": 94.0,
           "close_prec": 99.0, "volume": 1000, "adv_20d": None,
           "adv_20d_observations": 0},
    "CRM": {"open": 100.0, "high": 106.0, "low": 99.0, "close": 105.0,
            "close_prec": 100.0, "volume": 1000, "adv_20d": None,
            "adv_20d_observations": 0},
    "SPY": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "close_prec": 100.0, "volume": 1000, "adv_20d": None,
            "adv_20d_observations": 0},
}
SEDUTE = ["2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19"]


def _dossier():
    cutoff = datetime(2026, 8, 19, 23, 59, tzinfo=UTC)
    with (
        patch.object(dossier, "_psql", side_effect=_fake_psql),
        patch.object(dossier, "_barre", return_value=DAILY),
        patch.object(dossier, "_soglia_gate_s4", return_value=0.30),
        patch.object(dossier, "_timeline_eventi", return_value=[]),
        patch.object(dossier, "_barre_intraday", return_value=({}, cutoff)),
        patch.object(dossier, "_dettagli_ordini", return_value={}),
        patch.object(dossier, "_sedute_di_borsa", return_value=SEDUTE),
    ):
        return dossier.costruisci_dossier(date(2026, 8, 19), ["GE", "CRM"])


def test_la_posizione_detenuta_cieca_compare_nel_dossier():
    payload = _dossier()

    # premessa del difetto: il mover detenuto NON e' fra i candidati miss
    assert [c["symbol"] for c in payload["candidati_miss"]] == ["CRM"]

    copertura = payload["copertura_uscita"]
    (riga,) = copertura["posizioni"]
    assert riga["ticker"] == "GE"
    assert riga["trade_id"] == 71
    assert riga["righe_news_log_giorno"] == 0
    assert riga["segnali_sentiment_giorno"] == 0
    assert riga["copertura_nulla"] is True
    assert riga["perdita_marcata"] is True
    assert riga["sedute_consecutive_senza_righe"] == 3
    assert riga["fonti_osservate_finestra"] == ["alpaca_benzinga"]
    assert riga["cieco_lato_uscita"] is True

    aggregato = payload["aggregati"]["copertura_uscita"]
    assert aggregato["n_cieche_lato_uscita"] == 1
    assert aggregato["ticker_ciechi"] == ["GE"]


def test_schema_e_provenienza_dichiarano_la_nuova_misura():
    payload = _dossier()
    assert payload["schema_version"] == "2.8"
    assert "copertura_uscita" in payload["provenienza_dati"]
    assert "ore_tenuta_s4" in payload["provenienza_dati"]
    assert payload["aggregati"]["ore_tenuta_s4"] == {
        "strategia": "S4",
        "ampiezza_bucket_minuti": 15,
        "n_chiusure": 0,
        "buckets": [],
    }


def test_calendario_non_disponibile_non_uccide_il_dossier():
    """Se Alpaca non risponde sul calendario, lo streak resta UNKNOWN e il cron
    continua: un dossier senza streak vale piu' di nessun dossier."""
    cutoff = datetime(2026, 8, 19, 23, 59, tzinfo=UTC)
    with (
        patch.object(dossier, "_psql", side_effect=_fake_psql),
        patch.object(dossier, "_barre", return_value=DAILY),
        patch.object(dossier, "_soglia_gate_s4", return_value=0.30),
        patch.object(dossier, "_timeline_eventi", return_value=[]),
        patch.object(dossier, "_barre_intraday", return_value=({}, cutoff)),
        patch.object(dossier, "_dettagli_ordini", return_value={}),
        patch.object(dossier, "_sedute_di_borsa", return_value=[]),
    ):
        payload = dossier.costruisci_dossier(date(2026, 8, 19), ["GE", "CRM"])

    (riga,) = payload["copertura_uscita"]["posizioni"]
    assert riga["sedute_consecutive_senza_righe"] is None
    assert riga["cieco_lato_uscita"] is None
    assert "calendario_sedute_non_disponibile" in riga["missingness"]
