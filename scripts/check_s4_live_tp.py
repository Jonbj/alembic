#!/usr/bin/env python3
"""Obbligazione Q7: quanti P0 il TP live avrebbe toccato (contratto §2).

Il TP live e' acceso di default sui soli submit non frazionabili, mentre il
trial congela P0 senza take-profit. Questo comando misura la divergenza e dice
se P0 regge come benchmark operativo. Va rieseguito **a n=0** sul campione
vero: prima di allora il numero e' provvisorio, e il report lo dichiara.

Sul broker soltanto letture: asset (fractionability) e barre storiche.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import config
from src.strategies.s4.live_tp_check import (
    P0Lifecycle,
    PricePath,
    assess_live_tp_exposure,
    assess_universe_perimeter,
    load_live_tp_settings,
)

# Non chiedere ad Alpaca barre piu' recenti di cosi': una barra in formazione
# puo' ancora alzare il massimo.
_FEED_DELAY_MIN = 20


def _fetch_lifecycles(start: date, end: date) -> list[dict]:
    with (
        psycopg2.connect(config.DATABASE_URL) as conn,
        conn.cursor(cursor_factory=RealDictCursor) as cursor,
    ):
        cursor.execute(
            """
            SELECT
                p0.intent_id::text AS intent_id,
                p0.symbol,
                p0.d0,
                p0.comparable,
                p0.status,
                COALESCE(p0.filled_at, p0.trigger_at) AS exit_at,
                lc.fill_price,
                lc.filled_at AS entry_at
            FROM s4_exit_policy_current p0
            JOIN s4_lifecycle_current lc ON lc.intent_id = p0.intent_id
            WHERE p0.policy_id = 'P0'
              AND COALESCE(p0.d0, p0.observed_at::date) BETWEEN %s AND %s
            ORDER BY p0.d0, p0.intent_id
            """,
            (start, end),
        )
        return [dict(row) for row in cursor.fetchall()]


def _fetch_s4_universe() -> list[str]:
    """Simboli mai osservati come candidati S4, non solo quelli entrati."""
    with (
        psycopg2.connect(config.DATABASE_URL) as conn,
        conn.cursor(cursor_factory=RealDictCursor) as cursor,
    ):
        cursor.execute(
            "SELECT DISTINCT symbol FROM s4_intent_events WHERE event_type = 'candidate'"
        )
        return sorted(row["symbol"] for row in cursor.fetchall())


def _fetch_fractionability(symbols: Sequence[str]) -> dict[str, bool]:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    if not symbols:
        return {}
    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti")
    client = TradingClient(
        config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=config.ALPACA_PAPER_MODE
    )
    wanted = set(symbols)
    assets = client.get_all_assets(GetAssetsRequest(status=AssetStatus.ACTIVE))
    return {
        asset.symbol: bool(asset.fractionable)
        for asset in assets
        if asset.symbol in wanted
    }


def _fetch_highs(
    rows: Sequence[dict], now: datetime
) -> dict[str, PricePath]:
    from alpaca.data.enums import Adjustment
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    windows = [
        (row, row["entry_at"], row.get("exit_at") or now)
        for row in rows
        if row.get("entry_at") is not None
    ]
    if not windows:
        return {}
    client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
    start = min(entry for _, entry, _ in windows)
    end = min(
        max(exit_at for _, _, exit_at in windows),
        now - timedelta(minutes=_FEED_DELAY_MIN),
    )
    if end <= start:
        return {}
    payload = client.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=sorted({row["symbol"] for row, _, _ in windows}),
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            adjustment=Adjustment.ALL,
        )
    )
    data = getattr(payload, "data", {}) if payload is not None else {}

    paths: dict[str, PricePath] = {}
    for row, entry_at, exit_at in windows:
        bars = [
            bar
            for bar in data.get(row["symbol"], ())
            if getattr(bar, "timestamp", None) is not None
            and entry_at <= bar.timestamp <= exit_at
            and getattr(bar, "high", None) is not None
        ]
        paths[row["intent_id"]] = PricePath(
            highest_high=max((float(bar.high) for bar in bars), default=None),
            observed_from=entry_at,
            # La finestra osservata si ferma dove si ferma il feed: se e' prima
            # dell'uscita, il modulo lo classifica incompleto invece di
            # concludere che il TP non e' stato toccato.
            observed_to=min(exit_at, end),
        )
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Obbligazione Q7 del contratto trial exit S4."
    )
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    if args.end < args.start:
        parser.error("--end precede --start")

    settings = load_live_tp_settings()
    rows = _fetch_lifecycles(args.start, args.end)
    now = datetime.now(UTC)

    universe = _fetch_s4_universe()
    fractionable = _fetch_fractionability(
        sorted({*universe, *(row["symbol"] for row in rows)})
    )
    paths = _fetch_highs(rows, now)

    lifecycles = [
        P0Lifecycle(
            intent_id=row["intent_id"],
            symbol=row["symbol"],
            d0=row.get("d0"),
            entry_price=float(row.get("fill_price") or 0.0),
            entry_at=row["entry_at"],
            exit_at=row.get("exit_at"),
            fractionable=fractionable.get(row["symbol"]),
            comparable=bool(row.get("comparable")),
        )
        for row in rows
        if row.get("entry_at") is not None
    ]

    report = assess_live_tp_exposure(lifecycles, paths, settings)
    # Il campione dice cosa e' successo; l'universo dice cosa **puo'** succedere.
    # Con un perimetro strutturalmente vuoto la divergenza P0/live non esiste
    # per costruzione, e un campione piccolo non e' piu' un limite.
    report["universe_perimeter"] = assess_universe_perimeter(
        {symbol: fractionable.get(symbol) for symbol in universe}, settings
    )
    report["window_start"] = args.start.isoformat()
    report["window_end"] = args.end.isoformat()
    report["measured_at"] = now.isoformat()
    # Il contratto vuole questa misura prima di n=0, sul campione vero: finche'
    # n=0 non e' fissato il numero e' provvisorio, e dirlo evita che venga
    # citato come se l'obbligazione fosse assolta.
    report["obligation_satisfied"] = False
    report["obligation_note"] = (
        "provvisorio: da rieseguire a n=0 sul campione dichiarato nello snapshot"
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))

    if report["exceeds_threshold"] or report["worst_case_exceeds_threshold"]:
        return 1
    # Un perimetro strutturalmente vuoto e' una risposta valida anche senza
    # campione: nessun ordine S4 puo' ricevere il bracket.
    if report["universe_perimeter"]["perimeter_structurally_empty"]:
        return 0
    if not rows:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
