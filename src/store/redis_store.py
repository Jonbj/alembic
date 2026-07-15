"""Redis store for signals, kill-switch, and fallback counters."""

import json
from datetime import datetime, timezone
from typing import Callable, Optional

from redis import Redis

from src.config import config
from src.models.signals import SentimentResult


class RedisStore:
    """
    Redis storage for all trading system state.

    Grouped by domain:

    Signals:
        write_sentiment / read_sentiment — sentiment signals with 4h TTL

    Kill-switch:
        activate_killswitch / deactivate_killswitch / is_killswitch_active
        get_killswitch_reason

    Fallback circuit breaker:
        increment_fallback_counter / reset_fallback_counter / get_fallback_count
        is_fallback_alert_sent / reset_fallback_alert_flag
        get_qc_sizing_multiplier / set_qc_sizing_multiplier

    Divergence log:
        log_divergence / get_recent_divergences — list of last 1000 events

    Budget tracking:
        set_budget_exhausted / is_budget_exhausted / reset_budget_status

    Ensemble weights:
        get_ensemble_weights / set_ensemble_weights
        get_weight_suggestion / get_current_weights_stored
        delete_weight_suggestion / delete_suggestion_snapshot

    Performance:
        get_performance_report

    Regime detection:
        set_regime / get_regime — RegimeState JSON with TTL

    VIX cache:
        get_vix_cached / set_vix_cached — reduces FRED API calls

    Telegram poller:
        get_offset / set_offset — polling continuity across restarts (no TTL)

    Operating mode:
        set_mode / get_mode — backtest | paper | semi_auto | full_auto | halted
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

    def write_sentiment(self, result: SentimentResult, signal_id: int | None = None) -> None:
        """Write sentiment signal to Redis cache.

        Args:
            result: Sentiment result to cache
            signal_id: DB row id from pg_store.write_signal(), embedded so execution worker
                       can read it without a DB round-trip.
        """
        key = f"signal:{result.symbol}:sentiment"
        payload = json.loads(result.model_dump_json())
        if signal_id is not None:
            payload["signal_id"] = signal_id
        try:
            self._r.setex(key, self._signal_ttl, json.dumps(payload))
        except Exception as e:
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - dropping sentiment signal for {result.symbol}")
            else:
                raise

    def append_signal_history(self, symbol: str, score: float) -> None:
        """Append score to signal history list (max 5 entries, newest first).

        Key: signal:{symbol}:history — Redis list, LPUSH keeps newest at index 0.
        """
        key = f"signal:{symbol}:history"
        self._r.lpush(key, json.dumps({"score": score}))
        self._r.ltrim(key, 0, 4)  # keep last 5

    def get_signal_history(self, symbol: str, n: int = 3) -> list:
        """Return the last n sentiment scores for symbol (newest first).

        Returns empty list if no history exists or on any error.
        """
        key = f"signal:{symbol}:history"
        raw_list = self._r.lrange(key, 0, n - 1)
        scores = []
        for raw in raw_list:
            try:
                scores.append(float(json.loads(raw)["score"]))
            except (KeyError, ValueError, TypeError):
                pass
        return scores

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

    def activate_killswitch(self, reason: str = "", ttl: int | None = None) -> None:
        """
        Activate the kill-switch to halt trading.

        Args:
            reason: Optional reason for activation
            ttl: Optional TTL in seconds. None = permanent (manual deactivation required).
                 Pass 86400 for auto-drawdown triggers (auto-expires after 24h).
        """
        pipe = self._r.pipeline()
        if ttl is not None:
            pipe.setex("killswitch_active", ttl, 1)
            pipe.setex(
                "killswitch_reason",
                ttl,
                json.dumps(
                    {
                        "reason": reason,
                        "activated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
        else:
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

    def activate_operator_halt(self, reason: str = "manual operator halt") -> None:
        """Activate a permanent operator-initiated halt using a separate key.

        Unlike drawdown-triggered halts (which use killswitch_active with a TTL),
        this key has no TTL and must be explicitly cleared with deactivate_operator_halt().
        A Redis restart will lose this state — configure Redis persistence (appendonly yes)
        for production deployments.
        """
        pipe = self._r.pipeline()
        pipe.set("system:halted_by_operator", 1)
        pipe.set(
            "system:halted_by_operator_reason",
            json.dumps({"reason": reason, "activated_at": datetime.now(timezone.utc).isoformat()}),
        )
        try:
            pipe.execute()
        except Exception as e:
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - failed to activate operator halt (reason: {reason})")
            else:
                raise

    def deactivate_operator_halt(self) -> None:
        """Clear the operator-initiated halt."""
        self._r.delete("system:halted_by_operator", "system:halted_by_operator_reason")

    def deactivate_killswitch(self) -> None:
        """Deactivate the drawdown-triggered kill-switch (TTL-based)."""
        self._r.delete("killswitch_active", "killswitch_reason")

    def is_killswitch_active(self) -> bool:
        """Check if any kill-switch is active (drawdown-triggered OR operator halt)."""
        return bool(self._r.get("killswitch_active")) or bool(self._r.get("system:halted_by_operator"))

    def get_killswitch_reason(self) -> dict | None:
        """Get kill-switch activation reason (drawdown-triggered or operator halt)."""
        for key in ("system:halted_by_operator_reason", "killswitch_reason"):
            data = self._r.get(key)
            if data is not None:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    pass
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

    def get_weekly_report(self) -> dict | None:
        """Get latest weekly report from Redis. Returns None if not available or corrupted."""
        raw = self._r.get("performance:weekly_report")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None

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

    def delete_weight_suggestion(self) -> bool:
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

        Returns:
            True if the suggestion was present and deleted, False if already absent.
        """
        return bool(self._r.delete("ensemble:weights:suggestion"))

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
    # LOSS FEEDBACK ADJUSTMENTS
    # =========================================================================

    @staticmethod
    def _feedback_key(base: str, strategy: str | None) -> str:
        return f"{base}:{strategy}" if strategy else base

    def set_feedback_entry_threshold(self, value: float, ttl: int, strategy: str | None = None) -> None:
        """Override ENTRY_THRESHOLD in Redis. Execution worker reads this at cycle start."""
        key = self._feedback_key("feedback:entry_threshold", strategy)
        self._r.setex(key, ttl, str(value))
        # Legacy compatibility: S4 is the original key owner; mirror it on the bare key.
        if strategy == "S4":
            self._r.setex("feedback:entry_threshold", ttl, str(value))

    def get_feedback_entry_threshold(self, strategy: str | None = None) -> float | None:
        """Return feedback-adjusted entry threshold, or None if not set."""
        key = self._feedback_key("feedback:entry_threshold", strategy)
        raw = self._r.get(key)
        if raw is None and strategy is not None:
            # Fallback to legacy key if per-strategy key is absent.
            raw = self._r.get("feedback:entry_threshold")
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    def set_feedback_regime_scale(self, value: float, ttl: int, strategy: str | None = None) -> None:
        """Override regime multiplier scale factor in Redis (0.0–1.0)."""
        key = self._feedback_key("feedback:regime_scale", strategy)
        self._r.setex(key, ttl, str(value))
        if strategy == "S4":
            self._r.setex("feedback:regime_scale", ttl, str(value))

    def get_feedback_regime_scale(self, strategy: str | None = None) -> float | None:
        """Return feedback regime scale factor, or None if not set (default 1.0)."""
        key = self._feedback_key("feedback:regime_scale", strategy)
        raw = self._r.get(key)
        if raw is None and strategy is not None:
            raw = self._r.get("feedback:regime_scale")
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    def set_feedback_state(self, state: dict, ttl: int, strategy: str | None = None) -> None:
        """Persist full feedback audit state (consecutive_losses, rolling_pnl, timestamp)."""
        import json
        key = self._feedback_key("feedback:state", strategy)
        self._r.setex(key, ttl, json.dumps(state))

    def get_feedback_state(self, strategy: str | None = None) -> dict | None:
        """Return persisted feedback audit state, or None if not set."""
        import json
        key = self._feedback_key("feedback:state", strategy)
        raw = self._r.get(key)
        if raw is None and strategy is not None:
            raw = self._r.get("feedback:state")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    # =========================================================================
    # SHADOW MODE TOGGLE (Stage 2 model comparison)
    # =========================================================================

    _SHADOW_START_KEY = "shadow:model_comparison:started_at"

    def set_shadow_comparison_start(self, iso_ts: str) -> None:
        """Arm Stage-2 shadow mode (operator action; auto-report disarms it)."""
        self._r.set(self._SHADOW_START_KEY, iso_ts)

    def get_shadow_comparison_start(self) -> str | None:
        """Get shadow comparison start timestamp if armed, or None."""
        raw = self._r.get(self._SHADOW_START_KEY)
        return raw.decode() if isinstance(raw, bytes) else raw

    def clear_shadow_comparison_start(self) -> None:
        """Disarm Stage-2 shadow mode (auto-called after reporting)."""
        self._r.delete(self._SHADOW_START_KEY)

    def set_counterfactual_worker_state(self, state: dict, ttl: int = 86400 * 14) -> None:
        """Persist last Phase C counterfactual worker run metadata."""
        self._r.setex("counterfactual:worker:last_run", ttl, json.dumps(state))

    def get_counterfactual_worker_state(self) -> dict | None:
        """Return last Phase C counterfactual worker run metadata, if available."""
        raw = self._r.get("counterfactual:worker:last_run")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

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

    # =========================================================================
    # LLM MODEL SELECTION (token-budget override)
    # =========================================================================

    def set_llm_models(self, models: str) -> None:
        """Persist LLM model selection override.

        Args:
            models: Canonical comma-separated model keys (e.g. "glm52,gptoss")
                or "all". "all" expands at read time to every model with
                in_all=True in src.llm.model_registry; it is NOT necessarily the
                live pair. Use explicit keys for deterministic pair selection.
        """
        self._r.set("config:sentiment_llm_models", models)

    def get_llm_models(self) -> str | None:
        """Return LLM model selection override, or None if not set (use env/default)."""
        raw = self._r.get("config:sentiment_llm_models")
        return raw.decode() if isinstance(raw, bytes) else raw

    # =========================================================================
    # PORTFOLIO VALUE
    # =========================================================================

    def set_portfolio_value(self, equity: float) -> None:
        """Cache current portfolio equity in Redis (24h TTL)."""
        self._r.setex("portfolio:value", 86400, str(equity))

    def get_portfolio_value(self) -> float | None:
        """Return cached portfolio equity, or None if not present."""
        raw = self._r.get("portfolio:value")
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    # =========================================================================
    # OVERNIGHT ALERT DEDUP
    # =========================================================================

    def is_overnight_alert_sent(self, date_str: str) -> bool:
        """Return True if the overnight hold alert was already sent for *date_str* (YYYY-MM-DD)."""
        return bool(self._r.get(f"overnight_alert:{date_str}"))

    def mark_overnight_alert_sent(self, date_str: str) -> None:
        """Record that the overnight hold alert was sent for *date_str*; expires after 24h."""
        self._r.setex(f"overnight_alert:{date_str}", 86400, "1")

    # =========================================================================
    # GRANULAR KILL-SWITCH INSPECTION (for auto-recovery logic)
    # =========================================================================

    def is_drawdown_killswitch_active(self) -> bool:
        """Return True if the drawdown-triggered kill-switch key is set (TTL-based)."""
        return bool(self._r.get("killswitch_active"))

    def is_operator_halted(self) -> bool:
        """Return True if the permanent operator halt key is set."""
        return bool(self._r.get("system:halted_by_operator"))

    # ------------------------------------------------------------------
    # PEAD signal helpers removed 2026-07-15 (S7 retired). The Redis keys
    # signal:{symbol}:pead_event and pead:processed:{filing_id} are no longer
    # written; any stale keys TTL out (30d). See docs/S7_LIFECYCLE_HISTORY_2026-07-15.md.
    # ------------------------------------------------------------------

    def __enter__(self) -> "RedisStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
