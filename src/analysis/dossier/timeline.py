"""Timeline point-in-time e metriche intraday per il dossier alpha-miss.

Modulo puro: riceve eventi, barre e cutoff gia' caricati. Non tocca rete o DB.
Le barre intraday sono identificate dal loro istante di apertura: per un evento
che cade dentro una barra si usa sempre l'open della barra successiva, mai OHLC
della barra in corso, che conterrebbe informazione futura.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo


UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
STAGE_NAMES = (
    "published_at",
    "first_seen_at",
    "ingested_at",
    "scored_at",
    "eligible_cycle_at",
    "order_submitted_at",
    "filled_at",
)


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _required_utc(value: datetime | str) -> datetime:
    parsed = _as_utc(value)
    if parsed is None:  # pragma: no cover - il tipo esclude None
        raise ValueError("timestamp mancante")
    return parsed


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator != 0 else None


def _movement(daily: dict[str, float] | None) -> dict[str, float | None]:
    if not daily:
        return {
            "gap_return": None,
            "intraday_return": None,
            "mfe_from_open": None,
            "mae_from_open": None,
        }
    previous = daily.get("close_prec")
    open_ = daily.get("open")
    close = daily.get("close")
    high = daily.get("high")
    low = daily.get("low")
    return {
        "gap_return": (
            None
            if previous is None or previous == 0 or open_ is None
            else open_ / previous - 1.0
        ),
        "intraday_return": (
            None if open_ is None or open_ == 0 or close is None else close / open_ - 1.0
        ),
        "mfe_from_open": (
            None if open_ is None or open_ == 0 or high is None else high / open_ - 1.0
        ),
        "mae_from_open": (
            None if open_ is None or open_ == 0 or low is None else low / open_ - 1.0
        ),
    }


def _empty_stage(timestamp: datetime | None, reason: str) -> dict[str, Any]:
    return {
        "timestamp": timestamp.isoformat() if timestamp else None,
        "bar_timestamp": None,
        "price": None,
        "price_source": None,
        "actual_price": None,
        "actual_price_source": None,
        "quota_movimento_totale": None,
        "quota_movimento_intraday": None,
        "mfe": None,
        "mae": None,
        "missing_reason": reason,
    }


def _stage_metrics(
    timestamp: datetime | str | None,
    bars: list[dict[str, Any]],
    daily: dict[str, float] | None,
    cutoff: datetime,
    actual_price: float | None = None,
) -> dict[str, Any]:
    stage_time = _as_utc(timestamp)
    if stage_time is None:
        return _empty_stage(None, "timestamp_not_recorded")
    if stage_time > cutoff:
        return _empty_stage(stage_time, "stage_after_cutoff")

    subsequent = [
        bar
        for bar in bars
        if stage_time <= _required_utc(bar["timestamp"]) <= cutoff
    ]
    if not subsequent:
        return _empty_stage(stage_time, "no_bar_before_cutoff")

    first = subsequent[0]
    price = float(first["open"])
    previous = daily.get("close_prec") if daily else None
    open_ = daily.get("open") if daily else None
    close = daily.get("close") if daily else None
    total_denominator = (
        None if previous is None or close is None else close - previous
    )
    intraday_denominator = None if open_ is None or close is None else close - open_

    return {
        "timestamp": stage_time.isoformat(),
        "bar_timestamp": _required_utc(first["timestamp"]).isoformat(),
        "price": price,
        "price_source": "alpaca_sip_5min.open",
        "actual_price": actual_price,
        "actual_price_source": (
            "alpaca_order.filled_avg_price" if actual_price is not None else None
        ),
        "quota_movimento_totale": (
            None
            if previous is None or total_denominator is None
            else _ratio(price - previous, total_denominator)
        ),
        "quota_movimento_intraday": (
            None
            if open_ is None or intraday_denominator is None
            else _ratio(price - open_, intraday_denominator)
        ),
        "mfe": max(float(bar["high"]) for bar in subsequent) / price - 1.0,
        "mae": min(float(bar["low"]) for bar in subsequent) / price - 1.0,
        "missing_reason": None,
    }


def _session_name(timestamp: datetime | str) -> str | None:
    local_time = _required_utc(timestamp).astimezone(NEW_YORK).time()
    if time(4, 0) <= local_time < time(9, 30):
        return "premarket"
    if time(9, 30) <= local_time < time(16, 0):
        return "regular"
    if time(16, 0) <= local_time < time(20, 0):
        return "afterhours"
    return None


def session_summary(
    bars: list[dict[str, Any]], session_date: date | None = None
) -> dict[str, dict[str, Any]]:
    """Copertura e rendimento delle sessioni US, incluse le ore estese."""
    grouped: dict[str, list[dict[str, Any]]] = {
        "premarket": [],
        "regular": [],
        "afterhours": [],
    }
    for bar in sorted(bars, key=lambda item: _required_utc(item["timestamp"])):
        if (
            session_date is not None
            and _required_utc(bar["timestamp"]).astimezone(NEW_YORK).date()
            != session_date
        ):
            continue
        name = _session_name(bar["timestamp"])
        if name is not None:
            grouped[name].append(bar)

    result: dict[str, dict[str, Any]] = {}
    for name, session_bars in grouped.items():
        if not session_bars:
            result[name] = {
                "available": False,
                "bars": 0,
                "first_bar_at": None,
                "last_bar_at": None,
                "open": None,
                "close": None,
                "return": None,
            }
            continue
        first, last = session_bars[0], session_bars[-1]
        open_, close = float(first["open"]), float(last["close"])
        result[name] = {
            "available": True,
            "bars": len(session_bars),
            "first_bar_at": _required_utc(first["timestamp"]).isoformat(),
            "last_bar_at": _required_utc(last["timestamp"]).isoformat(),
            "open": open_,
            "close": close,
            "return": None if open_ == 0 else close / open_ - 1.0,
        }
    return result


def build_timeline(
    events: list[dict[str, Any]],
    mover_symbols: set[str],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    daily_bars: dict[str, dict[str, float]],
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Costruisce una riga per segnale e uno stub per ogni mover senza segnali."""
    cutoff_utc = _required_utc(cutoff)
    session_date = cutoff_utc.astimezone(NEW_YORK).date()
    rows: list[dict[str, Any]] = []
    symbols_with_signal: set[str] = set()

    for event in events:
        symbol = event["symbol"]
        symbols_with_signal.add(symbol)
        bars = sorted(
            bars_by_symbol.get(symbol, []),
            key=lambda item: _required_utc(item["timestamp"]),
        )
        stages = {
            name: _stage_metrics(
                event.get(name),
                bars,
                daily_bars.get(symbol),
                cutoff_utc,
                event.get("fill_price") if name == "filled_at" else None,
            )
            for name in STAGE_NAMES
        }
        rows.append({
            "kind": "signal",
            "symbol": symbol,
            "is_mover": symbol in mover_symbols,
            "signal_id": event.get("signal_id"),
            "news_log_id": event.get("news_log_id"),
            "score": event.get("score"),
            "fallback": event.get("fallback"),
            "order_id": event.get("order_id"),
            "trade_id": event.get("trade_id"),
            "order_lookup_error": event.get("order_lookup_error"),
            "movimento": _movement(daily_bars.get(symbol)),
            "sessioni": session_summary(bars, session_date),
            "stages": stages,
        })

    for symbol in sorted(mover_symbols - symbols_with_signal):
        bars = bars_by_symbol.get(symbol, [])
        rows.append({
            "kind": "mover_without_signal",
            "symbol": symbol,
            "is_mover": True,
            "signal_id": None,
            "news_log_id": None,
            "score": None,
            "fallback": None,
            "order_id": None,
            "trade_id": None,
            "order_lookup_error": None,
            "movimento": _movement(daily_bars.get(symbol)),
            "sessioni": session_summary(bars, session_date),
            "stages": {
                name: _empty_stage(None, "timestamp_not_recorded")
                for name in STAGE_NAMES
            },
        })

    return sorted(
        rows,
        key=lambda row: (
            row["symbol"],
            row["stages"]["scored_at"]["timestamp"] or "",
            row["signal_id"] or -1,
        ),
    )
