#!/usr/bin/env python3
"""Report riconciliato replacement/opportunity cost del trial exit S4 (#298)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime, timedelta
from uuid import UUID, uuid5

import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import config
from src.strategies.s4.counterfactual import (
    active_policy_hierarchy,
    build_paired_comparison,
    build_portfolio_counterfactual,
    build_replacement_report,
    pairs_for_window,
    replacement_records_for_window,
)
from src.strategies.s4.counterfactual_runtime import (
    build_point_in_time_candidates,
    policy_outcome_from_row,
    scan_freed_slots,
)
from src.strategies.s4.evaluator_bridge import (
    load_evaluation_settings,
    run_evaluation,
)
from src.strategies.s4.p0_baseline import VersionedTradeCostModel

# Il trial ledger (#299, criterio 5): ogni variante valutata su una finestra
# resta registrata, cosi' alla decision analysis la molteplicita' esplorata e'
# ricostruibile invece che affidata alla memoria di chi ha guardato.
_TRIAL_LEDGER_NAMESPACE = UUID("7c3d1e94-8b2f-5a41-9d6c-2e5f8a01b4d7")


def trial_ledger_id(variant: str, start: date, end: date) -> str:
    """Fingerprint di (finestra, variante): rieseguire il report non duplica.

    Il tracciamento e' per variante-vista-su-finestra, non per esecuzione: una
    riesecuzione con gli stessi input non aggiunge molteplicita' esplorata.
    """
    return str(uuid5(_TRIAL_LEDGER_NAMESPACE, f"{variant}|{start}|{end}"))


def _record_trial_ledger(
    entries: Sequence[dict], start: date, end: date
) -> None:
    """Append-only: nessuna riga esistente viene aggiornata o cancellata."""
    if not entries:
        return
    with psycopg2.connect(config.DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            for entry in entries:
                cursor.execute(
                    """
                    INSERT INTO s4_trial_ledger
                        (ledger_id, window_start, window_end, variant,
                         role, notes)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ledger_id) DO NOTHING
                    """,
                    (
                        trial_ledger_id(entry["variant"], start, end),
                        start,
                        end,
                        entry["variant"],
                        entry["role"],
                        list(entry.get("notes") or []),
                    ),
                )
        conn.commit()


# Codici d'uscita. Il report stampa un JSON valido in tutti e tre i casi:
# distinguerli e' l'unico modo perche' un chiamante sappia se la finestra e'
# misurabile senza rileggere il payload — e perche' non confonda "non ancora
# misurabile", che e' lo stato normale della raccolta, con un guasto.
EXIT_RECONCILED = 0
EXIT_NOT_RECONCILED = 1
EXIT_NO_COMPARABLE_PAIRS = 2


def _fetch_policy_rows(start: date, end: date) -> list[dict]:
    with (
        psycopg2.connect(config.DATABASE_URL) as conn,
        conn.cursor(cursor_factory=RealDictCursor) as cursor,
    ):
        cursor.execute(
            """
            SELECT
                intent_id::text AS intent_id, policy_id, symbol, d0,
                initial_notional, entry_cost_usd, exit_cost_usd,
                cost_model_version,
                status, reason_code, trigger_at, filled_at, fill_price,
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


def _fetch_entry_rows(intent_ids: Sequence[str]) -> list[dict]:
    """Il fill d'ingresso condiviso: punto d'ancora del path di prezzo."""
    if not intent_ids:
        return []
    with (
        psycopg2.connect(config.DATABASE_URL) as conn,
        conn.cursor(cursor_factory=RealDictCursor) as cursor,
    ):
        cursor.execute(
            """
            SELECT intent_id::text AS intent_id, filled_at, fill_price,
                   s4_virtual_quantity
            FROM s4_lifecycle_current
            WHERE intent_id IN %s
            """,
            (tuple(intent_ids),),
        )
        return [dict(row) for row in cursor.fetchall()]


def _fetch_quality_bars(
    symbols: Sequence[str], start: datetime, end: datetime
) -> dict[str, list[tuple[datetime, float, float]]]:
    """Barre al minuto con high e close: il path su cui nasce la qualita'."""
    from alpaca.data.enums import Adjustment
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    if not symbols or end <= start:
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
        end=end + timedelta(minutes=1),
        adjustment=Adjustment.ALL,
    )
    payload = client.get_stock_bars(request)
    data = getattr(payload, "data", {}) if payload is not None else {}
    return {
        symbol: [
            (bar.timestamp, float(bar.high), float(bar.close))
            for bar in data.get(symbol, ())
            if getattr(bar, "timestamp", None) is not None
            and getattr(bar, "high", None) is not None
            and getattr(bar, "close", None) is not None
        ]
        for symbol in sorted(set(symbols))
    }


