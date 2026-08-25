"""Metriche del book: ingressi, chiusure, aggregazioni."""

import pytest

from src.analysis.dossier.book import (
    aggregate_by_entry_hour,
    aggregate_contradiction_guard,
    compute_entries,
    compute_exits,
    compute_s4_entry_intents,
)


def _bar(
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
) -> dict[str, float]:
    return {"open": open_, "high": high, "low": low, "close": close}


def test_entry_percentile_misura_dove_si_e_comprato_nel_range():
    """0 = comprato sul minimo del giorno, 1 = sul massimo."""
    trades = [
        {
            "symbol": "AAA",
            "strategia": "S1",
            "ora_utc": "14:07",
            "entry_price": 90.0,
            "qty": 10.0,
        }
    ]
    out = compute_entries(trades, {"AAA": _bar()})
    assert out[0]["entry_percentile"] == pytest.approx(0.0)

    trades[0]["entry_price"] = 110.0
    assert compute_entries(trades, {"AAA": _bar()})[0][
        "entry_percentile"
    ] == pytest.approx(1.0)

    trades[0]["entry_price"] = 100.0
    assert compute_entries(trades, {"AAA": _bar()})[0][
        "entry_percentile"
    ] == pytest.approx(0.5)


def test_caso_reale_f_inseguimento_del_massimo():
    """S1 compro' F a 16.02 il 2026-07-29, range 15.16-16.29, chiusura 15.28."""
    trades = [
        {
            "symbol": "F",
            "strategia": "S1",
            "ora_utc": "14:07",
            "entry_price": 16.02,
            "qty": 100.0,
        }
    ]
    bars = {"F": {"open": 15.55, "high": 16.29, "low": 15.16, "close": 15.28}}
    out = compute_entries(trades, bars)
    assert out[0]["entry_percentile"] == pytest.approx(0.7611, abs=1e-4)
    assert out[0]["mtm_eod"] == pytest.approx(-74.0)


def test_mtm_eod_e_vs_apertura():
    trades = [
        {
            "symbol": "AAA",
            "strategia": "S4",
            "ora_utc": "15:22",
            "entry_price": 102.0,
            "qty": 5.0,
        }
    ]
    out = compute_entries(trades, {"AAA": _bar()})
    assert out[0]["mtm_eod"] == pytest.approx(15.0)  # (105 - 102) * 5
    assert out[0]["vs_apertura"] == pytest.approx(25.0)  # (105 - 100) * 5


def test_range_degenere_da_percentile_none_non_divisione_per_zero():
    trades = [
        {
            "symbol": "AAA",
            "strategia": "S1",
            "ora_utc": "14:07",
            "entry_price": 100.0,
            "qty": 1.0,
        }
    ]
    bars = {"AAA": {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}}
    assert compute_entries(trades, bars)[0]["entry_percentile"] is None


# --- #335: intenti S4 PIT + guardia ombra contraddizione --------------------
# La popolazione e' il ledger degli intenti tradabili #294, non i soli fill.


def _bar_cp(
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
    close_prec: float = 100.0,
) -> dict[str, float]:
    """Barra con chiusura precedente, per le metriche #335 che la richiedono."""
    return {"open": open_, "high": high, "low": low, "close": close,
            "close_prec": close_prec}


def _intent(symbol="WMT", score=0.318, trade_id=None, pnl=None):
    return {
        "intent_id": f"intent-{symbol}",
        "signal_id": 7001,
        "symbol": symbol,
        "signal_at": "2026-08-20T16:36:00+00:00",
        "decision_at": "2026-08-20T16:37:00+00:00",
        "signal_score": score,
        "final_reason_code": "RANK_SELECTED",
        "is_tradable": True,
        "trade_id": trade_id,
        "pnl_realizzato": pnl,
    }


