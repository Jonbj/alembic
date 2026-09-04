#!/usr/bin/env python3
"""Misura la degenerazione del sizing S1 senza cambiare la strategia (#490).

Calcola sul target vivo e sui primi giorni di borsa di ogni mese:
``n_target``, numero efficace di posizioni, quota di pesi raw sul cap e
Spearman fra rango del segnale e rango del peso. Il target vivo arriva dallo
stato Redis usato dal rebalance clock; la storia viene ricostruita dalle stesse
barre giornaliere Alpaca IEX e dagli stessi default ``S1Config`` del path live.

Lo script e' read-only verso Redis e Alpaca. Se le credenziali non sono
caricate nella shell, usa il worker Docker gia' configurato soltanto per leggere
le barre; non esporta credenziali dal container.

Uso:
    uv run python scripts/measure_s1_sizing_degeneracy.py
    python scripts/measure_s1_sizing_degeneracy.py --since 2026-06-01
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from src.config import config
from src.strategies.s1.sizing import compute_sizing_metrics
from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum

OUT = PROJECT_DIR / "docs" / "evidence" / "s1_sizing_degeneracy.json"
DEFAULT_SINCE = date(2026, 6, 1)
DEFAULT_WORKER_CONTAINER = "alembic-worker-1"
DEFAULT_REDIS_CONTAINER = "alembic-redis-1"


def first_trading_sessions(
    index: pd.DatetimeIndex,
    *,
    since: date,
) -> list[pd.Timestamp]:
    """Return the first available session of each month from ``since``."""
    sessions: list[pd.Timestamp] = []
    seen: set[tuple[int, int]] = set()
    for ts in pd.DatetimeIndex(index).sort_values().unique():
        stamp = pd.Timestamp(ts)
        if stamp.date() < since:
            continue
        month = (stamp.year, stamp.month)
        if month not in seen:
            seen.add(month)
            sessions.append(stamp)
    return sessions


def _strategy_snapshot(
    prices: pd.DataFrame,
    as_of: pd.Timestamp,
    *,
    target_weights: dict[str, float] | None = None,
) -> tuple[dict[str, int | float | None], int, str | None, dict[str, dict[str, float]]]:
    """Measure a reconstructed S1 target, or an externally persisted target."""
    panel = prices.loc[prices.index <= as_of]
    strategy = TimeSeriesMomentum(panel, S1Config())
    reconstructed = strategy.compute_target_weights(panel)

    if target_weights is None:
        return (
            strategy.last_sizing_metrics
            or compute_sizing_metrics(
                target_weights={}, signals={}, raw_weights={}, max_weight=S1Config().max_weight
            ),
            len(reconstructed),
            strategy._signal_wide.index[-1].date().isoformat()
            if not strategy._signal_wide.empty
            else None,
            {},
        )

    if strategy._signal_wide.empty or strategy._weight_wide.empty:
        metrics = compute_sizing_metrics(
            target_weights=target_weights,
            signals={},
            raw_weights={},
            max_weight=S1Config().max_weight,
        )
        return metrics, 0, None, {
            "target_weights": target_weights,
            "signals": {},
            "raw_weights": {},
        }

    valid_dates = strategy._signal_wide.index[strategy._signal_wide.index <= as_of]
    if len(valid_dates) == 0:
        metrics = compute_sizing_metrics(
            target_weights=target_weights,
            signals={},
            raw_weights={},
            max_weight=S1Config().max_weight,
        )
        return metrics, 0, None, {
            "target_weights": target_weights,
            "signals": {},
            "raw_weights": {},
        }

    lookup_date = valid_dates[-1]
    signals_row = strategy._signal_wide.loc[lookup_date]
    weights_row = strategy._weight_wide.loc[lookup_date]
    matched = [
        ticker
        for ticker in target_weights
        if ticker in signals_row.index
        and ticker in weights_row.index
        and pd.notna(signals_row[ticker])
        and pd.notna(weights_row[ticker])
    ]
    inputs = {
        "target_weights": target_weights,
        "signals": {ticker: float(signals_row[ticker]) for ticker in matched},
        "raw_weights": {ticker: float(weights_row[ticker]) for ticker in matched},
    }
    metrics = compute_sizing_metrics(
        target_weights=target_weights,
        signals=inputs["signals"],
        raw_weights=inputs["raw_weights"],
        max_weight=S1Config().max_weight,
    )
    return metrics, len(matched), lookup_date.date().isoformat(), inputs


def build_report(
    prices: pd.DataFrame,
    live_state: dict,
    *,
    since: date = DEFAULT_SINCE,
    generated_at: datetime | None = None,
) -> dict:
    """Build the JSON report from already-loaded inputs; no external I/O."""
    generated_at = generated_at or datetime.now(UTC)
    prices = prices.sort_index()
    live_ts = pd.Timestamp(live_state["last_rebalance"])
    target = {
        str(ticker): float(weight)
        for ticker, weight in (live_state.get("target_weights") or {}).items()
    }
    live_metrics, matched, live_lookup, live_inputs = _strategy_snapshot(
        prices,
        live_ts,
        target_weights=target,
    )

    historical = []
    for session in first_trading_sessions(prices.index, since=since):
        metrics, matched_target, lookup_date, _ = _strategy_snapshot(prices, session)
        historical.append(
            {
                "as_of": session.date().isoformat(),
                "signal_as_of": lookup_date,
                "metrics": metrics,
                "matched_target_symbols": matched_target,
            }
        )

    return {
        "generated_at": generated_at.isoformat(),
        "method": (
            "S1Config live defaults; Alpaca daily IEX bars, adjustment=all; "
            "target vivo da strategy:rebalance_state:S1; n_eff=1/sum(w^2); "
            "cap_bound sul peso inverse-vol raw prima della normalizzazione; "
            "Spearman sui ranghi medi di z e peso target"
        ),
        "live": {
            "as_of": live_ts.isoformat(),
            "signal_as_of": live_lookup,
            "target_sum": sum(target.values()),
            "matched_target_symbols": matched,
            "metrics": live_metrics,
            "inputs": live_inputs,
        },
        "historical_first_trading_days": historical,
        "operator_question": (
            "Dopo il freeze #171, S1 deve continuare a usare il segnale soltanto "
            "come gate oppure il sizing deve pesare la convinzione? Valutare la "
            "decisione insieme alle regole fra sleeve di #338; nessuna taratura "
            "e' applicata da questa misura."
        ),
    }


def _load_live_state(redis_container: str) -> dict:
    """Read the current S1 rebalance state, preferring the configured Redis."""
    try:
        from redis import Redis

        client = Redis.from_url(config.REDIS_URL, decode_responses=True)
        try:
            raw = client.get("strategy:rebalance_state:S1")
        finally:
            client.close()
    except Exception:  # noqa: BLE001 - local Redis is optional; Docker is the fallback
        result = subprocess.run(
            [
                "docker",
                "exec",
                redis_container,
                "redis-cli",
                "--raw",
                "get",
                "strategy:rebalance_state:S1",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"Redis non leggibile: {result.stderr.strip()[:300]}")
        raw = result.stdout.strip()
    if not raw:
        raise SystemExit("strategy:rebalance_state:S1 assente: nessun target vivo da misurare")
    try:
        state = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Stato S1 non decodificabile: {exc}") from exc
    if not state.get("last_rebalance") or not isinstance(state.get("target_weights"), dict):
        raise SystemExit("Stato S1 incompleto: servono last_rebalance e target_weights")
    return state


def _records_to_prices(records: list[dict]) -> pd.DataFrame:
    if not records:
        raise SystemExit("Alpaca non ha restituito barre giornaliere")
    frame = pd.DataFrame.from_records(records)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return (
        frame.pivot(index="timestamp", columns="symbol", values="close")
        .sort_index()
        .astype(float)
    )


def _load_prices_direct(symbols: list[str], start: datetime, end: datetime) -> pd.DataFrame:
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,
        adjustment=Adjustment.ALL,
    )
    frame = client.get_stock_bars(request).df
    if frame is None or frame.empty:
        raise SystemExit("Alpaca non ha restituito barre giornaliere")
    frame = frame.reset_index()
    return frame.pivot(index="timestamp", columns="symbol", values="close").sort_index()


def _load_prices_from_worker(
    symbols: list[str],
    start: datetime,
    end: datetime,
    worker_container: str,
) -> pd.DataFrame:
    code = """
