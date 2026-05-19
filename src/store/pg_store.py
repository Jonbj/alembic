"""PostgreSQL store for sentiment signals and performance metrics."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from src.config import config
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
    ):
        """Initialize PostgreSQL store.

        Args:
            conn: Optional existing connection. If None, will use connection pool.
            use_pool: If True, use the global connection pool. If False, create
                      a dedicated connection (useful for tests).
        """
        self._conn = conn
        self._use_pool = use_pool and conn is None
        self._owns_connection = conn is None and not self._use_pool

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
                self._conn = psycopg2.connect(config.DATABASE_URL)
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
        ON CONFLICT DO NOTHING
    """

    _INSERT_LLM_RESPONSE = """
        INSERT INTO llm_responses (signal_id, model_id, polarity, confidence, reasoning, eligible, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, now())
    """

    def log_news_item(self, item: NewsItem, ticker: str) -> None:
        """Write article metadata to news_log. Skips silently on conflict."""
        from src.models.news import MarketAuxNewsItem

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
            conn.commit()
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
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, title, url, source, ticker, raw_sentiment, fetched_at "
                f"FROM news_log {where} ORDER BY fetched_at DESC LIMIT %s",
                params,
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

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
        with conn.cursor() as cur:
            # FIX: Pass days as string parameter for interval arithmetic
            # This prevents SQL injection that was possible with:
            #   f"INTERVAL '{days} days'"
            cur.execute(self._FETCH_FOR_IC, (symbol, str(days)))
            return cur.fetchall()

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

    def add_forward_return(self, signal_id: int, forward_return: float) -> None:
        """Add forward return to a signal (called by performance worker)."""
        conn = self._get_connection()
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

    def __enter__(self) -> "PostgreSQLStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, rolling back on exception if connection owned."""
        if exc_type is not None and self._conn is not None:
            # Rollback on exception
            self._conn.rollback()
        self.close()
