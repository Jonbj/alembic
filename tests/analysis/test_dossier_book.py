"""Metriche del book: ingressi, chiusure, aggregazioni."""

import pytest

from src.analysis.dossier.book import (
    aggregate_by_entry_hour,
    aggregate_contradiction_guard,
    compute_entries,
    compute_exits,
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


# --- #335: ritorno di sessione al segnale + guardia ombra contraddizione -----
# Lo strumento manca all'entry gate (che valuta solo lo score): qui si misura,
# per ogni ingresso, quanto il titolo si era gia' mosso sulla seduta (vs
# chiusura precedente, gap incluso) e se quel movimento contraddice il segno
# dello score. Misura read-only, mai un blocco.


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


def test_ritorno_sessione_al_segnale_e_il_delta_sulla_chiusura_precedente():
    """(entry - close_prec) / close_prec: quanto il titolo si e' mosso sulla
    seduta (gap incluso) fino al segnale. 0 = comprato al livello di ieri."""
    trades = [{"symbol": "AAA", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 90.0, "qty": 10.0}]
    out = compute_entries(trades, {"AAA": _bar_cp()})[0]
    assert out["ritorno_sessione_al_segnale"] == pytest.approx(-0.10)

    trades[0]["entry_price"] = 110.0
    assert compute_entries(trades, {"AAA": _bar_cp()})[0][
        "ritorno_sessione_al_segnale"
    ] == pytest.approx(0.10)

    trades[0]["entry_price"] = 100.0
    assert compute_entries(trades, {"AAA": _bar_cp()})[0][
        "ritorno_sessione_al_segnale"
    ] == pytest.approx(0.0)


def test_ritorno_sessione_e_gap_incluso_non_solo_la_gamba_rth():
    """WMT 2026-08-20: close_prec=114, open=112 (gap down), entry=103.79.
    Il ritorno di sessione (~-9%) cattura il crollo; il solo delta su open
    (~-7%) sottostima. La misura giusta per la guardia e' vs close_prec."""
    trades = [{"symbol": "WMT", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 103.79, "qty": 1.0}]
    bars = {"WMT": {"open": 112.0, "high": 112.5, "low": 103.0,
                    "close": 104.0, "close_prec": 114.0}}
    out = compute_entries(trades, bars)[0]
    assert out["ritorno_sessione_al_segnale"] == pytest.approx(-0.0896, abs=1e-3)
    # (entry - open)/open sarebbe -7.3%: conferma che vs-open sottostima.
    assert (103.79 - 112.0) / 112.0 == pytest.approx(-0.0733, abs=1e-3)


def test_ritorno_sessione_none_senza_barra_o_close_prec():
    """Senza barra, o senza close_prec, il ritorno non si calcola: None, non zero."""
    trades = [{"symbol": "ZZZ", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 10.0, "qty": 1.0}]
    assert compute_entries(trades, {})[0]["ritorno_sessione_al_segnale"] is None

    # close_prec mancante (barra senza storico): None, non sostituito con vs-open.
    bars = {"ZZZ": {"open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5}}
    assert compute_entries(trades, bars)[0]["ritorno_sessione_al_segnale"] is None

    bars["ZZZ"]["close_prec"] = 0.0
    assert compute_entries(trades, bars)[0]["ritorno_sessione_al_segnale"] is None


def test_giorno_di_earnings_true_se_il_simbolo_e_in_calendario():
    """Il simbolo ha un rilascio earnings datato la seduta: True."""
    trades = [{"symbol": "WMT", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 103.79, "qty": 17.95}]
    out = compute_entries(
        trades, {"WMT": _bar()}, earnings_symbols={"WMT", "NVDA"}
    )[0]
    assert out["giorno_di_earnings"] is True


def test_giorno_di_earnings_false_se_il_simbolo_non_e_in_calendario():
    """Il simbolo non ha earnings quel giorno, ma il calendario e' disponibile:
    False (asserito, non sconosciuto)."""
    trades = [{"symbol": "MSFT", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 100.0, "qty": 1.0}]
    out = compute_entries(
        trades, {"MSFT": _bar()}, earnings_symbols={"WMT"}
    )[0]
    assert out["giorno_di_earnings"] is False


def test_giorno_di_earnings_none_se_il_calendario_non_disponibile():
    """Senza calendario (fetch remote off / FMP down) lo stato e' UNKNOWN:
    None, mai False impostato per difetto — il dossier non imputa zero."""
    trades = [{"symbol": "WMT", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 100.0, "qty": 1.0}]
    out = compute_entries(trades, {"WMT": _bar()})[0]  # earnings_symbols omesso
    assert out["giorno_di_earnings"] is None


def test_guardia_ombra_scatta_su_score_positivo_e_titolo_gia_crollato():
    """Caso WMT 2026-08-20: score +0.318 (sopra il gate 0.30) ma il titolo e'
    gia' sceso ~9% sulla seduta. La guardia ombra segna la contraddizione."""
    trades = [{"symbol": "WMT", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 103.79, "qty": 17.95, "signal_score": 0.318}]
    bars = {"WMT": {"open": 112.0, "high": 112.5, "low": 103.0,
                    "close": 104.0, "close_prec": 114.0}}
    out = compute_entries(trades, bars)[0]
    assert out["guardia_contraddizione_ombra"] is True
    assert out["ritorno_sessione_al_segnale"] == pytest.approx(-0.0896, abs=1e-3)
    assert out["motivo_guardia_contraddizione"] is not None
    assert "0.318" in out["motivo_guardia_contraddizione"]


def test_guardia_ombra_false_su_score_positivo_e_titolo_su():
    """Score positivo, titolo in risalita: nessuna contraddizione, non scatta."""
    trades = [{"symbol": "AAA", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 105.0, "qty": 1.0, "signal_score": 0.35}]
    out = compute_entries(trades, {"AAA": _bar_cp()})[0]  # entry 105, close_prec 100 -> +5%
    assert out["guardia_contraddizione_ombra"] is False
    assert out["motivo_guardia_contraddizione"] is None


def test_guardia_ombra_false_su_score_negativo_anche_se_titolo_giù():
    """Score negativo su un titolo in calo e' coerente (long-only non entrerebbe
    comunque): non e' una contraddizione, la guardia resta False."""
    trades = [{"symbol": "AAA", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 90.0, "qty": 1.0, "signal_score": -0.5}]
    out = compute_entries(trades, {"AAA": _bar_cp()})[0]  # entry 90, close_prec 100 -> -10%
    assert out["guardia_contraddizione_ombra"] is False


def test_guardia_ombra_none_senza_score_o_senza_close_prec():
    """Score mancante (trade legacy) o close_prec mancante: non decidibile,
    None — mai False imputato per difetto."""
    trades_no_score = [{"symbol": "AAA", "strategia": "S1", "ora_utc": "14:07",
                        "entry_price": 90.0, "qty": 1.0}]
    assert compute_entries(trades_no_score, {"AAA": _bar_cp()})[0][
        "guardia_contraddizione_ombra"
    ] is None

    # close_prec mancante: il ritorno e' None, quindi la guardia e' None anche
    # con score presente.
    trades_no_cp = [{"symbol": "ZZZ", "strategia": "S4", "ora_utc": "16:37",
                     "entry_price": 90.0, "qty": 1.0, "signal_score": 0.318}]
    bars = {"ZZZ": {"open": 100.0, "high": 101.0, "low": 89.0, "close": 95.0}}
    assert compute_entries(trades_no_cp, bars)[0][
        "guardia_contraddizione_ombra"
    ] is None


def test_guardia_ombra_soglia_configurabile():
    """La soglia e' uno strumento di misura (non taratura di strategia):
    sollevarla a -2% fa scattare la guardia anche su un calo del 3%."""
    trades = [{"symbol": "AAA", "strategia": "S4", "ora_utc": "16:37",
               "entry_price": 97.0, "qty": 1.0, "signal_score": 0.40}]
    bars = {"AAA": {"open": 99.0, "high": 101.0, "low": 96.0,
                    "close": 98.0, "close_prec": 100.0}}
    # ritorno di sessione = (97 - 100)/100 = -3%: sotto -4% no, sotto -2% si'
    assert compute_entries(trades, bars)[0]["guardia_contraddizione_ombra"] is False
    assert compute_entries(trades, bars, soglia_guardia=0.02)[0][
        "guardia_contraddizione_ombra"
    ] is True


def test_aggregate_guardia_conta_i_soppressi_e_somma_il_pnl_stesso_turno():
    """WMT 2026-08-20: ingresso soppresso dalla guardia, uscita stesso turno con
    pnl +$2.38. L'aggregato conta 1 soppresso e somma il suo P&L realizzato."""
    ingressi = [
        {"symbol": "WMT", "strategia": "S4", "guardia_contraddizione_ombra": True},
        {"symbol": "MSFT", "strategia": "S4", "guardia_contraddizione_ombra": False},
    ]
    chiusure = [
        {"symbol": "WMT", "strategia": "S4", "pnl_net": 2.38},
    ]
    out = aggregate_contradiction_guard(ingressi, chiusure)
    assert out["n_valutabili"] == 2
    assert out["n_soppressi"] == 1
    assert out["n_soppressi_con_uscita"] == 1
    assert out["n_soppressi_aperti"] == 0
    assert out["somma_pnl_realizzato_soppressi"] == pytest.approx(2.38)


def test_aggregate_guardia_soppresso_senza_uscita_resti_aperto():
    """Un ingresso soppresso senza chiusura nello stesso turno resta aperto:
    non imputiamo P&L zero, lo contiamo a parte."""
    ingressi = [{"symbol": "AAA", "strategia": "S4",
                 "guardia_contraddizione_ombra": True}]
    out = aggregate_contradiction_guard(ingressi, [])
    assert out["n_soppressi"] == 1
    assert out["n_soppressi_con_uscita"] == 0
    assert out["n_soppressi_aperti"] == 1
    assert out["somma_pnl_realizzato_soppressi"] == pytest.approx(0.0)


def test_aggregate_guardia_ignora_guardie_non_decidibili():
    """Ingressi con guardia None (score/ritorno mancanti) non sono valutabili:
    non entrano nel conteggio dei soppressi ne' dei valutabili."""
    ingressi = [
        {"symbol": "X", "strategia": "S4", "guardia_contraddizione_ombra": None},
        {"symbol": "Y", "strategia": "S4", "guardia_contraddizione_ombra": True},
    ]
    out = aggregate_contradiction_guard(ingressi, [])
    assert out["n_valutabili"] == 1
    assert out["n_soppressi"] == 1


def test_aggregate_guardia_accoppia_fifo_per_symbol_e_strategia():
    """Due ingressi soppressi sullo stesso simbolo+strategia, due uscite: il
    matching FIFO assegna ogni uscita al ingresso corrispondente in ordine."""
    ingressi = [
        {"symbol": "AAA", "strategia": "S4", "guardia_contraddizione_ombra": True},
        {"symbol": "AAA", "strategia": "S4", "guardia_contraddizione_ombra": True},
        {"symbol": "AAA", "strategia": "S4", "guardia_contraddizione_ombra": False},
    ]
    chiusure = [
        {"symbol": "AAA", "strategia": "S4", "pnl_net": -5.0},
        {"symbol": "AAA", "strategia": "S4", "pnl_net": 3.0},
    ]
    out = aggregate_contradiction_guard(ingressi, chiusure)
    assert out["n_soppressi"] == 2
    assert out["n_soppressi_con_uscita"] == 2
    assert out["somma_pnl_realizzato_soppressi"] == pytest.approx(-2.0)


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
