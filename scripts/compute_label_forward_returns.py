#!/usr/bin/env python3
"""Populate forward returns on the QX-01 label set from Alpaca historical bars.

For each LABELED news_label with a ground-truth ticker and published_at, computes
close-to-close forward returns at +1h (minute bars), +1d and +2d (daily bars),
point-in-time from published_at (entry = first bar at/after published_at). Uses the
first gt_ticker. Offline/idempotent; fail-soft per row (NULLs on missing data).

Run inside the worker container (Alpaca creds + DB):
    docker compose exec worker python scripts/compute_label_forward_returns.py
"""
from __future__ import annotations

import os
from datetime import timedelta

import psycopg2
import psycopg2.extras


def _conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading")
    return psycopg2.connect(url)


def _data_client():
    from alpaca.data.historical import StockHistoricalDataClient
    from src.config import config
    return StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)


def _pct(a: float, b: float) -> float | None:
    return (b / a - 1.0) if (a and a > 0) else None


def _forward_returns(client, symbol: str, published_at) -> dict:
    """Return {1h, 1d, 2d} close-to-close forward returns from published_at."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed

    out: dict[str, float | None] = {"1h": None, "1d": None, "2d": None}
    try:
        # Daily bars for 1d/2d
        dreq = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
            start=published_at - timedelta(days=1), end=published_at + timedelta(days=6),
            feed=DataFeed.IEX,
        )
        dbars = client.get_stock_bars(dreq).data.get(symbol, [])
        after = [b for b in dbars if b.timestamp >= published_at]
        if len(after) >= 2:
            out["1d"] = _pct(after[0].close, after[1].close)
        if len(after) >= 3:
            out["2d"] = _pct(after[0].close, after[2].close)
    except Exception as exc:
        print(f"  daily bars failed for {symbol}: {exc}")
    try:
        # Minute bars for 1h
        mreq = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=TimeFrame.Minute,
            start=published_at, end=published_at + timedelta(hours=3), feed=DataFeed.IEX,
        )
        mbars = client.get_stock_bars(mreq).data.get(symbol, [])
        after = [b for b in mbars if b.timestamp >= published_at]
        if after:
            entry = after[0]
            later = [b for b in after if b.timestamp >= published_at + timedelta(hours=1)]
            if later:
                out["1h"] = _pct(entry.close, later[0].close)
    except Exception as exc:
        print(f"  minute bars failed for {symbol}: {exc}")
    return out


def main() -> None:
    client = _data_client()
    done = 0
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT label_id, gt_tickers, published_at FROM news_labels
                   WHERE status='labeled' AND gt_tickers IS NOT NULL
                     AND array_length(gt_tickers,1) >= 1
                     AND forward_return_1d IS NULL AND published_at IS NOT NULL"""
            )
            rows = cur.fetchall()
        print(f"{len(rows)} labeled rows need forward returns")
        for r in rows:
            sym = r["gt_tickers"][0]
            fr = _forward_returns(client, sym, r["published_at"])
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE news_labels SET forward_return_1h=%s, forward_return_1d=%s,
                       forward_return_2d=%s, price_source='alpaca' WHERE label_id=%s""",
                    (fr["1h"], fr["1d"], fr["2d"], r["label_id"]),
                )
            conn.commit()
            done += 1
            print(f"  {sym} @ {r['published_at']:%Y-%m-%d}: 1h={fr['1h']} 1d={fr['1d']} 2d={fr['2d']}")
    print(f"Updated {done} rows.")


if __name__ == "__main__":
    main()
