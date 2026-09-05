"""Misura della classe «emittente autore, non oggetto» (issue #492).

La correzione ammessa durante il freeze e' solo osservativa: questi test
inchiodano l'euristica, il collegamento conservativo a decisioni/trade e il
controfattuale a una seduta senza modificare prompt, gate o segnali live.
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.measure_issuer_as_author import (
    REVERSAL_THRESHOLD,
    calcola_impatto,
    classifica_titolo,
    controfattuali_una_seduta,
    riepilogo_segmenti_prompt,
    stato_validazione_manuale,
    supera_soglia_operativa,
)

ALIASES = {
    "GS": ["Goldman Sachs Group Inc", "Goldman Sachs", "Goldman"],
    "JPM": ["JPMorgan Chase & Co", "JPMorgan Chase", "JPMorgan"],
    "MS": ["Morgan Stanley"],
    "NVDA": ["NVIDIA Corporation", "Nvidia"],
    "AMAT": ["Applied Materials Inc", "Applied Materials"],
}


@pytest.mark.parametrize(
    ("symbol", "title", "claim"),
    [
        (
            "GS",
            "Goldman Sachs warns investors to expect lower returns over the next year",
            "investors to expect lower returns over the next year",
        ),
        (
            "JPM",
            "JPMorgan Says Markets Are 'Extremely Risk-On'",
            "Markets Are 'Extremely Risk-On'",
        ),
        (
            "MS",
            "AI investors may pivot to hyperscalers from chipmakers, Morgan Stanley says",
            "AI investors may pivot to hyperscalers from chipmakers",
        ),
        (
            "NVDA",
            "Nvidia says AI demand will slow",
            "AI demand will slow",
        ),
    ],
)
def test_isola_issuer_che_pubblica_una_view_su_un_oggetto_esterno(symbol, title, claim):
    match = classifica_titolo(title, symbol, ALIASES[symbol])

    assert match is not None
    assert match["complemento"] == claim
    assert match["alias"]
    assert match["verbo"]


def test_accetta_un_analista_dell_emittente_come_autore_della_view():
    match = classifica_titolo(
        "Goldman Top Tech Specialist Sees Spike In Investor Angst",
        "GS",
        ALIASES["GS"],
    )

    assert match is not None
    assert match["verbo"].lower() == "sees"


@pytest.mark.parametrize(
    ("symbol", "title"),
    [
        ("GS", "Goldman Sachs Earnings Are Imminent; Analysts Revise Forecasts"),
        ("GS", "Analysts raise forecasts for Goldman Sachs after Q2 earnings"),
        ("GS", "Goldman Sachs raises its quarterly dividend and earnings outlook"),
        ("AMAT", "Applied Materials CEO Sees Tremendous Visibility Into Its Demand"),
        ("MS", "MS sees record inflows"),  # ticker corto/comune: non e' un alias sicuro
    ],
)
def test_esclude_i_casi_in_cui_issuer_non_e_autore_o_parla_di_se(symbol, title):
    assert classifica_titolo(title, symbol, ALIASES[symbol]) is None


def test_soglia_operativa_e_lunione_di_reversal_e_gate_lungo():
    assert REVERSAL_THRESHOLD == -0.35
    assert supera_soglia_operativa(-0.35, entry_threshold=0.30) == "reversal"
    assert supera_soglia_operativa(0.30, entry_threshold=0.30) == "long_entry"
    assert supera_soglia_operativa(0.12, entry_threshold=0.30) is None


def test_impatto_collega_solo_fk_dirette_e_order_id_di_uscita():
    candidates = [{"signal_id": 9593}, {"signal_id": 100}, {"signal_id": 200}]
    decisions = [
        {"id": 10, "signal_id": 9593, "decision": "SELL", "order_id": "sell-gs"},
        {"id": 20, "signal_id": 100, "decision": "BUY", "order_id": "buy-x"},
        # Stesso score/simbolo ma FK nulla: non va attribuita per somiglianza.
        {"id": 30, "signal_id": None, "decision": "BUY", "order_id": "ambigua"},
    ]
    trades = [
        {
            "id": 259,
            "signal_id": None,
            "decision_id": 999,
            "entry_notional": 680.0,
            "exit_order_id": "sell-gs",
            "exit_order_ids": [],
            "exit_price": 1002.15,
            "qty": 0.645154,
            "exit_time": "2026-09-02T19:07:00+00:00",
            "net_pnl": -34.91728666563865,
        },
        {
            "id": 300,
            "signal_id": 100,
            "decision_id": 20,
            "entry_notional": 500.0,
            "exit_order_id": None,
            "exit_order_ids": [],
            "exit_price": None,
            "qty": 2.0,
            "exit_time": None,
            "net_pnl": None,
        },
    ]

    enriched, summary = calcola_impatto(candidates, decisions, trades)

    by_id = {row["signal_id"]: row for row in enriched}
    assert by_id[9593]["decisioni"][0]["decision"] == "SELL"
    assert by_id[9593]["trade_ids"] == [259]
    assert by_id[9593]["pnl_realizzato_usd"] == pytest.approx(-34.91728666563865)
    assert by_id[100]["trade_ids"] == [300]
    assert by_id[200]["trade_ids"] == []
    assert summary == {
        "candidati_con_decisione_buy_sell": 2,
        "decisioni_buy_sell": 2,
        "trade_collegati": 2,
        "notional_mosso_usd": pytest.approx(500.0 + 1002.15 * 0.645154),
        "pnl_realizzato_usd": pytest.approx(-34.91728666563865),
    }


def test_un_trade_raggiunto_da_piu_link_viene_contato_una_sola_volta():
    candidates = [{"signal_id": 100}]
    decisions = [{"id": 20, "signal_id": 100, "decision": "BUY", "order_id": "buy-x"}]
    trades = [
        {
            "id": 300,
            "signal_id": 100,
            "decision_id": 20,
            "entry_notional": 500.0,
            "exit_order_id": None,
            "exit_order_ids": [],
            "exit_price": 260.0,
            "qty": 2.0,
            "exit_time": "2026-09-03T20:00:00+00:00",
            "net_pnl": 20.0,
        }
    ]

    _, summary = calcola_impatto(candidates, decisions, trades)

    assert summary["trade_collegati"] == 1
    assert summary["pnl_realizzato_usd"] == 20.0
    assert summary["notional_mosso_usd"] == 500.0


def test_controfattuale_usa_close_della_seduta_del_segnale_e_della_successiva():
    candidates = [
        {"signal_id": 1, "symbol": "GS", "generated_at": "2026-09-02T19:01:03+00:00"},
        # Domenica: baseline = prima seduta successiva, forward = quella dopo.
        {"signal_id": 2, "symbol": "NVDA", "generated_at": "2026-09-06T12:00:00+00:00"},
    ]
    closes = {
        "GS": [(date(2026, 9, 2), 1002.15), (date(2026, 9, 3), 1037.36)],
        "NVDA": [
            (date(2026, 9, 4), 180.0),
            (date(2026, 9, 8), 181.0),
            (date(2026, 9, 9), 184.62),
        ],
    }

    result = controfattuali_una_seduta(candidates, closes)

    assert result[1]["seduta_base"] == "2026-09-02"
    assert result[1]["seduta_successiva"] == "2026-09-03"
    assert result[1]["rendimento_1_seduta"] == pytest.approx(1037.36 / 1002.15 - 1)
    assert result[2]["seduta_base"] == "2026-09-08"
    assert result[2]["seduta_successiva"] == "2026-09-09"


def test_validazione_manuale_richiede_almeno_20_candidati_classificati():
    candidates = [{"signal_id": i} for i in range(1, 22)]
    labels = {i: {"classe": i <= 15, "nota": "verifica titolo"} for i in range(1, 21)}

    result = stato_validazione_manuale(candidates, labels, minimum=20)

    assert result["n_classificati"] == 20
    assert result["classe"] == 15
    assert result["non_classe"] == 5
    assert result["precisione_euristica"] == 0.75


def test_validazione_manuale_fallisce_se_il_campione_e_insufficiente():
    with pytest.raises(ValueError, match="almeno 20"):
        stato_validazione_manuale(
            [{"signal_id": i} for i in range(1, 20)],
            {i: {"classe": True, "nota": ""} for i in range(1, 20)},
            minimum=20,
        )


def test_segmenta_variante_a_senza_mescolare_il_caso_gs_col_precedente():
    candidates = [
        {
            "signal_id": 1,
            "segmento_prompt": "pre_variante_a",
            "soglia_operativa_superata": None,
            "classe_validata_manualmente": True,
        },
        {
            "signal_id": 9593,
            "segmento_prompt": "variante_a",
            "soglia_operativa_superata": "reversal",
            "classe_validata_manualmente": True,
        },
    ]
    decisions = [
        {"id": 10, "signal_id": 9593, "decision": "SELL", "order_id": "sell-gs"},
    ]
    trades = [
        {
            "id": 259,
            "signal_id": None,
            "decision_id": 999,
            "entry_notional": 680.0,
            "exit_order_id": "sell-gs",
            "exit_order_ids": [],
            "exit_price": 1002.15,
            "qty": 0.645154,
            "exit_time": "2026-09-02T19:07:00+00:00",
            "net_pnl": -34.92,
        }
    ]

    result = riepilogo_segmenti_prompt(candidates, decisions, trades)

    assert result["pre_variante_a"]["candidati"] == 1
    assert result["pre_variante_a"]["decisioni_buy_sell"] == 0
    assert result["variante_a"]["candidati_sopra_soglia"] == 1
    assert result["variante_a"]["classe_validata"]["pnl_realizzato_usd"] == -34.92
