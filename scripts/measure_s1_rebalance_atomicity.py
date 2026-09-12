#!/usr/bin/env python3
"""Misura il drift fra decisione e SELL differito dei ribilanciamenti S1 (#468).

Legge soltanto ``portfolio_cycles``, ``execution_decisions`` e ``trades`` e
scarica barre minute IEX adjusted da Alpaca.  Non modifica database, Redis,
configurazione o comportamento di esecuzione.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

DEFAULT_SINCE = datetime(2026, 8, 7, 14, 7, tzinfo=UTC)
DEFAULT_OUTPUT = PROJECT_DIR / "docs" / "evidence" / "s1_rebalance_atomicity.json"
MAX_REFERENCE_STALENESS = timedelta(minutes=5)


def _complete_bar_price(
    closes: pd.DataFrame,
    symbol: str,
    observed_at: datetime,
) -> float | None:
    """Return the last completed minute close available at ``observed_at``."""
    if symbol not in closes.columns or closes.empty:
        return None
    cutoff = pd.Timestamp(observed_at).floor("min")
    series = closes.loc[closes.index < cutoff, symbol].dropna()
    if series.empty:
        return None
    bar_at = pd.Timestamp(series.index[-1])
    if cutoff - bar_at > pd.Timedelta(MAX_REFERENCE_STALENESS):
        return None
    return float(series.iloc[-1])


def measure_exit_drift(
    event: dict[str, Any],
    closes: pd.DataFrame,
) -> dict[str, Any]:
    """Measure signed drift for a seller between target decision and exit.

    Positive dollars mean delaying the SELL obtained a higher reference price;
    negative dollars mean the delay cost money.  Minute bars are only used once
    complete, so the measurement cannot see beyond either cycle timestamp.
    """
    decision_time = event["decision_time"]
    exit_time = event["exit_time"]
    symbol = str(event["symbol"])
    quantity = float(event["quantity"])
    decision_price = _complete_bar_price(closes, symbol, decision_time)
    exit_price = _complete_bar_price(closes, symbol, exit_time)
    measured = {
        **event,
        "decision_time": decision_time.isoformat(),
        "exit_time": exit_time.isoformat(),
        "quantity": quantity,
        "delay_minutes": (exit_time - decision_time).total_seconds() / 60,
        "decision_price": decision_price,
        "exit_price": exit_price,
        "drift_pct": None,
        "drift_usd": None,
        "status": "missing_price",
    }
    if decision_price is None or exit_price is None or decision_price <= 0:
        return measured
    measured.update(
        {
            "drift_pct": exit_price / decision_price - 1.0,
            "drift_usd": (exit_price - decision_price) * quantity,
            "status": "measured",
        }
    )
    return measured


def summarize(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [row for row in measurements if row["status"] == "measured"]
    return {
        "symbols_total": len(measurements),
        "symbols_measured": len(measured),
        "symbols_missing_price": len(measurements) - len(measured),
        "median_delay_minutes": (
            median(float(row["delay_minutes"]) for row in measured)
            if measured
            else None
        ),
        "total_drift_usd": (
            sum(float(row["drift_usd"]) for row in measured)
            if measured
            else None
        ),
    }


def summarize_rebalances(measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in measurements:
        grouped.setdefault(str(row["decision_time"]), []).append(row)
    return [
        {"decision_time": decision_time, **summarize(rows)}
        for decision_time, rows in sorted(grouped.items())
    ]


def _fetch_exit_events(conn: Any, since: datetime) -> list[dict[str, Any]]:
    """Reconstruct the first hysteresis candidate for executed S1 drops.

    Historical portfolio_cycles predate #468's fields.  With the production
    ``exit_persistence_cycles=2`` rule, the first candidate is the immediately
    preceding effective cycle.  Restricting its distance to 10--20 minutes
    admits the scheduled 15-minute pair and rejects gaps or manual runs.
    """
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT ed.symbol,
                   ed.order_id,
                   trade.qty AS quantity,
                   decision_cycle.id AS decision_cycle_id,
                   decision_cycle.timestamp AS decision_time,
                   exit_cycle.id AS exit_cycle_id,
                   exit_cycle.timestamp AS exit_time
            FROM execution_decisions ed
            JOIN LATERAL (
                SELECT pc.id, pc.timestamp
                FROM portfolio_cycles pc
                WHERE pc.timestamp <= ed.tick_time
                ORDER BY pc.timestamp DESC
                LIMIT 1
            ) exit_cycle ON TRUE
            JOIN LATERAL (
                SELECT pc.id, pc.timestamp
                FROM portfolio_cycles pc
                WHERE pc.timestamp < exit_cycle.timestamp
                ORDER BY pc.timestamp DESC
                LIMIT 1
            ) decision_cycle ON TRUE
            JOIN LATERAL (
                SELECT t.qty
                FROM trades t
                WHERE t.exit_order_id = ed.order_id
                   OR ed.order_id = ANY(COALESCE(t.exit_order_ids, ARRAY[]::TEXT[]))
                ORDER BY t.exit_time DESC
                LIMIT 1
            ) trade ON TRUE
            WHERE ed.exit_mechanism = 's1_weight_drop'
              AND ed.order_id IS NOT NULL
              AND ed.tick_time >= %s
              AND exit_cycle.timestamp - decision_cycle.timestamp
                  BETWEEN INTERVAL '10 minutes' AND INTERVAL '20 minutes'
            ORDER BY decision_cycle.timestamp, ed.symbol
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


def _fetch_minute_closes(events: list[dict[str, Any]]) -> pd.DataFrame:
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from src.config import config

    client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
    request = StockBarsRequest(
        symbol_or_symbols=sorted({str(row["symbol"]) for row in events}),
        timeframe=TimeFrame.Minute,
        start=min(row["decision_time"] for row in events) - timedelta(minutes=10),
        end=max(row["exit_time"] for row in events) + timedelta(minutes=5),
        feed=DataFeed.IEX,
        adjustment=Adjustment.ALL,
    )
    raw = client.get_stock_bars(request).df
    if raw.empty:
        raise RuntimeError("Alpaca non ha restituito barre minute IEX")
    return raw.reset_index().pivot(index="timestamp", columns="symbol", values="close")


def _round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    return value


def _print_markdown(measurements: list[dict[str, Any]]) -> None:
    print("| decisione | SELL | simbolo | ritardo | drift % | drift $ |")
    print("|---|---|---|---:|---:|---:|")
    for row in measurements:
        drift_pct = (
            f"{row['drift_pct']:+.3%}" if row["drift_pct"] is not None else "—"
        )
        drift_usd = (
            f"${row['drift_usd']:+.2f}" if row["drift_usd"] is not None else "—"
        )
        print(
            f"| {row['decision_time']} | {row['exit_time']} | {row['symbol']} | "
            f"{row['delay_minutes']:.1f} min | {drift_pct} | {drift_usd} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default=DEFAULT_SINCE.isoformat())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since)

    # The historical pairing below is valid for the live rule that produced
    # these rows.  Read the production helper instead of duplicating its config
    # lookup in the measurement (#169/#467 measurement parity).
    from src.workers.portfolio_scheduler import _get_exit_persistence_cycles

    persistence_cycles = _get_exit_persistence_cycles()
    if persistence_cycles != 2:
        raise RuntimeError(
            "La misura preregistrata richiede exit_persistence_cycles=2; "
            f"il path di produzione restituisce {persistence_cycles}"
        )

    conn = _connect()
    try:
        events = _fetch_exit_events(conn, since)
    finally:
        conn.close()
    if not events:
        raise RuntimeError("Nessun SELL s1_weight_drop con coppia di cicli valida")

    closes = _fetch_minute_closes(events)
    measurements = [measure_exit_drift(event, closes) for event in events]
    generated_at = datetime.now(UTC)
    payload = _round_floats(
        {
            "schema_version": "1.0",
            "issue": 468,
            "generated_at": generated_at.isoformat(),
            "since": since.isoformat(),
            "source": {
                "events": "PostgreSQL portfolio_cycles + execution_decisions + trades",
                "prices": "Alpaca StockBars IEX, Adjustment.ALL, TimeFrame.Minute",
                "production_rule": (
                    "src.workers.portfolio_scheduler._get_exit_persistence_cycles() = "
                    f"{persistence_cycles}"
                ),
            },
            "method": (
                "Per ogni SELL eseguito con exit_mechanism=s1_weight_drop, il ciclo "
                "di decisione storico e' il portfolio_cycle immediatamente precedente, "
                "ammesso solo a distanza 10-20 minuti: e' il primo candidato soppresso "
                "dalla regola di produzione exit_persistence_cycles=2. I prezzi sono i "
                "close delle ultime barre minute complete prima dei due timestamp. Drift "
                "positivo significa che il rinvio ha favorito il venditore."
            ),
            "summary": summarize(measurements),
            "rebalances": summarize_rebalances(measurements),
            "exits": measurements,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    _print_markdown(payload["exits"])
    print()
    print(
        f"Totale: {payload['summary']['symbols_measured']}/"
        f"{payload['summary']['symbols_total']} simboli, "
        f"drift ${payload['summary']['total_drift_usd']:+.2f}."
    )
    print(f"JSON scritto in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