def test_intento_usa_prima_barra_osservabile_non_fill_ne_barra_in_corso():
    bars = {"WMT": [
        {"timestamp": "2026-08-20T16:35:00+00:00", "open": 105.0},
        {"timestamp": "2026-08-20T16:40:00+00:00", "open": 104.25},
    ]}
    out = compute_s4_entry_intents(
        [_intent(trade_id=42, pnl=2.38)], bars, {"WMT": _bar_cp(close_prec=114.0)}
    )[0]

    assert out["prezzo_al_segnale"] == 104.25
    assert out["prezzo_al_segnale_timestamp"] == "2026-08-20T16:40:00+00:00"
    assert out["ritorno_sessione_al_segnale"] == pytest.approx(104.25 / 114.0 - 1)
    assert out["guardia_contraddizione_ombra"] is True


def test_intento_non_eseguito_resta_misurabile_senza_fill():
    bars = {"WMT": [{"timestamp": "2026-08-20T16:40:00+00:00", "open": 104.25}]}
    out = compute_s4_entry_intents(
        [_intent()], bars, {"WMT": _bar_cp(close_prec=114.0)},
        earnings_symbols={"WMT"},
    )[0]

    assert out["trade_id"] is None
    assert out["pnl_realizzato"] is None
    assert out["giorno_di_earnings"] is True
    assert out["guardia_contraddizione_ombra"] is True


def test_intento_espone_missingness_senza_barra_o_close_precedente():
    out = compute_s4_entry_intents([_intent()], {}, {"WMT": _bar()})[0]

    assert out["prezzo_al_segnale"] is None
    assert out["ritorno_sessione_al_segnale"] is None
    assert out["guardia_contraddizione_ombra"] is None
    assert out["missingness"] == {
        "prezzo_al_segnale": "no_observable_bar_at_or_after_signal",
        "ritorno_sessione_al_segnale": "previous_close_missing",
    }


def test_intento_senza_disposition_non_diventa_non_tradabile_per_difetto():
    intent = _intent()
    intent["is_tradable"] = None
    bars = {"WMT": [{"timestamp": "2026-08-20T16:40:00+00:00", "open": 104.25}]}

    out = compute_s4_entry_intents(
        [intent], bars, {"WMT": _bar_cp(close_prec=114.0)}
    )[0]

    assert out["is_tradable"] is None
    assert out["missingness"]["disposition"] == "not_recorded"


def test_guardia_ombra_soglia_configurabile_sugli_intenti():
    bars = {"WMT": [{"timestamp": "2026-08-20T16:40:00+00:00", "open": 97.0}]}
    daily = {"WMT": _bar_cp(close_prec=100.0)}

    assert compute_s4_entry_intents([_intent(score=0.4)], bars, daily)[0][
        "guardia_contraddizione_ombra"
    ] is False
    assert compute_s4_entry_intents(
        [_intent(score=0.4)], bars, daily, soglia_guardia=0.02
    )[0]["guardia_contraddizione_ombra"] is True


def test_aggregato_distingue_eseguiti_non_eseguiti_e_pnl_mancante():
    intents = [
        {"is_tradable": True, "guardia_contraddizione_ombra": True, "trade_id": 42,
         "pnl_realizzato": 2.38},
        {"is_tradable": True, "guardia_contraddizione_ombra": True, "trade_id": 43,
         "pnl_realizzato": None},
        {"is_tradable": True, "guardia_contraddizione_ombra": True, "trade_id": None,
         "pnl_realizzato": None},
        {"is_tradable": True, "guardia_contraddizione_ombra": False, "trade_id": 44,
         "pnl_realizzato": -5.0},
        {"is_tradable": True, "guardia_contraddizione_ombra": None, "trade_id": None,
         "pnl_realizzato": None},
        {"is_tradable": False, "guardia_contraddizione_ombra": True,
         "trade_id": None, "pnl_realizzato": None},
        {"is_tradable": None, "guardia_contraddizione_ombra": True,
         "trade_id": None, "pnl_realizzato": None},
    ]

    out = aggregate_contradiction_guard(intents)

    assert out["n_intenti"] == 7
    assert out["n_intenti_tradabili"] == 5
    assert out["n_intenti_non_tradabili"] == 1
    assert out["n_intenti_disposizione_mancante"] == 1
    assert out["n_valutabili"] == 4
    assert out["n_soppressi"] == 3
    assert out["n_soppressi_eseguiti"] == 2
    assert out["n_soppressi_non_eseguiti"] == 1
    assert out["n_soppressi_con_pnl"] == 1
    assert out["n_soppressi_senza_pnl"] == 1
    assert out["somma_pnl_realizzato_soppressi"] == pytest.approx(2.38)


