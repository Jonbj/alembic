"""Orchestratore del P&L totale per sleeve (#210).

L'orchestratore e' sottile come ``scripts/economic_pnl_scoreboard``: ogni
formula sta nei moduli puri (``src/analysis/dossier/total_pnl.py``, gia'
coperto da ``test_dossier_total_pnl``). Qui si verifica solo il wiring
dell'I/O -- Postgres per realized e posizioni, Alpaca SIP per i prezzi
correnti -- e che il payload finale abbia la forma promessa al verdetto
del 28/09.
"""

from contextlib import ExitStack
from datetime import date
from unittest.mock import patch

import scripts.realized_total_pnl as orch


def _patch_io(canned):
    """Rende deterministici i tre punti di I/O dell'orchestratore."""
    def fake_psql(query):
        # la prima query e' quella dei trade (realized + simboli aperti);
        # il resultato deve poter servire entrambi gli scopi.
        return canned["trade_rows"]
    stack = ExitStack()
    stack.enter_context(patch.object(orch, "_psql", side_effect=fake_psql))
    stack.enter_context(patch.object(orch, "_load_closes", return_value=canned["closes"]))
    return stack


def _canned():
    return {
        # symbol | stop_strategy | signal_id | entry_price | entry_date | exit_price
        # | exit_date | net_pnl | qty
        "trade_rows": [
            # S1: chiusa in finestra a -10
            ["AAA", "S1", "", "100.0", "2026-07-14", "90.0",
             "2026-08-05", "-10.0", "10.0"],
            # S1: aperta, MTMark = (110 - 100)*10 = +100
            ["BBB", "S1", "", "100.0", "2026-08-02", "", "", "", "10.0"],
            # S4: aperta, MTMark = (108 - 100)*10 = +80
            ["CCC", "S4", "42", "100.0", "2026-08-03", "", "", "", "10.0"],
            # Contaminazione: aperta, MTMark = (90 - 100)*10 = -100
            ["DDD", "", "", "100.0", "2026-07-10", "", "", "", "10.0"],
            # Legacy NULL prima della finestra: ignorata
            ["EEE", "", "", "50.0", "2026-07-10", "55.0", "2026-07-09",
             "50.0", "5.0"],
        ],
        "closes": {
            # L'ultimo giorno di borsa della finestra [W_START, AS_OF]
            date(2026, 8, 20): {"BBB": 110.0, "CCC": 108.0, "DDD": 90.0},
        },
    }


def test_orchestratore_calcola_realized_e_mtm_per_sleeve():
    canned = _canned()
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 20))

    pnl = payload["pnl_totale"]
    # S1: realized=-10 (chiusura AAA), MTMark=+100 (BBB aperta) -> total=+90
    assert pnl["S1"]["realized"] == -10.0
    assert pnl["S1"]["mark_to_market_open"] == 100.0
    assert pnl["S1"]["total"] == 90.0
    # S4: realized=0, MTMark=+80
    assert pnl["S4"]["realized"] == 0.0
    assert pnl["S4"]["mark_to_market_open"] == 80.0
    assert pnl["S4"]["total"] == 80.0
    # CONTAMINAZIONE: realized=0, MTMark=-100
    assert pnl["CONTAMINAZIONE"]["mark_to_market_open"] == -100.0
    # BOOK: somma delle tre
    assert pnl["BOOK"]["total"] == 90.0 + 80.0 - 100.0


def test_orchestratore_realized_chiuse_prima_della_finestra_sono_zero():
    canned = _canned()
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 20))

    # EEE chiusa il 2026-07-09 e' fuori finestra -> realized 0
    pnl = payload["pnl_totale"]
    total_realized = sum(pnl[s]["realized"] for s in ("S1", "S4", "CONTAMINAZIONE"))
    assert total_realized == -10.0  # solo AAA


def test_orchestratore_aperte_senza_close_di_riferimento_in_non_marcabili():
    canned = _canned()
    # Togliamo il close di BBB: la posizione resta aperta ma non marcabile.
    canned["closes"] = {
        date(2026, 8, 20): {"CCC": 108.0, "DDD": 90.0},
    }
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 20))

    pnl = payload["pnl_totale"]
    assert pnl["S1"]["mark_to_market_open"] == 0.0
    assert pnl["S1"]["n_open_unmarked"] == 1
    assert pnl["S1"]["n_open_marked"] == 0


def test_orchestratore_payload_espone_finestra_e_attribuzione():
    canned = _canned()
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 20))

    assert payload["finestra_inizio"] == orch.INIZIO_OSSERVAZIONE.isoformat()
    assert payload["data"] == "2026-08-20"
    assert payload["fonte_prezzi"] == "Alpaca SIP, adjustment=all"
    assert "stop_strategy" in payload["attribuzione"]
    assert "CONTAMINAZIONE" in payload["attribuzione"]


def test_orchestratore_book_n_chiusi_e_n_aperte_coerenti():
    canned = _canned()
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 20))

    pnl = payload["pnl_totale"]
    n_closed = (pnl["S1"]["n_closed"] + pnl["S4"]["n_closed"]
                + pnl["CONTAMINAZIONE"]["n_closed"])
    n_open_marked = (pnl["S1"]["n_open_marked"] + pnl["S4"]["n_open_marked"]
                     + pnl["CONTAMINAZIONE"]["n_open_marked"])
    assert n_closed == pnl["BOOK"]["n_closed"] == 1
    assert n_open_marked == pnl["BOOK"]["n_open_marked"] == 3
