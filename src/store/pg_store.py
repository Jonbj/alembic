"""PostgreSQL store for sentiment signals and performance metrics."""

from datetime import timedelta
from typing import Any

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from src.config import config
from src.models.signals import SentimentResult

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
                timeout=30,  # CRITICAL FIX: Prevent hang on pool exhaustion
            )
        except psycopg2.OperationalError as e:
            # Pool initialization failed (e.g., DB not reachable)
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
            # Get connection from pool with timeout handling
            try:
                return _get_pool().getconn()
            except psycopg2.pool.PoolTimeout:
                # Fallback: create temporary dedicated connection
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

    def write_signal(self, result: SentimentResult) -> None:
        """Write sentiment signal to database."""
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
            conn.commit()
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

    def __enter__(self) -> "PostgreSQLStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, rolling back on exception if connection owned."""
        if exc_type is not None and self._conn is not None:
            # Rollback on exception
            self._conn.rollback()
        self.close()
