#!/usr/bin/env python3
"""Misura la latenza tra il flip negativo S1 e l'uscita mensile (#489).

Legge i trade S1 chiusi da ``s1_weight_drop`` dal database, scarica le stesse
barre IEX adjusted usate dal portfolio scheduler e rigenera lo stesso pannello
cross-sectional S1. Non modifica database, Redis o configurazione.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

DEFAULT_SINCE = date(2026, 7, 1)
MONTHLY_CLOCK_CUTOFF = datetime(2026, 8, 7, 14, 7, tzinfo=UTC)
DEFAULT_OUTPUT = PROJECT_DIR / "docs" / "evidence" / "s1_exit_latency.json"


def _session_date(value: Any) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _symbol_panel(
    symbol: str,
    signals: pd.DataFrame,
    closes: pd.DataFrame,
    entry_time: Any,
    exit_time: Any,
) -> pd.DataFrame:
    if symbol not in signals.columns or symbol not in closes.columns:
        return pd.DataFrame(columns=["signal", "close", "session_date"])
    panel = pd.concat(
        [signals[symbol].rename("signal"), closes[symbol].rename("close")],
        axis=1,
        join="inner",
    ).dropna()
    panel["session_date"] = [_session_date(idx) for idx in panel.index]
    start = _session_date(entry_time)
    end = _session_date(exit_time)
    return panel[(panel["session_date"] >= start) & (panel["session_date"] <= end)]


def _terminal_negative_run(panel: pd.DataFrame) -> pd.DataFrame:
    """Return the negative run still active at exit, or an empty panel."""
    if panel.empty or float(panel.iloc[-1]["signal"]) >= 0:
        return panel.iloc[0:0]
    start = len(panel) - 1
    while start > 0 and float(panel.iloc[start - 1]["signal"]) < 0:
        start -= 1
    return panel.iloc[start:]


def measure_trade_latency(
    trade: dict[str, Any],
    signals: pd.DataFrame,
    closes: pd.DataFrame,
) -> dict[str, Any]:
    """Measure one trade, splitting gross P&L at the terminal negative flip."""
    symbol = str(trade["symbol"])
    panel = _symbol_panel(
        symbol, signals, closes, trade["entry_time"], trade["exit_time"]
    )
    negative_run = _terminal_negative_run(panel)
    reconstructed = (float(trade["exit_price"]) - float(trade["entry_price"])) * float(
        trade["qty"]
    )
    result = {
        "trade_id": int(trade["trade_id"]),
        "symbol": symbol,
        "entry_time": trade["entry_time"].isoformat(),
        "entry_price": float(trade["entry_price"]),
        "exit_time": trade["exit_time"].isoformat(),
        "exit_price": float(trade["exit_price"]),
        "qty": float(trade["qty"]),
        "gross_pnl_db_usd": (
            float(trade["gross_pnl"]) if trade.get("gross_pnl") is not None else None
        ),
        "net_pnl_db_usd": (
            float(trade["net_pnl"]) if trade.get("net_pnl") is not None else None
        ),
        "gross_pnl_reconstructed_usd": reconstructed,
        "flip_date": None,
        "flip_signal_z": None,
        "flip_close": None,
        "delay_sessions": None,
        "pnl_before_flip_usd": None,
        "pnl_after_flip_usd": None,
        "status": "no_negative_flip_at_exit"
        if not panel.empty
        else "missing_signal_or_price_panel",
    }
    if negative_run.empty:
        return result

    flip = negative_run.iloc[0]
    flip_close = float(flip["close"])
    qty = float(trade["qty"])
    result.update(
        {
            "flip_date": flip["session_date"].isoformat(),
            "flip_signal_z": float(flip["signal"]),
            "flip_close": flip_close,
            # Sedute dopo il close che rende osservabile il flip, fino alla
            # seduta dell'uscita inclusa.
            "delay_sessions": max(0, len(negative_run) - 1),
            "pnl_before_flip_usd": (flip_close - float(trade["entry_price"])) * qty,
            "pnl_after_flip_usd": (float(trade["exit_price"]) - flip_close) * qty,
            "status": "measured",
        }
    )
    return result


def summarize(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [row for row in measurements if row["status"] == "measured"]
    delays = [int(row["delay_sessions"]) for row in measured]
    total_pre = sum(float(row["pnl_before_flip_usd"]) for row in measured)
    total_post = sum(float(row["pnl_after_flip_usd"]) for row in measured)
    worst = min(measured, key=lambda row: row["pnl_after_flip_usd"], default=None)
    return {
        "trades_total": len(measurements),
        "trades_with_negative_flip": len(measured),
        "trades_without_negative_flip": len(measurements) - len(measured),
        "median_delay_sessions": median(delays) if delays else None,
        "max_delay_sessions": max(delays) if delays else None,
        "total_pnl_before_flip_usd": total_pre,
        "total_pnl_after_flip_usd": total_post,
        "total_gross_pnl_measured_usd": total_pre + total_post,
        "worst_post_flip_trade": (
            {
                "trade_id": worst["trade_id"],
                "symbol": worst["symbol"],
                "pnl_after_flip_usd": worst["pnl_after_flip_usd"],
                "delay_sessions": worst["delay_sessions"],
            }
            if worst
            else None
        ),
    }


def summaries_by_regime(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep the full history visible while isolating the monthly-clock regime."""
    post_monthly = [
        row
        for row in measurements
        if datetime.fromisoformat(row["exit_time"]) >= MONTHLY_CLOCK_CUTOFF
    ]
    return {
        "full_history": summarize(measurements),
        "post_monthly_clock": {
            "cutoff": MONTHLY_CLOCK_CUTOFF.isoformat(),
            **summarize(post_monthly),
        },
    }


