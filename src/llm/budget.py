"""LLM Budget tracking and enforcement."""

import asyncio
from datetime import date, datetime, timezone
from typing import Literal

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from src.config import config


class LLMBudgetExhaustedError(Exception):
    """Raised when LLM daily budget is exhausted."""

    pass


def _get_pool() -> pool.ThreadedConnectionPool:
    """Get the global connection pool (shared with pg_store)."""
    # Import here to avoid circular dependency
    from src.store.pg_store import _get_pool as get_pg_pool
    return get_pg_pool()


class LLMBudgetTracker:
    """
    Track and enforce daily LLM spending budget.

    Features:
    - Tracks spending per day in PostgreSQL
    - Estimates cost based on prompt/response token counts
    - Blocks calls when budget exhausted (fallback to FinBERT)
    - Thread-safe via database row-level locking
    - Uses connection pooling for efficient resource management

    Usage:
        tracker = LLMBudgetTracker()
        try:
            await tracker.check_budget()  # Raises if exhausted
            # ... make LLM call ...
            await tracker.record_spending(
                model_id="opus",
                input_tokens=1500,
                output_tokens=500
            )
        except LLMBudgetExhaustedError:
            # Fall back to FinBERT
            pass
    """

    def __init__(
        self,
        conn: psycopg2.extensions.connection | None = None,
        use_pool: bool = True,
    ):
        """Initialize budget tracker.

        Args:
            conn: Optional PostgreSQL connection. If None, uses connection pool.
            use_pool: If True, use the global connection pool.
        """
        self._conn = conn
        self._use_pool = use_pool and conn is None
        self._owns_connection = conn is None and not self._use_pool
        self._daily_limit = config.LLM_DAILY_BUDGET_USD
        self._model_costs = config.MODEL_COSTS

    def _get_connection(self) -> psycopg2.extensions.connection:
        """Get or create database connection."""
        if self._conn is not None:
            return self._conn

        if self._use_pool:
            return _get_pool().getconn()

        # Fallback to dedicated connection
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

    async def check_budget(self) -> Literal["ok", "exhausted"]:
        """
        Check if budget is exhausted for today.

        Returns:
            "ok" if budget available, "exhausted" if over limit.

        Raises:
            LLMBudgetExhaustedError: If budget is exhausted.
        """
        conn = self._get_connection()

        def _check() -> Literal["ok", "exhausted"]:
            today = date.today()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT total_spent_usd, budget_exhausted
                    FROM llm_budget
                    WHERE date = %s
                    FOR UPDATE  -- Row-level lock for thread safety
                    """,
                    (today,),
                )
                row = cur.fetchone()

                if row is None:
                    # No row yet = no spending = ok
                    return "ok"

                if row["budget_exhausted"]:
                    return "exhausted"

                if row["total_spent_usd"] >= self._daily_limit:
                    return "exhausted"

                return "ok"

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _check)

        if result == "exhausted":
            raise LLMBudgetExhaustedError(
                f"Daily LLM budget of ${self._daily_limit:.2f} exhausted"
            )

        return result

    async def record_spending(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Record spending for an LLM call.

        Args:
            model_id: Model identifier (e.g., "opus", "qwen3.5:cloud")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Total spent today after this recording
        """
        # Get model costs (default to sonnet pricing if unknown)
        costs = self._model_costs.get(model_id, (3.0, 15.0))
        input_cost_per_m = costs[0]
        output_cost_per_m = costs[1]

        # Calculate cost for this call
        call_cost = (
            (input_tokens / 1_000_000) * input_cost_per_m
            + (output_tokens / 1_000_000) * output_cost_per_m
        )

        conn = self._get_connection()
        today = date.today()

        def _record() -> float:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Upsert today's row
                cur.execute(
                    """
                    INSERT INTO llm_budget (date, total_spent_usd, token_count_input, token_count_output)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (date) DO UPDATE SET
                        total_spent_usd = llm_budget.total_spent_usd + %s,
                        token_count_input = llm_budget.token_count_input + %s,
                        token_count_output = llm_budget.token_count_output + %s,
                        updated_at = now()
                    RETURNING total_spent_usd
                    """,
                    (
                        today,
                        call_cost,
                        input_tokens,
                        output_tokens,
                        call_cost,
                        input_tokens,
                        output_tokens,
                    ),
                )
                row = cur.fetchone()

                # Check if we just exceeded budget
                if row and row["total_spent_usd"] >= self._daily_limit:
                    cur.execute(
                        """
                        UPDATE llm_budget
                        SET budget_exhausted = TRUE,
                            exhausted_at = now()
                        WHERE date = %s
                        """,
                        (today,),
                    )

            conn.commit()
            return row["total_spent_usd"] if row else call_cost

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _record)

    async def get_remaining_budget(self) -> float:
        """Get remaining budget for today."""
        conn = self._get_connection()

        def _get_remaining() -> float:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT total_spent_usd FROM llm_budget WHERE date = %s",
                    (date.today(),),
                )
                row = cur.fetchone()

            if row is None:
                return self._daily_limit

            spent = row["total_spent_usd"] or 0.0
            return max(0.0, self._daily_limit - spent)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _get_remaining)

    async def reset_budget(self) -> None:
        """
        Reset budget for today (admin operation).

        Should be called at midnight or by admin to restore access.
        """
        conn = self._get_connection()
        today = date.today()

        def _reset() -> None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llm_budget (date, total_spent_usd)
                    VALUES (%s, 0.0)
                    ON CONFLICT (date) DO UPDATE SET
                        budget_exhausted = FALSE,
                        exhausted_at = NULL,
                        total_spent_usd = 0.0,
                        updated_at = now()
                    """,
                    (today,),
                )
            conn.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _reset)

    def __enter__(self) -> "LLMBudgetTracker":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
