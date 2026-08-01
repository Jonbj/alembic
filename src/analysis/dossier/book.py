"""Metriche del nostro book per il dossier.

Modulo puro: riceve trade e barre gia' caricati, non tocca rete ne' DB.
"""

from __future__ import annotations

import statistics
from typing import TypedDict


class EntryTrade(TypedDict):
    """Campi di un ingresso necessari alle metriche del dossier."""

    symbol: str
    strategia: str
    ora_utc: str
    entry_price: float
    qty: float


class DailyBar(TypedDict):
    """Barra giornaliera OHLC usata per misurare un ingresso."""

    open: float
    high: float
    low: float
    close: float


class EntryMetrics(EntryTrade):
    """Ingresso arricchito con metriche provvisorie di fine giornata."""

    entry_percentile: float | None
    mtm_eod: float | None
    vs_apertura: float | None


class ExitTrade(TypedDict):
    """Campi di una chiusura necessari alle metriche del dossier."""

    symbol: str
    strategia: str
    exit_price: float
    qty: float
    pnl_net: float
    exit_reason: str
    ore_tenuta: float


class ExitMetrics(ExitTrade):
    """Chiusura arricchita con il drift successivo all'uscita."""

    drift_post_uscita: float | None


class ClosedTradeForHour(TypedDict):
    """Campi minimi per aggregare il P&L per ora di ingresso."""

    ora_ingresso: int
    pnl_net: float


class EntryHourAggregate(TypedDict):
    """Statistiche descrittive dei trade entrati nella stessa ora UTC."""

    ora: int
    n: int
    win: int
    somma_pnl: float
    media: float
    dev_std: float | None
    t_stat: float | None


def compute_entries(
    trades: list[EntryTrade], bars: dict[str, DailyBar]
) -> list[EntryMetrics]:
    """Metriche degli ingressi del giorno, con esito PROVVISORIO di fine giornata.

    Attenzione a come si legge: su un book dove la posizione media dura 14 giorni,
    il mark-to-market di fine giornata NON e' un giudizio sulla decisione. Serve a
    rendere visibile un pattern aggregato, non a condannare il singolo trade.

    entry_percentile e' la misura dell'inseguimento: 0 = comprato sul minimo del
    giorno, 1 = sul massimo. None se il range e' degenere o la barra manca.
    """
    result: list[EntryMetrics] = []
    for trade in trades:
        bar = bars.get(trade["symbol"])
        row: EntryMetrics = {
            "symbol": trade["symbol"],
            "strategia": trade["strategia"],
            "ora_utc": trade["ora_utc"],
            "entry_price": trade["entry_price"],
            "qty": trade["qty"],
            "entry_percentile": None,
            "mtm_eod": None,
            "vs_apertura": None,
        }
        if bar is not None:
            rng = bar["high"] - bar["low"]
            if rng > 0:
                row["entry_percentile"] = (trade["entry_price"] - bar["low"]) / rng
            row["mtm_eod"] = (bar["close"] - trade["entry_price"]) * trade["qty"]
            row["vs_apertura"] = (bar["close"] - bar["open"]) * trade["qty"]
        result.append(row)
    return result


def compute_exits(
    trades: list[ExitTrade], closes: dict[str, float]
) -> list[ExitMetrics]:
    """Metriche delle posizioni chiuse: qui il verdetto e' legittimo, l'esito e' completo.

    drift_post_uscita positivo = soldi lasciati sul tavolo (il titolo e' salito dopo
    che siamo usciti); negativo = perdita evitata. Se la mediana mobile e' stabilmente
    positiva, usciamo troppo presto — ed e' misurabile, a differenza di un miss.
    """
    result: list[ExitMetrics] = []
    for trade in trades:
        close = closes.get(trade["symbol"])
        result.append(
            {
                "symbol": trade["symbol"],
                "strategia": trade["strategia"],
                "exit_price": trade["exit_price"],
                "qty": trade["qty"],
                "pnl_net": trade["pnl_net"],
                "exit_reason": trade["exit_reason"],
                "ore_tenuta": trade["ore_tenuta"],
                "drift_post_uscita": (
                    None
                    if close is None
                    else (close - trade["exit_price"]) * trade["qty"]
                ),
            }
        )
    return result


def aggregate_by_entry_hour(
    chiusi: list[ClosedTradeForHour],
) -> list[EntryHourAggregate]:
    """Raggruppa i trade chiusi per ora UTC di ingresso.

    ATTENZIONE ALLA LETTURA: e' un'analisi post-hoc su molti bucket orari. Un t_stat
    marginale qui NON e' una scoperta: con ~8 bucket, una correzione per confronti
    multipli lo annulla. Il campo esiste per ordinare le ipotesi, non per dichiararle
    vere. Chi consuma questo dato deve riportare anche la numerosita'.
    """
    per_ora: dict[int, list[float]] = {}
    for trade in chiusi:
        per_ora.setdefault(trade["ora_ingresso"], []).append(trade["pnl_net"])

    result: list[EntryHourAggregate] = []
    for ora in sorted(per_ora):
        pnl_values = per_ora[ora]
        sample_size = len(pnl_values)
        mean = sum(pnl_values) / sample_size
        std_dev = statistics.stdev(pnl_values) if sample_size >= 2 else None
        t_stat = (mean / (std_dev / (sample_size**0.5))) if std_dev else None
        result.append(
            {
                "ora": ora,
                "n": sample_size,
                "win": sum(1 for pnl in pnl_values if pnl > 0),
                "somma_pnl": sum(pnl_values),
                "media": mean,
                "dev_std": std_dev,
                "t_stat": t_stat,
            }
        )
    return result
