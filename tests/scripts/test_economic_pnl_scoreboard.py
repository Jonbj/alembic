"""Orchestratore del scoreboard economico (#278): wiring I/O -> moduli puri.

L'orchestratore e' sottile di proposito: ogni formula sta nei moduli puri (gia'
coperti da test_dossier_economic_pnl / test_dossier_scoreboard). Qui si verifica
che l'I/O (Postgres, ledger, barre) venga raccolto nel formato giusto e passato
ai moduli, e che contaminazione e missingness arrivino all'output.
"""

from datetime import date
from contextlib import ExitStack
from unittest.mock import patch

import scripts.economic_pnl_scoreboard as orch


def _patch_io(canned):
    """Rende l'I/O dell'orchestratore deterministiche e restituisce uno stack."""
    def fake_psql(query):
        return canned["position_rows"]
    stack = ExitStack()
    stack.enter_context(patch.object(orch, "_psql", side_effect=fake_psql))
    stack.enter_context(patch.object(orch, "_market_rows", return_value=canned["market_rows"]))
    stack.enter_context(patch.object(orch, "_load_closes", return_value=canned["closes"]))
    return stack


def _canned():
    return {
        "market_rows": [
            {"data": "2026-07-31", "spy": 0.05, "miss": {"NO_NEWS": 1}, "dispersione_sigma": 0.03},
            {"data": "2026-08-03", "spy": 0.01, "miss": {"NO_NEWS": 3, "THIN_NEUTRAL": 1},
             "dispersione_sigma": 0.02},
            {"data": "2026-08-04", "spy": -0.005, "miss": {"THIN_NEUTRAL": 2},
             "dispersione_sigma": 0.02},
            {"data": "2026-08-07", "spy": 0.02, "miss": {"NO_NEWS": 2},
             "dispersione_sigma": 0.02},
            {"data": "2026-08-12", "spy": 0.003, "miss": {"NO_NEWS": 4, "THIN_NEUTRAL": 1},
             "dispersione_sigma": 0.02},
        ],
        # righe psql: symbol|stop_strategy|signal_id|entry_price|entry_date|exit_price|exit_date|qty
        "position_rows": [
            # S1 pre-finestra ancora aperta
            ["AAA", "S1", "", "100.0", "2026-07-10", "", "", "10.0"],
            # S4 entrato nella finestra e uscito
            ["BBB", "S4", "42", "50.0", "2026-08-04", "52.0", "2026-08-07", "20.0"],
            # contaminazione: nessuno stop_strategy, nessun signal_id (le 12 del 2026-07-10)
            ["CCC", "", "", "30.0", "2026-07-10", "", "", "5.0"],
        ],
        "closes": {
            date(2026, 8, 3): {"AAA": 100.0, "BBB": 50.0, "CCC": 30.0},
            date(2026, 8, 4): {"AAA": 104.0, "BBB": 51.0, "CCC": 28.0},
            date(2026, 8, 7): {"AAA": 106.0, "BBB": 53.0, "CCC": 31.0},
            date(2026, 8, 12): {"AAA": 110.0, "CCC": 29.0},
        },
    }


def test_orchestratore_wiring_produce_scoreboard_con_giorno_n_e_dominante():
    canned = _canned()
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 12))

    sb = payload["scoreboard"]
    # 5 righe nel ledger, ma 07-31 e' pre-finestra -> 4 giorni osservati
    assert sb["giorno"]["n"] == 4
    assert sb["giorno"]["denominatore"] == 40
    # NO_NEWS dominante su 08-03, 08-07, 08-12 (08-04 dominante THIN_NEUTRAL)
    assert sb["no_news_dominant"]["numerator"] == 3
    assert sb["no_news_dominant"]["denominator"] == 4


def test_orchestratore_calcola_pnl_economico_s1_s4_contaminazione():
    canned = _canned()
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 12))

    cum = payload["pnl_economico"]["cumulato"]
    # S1: AAA pre-finestra, mark_from=close 08-03=100, cum 08-12=(110-100)*10=100
    assert cum["S1"][date(2026, 8, 12)] == 100.0
    # S4: BBB entry 08-04 a 50, uscita 08-07 a 52 -> (52-50)*20=40, costante dopo
    assert cum["S4"][date(2026, 8, 12)] == 40.0
    # CONTAM: CCC pre-finestra mark_from=close 08-03=30, cum 08-12=(29-30)*5=-5
    assert cum["CONTAMINAZIONE"][date(2026, 8, 12)] == -5.0
    # BOOK = 100 + 40 - 5 = 135
    assert cum["BOOK"][date(2026, 8, 12)] == 135.0
    # la contaminazione non e' finita in S1
    assert payload["numerosita"]["S1"] == 1
    assert payload["numerosita"]["S4"] == 1
    assert payload["numerosita"]["CONTAMINAZIONE"] == 1


def test_orchestratore_s4_dentro_200_e_s1_vs_spy():
    canned = _canned()
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 12))

    sb = payload["scoreboard"]
    assert sb["s4_vs_200"]["cumulato"] == 40.0
    assert sb["s4_vs_200"]["within"] is True
    # S1 capital_base = close 08-03 * qty = 100*10 = 1000
    assert sb["s1_vs_spy"]["capital_base"] == 1000.0
    # SPY cum = (1.01)(0.995)(1.02)(1.003) - 1
    spy = (1.01 * 0.995 * 1.02 * 1.003) - 1.0
    assert sb["s1_vs_spy"]["spy_cum_return"] == spy
    assert sb["s1_vs_spy"]["spy_benchmark_usd"] == spy * 1000.0


def test_orchestratore_clampa_as_of_oltre_ultimo_osservato():
    canned = _canned()
    with _patch_io(canned):
        payload = orch.costruisci(date(2026, 8, 20))  # oltre il ledger
    # clampato al 2026-08-12
    assert payload["data"] == "2026-08-12"