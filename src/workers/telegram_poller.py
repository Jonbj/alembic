"""Telegram poller Celery task — processes inline keyboard callbacks for weight approval.

This module implements the Telegram approval flow for ensemble weight suggestions.
When the performance worker calculates new weights but guardrails block auto-apply,
a freeze notification is sent with inline keyboard buttons (✅ Approva / ❌ Rifiuta).
This poller runs every 5 seconds via Celery beat to process user taps.

Architecture:
    Celery beat (5s) → poll_telegram_updates() → GET /getUpdates → process callbacks

    - User authorization via TELEGRAM_ALLOWED_USER_IDS allowlist
    - Token-based anti-replay: SHA256(computed_at)[:8] validates callback freshness
    - Idempotent: double-taps find deleted suggestion → "Già processata"
    - Fail-safe: HTTP errors don't update offset → retry next run

Redis Keys:
    telegram:poller:offset — Last processed update_id + 1 (no TTL, survives restarts)
    ensemble:weights:suggestion — Current pending suggestion (7d TTL)

PostgreSQL Tables:
    weight_update_log — Audit trail for all approval/rejection events

Usage:
    The task is automatically scheduled by Celery beat. No manual invocation needed.
    Ensure TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS are set in environment.
"""

import hashlib
import logging

import httpx

from src.config import config
from src.notifications.telegram import TelegramNotifier
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)


def _compute_suggestion_token(computed_at: str) -> str:
    """
    Compute 8-character SHA256 token from suggestion timestamp for anti-replay.

    The token is embedded in callback_data as "approve:<token>" or "reject:<token>".
    When a user taps, we recompute the token from the current Redis suggestion
    and compare. Mismatch means:
    - Suggestion was replaced by newer run (stale message)
    - Suggestion already processed and deleted (double-tap)

    Args:
        computed_at: ISO timestamp from suggestion["computed_at"]

    Returns:
        8-character hex string (first 8 chars of SHA256)
    """
    return hashlib.sha256(computed_at.encode()).hexdigest()[:8]


@app.task(name="src.workers.telegram_poller.poll_telegram_updates")
def poll_telegram_updates() -> None:
    """
    Poll Telegram /getUpdates every 5s, process callback_query for approve/reject.

    Guardrail cascade (execution order):
    1. TELEGRAM_ALLOWED_USER_IDS empty → silent exit (polling disabled)
    2. HTTP /getUpdates fails → log error, don't update offset (retry next run)
    3. No callback_query in updates → update offset only
    4. User not in allowlist → silent rejection (no answerCallbackQuery)
    5. Token mismatch (stale/double-tap) → "Già processata", remove keyboard
    6. Valid approve → apply weights, log to PG, delete suggestion, remove keyboard
    7. Valid reject → delete suggestion, log to PG with empty weights, remove keyboard

    Fail-safe behaviors:
    - Redis down during approve → exception raised, offset NOT updated → retry processes same callback
    - Telegram API down → HTTPError caught, offset NOT updated → retry next run
    - Handler exception → re-raised to prevent offset update → idempotent retry

    Returns:
        None. Side effects: Redis state changes, PostgreSQL audit log, Telegram API calls.
    """
    # Early exit if allowlist is empty (feature disabled)
    # This allows the task to run without processing callbacks while still
    # consuming updates to prevent Telegram message queue buildup
    if not config.TELEGRAM_ALLOWED_USER_IDS:
        log.debug("poll_telegram_updates: TELEGRAM_ALLOWED_USER_IDS empty, skipping")
        return

    # Initialize stores and notifier
    redis = RedisStore()
    notifier = TelegramNotifier()
    pg = PostgreSQLStore()

    # Get current offset from Redis (defaults to 0 on first run)
    offset = redis.get_offset() or 0

    try:
        # Use sync httpx client (Celery tasks are synchronous)
        # timeout=10s prevents hanging on slow connections
        with httpx.Client(timeout=10.0) as client:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
            # timeout=1 enables long-polling: Telegram holds connection up to 1s
            # waiting for new updates. This reduces latency without busy-polling.
            response = client.get(url, params={"offset": offset, "timeout": 1})
            response.raise_for_status()
            data = response.json()

        # Telegram API response format: {"ok": bool, "result": [...]}
        if not data.get("ok"):
            log.error("Telegram API error: %s", data)
            return

        updates = data.get("result", [])
        if not updates:
            # No new updates since last offset — normal idle state
            return

        # Process each update sequentially
        for update in updates:
            # Only process callback_query (inline button taps)
            # Regular messages are ignored — we only care about approve/reject actions
            callback_query = update.get("callback_query")
            if not callback_query:
                continue

            # Extract callback metadata
            callback_id = callback_query.get("id")  # Unique callback ID for answerCallbackQuery
            chat_id = callback_query.get("from", {}).get("id")  # User's Telegram ID
            user_id = str(chat_id) if chat_id else None
            message = callback_query.get("message", {})  # Original message with keyboard
            message_id = message.get("message_id")  # Message ID to edit (remove keyboard after)
            data = callback_query.get("data", "")  # callback_data: "approve:<token>" or "reject:<token>"

            # Skip non-approval callbacks (e.g., other bot keyboards)
            if not data.startswith(("approve:", "reject:")):
                continue

            # SECURITY: Verify user is in allowlist
            # TELEGRAM_ALLOWED_USER_IDS must be set in environment (comma-separated)
            # If user not authorized: silent rejection (no response to avoid spam)
            if user_id not in config.TELEGRAM_ALLOWED_USER_IDS:
                log.warning("Unauthorized user tap: user_id=%s", user_id)
                continue

            # Parse action and token from callback_data
            # Format: "approve:abc12345" or "reject:xyz78901"
            action, token = data.split(":", 1)

            # SECURITY: Fetch current suggestion and validate token
            # Token = SHA256(computed_at)[:8] — prevents replay attacks
            suggestion = redis.get_weight_suggestion()
            if suggestion is None:
                # Suggestion already processed (approved/rejected) or expired (7d TTL)
                # This handles double-tap: first tap deletes, second tap finds None
                _answer_callback(client, callback_id, "Già processata")
                if message_id:
                    _remove_keyboard(client, chat_id, message_id)
                continue

            # Recompute expected token from suggestion timestamp
            computed_at = suggestion.get("computed_at", "")
            expected_token = _compute_suggestion_token(computed_at)
            if token != expected_token:
                # Token mismatch: suggestion was replaced by newer run
                # User is tapping an old message after new weights were computed
                _answer_callback(client, callback_id, "Già processata")
                if message_id:
                    _remove_keyboard(client, chat_id, message_id)
                continue

            # Route to handler based on action
            if action == "approve":
                _handle_approve(redis, pg, client, callback_id, suggestion, message_id, chat_id, notifier)
            elif action == "reject":
                _handle_reject(redis, pg, client, callback_id, suggestion, message_id, chat_id, notifier)

        # Update offset to last processed update_id + 1
        # This tells Telegram to only return NEW updates on next poll
        # On error (exception below), offset is NOT updated → same updates retried
        if updates:
            last_update_id = max(u.get("update_id", 0) for u in updates)
            redis.set_offset(last_update_id + 1)

    except httpx.HTTPError as e:
        # Network error talking to Telegram API
        # Don't update offset — retry same updates on next run (5s later)
        log.error("Telegram polling HTTP error: %s", e)
    except Exception as e:
        # Unexpected error (Redis down, PG down, logic bug)
        # Don't update offset — retry same updates on next run
        # This ensures no callback is lost due to transient failures
        log.exception("poll_telegram_updates error: %s", e)


