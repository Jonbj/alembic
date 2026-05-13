"""ForwardReturnCalculator — computes 1h/4h/24h price returns for backtest signals."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)


@dataclass
class ForwardReturns:
    return_1h: float | None
    return_4h: float | None
    return_24h: float | None


class ForwardReturnCalculator:
    """Downloads yfinance prices and populates forward returns in backtest_signals.

    Call pattern:
        calc = ForwardReturnCalculator(pg_conn)
        calc.populate(run_id, start_date, end_date)

    Downloads hourly + daily price data once per ticker for the entire period.
    Computes three forward returns per signal:
      - 1h:  (price at next_bar + 1h) / (price at next_bar) - 1
      - 4h:  (price at next_bar + 4h) / (price at next_bar) - 1
      - 24h: (next_day_close) / (current_day_close) - 1
    Returns None for any horizon where the required bar is missing (weekend, holiday,
    post-market). No interpolation — never guess prices.
    """

    def __init__(self, pg_conn) -> None:
        self._conn = pg_conn

    def populate(self, run_id: str, start_date: datetime, end_date: datetime) -> int:
        """Populate forward_return_1h/4h/24h for all scored rows in run_id.

        Returns the number of rows updated.
        """
        rows = self._fetch_scored_rows(run_id)
        if not rows:
            log.info("No scored rows found for run_id=%s", run_id)
            return 0

        tickers = list({r["symbol"] for r in rows})
        log.info("Downloading prices for %d tickers", len(tickers))

        hourly = self._download_prices(tickers, start_date, end_date, interval="1h")
        daily = self._download_prices(tickers, start_date, end_date, interval="1d")

        updates = []
        for row in rows:
            fwd = self._compute_returns(
                row["symbol"],
                row["generated_at"],
                hourly.get(row["symbol"]),
                daily.get(row["symbol"]),
            )
            updates.append((
                fwd.return_1h, fwd.return_4h, fwd.return_24h, row["id"]
            ))

        with self._conn.cursor() as cur:
            cur.executemany(
                "UPDATE backtest_signals "
                "SET forward_return_1h=%s, forward_return_4h=%s, forward_return_24h=%s "
                "WHERE id=%s",
                updates,
            )
        self._conn.commit()
        log.info("Updated %d forward return rows for run_id=%s", len(updates), run_id)
        return len(updates)

    def _fetch_scored_rows(self, run_id: str) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, symbol, generated_at "
                "FROM backtest_signals "
                "WHERE run_id = %s AND score IS NOT NULL "
                "ORDER BY generated_at",
                (run_id,),
            )
            return [
                {"id": row[0], "symbol": row[1], "generated_at": row[2]}
                for row in cur.fetchall()
            ]

    def _download_prices(
        self,
        tickers: list[str],
        start: datetime,
        end: datetime,
        interval: str,
    ) -> dict[str, pd.Series]:
        """Download close prices for each ticker. Returns dict ticker → pd.Series."""
        result: dict[str, pd.Series] = {}
        dl_start = (start - timedelta(days=1)).strftime("%Y-%m-%d")
        dl_end = (end + timedelta(days=2)).strftime("%Y-%m-%d")
        for ticker in tickers:
            try:
                df = yf.download(
                    ticker,
                    start=dl_start,
                    end=dl_end,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
                if not df.empty:
                    result[ticker] = df["Close"]
                else:
                    log.warning("yfinance returned empty data for %s (%s)", ticker, interval)
            except Exception as e:
                log.warning("yfinance download failed for %s: %s", ticker, e)
        return result

    def _compute_returns(
        self,
        symbol: str,
        ts: datetime,
        hourly: pd.Series | None,
        daily: pd.Series | None,
    ) -> ForwardReturns:
        """Compute 1h, 4h, 24h forward returns for a single signal at timestamp ts."""
        if hourly is None:
            return ForwardReturns(None, None, None)

        ts_utc = pd.Timestamp(ts).tz_convert("UTC") if ts.tzinfo else pd.Timestamp(ts, tz="UTC")

        # Find the first bar at or after ts
        idx = hourly.index.searchsorted(ts_utc)
        if idx >= len(hourly.index):
            return ForwardReturns(None, None, None)

        t_bar = hourly.index[idx]
        price_t = float(hourly.iloc[idx])

        def _return_at_offset(offset_hours: int) -> float | None:
            target = t_bar + pd.Timedelta(hours=offset_hours)
            future = hourly[hourly.index >= target]
            if future.empty:
                return None
            # Accept bar within 30 minutes of target to handle DST / market-open offsets
            if (future.index[0] - target).total_seconds() > 1800:
                return None
            return float((future.iloc[0] - price_t) / price_t)

        return_1h = _return_at_offset(1)
        return_4h = _return_at_offset(4)

        # 24h: next trading day close / current trading day close
        return_24h: float | None = None
        if daily is not None:
            day_ts = ts_utc.normalize()
            d_idx = daily.index.searchsorted(day_ts)
            if d_idx + 1 < len(daily.index):
                close_today = float(daily.iloc[d_idx])
                close_next = float(daily.iloc[d_idx + 1])
                if close_today > 0:
                    return_24h = (close_next - close_today) / close_today

        return ForwardReturns(return_1h, return_4h, return_24h)
