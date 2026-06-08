"""PostgreSQL store for sentiment signals and performance metrics."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

log = logging.getLogger(__name__)

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from src.config import config
from src.costs.calculator import TradeCostCalculator
from src.models.signals import SentimentResult

if TYPE_CHECKING:
    from src.models.news import NewsItem
    from src.llm.ensemble import ModelOutput

# Global connection pool - lazy initialized
_db_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    """Get or create the global connection pool."""
    global _db_pool
    if _db_pool is None:
        # Min 2 connections, max 20 - adjust based on workload
        # Timeout: raise after 30s instead of hanging indefinitely
        try:
            _db_pool = pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                dsn=config.DATABASE_URL,
            )
        except psycopg2.OperationalError as e:
            raise RuntimeError(f"Failed to initialize database connection pool: {e}")
    return _db_pool


class PostgreSQLStore:
    """PostgreSQL storage for sentiment signals and performance data.

    Uses connection pooling for efficient resource management in production.
    """

    # FIX: Use parameterized query instead of string interpolation for INTERVAL
    # Original vulnerable code:
    #   _FETCH_FOR_IC = "SELECT ... WHERE generated_at >= now() - INTERVAL '%s days'"
    # This allowed SQL injection via the 'days' parameter.
    #
    # Fixed: Pass the interval as a parameter using PostgreSQL's interval arithmetic
    _FETCH_FOR_IC = """
        SELECT score, confidence, forward_return, generated_at, model_id, fallback_used
        FROM sentiment_signals
        WHERE symbol = %s
          AND generated_at >= now() - (%s || ' days')::interval
          AND fallback_used = FALSE
        ORDER BY generated_at ASC
    """

    _INSERT_SIGNAL = """
        INSERT INTO sentiment_signals (
            symbol, score, confidence, reasoning, model_id,
            ensemble_std, fallback_used, generated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, generated_at) DO UPDATE SET
            score = EXCLUDED.score,
            confidence = EXCLUDED.confidence,
            reasoning = EXCLUDED.reasoning,
            model_id = EXCLUDED.model_id,
            ensemble_std = EXCLUDED.ensemble_std,
            fallback_used = EXCLUDED.fallback_used
        RETURNING id
    """

    _INSERT_WEIGHT_LOG = """
        INSERT INTO weight_update_log (
            source, applied_weights, suggested_weights,
            purified_icir, freeze_reason, note, approved_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    def __init__(
        self,
        conn: psycopg2.extensions.connection | None = None,
        use_pool: bool = True,
        cost_calc: TradeCostCalculator | None = None,
    ):
        """Initialize PostgreSQL store.

        Args:
            conn: Optional existing connection. If None, will use connection pool.
            use_pool: If True, use the global connection pool. If False, create
                      a dedicated connection (useful for tests).
            cost_calc: Optional TradeCostCalculator instance. If None, a default
                       instance is created using config/cost_model.yaml.
        """
        self._conn = conn
        self._use_pool = use_pool and conn is None
        self._owns_connection = conn is None and not self._use_pool
        self._cost_calc = cost_calc or TradeCostCalculator()

    def _get_connection(self) -> psycopg2.extensions.connection:
        """Get or create database connection."""
        if self._conn is not None:
            return self._conn

        if self._use_pool:
            # Get connection from pool — store in self._conn so close() can return it
            try:
                self._conn = _get_pool().getconn()
                return self._conn
            except psycopg2.pool.PoolError:
                # Pool exhausted — fall back to a direct connection.
                # Must clear _use_pool so _release_connection() calls conn.close()
                # instead of putconn() on a connection that was never in the pool.
                self._conn = psycopg2.connect(config.DATABASE_URL)
                self._use_pool = False
                self._owns_connection = True
                return self._conn

        # Create dedicated connection (not recommended for production)
        self._conn = psycopg2.connect(config.DATABASE_URL)
        self._owns_connection = True
        return self._conn

    def _release_connection(self, conn: psycopg2.extensions.connection) -> None:
        """Return connection to pool if using pooling."""
        if self._use_pool and conn is not None:
            _get_pool().putconn(conn)
        elif self._owns_connection and conn is not None:
            conn.close()

    def close(self) -> None:
        """Close connection or return it to pool."""
        if self._conn is not None:
            self._release_connection(self._conn)
            self._conn = None

    def write_signal(self, result: SentimentResult) -> int:
        """Write sentiment signal to database. Returns the inserted/updated row id."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_SIGNAL,
                    (
                        result.symbol,
                        result.score,
                        result.confidence,
                        result.reasoning,
                        result.model_id,
                        result.ensemble_std,
                        result.fallback_used,
                        result.generated_at,
                    ),
                )
                row = cur.fetchone()
                signal_id: int = row[0]
            conn.commit()
            return signal_id
        except Exception:
            conn.rollback()
            raise

    _INSERT_NEWS_LOG = """
        INSERT INTO news_log (title, url, source, ticker, body_snippet, raw_sentiment, fetched_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url, ticker) DO NOTHING
        RETURNING id
    """

    _INSERT_LLM_RESPONSE = """
        INSERT INTO llm_responses (signal_id, model_id, polarity, confidence, reasoning, eligible, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, now())
    """

    def log_news_item(
        self,
        item: NewsItem,
        ticker: str,
        computed_sentiment: float | None = None,
    ) -> int | None:
        """Write article metadata to news_log. Skips silently on conflict.

        Args:
            item: The news article to log.
            ticker: Ticker symbol associated with this article.
            computed_sentiment: LLM/FinBERT score (polarity × confidence) computed
                by the sentiment worker. When provided this takes precedence over
                the article-level MarketAux sentiment so the stored value always
                reflects the actual signal used for trading decisions. When None,
                falls back to MarketAux article-level sentiment (or NULL for
                GDELT/Alpaca articles that lack a pre-computed score).

        Returns:
            The inserted row id, or None if the row already existed (ON CONFLICT DO NOTHING).
        """
        from src.models.news import MarketAuxNewsItem

        if computed_sentiment is not None:
            raw_sentiment = computed_sentiment
        else:
            raw_sentiment = item.marketaux_sentiment if isinstance(item, MarketAuxNewsItem) else None
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_NEWS_LOG,
                    (
                        item.title[:500] if item.title else "",
                        item.url[:1000] if item.url else "",
                        item.source,
                        ticker,
                        item.body[:500] if item.body else None,
                        raw_sentiment,
                        item.timestamp,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else None
        except Exception:
            conn.rollback()
            raise

    _LINK_SIGNAL_TO_NEWS = """
        UPDATE sentiment_signals SET news_log_id = %s WHERE id = %s
    """

    def link_signal_to_news(self, signal_id: int, news_log_id: int) -> None:
        """Set news_log_id on an already-written sentiment_signals row."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._LINK_SIGNAL_TO_NEWS, (news_log_id, signal_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    _INSERT_DECISION = """
        INSERT INTO execution_decisions
            (tick_time, symbol, signal_id, score, regime_mult, ema_pass, decision, order_id, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    def write_execution_decision(
        self,
        tick_time,
        symbol: str,
        signal_id: int | None,
        score: float,
        regime_mult: float,
        ema_pass: bool,
        decision: str,
        order_id: str | None = None,
        reason: str | None = None,
    ) -> int:
        """Insert one execution decision row. Returns the new id."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_DECISION,
                    (tick_time, symbol, signal_id, score, regime_mult, ema_pass, decision, order_id, reason),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row[0])
        except Exception:
            conn.rollback()
            raise

    def fetch_decisions(
        self,
        symbol: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Return decision log rows, most-recent first."""
        filters = []
        params: list = []
        if symbol:
            filters.append("symbol = %s")
            params.append(symbol)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT id, tick_time, symbol, signal_id, score, regime_mult,
                               ema_pass, decision, order_id, reason, created_at
                        FROM execution_decisions {where}
                        ORDER BY tick_time DESC LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    # --- Counterfactual (Phase C) ---

    def fetch_skip_decisions_without_counterfactual(
        self,
        days_back: int = 7,
        limit: int = 500,
    ) -> list[dict]:
        """Return SKIP_EMA and SKIP_CAP rows from the last N days that have no counterfactual yet."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, tick_time, symbol, score, regime_mult, decision
                       FROM execution_decisions
                       WHERE decision IN ('SKIP_EMA', 'SKIP_CAP')
                         AND counterfactual_computed_at IS NULL
                         AND tick_time >= now() - (%s || ' days')::interval
                       ORDER BY tick_time DESC
                       LIMIT %s""",
                    (str(days_back), limit),
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def bulk_set_counterfactual(
        self,
        updates: list[tuple],
    ) -> int:
        """Bulk-write counterfactual_return_1h and counterfactual_computed_at.

        Args:
            updates: list of (decision_id, return_1h_or_None, computed_at)
        Returns:
            Number of rows updated.
        """
        if not updates:
            return 0
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    """UPDATE execution_decisions
                       SET counterfactual_return_1h = %s,
                           counterfactual_computed_at = %s
                       WHERE id = %s""",
                    [(ret, ts, did) for did, ret, ts in updates],
                )
                count = cur.rowcount
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise

    _COUNTERFACTUAL_SUMMARY_SQL = """
        SELECT
            decision,
            COUNT(*) AS total_skips,
            COUNT(counterfactual_return_1h) AS computed,
            COALESCE(AVG(counterfactual_return_1h), 0) AS avg_return,
            COALESCE(
                SUM(CASE WHEN counterfactual_return_1h > 0 THEN 1 ELSE 0 END)::float
                / NULLIF(COUNT(counterfactual_return_1h), 0),
                0
            ) AS pct_profitable,
            COALESCE(SUM(CASE WHEN counterfactual_return_1h > 0 THEN counterfactual_return_1h ELSE 0 END), 0)
                AS sum_positive_returns
        FROM execution_decisions
        WHERE decision IN ('SKIP_EMA', 'SKIP_CAP')
          AND tick_time >= now() - (%s || ' days')::interval
        GROUP BY decision
        ORDER BY decision
    """

    def fetch_counterfactual_summary(self, days: int = 7) -> list[dict]:
        """Return aggregate counterfactual stats per decision type."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._COUNTERFACTUAL_SUMMARY_SQL, (str(days),))
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            return [
                {
                    **row,
                    "avg_return": round(float(row["avg_return"]), 4),
                    "pct_profitable": round(float(row["pct_profitable"]), 4),
                    "sum_positive_returns": round(float(row["sum_positive_returns"]), 4),
                }
                for row in rows
            ]
        except Exception:
            conn.rollback()
            raise

    _INSERT_TRADE = """
        INSERT INTO trades
            (symbol, signal_id, decision_id, entry_order_id,
             entry_time, entry_notional, score, regime_mult, qty)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    _CLOSE_TRADE = """
        UPDATE trades SET
            exit_price            = %s,
            exit_time             = %s,
            exit_reason           = %s,
            entry_price           = COALESCE(entry_price, %s),
            gross_pnl             = (%s - COALESCE(entry_price, %s)) * qty,
            cost_bps              = %s,
            cost_usd              = %s,
            spread_cost_bps       = %s,
            impact_cost_bps       = %s,
            regulatory_cost_usd   = %s,
            slippage_est          = %s,
            net_pnl               = ((%s - COALESCE(entry_price, %s)) * qty) - %s
        WHERE symbol = %s AND exit_time IS NULL
        RETURNING id
    """

    def open_trade(
        self,
        symbol: str,
        signal_id: int | None,
        decision_id: int | None,
        entry_order_id: str,
        entry_time,
        entry_notional: float,
        score: float,
        regime_mult: float,
        qty: float | None = None,
    ) -> None:
        """Insert an open trade row (entry_price populated later by reconcile)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_TRADE,
                    (symbol, signal_id, decision_id, entry_order_id,
                     entry_time, entry_notional, score, regime_mult, qty),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close_trade(
        self,
        symbol: str,
        exit_price: float,
        exit_time,
        exit_reason: str,
        entry_price: float | None = None,
        entry_notional: float | None = None,
        qty: float | None = None,
    ) -> int | None:
        """Update the open trade row for symbol with exit data and compute P&L.

        Args:
            symbol:          Ticker symbol of the trade to close.
            exit_price:      Fill price at which the position was exited.
            exit_time:       Timestamp of the exit.
            exit_reason:     Why the trade was closed (e.g. "stop_loss").
            entry_price:     Optional fill price from the Alpaca position object.
                             When provided, COALESCE(entry_price, %s) fills in the
                             DB column if it is still NULL (intra-day stop-loss before
                             reconcile_trade_fills has run).  When absent (None),
                             COALESCE falls back to whatever is already in the DB
                             column — preserving the original behavior for callers
                             that do not have the entry price readily available.
            entry_notional:  Trade notional in USD for cost calculation.
                             If None, fetched from the DB row before updating.
            qty:             Number of shares for cost calculation.
                             If None, fetched from the DB row before updating.

        Returns:
            The id of the updated trade row, or None if no open trade was found
            for the given symbol.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Fetch notional + qty from DB if not provided (e.g. stop-loss path)
                if entry_notional is None or qty is None:
                    cur.execute(
                        "SELECT entry_notional, qty FROM trades WHERE symbol = %s AND exit_time IS NULL FOR UPDATE SKIP LOCKED",
                        (symbol,),
                    )
                    row = cur.fetchone()
                    if row:
                        entry_notional = float(row[0]) if row[0] is not None else 0.0
                        qty = float(row[1]) if row[1] is not None else 0.0
                    else:
                        entry_notional = 0.0
                        qty = 0.0

                costs = self._cost_calc.compute(
                    symbol=symbol,
                    notional=entry_notional,
                    qty=qty,
                    fill_price=float(exit_price),
                    side="SELL",
                )

                cur.execute(
                    self._CLOSE_TRADE,
                    (
                        exit_price,                      # exit_price =
                        exit_time,                       # exit_time =
                        exit_reason,                     # exit_reason =
                        entry_price,                     # COALESCE(entry_price, ?)
                        exit_price, entry_price,         # gross_pnl numerator
                        costs.total_cost_bps,            # cost_bps =
                        costs.total_cost_usd,            # cost_usd =
                        costs.spread_cost_bps,           # spread_cost_bps =
                        costs.impact_cost_bps,           # impact_cost_bps =
                        costs.regulatory_cost_usd,       # regulatory_cost_usd =
                        costs.total_cost_usd,            # slippage_est = (backward compat)
                        exit_price, entry_price,         # net_pnl numerator
                        costs.total_cost_usd,            # net_pnl deduction
                        symbol,                          # WHERE symbol =
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else None
        except Exception:
            conn.rollback()
            raise

    def fetch_trades(
        self,
        symbol: str | None = None,
        status: str = "all",
        limit: int = 50,
    ) -> list[dict]:
        """Return trades, most-recent first. status: 'open' | 'closed' | 'all'."""
        filters = []
        params: list = []
        if symbol:
            filters.append("symbol = %s")
            params.append(symbol)
        if status == "open":
            filters.append("exit_time IS NULL")
        elif status == "closed":
            filters.append("exit_time IS NOT NULL")
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT id, symbol, signal_id, decision_id, entry_order_id,
                               entry_price, entry_time, entry_notional, score, regime_mult,
                               exit_price, exit_time, exit_reason, qty,
                               gross_pnl, slippage_est, net_pnl, postmortem_diagnosis, created_at
                        FROM trades {where}
                        ORDER BY entry_time DESC LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    _TRADE_SUMMARY_SQL = """
        SELECT
            COUNT(*) AS total_trades,
            SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) AS wins,
            COALESCE(AVG(gross_pnl), 0) AS avg_gross_pnl,
            COALESCE(AVG(slippage_est), 0) AS avg_slippage_est,
            COALESCE(AVG(net_pnl), 0) AS avg_net_pnl,
            COALESCE(SUM(gross_pnl), 0) AS total_gross_pnl,
            COALESCE(SUM(net_pnl), 0) AS total_net_pnl,
            COALESCE(SUM(entry_notional), 0) AS total_notional,
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (exit_time - entry_time)) / 60), 0
            ) AS avg_hold_minutes,
            COALESCE(AVG(cost_bps), 0) AS avg_cost_bps,
            COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
            COALESCE(AVG(spread_cost_bps), 0) AS avg_spread_cost_bps,
            COALESCE(AVG(impact_cost_bps), 0) AS avg_impact_cost_bps
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
    """

    def fetch_trade_summary(self, days: int = 7) -> dict:
        """Return aggregated P&L metrics for closed trades in the last `days` days."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._TRADE_SUMMARY_SQL, (str(days),))
                row = cur.fetchone()
            if not row:
                return {k: 0 for k in [
                    "total_trades", "win_rate", "avg_gross_pnl", "avg_slippage_est",
                    "avg_net_pnl", "total_gross_pnl", "total_net_pnl",
                    "total_notional", "avg_hold_minutes", "trades_per_week",
                    "return_on_notional", "slippage_pct_of_gross",
                    "avg_cost_bps", "total_cost_usd", "avg_spread_cost_bps",
                    "avg_impact_cost_bps", "cost_drag_pct",
                ]}
            (total, wins, avg_gross, avg_slip, avg_net,
             total_gross, total_net, total_notional, avg_hold,
             avg_cost_bps, total_cost_usd, avg_spread_bps, avg_impact_bps) = row
            total = int(total)
            wins = int(wins or 0)
            win_rate = (wins / total) if total > 0 else 0.0
            trades_per_week = (total / days) * 7
            return_on_notional = (float(total_net) / float(total_notional)) if total_notional else 0.0
            slippage_pct = (float(avg_slip) / float(avg_gross)) if avg_gross else 0.0
            cost_drag_pct = (float(total_cost_usd) / float(total_notional)) if total_notional else 0.0
            return {
                "total_trades": total,
                "win_rate": round(win_rate, 4),
                "avg_gross_pnl": round(float(avg_gross), 2),
                "avg_slippage_est": round(float(avg_slip), 2),
                "avg_net_pnl": round(float(avg_net), 2),
                "total_gross_pnl": round(float(total_gross), 2),
                "total_net_pnl": round(float(total_net), 2),
                "total_notional": round(float(total_notional), 2),
                "avg_hold_minutes": round(float(avg_hold), 1),
                "trades_per_week": round(trades_per_week, 1),
                "return_on_notional": round(return_on_notional, 4),
                "slippage_pct_of_gross": round(slippage_pct, 4),
                "avg_cost_bps": round(float(avg_cost_bps), 2),
                "total_cost_usd": round(float(total_cost_usd), 2),
                "avg_spread_cost_bps": round(float(avg_spread_bps), 2),
                "avg_impact_cost_bps": round(float(avg_impact_bps), 2),
                "cost_drag_pct": round(cost_drag_pct, 6),
            }
        except Exception:
            conn.rollback()
            raise

    def fetch_llm_budget_period(self, days: int = 30) -> float:
        """Return total LLM API spend (USD) over the last `days` days from llm_budget table."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(total_spent_usd), 0.0) FROM llm_budget"
                    " WHERE date >= CURRENT_DATE - (%s || ' days')::interval",
                    (str(days),),
                )
                row = cur.fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            conn.rollback()
            raise

    def reconcile_trade_fills(self, trading_client) -> int:
        """Fetch fill prices from Alpaca for trades where entry_price IS NULL.

        Called daily (run_daily_report). Returns the count of rows updated.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, entry_order_id FROM trades
                       WHERE entry_price IS NULL
                         AND entry_time > now() - '24 hours'::interval"""
                )
                rows = cur.fetchall()
            updated = 0
            for trade_id, order_id in rows:
                try:
                    order = trading_client.get_order_by_id(order_id)
                    if order.filled_avg_price is None:
                        continue
                    fill_price = float(order.filled_avg_price)
                    fill_qty = float(order.filled_qty) if order.filled_qty else None
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE trades SET entry_price = %s, qty = %s WHERE id = %s",
                            (fill_price, fill_qty, trade_id),
                        )
                    updated += 1
                except Exception as e:
                    log.warning("Failed to reconcile order %s: %s", order_id, e)
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise

    def log_llm_responses(self, signal_id: int, outputs: list[ModelOutput]) -> None:
        """Write per-model outputs to llm_responses. No-op for empty list."""
        if not outputs:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                for out in outputs:
                    cur.execute(
                        self._INSERT_LLM_RESPONSE,
                        (
                            signal_id,
                            out.model_id,
                            out.polarity,
                            out.confidence,
                            out.reasoning,
                            True,
                        ),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_news_recent(
        self,
        limit: int = 100,
        ticker: str | None = None,
        source: str | None = None,
    ) -> list[dict]:
        """Return recent news_log rows as dicts, newest first."""
        filters = []
        params: list = []
        if ticker:
            filters.append("ticker = %s")
            params.append(ticker)
        if source:
            filters.append("source = %s")
            params.append(source)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, title, url, source, ticker, raw_sentiment, fetched_at "
                    f"FROM news_log {where} ORDER BY fetched_at DESC LIMIT %s",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def get_llm_feedback(
        self,
        limit: int = 50,
        ticker: str | None = None,
        model_id: str | None = None,
    ) -> list[dict]:
        """Return recent llm_responses joined with sentiment_signals, newest first."""
        filters = []
        params: list = []
        if ticker:
            filters.append("s.symbol = %s")
            params.append(ticker)
        if model_id:
            filters.append("r.model_id = %s")
            params.append(model_id)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT r.id, r.signal_id, s.symbol, r.model_id, r.polarity,
                           r.confidence, r.reasoning, r.eligible, r.generated_at,
                           s.fallback_used, s.ensemble_std
                    FROM llm_responses r
                    JOIN sentiment_signals s ON s.id = r.signal_id
                    {where}
                    ORDER BY r.generated_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    # FIX: Use timedelta from Python instead of string interpolation
    # Original vulnerable code:
    #   def fetch_signals_for_ic(self, symbol: str, days: int) -> list[tuple]:
    #       cur.execute(_FETCH_FOR_IC, (symbol, days))  # days interpolated into SQL
    #
    # Fixed: Convert days to string and use PostgreSQL interval arithmetic
    def fetch_signals_for_ic(self, symbol: str, days: int) -> list[tuple[Any, ...]]:
        """
        Fetch signals for IC calculation.

        FIX: Uses parameterized query with interval arithmetic to prevent SQL injection.

        Args:
            symbol: Asset symbol to fetch signals for
            days: Number of days of history to fetch

        Returns:
            List of (score, confidence, forward_return, generated_at, model_id, fallback_used) tuples
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_FOR_IC, (symbol, str(days)))
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise

    _FETCH_PER_MODEL_FOR_IC = """
        SELECT r.model_id,
               r.polarity * r.confidence AS score,
               s.forward_return
        FROM llm_responses r
        JOIN sentiment_signals s ON s.id = r.signal_id
        WHERE s.symbol = %s
          AND s.generated_at >= now() - (%s || ' days')::interval
          AND s.forward_return IS NOT NULL
          AND s.fallback_used = FALSE
          AND r.eligible = TRUE
        ORDER BY s.generated_at ASC
    """

    def fetch_per_model_signals_for_ic(self, symbol: str, days: int) -> list[tuple]:
        """Fetch per-model (model_id, score, forward_return) for LOO ICIR.

        Queries llm_responses joined with sentiment_signals so each individual
        model output is aligned with the parent signal's forward return.
        sentiment_signals.model_id stores a compound ensemble ID and cannot be
        used for per-model grouping; this method uses the correct source.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_PER_MODEL_FOR_IC, (symbol, str(days)))
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise

    _FETCH_RECENT_SIGNALS = """
        SELECT score, model_id
        FROM sentiment_signals
        WHERE generated_at >= now() - (%s || ' hours')::interval
          AND fallback_used = FALSE
        ORDER BY generated_at ASC
    """

    def fetch_signals_last_hours(self, hours: int) -> list[tuple]:
        """Fetch (score, model_id) for all non-fallback signals in the last N hours."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_RECENT_SIGNALS, (str(hours),))
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise

    _FETCH_SIGNALS_FOR_CYCLE = """
        SELECT DISTINCT ON (symbol)
            symbol, score, confidence,
            COALESCE(reasoning, '') AS reasoning,
            model_id, ensemble_std, fallback_used, generated_at
        FROM sentiment_signals
        WHERE generated_at >= NOW() - (%s || ' hours')::interval
          AND symbol = ANY(%s)
        ORDER BY symbol, generated_at DESC
    """

    def fetch_signals_for_cycle(
        self, hours: int = 4, symbols: list[str] | None = None
    ) -> list[SentimentResult]:
        """Fetch the latest signal per symbol from the last N hours.

        Used by the live portfolio cycle to load fresh signals for S4.
        Only returns signals for symbols in the provided list (watchlist) so
        that off-watchlist tickers don't consume ranking slots in S4 and then
        get silently dropped when no market price is available.

        Returns SentimentResult objects with timezone-aware generated_at.
        """
        from datetime import timezone as _tz

        watchlist = symbols or []
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(self._FETCH_SIGNALS_FOR_CYCLE, (str(hours), watchlist))
                rows = cur.fetchall()
        except Exception:
            conn.rollback()
            raise

        results = []
        for row in rows:
            generated_at = row["generated_at"]
            if generated_at is not None and generated_at.tzinfo is None:
                generated_at = generated_at.replace(tzinfo=_tz.utc)
            results.append(
                SentimentResult(
                    symbol=row["symbol"],
                    score=float(row["score"]),
                    confidence=float(row["confidence"]),
                    reasoning=row.get("reasoning") or "",
                    model_id=row.get("model_id") or "unknown",
                    ensemble_std=float(row.get("ensemble_std") or 0.0),
                    fallback_used=bool(row.get("fallback_used", False)),
                    generated_at=generated_at,
                )
            )
        return results

    def fetch_latest_signal_ids(self, symbols: list[str], hours: int = 24) -> dict[str, int]:
        """Return {symbol: latest_signal_id} for the given symbols within the last N hours."""
        if not symbols:
            return {}
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT DISTINCT ON (symbol) symbol, id
                       FROM sentiment_signals
                       WHERE symbol = ANY(%s)
                         AND generated_at >= now() - (%s || ' hours')::interval
                       ORDER BY symbol, generated_at DESC""",
                    (symbols, str(hours)),
                )
                return {row[0]: row[1] for row in cur.fetchall()}
        except Exception:
            conn.rollback()
            raise

    def fetch_signals_for_backtest(
        self, symbol: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """
        Fetch signals for backtesting within a date range.

        Args:
            symbol: Asset symbol
            start_date: ISO format start date
            end_date: ISO format end date

        Returns:
            List of signal dictionaries
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT symbol, score, confidence, reasoning, model_id,
                           ensemble_std, fallback_used, generated_at
                    FROM sentiment_signals
                    WHERE symbol = %s
                      AND generated_at >= %s
                      AND generated_at <= %s
                    ORDER BY generated_at ASC
                    """,
                    (symbol, start_date, end_date),
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def add_forward_return(self, signal_id: int, forward_return: float) -> None:
        """Add forward return to a signal (called by performance worker)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sentiment_signals
                    SET forward_return = %s
                    WHERE id = %s
                    """,
                    (forward_return, signal_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def fetch_signals_pending_forward_return(
        self, days_back: int = 60
    ) -> list[tuple]:
        """Fetch signals that need a forward return populated.

        Returns (id, symbol, generated_at) for non-fallback signals that:
          - Have no forward_return yet
          - Are older than 1 day (need next trading day to have closed)
          - Are within days_back days (avoid re-processing old history)

        Args:
            days_back: Maximum lookback window in days (default 60).
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, symbol, generated_at
                    FROM sentiment_signals
                    WHERE forward_return IS NULL
                      AND fallback_used = false
                      AND generated_at < NOW() - INTERVAL '1 day'
                      AND generated_at > NOW() - INTERVAL '1 day' * %s
                    ORDER BY symbol, generated_at
                    """,
                    (days_back,),
                )
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise
    def fetch_latest_signals(self, symbols: list[str]) -> list[dict]:
        """Fetch the latest signal for each symbol from PostgreSQL.

        Used as fallback when Redis cache has expired.
        Returns list of dicts matching the Redis sentiment signal format.
        """
        if not symbols:
            return []
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                placeholders = ", ".join(["%s"] * len(symbols))
                cur.execute(
                    "SELECT DISTINCT ON (symbol) "
                    "  symbol, score, confidence, reasoning, "
                    "  model_id, ensemble_std, fallback_used, generated_at "
                    "FROM sentiment_signals "
                    "WHERE symbol IN (" + placeholders + ") "
                    "ORDER BY symbol, generated_at DESC",
                    tuple(symbols)
                )
                rows = cur.fetchall()
                results = []
                for row in rows:
                    d = dict(row)
                    if d.get("generated_at") is not None:
                        d["generated_at"] = d["generated_at"].isoformat()
                    results.append(d)
                return results
        except Exception:
            conn.rollback()
            raise

    def bulk_add_forward_returns(
        self, updates: list[tuple[int, float]]
    ) -> int:
        """Update forward_return for multiple signals in a single transaction.

        Args:
            updates: List of (signal_id, forward_return) tuples.

        Returns:
            Number of rows updated.
        """
        if not updates:
            return 0
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE sentiment_signals SET forward_return = %s WHERE id = %s",
                    [(ret, sid) for sid, ret in updates],
                )
                updated = cur.rowcount
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise

    # -------------------------------------------------------------------------
    # Trade analytics (Phase A)
    # -------------------------------------------------------------------------

    _ANALYTICS_BY_SYMBOL = """
        SELECT
            symbol AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
        GROUP BY symbol
        ORDER BY total_net_pnl DESC
    """

    _ANALYTICS_BY_REGIME = """
        SELECT
            CASE
                WHEN regime_mult <= 0.6  THEN 'bear'
                WHEN regime_mult <= 0.9  THEN 'caution'
                WHEN regime_mult <= 1.1  THEN 'neutral'
                WHEN regime_mult <= 1.35 THEN 'bull'
                ELSE 'strong_bull'
            END AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
        GROUP BY CASE
            WHEN regime_mult <= 0.6  THEN 'bear'
            WHEN regime_mult <= 0.9  THEN 'caution'
            WHEN regime_mult <= 1.1  THEN 'neutral'
            WHEN regime_mult <= 1.35 THEN 'bull'
            ELSE 'strong_bull'
        END
        ORDER BY avg_net_pnl DESC
    """

    _ANALYTICS_BY_HOUR = """
        SELECT
            EXTRACT(HOUR FROM entry_time AT TIME ZONE 'America/New_York')::int::text AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
        GROUP BY EXTRACT(HOUR FROM entry_time AT TIME ZONE 'America/New_York')::int
        ORDER BY EXTRACT(HOUR FROM entry_time AT TIME ZONE 'America/New_York')::int
    """

    _ANALYTICS_BY_SCORE_BUCKET = """
        SELECT
            TO_CHAR(FLOOR(ss.score * 10) * 0.1::numeric, 'FM0.0') || '–' ||
            TO_CHAR((FLOOR(ss.score * 10) * 0.1::numeric + 0.1), 'FM0.0') AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN t.net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(t.net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(t.net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades t
        JOIN sentiment_signals ss ON ss.id = t.signal_id
        WHERE t.exit_time IS NOT NULL
          AND t.exit_time >= now() - (%s || ' days')::interval
          AND t.signal_id IS NOT NULL
        GROUP BY FLOOR(ss.score * 10)
        ORDER BY FLOOR(ss.score * 10)
    """

    _ANALYTICS_BY_HOLD_TIME = """
        SELECT
            CASE
                WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 3600
                    THEN '<1h'
                WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 14400
                    THEN '1-4h'
                WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 28800
                    THEN '4-8h'
                WHEN DATE(exit_time AT TIME ZONE 'America/New_York')
                   > DATE(entry_time AT TIME ZONE 'America/New_York')
                    THEN 'overnight'
                ELSE 'extended'
            END AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
        GROUP BY CASE
            WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 3600
                THEN '<1h'
            WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 14400
                THEN '1-4h'
            WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 28800
                THEN '4-8h'
            WHEN DATE(exit_time AT TIME ZONE 'America/New_York')
               > DATE(entry_time AT TIME ZONE 'America/New_York')
                THEN 'overnight'
            ELSE 'extended'
        END
        ORDER BY avg_net_pnl DESC
    """

    def _fetch_analytics(self, sql: str, limit_days: int) -> list[dict]:
        """Shared executor for all analytics queries."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (str(limit_days),))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def fetch_analytics_by_symbol(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by symbol."""
        return self._fetch_analytics(self._ANALYTICS_BY_SYMBOL, limit_days)

    def fetch_analytics_by_regime(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by regime multiplier bucket."""
        return self._fetch_analytics(self._ANALYTICS_BY_REGIME, limit_days)

    def fetch_analytics_by_hour(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by hour of day (EST, 9-16)."""
        return self._fetch_analytics(self._ANALYTICS_BY_HOUR, limit_days)

    def fetch_analytics_by_score_bucket(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by 0.1-wide LLM score bins."""
        return self._fetch_analytics(self._ANALYTICS_BY_SCORE_BUCKET, limit_days)

    def fetch_analytics_by_hold_time(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by hold duration bucket."""
        return self._fetch_analytics(self._ANALYTICS_BY_HOLD_TIME, limit_days)

    _FETCH_TRADE_WITH_SIGNAL = """
        SELECT
            t.id, t.symbol, t.entry_time, t.exit_time,
            t.entry_price, t.exit_price, t.net_pnl,
            t.score, t.regime_mult, t.exit_reason,
            ss.confidence, ss.ensemble_std,
            ss.generated_at AS signal_generated_at,
            t.postmortem_diagnosis
        FROM trades t
        LEFT JOIN sentiment_signals ss ON ss.id = t.signal_id
        WHERE t.id = %s
    """

    def fetch_trade_with_signal(self, trade_id: int) -> dict | None:
        """Return a trade row joined with its signal's confidence/ensemble_std."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_TRADE_WITH_SIGNAL, (trade_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
        except Exception:
            conn.rollback()
            raise

    def write_postmortem(self, trade_id: int, diagnosis: str) -> None:
        """Store postmortem diagnosis for a closed trade."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE trades SET postmortem_diagnosis = %s WHERE id = %s",
                    (diagnosis, trade_id),
                )
                if cur.rowcount == 0:
                    log.warning("write_postmortem: no trade row found for id=%s", trade_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def log_weight_update(
        self,
        source: str,
        applied_weights: dict,
        suggested_weights: dict | None = None,
        purified_icir: dict | None = None,
        freeze_reason: str | None = None,
        note: str | None = None,
        approved_by: str | None = None,
    ) -> int:
        """Write a row to weight_update_log and return the generated id."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_WEIGHT_LOG,
                    (
                        source,
                        json.dumps(applied_weights),
                        json.dumps(suggested_weights) if suggested_weights is not None else None,
                        json.dumps(purified_icir) if purified_icir is not None else None,
                        freeze_reason,
                        note,
                        approved_by,
                    ),
                )
                log_id: int = cur.fetchone()[0]
            conn.commit()
            return log_id
        except Exception:
            conn.rollback()
            raise

    def delete_old_news_log(self, older_than_days: int) -> int:
        """Delete news_log rows older than given days. Returns deleted count."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM news_log WHERE fetched_at < now() - (%s || ' days')::interval",
                    (str(older_than_days),),
                )
                deleted = cur.rowcount
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise

    def delete_old_llm_responses(self, older_than_days: int) -> int:
        """Delete llm_responses rows older than given days. Returns deleted count."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM llm_responses WHERE generated_at < now() - (%s || ' days')::interval",
                    (str(older_than_days),),
                )
                deleted = cur.rowcount
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise


    def get_last_portfolio_cycle(self) -> dict | None:
        """Return the most recent portfolio cycle, or None if no cycles exist."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timestamp, strategies_run, orders_count, constraints_fired, final_orders "
                    "FROM portfolio_cycles ORDER BY timestamp DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "strategies_run": row[1] if isinstance(row[1], list) else [],
                    "orders_count": row[2] or 0,
                    "constraints_fired": row[3] if isinstance(row[3], list) else [],
                    "final_orders": row[4] if isinstance(row[4], list) else [],
                }
        except Exception:
            conn.rollback()
            return None

    def get_portfolio_cycle_history(self, limit: int = 30) -> list[dict]:
        """Return the last N portfolio cycles, newest first."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timestamp, strategies_run, orders_count, constraints_fired, final_orders "
                    "FROM portfolio_cycles ORDER BY timestamp DESC LIMIT %s",
                    (limit,)
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    result.append({
                        "timestamp": row[0].isoformat() if row[0] else None,
                        "strategies_run": row[1] if isinstance(row[1], list) else [],
                        "orders_count": row[2] or 0,
                        "constraints_fired": row[3] if isinstance(row[3], list) else [],
                        "final_orders": row[4] if isinstance(row[4], list) else [],
                    })
                return result
        except Exception:
            conn.rollback()
            return []

    def __del__(self) -> None:
        """Return pooled connection to pool on GC if close() was not called."""
        try:
            if self._conn is not None:
                self._release_connection(self._conn)
                self._conn = None
        except Exception:
            pass

    def __enter__(self) -> "PostgreSQLStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, rolling back on exception if connection owned."""
        if exc_type is not None and self._conn is not None:
            self._conn.rollback()
        self.close()
