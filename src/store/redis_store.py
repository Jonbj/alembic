"""Redis store for signals, kill-switch, and fallback counters."""

import json
from datetime import datetime, timezone
from typing import Callable, Optional

from redis import Redis

from src.config import config
from src.models.signals import SentimentResult


class RedisStore:
    """
    Redis storage for trading system state.

    Features:
    - Signal caching (4 hour TTL)
    - Kill-switch activation
    - Consecutive fallback counter (circuit breaker)
    - Divergence logging
    - Budget exhaustion tracking
    """

    def __init__(
        self,
        redis_client: Optional[Redis] = None,
        on_fallback_alert: Optional[Callable[[int], None]] = None,
    ):
        """Initialize Redis store.

        Args:
            redis_client: Optional Redis client. If None, creates new connection.
            on_fallback_alert: Optional callback to invoke when fallback threshold
                               is reached. Signature: callback(count: int) -> None
        """
        self._r = redis_client
        self._owns_client = redis_client is None
        self._signal_ttl = config.REDIS_SIGNAL_TTL_SECONDS
        self._max_fallbacks = config.MAX_CONSECUTIVE_FALLBACKS
        self._on_fallback_alert = on_fallback_alert

        if self._r is None:
            self._r = Redis.from_url(config.REDIS_URL)

    def close(self) -> None:
        """Close Redis connection if we own it."""
        if self._owns_client:
            self._r.close()

    def write_sentiment(self, result: SentimentResult) -> None:
        """
        Write sentiment signal to Redis cache.

        Args:
            result: Sentiment result to cache
        """
        key = f"signal:{result.symbol}:sentiment"
        try:
            self._r.setex(key, self._signal_ttl, result.model_dump_json())
        except Exception as e:
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - dropping sentiment signal for {result.symbol}")
            else:
                raise

    def read_sentiment(self, symbol: str) -> dict | None:
        """
        Read cached sentiment for a symbol.

        Args:
            symbol: Asset symbol

        Returns:
            Dict with signal data or None if not found/expired
        """
        key = f"signal:{symbol}:sentiment"
        data = self._r.get(key)
        if data is None:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            # Corrupted JSON - log and return None
            print(f"RedisStore: Corrupted JSON for {symbol}")
            return None

    def activate_killswitch(self, reason: str = "") -> None:
        """
        Activate the kill-switch to halt trading.

        Args:
            reason: Optional reason for activation
        """
        pipe = self._r.pipeline()
        pipe.set("killswitch_active", 1)
        pipe.set(
            "killswitch_reason",
            json.dumps(
                {
                    "reason": reason,
                    "activated_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )
        try:
            pipe.execute()
        except Exception as e:
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - failed to activate killswitch (reason: {reason})")
            else:
                raise

    def deactivate_killswitch(self) -> None:
        """Deactivate the kill-switch."""
        self._r.delete("killswitch_active", "killswitch_reason")

    def is_killswitch_active(self) -> bool:
        """Check if kill-switch is active."""
        return bool(self._r.get("killswitch_active"))

    def get_killswitch_reason(self) -> dict | None:
        """Get kill-switch activation reason."""
        data = self._r.get("killswitch_reason")
        if data is None:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    # =========================================================================
    # FALLBACK COUNTER (Circuit Breaker)
    # =========================================================================
    # Spec requirement: "3 consensus fallback consecutivi → alert Telegram + QC sizing ×0.5"
    #
    # This counter tracks consecutive times the ensemble failed (divergence or
    # all models below confidence threshold) and fell back to FinBERT.
    #
    # When counter reaches 3:
    # 1. Send Telegram alert
    # 2. Set QC position sizing multiplier to 0.5
    # 3. Log audit event
    # =========================================================================

    def increment_fallback_counter(self) -> int:
        """
        Increment the consecutive fallback counter.

        Returns:
            New counter value after increment
        """
        try:
            # Atomic increment and get
            new_value = self._r.incr("fallback:consecutive:count")

            # Set expiry: counter resets after 24 hours of no fallbacks
            # This ensures "consecutive" means within a trading day
            self._r.expire("fallback:consecutive:count", 24 * 3600)

            # Check if we hit the threshold - trigger ONLY ONCE at exact threshold
            if new_value == self._max_fallbacks:
                self._on_fallback_threshold_reached(new_value)

            return new_value
        except Exception as e:
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - failed to increment fallback counter")
                return 0  # Return safe default
            else:
                raise

    def reset_fallback_counter(self) -> None:
        """Reset the consecutive fallback counter."""
        self._r.delete("fallback:consecutive:count")

    def get_fallback_count(self) -> int:
        """Get current consecutive fallback count."""
        val = self._r.get("fallback:consecutive:count")
        return int(val) if val else 0

    def _on_fallback_threshold_reached(self, count: int) -> None:
        """
        Called when fallback counter reaches MAX_CONSECUTIVE_FALLBACKS.

        Actions:
        1. Set QC sizing multiplier to 0.5
        2. Invoke callback for Telegram alert (if configured)
        3. Log to divergence log
        """
        # Set position sizing multiplier
        self._r.set("qc:sizing_multiplier", "0.5")
        self._r.expire("qc:sizing_multiplier", 24 * 3600)  # Reset after 24h

        # Mark that alert has been sent to prevent duplicates
        self._r.set("fallback:alert_sent", "1")
        self._r.expire("fallback:alert_sent", 24 * 3600)

        # Log the event
        self.log_divergence(
            symbol="SYSTEM",
            std=0.0,
            model_scores={"fallback_threshold_reached": count},
            event_type="fallback_circuit_breaker",
        )

        # Invoke callback for Telegram alert if configured
        if self._on_fallback_alert is not None:
            try:
                self._on_fallback_alert(count)
            except Exception as e:
                print(f"RedisStore: Failed to invoke fallback alert callback: {e}")

    def is_fallback_alert_sent(self) -> bool:
        """Check if fallback alert has been sent (for deduplication)."""
        return bool(self._r.get("fallback:alert_sent"))

    def reset_fallback_alert_flag(self) -> None:
        """Reset the alert sent flag (called when counter is reset)."""
        self._r.delete("fallback:alert_sent")

    def get_qc_sizing_multiplier(self) -> float:
        """Get current QuantConnect position sizing multiplier."""
        val = self._r.get("qc:sizing_multiplier")
        return float(val) if val else 1.0

    # =========================================================================
    # DIVERGENCE LOGGING
    # =========================================================================

    def log_divergence(
        self,
        symbol: str,
        std: float,
        model_scores: dict[str, float],
        event_type: str = "ensemble_divergence",
    ) -> None:
        """
        Log an ensemble divergence event.

        Args:
            symbol: Asset symbol (or "SYSTEM" for system-wide events)
            std: Ensemble standard deviation
            model_scores: Dict of model_id -> score
            event_type: Type of event ("ensemble_divergence" or "fallback_circuit_breaker")
        """
        entry = json.dumps(
            {
                "symbol": symbol,
                "std": std,
                "scores": model_scores,
                "ts": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
            }
        )

        # Push to divergence log list with OOM handling
        try:
            self._r.lpush("ensemble:divergence:log", entry)
            self._r.ltrim("ensemble:divergence:log", 0, 999)
            self._r.expire("ensemble:divergence:log", 24 * 3600)
        except Exception as e:
            # Handle Redis OOM (Out Of Memory) gracefully
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - dropping divergence log entry for {symbol}")
            else:
                raise  # Re-raise other exceptions

    def get_recent_divergences(self, limit: int = 10) -> list[dict]:
        """Get recent divergence events."""
        entries = self._r.lrange("ensemble:divergence:log", 0, limit - 1)
        return [json.loads(e) for e in entries]

    # =========================================================================
    # BUDGET TRACKING (Redis cache for budget status)
    # =========================================================================

    def set_budget_exhausted(self) -> None:
        """Mark LLM budget as exhausted for today."""
        try:
            self._r.set("budget:exhausted", "1")
            # TTL until midnight + 1 hour buffer
            now = datetime.now(timezone.utc)
            midnight = now.replace(hour=23, minute=59, second=59, microsecond=0)
            ttl = int((midnight - now).total_seconds()) + 3600
            self._r.expire("budget:exhausted", ttl)
        except Exception as e:
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - failed to set budget exhausted flag")
            else:
                raise

    def is_budget_exhausted(self) -> bool:
        """Check if LLM budget is exhausted."""
        return bool(self._r.get("budget:exhausted"))

    def reset_budget_status(self) -> None:
        """Reset budget exhausted status (called at midnight)."""
        self._r.delete("budget:exhausted")

    # =========================================================================
    # ENSEMBLE WEIGHTS
    # =========================================================================

    def get_ensemble_weights(self) -> str | None:
        """Get current ensemble weights from Redis."""
        return self._r.get("ensemble:weights:current")

    def set_ensemble_weights(self, weights: dict[str, float], source: str = "auto") -> None:
        """Store ensemble weights in Redis."""
        data = json.dumps({"weights": weights, "source": source})
        self._r.setex("ensemble:weights:current", 86400 * 30, data)

    def get_weight_suggestion(self) -> dict | None:
        """Get current weight suggestion from Redis. Returns None if absent or corrupted."""
        raw = self._r.get("ensemble:weights:suggestion")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def get_current_weights_stored(self) -> dict | None:
        """Get stored ensemble weights from Redis. Returns None if not set."""
        raw = self._r.get("ensemble:weights:current")
        if raw is None:
            return None
        return json.loads(raw)

    def get_performance_report(self) -> dict | None:
        """Get latest performance report from Redis. Returns None if not available."""
        raw = self._r.get("performance:latest_report")
        if raw is None:
            return None
        return json.loads(raw)

    def get_vix_cached(self) -> float | None:
        """Get cached VIX value from Redis. Returns None if absent or corrupted."""
        raw = self._r.get("macro:vix:latest")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            # Corrupted data in Redis - log and return None
            print(f"RedisStore: Corrupted VIX data in cache: {raw!r}")
            return None

    def set_vix_cached(self, value: float, ttl: int = 3600) -> None:
        """Cache VIX value in Redis with TTL in seconds."""
        self._r.setex("macro:vix:latest", ttl, str(value))

    def delete_suggestion_snapshot(self) -> None:
        """Delete the weight suggestion snapshot key."""
        self._r.delete("ensemble:weights:suggestion:snapshot")

    # =========================================================================
    # TELEGRAM POLLER OFFSET
    # =========================================================================
    #
    # These methods support the Telegram approval flow (Feature C).
    # The poll_telegram_updates task stores its progress in Redis to avoid
    # reprocessing the same callbacks on every run.
    #
    # Key: telegram:poller:offset
    # Value: Integer (last update_id + 1)
    # TTL: None — must survive restarts to maintain polling continuity
    #
    # =========================================================================

    def get_offset(self) -> int | None:
        """
        Get stored Telegram update offset from Redis.

        Returns:
            Integer offset if set, None if not yet initialized.
            The poller treats None as 0 (start from beginning).
        """
        raw = self._r.get("telegram:poller:offset")
        return int(raw) if raw else None

    def set_offset(self, offset: int) -> None:
        """
        Store Telegram update offset in Redis.

        Called after successfully processing a batch of updates.
        On error during processing, this is NOT called, so the next
        run retries the same updates (idempotent retry).

        Args:
            offset: The next update_id to fetch (last_processed + 1)
        """
        self._r.set("telegram:poller:offset", offset)

    def delete_weight_suggestion(self) -> None:
        """
        Delete the weight suggestion key after approval or rejection.

        Called by both _handle_approve and _handle_reject in telegram_poller.py.
        Deleting the suggestion:
        - Prevents double-processing (second tap finds None → "Già processata")
        - Cleans up Redis memory
        - Invalidates any old keyboard messages (stale token guard)

        Note: This only deletes ensemble:weights:suggestion.
        The snapshot key (ensemble:weights:suggestion:snapshot) is deleted
        separately by check_suggestion_expiry or on successful approval.
        """
        self._r.delete("ensemble:weights:suggestion")

    # =========================================================================
    # REGIME DETECTION
    # =========================================================================

    def set_regime(self, state: "RegimeState", ttl: int) -> None:  # type: ignore[name-defined]
        """Persist RegimeState JSON in Redis with TTL."""
        from src.models.regime import RegimeState  # local import to avoid circular
        self._r.setex("regime:current", ttl, state.model_dump_json())

    def get_regime(self) -> "RegimeState | None":  # type: ignore[name-defined]
        """Read RegimeState from Redis. Returns None if absent or corrupted."""
        from src.models.regime import RegimeState
        raw = self._r.get("regime:current")
        if raw is None:
            return None
        try:
            return RegimeState.model_validate_json(raw)
        except Exception:
            return None

    def set_qc_sizing_multiplier(self, value: float, ttl: int) -> None:
        """Write qc:sizing_multiplier with TTL. Overwrites existing value."""
        self._r.setex("qc:sizing_multiplier", ttl, str(value))

    # =========================================================================
    # OPERATING MODE
    # =========================================================================

    def set_mode(self, mode: str) -> None:
        """Set system operating mode.

        Args:
            mode: One of "backtest", "paper", "semi_auto", "full_auto", "halted"
        """
        try:
            self._r.set("system:mode", mode)
            self._r.expire("system:mode", 86400 * 30)  # 30 days TTL
        except Exception as e:
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - failed to set mode to {mode}")
            else:
                raise

    def get_mode(self) -> str | None:
        """Get current system operating mode."""
        return self._r.get("system:mode")

    def __enter__(self) -> "RedisStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
