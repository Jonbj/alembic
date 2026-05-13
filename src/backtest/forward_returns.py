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

    Why batch download instead of per-signal?
      yfinance is network-heavy. Downloading once per ticker for the whole period
      and slicing in-memory is ~100x faster than N API calls.
    """

    def __init__(self, pg_conn) -> None:
        self._conn = pg_conn

    def populate(self, run_id: str, start_date: datetime, end_date: datetime) -> int:
        """Populate forward_return_1h/4h/24h for all scored rows in run_id.

        Pipeline:
          1. SELECT all scored rows for this run_id from backtest_signals.
          2. Determine unique tickers.
          3. Download hourly + daily close prices once per ticker (vectorized).
          4. For each signal row, compute three forward returns via _compute_returns.
          5. Batch UPDATE all rows in a single executemany call.

        Returns:
            Number of rows updated (should equal number of scored rows).
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
        """Fetch scored rows from backtest_signals for a given run_id.

        Filters: score IS NOT NULL (ensures LLM inference completed).
        Ordering: generated_at ascending (not required for correctness, but
        makes logs and debugging deterministic).
        """
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
        """Download close prices for each ticker. Returns dict ticker → pd.Series.

        Edge-case handling:
          - start_date expanded by -1 day, end_date by +2 days to cover signals
            near the period boundary (we need forward bars *after* the signal).
          - Empty DataFrame → log warning, skip ticker (all returns will be None).
          - Any Exception (network, invalid ticker, delisted) → log warning, skip.
            We do NOT fail the entire backtest because one ticker is bad.
          - auto_adjust=True to use adjusted close (splits/dividends corrected).
          - progress=False to silence yfinance console spam.
        """
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
        """Compute 1h, 4h, 24h forward returns for a single signal at timestamp ts.

        Algorithm for 1h/4h:
          1. Convert ts to UTC pd.Timestamp (handles naive datetimes safely).
          2. Find first hourly bar at or after ts via searchsorted (O(log N)).
          3. If no such bar exists → all None (signal after last price).
          4. Anchor price = price at that bar.
          5. For +1h / +4h: look for bar at target time. Accept within 30 minutes
             to absorb DST shifts and market-open irregularities.
          6. If target bar missing → None (weekend, holiday, post-market).

        Algorithm for 24h:
          1. Normalize ts to midnight → trading day.
          2. Find that day's close in daily series via searchsorted.
          3. Next day's close = daily[d_idx + 1].
          4. If either missing → None.

        Why no interpolation?
          Interpolating missing bars would introduce look-ahead bias
          (we'd be using future information not available at signal time).
          None returns are dropped from IC calculation, not imputed.
        """
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
