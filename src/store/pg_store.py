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

# Stage-2 shadow-mode model comparison (src/workers/performance.run_shadow_comparison_report
# and scripts/report_model_comparison.py): fetch_shadow_rows/fetch_live_response_rows both
# return plain tuples, positionally aligned to this column order, which both callers use to
# build a pandas DataFrame. This is the single source of truth for that order — if either
# _FETCH_SHADOW_ROWS or _FETCH_LIVE_RESPONSE_ROWS SELECT column order changes below, this
# list (and any caller still hardcoding its own copy) must change with it, or the DataFrame
# silently misaligns (no error — just wrong IC/hit-rate numbers).
SHADOW_COMPARISON_COLUMNS = ["news_log_id", "model_id", "polarity", "confidence", "parse_error"]


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
            ensemble_std, fallback_used, generated_at, published_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        """Return connection to pool if using pooling.

        B7/B32 (2026-07-15): rollback before returning/closing so a connection
        left 'idle in transaction' by a read-only method (load_frozen_stop,
        fetch_open_trade_meta) is cleaned before it goes back into the pool —
        otherwise putconn returns a dirty connection and the next user inherits
        an open transaction. Seen live: 20 leaked idle-in-transaction conns.

        Only rolled back on paths we actually release (pool / owned). An
        externally-supplied connection (conn=..., use_pool=False) is not ours
        to roll back or close — the caller owns its transaction lifecycle.
        """
        if conn is None:
            return
        if self._use_pool:
            try:
                conn.rollback()
            except Exception:
                pass
            _get_pool().putconn(conn)
        elif self._owns_connection:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()

    def close(self) -> None:
        """Close connection or return it to pool."""
        if self._conn is not None:
            self._release_connection(self._conn)
            self._conn = None

    def rollback(self) -> None:
        """Rollback the current transaction WITHOUT releasing the connection.

        For callers that loop over multiple independent writes (the portfolio
        scheduler's per-order trade-write loop, B33): if one order's write
        throws, psycopg2 leaves the connection in 'current transaction is
        aborted' state and every subsequent command fails until rolled back.
        Rolling back here clears that state so the next order can proceed on
        the same connection. Idempotent and safe after a commit (no-ops a fresh
        transaction). Does NOT close/return the connection — call close() when
        the loop is done.
        """
        if self._conn is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass

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
                        result.published_at,
                    ),
                )
                row = cur.fetchone()
                signal_id: int = row[0]
            conn.commit()
            return signal_id
        except Exception:
            conn.rollback()
            raise

    _UPSERT_FALLBACK_INCREMENT = """
        INSERT INTO fallback_counters (counter_name, counter_value, last_increment_at)
        VALUES (%s, %s, now())
        ON CONFLICT (counter_name) DO UPDATE
        SET counter_value = EXCLUDED.counter_value, last_increment_at = now()
    """

    def record_fallback_increment(self, counter_name: str, value: int) -> None:
        """Persist the consecutive-fallback count (audit/durability alongside Redis)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._UPSERT_FALLBACK_INCREMENT, (counter_name, value))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    _UPSERT_FALLBACK_RESET = """
        INSERT INTO fallback_counters (counter_name, counter_value, reset_at)
        VALUES (%s, 0, now())
        ON CONFLICT (counter_name) DO UPDATE
        SET counter_value = 0, reset_at = now()
    """

    def record_fallback_reset(self, counter_name: str) -> None:
        """Persist a fallback-counter reset (audit/durability alongside Redis)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._UPSERT_FALLBACK_RESET, (counter_name,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    _INSERT_NEWS_LOG = """
        INSERT INTO news_log (title, url, source, ticker, body_snippet, raw_sentiment, published_at, extraction_method, raw_ingested_at, content_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url, ticker) DO NOTHING
        RETURNING id
    """

    _INSERT_LLM_RESPONSE = """
        INSERT INTO llm_responses (signal_id, model_id, polarity, confidence, reasoning, eligible, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, now())
    """

    _INSERT_SHADOW_RESPONSE = """
        INSERT INTO llm_shadow_responses
            (news_log_id, symbol, model_id, polarity, confidence, reasoning,
             parse_error, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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

        from src.connectors.deduplicator import compute_dedup_hash
        try:
            content_hash = compute_dedup_hash(item)
        except Exception:
            content_hash = None

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
                        getattr(item, "extraction_method", "") or None,
                        item.raw_ingested_at,
                        content_hash,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    # QS-09: ON CONFLICT DO NOTHING returned no id (this (url, ticker)
                    # was already in news_log from a previous fetch). Look up the
                    # existing row so the signal still links to its news (otherwise
                    # news_log_id stays NULL and breaks auditability/joins).
                    cur.execute(
                        "SELECT id FROM news_log WHERE url = %s AND ticker = %s",
                        (item.url[:1000] if item.url else "", ticker),
                    )
                    row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else None
        except Exception:
            conn.rollback()
            raise

    # EN-06: canonical funnel counters ← worker stats-dict synonyms.
    # "discarded" (GKG worker) and "filtered" (RSS/EDGAR workers) are the REAL keys
    # found in src/workers/ingestion.py for no-ticker-match discards (there is no
    # separate discarded_stale/parse_fail counter yet — those stay 0 until S2-2).
    _INGESTION_STAT_SYNONYMS: dict[str, tuple[str, ...]] = {
        "fetched": ("fetched", "total_fetched", "items_fetched", "total"),
        "queued": ("queued", "pushed", "enqueued"),
        "duplicates": ("duplicates", "skipped_duplicate", "dupes"),
        "discarded_no_ticker": (
            "discarded_no_ticker", "skipped_no_ticker", "no_ticker", "no_asset_tags",
            "discarded", "filtered",
        ),
        "discarded_stale": ("discarded_stale", "skipped_stale", "stale"),
        "parse_fail": ("parse_fail", "parse_errors", "errors"),
    }

    _UPSERT_INGESTION_STATS = """
        INSERT INTO ingestion_stats_daily
            (day, source, fetched, queued, duplicates,
             discarded_no_ticker, discarded_stale, parse_fail, updated_at)
        VALUES (CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (day, source) DO UPDATE SET
            fetched             = ingestion_stats_daily.fetched + EXCLUDED.fetched,
            queued              = ingestion_stats_daily.queued + EXCLUDED.queued,
            duplicates          = ingestion_stats_daily.duplicates + EXCLUDED.duplicates,
            discarded_no_ticker = ingestion_stats_daily.discarded_no_ticker + EXCLUDED.discarded_no_ticker,
            discarded_stale     = ingestion_stats_daily.discarded_stale + EXCLUDED.discarded_stale,
            parse_fail          = ingestion_stats_daily.parse_fail + EXCLUDED.parse_fail,
            updated_at          = now()
    """

    def record_ingestion_stats(self, source: str, stats: dict) -> None:
        """Upsert-increment today's funnel counters for a source. Fail-safe: never raises."""
        try:
            canon = {
                key: sum(int(stats.get(s, 0) or 0) for s in synonyms)
                for key, synonyms in self._INGESTION_STAT_SYNONYMS.items()
            }
            if not any(canon.values()):
                return
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    self._UPSERT_INGESTION_STATS,
                    (source, canon["fetched"], canon["queued"], canon["duplicates"],
                     canon["discarded_no_ticker"], canon["discarded_stale"], canon["parse_fail"]),
                )
            conn.commit()
        except Exception as exc:
            log.warning("record_ingestion_stats(%s) failed (fail-safe): %s", source, exc)

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
            (tick_time, symbol, signal_id, score, signal_score, regime_mult, ema_pass, decision, order_id, reason, exit_mechanism)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        signal_score: float | None = None,
        exit_mechanism: str | None = None,
    ) -> int:
        """Insert one execution decision row. Returns the new id.

        Args:
            score:          Portfolio allocation weight (e.g. 0.02 = 2% target weight).
            signal_score:   Actual LLM sentiment score that drove the decision (e.g. +0.707).
                            Stored separately from score so IC analytics can correlate
                            signal quality with subsequent returns.
            exit_mechanism: #60 — structured tag for weight-0 S4 SELL exits
                            ("no_signal" | "expired" | "whipsaw"). None for all
                            other decision types (BUY, stop_loss, sentiment_reversal, ...),
                            which already carry a clear, self-descriptive reason string.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_DECISION,
                    (tick_time, symbol, signal_id, score, signal_score, regime_mult, ema_pass, decision, order_id, reason, exit_mechanism),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row[0])
        except Exception:
            conn.rollback()
            raise

    _INSERT_RESOLVED_ENTITY = """
        INSERT INTO news_resolved_entities
            (news_log_id, url, candidate_ticker, extraction_method, decision,
             resolved_ticker, resolution_confidence, ambiguity_margin, directness,
             tradable, exchange, figi, source_ticker_match, alias_match,
             sec_openfigi_match, llm_agreement)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    def write_resolved_entity(
        self, *, candidate_ticker: str, extraction_method: str, verdict, evidence,
        url: str | None = None, news_log_id: int | None = None,
    ) -> None:
        """Persist a SHADOW resolver verdict to news_resolved_entities (offline only —
        never gates the live signal). ``verdict`` is a ResolvedTicker, ``evidence`` a
        ResolutionEvidence (src/connectors/ticker_resolver.py)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._INSERT_RESOLVED_ENTITY, (
                    news_log_id, url, candidate_ticker, extraction_method,
                    verdict.decision, verdict.resolved_ticker, verdict.resolution_confidence,
                    verdict.ambiguity_margin, verdict.directness, verdict.tradable,
                    verdict.exchange, verdict.figi, evidence.source_ticker_match,
                    evidence.alias_match, evidence.sec_openfigi_match, evidence.llm_agreement,
                ))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def update_decision_order_id(self, decision_id: int, order_id: str) -> None:
        """Back-fill the Alpaca order_id on an execution_decisions row after submission."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE execution_decisions SET order_id = %s WHERE id = %s",
                    (order_id, decision_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def fetch_order_trace(self, order_ids: list[str]) -> dict[str, dict]:
        """Return local Alembic trace metadata keyed by broker order id."""
        clean_order_ids = [str(order_id) for order_id in order_ids if order_id]
        if not clean_order_ids:
            return {}
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (order_id)
                           order_id, signal_id, decision_id, news_log_id, trade_id
                    FROM (
                        SELECT ed.order_id,
                               ed.signal_id,
                               ed.id AS decision_id,
                               ss.news_log_id,
                               NULL::BIGINT AS trade_id
                        FROM execution_decisions ed
                        LEFT JOIN sentiment_signals ss ON ss.id = ed.signal_id
                        WHERE ed.order_id = ANY(%s)

                        UNION ALL

                        SELECT t.entry_order_id AS order_id,
                               t.signal_id,
                               t.decision_id,
                               ss.news_log_id,
                               t.id AS trade_id
                        FROM trades t
                        LEFT JOIN sentiment_signals ss ON ss.id = t.signal_id
                        WHERE t.entry_order_id = ANY(%s)

                        UNION ALL

                        SELECT t.exit_order_id AS order_id,
                               t.signal_id,
                               t.decision_id,
                               ss.news_log_id,
                               t.id AS trade_id
                        FROM trades t
                        LEFT JOIN sentiment_signals ss ON ss.id = t.signal_id
                        WHERE t.exit_order_id = ANY(%s)
                    ) traces
                    WHERE order_id IS NOT NULL
                    ORDER BY order_id, trade_id NULLS LAST, decision_id NULLS LAST
                    """,
                    (clean_order_ids, clean_order_ids, clean_order_ids),
                )
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
                return {
                    row["order_id"]: {
                        "signal_id": int(row["signal_id"]) if row["signal_id"] is not None else None,
                        "decision_id": int(row["decision_id"]) if row["decision_id"] is not None else None,
                        "news_log_id": int(row["news_log_id"]) if row["news_log_id"] is not None else None,
                        "trade_id": int(row["trade_id"]) if row["trade_id"] is not None else None,
                    }
                    for row in rows
                }
        except Exception:
            conn.rollback()
            raise

    def fetch_decisions(
        self,
        symbol: str | None = None,
        decision_id: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Return decision log rows, most-recent first.

        Includes signal_generated_at (from sentiment_signals JOIN) so the UI
        can display the lag between signal generation and portfolio cycle decision.
        """
        filters = []
        params: list = []
        if symbol:
            filters.append("ed.symbol = %s")
            params.append(symbol)
        if decision_id is not None:
            filters.append("ed.id = %s")
            params.append(decision_id)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT ed.id, ed.tick_time, ed.symbol, ed.signal_id, ed.score,
                               ed.signal_score, ed.regime_mult, ed.ema_pass, ed.decision,
                               ed.order_id, ed.reason, ed.created_at,
                               ss.generated_at AS signal_generated_at,
                               ss.news_log_id
                        FROM execution_decisions ed
                        LEFT JOIN sentiment_signals ss ON ss.id = ed.signal_id
                        {where}
                        ORDER BY ed.tick_time DESC LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def fetch_signal_decision_status(self, signal_ids: list[int]) -> dict[int, dict]:
        """Return the first decision made for each signal_id (used_in_decision enrichment).

        Returns {signal_id: {used_in_decision: True, decision_id: int, decision_at: str, decision_type: str}}.
        Signal IDs not present in execution_decisions are absent from the result.
        """
        if not signal_ids:
            return {}
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                placeholders = ", ".join(["%s"] * len(signal_ids))
                cur.execute(
                    f"""SELECT DISTINCT ON (signal_id)
                               signal_id, id, tick_time, decision
                        FROM execution_decisions
                        WHERE signal_id IN ({placeholders})
                        ORDER BY signal_id, tick_time DESC""",
                    signal_ids,
                )
                result: dict[int, dict] = {}
                for row in cur.fetchall():
                    sid, decision_id, tick_time, decision = row
                    result[int(sid)] = {
                        "used_in_decision": True,
                        "decision_id": int(decision_id),
                        "decision_at": tick_time.isoformat() if tick_time else None,
                        "decision_type": decision,
                    }
                return result
        except Exception:
            conn.rollback()
            raise

    # --- Counterfactual (Phase C) ---

    def fetch_skip_decisions_without_counterfactual(
        self,
        days_back: int = 7,
        limit: int = 500,
    ) -> list[dict]:
        """Return trade-filter skip rows from the last N days that have no counterfactual yet."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, tick_time, symbol, score, regime_mult, decision
                       FROM execution_decisions
                       WHERE decision IN ('SKIP_THRESHOLD', 'SKIP_EMA', 'SKIP_CAP')
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
        WHERE decision IN ('SKIP_THRESHOLD', 'SKIP_EMA', 'SKIP_CAP')
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

    def fetch_counterfactual_status(self, days: int = 7) -> dict:
        """Return raw Phase C skip counts and processing coverage for the window."""
        phase_c_decisions = {"SKIP_THRESHOLD", "SKIP_EMA", "SKIP_CAP"}
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT
                           decision,
                           COUNT(*) AS total,
                           COUNT(counterfactual_computed_at) AS processed,
                           COUNT(counterfactual_return_1h) AS with_return,
                           SUM(CASE WHEN counterfactual_computed_at IS NULL THEN 1 ELSE 0 END) AS pending
                       FROM execution_decisions
                       WHERE decision LIKE 'SKIP_%%'
                         AND tick_time >= now() - (%s || ' days')::interval
                       GROUP BY decision
                       ORDER BY decision""",
                    (str(days),),
                )
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]

                cur.execute(
                    """SELECT MAX(counterfactual_computed_at)
                       FROM execution_decisions
                       WHERE decision IN ('SKIP_THRESHOLD', 'SKIP_EMA', 'SKIP_CAP')"""
                )
                last_processed = cur.fetchone()[0]

            raw_counts = [
                {
                    "decision": row["decision"],
                    "total": int(row["total"]),
                    "processed": int(row["processed"]),
                    "with_return": int(row["with_return"]),
                    "pending": int(row["pending"] or 0),
                    "included_in_phase_c": row["decision"] in phase_c_decisions,
                }
                for row in rows
            ]
            phase_c_rows = [row for row in raw_counts if row["included_in_phase_c"]]
            return {
                "days": days,
                "last_processed_at": last_processed.isoformat() if last_processed else None,
                "raw_skip_counts": raw_counts,
                "phase_c": {
                    "total_skips": sum(row["total"] for row in phase_c_rows),
                    "processed": sum(row["processed"] for row in phase_c_rows),
                    "with_return": sum(row["with_return"] for row in phase_c_rows),
                    "pending": sum(row["pending"] for row in phase_c_rows),
                },
            }
        except Exception:
            conn.rollback()
            raise

    _INSERT_TRADE = """
        INSERT INTO trades
            (symbol, signal_id, decision_id, entry_order_id,
             entry_time, entry_notional, score, regime_mult, qty, signal_score,
             stop_strategy, stop_mode, stop_vol_at_entry, stop_k,
             stop_floor, stop_cap, stop_d_init, stop_vol_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
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
        signal_score: float | None = None,
        frozen_stop: "FrozenStop | None" = None,
    ) -> None:
        """Insert an open trade row (entry_price populated later by reconcile).

        Args:
            score: Portfolio allocation weight (e.g. 0.02 = 2% target weight).
            signal_score: Actual LLM sentiment score that motivated the trade.
                Stored separately so IC / score-bucket analytics are meaningful.
            frozen_stop: Optional frozen stop parameters (migration 034).
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                fs = frozen_stop
                cur.execute(
                    self._INSERT_TRADE,
                    (symbol, signal_id, decision_id, entry_order_id,
                     entry_time, entry_notional, score, regime_mult, qty, signal_score,
                     fs.strategy if fs else None,
                     fs.mode if fs else None,
                     fs.vol_at_entry if fs else None,
                     fs.k if fs else None,
                     fs.floor if fs else None,
                     fs.cap if fs else None,
                     fs.d_init if fs else None,
                     fs.vol_source if fs else None),
                )
                row = cur.fetchone()
                trade_id: int | None = row[0] if row else None
                # P0-12: write audit row in the same transaction so a failed audit
                # rolls back the trade (no unaudited trades can exist).
                cur.execute(
                    self._INSERT_AUDIT_LOG,
                    (
                        "INSERT",
                        "trades",
                        trade_id,
                        __import__("json").dumps({
                            "symbol": symbol,
                            "entry_order_id": entry_order_id,
                            "entry_notional": entry_notional,
                            "score": score,
                        }),
                    ),
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
                # Always SELECT FOR UPDATE to hold the row lock for the entire
                # transaction — prevents two workers from closing the same trade.
                cur.execute(
                    "SELECT entry_notional, qty FROM trades WHERE symbol = %s AND exit_time IS NULL FOR UPDATE SKIP LOCKED",
                    (symbol,),
                )
                db_row = cur.fetchone()
                if db_row is None:
                    return None  # already closed or locked by another worker

                if entry_notional is None or qty is None:
                    entry_notional = float(db_row[0]) if db_row[0] is not None else 0.0
                    qty = float(db_row[1]) if db_row[1] is not None else 0.0

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

    def record_trade_exit(
        self,
        symbol: str,
        exit_order_id: str,
        exit_time,
        exit_reason: str,
        *,
        trade_id: int | None = None,
        is_final: bool = True,
    ) -> int | None:
        """Mark a trade as exited; exit_price is reconciled later by
        reconcile_trade_fills.

        Multi-tranche model (WS-5 fix-back 2026-07-14). A position wound down
        across several SELL tranches (e.g. SHEL, 3 tranches over 3 cycles) is ONE
        trade row. ``exit_order_ids`` accumulates every tranche's order id so the
        daily reconcile can aggregate them into one weighted-average exit price.

        Targeting — targets ONLY the trade being wound down, never the many
        historical closed trades for the same symbol (META 24, AZN 20, ...):
        - ``trade_id`` given (preferred, caller passes the open trade's id):
          ``WHERE id = %s``.
        - ``trade_id`` None (fallback): ``WHERE symbol = %s AND exit_time IS NULL``
          — the single open trade (the pyramiding guard guarantees at most one
          open trade per symbol). NEVER a naked ``WHERE symbol = %s``, which
          would match and corrupt every historical trade's ``exit_order_ids``.

        ``is_final`` controls whether this tranche closes the trade:
        - ``is_final=True`` (default; stop-loss / reversal full-close SELLs and
          the final portfolio tranche): set ``exit_time`` + ``exit_reason`` and
          return the ``trade_id`` so the caller runs its postmortem exactly once.
        - ``is_final=False`` (partial portfolio SELL tranche, target weight > 0):
          append the order id but do NOT set ``exit_time``/``exit_reason`` — the
          trade stays "open" so the pyramiding guard keeps blocking re-BUY during
          wind-down and the daily reconcile skips it until it is fully closed;
          return None so the caller skips the postmortem until the final tranche.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # exit_order_id (single, first tranche) + exit_order_ids (all
                # tranches, dedup) are updated on EVERY tranche so reconcile can
                # aggregate every fill.
                # NB: use array_append(...), NOT `arr || elem`. On this Postgres
                # `text[] || text` resolves to array_cat and tries to cast the
                # scalar string to text[], throwing 'malformed array literal'
                # (reproduced 2026-07-15). This was the real root cause of the
                # 5-missing-SELL-trace incident: the first SELL on a fresh
                # position (exit_order_ids NULL) hit `COALESCE(NULL, ARRAY[]::text[]) || %s`
                # and raised, which (pre-B33) broke the whole trade-write loop.
                # array_append(anyarray, anyelement) is unambiguous.
                # Dedup guard: array_position is 1-BASED and returns NULL when the
                # element is absent; COALESCE(..., 0) = 0 means "not present → append".
                append_clause = (
                    "exit_order_id = COALESCE(exit_order_id, %s),\n"
                    "                               exit_order_ids = CASE\n"
                    "                                   WHEN COALESCE(\n"
                    "                                       array_position(COALESCE(exit_order_ids, ARRAY[]::text[]), %s),\n"
                    "                                       0\n"
                    "                                   ) = 0\n"
                    "                                   THEN array_append(COALESCE(exit_order_ids, ARRAY[]::text[]), %s)\n"
                    "                                   ELSE exit_order_ids\n"
                    "                               END"
                )
                if is_final:
                    set_clause = (
                        append_clause
                        + ",\n                               exit_time = COALESCE(exit_time, %s),\n"
                        "                               exit_reason = COALESCE(exit_reason, %s)"
                    )
                    set_params = (exit_order_id, exit_order_id, exit_order_id,
                                   exit_time, exit_reason)
                else:
                    set_clause = append_clause
                    set_params = (exit_order_id, exit_order_id, exit_order_id)

                if trade_id is not None:
                    where_sql = "WHERE id = %s"
                    where_params = (trade_id,)
                else:
                    where_sql = "WHERE symbol = %s AND exit_time IS NULL"
                    where_params = (symbol,)

                cur.execute(
                    f"""UPDATE trades
                        SET {set_clause}
                        {where_sql}
                        RETURNING id""",
                    set_params + where_params,
                )
                row = cur.fetchone()
            conn.commit()
            if row is None:
                # No matching open trade (e.g. a SELL for a symbol with no open
                # row, or a double close): nothing to record, no postmortem.
                return None
            trade_id = int(row[0])
            # Postmortem runs only on the final tranche.
            return trade_id if is_final else None
        except Exception:
            conn.rollback()
            raise

    def fetch_open_trade_meta(self, symbol: str) -> dict | None:
        """Return strategy + signal_id for the open trade for symbol.

        Mirrors the origin-strategy derivation in src/api/routes/trading.py:
        S4 if signal-driven, S1 otherwise. Returns None if no open trade exists.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT signal_id FROM trades WHERE symbol = %s AND exit_time IS NULL",
                    (symbol,),
                )
                row = cur.fetchone()
            # B7/B32: read-only — end the transaction so the connection is not
            # left 'idle in transaction' (the exact state of the leaked conns).
            conn.rollback()
            if row is None:
                return None
            signal_id = row[0]
            return {
                "signal_id": signal_id,
                "strategy": "S4" if signal_id is not None else "S1",
            }
        except Exception:
            conn.rollback()
            raise

    def fetch_open_trade_entry_time(self, symbol: str) -> str | None:
        """Return the entry_time (ISO string) of the open trade for symbol, if any."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT entry_time FROM trades WHERE symbol = %s AND exit_time IS NULL ORDER BY entry_time DESC LIMIT 1",
                    (symbol,),
                )
                row = cur.fetchone()
            conn.rollback()
            if row is None or row[0] is None:
                return None
            # row[0] may be datetime or string depending on psycopg2/adapter.
            return row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
        except Exception:
            conn.rollback()
            raise

    def load_frozen_stop(self, symbol: str) -> "FrozenStop | None":
        """Load the frozen stop params from the open trade row for symbol."""
        from src.portfolio.stop_policy import FrozenStop

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT stop_strategy, stop_mode, stop_vol_at_entry, stop_k,
                           stop_floor, stop_cap, stop_d_init, stop_vol_source
                    FROM trades
                    WHERE symbol = %s AND exit_time IS NULL
                    """,
                    (symbol,),
                )
                row = cur.fetchone()
            # B7/B32: read-only — end the transaction so the connection is not
            # left 'idle in transaction' (load_frozen_stop was the last query on
            # the 20 leaked live connections, 2026-07-14).
            conn.rollback()
            if row is None or row[6] is None:
                return None
            return FrozenStop(
                strategy=row[0],
                mode=row[1] or "fixed",
                vol_at_entry=row[2],
                sigma_eff=row[2],
                k=row[3],
                floor=row[4],
                cap=row[5],
                d_init=float(row[6]),
                vol_source=row[7],
            )
        except Exception:
            conn.rollback()
            raise

    def save_frozen_stop(self, trade_id: int, frozen: "FrozenStop") -> None:
        """Persist frozen stop parameters on an existing open trade row.

        Used when the entry order id is known only after open_trade is called, or
        when a live trade needs its frozen stop backfilled (spec §6.4).
        """
        if frozen is None:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE trades
                    SET stop_strategy   = %s,
                        stop_mode       = %s,
                        stop_vol_at_entry = %s,
                        stop_k          = %s,
                        stop_floor      = %s,
                        stop_cap        = %s,
                        stop_d_init     = %s,
                        stop_vol_source = %s
                    WHERE id = %s AND exit_time IS NULL
                    """,
                    (
                        frozen.strategy,
                        frozen.mode,
                        frozen.vol_at_entry,
                        frozen.k,
                        frozen.floor,
                        frozen.cap,
                        frozen.d_init,
                        frozen.vol_source,
                        trade_id,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def insert_stop_decision(self, decision: "StopDecision", exit_order_id: str | None) -> None:
        """Persist one fired protective stop decision."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stop_decisions
                        (trade_id, symbol, strategy, mode, entry_price, observed_price,
                         trigger_price, d_init, vol_at_entry, sigma_eff, k, floor, cap,
                         price_source, vol_source, exit_order_id, cycle_ts)
                    VALUES (
                        (SELECT id FROM trades WHERE symbol=%s AND exit_time IS NULL),
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        decision.symbol,
                        decision.symbol,
                        decision.strategy,
                        decision.mode,
                        decision.entry_price,
                        decision.observed_price,
                        decision.trigger_price,
                        decision.d_init,
                        decision.vol_at_entry,
                        decision.sigma_eff,
                        decision.k,
                        decision.floor,
                        decision.cap,
                        decision.price_source,
                        decision.vol_source,
                        exit_order_id,
                        decision.cycle_ts,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def insert_stop_shadow(self, rows: list[dict]) -> None:
        """Persist per-cycle shadow log rows (high volume, batched)."""
        if not rows:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                _values = [
                    (
                        r["cycle_ts"], r["symbol"], r.get("strategy"),
                        r.get("entry_price"), r.get("observed_price"),
                        r.get("vol_at_entry"), r.get("sigma_eff"), r.get("vol_source"),
                        r.get("d_init_fixed"), r.get("trigger_fixed"), r.get("would_breach_fixed"),
                        r.get("d_init_vol_scaled"), r.get("trigger_vol_scaled"), r.get("would_breach_vol_scaled"),
                        r.get("d_hard"), r.get("d_hard_trigger"), r.get("d_hard_breached"),
                    )
                    for r in rows
                ]
                cur.executemany(
                    """
                    INSERT INTO stop_shadow_log
                        (cycle_ts, symbol, strategy, entry_price, observed_price,
                         vol_at_entry, sigma_eff, vol_source,
                         d_init_fixed, trigger_fixed, would_breach_fixed,
                         d_init_vol_scaled, trigger_vol_scaled, would_breach_vol_scaled,
                         d_hard, d_hard_trigger, d_hard_breached)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    _values,
                )
            conn.commit()
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
                               gross_pnl, slippage_est, net_pnl, postmortem_diagnosis, created_at,
                               stop_strategy, stop_d_init
                        FROM trades {where}
                        ORDER BY entry_time DESC LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def fetch_daily_pnl(self, from_date: str, to_date: str) -> list[dict]:
        """Return per-day P&L breakdown from closed trades, with individual trade detail.

        Args:
            from_date: inclusive start date as 'YYYY-MM-DD'
            to_date:   inclusive end date as 'YYYY-MM-DD'

        Returns list of dicts with keys:
            date, trades_closed, total_gross_pnl, total_costs, total_net_pnl,
            winners, losers, trades (list of individual trade dicts)
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Daily aggregates
                cur.execute(
                    """
                    SELECT
                        (exit_time AT TIME ZONE 'UTC')::date                   AS trading_date,
                        COUNT(*)                                                AS trades_closed,
                        ROUND(SUM(COALESCE(gross_pnl, net_pnl))::numeric, 2)  AS total_gross_pnl,
                        ROUND(SUM(COALESCE(gross_pnl, net_pnl) - net_pnl)::numeric, 2)
                                                                                AS total_costs,
                        ROUND(SUM(net_pnl)::numeric, 2)                        AS total_net_pnl,
                        COUNT(CASE WHEN net_pnl > 0 THEN 1 END)                AS winners,
                        COUNT(CASE WHEN net_pnl < 0 THEN 1 END)                AS losers
                    FROM trades
                    WHERE exit_time IS NOT NULL AND net_pnl IS NOT NULL
                      AND exit_reason IS DISTINCT FROM 'LEGACY_FLATTEN'
                      AND (exit_time AT TIME ZONE 'UTC')::date BETWEEN %s AND %s
                    GROUP BY trading_date
                    ORDER BY trading_date
                    """,
                    (from_date, to_date),
                )
                agg_cols = [d[0] for d in cur.description]
                day_rows = [dict(zip(agg_cols, row)) for row in cur.fetchall()]

                # Per-trade detail for the same date range
                cur.execute(
                    """
                    SELECT t.id, t.symbol, t.signal_id, t.decision_id, ss.news_log_id,
                           t.entry_order_id, t.entry_time, t.exit_time, t.entry_price, t.exit_price,
                           t.qty, t.gross_pnl, t.net_pnl, t.exit_reason,
                           (exit_time AT TIME ZONE 'UTC')::date AS trading_date
                    FROM trades t
                    LEFT JOIN sentiment_signals ss ON ss.id = t.signal_id
                    WHERE t.exit_time IS NOT NULL AND t.net_pnl IS NOT NULL
                      AND t.exit_reason IS DISTINCT FROM 'LEGACY_FLATTEN'
                      AND (t.exit_time AT TIME ZONE 'UTC')::date BETWEEN %s AND %s
                    ORDER BY t.exit_time ASC
                    """,
                    (from_date, to_date),
                )
                trade_cols = [d[0] for d in cur.description]
                trade_rows = [dict(zip(trade_cols, row)) for row in cur.fetchall()]

                # Group trades by date
                from collections import defaultdict
                trades_by_date: dict = defaultdict(list)
                for t in trade_rows:
                    d = str(t["trading_date"])
                    trades_by_date[d].append({
                        "id": int(t["id"]),
                        "symbol": t["symbol"],
                        "signal_id": int(t["signal_id"]) if t["signal_id"] is not None else None,
                        "decision_id": int(t["decision_id"]) if t["decision_id"] is not None else None,
                        "news_log_id": int(t["news_log_id"]) if t["news_log_id"] is not None else None,
                        "entry_order_id": t["entry_order_id"],
                        "entry_time": t["entry_time"].isoformat() if t["entry_time"] else None,
                        "exit_time": t["exit_time"].isoformat() if t["exit_time"] else None,
                        "entry_price": float(t["entry_price"]) if t["entry_price"] is not None else None,
                        "exit_price": float(t["exit_price"]) if t["exit_price"] is not None else None,
                        "qty": float(t["qty"]) if t["qty"] is not None else None,
                        "gross_pnl": float(t["gross_pnl"]) if t["gross_pnl"] is not None else None,
                        "net_pnl": float(t["net_pnl"]),
                        "exit_reason": t["exit_reason"],
                    })

                result = []
                for row in day_rows:
                    d = str(row["trading_date"])
                    result.append({
                        "date": d,
                        "trades_closed": int(row["trades_closed"]),
                        "total_gross_pnl": float(row["total_gross_pnl"]),
                        "total_costs": float(row["total_costs"]),
                        "total_net_pnl": float(row["total_net_pnl"]),
                        "winners": int(row["winners"]),
                        "losers": int(row["losers"]),
                        "trades": trades_by_date.get(d, []),
                    })
                return result
        except Exception:
            conn.rollback()
            raise

    def fetch_nav_daily(self, from_date: str, to_date: str) -> list[dict]:
        """Return the last NAV snapshot per calendar day from risk_reports.

        One row per day in [from_date, to_date] (days without a snapshot are
        absent). Feeds the mark-to-market enrichment of /api/performance/daily:
        closed-trade sums alone hid the real day result (2026-07-17: −$18.46
        realized vs −$115.60 NAV).
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (day)
                        (timestamp AT TIME ZONE 'UTC')::date AS day,
                        nav
                    FROM risk_reports
                    WHERE nav IS NOT NULL
                      AND (timestamp AT TIME ZONE 'UTC')::date BETWEEN %s AND %s
                    ORDER BY day, timestamp DESC
                    """,
                    (from_date, to_date),
                )
                return [
                    {"date": str(row[0]), "nav": float(row[1])}
                    for row in cur.fetchall()
                ]
        except Exception:
            conn.rollback()
            raise

    def fetch_recently_bought_symbols(self, minutes: int = 30) -> set[str]:
        """Return symbols with an open trade entered in the last `minutes` minutes.

        Used by the portfolio scheduler to enforce a minimum hold period:
        positions entered recently must not be sold in the same cycle.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT DISTINCT symbol FROM trades
                       WHERE entry_time >= now() - (%s || ' minutes')::interval
                         AND exit_time IS NULL""",
                    (str(minutes),),
                )
                return {row[0] for row in cur.fetchall()}
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
        """Fetch fill prices from Alpaca for open entry and exit orders.

        Called daily (run_daily_report). Reconciles:
        - Entry fills: trades where entry_price IS NULL
        - Exit fills:  trades where exit_order_id IS NOT NULL and exit_price IS NULL

        Returns the total count of rows updated.
        """
        conn = self._get_connection()
        try:
            # Reconcile entry fills — also compute entry-side cost estimate so
            # open trades have a lower-bound cost_usd while the position is held.
            # (Full round-trip costs are overwritten at close time by the exit reconcile.)
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, entry_order_id, symbol, entry_notional FROM trades
                       WHERE entry_price IS NULL
                         AND entry_time > now() - '7 days'::interval"""
                )
                rows = cur.fetchall()
            updated = 0
            for trade_id, order_id, symbol, entry_notional_db in rows:
                try:
                    order = trading_client.get_order_by_id(order_id)
                    if order.filled_avg_price is None:
                        continue
                    fill_price = float(order.filled_avg_price)
                    fill_qty = float(order.filled_qty) if order.filled_qty else None
                    notional = float(entry_notional_db) if entry_notional_db else (
                        fill_price * fill_qty if fill_qty else 0.0
                    )
                    entry_costs = self._cost_calc.compute(
                        symbol=symbol or "UNKNOWN",
                        notional=notional,
                        qty=fill_qty or 0.0,
                        fill_price=fill_price,
                        side="BUY",
                    )
                    with conn.cursor() as cur:
                        cur.execute(
                            """UPDATE trades
                               SET entry_price = %s,
                                   qty         = %s,
                                   cost_usd    = %s,
                                   cost_bps    = %s
                               WHERE id = %s""",
                            (fill_price, fill_qty,
                             entry_costs.total_cost_usd, entry_costs.total_cost_bps,
                             trade_id),
                        )
                    updated += 1
                except Exception as e:
                    log.warning("Failed to reconcile order %s: %s", order_id, e)

            # Reconcile exit fills — compute P&L once fill price is known.
            # WS-5 fix-back (2026-07-14): reconcile ONLY fully-closed trades
            # (exit_time IS NOT NULL, set on the final tranche). Intermediate
            # tranches set exit_order_id/exit_order_ids but keep exit_time NULL,
            # so a position mid-wind-down is not prematurely reconciled with a
            # partial fill. Aggregates every tranche in exit_order_ids.
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, exit_order_id, exit_order_ids,
                              entry_price, entry_notional, qty, symbol
                       FROM trades
                       WHERE exit_time IS NOT NULL
                         AND exit_price IS NULL
                         AND exit_time > now() - '48 hours'::interval"""
                )
                exit_rows = cur.fetchall()
            exit_updated = 0
            for trade_id, exit_order_id, exit_order_ids, entry_price, entry_notional, qty, symbol in exit_rows:
                try:
                    order_ids = list(exit_order_ids) if exit_order_ids else [exit_order_id]
                    fills: list[tuple[float, float]] = []
                    for oid in order_ids:
                        order = trading_client.get_order_by_id(oid)
                        if order.filled_avg_price is None:
                            continue
                        fill_price = float(order.filled_avg_price)
                        fill_qty = float(order.filled_qty) if order.filled_qty else 0.0
                        fills.append((fill_price, fill_qty))
                    if not fills:
                        continue
                    total_fill_qty = sum(q for _, q in fills)
                    if total_fill_qty <= 0:
                        continue
                    avg_exit_price = sum(p * q for p, q in fills) / total_fill_qty
                    entry_p = float(entry_price) if entry_price is not None else 0.0
                    # Use the actual filled quantity across all tranches so the
                    # P&L matches the total shares that left the position.
                    qty_f = total_fill_qty
                    notional_f = float(entry_notional) if entry_notional is not None else (
                        avg_exit_price * qty_f
                    )
                    costs = self._cost_calc.compute(
                        symbol=symbol,
                        notional=notional_f,
                        qty=qty_f,
                        fill_price=avg_exit_price,
                        side="SELL",
                    )
                    gross_pnl = (avg_exit_price - entry_p) * qty_f if entry_p else None
                    net_pnl = (gross_pnl - costs.total_cost_usd) if gross_pnl is not None else None
                    with conn.cursor() as cur:
                        cur.execute(
                            """UPDATE trades SET
                               exit_price = %s,
                               qty = %s,
                               gross_pnl = %s,
                               net_pnl = %s,
                               cost_bps = %s,
                               cost_usd = %s,
                               spread_cost_bps = %s,
                               impact_cost_bps = %s,
                               regulatory_cost_usd = %s,
                               slippage_est = %s
                               WHERE id = %s""",
                            (avg_exit_price, qty_f, gross_pnl, net_pnl,
                             costs.total_cost_bps, costs.total_cost_usd,
                             costs.spread_cost_bps, costs.impact_cost_bps,
                             costs.regulatory_cost_usd, costs.total_cost_usd,
                             trade_id),
                        )
                    exit_updated += 1
                except Exception as e:
                    log.warning("Failed to reconcile exit order(s) %s for trade %s: %s", order_ids, trade_id, e)
            conn.commit()
            return updated + exit_updated
        except Exception:
            conn.rollback()
            raise

    def log_llm_responses(
        self,
        signal_id: int,
        outputs: list[ModelOutput],
        min_confidence: float = 0.4,
        force_ineligible: bool = False,
    ) -> None:
        """Write per-model outputs to llm_responses. No-op for empty list.

        QS-06: ``eligible`` reflects whether the model passed the ensemble confidence
        filter (``confidence >= min_confidence``) — NOT hardcoded True. Without this,
        LOO-ICIR and post-hoc audit count discarded (<0.4) models as if they entered
        the signal, misrepresenting what actually contributed.

        ``force_ineligible=True`` marks every row ineligible regardless of
        confidence — used for divergence-fallback outputs, which are persisted
        for audit but did not enter the signal (FinBERT did).
        """
        if not outputs:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    self._INSERT_LLM_RESPONSE,
                    [
                        (
                            signal_id, out.model_id, out.polarity, out.confidence,
                            out.reasoning,
                            False if force_ineligible else out.confidence >= min_confidence,
                        )
                        for out in outputs
                    ],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def log_shadow_responses(self, rows: list[dict]) -> None:
        """Write Stage-2 shadow-model outputs. No-op for empty list.

        Rows are audit/measurement only: nothing in the live path reads them.
        news_log_id may be None (URL/ticker conflict in log_news_item), hence
        the extra symbol column for joinability.
        """
        if not rows:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    self._INSERT_SHADOW_RESPONSE,
                    [
                        (r.get("news_log_id"), r["symbol"], r["model_id"],
                         r.get("polarity"), r.get("confidence"), r.get("reasoning"),
                         bool(r.get("parse_error", False)), r.get("latency_ms"))
                        for r in rows
                    ],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # WARNING: this SELECT's column order must stay in sync with the module-level
    # SHADOW_COMPARISON_COLUMNS constant above — both run_shadow_comparison_report
    # (src/workers/performance.py) and scripts/report_model_comparison.py build a
    # DataFrame from this method's raw tuples using that name list, positionally.
    _FETCH_SHADOW_ROWS = """
        SELECT news_log_id, model_id, polarity, confidence, parse_error
        FROM llm_shadow_responses
        WHERE created_at >= %s
    """

    def fetch_shadow_rows(self, since) -> list[tuple]:
        """Stage-2 shadow-model rows (news_log_id, model_id, polarity, confidence,
        parse_error) generated since `since`. Used by the auto-report task and the
        manual report script — see src/performance/model_comparison.build_comparison.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_SHADOW_ROWS, (since,))
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise

    # WARNING: this SELECT's column order must stay in sync with the module-level
    # SHADOW_COMPARISON_COLUMNS constant above (and with _FETCH_SHADOW_ROWS, since
    # fetch_shadow_rows and fetch_live_response_rows feed the same DataFrame) — see
    # the note on _FETCH_SHADOW_ROWS above.
    _FETCH_LIVE_RESPONSE_ROWS = """
        SELECT s.news_log_id, r.model_id, r.polarity, r.confidence, FALSE AS parse_error
        FROM llm_responses r
        JOIN sentiment_signals s ON s.id = r.signal_id
        WHERE r.generated_at >= %s AND s.news_log_id IS NOT NULL
    """

    def fetch_live_response_rows(self, since) -> list[tuple]:
        """Live-ensemble per-model rows since `since`, shaped like fetch_shadow_rows
        (parse_error hardcoded FALSE — live llm_responses rows are always parsed) so
        both can feed the same comparison DataFrame.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_LIVE_RESPONSE_ROWS, (since,))
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise

    _FETCH_FWD_BY_NEWS = """
        SELECT news_log_id, forward_return
        FROM sentiment_signals
        WHERE news_log_id IS NOT NULL
          AND forward_return IS NOT NULL
          AND generated_at >= %s
    """

    def fetch_fwd_by_news(self, since) -> list[tuple]:
        """(news_log_id, forward_return) pairs since `since` — the join key used
        by build_comparison to score both shadow and live per-model rows.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_FWD_BY_NEWS, (since,))
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise

    def get_news_recent(
        self,
        limit: int = 100,
        ticker: str | None = None,
        source: str | None = None,
    ) -> list[dict]:
        """Return recent news_log rows with downstream trace counts, newest first."""
        filters = []
        params: list = []
        if ticker:
            filters.append("nl.ticker = %s")
            params.append(ticker)
        if source:
            filters.append("nl.source = %s")
            params.append(source)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT nl.id, nl.title, nl.url, nl.source, nl.ticker,
                               nl.raw_sentiment, nl.body_snippet, nl.fetched_at, nl.published_at,
                               COALESCE(sc.signal_count, 0) AS signal_count,
                               COALESCE(dc.decision_count, 0) AS decision_count,
                               COALESCE(oc.order_count, 0) AS order_count,
                               ls.id AS latest_signal_id,
                               ld.id AS latest_decision_id,
                               ld.decision AS latest_decision,
                               ld.reason AS latest_decision_reason,
                               ld.signal_score AS latest_decision_signal_score,
                               ld.order_id AS latest_decision_order_id,
                               ld.tick_time AS latest_decision_at
                        FROM news_log nl
                        LEFT JOIN (
                            SELECT news_log_id, COUNT(*) AS signal_count
                            FROM sentiment_signals
                            WHERE news_log_id IS NOT NULL
                            GROUP BY news_log_id
                        ) sc ON sc.news_log_id = nl.id
                        LEFT JOIN (
                            SELECT ss.news_log_id, COUNT(ed.id) AS decision_count
                            FROM sentiment_signals ss
                            JOIN execution_decisions ed ON ed.signal_id = ss.id
                            WHERE ss.news_log_id IS NOT NULL
                            GROUP BY ss.news_log_id
                        ) dc ON dc.news_log_id = nl.id
                        LEFT JOIN (
                            SELECT news_log_id, COUNT(*) AS order_count
                            FROM (
                                SELECT DISTINCT ss.news_log_id, ed.order_id AS trace_id
                                FROM sentiment_signals ss
                                JOIN execution_decisions ed ON ed.signal_id = ss.id
                                WHERE ss.news_log_id IS NOT NULL
                                  AND ed.order_id IS NOT NULL
                                UNION
                                SELECT DISTINCT ss.news_log_id, t.id::text AS trace_id
                                FROM sentiment_signals ss
                                JOIN trades t ON t.signal_id = ss.id
                                WHERE ss.news_log_id IS NOT NULL
                            ) orders
                            GROUP BY news_log_id
                        ) oc ON oc.news_log_id = nl.id
                        LEFT JOIN LATERAL (
                            SELECT id, score, generated_at
                            FROM sentiment_signals
                            WHERE news_log_id = nl.id
                            ORDER BY generated_at DESC
                            LIMIT 1
                        ) ls ON TRUE
                        LEFT JOIN LATERAL (
                            SELECT ed.id, ed.decision, ed.reason, ed.signal_score,
                                   ed.order_id, ed.tick_time
                            FROM execution_decisions ed
                            WHERE ed.signal_id = ls.id
                               OR (
                                   ed.signal_id IS NULL
                                   AND ls.id IS NOT NULL
                                   AND ed.symbol = nl.ticker
                                   AND ed.tick_time >= ls.generated_at
                                   AND ed.tick_time <= ls.generated_at + INTERVAL '6 hours'
                                   AND ed.signal_score IS NOT NULL
                                   AND ABS(ed.signal_score - ls.score) < 0.000001
                               )
                            ORDER BY
                                CASE WHEN ed.signal_id = ls.id THEN 0 ELSE 1 END,
                                ed.tick_time ASC
                            LIMIT 1
                        ) ld ON TRUE
                        {where}
                        ORDER BY nl.fetched_at DESC LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def get_news_source_quality(self, days: int = 30) -> list[dict]:
        """Return per-source news quality funnel metrics for the recent window."""
        days = max(1, min(days, 365))
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH source_news AS (
                        SELECT id, source, ticker, raw_sentiment, fetched_at, published_at
                        FROM news_log
                        WHERE fetched_at >= NOW() - (%s * INTERVAL '1 day')
                    ),
                    signal_stats AS (
                        SELECT
                            nl.source,
                            COUNT(DISTINCT ss.id) AS signals_count,
                            AVG(ss.score) AS avg_score,
                            AVG(ss.confidence) AS avg_confidence
                        FROM source_news nl
                        LEFT JOIN sentiment_signals ss ON ss.news_log_id = nl.id
                        GROUP BY nl.source
                    ),
                    decision_stats AS (
                        SELECT
                            nl.source,
                            COUNT(DISTINCT ed.id) AS decisions_count
                        FROM source_news nl
                        JOIN sentiment_signals ss ON ss.news_log_id = nl.id
                        JOIN execution_decisions ed ON ed.signal_id = ss.id
                        GROUP BY nl.source
                    ),
                    order_stats AS (
                        SELECT source, COUNT(*) AS orders_count
                        FROM (
                            SELECT DISTINCT nl.source, 'decision:' || ed.id::text AS trace_id
                            FROM source_news nl
                            JOIN sentiment_signals ss ON ss.news_log_id = nl.id
                            JOIN execution_decisions ed ON ed.signal_id = ss.id
                            WHERE ed.order_id IS NOT NULL
                            UNION
                            SELECT DISTINCT
                                nl.source,
                                CASE
                                    WHEN t.decision_id IS NOT NULL THEN 'decision:' || t.decision_id::text
                                    ELSE 'trade:' || t.id::text
                                END AS trace_id
                            FROM source_news nl
                            JOIN sentiment_signals ss ON ss.news_log_id = nl.id
                            JOIN trades t ON t.signal_id = ss.id
                        ) traced_orders
                        GROUP BY source
                    ),
                    trade_stats AS (
                        SELECT
                            nl.source,
                            COUNT(DISTINCT t.id) AS trades_count,
                            COUNT(DISTINCT t.id) FILTER (
                                WHERE t.exit_time IS NOT NULL AND t.net_pnl IS NOT NULL
                            ) AS closed_trades_count,
                            AVG(t.net_pnl) FILTER (
                                WHERE t.exit_time IS NOT NULL AND t.net_pnl IS NOT NULL
                            ) AS avg_net_pnl,
                            SUM(t.net_pnl) FILTER (
                                WHERE t.exit_time IS NOT NULL AND t.net_pnl IS NOT NULL
                            ) AS total_net_pnl,
                            AVG(CASE
                                WHEN t.exit_time IS NOT NULL AND t.net_pnl IS NOT NULL
                                THEN CASE WHEN t.net_pnl > 0 THEN 1.0 ELSE 0.0 END
                            END)::float AS win_rate
                        FROM source_news nl
                        JOIN sentiment_signals ss ON ss.news_log_id = nl.id
                        JOIN trades t ON t.signal_id = ss.id
                        GROUP BY nl.source
                    )
                    SELECT
                        nl.source,
                        COUNT(*) AS news_count,
                        COUNT(*) FILTER (
                            WHERE nl.ticker IS NOT NULL
                              AND nl.ticker <> ''
                              AND nl.ticker <> 'UNKNOWN'
                        ) AS with_ticker_count,
                        COUNT(*) FILTER (WHERE nl.raw_sentiment IS NOT NULL) AS with_sentiment_count,
                        AVG(ABS(nl.raw_sentiment)) FILTER (
                            WHERE nl.raw_sentiment IS NOT NULL
                        ) AS avg_abs_raw_sentiment,
                        AVG(EXTRACT(EPOCH FROM (nl.fetched_at - nl.published_at)) / 60.0) FILTER (
                            WHERE nl.published_at IS NOT NULL
                              AND nl.fetched_at IS NOT NULL
                              AND nl.fetched_at >= nl.published_at
                        )::float AS avg_publish_to_fetch_minutes,
                        COALESCE(ss.signals_count, 0) AS signals_count,
                        COALESCE(ds.decisions_count, 0) AS decisions_count,
                        COALESCE(os.orders_count, 0) AS orders_count,
                        COALESCE(ts.trades_count, 0) AS trades_count,
                        COALESCE(ts.closed_trades_count, 0) AS closed_trades_count,
                        ss.avg_score,
                        ss.avg_confidence,
                        ts.avg_net_pnl,
                        ts.total_net_pnl,
                        ts.win_rate,
                        COALESCE(ss.signals_count, 0)::float / NULLIF(COUNT(*), 0) AS signal_rate,
                        COALESCE(ds.decisions_count, 0)::float / NULLIF(COALESCE(ss.signals_count, 0), 0) AS decision_rate,
                        COALESCE(os.orders_count, 0)::float / NULLIF(COALESCE(ds.decisions_count, 0), 0) AS order_rate
                    FROM source_news nl
                    LEFT JOIN signal_stats ss ON ss.source = nl.source
                    LEFT JOIN decision_stats ds ON ds.source = nl.source
                    LEFT JOIN order_stats os ON os.source = nl.source
                    LEFT JOIN trade_stats ts ON ts.source = nl.source
                    GROUP BY
                        nl.source,
                        ss.signals_count,
                        ss.avg_score,
                        ss.avg_confidence,
                        ds.decisions_count,
                        os.orders_count,
                        ts.trades_count,
                        ts.closed_trades_count,
                        ts.avg_net_pnl,
                        ts.total_net_pnl,
                        ts.win_rate
                    ORDER BY news_count DESC, nl.source
                    """,
                    (days,),
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

    _FETCH_ALL_FOR_IC = """
        SELECT score, confidence, forward_return, generated_at, model_id, fallback_used
        FROM sentiment_signals
        WHERE symbol = ANY(%s)
          AND generated_at >= now() - (%s || ' days')::interval
          AND fallback_used = FALSE
        ORDER BY generated_at ASC
    """

    def fetch_all_signals_for_ic(self, symbols: list[str], days: int) -> list[tuple]:
        """Batch version of fetch_signals_for_ic — single query for all symbols."""
        if not symbols:
            return []
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_ALL_FOR_IC, (symbols, str(days)))
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise

    _FETCH_ALL_PER_MODEL_FOR_IC = """
        SELECT r.model_id,
               r.polarity * r.confidence AS score,
               s.forward_return
        FROM llm_responses r
        JOIN sentiment_signals s ON s.id = r.signal_id
        WHERE s.symbol = ANY(%s)
          AND s.generated_at >= now() - (%s || ' days')::interval
          AND s.forward_return IS NOT NULL
          AND s.fallback_used = FALSE
          AND r.eligible = TRUE
        ORDER BY s.generated_at ASC
    """

    def fetch_all_per_model_signals_for_ic(self, symbols: list[str], days: int) -> list[tuple]:
        """Batch version of fetch_per_model_signals_for_ic — single query for all symbols."""
        if not symbols:
            return []
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_ALL_PER_MODEL_FOR_IC, (symbols, str(days)))
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

    # Per symbol, prefer the most recent ENSEMBLE signal over a FinBERT fallback within
    # the freshness window (fallback_used ASC first): a low-conviction FinBERT fallback
    # generated after a strong ensemble signal must NOT overwrite it (the ensemble is the
    # more reliable read of current sentiment). Among same-status signals, most recent wins.
    _FETCH_SIGNALS_FOR_CYCLE = """
        SELECT DISTINCT ON (symbol)
            id, symbol, score, confidence,
            COALESCE(reasoning, '') AS reasoning,
            model_id, ensemble_std, fallback_used, generated_at
        FROM sentiment_signals
        WHERE generated_at >= NOW() - (%s || ' hours')::interval
          AND (published_at IS NULL
               OR published_at >= NOW() - (%s || ' hours')::interval)
          AND symbol = ANY(%s)
        ORDER BY symbol, fallback_used ASC, generated_at DESC
    """

    def fetch_signals_for_cycle(
        self, hours: int = 4, symbols: list[str] | None = None,
        news_age_hours: float | None = None,
    ) -> list[SentimentResult]:
        """Fetch one signal per symbol from the last N hours.

        Used by the live portfolio cycle to load fresh signals for S4.
        Only returns signals for symbols in the provided list (watchlist) so
        that off-watchlist tickers don't consume ranking slots in S4 and then
        get silently dropped when no market price is available.

        Within the window, the **most recent ensemble** signal is preferred over a
        FinBERT fallback (so a weak fallback does not overwrite a strong recent
        ensemble read); among same-status signals the most recent wins.

        published_at gate (FIX-03): when `news_age_hours` is set, signals whose
        news is older are excluded; NULL published_at (legacy rows) passes — the
        generated_at window still bounds those. Default None = NO event-time gate:
        only the S4 entry path passes an explicit bound. Sell-protection and
        audit/reason callers need older-news signals (e.g. "signal expired 20h
        ago") and must not be narrowed by the entry-freshness policy.

        Returns SentimentResult objects with timezone-aware generated_at.
        """
        from datetime import timezone as _tz

        watchlist = symbols or []
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _news_h = news_age_hours if news_age_hours is not None else 24 * 365
                cur.execute(
                    self._FETCH_SIGNALS_FOR_CYCLE,
                    (str(hours), str(_news_h), watchlist),
                )
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
                    signal_id=row.get("id"),
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

    def fetch_signals_for_backtest_batch(
        self, symbols: list[str], start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Fetch signals for all symbols in a single query (avoids N+1)."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT symbol, score, confidence, reasoning, model_id,
                           ensemble_std, fallback_used, generated_at
                    FROM sentiment_signals
                    WHERE symbol = ANY(%s)
                      AND generated_at >= %s
                      AND generated_at <= %s
                    ORDER BY generated_at ASC
                    """,
                    (symbols, start_date, end_date),
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

    _FETCH_PENDING_FWD = """
        SELECT id, symbol, generated_at
        FROM sentiment_signals
        WHERE (forward_return IS NULL
               OR forward_return_3d IS NULL
               OR forward_return_5d IS NULL)
          AND generated_at < NOW() - INTERVAL '1 day'
          AND generated_at > NOW() - INTERVAL '1 day' * %s
        ORDER BY symbol, generated_at
    """

    def fetch_signals_pending_forward_return(
        self, days_back: int = 60
    ) -> list[tuple]:
        """Fetch signals that need a forward return populated.

        Returns (id, symbol, generated_at) for signals — including FinBERT
        fallback rows (they are tradeable via the no-fresh-ensemble path and
        needed for shadow-model evaluation) — that:
          - Are missing at least one horizon (1d/3d/5d)
          - Are older than 1 day (need next trading day to have closed)
          - Are within days_back days (avoid re-processing old history)

        A row stays pending until every computable horizon is filled.

        Args:
            days_back: Maximum lookback window in days (default 60).
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_PENDING_FWD, (days_back,))
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
                    "  id AS signal_id, symbol, score, confidence, reasoning, "
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

    def fetch_signals_by_ids(self, signal_ids: list[int]) -> list[dict]:
        """Fetch historical signals by exact local signal ids."""
        clean_signal_ids = [int(signal_id) for signal_id in signal_ids if signal_id]
        if not clean_signal_ids:
            return []
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT id AS signal_id, symbol, score, confidence, reasoning,
                              model_id, ensemble_std, fallback_used, generated_at
                       FROM sentiment_signals
                       WHERE id = ANY(%s)
                       ORDER BY generated_at DESC""",
                    (clean_signal_ids,),
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

    def fetch_signals_for_news(self, news_log_id: int, limit: int = 50) -> list[dict]:
        """Fetch historical signals generated from a specific news_log row."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT id AS signal_id, symbol, score, confidence, reasoning,
                              model_id, ensemble_std, fallback_used, generated_at
                       FROM sentiment_signals
                       WHERE news_log_id = %s
                       ORDER BY generated_at DESC
                       LIMIT %s""",
                    (news_log_id, limit),
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
        self, updates: list[tuple[int, float | None, float | None, float | None]]
    ) -> int:
        """Update 1d/3d/5d forward returns for multiple signals in one transaction.

        Args:
            updates: List of (signal_id, forward_return, forward_return_3d,
                forward_return_5d) tuples. A None horizon is left untouched via
                COALESCE (preserves any previously-written value) so a row with
                only partially-computable horizons can be completed on a later run.

        Returns:
            Number of rows updated.
        """
        if not updates:
            return 0
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    UPDATE sentiment_signals
                    SET forward_return    = COALESCE(%s, forward_return),
                        forward_return_3d = COALESCE(%s, forward_return_3d),
                        forward_return_5d = COALESCE(%s, forward_return_5d)
                    WHERE id = %s
                    """,
                    [(f1, f3, f5, sid) for sid, f1, f3, f5 in updates],
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

    # ── Audit log ─────────────────────────────────────────────────────────────

    _INSERT_AUDIT_LOG = (
        "INSERT INTO audit_log (action, table_name, record_id, details) "
        "VALUES (%s::audit_action_enum, %s, %s, %s)"
    )

    def write_audit_log(
        self,
        action: str,
        table_name: str | None = None,
        record_id: int | None = None,
        details: dict | None = None,
        user_id: str = "system",
    ) -> None:
        """Insert one row into audit_log.

        Args:
            action:     One of audit_action_enum values (e.g. 'INSERT', 'KILLSWITCH_ACTIVATE').
            table_name: Affected table, if applicable.
            record_id:  Primary key of the affected row, if applicable.
            details:    Arbitrary JSON payload (symbol, qty, reason, …).
            user_id:    Caller identity; defaults to 'system' for automated paths.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_AUDIT_LOG,
                    (
                        action,
                        table_name,
                        record_id,
                        json.dumps(details or {}),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ── Zeygos scores ─────────────────────────────────────────────────────────

    def insert_zeygos_scores(self, rows: list) -> int:
        """Upsert ZeygosRow list into zeygos_scores. Returns number of new rows."""
        if not rows:
            return 0
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO zeygos_scores
                       (report_date, market, sector, rank, ticker_refinitiv,
                        ticker, company_name, score_analysts, score_momentum,
                        score_valuation, score_solidity, score_dividend,
                        score_growth, score_interest, score_finale)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (report_date, ticker_refinitiv) DO NOTHING""",
                    [
                        (
                            r.report_date, r.market, r.sector, r.rank,
                            r.ticker_refinitiv, r.ticker, r.company_name,
                            r.score_analysts, r.score_momentum, r.score_valuation,
                            r.score_solidity, r.score_dividend, r.score_growth,
                            r.score_interest, r.score_finale,
                        )
                        for r in rows
                    ],
                )
                inserted = cur.rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return inserted

    def fetch_zeygos_universe(self, min_score: float = 65.0) -> set[str]:
        """Return normalized tickers from the latest Zeygos report with score >= min_score.

        Returns empty set (fail-open) on any error or if no data is present.
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT DISTINCT ticker
                       FROM zeygos_scores
                       WHERE report_date = (SELECT MAX(report_date) FROM zeygos_scores)
                         AND score_finale >= %s""",
                    (min_score,),
                )
                return {row[0] for row in cur.fetchall()}
        except Exception as exc:
            log.warning("fetch_zeygos_universe failed: %s — no filter applied", exc)
            return set()

    # ── context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "PostgreSQLStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, rolling back on exception if connection owned."""
        if exc_type is not None and self._conn is not None:
            self._conn.rollback()
        self.close()