import json, sys
from datetime import datetime
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from src.config import config

symbols = json.loads(sys.argv[1])
client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
request = StockBarsRequest(
    symbol_or_symbols=symbols,
    timeframe=TimeFrame.Day,
    start=datetime.fromisoformat(sys.argv[2]),
    end=datetime.fromisoformat(sys.argv[3]),
    feed=DataFeed.IEX,
    adjustment=Adjustment.ALL,
)
frame = client.get_stock_bars(request).df.reset_index()
records = [
    {"symbol": row.symbol, "timestamp": row.timestamp.isoformat(), "close": float(row.close)}
    for row in frame.itertuples(index=False)
]
print(json.dumps(records, separators=(",", ":")))
"""
    result = subprocess.run(
        [
            "docker",
            "exec",
            worker_container,
            "python",
            "-c",
            code,
            json.dumps(symbols),
            start.isoformat(),
            end.isoformat(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Fetch Alpaca nel worker fallita: {result.stderr.strip()[:300]}")
    return _records_to_prices(json.loads(result.stdout))


def load_prices(
    symbols: list[str],
    start: datetime,
    end: datetime,
    *,
    worker_container: str,
) -> pd.DataFrame:
    if config.ALPACA_API_KEY and config.ALPACA_SECRET_KEY:
        return _load_prices_direct(symbols, start, end)
    return _load_prices_from_worker(symbols, start, end, worker_container)


def _format_number(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "n/d"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def print_table(report: dict) -> None:
    print(f"{'data':<12} {'fonte':<10} {'n':>4} {'n_eff':>8} {'cap':>8} {'rho(z,w)':>10}")
    rows = [(report["live"]["as_of"][:10], "live", report["live"]["metrics"])]
    rows.extend(
        (row["as_of"], "storico", row["metrics"])
        for row in report["historical_first_trading_days"]
    )
    for as_of, source, metrics in rows:
        print(
            f"{as_of:<12} {source:<10} {metrics['n_target']:>4} "
            f"{_format_number(metrics['n_eff']):>8} "
            f"{_format_number(metrics['cap_bound_share']):>8} "
            f"{_format_number(metrics['spearman_signal_weight']):>10}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=date.fromisoformat, default=DEFAULT_SINCE)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--worker-container", default=DEFAULT_WORKER_CONTAINER)
    parser.add_argument("--redis-container", default=DEFAULT_REDIS_CONTAINER)
    args = parser.parse_args()

    live_state = _load_live_state(args.redis_container)
    symbols = list(config.WATCHLIST_SYMBOLS or [])
    if not symbols:
        raise SystemExit("Watchlist S1 vuota in config/trading.yaml")
    start = datetime.combine(args.since - timedelta(days=620), datetime.min.time(), UTC)
    end_date = max(datetime.now(UTC).date(), pd.Timestamp(live_state["last_rebalance"]).date())
    end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), UTC)
    prices = load_prices(symbols, start, end, worker_container=args.worker_container)
    report = build_report(prices, live_state, since=args.since)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(args.output)
    print_table(report)
    print(f"\nscritto {args.output}")


if __name__ == "__main__":
    main()
