"""#324 — cecita' della copertura news sul lato uscita del libro.

Il dossier misura la copertura sui **mover non in portafoglio**: `compute_miss_candidates`
scarta per costruzione i simboli gia' detenuti (`sym not in in_portafoglio`). Una
posizione in perdita marcata che non ha una riga di news da giorni non compare quindi in
nessun conteggio: l'assenza di notizia non impedisce solo l'ingresso, impedisce anche
qualunque segnale di uscita, e quel secondo effetto non era misurato da nulla.

Questi test fissano il contratto del modulo puro prima del wiring nel dossier. Misura
read-only: non esiste nessuna decisione di trading che leggera' questi campi.
"""

import pytest

from src.analysis.dossier.exit_coverage import build_exit_coverage


SEDUTE = [
    "2026-08-13",
    "2026-08-14",
    "2026-08-17",
    "2026-08-18",
    "2026-08-19",
]
DATA = "2026-08-19"


def _posizione(
    symbol: str,
    *,
    trade_id: int = 1,
    strategia: str = "S1",
    qty: float | None = 10.0,
    entry_price: float | None = 100.0,
    entry_time: str | None = "2026-07-22T14:00:00+00:00",
    exit_time: str | None = None,
    exit_price: float | None = None,
) -> dict:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "strategia": strategia,
        "qty": qty,
        "entry_price": entry_price,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "exit_price": exit_price,
    }


def _build(posizioni, **kwargs):
    parametri = {
        "data": DATA,
        "sedute": SEDUTE,
        "righe_per_seduta": {},
        "fonti_finestra": {},
        "copertura_per_ticker": {},
        "segnali_per_ticker": {},
        "barre": {},
    }
    parametri.update(kwargs)
    return build_exit_coverage(posizioni, **parametri)


