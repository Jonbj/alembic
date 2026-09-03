"""PostgreSQL store for sentiment signals and performance metrics."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from src.config import config
from src.costs.calculator import TradeCostCalculator
from src.models.signals import SentimentResult

if TYPE_CHECKING:
    from src.llm.ensemble import ModelOutput
    from src.models.news import NewsItem
    from src.portfolio.stop_policy import FrozenStop, StopDecision
    from src.strategies.s4.intent_ledger import S4IntentEvent
    from src.strategies.s4.lifecycle import (
        S4LifecycleEvent,
        S4VirtualExitEvent,
        SubmittedIntent,
    )
    from src.strategies.s4.p0_baseline import P0ReplayEvent

log = logging.getLogger(__name__)

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


# Epsilon for "the position is exhausted" comparisons. Fractional Alpaca fills
# carry tiny float residue (e.g. 2.981064744 - 2.981064 = 7e-7); anything below
# this is rounding noise, not a real residual. NOT a calibration knob — it is a
# float-tolerance, fixed by the broker's quantity precision, not tuned to P&L.
_QUANTITY_EPS = 1e-6


def remaining_after_exits(
    entry_qty: float,
    recorded_ids,
    fills: list[tuple[str, float]],
    *,
    eps: float = _QUANTITY_EPS,
) -> tuple[float, list[str]]:
    """Recompute the live open quantity of a trade from authoritative broker fills.

    #397: ``trades.qty`` is overloaded (entry fill qty while open, exit fill qty
    once closed), so it can never answer "how much is still held" for a
    partially-wound-down trade. This pure function recomputes that quantity from
    the broker's SELL fills so an open row always states the live position.

    Both holes in #397 are closed here by the same recompute:
    - Hole 1 (partial portfolio SELL tranches): their order ids already sit in
      ``recorded_ids`` (exit_order_ids); their filled qty decrements the total.
    - Hole 2 (broker-side protective-stop fills): orders NOT yet in
      ``recorded_ids`` still decrement the total and are returned in ``new_ids``
      so the caller can append them to exit_order_ids (and price them on the
      next closed-trade reconcile pass).

    Idempotent: re-running with the same fills yields the same remaining and an
    empty ``new_ids`` (recorded ids are never re-appended). A fill with zero
    filled_qty (cancelled/replaced) is ignored — it is not an exit.

    Args:
        entry_qty: entry fill quantity (trades.qty while the row is open).
        recorded_ids: exit_order_ids already on the row (None = no exits yet).
        fills: broker SELL fills for the symbol since entry, as (order_id,
            filled_qty). May include ids already recorded (deduped).

    Returns:
        (remaining, new_ids): remaining clamped to >= 0; new_ids the filled SELL
        order ids not already in recorded_ids, in first-seen order.
    """
    recorded = set(recorded_ids or ())
    counted: set[str] = set()
    total = 0.0
    new_ids: list[str] = []
    for oid, fq in fills:
        if oid in counted:
            continue  # same order reported twice by the broker — count once
        if fq is None or float(fq) <= eps:
            continue  # cancelled/replaced order with no fill is not an exit
        counted.add(oid)
        total += float(fq)
        if oid not in recorded:
            new_ids.append(oid)
    remaining = max(0.0, float(entry_qty) - total)
    return remaining, new_ids


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

    _INSERT_ENSEMBLE_CYCLE_HEALTH = """
        INSERT INTO ensemble_cycle_health (
            cycle_started_at, cycle_ended_at,
            n_ensemble, n_single, n_finbert, aggregate, rth
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    def record_ensemble_cycle_health(
        self,
        cycle_started_at: datetime,
        cycle_ended_at: datetime,
        n_ensemble: int,
        n_single: int,
        n_finbert: int,
        rth: bool,
    ) -> None:
        """Persist one row per SentimentWorker run (#427).

        Pure observability: not read by execution, sizing, or any money-path
        code. `aggregate = n_ensemble + n_single + n_finbert` matches the worker's
        own len(results), so a CHECK constraint violation is a worker-level bug,
        not a data-quality concern.
        """
        conn = self._get_connection()
        aggregate = n_ensemble + n_single + n_finbert
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_ENSEMBLE_CYCLE_HEALTH,
                    (
                        cycle_started_at,
                        cycle_ended_at,
                        n_ensemble,
                        n_single,
                        n_finbert,
                        aggregate,
                        rth,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

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
        INSERT INTO llm_responses (
            signal_id, model_id, polarity, confidence, reasoning,
            event_type, directness, materiality, novelty, risk_flags,
            evidence_sentences, eligible, generated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
    """

    _INSERT_SHADOW_RESPONSE = """
        INSERT INTO llm_shadow_responses
            (news_log_id, symbol, model_id, polarity, confidence, reasoning,
             parse_error, latency_ms, failure_reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    _INSERT_S4_INTENT_EVENT = """
        INSERT INTO s4_intent_events (
            event_id, intent_id, causal_event_id, event_type, occurred_at,
            decision_slot, symbol, signal_id, published_at, first_seen_at,
            model_generated_at, decision_at, rank, held_at_rank,
            signal_age_at_slot, competing_candidates,
            s1_state, anti_pyramiding, reason_code, is_tradable, versions,
            snapshot, missingness
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s::jsonb,
            %s::jsonb, %s, %s, %s, %s::jsonb,
            %s::jsonb, %s::jsonb
        )
        ON CONFLICT DO NOTHING
    """

    def write_s4_intent_events(self, events: list["S4IntentEvent"]) -> None:
        """Append S4 intent events; deterministic event IDs make retries idempotent."""
        if not events:
            return
        params = [(
            event.event_id,
            event.intent_id,
            event.causal_event_id,
            event.event_type,
            event.occurred_at,
            event.decision_slot,
            event.symbol,
            event.signal_id,
            event.published_at,
            event.first_seen_at,
            event.model_generated_at,
            event.decision_at,
            event.rank,
            event.held_at_rank,
            event.signal_age_at_slot,
            json.dumps(list(event.competing_candidates)),
            json.dumps(event.s1_state, sort_keys=True),
            event.anti_pyramiding,
            event.reason_code,
            event.is_tradable,
            json.dumps(event.versions, sort_keys=True),
            json.dumps(event.snapshot, sort_keys=True),
            json.dumps(event.missingness, sort_keys=True),
        ) for event in events]
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(self._INSERT_S4_INTENT_EVENT, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    _INSERT_S4_LIFECYCLE_EVENT = """
        INSERT INTO s4_lifecycle_events (
            event_id, intent_id, event_type, observed_at, symbol, order_id,
            status, reason_code, fill_id, filled_at, filled_quantity,
            filled_notional, fill_price, first_executable_price,
            first_executable_price_source, d0, due_session, policy_version,
            s1_virtual_quantity, s4_virtual_quantity, broker_quantity,
            unattributed_quantity, virtual_exit_quantity, virtual_exit_price,
            reconstructible, details
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s::jsonb
        )
        ON CONFLICT (event_id) DO NOTHING
    """

    def write_s4_lifecycle_events(
        self, events: list["S4LifecycleEvent | S4VirtualExitEvent"]
    ) -> None:
        """Append shadow lifecycle observations; deterministic IDs dedupe retries."""
        if not events:
            return
        params = []
        for event in events:
            params.append((
                event.event_id,
                event.intent_id,
                event.event_type,
                event.observed_at,
                event.symbol,
                getattr(event, "order_id", None),
                event.status,
                event.reason_code,
                getattr(event, "fill_id", None),
                getattr(event, "filled_at", None),
                getattr(event, "filled_quantity", 0.0),
                getattr(event, "filled_notional", 0.0),
                getattr(event, "fill_price", None),
                getattr(event, "first_executable_price", None),
                getattr(event, "first_executable_price_source", None),
                getattr(event, "d0", None),
                getattr(event, "due_session", None),
                event.policy_version,
                event.s1_virtual_quantity,
                event.s4_virtual_quantity,
                getattr(event, "broker_quantity", None),
                getattr(event, "unattributed_quantity", None),
                getattr(event, "virtual_exit_quantity", None),
                getattr(event, "price", None),
                getattr(event, "reconstructible", True),
                json.dumps(getattr(event, "details", {}), sort_keys=True),
            ))
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(self._INSERT_S4_LIFECYCLE_EVENT, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    _INSERT_S4_EXIT_POLICY_EVENT = """
        INSERT INTO s4_exit_policy_events (
            event_id, intent_id, policy_id, policy_version, event_type,
            observed_at, d0, symbol, status, reason_code, trigger_at,
            virtual_exit_quantity, runtime_quantity, first_executable_at,
            first_executable_price, first_executable_price_source, filled_at,
            fill_price, initial_notional, gross_pnl, entry_cost_usd,
            exit_cost_usd, net_pnl, cost_model_version, runtime_decision_id,
            runtime_order_id, comparable, divergence_reasons, details
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s::jsonb
        )
        ON CONFLICT (event_id) DO NOTHING
    """

    def write_s4_exit_policy_events(self, events: list["P0ReplayEvent"]) -> None:
        """Append policy shadow events; no field can request a broker action."""
        if not events:
            return
        params = [(
            event.event_id,
            event.intent_id,
            event.policy_id,
            event.policy_version,
            event.event_type,
            event.observed_at,
            event.d0,
            event.symbol,
            event.status,
            event.reason_code,
            event.trigger_at,
            event.virtual_exit_quantity,
            event.runtime_quantity,
            event.first_executable_at,
            event.first_executable_price,
            event.first_executable_price_source,
            event.filled_at,
            event.fill_price,
            event.initial_notional,
            event.gross_pnl,
            event.entry_cost_usd,
            event.exit_cost_usd,
            event.net_pnl,
            event.cost_model_version,
            event.runtime_decision_id,
            event.runtime_order_id,
            event.comparable,
            list(event.divergence_reasons),
            json.dumps(event.details, sort_keys=True),
        ) for event in events]
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(self._INSERT_S4_EXIT_POLICY_EVENT, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def fetch_s4_p0_replay_candidates(self) -> list[dict]:
        """Read closed E0 lifecycles not yet terminally projected into P0."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        lc.*,
                        t.id AS runtime_trade_id,
                        COALESCE(
                            t.exit_order_ids,
                            CASE
                                WHEN t.exit_order_id IS NULL THEN ARRAY[]::TEXT[]
                                ELSE ARRAY[t.exit_order_id]::TEXT[]
                            END
                        ) AS runtime_order_ids,
                        t.exit_time AS runtime_exit_time,
                        t.exit_reason AS runtime_exit_reason,
                        runtime_decision.id AS runtime_decision_id,
                        COALESCE(runtime_decision.tick_time, t.exit_time) AS trigger_at,
                        runtime_decision.exit_mechanism,
                        runtime_decision.reason AS runtime_reason
                    FROM s4_lifecycle_current lc
                    LEFT JOIN trades t ON t.entry_order_id = lc.order_id
                    LEFT JOIN LATERAL (
                        SELECT ed.id, ed.tick_time, ed.exit_mechanism, ed.reason
                        FROM execution_decisions ed
                        WHERE ed.decision = 'SELL'
                          AND ed.symbol = lc.symbol
                          AND ed.order_id = ANY(COALESCE(
                              t.exit_order_ids,
                              CASE
                                  WHEN t.exit_order_id IS NULL THEN ARRAY[]::TEXT[]
                                  ELSE ARRAY[t.exit_order_id]::TEXT[]
                              END
                          ))
                        ORDER BY ed.tick_time, ed.id
                        LIMIT 1
                    ) runtime_decision ON TRUE
                    LEFT JOIN s4_exit_policy_current p0
                      ON p0.intent_id = lc.intent_id
                     AND p0.policy_id = 'P0'
                    WHERE lc.filled_quantity > 0
                      AND (
                          p0.intent_id IS NULL
                          OR p0.status NOT IN ('CLOSED', 'RISK_EXITED')
                          -- La proiezione P0 nasce da una precisa osservazione
                          -- di lifecycle. Se a monte ne e' arrivata una nuova
                          -- — un ingresso prima non ricostruibile che lo
                          -- diventa — quella corrente e' ferma a un'osservazione
                          -- superata e va riproiettata, anche se terminale.
                          -- Il confronto e' sull'identita' dell'osservazione,
                          -- non su `comparable`: un intento che resta non
                          -- comparabile non viene riofferto a ogni ciclo.
                          OR p0.details->>'entry_lifecycle_event_id'
                             IS DISTINCT FROM lc.event_id::text
                      )
                    ORDER BY COALESCE(t.exit_time, lc.observed_at), lc.intent_id
                    """
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.rollback()

    def fetch_s4_submitted_intents(self) -> list["SubmittedIntent"]:
        """Read submitted #294 intents without inventing missing broker metadata."""
        from src.strategies.s4.lifecycle import SubmittedIntent

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        intent_id::text AS intent_id,
                        symbol,
                        snapshot->'disposition'->>'order_id' AS order_id,
                        occurred_at AS submitted_at,
                        (snapshot->'disposition'->>'requested_quantity')::DOUBLE PRECISION
                            AS requested_quantity,
                        (snapshot->'disposition'->>'notional')::DOUBLE PRECISION
                            AS requested_notional,
                        (snapshot->'disposition'->>'first_executable_price')::DOUBLE PRECISION
                            AS first_executable_price,
                        snapshot->'disposition'->>'first_executable_price_source'
                            AS first_executable_price_source,
                        versions->'policy'->>'version' AS policy_version,
                        COALESCE(
                            snapshot->'disposition'->'sleeve_contributions',
                            '{}'::jsonb
                        ) AS sleeve_contributions,
                        reason_code AS submission_reason_code,
                        snapshot->'disposition'->>'error_type' AS submission_error
                    FROM s4_intent_events
                    WHERE event_type = 'disposition'
                      AND reason_code IN ('SUBMITTED', 'BROKER_REJECT')
                      AND occurred_at > now() - '7 days'::interval
                    ORDER BY occurred_at, intent_id
                    """
                )
                rows = cur.fetchall()
            return [SubmittedIntent(
                intent_id=str(row["intent_id"]),
                symbol=row["symbol"],
                order_id=row["order_id"],
                submitted_at=row["submitted_at"],
                requested_quantity=float(row["requested_quantity"] or 0.0),
                requested_notional=float(row["requested_notional"] or 0.0),
                first_executable_price=float(row["first_executable_price"] or 0.0),
                first_executable_price_source=(
                    row["first_executable_price_source"] or "not_recorded"
                ),
                policy_version=row["policy_version"] or "unknown",
                sleeve_contributions=dict(row["sleeve_contributions"] or {}),
                submission_reason_code=row["submission_reason_code"],
                submission_error=row["submission_error"],
            ) for row in rows]
        except Exception:
            conn.rollback()
            raise

    def fetch_s4_p1_candidates(self) -> list[dict]:
        """Lifecycle su cui la challenger P1 (#297) deve ancora dire la sua.

        Riofferti finche' la decisione non e' terminale — P1 puo' restare
        aperta per due sedute dopo che il runtime ha gia' venduto — e ogni
        volta che l'osservazione di lifecycle a monte cambia (stessa regola di
        #374: senza, una correzione dell'ingresso non si propagherebbe mai).

        Lo stop congelato all'ingresso viaggia con la riga: il controfattuale
        deve applicare la distanza point-in-time, non una ricalcolata oggi.
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        lc.*,
                        t.stop_mode,
                        t.stop_d_init,
                        t.stop_vol_at_entry,
                        t.stop_floor,
                        t.stop_cap
                    FROM s4_lifecycle_current lc
                    LEFT JOIN trades t ON t.entry_order_id = lc.order_id
                    LEFT JOIN s4_exit_policy_current p1
                      ON p1.intent_id = lc.intent_id
                     AND p1.policy_id = 'P1'
                    WHERE lc.filled_quantity > 0
                      AND (
                          p1.intent_id IS NULL
                          OR p1.status NOT IN ('CLOSED', 'RISK_EXITED', 'CENSORED')
                          OR p1.details->>'entry_lifecycle_event_id'
                             IS DISTINCT FROM lc.event_id::text
                      )
                    ORDER BY lc.d0, lc.intent_id
                    """
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.rollback()

    def fetch_s4_exit_order_ids(self) -> dict[str, tuple[str, ...]]:
        """Ordini di uscita legati a ciascun ingresso S4, per entry_order_id.

        La chiave e' l'ordine d'ingresso, non il simbolo: legare le uscite al
        simbolo accrediterebbe a un intento l'uscita di un altro sullo stesso
        ticker, che e' esattamente il modo in cui un ammanco vero verrebbe
        spiegato via.
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        entry_order_id,
                        COALESCE(
                            exit_order_ids,
                            CASE
                                WHEN exit_order_id IS NULL THEN ARRAY[]::TEXT[]
                                ELSE ARRAY[exit_order_id]::TEXT[]
                            END
                        ) AS exit_order_ids
                    FROM trades
                    WHERE entry_order_id IS NOT NULL
                      AND entry_time > now() - '30 days'::interval
                    """
                )
                rows = cur.fetchall()
            return {
                str(row["entry_order_id"]): tuple(
                    str(order_id)
                    for order_id in (row["exit_order_ids"] or ())
                    if order_id
                )
                for row in rows
                if row["exit_order_ids"]
            }
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
        before: tuple | None = None,
    ) -> list[dict]:
        """Return one page of trade-filter skip rows with no counterfactual yet.

        Args:
            days_back: how far back to look.
            limit: page size.
            before: keyset cursor ``(tick_time, id)`` from the previous page —
                only rows strictly older than it are returned. ``None`` starts
                from the newest row.

        Rows come back newest-first, ordered by ``(tick_time DESC, id DESC)``
        so the cursor is total: no row is skipped or returned twice across
        pages. #337: the old caller took a single ``LIMIT 500`` page and dropped
        everything older, which systematically starved the first hour of each
        session. Use fetch_all_skip_decisions_without_counterfactual() to page
        to exhaustion.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                params: list = [str(days_back)]
                cursor_clause = ""
                if before is not None:
                    cursor_clause = "AND (tick_time, id) < (%s, %s)"
                    params.extend([before[0], before[1]])
                params.append(limit)
                cur.execute(
                    f"""SELECT id, tick_time, symbol, score, regime_mult, decision,
                               COALESCE(counterfactual_attempts, 0) AS counterfactual_attempts
                       FROM execution_decisions
                       WHERE decision IN ('SKIP_THRESHOLD', 'SKIP_EMA', 'SKIP_CAP', 'SKIP_PYRAMIDING')
                         AND counterfactual_computed_at IS NULL
                         AND tick_time >= now() - (%s || ' days')::interval
                         {cursor_clause}
                       ORDER BY tick_time DESC, id DESC
                       LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def fetch_all_skip_decisions_without_counterfactual(
        self,
        days_back: int = 7,
        page_size: int = 500,
        max_rows: int = 20000,
    ) -> list[dict]:
        """Page through every pending skip row in the window until exhaustion.

        #337: replaces the single ``LIMIT 500`` batch. Because the pages are
        keyset-driven rather than offset-driven, rows the worker deliberately
        leaves pending (PENDING_OVERNIGHT) do not re-enter later pages of the
        same run, so this terminates.

        ``max_rows`` is a safety bound on a pathological backlog, not an
        expected limit: a 7-day window at ~600 skips/day is ~4200 rows.
        """
        collected: list[dict] = []
        before: tuple | None = None
        while len(collected) < max_rows:
            requested = min(page_size, max_rows - len(collected))
            page = self.fetch_skip_decisions_without_counterfactual(
                days_back=days_back,
                limit=requested,
                before=before,
            )
            if not page:
                break
            page = page[:requested]  # keep max_rows a hard bound
            collected.extend(page)
            last = page[-1]
            before = (last["tick_time"], last["id"])
            if len(page) < requested:
                break
        return collected

    def fetch_force_exit_decisions_without_counterfactual(
        self,
        days_back: int | None = None,
        limit: int = 500,
        before: tuple | None = None,
    ) -> list[dict]:
        """Return one page of force-exit SELL rows with no counterfactual yet.

        #450: ``decision='SELL'`` AND ``reason LIKE 'sentiment_reversal%'`` is
        the population written by ``_sentiment_reversal_sells`` in
        ``portfolio_scheduler.py`` (L4742-4796). It is the *only* universe of
        force-exit SELLs the operator can answer for today: stop-loss SELLs
        are routed through ``stop_policy`` and ``record_trade_exit`` with a
        distinct ``exit_reason``, and ordinary portfolio rebalance SELLs
        carry ``reason='portfolio_sell'`` — not in scope. LIKE on the reason
        prefix is safe because the writer prefixes every row with
        ``sentiment_reversal`` (the score and threshold suffix is parseable
        but not used for routing).

        ``days_back=None`` (the default) means NO time window, unlike the
        SKIP fetcher's 7 days. The force-exit universe is small and
        append-only (33 rows over two months of live record), but it
        predates this fix, so a window would leave the historical rows NULL
        forever — the acceptance criterion asks for all of them. Boundedness
        comes from the migration-060 partial index: processed rows leave it
        because ``counterfactual_computed_at`` is set, and terminal-reason
        rows are frozen by the attempt budget (#337), so the steady-state
        scan reads only the genuinely pending handful.

        Args: otherwise identical contract to
        ``fetch_skip_decisions_without_counterfactual`` so the two paths
        share the keyset paged-iteration pattern (#337).
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                params: list = []
                window_clause = ""
                if days_back is not None:
                    window_clause = "AND tick_time >= now() - (%s || ' days')::interval"
                    params.append(str(days_back))
                cursor_clause = ""
                if before is not None:
                    cursor_clause = "AND (tick_time, id) < (%s, %s)"
                    params.extend([before[0], before[1]])
                params.append(limit)
                cur.execute(
                    f"""SELECT id, tick_time, symbol, score, regime_mult, decision,
                               COALESCE(counterfactual_attempts, 0) AS counterfactual_attempts
                       FROM execution_decisions
                       WHERE decision = 'SELL'
                         AND reason LIKE 'sentiment_reversal%'
                         AND counterfactual_computed_at IS NULL
                         {window_clause}
                         {cursor_clause}
                       ORDER BY tick_time DESC, id DESC
                       LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def fetch_all_force_exit_decisions_without_counterfactual(
        self,
        days_back: int | None = None,
        page_size: int = 500,
        max_rows: int = 20000,
    ) -> list[dict]:
        """Page through every pending force-exit SELL row.

        #450: same keyset exhaustion pattern as
        ``fetch_all_skip_decisions_without_counterfactual``. ``days_back``
        defaults to None (no time window — see the single-page method) so one
        run also backfills the pre-fix history. Rows the worker deliberately
        leaves pending (PENDING_OVERNIGHT) are pruned by the
        ``counterfactual_computed_at IS NULL`` predicate in the inner page
        query, so they do not re-enter later pages of the same run.
        """
        collected: list[dict] = []
        before: tuple | None = None
        while len(collected) < max_rows:
            requested = min(page_size, max_rows - len(collected))
            page = self.fetch_force_exit_decisions_without_counterfactual(
                days_back=days_back,
                limit=requested,
                before=before,
            )
            if not page:
                break
            page = page[:requested]
            collected.extend(page)
            last = page[-1]
            before = (last["tick_time"], last["id"])
            if len(page) < requested:
                break
        return collected

    def bulk_set_counterfactual(
        self,
        updates: list[tuple],
    ) -> int:
        """Bulk-write the counterfactual outcome of a set of decisions.

        Args:
            updates: list of tuples, either
                ``(decision_id, return_1h_or_None, computed_at)`` — legacy 3-tuple,
                writes no reason/overnight/attempt state — or the full
                ``(decision_id, return_1h_or_None, computed_at_or_None,
                skip_reason_or_None, return_overnight_or_None, attempts)``.

                #337: ``computed_at=None`` means "deliberately left pending, retry
                on the next run"; ``attempts`` is what stops that from looping
                forever. ``skip_reason`` records *why* a NULL return is NULL, so
                the censoring is readable at query time instead of inferred.
        Returns:
            Number of rows updated.
        """
        if not updates:
            return 0

        def _normalise(u: tuple) -> tuple:
            if len(u) == 3:
                did, ret, ts = u
                return (ret, ts, None, None, 0, did)
            did, ret, ts, reason, overnight, attempts = u
            return (ret, ts, reason, overnight, attempts, did)

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    """UPDATE execution_decisions
                       SET counterfactual_return_1h = %s,
                           counterfactual_computed_at = %s,
                           counterfactual_skip_reason = %s,
                           counterfactual_return_overnight = %s,
                           counterfactual_attempts = %s
                       WHERE id = %s""",
                    [_normalise(u) for u in updates],
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

    # #450: pair each sentiment_reversal exit with both the realised P&L and
    # the counterfactual return the worker computed, so the operator can
    # read "is this rule net-positive?" from a single SELECT.
    #
    # The join is on t.exit_order_id = ed.order_id (NOT t.decision_id = ed.id)
    # because the writer that submits the SELL order
    # (_sentiment_reversal_sells, portfolio_scheduler L4742-4796) sets
    # ed.order_id AFTER calling record_trade_exit — ed.id is not yet known to
    # the trade writer, so the back-link is the order id.
    _FORCE_EXIT_VS_COUNTERFACTUAL_SQL = """
        SELECT
            ed.symbol,
            ed.tick_time,
            ed.id        AS decision_id,
            t.id         AS trade_id,
            t.net_pnl    AS realized_net_pnl,
            t.exit_price AS realized_exit_price,
            t.entry_price,
            t.exit_reason,
            ed.counterfactual_return_1h,
            ed.counterfactual_return_overnight,
            ed.counterfactual_computed_at,
            ed.counterfactual_skip_reason
        FROM execution_decisions ed
        JOIN trades t
          ON t.exit_reason   = 'sentiment_reversal'
         AND (t.exit_order_id = ed.order_id
              OR ed.order_id = ANY(t.exit_order_ids))
        WHERE ed.decision = 'SELL'
          AND ed.reason LIKE 'sentiment_reversal%'
          AND ed.tick_time >= now() - (%s || ' days')::interval
        ORDER BY ed.tick_time DESC
    """

    def fetch_force_exit_pnl_vs_counterfactual(self, days: int = 30) -> list[dict]:
        """Return one row per sentiment_reversal exit, paired with its counterfactual.

        #450: ``trades.exit_reason='sentiment_reversal'`` rows whose exit
        order matches a ``SELL`` execution_decision with reason
        ``sentiment_reversal`` — on ``exit_order_id`` or, for a position
        already partially exited, on ``exit_order_ids`` (record_trade_exit
        keeps the FIRST tranche's id in ``exit_order_id``, so a later
        reversal SELL lands only in the array). The pair carries the
        realised P&L, the exit price, the entry price, and the worker's two
        counterfactual returns (1h or overnight depending on when the SELL
        fired).

        Sign convention reminder: for a SELL, the counterfactual_return_1h
        stored in the row is the *negative* of the underlying price move
        (so a future DROP shows as a positive "saved" return — same axis as
        SKIP_*, where a positive return means "the gate skipped a winner").
        Comparing the realised P&L directly to counterfactual_return_1h
        therefore puts both metrics on a "savings" axis: positive on either
        column is good for the decision.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FORCE_EXIT_VS_COUNTERFACTUAL_SQL, (str(days),))
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            return rows
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
        strategy: str | None = None,
    ) -> None:
        """Insert an open trade row (entry_price populated later by reconcile).

        Args:
            score: Portfolio allocation weight (e.g. 0.02 = 2% target weight).
            signal_score: Actual LLM sentiment score that motivated the trade.
                Stored separately so IC / score-bucket analytics are meaningful.
            frozen_stop: Optional frozen stop parameters (migration 034).
            strategy: Origin sleeve. When omitted, infer S4 from a signal-backed
                trade and S1 otherwise; attribution must not depend on stop freezing.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                fs = frozen_stop
                origin_strategy = strategy or (
                    fs.strategy if fs else ("S4" if signal_id is not None else "S1")
                )
                cur.execute(
                    self._INSERT_TRADE,
                    (symbol, signal_id, decision_id, entry_order_id,
                     entry_time, entry_notional, score, regime_mult, qty, signal_score,
                     origin_strategy,
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
                            "stop_strategy": origin_strategy,
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

    def record_news_discards(self, rows: list[dict]) -> None:
        """Persist structured news discard events for FIX-06 measurement."""
        if not rows:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO news_queue_drops
                        (item_id, article_id, symbol, source, published_at,
                         age_hours, title, url, raw_ingested_at, content_hash,
                         discarded_reason, discard_stage)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            r["item_id"], r["article_id"], r.get("symbol"),
                            r.get("source"), r.get("published_at"),
                            r.get("age_hours"), r.get("title"), r.get("url"),
                            r.get("raw_ingested_at"), r.get("content_hash"),
                            r["discarded_reason"], r["discard_stage"],
                        )
                        for r in rows
                    ],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def record_news_queue_drops(self, rows: list[dict]) -> None:
        """Backward-compatible #149 writer; legacy callers mean stale/sentiment."""
        normalized = [
            {
                **row,
                "discarded_reason": row.get("discarded_reason", "stale"),
                "discard_stage": row.get("discard_stage", "sentiment"),
            }
            for row in rows
        ]
        self.record_news_discards(normalized)

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
                               stop_strategy, stop_d_init,
                               quantity_remaining, exit_order_ids
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
                        nav,
                        total_exposure
                    FROM risk_reports
                    WHERE nav IS NOT NULL
                      AND (timestamp AT TIME ZONE 'UTC')::date BETWEEN %s AND %s
                    ORDER BY day, timestamp DESC
                    """,
                    (from_date, to_date),
                )
                return [
                    {
                        "date": str(row[0]),
                        "nav": float(row[1]),
                        "exposure": float(row[2]) if row[2] is not None else None,
                    }
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
                                   cost_bps    = %s,
                                   quantity_remaining = %s
                               WHERE id = %s""",
                            (fill_price, fill_qty,
                             entry_costs.total_cost_usd, entry_costs.total_cost_bps,
                             fill_qty, trade_id),
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
                               slippage_est = %s,
                               quantity_remaining = GREATEST(0, qty - %s)
                               WHERE id = %s""",
                            (avg_exit_price, qty_f, gross_pnl, net_pnl,
                             costs.total_cost_bps, costs.total_cost_usd,
                             costs.spread_cost_bps, costs.impact_cost_bps,
                             costs.regulatory_cost_usd, costs.total_cost_usd,
                             qty_f, trade_id),
                        )
                    exit_updated += 1
                except Exception as e:
                    log.warning("Failed to reconcile exit order(s) %s for trade %s: %s", order_ids, trade_id, e)
            conn.commit()
            return updated + exit_updated
        except Exception:
            conn.rollback()
            raise

    def reconcile_open_positions(
        self,
        trading_client,
        *,
        lookback_days: int = 30,
        symbols: list[str] | None = None,
    ) -> int:
        """#397: maintain ``quantity_remaining`` for OPEN trades and write back
        broker-side SELL fills (incl. protective-stop fills) that never reached
        ``record_trade_exit``.

        ``trades.qty`` is the entry fill qty while a trade is open; partial exits
        and broker-side stop fills were never decremented, so an open row could
        state 74x the live broker position (NOK/WDC/MRVL, [F-048]). This method
        recomputes the live quantity from authoritative broker SELL fills:

        For every open trade (``exit_time IS NULL``) with a reconciled entry
        (``qty IS NOT NULL``) within ``lookback_days``:
          - pull the broker's CLOSED orders for the symbol since entry,
          - take every filled SELL (the portfolio tranches already in
            ``exit_order_ids`` AND the protective-stop fills that are not),
          - ``quantity_remaining = entry_qty - sum(filled SELL qty)`` (clamped 0),
          - append any newly-discovered SELL order id to ``exit_order_ids`` so the
            next ``reconcile_trade_fills`` prices it from the real fill,
          - if the position is exhausted (remaining <= eps), close the trade
            (``exit_time``/``exit_reason='reconcile_close'``).

        Idempotent recompute, not accumulate: re-running with the same broker
        state yields the same ``quantity_remaining`` and appends nothing. It never
        touches ``exit_price``/``gross_pnl``/``net_pnl`` — those stay with
        ``reconcile_trade_fills``, which prices from the real order ids now linked
        in ``exit_order_ids``. So closing here is backed by a real broker fill,
        not the synthetic-id inference that ``force_close_orphans`` deliberately
        avoids for genuinely-orphan trades.

        Returns the count of open-trade rows updated (remaining set and/or
        trade closed). Best-effort per trade: one symbol's broker fetch failure
        is logged and skipped, never aborting the rest.
        """
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        conn = self._get_connection()
        updated = 0
        try:
            with conn.cursor() as cur:
                filters = ["exit_time IS NULL", "qty IS NOT NULL"]
                params: list = []
                if symbols:
                    filters.append("symbol = ANY(%s)")
                    params.append(list(symbols))
                if lookback_days:
                    filters.append(f"entry_time > now() - '{int(lookback_days)} days'::interval")
                where = " AND ".join(filters)
                cur.execute(
                    f"""SELECT id, symbol, qty, entry_time, exit_order_ids
                        FROM trades
                        WHERE {where}""",
                    params,
                )
                open_rows = cur.fetchall()

            for trade_id, symbol, qty, entry_time, exit_order_ids in open_rows:
                try:
                    entry_qty = float(qty)
                    # Pull the broker's closed orders for this symbol since
                    # entry. `after` bounds by created_at; we re-bound by
                    # filled_at >= entry_time below so a stop placed before a
                    # later re-entry cannot steal an earlier trade's fill
                    # (pyramiding guard => one open trade/symbol anyway).
                    request = GetOrdersRequest(
                        status=QueryOrderStatus.CLOSED,
                        symbols=[symbol],
                        after=entry_time,
                        limit=500,
                    )
                    broker_orders = trading_client.get_orders(request)
                    fills: list[tuple[str, float]] = []
                    for o in broker_orders:
                        side = getattr(o, "side", None)
                        side_val = getattr(side, "value", side)
                        if str(side_val).lower() != "sell":
                            continue
                        raw_qty = getattr(o, "filled_qty", None)
                        if raw_qty is None:
                            continue
                        filled_at = getattr(o, "filled_at", None)
                        if filled_at is not None and filled_at < entry_time:
                            continue  # fill predates this trade's entry
                        fills.append((str(o.id), float(raw_qty)))

                    remaining, new_ids = remaining_after_exits(
                        entry_qty, exit_order_ids, fills,
                    )
                    # No exits recorded and none discovered: a fresh, fully-held
                    # position — quantity_remaining is set at entry reconcile, so
                    # there is nothing to write here. Keeps the common case off
                    # the write path.
                    if not exit_order_ids and not new_ids:
                        continue

                    merged_ids = list(exit_order_ids or [])
                    for oid in new_ids:
                        if oid not in merged_ids:
                            merged_ids.append(oid)

                    exhausted = remaining <= _QUANTITY_EPS
                    if exhausted:
                        log.info(
                            "#397: closing trade %s (%s): position exhausted by "
                            "broker SELL fill(s) %s newly linked to exit_order_ids",
                            trade_id, symbol,
                            ",".join(new_ids) or "(all already recorded)",
                        )
                    with conn.cursor() as cur:
                        if exhausted:
                            cur.execute(
                                """UPDATE trades
                                   SET quantity_remaining = %s,
                                       exit_order_ids = %s,
                                       exit_time = COALESCE(exit_time, now()),
                                       exit_reason = COALESCE(exit_reason, 'reconcile_close')
                                   WHERE id = %s""",
                                (remaining, merged_ids or None, trade_id),
                            )
                        else:
                            cur.execute(
                                """UPDATE trades
                                   SET quantity_remaining = %s,
                                       exit_order_ids = %s
                                   WHERE id = %s""",
                                (remaining, merged_ids or None, trade_id),
                            )
                    updated += 1
                except Exception as e:
                    log.warning(
                        "#397: open-position reconcile failed for trade %s (%s): %s",
                        trade_id, symbol, e,
                    )
            conn.commit()
            return updated
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
                            out.reasoning, out.event_type, out.directness,
                            out.materiality, out.novelty, out.risk_flags,
                            out.evidence_sentences,
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
                         bool(r.get("parse_error", False)), r.get("latency_ms"),
                         r.get("failure_reason"))
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
        SELECT DISTINCT ON (ss.symbol)
            ss.id, ss.symbol, ss.score, ss.confidence,
            COALESCE(ss.reasoning, '') AS reasoning,
            ss.model_id, ss.ensemble_std, ss.fallback_used,
            ss.generated_at, ss.published_at, ss.news_log_id,
            COALESCE(nl.raw_ingested_at, nl.fetched_at, nl.created_at) AS first_seen_at,
            nl.source AS news_source, nl.content_hash, nl.extraction_method,
            resolver.decision AS resolver_decision,
            resolver.extraction_method AS resolver_method
        FROM sentiment_signals AS ss
        LEFT JOIN news_log AS nl ON nl.id = ss.news_log_id
        LEFT JOIN LATERAL (
            SELECT nre.decision, nre.extraction_method
            FROM news_resolved_entities AS nre
            WHERE nre.news_log_id = ss.news_log_id
              AND nre.candidate_ticker = ss.symbol
            ORDER BY nre.created_at DESC, nre.id DESC
            LIMIT 1
        ) AS resolver ON TRUE
        WHERE ss.generated_at >= NOW() - (%s || ' hours')::interval
          AND (ss.published_at IS NULL
               OR ss.published_at >= NOW() - (%s || ' hours')::interval)
          AND ss.symbol = ANY(%s)
        ORDER BY ss.symbol, ss.fallback_used ASC, ss.generated_at DESC
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
            published_at = row.get("published_at")
            if published_at is not None and published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=_tz.utc)
            first_seen_at = row.get("first_seen_at")
            if first_seen_at is not None and first_seen_at.tzinfo is None:
                first_seen_at = first_seen_at.replace(tzinfo=_tz.utc)
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
                    published_at=published_at,
                    signal_id=row.get("id"),
                    news_log_id=row.get("news_log_id"),
                    first_seen_at=first_seen_at,
                    news_source=row.get("news_source"),
                    content_hash=row.get("content_hash"),
                    extraction_method=row.get("extraction_method"),
                    resolver_decision=row.get("resolver_decision"),
                    resolver_method=row.get("resolver_method"),
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