def test_simbolo_senza_barra_e_saltato_non_inventato():
    trades = [
        {
            "symbol": "ZZZ",
            "strategia": "S1",
            "ora_utc": "14:07",
            "entry_price": 10.0,
            "qty": 1.0,
        }
    ]
    out = compute_entries(trades, {})
    assert out[0]["entry_percentile"] is None
    assert out[0]["mtm_eod"] is None


def test_drift_post_uscita_positivo_significa_soldi_lasciati_sul_tavolo():
    trades = [
        {
            "symbol": "AAA",
            "strategia": "S4",
            "exit_price": 100.0,
            "qty": 10.0,
            "pnl_net": 50.0,
            "exit_reason": "portfolio_sell",
            "ore_tenuta": 3.5,
        }
    ]
    out = compute_exits(trades, {"AAA": 103.0})
    assert out[0]["drift_post_uscita"] == pytest.approx(30.0)


def test_drift_negativo_significa_perdita_evitata():
    trades = [
        {
            "symbol": "AAA",
            "strategia": "S4",
            "exit_price": 100.0,
            "qty": 10.0,
            "pnl_net": 50.0,
            "exit_reason": "stop_loss",
            "ore_tenuta": 3.5,
        }
    ]
    out = compute_exits(trades, {"AAA": 97.0})
    assert out[0]["drift_post_uscita"] == pytest.approx(-30.0)


def test_caso_reale_msft_uscita_sopra_la_chiusura():
    """MSFT 2026-07-30: uscita a 455.56, chiusura 451.55, 2.82 azioni."""
    trades = [
        {
            "symbol": "MSFT",
            "strategia": "S4",
            "exit_price": 455.56,
            "qty": 2.82,
            "pnl_net": 13.03,
            "exit_reason": "portfolio_sell",
            "ore_tenuta": 2.75,
        }
    ]
    out = compute_exits(trades, {"MSFT": 451.55})
    assert out[0]["drift_post_uscita"] == pytest.approx(-11.31, abs=0.01)


def test_senza_prezzo_di_chiusura_drift_none():
    trades = [
        {
            "symbol": "ZZZ",
            "strategia": "S1",
            "exit_price": 10.0,
            "qty": 1.0,
            "pnl_net": 1.0,
            "exit_reason": "portfolio_sell",
            "ore_tenuta": 1.0,
        }
    ]
    assert compute_exits(trades, {})[0]["drift_post_uscita"] is None


def test_aggregazione_per_ora_conta_e_somma():
    chiusi = [
        {"ora_ingresso": 14, "pnl_net": -10.0},
        {"ora_ingresso": 14, "pnl_net": -20.0},
        {"ora_ingresso": 14, "pnl_net": 6.0},
        {"ora_ingresso": 19, "pnl_net": 5.0},
    ]
    out = {r["ora"]: r for r in aggregate_by_entry_hour(chiusi)}
    assert out[14]["n"] == 3
    assert out[14]["win"] == 1
    assert out[14]["somma_pnl"] == pytest.approx(-24.0)
    assert out[14]["media"] == pytest.approx(-8.0)


def test_t_stat_none_sotto_i_due_campioni():
    """Con un solo trade la dev.std non esiste: t_stat None, non zero."""
    out = aggregate_by_entry_hour([{"ora_ingresso": 14, "pnl_net": -10.0}])
    assert out[0]["t_stat"] is None
    assert out[0]["dev_std"] is None


