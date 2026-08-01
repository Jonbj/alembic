"""Metriche del nostro book per il dossier.

Modulo puro: riceve trade e barre gia' caricati, non tocca rete ne' DB.
"""
from __future__ import annotations

import statistics


def compute_entries(trades: list[dict], bars: dict[str, dict]) -> list[dict]:
    """Metriche degli ingressi del giorno, con esito PROVVISORIO di fine giornata.

    Attenzione a come si legge: su un book dove la posizione media dura 14 giorni,
    il mark-to-market di fine giornata NON e' un giudizio sulla decisione. Serve a
    rendere visibile un pattern aggregato, non a condannare il singolo trade.

    entry_percentile e' la misura dell'inseguimento: 0 = comprato sul minimo del
    giorno, 1 = sul massimo. None se il range e' degenere o la barra manca.
    """
    out = []
    for t in trades:
        bar = bars.get(t["symbol"])
        riga = {
            "symbol": t["symbol"],
            "strategia": t["strategia"],
            "ora_utc": t["ora_utc"],
            "entry_price": t["entry_price"],
            "qty": t["qty"],
            "entry_percentile": None,
            "mtm_eod": None,
            "vs_apertura": None,
        }
        if bar is not None:
            rng = bar["high"] - bar["low"]
            if rng > 0:
                riga["entry_percentile"] = (t["entry_price"] - bar["low"]) / rng
            riga["mtm_eod"] = (bar["close"] - t["entry_price"]) * t["qty"]
            riga["vs_apertura"] = (bar["close"] - bar["open"]) * t["qty"]
        out.append(riga)
    return out


def compute_exits(trades: list[dict], closes: dict[str, float]) -> list[dict]:
    """Metriche delle posizioni chiuse: qui il verdetto e' legittimo, l'esito e' completo.

    drift_post_uscita positivo = soldi lasciati sul tavolo (il titolo e' salito dopo
    che siamo usciti); negativo = perdita evitata. Se la mediana mobile e' stabilmente
    positiva, usciamo troppo presto — ed e' misurabile, a differenza di un miss.
    """
    out = []
    for t in trades:
        close = closes.get(t["symbol"])
        out.append({
            "symbol": t["symbol"],
            "strategia": t["strategia"],
            "exit_price": t["exit_price"],
            "qty": t["qty"],
            "pnl_net": t["pnl_net"],
            "exit_reason": t["exit_reason"],
            "ore_tenuta": t["ore_tenuta"],
            "drift_post_uscita": (
                None if close is None else (close - t["exit_price"]) * t["qty"]
            ),
        })
    return out