def _answer_callback(client: httpx.Client, callback_id: str, text: str) -> None:
    """
    Send answerCallbackQuery to Telegram to show toast notification on button tap.

    This is required by Telegram: every callback_query must be acknowledged
    within ~30 seconds, otherwise the user sees a loading spinner.

    Args:
        client: Synchronous httpx.Client (already authenticated via bot_token)
        callback_id: Unique ID from callback_query["id"]
        text: Toast message to show. Common values:
            - "✅ Pesi applicati" (approve success)
            - "❌ Suggestion rifiutata" (reject success)
            - "Già processata" (stale token / double-tap)
            - "" (silent rejection for unauthorized users)
        show_alert: True shows modal alert, False shows toast (we use True)
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        response = client.post(url, json={"callback_query_id": callback_id, "text": text, "show_alert": True})
        response.raise_for_status()
    except httpx.HTTPError as e:
        # Non-critical: user already tapped, action may have succeeded
        # Log but don't raise — we don't want to retry the whole handler
        log.warning("Failed to answer callback: %s", e)


def _remove_keyboard(client: httpx.Client, chat_id: int, message_id: int) -> None:
    """
    Remove inline keyboard from message after processing (one-time action).

    This prevents:
    - Confusion (buttons still clickable after action completed)
    - Spam (user tapping multiple times)
    - Security (unauthorized users can't tap after original user did)

    Implementation note: TelegramNotifier.edit_message_reply_markup is async,
    so we wrap it with asyncio.run() for use in this sync Celery task.

    Args:
        client: Synchronous httpx.Client (not used directly, passed to notifier)
        chat_id: Telegram chat ID (channel or private)
        message_id: Message ID containing the keyboard to remove
    """
    notifier = TelegramNotifier()
    # Run async method in sync context (Celery task is synchronous)
    import asyncio
    asyncio.run(notifier.edit_message_reply_markup(str(chat_id), message_id, keyboard=None))


def _handle_approve(
    redis: RedisStore,
    pg: PostgreSQLStore,
    client: httpx.Client,
    callback_id: str,
    suggestion: dict,
    message_id: int | None,
    chat_id: int | None,
    notifier: TelegramNotifier,
) -> None:
    """
    Handle approve button tap: apply weights, log audit, remove keyboard.

    This is the critical path for the Telegram approval flow. When a user
    taps "✅ Approva", this function:

    1. Extracts suggested_weights from the Redis suggestion
    2. Writes weights to Redis via set_ensemble_weights(source="telegram")
    3. Deletes the suggestion (prevents double-approve)
    4. Logs the event to PostgreSQL weight_update_log table
    5. Sends "✅ Pesi applicati" toast to user
    6. Removes the keyboard from the message (one-time action)

    Error handling:
    - Any exception is re-raised to prevent offset update
    - This ensures the callback is retried on next run (5s) if PG/Redis fails
    - Idempotency: if weights already applied, suggestion is gone → "Già processata"

    Args:
        redis: RedisStore instance for reading suggestion and writing weights
        pg: PostgreSQLStore instance for audit logging
        client: Synchronous httpx.Client for Telegram API calls
        callback_id: Callback ID for answerCallbackQuery
        suggestion: Dict from Redis with suggested_weights, computed_at, etc.
        message_id: Message ID to edit (remove keyboard after processing)
        chat_id: Chat ID for edit_message_reply_markup
        notifier: TelegramNotifier for async edit_message_reply_markup call
    """
    try:
        weights = suggestion.get("suggested_weights", {})
        computed_at = suggestion.get("computed_at", "")

        # Apply weights to Redis (source="telegram" for audit trail)
        redis.set_ensemble_weights(weights, source="telegram")

        # Delete suggestion immediately to prevent double-approve
        # This is idempotent: if already deleted, no-op
        redis.delete_weight_suggestion()

        # Log to PostgreSQL for audit trail
        # Fields: source, applied_weights, previous_weights, suggestion_data
        pg.log_weight_update(
            source="telegram",
            applied_weights=weights,
            previous_weights=suggestion.get("current_weights", {}),
            suggestion_data=suggestion,
        )

        # Acknowledge the tap with success toast
        _answer_callback(client, callback_id, "✅ Pesi applicati")

        # Remove keyboard to prevent further taps
        if message_id and chat_id:
            _remove_keyboard(client, chat_id, message_id)

        log.info("Telegram approval: weights applied from user tap")

    except Exception as e:
        # Critical error: weights may not have been applied
        # Re-raise to prevent offset update → retry on next run
        log.exception("Approve handler error: %s", e)
        _answer_callback(client, callback_id, "Errore durante l'approvazione")
        raise


def _handle_reject(
    redis: RedisStore,
    pg: PostgreSQLStore,
    client: httpx.Client,
    callback_id: str,
    suggestion: dict,
    message_id: int | None,
    chat_id: int | None,
    notifier: TelegramNotifier,
) -> None:
    """
    Handle reject button tap: delete suggestion, log audit, remove keyboard.

    When a user taps "❌ Rifiuta", this function:

    1. Deletes the suggestion from Redis (no weights applied)
    2. Logs the rejection to PostgreSQL with:
       - source="rejected_via_telegram"
       - applied_weights={} (empty dict indicates no change)
       - previous_weights (what was active before)
       - suggestion_data (full context for audit)
    3. Sends "❌ Suggestion rifiutata" toast to user
    4. Removes the keyboard from the message

    Error handling:
    - Any exception is re-raised to prevent offset update
    - Retry on next run (5s) if PG/Redis fails
    - Idempotency: if already rejected, suggestion gone → "Già processata"

    Args:
        redis: RedisStore instance for deleting suggestion
        pg: PostgreSQLStore instance for audit logging
        client: Synchronous httpx.Client for Telegram API calls
        callback_id: Callback ID for answerCallbackQuery
        suggestion: Dict from Redis with suggested_weights, computed_at, etc.
        message_id: Message ID to edit (remove keyboard after processing)
        chat_id: Chat ID for edit_message_reply_markup
        notifier: TelegramNotifier for async edit_message_reply_markup call
    """
    try:
        # Delete suggestion without applying weights
        # User explicitly rejected the proposed changes
        redis.delete_weight_suggestion()

        # Log rejection to PostgreSQL audit trail
        # applied_weights={} signals "no change applied"
        pg.log_weight_update(
            source="rejected_via_telegram",
            applied_weights={},
            previous_weights=suggestion.get("current_weights", {}),
            suggestion_data=suggestion,
        )

        # Acknowledge the tap with rejection toast
        _answer_callback(client, callback_id, "❌ Suggestion rifiutata")

        # Remove keyboard to prevent further taps
        if message_id and chat_id:
            _remove_keyboard(client, chat_id, message_id)

        log.info("Telegram rejection: suggestion discarded")

    except Exception as e:
        # Critical error: rejection may not have been logged
        # Re-raise to prevent offset update → retry on next run
        log.exception("Reject handler error: %s", e)
        _answer_callback(client, callback_id, "Errore durante il rifiuto")
        raise
