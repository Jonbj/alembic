#!/usr/bin/env python3
"""Misura il gap fra target S1 persistito e posizioni reali del broker (#491).

Lo script e' strettamente osservativo: legge Redis, PostgreSQL e Alpaca paper,
scrive un JSON in ``docs/evidence/`` e stampa la stessa fotografia in Markdown.
Non invia ordini e non modifica alcuno stato remoto.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / "s1_weight_gap.json"
REBALANCE_KEY = "strategy:rebalance_state:S1"


def _sleeve_samples(
    fills: list[dict[str, Any]], target_weights: dict[str, Any]
) -> list[float]:
    ratios: list[float] = []
    for fill in fills:
        try:
            notional = float(fill["entry_notional"])
            # Fonte autorevole: peso sleeve-local salvato nel rebalance state.
            # trades.score e' invece portfolio-level e raddoppiava la sleeve
            # osservata il 2026-09-04 (70.7k invece di 35.3k).
            weight = float(target_weights[str(fill["symbol"])])
        except (KeyError, TypeError, ValueError):
            continue
        if notional > 0 and weight > 0:
            ratios.append(notional / weight)
    return sorted(ratios)


def build_report(
    *,
    as_of: datetime,
    rebalance_state: dict[str, Any],
    rebalance_fills: list[dict[str, Any]],
    broker_positions: dict[str, float],
    open_trade_sleeves: dict[str, str | None],
) -> dict[str, Any]:
    """Costruisce la fotografia da input gia' acquisiti, senza rete."""
    weights = rebalance_state.get("target_weights") or {}
    if not isinstance(weights, dict) or not weights:
        raise ValueError("target_weights S1 assenti o vuoti in Redis")
    last_rebalance = rebalance_state.get("last_rebalance")
    if not last_rebalance:
        raise ValueError("last_rebalance S1 assente in Redis")

    sleeve_samples = _sleeve_samples(rebalance_fills, weights)
    if not sleeve_samples:
        raise ValueError("nessun fill valido per ricavare la sleeve implicita")
    sleeve = float(median(sleeve_samples))
    rows: list[dict[str, Any]] = []
    for symbol, raw_weight in sorted(weights.items()):
        weight = float(raw_weight)
        target = max(0.0, weight * sleeve)
        current = max(0.0, float(broker_positions.get(symbol, 0.0)))
        origin = open_trade_sleeves.get(symbol)
        rows.append(
            {
                "symbol": symbol,
                "target_weight": weight,
                "target_usd": target,
                "current_usd": current,
                "ratio": current / target if target else None,
                # Segno contabile: negativo = capitale mancante rispetto al target.
                "gap_usd": current - target,
                "open_trade_sleeve": origin,
                "covered_by_other_sleeve": bool(origin and origin != "S1"),
            }
        )

    def totals(selected: list[dict[str, Any]]) -> dict[str, float]:
        target = sum(row["target_usd"] for row in selected)
        current = sum(row["current_usd"] for row in selected)
        return {"target_usd": target, "current_usd": current, "gap_usd": current - target}

    exclusive = [row for row in rows if not row["covered_by_other_sleeve"]]
    return {
        "schema_version": 1,
        "as_of": as_of.astimezone(timezone.utc).isoformat(),
        "last_rebalance": str(last_rebalance),
        "sleeve_implicit_usd": sleeve,
        "sleeve_samples_usd": sleeve_samples,
        "rows": rows,
        "totals": {
            "gross": totals(rows),
            "excluding_other_sleeves": totals(exclusive),
        },
    }


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"S1 weight gap al {report['as_of']} (ultimo rebalance {report['last_rebalance']})",
        "",
        "| simbolo | target $ | attuale $ | rapporto | gap $ | sleeve a libro |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        ratio = "n/d" if row["ratio"] is None else f"{row['ratio']:.2f}"
        lines.append(
            f"| {row['symbol']} | {row['target_usd']:.2f} | {row['current_usd']:.2f} "
            f"| {ratio} | {row['gap_usd']:+.2f} | {row['open_trade_sleeve'] or '—'} |"
        )
    gross = report["totals"]["gross"]
    exclusive = report["totals"]["excluding_other_sleeves"]
    lines.extend(
        [
            "",
            f"- Gap grezzo: {gross['gap_usd']:+.2f} USD "
            f"({gross['current_usd']:.2f} / {gross['target_usd']:.2f})",
            f"- Gap senza nomi coperti da altra sleeve: {exclusive['gap_usd']:+.2f} USD "
            f"({exclusive['current_usd']:.2f} / {exclusive['target_usd']:.2f})",
        ]
    )
    return "\n".join(lines)


def _fetch_rebalance_fills(conn: Any, rebalance_at: datetime) -> list[dict[str, Any]]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT symbol, entry_notional
            FROM trades
            WHERE entry_time = %s
              AND stop_strategy = 'S1'
              AND entry_notional IS NOT NULL
            ORDER BY id
            """,
            (rebalance_at,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _fetch_open_trade_sleeves(conn: Any) -> dict[str, str | None]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT symbol, stop_strategy
            FROM trades
            WHERE exit_time IS NULL
            ORDER BY id DESC
            """
        )
        # La prima riga per simbolo e' il trade aperto piu' recente.
        return {symbol: sleeve for symbol, sleeve in reversed(cursor.fetchall())}


def _broker_position_values(client: Any) -> dict[str, float]:
    values: dict[str, float] = {}
    for position in client.get_all_positions():
        value = getattr(position, "market_value", None)
        if value is None:
            value = float(position.qty) * float(position.current_price)
        values[position.symbol] = max(0.0, float(value))
    return values


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _collect(as_of: datetime) -> dict[str, Any]:
    import psycopg2
    from alpaca.trading.client import TradingClient
    from redis import Redis

    from src.config import config

    redis_client = Redis.from_url(config.REDIS_URL, decode_responses=True)
    try:
        raw_state_value = redis_client.get(REBALANCE_KEY)
    finally:
        redis_client.close()
    if not raw_state_value:
        raise RuntimeError(f"chiave Redis assente: {REBALANCE_KEY}")
    raw_state = (
        raw_state_value.decode()
        if isinstance(raw_state_value, bytes)
        else str(raw_state_value)
    )
    state = json.loads(raw_state)
    rebalance_at = _parse_timestamp(state["last_rebalance"])

    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    conn = psycopg2.connect(database_url)
    try:
        fills = _fetch_rebalance_fills(conn, rebalance_at)
        sleeves = _fetch_open_trade_sleeves(conn)
    finally:
        conn.close()

    client = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_PAPER_MODE,
    )
    return build_report(
        as_of=as_of,
        rebalance_state=state,
        rebalance_fills=fills,
        broker_positions=_broker_position_values(client),
        open_trade_sleeves=sleeves,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--at",
        default=datetime.now(timezone.utc).isoformat(),
        help="Istante UTC da associare alla fotografia (default: adesso).",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = _collect(_parse_timestamp(args.at))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(format_markdown(report))
    print(f"\nJSON: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
