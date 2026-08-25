"""Wiring della guardia ombra contraddizione e di `giorno_di_earnings` nel
dossier (#335). Verifica che lo score LLM (trades.signal_score) e il ritorno
intraday arrivino a `compute_entries` e che l'aggregato ombra compaia in
`aggregati`. Misura read-only: nessun ordine cambiato.
"""

from datetime import date, datetime, timezone
from unittest.mock import patch

import scripts.alpha_miner_dossier as dossier

UTC = timezone.utc


def _fake_psql(query):
    """Risponde solo alle query del book; il resto a lista vuota come il test
    della timeline. 6 colonne per gli ingressi (signal_score incluso)."""
    if "FROM trades WHERE entry_time >=" in query:
        # symbol, strategia, ora, entry_price, qty, signal_score
        return [["WMT", "S4", "16:37", "103.79", "17.95", "0.318"]]
    if "FROM trades WHERE exit_time >=" in query:
        # symbol, strategia, exit_price, qty, net_pnl, exit_reason, ore_tenuta
        return [["WMT", "S4", "103.98", "17.95", "2.38", "sentiment_reversal", "1.0"]]
    if "article_coverage_279" in query:
        return []
    if "FROM sentiment_signals" in query:
        return []
    if "FROM news_log" in query:
        return [["WMT", "1"]]
    return []


def test_dossier_attacha_guardia_ombra_e_aggregato_soppressi():
    """Caso WMT 2026-08-20: score +0.318, titolo gia' sceso ~9% sulla seduta.
    Il dossier marca l'ingresso con la guardia ombra e l'aggregato conta 1
    soppresso con P&L realizzato +$2.38 (stesso turno)."""
    daily = {
        "WMT": {
            "open": 114.0,
            "high": 114.5,
            "low": 103.0,
            "close": 103.98,
            "close_prec": 114.0,
        },
        "SPY": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                "close_prec": 100.0},
    }
    intraday = {"WMT": [{
        "timestamp": datetime(2026, 8, 20, 16, 37, tzinfo=UTC),
        "open": 104.0, "high": 104.5, "low": 103.0, "close": 103.79,
    }]}
    cutoff = datetime(2026, 8, 20, 23, 59, tzinfo=UTC)

    with (
        patch.object(dossier, "_psql", side_effect=_fake_psql),
        patch.object(dossier, "_barre", return_value=daily),
        patch.object(dossier, "_soglia_gate_s4", return_value=0.30),
        patch.object(dossier, "_timeline_eventi", return_value=[], create=True),
        patch.object(
            dossier, "_barre_intraday", return_value=(intraday, cutoff), create=True
        ),
        patch.object(dossier, "_dettagli_ordini", return_value={}, create=True),
    ):
        payload = dossier.costruisci_dossier(date(2026, 8, 20), ["WMT"])

    ingresso = payload["ingressi"][0]
    assert ingresso["symbol"] == "WMT"
    assert ingresso["ritorno_sessione_al_segnale"] is not None
    assert ingresso["ritorno_sessione_al_segnale"] < -0.04
    assert ingresso["guardia_contraddizione_ombra"] is True
    assert ingresso["motivo_guardia_contraddizione"] is not None
    # fetch_remote_context=False -> calendario non disponibile -> UNKNOWN, non False
    assert ingresso["giorno_di_earnings"] is None

    giorno = payload["aggregati"]["guardia_contraddizione"]["giorno"]
    assert giorno["n_soppressi"] == 1
    assert giorno["n_soppressi_con_uscita"] == 1
    assert giorno["somma_pnl_realizzato_soppressi"] == 2.38

    finestra = payload["aggregati"]["guardia_contraddizione"]["finestra_osservazione"]
    assert "n_giorni_coperti" in finestra
    assert "copertura" in finestra


# --- _earnings_symbols_from_calendar: tre forme, UNKNOWN on earnings-failure ---

def test_earnings_symbols_none_se_calendario_none():
    assert dossier._earnings_symbols_from_calendar(None) is None


def test_earnings_symbols_da_dizionario_con_events():
    cal = {
        "events": [
            {"symbol": "WMT", "event_type": "earnings", "event_date": "2026-08-20"},
            {"symbol": "MSFT", "event_type": "dividend", "event_date": "2026-08-20"},
        ],
        "missingness": [],
        "complete": True,
    }
    assert dossier._earnings_symbols_from_calendar(cal) == {"WMT"}


def test_earnings_symbols_none_se_fonte_earnings_fallita():
    """missingness segnala earnings_calendar_unavailable -> UNKNOWN, non vuoto."""
    cal = {
        "events": [{"symbol": "MSFT", "event_type": "dividend"}],
        "missingness": ["earnings_calendar_unavailable"],
        "complete": False,
    }
    assert dossier._earnings_symbols_from_calendar(cal) is None


def test_earnings_symbols_accetta_lista_nuda_di_eventi():
    """I test possono passare una lista (forma tollerata da build_event_context)."""
    cal = [{"symbol": "NVDA", "event_type": "earnings", "event_date": "2026-08-12"}]
    assert dossier._earnings_symbols_from_calendar(cal) == {"NVDA"}