def _cohort_exit_quality(cohort, rows: list[dict]) -> dict[str, object]:
    """Deriva la qualita' dell'uscita per le coppie del verdetto, dal path.

    Ogni metrica che manca resta `None` e resta fuori dalle medie: fill senza
    barre, barre senza fill o intenti ancora aperti non sono un favore, sono
    un ignoto — e il valutatore li dichiara tali.
    """
    from src.strategies.s4.exit_quality import (
        PairedExitPath,
        exit_quality_from_path,
    )

    exits = {(row["intent_id"], row["policy_id"]): row for row in rows}
    entry_rows = _fetch_entry_rows([pair.intent_id for pair in cohort])
    entries = {row["intent_id"]: row for row in entry_rows}

    paths: list[PairedExitPath] = []
    for pair in cohort:
        entry = entries.get(pair.intent_id)
        baseline = exits.get((pair.intent_id, pair.baseline_policy_id))
        challenger = exits.get((pair.intent_id, pair.policy_id))
        if entry is None:
            continue
        paths.append(
            PairedExitPath(
                intent_id=pair.intent_id,
                entry_at=entry.get("filled_at"),
                entry_price=entry.get("fill_price"),
                quantity=float(entry.get("s4_virtual_quantity") or 0.0),
                baseline_exit_at=(baseline or {}).get("filled_at"),
                baseline_exit_price=(baseline or {}).get("fill_price"),
                challenger_exit_at=(challenger or {}).get("filled_at"),
                challenger_exit_price=(challenger or {}).get("fill_price"),
            )
        )

    finestre = [
        (path.entry_at, path.challenger_exit_at)
        for path in paths
        if path.entry_at is not None and path.challenger_exit_at is not None
    ]
    if not finestre:
        return {}
    simboli = {pair.intent_id: pair.symbol for pair in cohort}
    bars = _fetch_quality_bars(
        sorted(set(simboli.values())),
        min(inizio for inizio, _ in finestre),
        max(fine for _, fine in finestre),
    )
    return {
        path.intent_id: exit_quality_from_path(
            path, bars.get(simboli[path.intent_id], ())
        )
        for path in paths
    }


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
    # Criterio 5: il ledger registra tutte le varianti viste, non i soli
    # gradini confirmatory. Una diagnostica guardata fuori da questo script
    # (D+1, D+3, term structure, sottoperiodi) resta molteplicita' esplorata:
    # chi la guarda la dichiara qui, e il ledger append-only la conserva.
    parser.add_argument(
        "--diagnostica-vista",
        action="append",
        default=[],
        dest="diagnostiche_viste",
        metavar="NOME",
        help=(
            "variante diagnostica guardata in questa finestra "
            "(ripetibile); entra nel trial ledger con role=diagnostic"
        ),
    )
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
        return EXIT_NO_COMPARABLE_PAIRS

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

    scan = scan_freed_slots(
        outcomes, baseline_policy_id="P0", policy_id=policy_id
    )
    slots = list(scan.slots)
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
        without_slot=scan.without_slot,
    )
    cohort = pairs_for_window(
        comparison,
        policy_id=policy_id,
        window_start=args.start,
        window_end=args.end,
    )
    payload["paired_records"] = [asdict(pair) for pair in cohort]
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
    # `paired`: la coorte D0 ritagliata, non il confronto intero. Fino a qui il
    # ritaglio era di fatto delegato alla SQL, che filtra sulla stessa
    # finestra; ma il verdetto e' l'unico blocco che diventa una decisione, e
    # non puo' dipendere da un filtro che vive in un'altra funzione.
    settings = load_evaluation_settings()
    payload["evaluation"] = run_evaluation(
        cohort,
        policy_id=policy_id,
        mde_time_bps=settings.mde_time_bps,
        scheme=settings.scheme,
        n_cluster=settings.n_cluster,
        mde_counter_bps=settings.mde_counter_bps,
        exit_quality=_cohort_exit_quality(cohort, rows),
        diagnostics_seen=tuple(args.diagnostiche_viste),
    )
    # Il criterio 5 chiede che il ledger sopravviva alla singola esecuzione:
    # il report gira da cron ogni 6 sedute (check_s4_trial_milestones), quindi
    # la persistenza e' qui, nel punto in cui la variante e' stata vista.
    _record_trial_ledger(payload["evaluation"]["ledger"], args.start, args.end)
    print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))

    # Il criterio e' `comparable`, non `total`: riconciliare zero con zero
    # riesce sempre, quindi `reconciled` non porta informazione su una finestra
    # senza coppie misurabili. Uscire 0 li' significherebbe dire "a posto"
    # proprio quando la metrica primaria non esiste.
    if payload["paired"]["comparable"] == 0:  # type: ignore[index]
        return EXIT_NO_COMPARABLE_PAIRS
    if payload["reconciliation"]["reconciled"]:  # type: ignore[index]
        return EXIT_RECONCILED
    return EXIT_NOT_RECONCILED


if __name__ == "__main__":
    raise SystemExit(main())
