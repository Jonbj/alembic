"""Metriche del book: ingressi, chiusure, aggregazioni."""
import pytest

from src.analysis.dossier.book import compute_entries


def _bar(open_=100.0, high=110.0, low=90.0, close=105.0):
    return {"open": open_, "high": high, "low": low, "close": close}


def test_entry_percentile_misura_dove_si_e_comprato_nel_range():
    """0 = comprato sul minimo del giorno, 1 = sul massimo."""
    trades = [{"symbol": "AAA", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 90.0, "qty": 10.0}]
    out = compute_entries(trades, {"AAA": _bar()})
    assert out[0]["entry_percentile"] == pytest.approx(0.0)

    trades[0]["entry_price"] = 110.0
    assert compute_entries(trades, {"AAA": _bar()})[0]["entry_percentile"] == pytest.approx(1.0)

    trades[0]["entry_price"] = 100.0
    assert compute_entries(trades, {"AAA": _bar()})[0]["entry_percentile"] == pytest.approx(0.5)


def test_caso_reale_f_inseguimento_del_massimo():
    """S1 compro' F a 16.02 il 2026-07-29, range 15.16-16.29, chiusura 15.28."""
    trades = [{"symbol": "F", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 16.02, "qty": 100.0}]
    bars = {"F": {"open": 15.55, "high": 16.29, "low": 15.16, "close": 15.28}}
    out = compute_entries(trades, bars)
    assert out[0]["entry_percentile"] == pytest.approx(0.7611, abs=1e-4)
    assert out[0]["mtm_eod"] == pytest.approx(-74.0)


def test_mtm_eod_e_vs_apertura():
    trades = [{"symbol": "AAA", "strategia": "S4", "ora_utc": "15:22",
               "entry_price": 102.0, "qty": 5.0}]
    out = compute_entries(trades, {"AAA": _bar()})
    assert out[0]["mtm_eod"] == pytest.approx(15.0)      # (105 - 102) * 5
    assert out[0]["vs_apertura"] == pytest.approx(25.0)  # (105 - 100) * 5


def test_range_degenere_da_percentile_none_non_divisione_per_zero():
    trades = [{"symbol": "AAA", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 100.0, "qty": 1.0}]
    bars = {"AAA": {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}}
    assert compute_entries(trades, bars)[0]["entry_percentile"] is None


def test_simbolo_senza_barra_e_saltato_non_inventato():
    trades = [{"symbol": "ZZZ", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 10.0, "qty": 1.0}]
    out = compute_entries(trades, {})
    assert out[0]["entry_percentile"] is None
    assert out[0]["mtm_eod"] is None


from src.analysis.dossier.book import compute_exits


def test_drift_post_uscita_positivo_significa_soldi_lasciati_sul_tavolo():
    trades = [{"symbol": "AAA", "strategia": "S4", "exit_price": 100.0, "qty": 10.0,
               "pnl_net": 50.0, "exit_reason": "portfolio_sell", "ore_tenuta": 3.5}]
    out = compute_exits(trades, {"AAA": 103.0})
    assert out[0]["drift_post_uscita"] == pytest.approx(30.0)


def test_drift_negativo_significa_perdita_evitata():
    trades = [{"symbol": "AAA", "strategia": "S4", "exit_price": 100.0, "qty": 10.0,
               "pnl_net": 50.0, "exit_reason": "stop_loss", "ore_tenuta": 3.5}]
    out = compute_exits(trades, {"AAA": 97.0})
    assert out[0]["drift_post_uscita"] == pytest.approx(-30.0)


def test_caso_reale_msft_uscita_sopra_la_chiusura():
    """MSFT 2026-07-30: uscita a 455.56, chiusura 451.55, 2.82 azioni."""
    trades = [{"symbol": "MSFT", "strategia": "S4", "exit_price": 455.56, "qty": 2.82,
               "pnl_net": 13.03, "exit_reason": "portfolio_sell", "ore_tenuta": 2.75}]
    out = compute_exits(trades, {"MSFT": 451.55})
    assert out[0]["drift_post_uscita"] == pytest.approx(-11.31, abs=0.01)


def test_senza_prezzo_di_chiusura_drift_none():
    trades = [{"symbol": "ZZZ", "strategia": "S1", "exit_price": 10.0, "qty": 1.0,
               "pnl_net": 1.0, "exit_reason": "portfolio_sell", "ore_tenuta": 1.0}]
    assert compute_exits(trades, {})[0]["drift_post_uscita"] is None


from src.analysis.dossier.book import aggregate_by_entry_hour


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
    chiusi = [{"ora_ingresso": 19, "pnl_net": 1.0}, {"ora_ingresso": 14, "pnl_net": 1.0}]
    assert [r["ora"] for r in aggregate_by_entry_hour(chiusi)] == [14, 19]