def test_t_stat_none_se_dev_std_nulla():
    """Tutti i valori identici: la dev.std e' zero, il t non e' definito."""
    chiusi = [{"ora_ingresso": 14, "pnl_net": -5.0} for _ in range(3)]
    assert aggregate_by_entry_hour(chiusi)[0]["t_stat"] is None


def test_ordinamento_per_ora_crescente():
    chiusi = [
        {"ora_ingresso": 19, "pnl_net": 1.0},
        {"ora_ingresso": 14, "pnl_net": 1.0},
    ]
    assert [r["ora"] for r in aggregate_by_entry_hour(chiusi)] == [14, 19]


# --- #246 Q4: due campi distinti per la quota di movimento -------------------
# Non sono la stessa grandezza e non vanno mediate: la prima ha per denominatore
# la gamba intraday (close - open), la seconda il movimento close-to-close.


def test_quota_movimento_precedente_al_segnale_su_gamba_intraday():
    """Comprato a meta' della gamba intraday: quota 0,5, denominatore sano."""
    trades = [{"symbol": "AAA", "strategia": "S4", "ora_utc": "17:22",
               "entry_price": 105.0, "qty": 10.0}]
    bars = {"AAA": {"open": 100.0, "high": 112.0, "low": 99.0, "close": 110.0,
                    "close_prec": 98.0}}
    out = compute_entries(trades, bars)[0]
    assert out["quota_movimento_precedente_al_segnale"] == pytest.approx(0.5)
    assert out["denominatore_degenere"] is False


def test_quota_sopra_uno_non_e_clampata():
    """ORCL 08-11 valeva 110,8%: al primo segnale il prezzo aveva gia' superato
    la chiusura. Clampare a 1 cancellerebbe proprio il fatto da misurare."""
    trades = [{"symbol": "ORCL", "strategia": "S4", "ora_utc": "15:00",
               "entry_price": 112.0, "qty": 1.0}]
    bars = {"ORCL": {"open": 100.0, "high": 113.0, "low": 99.0, "close": 110.0,
                     "close_prec": 99.0}}
    out = compute_entries(trades, bars)[0]
    assert out["quota_movimento_precedente_al_segnale"] == pytest.approx(1.2)


def test_denominatore_degenere_quando_la_gamba_intraday_e_piatta():
    """08-12: gamba intraday piatta su 7 mover su 9. La quota esce ancora, ma
    marcata: e' il flag, non l'assenza del numero, a dire che non si legge."""
    trades = [{"symbol": "BBB", "strategia": "S4", "ora_utc": "17:22",
               "entry_price": 100.1, "qty": 1.0}]
    bars = {"BBB": {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2,
                    "close_prec": 95.0}}
    out = compute_entries(trades, bars)[0]
    assert out["denominatore_degenere"] is True
    assert out["quota_movimento_precedente_al_segnale"] is not None


def test_quota_nel_gap_e_una_misura_diversa_con_un_altro_denominatore():
    """(open - close_prec) / (close - close_prec): il 08-12 valeva 99% mediano."""
    trades = [{"symbol": "CCC", "strategia": "S4", "ora_utc": "17:22",
               "entry_price": 100.1, "qty": 1.0}]
    bars = {"CCC": {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2,
                    "close_prec": 95.0}}
    out = compute_entries(trades, bars)[0]
    assert out["quota_nel_gap"] == pytest.approx(5.0 / 5.2)
    # Le due quote restano campi separati con nomi diversi: nessuna media.
    assert out["quota_nel_gap"] != out["quota_movimento_precedente_al_segnale"]


def test_quota_nel_gap_none_senza_chiusura_precedente():
    """Senza close_prec la quota nel gap non esiste: None, non zero, e non
    sostituita dalla quota intraday."""
    trades = [{"symbol": "DDD", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 105.0, "qty": 1.0}]
    out = compute_entries(trades, {"DDD": _bar()})[0]
    assert out["quota_nel_gap"] is None
    assert out["quota_movimento_precedente_al_segnale"] is not None