def test_posizione_in_perdita_marcata_e_a_zero_copertura_e_cieca_lato_uscita():
    """GE il 2026-08-19: -5% dall'ingresso, zero righe news_log su due sedute."""
    payload = _build(
        [_posizione("GE", trade_id=71)],
        righe_per_seduta={"GE": {"2026-08-14": 3}},
        barre={"GE": {"close": 94.0, "open": 99.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["ticker"] == "GE"
    assert riga["trade_id"] == 71
    assert riga["ritorno_da_ingresso"] == pytest.approx(-0.06)
    assert riga["perdita_marcata"] is True
    assert riga["copertura_nulla"] is True
    assert riga["sedute_consecutive_senza_righe"] == 3  # 17, 18, 19
    assert riga["cieco_lato_uscita"] is True
    assert riga["missingness"] == []

    aggregato = payload["aggregato"]
    assert aggregato["n_posizioni"] == 1
    assert aggregato["n_copertura_nulla"] == 1
    assert aggregato["n_perdita_marcata"] == 1
    assert aggregato["n_cieche_lato_uscita"] == 1
    assert aggregato["n_cieche_ancora_aperte"] == 1
    assert aggregato["ticker_ciechi"] == ["GE"]
    assert aggregato["notional_cieco_usd"] == 940.0


def test_una_sola_seduta_senza_righe_non_basta():
    """La soglia di ricorrenza e' dichiarata: una giornata muta non e' un difetto."""
    payload = _build(
        [_posizione("DELL")],
        righe_per_seduta={"DELL": {"2026-08-18": 2}},
        barre={"DELL": {"close": 90.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["sedute_consecutive_senza_righe"] == 1
    assert riga["perdita_marcata"] is True
    assert riga["copertura_nulla"] is True
    assert riga["cieco_lato_uscita"] is False


def test_perdita_sotto_soglia_non_e_cecita_anche_a_copertura_nulla():
    """La cecita' interessa dove c'e' qualcosa da decidere: posizione in rosso marcato."""
    payload = _build(
        [_posizione("WDC")],
        barre={"WDC": {"close": 99.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["ritorno_da_ingresso"] == pytest.approx(-0.01)
    assert riga["perdita_marcata"] is False
    assert riga["copertura_nulla"] is True
    assert riga["cieco_lato_uscita"] is False
    assert payload["aggregato"]["n_cieche_lato_uscita"] == 0


def test_un_segnale_di_sentiment_esclude_la_copertura_nulla():
    """Zero righe news_log ma un segnale scritto: il canale d'uscita non era muto."""
    payload = _build(
        [_posizione("GE")],
        segnali_per_ticker={"GE": 2},
        barre={"GE": {"close": 90.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["segnali_sentiment_giorno"] == 2
    assert riga["copertura_nulla"] is False
    assert riga["cieco_lato_uscita"] is False


def test_barra_mancante_lascia_la_perdita_e_il_verdetto_indeterminati():
    """Senza close non si inventa un mark: UNKNOWN, non False per difetto."""
    payload = _build([_posizione("BP")])

    (riga,) = payload["posizioni"]
    assert riga["ritorno_da_ingresso"] is None
    assert riga["perdita_marcata"] is None
    assert riga["cieco_lato_uscita"] is None
    assert "daily_bar_missing" in riga["missingness"]
    assert payload["aggregato"]["n_indeterminati"] == 1
    assert payload["aggregato"]["n_cieche_lato_uscita"] == 0


def test_prezzo_di_ingresso_mancante_lascia_il_verdetto_indeterminato():
    payload = _build(
        [_posizione("BA", entry_price=None)],
        barre={"BA": {"close": 50.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["ritorno_da_ingresso"] is None
    assert riga["cieco_lato_uscita"] is None
    assert "entry_price_missing" in riga["missingness"]


def test_senza_calendario_lo_streak_e_il_verdetto_restano_indeterminati():
    """Il calendario Alpaca puo' non rispondere: lo streak non vale zero."""
    payload = _build(
        [_posizione("GE")],
        sedute=[],
        barre={"GE": {"close": 90.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["sedute_consecutive_senza_righe"] is None
    assert riga["cieco_lato_uscita"] is None
    assert "calendario_sedute_non_disponibile" in riga["missingness"]
    assert payload["aggregato"]["n_indeterminati"] == 1


def test_lo_streak_non_conta_sedute_precedenti_all_ingresso():
    """Una posizione aperta ieri non puo' essere cieca da una settimana."""
    payload = _build(
        [_posizione("NOW", entry_time="2026-08-18T15:00:00+00:00")],
        barre={"NOW": {"close": 90.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["sedute_consecutive_senza_righe"] == 2  # 18 e 19, non prima
    assert riga["streak_troncato_da"] == "ingresso"
    assert riga["cieco_lato_uscita"] is True


def test_lo_streak_dichiara_il_troncamento_dalla_finestra():
    """Nessuna riga in tutta la finestra: lo streak vero puo' essere piu' lungo."""
    payload = _build(
        [_posizione("AZN")],
        barre={"AZN": {"close": 90.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["sedute_consecutive_senza_righe"] == len(SEDUTE)
    assert riga["streak_troncato_da"] == "finestra"


def test_uscita_intraday_in_profitto_non_diventa_cieca_per_il_close_successivo():
    """Dopo l'uscita il book non subisce il successivo crollo fino al close."""
    payload = _build(
        [_posizione(
            "CRM",
            exit_time="2026-08-19T18:00:00+00:00",
            exit_price=105.0,
        )],
        barre={"CRM": {"close": 90.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["uscita_nella_seduta"] is True
    assert riga["exit_price"] == 105.0
    assert riga["mark_close"] == 90.0
    assert riga["mark_valutazione"] == 105.0
    assert riga["mark_valutazione_fonte"] == "exit_price"
    assert riga["ritorno_da_ingresso"] == pytest.approx(0.05)
    assert riga["perdita_marcata"] is False
    assert riga["cieco_lato_uscita"] is False
    aggregato = payload["aggregato"]
    assert aggregato["n_cieche_lato_uscita"] == 0
    assert aggregato["n_cieche_ancora_aperte"] == 0


def test_uscita_intraday_senza_prezzo_lascia_il_verdetto_indeterminato():
    """Un fill non ancora riconciliato non autorizza il fallback al close EOD."""
    payload = _build(
        [_posizione("CRM", exit_time="2026-08-19T18:00:00+00:00")],
        barre={"CRM": {"close": 90.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["uscita_nella_seduta"] is True
    assert riga["mark_valutazione"] is None
    assert riga["mark_valutazione_fonte"] == "exit_price"
    assert riga["ritorno_da_ingresso"] is None
    assert riga["perdita_marcata"] is None
    assert riga["cieco_lato_uscita"] is None
    assert "exit_price_missing" in riga["missingness"]
    assert payload["aggregato"]["n_indeterminati"] == 1


def test_le_fonti_osservate_distinguono_zero_resa_da_zero_configurazione():
    """#324 punto 2: le fonti per-ticker sono le stesse per tutta la watchlist,
    quindi zero righe significa zero resa del provider, non fonte non configurata.
    Il campo espone le fonti che HANNO prodotto qualcosa nella finestra."""
    payload = _build(
        [_posizione("GE", trade_id=1), _posizione("F", trade_id=2)],
        righe_per_seduta={"GE": {"2026-08-13": 4}},
        fonti_finestra={"GE": ["alpaca_benzinga", "gdelt_gkg"]},
        barre={"GE": {"close": 90.0}, "F": {"close": 90.0}},
    )

    # le righe sono ordinate per ticker: F precede GE
    f, ge = payload["posizioni"]
    assert ge["fonti_osservate_finestra"] == ["alpaca_benzinga", "gdelt_gkg"]
    assert f["fonti_osservate_finestra"] == []
    assert payload["aggregato"]["ticker_ciechi"] == ["F", "GE"]


def test_copertura_effettiva_nulla_e_distinta_dalla_copertura_nulla():
    """Articoli presenti ma nessuno issuer-specific tempestivo: e' un difetto di
    rilevanza (#279), non un buco di ingestione. Non deve diventare cecita'."""
    payload = _build(
        [_posizione("ADBE")],
        righe_per_seduta={"ADBE": {DATA: 5}},
        copertura_per_ticker={
            "ADBE": {"articoli_unici": 3, "effective_timely_articles": 0}
        },
        barre={"ADBE": {"close": 90.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["righe_news_log_giorno"] == 5
    assert riga["articoli_unici_giorno"] == 3
    assert riga["articoli_effective_timely_giorno"] == 0
    assert riga["copertura_nulla"] is False
    assert riga["copertura_effettiva_nulla"] is True
    assert riga["cieco_lato_uscita"] is False
    assert payload["aggregato"]["n_copertura_effettiva_nulla"] == 1


def test_causal_event_id_e_stabile_e_non_raddoppia_fra_giorni():
    payload = _build(
        [_posizione("GE", trade_id=71)],
        barre={"GE": {"close": 90.0}},
    )
    (riga,) = payload["posizioni"]
    assert riga["causal_event_id"] == "exit-coverage:71:2026-08-19"


def test_definizione_e_parametri_sono_dichiarati_nel_payload():
    payload = _build([], barre={})
    assert payload["soglia_perdita_da_ingresso"] == -0.03
    assert payload["sedute_minime"] == 2
    assert "definizione" in payload
    assert payload["aggregato"]["n_posizioni"] == 0
    assert payload["aggregato"]["notional_cieco_usd"] == 0.0


def test_ritorno_di_seduta_e_distinto_dal_ritorno_da_ingresso():
    """Il 2026-08-19 GE ha fatto -5,03% nella seduta ma era +4,25% dall'ingresso: la
    perdita da tenere sotto osservazione per un'uscita e' la seconda, non la prima.
    Il dossier riporta entrambe perche' rispondono a due domande diverse."""
    payload = _build(
        [_posizione("GE", entry_price=90.0)],
        barre={"GE": {"close": 94.0, "close_prec": 99.0}},
    )

    (riga,) = payload["posizioni"]
    assert riga["ritorno_da_ingresso"] == pytest.approx(0.0444, abs=1e-4)
    assert riga["ritorno_seduta"] == pytest.approx(-0.0505, abs=1e-4)
    assert riga["perdita_marcata"] is False
    assert riga["cieco_lato_uscita"] is False


def test_ritorno_di_seduta_none_senza_close_precedente():
    payload = _build(
        [_posizione("GE")],
        barre={"GE": {"close": 94.0}},
    )
    (riga,) = payload["posizioni"]
    assert riga["ritorno_seduta"] is None
