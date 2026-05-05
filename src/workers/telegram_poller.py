"""Telegram poller Celery task — processes inline keyboard callbacks."""

import hashlib
import logging
from typing import Literal

import httpx

from src.config import config
from src.models.regime import RegimeState  # type: ignore[attr-defined]
from src.notifications.telegram import TelegramNotifier
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)


def _compute_suggestion_token(computed_at: str) -> str:
    """Compute SHA256 token from suggestion computed_at timestamp."""
    return hashlib.sha256(computed_at.encode()).hexdigest()[:8]


@app.task(name="src.workers.telegram_poller.poll_telegram_updates")
def poll_telegram_updates() -> None:
    """
    Poll Telegram /getUpdates every 5s, process callback_query for approve/reject.

    Flow:
    1. GET /getUpdates with offset from Redis (telegram:poller:offset)
    2. Filter callback_query messages
    3. Verify user_id in TELEGRAM_ALLOWED_USER_IDS
    4. Verify token matches current suggestion
    5. Execute action (approve/reject) or reject stale token
    6. Update offset in Redis
    """
    if not config.TELEGRAM_ALLOWED_USER_IDS:
        log.debug("poll_telegram_updates: TELEGRAM_ALLOWED_USER_IDS empty, skipping")
        return

    redis = RedisStore()
    notifier = TelegramNotifier()
    pg = PostgreSQLStore()

    # Get current offset from Redis
    offset = redis.get_offset() or 0

    try:
        with httpx.Client(timeout=10.0) as client:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
            response = client.get(url, params={"offset": offset, "timeout": 1})
            response.raise_for_status()
            data = response.json()

        if not data.get("ok"):
            log.error("Telegram API error: %s", data)
            return

        updates = data.get("result", [])
        if not updates:
            return

        # Process each update
        for update in updates:
            callback_query = update.get("callback_query")
            if not callback_query:
                continue

            callback_id = callback_query.get("id")
            chat_id = callback_query.get("from", {}).get("id")
            user_id = str(chat_id) if chat_id else None
            message = callback_query.get("message", {})
            message_id = message.get("message_id")
            data = callback_query.get("data", "")

            if not data.startswith(("approve:", "reject:")):
                continue

            # Verify user is allowed
            if user_id not in config.TELEGRAM_ALLOWED_USER_IDS:
                log.warning("Unauthorized user tap: user_id=%s", user_id)
                # Silent rejection - no answerCallbackQuery to avoid spam
                continue

            # Parse action and token
            action, token = data.split(":", 1)

            # Get current suggestion from Redis
            suggestion = redis.get_weight_suggestion()
            if suggestion is None:
                # Suggestion already processed or expired
                _answer_callback(client, callback_id, "Già processata")
                if message_id:
                    _remove_keyboard(client, chat_id, message_id)
                continue

            # Verify token
            computed_at = suggestion.get("computed_at", "")
            expected_token = _compute_suggestion_token(computed_at)
            if token != expected_token:
                # Stale token (suggestion was replaced)
                _answer_callback(client, callback_id, "Già processata")
                if message_id:
                    _remove_keyboard(client, chat_id, message_id)
                continue

            # Execute action
            if action == "approve":
                _handle_approve(redis, pg, client, callback_id, suggestion, message_id, chat_id, notifier)
            elif action == "reject":
                _handle_reject(redis, pg, client, callback_id, suggestion, message_id, chat_id, notifier)

        # Update offset to last update_id + 1
        if updates:
            last_update_id = max(u.get("update_id", 0) for u in updates)
            redis.set_offset(last_update_id + 1)

    except httpx.HTTPError as e:
        log.error("Telegram polling HTTP error: %s", e)
        # Don't update offset on error - retry next run
    except Exception as e:
        log.exception("poll_telegram_updates error: %s", e)
        # Don't update offset on error - retry next run


def _answer_callback(client: httpx.Client, callback_id: str, text: str) -> None:
    """Send answerCallbackQuery to Telegram."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        response = client.post(url, json={"callback_query_id": callback_id, "text": text, "show_alert": True})
        response.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("Failed to answer callback: %s", e)


def _remove_keyboard(client: httpx.Client, chat_id: int, message_id: int) -> None:
    """Remove inline keyboard from message."""
    notifier = TelegramNotifier()
    # Run async method in sync context
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
    """Handle approve button tap."""
    try:
        weights = suggestion.get("suggested_weights", {})
        computed_at = suggestion.get("computed_at", "")

        # Apply weights
        redis.set_ensemble_weights(weights, source="telegram")
        redis.delete_weight_suggestion()

        # Log to PostgreSQL
        pg.log_weight_update(
            source="telegram",
            applied_weights=weights,
            previous_weights=suggestion.get("current_weights", {}),
            suggestion_data=suggestion,
        )

        _answer_callback(client, callback_id, "✅ Pesi applicati")
        if message_id and chat_id:
            _remove_keyboard(client, chat_id, message_id)

        log.info("Telegram approval: weights applied from user tap")

    except Exception as e:
        log.exception("Approve handler error: %s", e)
        _answer_callback(client, callback_id, "Errore durante l'approvazione")
        raise  # Re-raise to prevent offset update


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
    """Handle reject button tap."""
    try:
        # Delete suggestion without applying
        redis.delete_weight_suggestion()

        # Log rejection
        pg.log_weight_update(
            source="rejected_via_telegram",
            applied_weights={},
            previous_weights=suggestion.get("current_weights", {}),
            suggestion_data=suggestion,
        )

        _answer_callback(client, callback_id, "❌ Suggestion rifiutata")
        if message_id and chat_id:
            _remove_keyboard(client, chat_id, message_id)

        log.info("Telegram rejection: suggestion discarded")

    except Exception as e:
        log.exception("Reject handler error: %s", e)
        _answer_callback(client, callback_id, "Errore durante il rifiuto")
        raise  # Re-raise to prevent offset update