def test_gamba_intraday_nulla_da_quota_none_e_flag_degenere():
    """close == open: il denominatore e' zero, la quota non esiste."""
    trades = [{"symbol": "EEE", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 100.0, "qty": 1.0}]
    bars = {"EEE": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                    "close_prec": 100.0}}
    out = compute_entries(trades, bars)[0]
    assert out["quota_movimento_precedente_al_segnale"] is None
    assert out["denominatore_degenere"] is True


# --- #246 Q3: t_stat_is_test, n_legacy, scomposizione per sleeve -------------


def test_t_stat_is_test_e_sempre_falso():
    """Il t dell'ora 14 (-4,96) non e' un test: 87 su 129 sono coorte legacy e
    33 vengono da un solo giorno. Il flag lo dice a chi legge il JSON."""
    chiusi = [{"ora_ingresso": 14, "pnl_net": p, "stop_strategy": "S1"}
              for p in (-10.0, -5.0, 3.0)]
    assert all(r["t_stat_is_test"] is False for r in aggregate_by_entry_hour(chiusi))


def test_n_legacy_conta_i_trade_senza_stop_strategy():
    """La coorte F-002 (stop_strategy NULL) va contata, non fusa nelle sleeve."""
    chiusi = (
        [{"ora_ingresso": 14, "pnl_net": -1.0, "stop_strategy": None} for _ in range(87)]
        + [{"ora_ingresso": 14, "pnl_net": -1.0, "stop_strategy": "S1"} for _ in range(27)]
        + [{"ora_ingresso": 14, "pnl_net": -1.0, "stop_strategy": "S4"} for _ in range(15)]
    )
    out = aggregate_by_entry_hour(chiusi)[0]
    assert out["n"] == 129
    assert out["n_legacy"] == 87


def test_scomposizione_per_sleeve_rende_visibile_s1_2_su_27():
    """Il fatto che resta dopo il ridimensionamento: S1 all'ora 14 fa 2 su 27."""
    chiusi = (
        [{"ora_ingresso": 14, "pnl_net": 5.0, "stop_strategy": "S1"} for _ in range(2)]
        + [{"ora_ingresso": 14, "pnl_net": -20.0, "stop_strategy": "S1"} for _ in range(25)]
        + [{"ora_ingresso": 14, "pnl_net": -10.0, "stop_strategy": None} for _ in range(87)]
    )
    per_sleeve = {r["stop_strategy"]: r for r in aggregate_by_entry_hour(chiusi)[0]["per_stop_strategy"]}
    assert per_sleeve["S1"]["n"] == 27
    assert per_sleeve["S1"]["win"] == 2
    # La coorte legacy c'e' ancora, sotto la sua chiave: mai eliminata in silenzio.
    assert per_sleeve[None]["n"] == 87


def test_coorte_legacy_riportata_in_coda_dopo_le_sleeve_attribuite():
    chiusi = [
        {"ora_ingresso": 14, "pnl_net": 1.0, "stop_strategy": None},
        {"ora_ingresso": 14, "pnl_net": 1.0, "stop_strategy": "S4"},
        {"ora_ingresso": 14, "pnl_net": 1.0, "stop_strategy": "S1"},
    ]
    ordine = [r["stop_strategy"] for r in aggregate_by_entry_hour(chiusi)[0]["per_stop_strategy"]]
    assert ordine == ["S1", "S4", None]


def test_trade_senza_stop_strategy_dichiarata_conta_come_legacy():
    """Un input privo del campo (dossier vecchi) e' coorte legacy, non un errore."""
    out = aggregate_by_entry_hour([{"ora_ingresso": 14, "pnl_net": -1.0}])[0]
    assert out["n_legacy"] == 1
    assert out["per_stop_strategy"][0]["stop_strategy"] is None