def _fetch_trades(conn: Any, since: date) -> list[dict[str, Any]]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (t.id)
                   t.id AS trade_id,
                   t.symbol,
                   t.entry_time,
                   t.entry_price,
                   t.exit_time,
                   t.exit_price,
                   t.qty,
                   t.gross_pnl,
                   t.net_pnl
            FROM trades t
            JOIN execution_decisions ed
              ON ed.order_id = t.exit_order_id
              OR ed.order_id = ANY(COALESCE(t.exit_order_ids, ARRAY[]::TEXT[]))
            WHERE t.stop_strategy = 'S1'
              AND t.exit_time IS NOT NULL
              AND t.exit_time::date >= %s
              AND ed.exit_mechanism = 's1_weight_drop'
            ORDER BY t.id, ed.tick_time DESC
            """,
            (since,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _connect():
    import psycopg2

    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(database_url)


def _fetch_price_panel(symbols: list[str], end: datetime) -> pd.DataFrame:
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from src.config import config

    client = StockHistoricalDataClient(
        config.ALPACA_API_KEY,
        config.ALPACA_SECRET_KEY,
    )
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=end - timedelta(days=600),
        end=end,
        feed=DataFeed.IEX,
        adjustment=Adjustment.ALL,
    )
    raw = client.get_stock_bars(request).df
    if raw.empty:
        raise RuntimeError("Alpaca non ha restituito barre IEX")
    return raw.reset_index().pivot(index="timestamp", columns="symbol", values="close")


def _signal_panel(closes: pd.DataFrame) -> pd.DataFrame:
    from src.strategies.s1.signal import generate_signals

    generated = generate_signals(closes)
    if generated.empty:
        raise RuntimeError("Il path S1 non ha generato segnali dal pannello Alpaca")
    return generated.pivot(index="as_of", columns="ticker", values="signal")


def _round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    return value


def _print_markdown(
    measurements: list[dict[str, Any]], summaries: dict[str, Any]
) -> None:
    print(
        "| trade | simbolo | flip z<0 | ritardo (sedute) | P&L pre flip | P&L post flip | totale lordo |"
    )
    print("|---:|---|---|---:|---:|---:|---:|")
    for row in measurements:
        flip = row["flip_date"] or "—"
        delay = row["delay_sessions"] if row["delay_sessions"] is not None else "—"
        pre = (
            f"${row['pnl_before_flip_usd']:.2f}"
            if row["pnl_before_flip_usd"] is not None
            else "—"
        )
        post = (
            f"${row['pnl_after_flip_usd']:.2f}"
            if row["pnl_after_flip_usd"] is not None
            else "—"
        )
        print(
            f"| {row['trade_id']} | {row['symbol']} | {flip} | {delay} | "
            f"{pre} | {post} | ${row['gross_pnl_reconstructed_usd']:.2f} |"
        )
    print()
    for label, summary in summaries.items():
        print(
            f"Sintesi {label}: "
            f"{summary['trades_with_negative_flip']}/{summary['trades_total']} trade con flip; "
            f"ritardo mediano {summary['median_delay_sessions']} sedute; "
            f"P&L dopo il flip ${summary['total_pnl_after_flip_usd']:.2f}."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default=DEFAULT_SINCE.isoformat())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    since = date.fromisoformat(args.since)

    conn = _connect()
    try:
        trades = _fetch_trades(conn, since)
    finally:
        conn.close()
    if not trades:
        raise RuntimeError("Nessuna uscita S1 s1_weight_drop nella finestra richiesta")

    from src.config import config

    symbols = sorted(
        set(config.WATCHLIST_SYMBOLS or []) | {row["symbol"] for row in trades}
    )
    generated_at = datetime.now(UTC)
    closes = _fetch_price_panel(symbols, generated_at)
    signals = _signal_panel(closes)
    measurements = [measure_trade_latency(row, signals, closes) for row in trades]
    summaries = summaries_by_regime(measurements)
    payload = _round_floats(
        {
            "schema_version": "1.0",
            "issue": 489,
            "generated_at": generated_at.isoformat(),
            "since": since.isoformat(),
            "source": {
                "trades": "PostgreSQL trades + execution_decisions (S1/s1_weight_drop)",
                "prices": "Alpaca StockBars IEX, Adjustment.ALL, TimeFrame.Day",
                "signal": "src.strategies.s1.signal.generate_signals defaults",
            },
            "method": (
                "Il flip e' l'inizio dell'ultima sequenza signal_z < 0 ancora attiva "
                "all'uscita. Il P&L lordo e' spezzato al close della seduta di flip; "
                "il ritardo conta le sedute successive fino all'uscita inclusa."
            ),
            "summaries": summaries,
            "trades": measurements,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    _print_markdown(payload["trades"], payload["summaries"])
    print(f"\nJSON scritto in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
