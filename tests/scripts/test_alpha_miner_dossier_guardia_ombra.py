"""Wiring della guardia ombra contraddizione e di `giorno_di_earnings` nel
dossier (#335). Verifica che ogni entry intent del ledger #294, anche non
eseguito, venga misurato al prezzo PIT del segnale e compaia nell'aggregato
ombra. Misura read-only: nessun ordine cambiato.
"""

from datetime import date, datetime, timezone
from unittest.mock import patch

import scripts.alpha_miner_dossier as dossier

UTC = timezone.utc


def _fake_psql(query):
    """Risponde alle query del book e del ledger degli intenti S4."""
    if "FROM s4_tradable_intent_population" in query:
        # intent_id, signal_id, symbol, model_generated_at, decision_at, score,
        # final_reason_code, is_tradable, trade_id, pnl_net
        return [
            [
                "intent-wmt", "7001", "WMT", "2026-08-20T16:36:00+00:00",
                "2026-08-20T16:37:00+00:00", "0.318", "RANK_SELECTED", "t",
                "42", "2.38",
            ],
            [
                "intent-msft", "7002", "MSFT", "2026-08-20T16:38:00+00:00",
                "2026-08-20T16:52:00+00:00", "0.410", "RANK_SELECTED", "t",
                "", "",
            ],
        ]
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


def test_dossier_misura_tutti_gli_intenti_al_prezzo_pit_del_segnale():
    """Il ledger porta sia WMT eseguito sia MSFT scartato. WMT va misurato a
    104.25 (prima barra dopo le 16:36), non al fill 103.79 della tabella trades."""
    daily = {
        "WMT": {
            "open": 114.0,
            "high": 114.5,
            "low": 103.0,
            "close": 103.98,
            "close_prec": 114.0,
        },
        "MSFT": {
            "open": 100.0,
            "high": 101.0,
            "low": 94.0,
            "close": 95.0,
            "close_prec": 100.0,
        },
        "SPY": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                "close_prec": 100.0},
    }
    intraday = {
        "WMT": [{
            "timestamp": datetime(2026, 8, 20, 16, 40, tzinfo=UTC),
            "open": 104.25, "high": 104.5, "low": 103.0, "close": 103.79,
        }],
        "MSFT": [{
            "timestamp": datetime(2026, 8, 20, 16, 40, tzinfo=UTC),
            "open": 95.0, "high": 95.5, "low": 94.0, "close": 94.5,
        }],
    }
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

    assert len(payload["intenti_ingresso_s4"]) == 2
    wmt, msft = payload["intenti_ingresso_s4"]
    assert wmt["symbol"] == "WMT"
    assert wmt["prezzo_al_segnale"] == 104.25
    assert wmt["prezzo_al_segnale"] != payload["ingressi"][0]["entry_price"]
    assert wmt["prezzo_al_segnale_fonte"] == "alpaca_sip_5min.open"
    assert wmt["ritorno_sessione_al_segnale"] < -0.04
    assert wmt["guardia_contraddizione_ombra"] is True
    assert wmt["trade_id"] == 42
    assert wmt["pnl_realizzato"] == 2.38
    # fetch_remote_context=False -> calendario non disponibile -> UNKNOWN, non False
    assert wmt["giorno_di_earnings"] is None

    assert msft["symbol"] == "MSFT"
    assert msft["trade_id"] is None
    assert msft["pnl_realizzato"] is None
    assert msft["guardia_contraddizione_ombra"] is True

    giorno = payload["aggregati"]["guardia_contraddizione"]["giorno"]
    assert giorno["n_intenti"] == 2
    assert giorno["n_soppressi"] == 2
    assert giorno["n_soppressi_eseguiti"] == 1
    assert giorno["n_soppressi_non_eseguiti"] == 1
    assert giorno["n_soppressi_con_pnl"] == 1
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
