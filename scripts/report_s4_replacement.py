#!/usr/bin/env python3
"""Report riconciliato replacement/opportunity cost del trial exit S4 (#298)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import config
from src.strategies.s4.counterfactual import (
    active_policy_hierarchy,
    build_paired_comparison,
    build_portfolio_counterfactual,
    build_replacement_report,
    replacement_records_for_window,
)
from src.strategies.s4.counterfactual_runtime import (
    build_freed_slots,
    build_point_in_time_candidates,
    policy_outcome_from_row,
)
from src.strategies.s4.evaluator_bridge import (
    load_evaluation_settings,
    run_evaluation,
)
from src.strategies.s4.p0_baseline import VersionedTradeCostModel


def _fetch_policy_rows(start: date, end: date) -> list[dict]:
    with (
        psycopg2.connect(config.DATABASE_URL) as conn,
        conn.cursor(cursor_factory=RealDictCursor) as cursor,
    ):
        cursor.execute(
            """
            SELECT
                intent_id::text AS intent_id, policy_id, symbol, d0,
                initial_notional, status, reason_code, trigger_at, filled_at,
                virtual_exit_quantity, net_pnl, comparable, details
            FROM s4_exit_policy_current
            WHERE policy_id IN ('P0', 'P1')
              AND COALESCE(d0, observed_at::date) BETWEEN %s AND %s
            ORDER BY intent_id, policy_id
            """,
            (start, end),
        )
        return [dict(row) for row in cursor.fetchall()]


def _fetch_intent_rows(until: datetime) -> list[dict]:
    """Disposition fino al cutoff; il filtro PIT finale resta nel dominio."""
    with (
        psycopg2.connect(config.DATABASE_URL) as conn,
        conn.cursor(cursor_factory=RealDictCursor) as cursor,
    ):
        cursor.execute(
            """
            SELECT
                intent_id::text AS intent_id, symbol, signal_id, rank,
                occurred_at, decision_slot, decision_at, is_tradable,
                reason_code, s1_state, anti_pyramiding
            FROM s4_intent_events
            WHERE event_type = 'disposition'
              AND occurred_at <= %s
              AND decision_at <= %s
            ORDER BY decision_slot, rank NULLS LAST, symbol, intent_id
            """,
            (until, until),
        )
        return [dict(row) for row in cursor.fetchall()]


def _fetch_session_dates(start: date, end: date) -> list[date]:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetCalendarRequest

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti")
    client = TradingClient(
        config.ALPACA_API_KEY,
        config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_PAPER_MODE,
    )
    rows = client.get_calendar(GetCalendarRequest(start=start, end=end))
    dates: list[date] = []
    for row in rows:
        if isinstance(row, str):
            raise RuntimeError(f"Alpaca calendar returned an error: {row}")
        dates.append(row.date)
    return dates


def _fetch_candidate_bars(
    symbols: Sequence[str], start: datetime, end: datetime
) -> dict[str, list[tuple[datetime, float]]]:
    from alpaca.data.enums import Adjustment
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    if not symbols:
        return {}
    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti")
    client = StockHistoricalDataClient(
        config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY
    )
    request = StockBarsRequest(
        symbol_or_symbols=sorted(set(symbols)),
        timeframe=TimeFrame.Minute,
        start=start,
        # Alpaca tratta ``end`` come esclusivo; un minuto include la barra al
        # confine senza osservare alcun prezzo successivo nel calcolo.
        end=end + timedelta(minutes=1),
        adjustment=Adjustment.ALL,
    )
    payload = client.get_stock_bars(request)
    data = getattr(payload, "data", {}) if payload is not None else {}
    return {
        symbol: [
            (bar.timestamp, float(bar.close))
            for bar in data.get(symbol, ())
            if getattr(bar, "timestamp", None) is not None
            and getattr(bar, "close", None) is not None
        ]
        for symbol in sorted(set(symbols))
    }


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _empty_report(start: date, end: date, policy_id: str) -> dict[str, object]:
    comparison = build_paired_comparison(
        [],
        [],
        active_policies=active_policy_hierarchy(),
    )
    payload = build_replacement_report(
        comparison,
        (),
        policy_id=policy_id,
        window_start=start,
        window_end=end,
    )
    payload["paired_records"] = []
    payload["evaluation"] = run_evaluation(
        (),
        policy_id=policy_id,
        mde_time_bps=load_evaluation_settings().mde_time_bps,
        scheme=load_evaluation_settings().scheme,
        n_cluster=load_evaluation_settings().n_cluster,
    )
    payload["replacement_records"] = []
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Misura replacement e opportunity cost P1-P0 del trial exit S4."
    )
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    if args.end < args.start:
        parser.error("--end precede --start")

    policy_id = "P1"
    rows = _fetch_policy_rows(args.start, args.end)
    if not rows:
        print(
            json.dumps(
                _empty_report(args.start, args.end, policy_id),
                indent=2,
                sort_keys=True,
                default=_json_default,
            )
        )
        return 2

    outcomes = [policy_outcome_from_row(row) for row in rows]
    hierarchy = active_policy_hierarchy()
    baseline = [outcome for outcome in outcomes if outcome.policy_id == "P0"]
    challengers = [outcome for outcome in outcomes if outcome.policy_id != "P0"]

    observed_dates = [
        outcome.d0 for outcome in outcomes if outcome.d0 is not None
    ] + [
        outcome.exit_at.date()
        for outcome in outcomes
        if outcome.exit_at is not None
    ]
    session_start = min(observed_dates, default=args.start)
    session_end = max(observed_dates, default=args.end)
    sessions = _fetch_session_dates(session_start, session_end)
    comparison = build_paired_comparison(
        baseline,
        challengers,
        active_policies=hierarchy,
        sessions=sessions,
    )

    slots = build_freed_slots(
        outcomes, baseline_policy_id="P0", policy_id=policy_id
    )
    if slots:
        intent_rows = _fetch_intent_rows(max(slot.freed_at for slot in slots))
        unpriced = build_point_in_time_candidates(slots, intent_rows, {})
        symbols = [
            candidate.symbol
            for candidates in unpriced.values()
            for candidate in candidates
        ]
        bars = _fetch_candidate_bars(
            symbols,
            min(slot.freed_at for slot in slots),
            max(slot.slot_closes_at for slot in slots),
        )
        candidates = build_point_in_time_candidates(slots, intent_rows, bars)
    else:
        candidates = {}
    records = build_portfolio_counterfactual(
        slots,
        candidates,
        sessions=sessions,
        cost_model=VersionedTradeCostModel(),
    )
    payload = build_replacement_report(
        comparison,
        records,
        policy_id=policy_id,
        window_start=args.start,
        window_end=args.end,
    )
    payload["paired_records"] = [
        asdict(pair)
        for pair in comparison.pairs
        if pair.policy_id == policy_id
        and pair.d0 is not None
        and args.start <= pair.d0 <= args.end
    ]
    payload["replacement_records"] = [
        asdict(record)
        for record in replacement_records_for_window(
            comparison,
            records,
            policy_id=policy_id,
            window_start=args.start,
            window_end=args.end,
        )
    ]
    # Il valutatore confirmatory (#299) legge le stesse coppie del blocco
    # `paired`: una sola sorgente, cosi' il verdetto non puo' divergere dalla
    # misura pubblicata sopra.
    settings = load_evaluation_settings()
    payload["evaluation"] = run_evaluation(
        comparison.pairs,
        policy_id=policy_id,
        mde_time_bps=settings.mde_time_bps,
        scheme=settings.scheme,
        n_cluster=settings.n_cluster,
        mde_counter_bps=settings.mde_counter_bps,
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))

    # Il criterio e' `comparable`, non `total`: riconciliare zero con zero
    # riesce sempre, quindi `reconciled` non porta informazione su una finestra
    # senza coppie misurabili. Uscire 0 li' significherebbe dire "a posto"
    # proprio quando la metrica primaria non esiste.
    if payload["paired"]["comparable"] == 0:  # type: ignore[index]
        return 2
    return 0 if payload["reconciliation"]["reconciled"] else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
