# Telegram Approval Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inline keyboard buttons (✅ Approva / ❌ Rifiuta) to the Telegram freeze notification so the operator can approve or reject weight suggestions without touching the API.

**Architecture:** A Celery beat task (`poll_telegram_updates`) polls `/getUpdates` every 5 seconds, extracts `callback_query` events, validates the user against an allowlist and the token against the current Redis suggestion, then applies or deletes the suggestion. The performance worker's freeze path is updated to send the message with the inline keyboard instead of a plain text hint.

**Tech Stack:** httpx (sync client in poller), Telegram Bot API (sendMessage + answerCallbackQuery + editMessageReplyMarkup), Celery beat, Redis, PostgreSQL (existing `weight_update_log` table).

---

## File Map

| File | Action |
|------|--------|
| `src/config.py` | Add `TELEGRAM_ALLOWED_USER_IDS: list[str]` |
| `src/store/redis_store.py` | Add `get_telegram_update_offset()`, `set_telegram_update_offset()`, `delete_weight_suggestion()` |
| `src/notifications/telegram.py` | Add `send_message_with_keyboard()`, `edit_message_reply_markup()`, `format_freeze_message_with_keyboard()` |
| `src/workers/telegram_poller.py` | Create — Celery task `poll_telegram_updates()` |
| `src/workers/performance.py` | Freeze path calls `send_message_with_keyboard()` instead of `send_alert()` |
| `src/workers/celery_app.py` | Add beat schedule entry every 5s |
| `tests/test_redis_store.py` | Add `TestTelegramOffset` + `TestDeleteWeightSuggestion` |
| `tests/notifications/test_telegram.py` | Add `TestSendMessageWithKeyboard` + `TestFormatFreezeMessageWithKeyboard` |
| `tests/workers/test_telegram_poller.py` | Create — 5 scenarios |
| `tests/workers/test_performance_worker.py` | Update freeze tests to expect `send_message_with_keyboard` |

---

## Task 1: Config — TELEGRAM_ALLOWED_USER_IDS

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py` (create new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
"""Tests for Config fields."""

import os
from unittest.mock import patch

import pytest


class TestTelegramAllowedUserIds:
    def test_parses_comma_separated_ids(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
            TELEGRAM_ALLOWED_USER_IDS=["123", "456"],
        )
        assert cfg.TELEGRAM_ALLOWED_USER_IDS == ["123", "456"]

    def test_defaults_to_empty_list(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        assert cfg.TELEGRAM_ALLOWED_USER_IDS == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: `FAILED` — `Config` has no field `TELEGRAM_ALLOWED_USER_IDS`.

- [ ] **Step 3: Add the field to `src/config.py`**

Open `src/config.py`. After the `TELEGRAM_CHAT_ID` field (around line 65), add:

```python
    TELEGRAM_ALLOWED_USER_IDS: list[str] = Field(
        default_factory=lambda: [
            uid.strip()
            for uid in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
            if uid.strip()
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: `PASSED` (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add TELEGRAM_ALLOWED_USER_IDS config field"
```

---

## Task 2: Redis Store — offset and delete methods

**Files:**
- Modify: `src/store/redis_store.py`
- Test: `tests/test_redis_store.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_redis_store.py`:

```python
class TestTelegramOffset:
    """Tests for telegram update offset methods."""

    def test_get_returns_zero_when_not_set(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        store = RedisStore(redis_client=mock_redis)
        assert store.get_telegram_update_offset() == 0

    def test_get_returns_stored_value(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"42"
        store = RedisStore(redis_client=mock_redis)
        assert store.get_telegram_update_offset() == 42

    def test_set_stores_as_string_without_ttl(self):
        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)
        store.set_telegram_update_offset(100)
        mock_redis.set.assert_called_once_with("telegram:update_offset", "100")


class TestDeleteWeightSuggestion:
    """Tests for delete_weight_suggestion."""

    def test_returns_true_when_key_existed(self):
        mock_redis = MagicMock()
        mock_redis.delete.return_value = 1
        store = RedisStore(redis_client=mock_redis)
        assert store.delete_weight_suggestion() is True
        mock_redis.delete.assert_called_once_with(
            "ensemble:weights:suggestion",
            "ensemble:weights:suggestion:snapshot",
        )

    def test_returns_false_when_key_absent(self):
        mock_redis = MagicMock()
        mock_redis.delete.return_value = 0
        store = RedisStore(redis_client=mock_redis)
        assert store.delete_weight_suggestion() is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_redis_store.py::TestTelegramOffset tests/test_redis_store.py::TestDeleteWeightSuggestion -v
```

Expected: `FAILED` — methods do not exist yet.

- [ ] **Step 3: Add the three methods to `src/store/redis_store.py`**

At the end of the `# REGIME DETECTION` section (after `set_qc_sizing_multiplier`), add a new section:

```python
    # =========================================================================
    # TELEGRAM POLLER
    # =========================================================================

    def get_telegram_update_offset(self) -> int:
        """Read the Telegram /getUpdates offset from Redis. Returns 0 if not set."""
        raw = self._r.get("telegram:update_offset")
        if raw is None:
            return 0
        try:
            return int(raw)
        except (ValueError, TypeError):
            return 0

    def set_telegram_update_offset(self, offset: int) -> None:
        """Persist the Telegram update offset. No TTL — must survive restarts."""
        self._r.set("telegram:update_offset", str(offset))

    def delete_weight_suggestion(self) -> bool:
        """Delete both suggestion keys. Returns True if at least one key existed."""
        count = self._r.delete(
            "ensemble:weights:suggestion",
            "ensemble:weights:suggestion:snapshot",
        )
        return count > 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_redis_store.py::TestTelegramOffset tests/test_redis_store.py::TestDeleteWeightSuggestion -v
```

Expected: `PASSED` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/store/redis_store.py tests/test_redis_store.py
git commit -m "feat: add telegram offset and delete_weight_suggestion to RedisStore"
```

---

## Task 3: TelegramNotifier — keyboard methods and formatter

**Files:**
- Modify: `src/notifications/telegram.py`
- Test: `tests/notifications/test_telegram.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/notifications/test_telegram.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.notifications.telegram import (
    TelegramNotifier,
    format_freeze_message_with_keyboard,
)


class TestSendMessageWithKeyboard:
    """Tests for TelegramNotifier.send_message_with_keyboard."""

    @pytest.mark.asyncio
    async def test_returns_message_id_on_success(self):
        notifier = TelegramNotifier(bot_token="TOKEN", chat_id="CHAT")
        keyboard = [[{"text": "✅ Approva", "callback_data": "approve:abc123"}]]

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"message_id": 42}}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await notifier.send_message_with_keyboard("hello", keyboard)

        assert result == 42

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self):
        notifier = TelegramNotifier(bot_token="", chat_id="")
        result = await notifier.send_message_with_keyboard("msg", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        notifier = TelegramNotifier(bot_token="TOKEN", chat_id="CHAT")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await notifier.send_message_with_keyboard("msg", [])

        assert result is None


class TestFormatFreezeMessageWithKeyboard:
    """Tests for format_freeze_message_with_keyboard."""

    def test_returns_text_without_api_hint(self):
        text, _ = format_freeze_message_with_keyboard(
            suggested_weights={"opus": 0.5, "qwen3.5:cloud": 0.5},
            current_weights={"opus": 0.34, "qwen3.5:cloud": 0.33},
            freeze_reason="VIX = 35.0 >= 30.0",
            suggestion_token="abc12345",
        )
        assert "VIX" in text
        assert "POST /api/weights/approve" not in text

    def test_keyboard_contains_approve_and_reject(self):
        _, keyboard = format_freeze_message_with_keyboard(
            suggested_weights={"opus": 1.0},
            current_weights={"opus": 1.0},
            freeze_reason="test",
            suggestion_token="tok00001",
        )
        assert keyboard == [[
            {"text": "✅ Approva", "callback_data": "approve:tok00001"},
            {"text": "❌ Rifiuta", "callback_data": "reject:tok00001"},
        ]]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/notifications/test_telegram.py::TestSendMessageWithKeyboard tests/notifications/test_telegram.py::TestFormatFreezeMessageWithKeyboard -v
```

Expected: `FAILED` — `send_message_with_keyboard` and `format_freeze_message_with_keyboard` do not exist.

- [ ] **Step 3: Add methods to `src/notifications/telegram.py`**

Inside the `TelegramNotifier` class, after `send_alert`, add:

```python
    async def send_message_with_keyboard(
        self,
        message: str,
        keyboard: list[list[dict]],
        parse_mode: str = "HTML",
    ) -> int | None:
        """Send message with InlineKeyboardMarkup. Returns message_id or None on failure."""
        if not self._enabled:
            return None

        full_message = f"⚠️ <b>[LLM Trading]</b>\n\n{message}"
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": full_message,
            "parse_mode": parse_mode,
            "reply_markup": {"inline_keyboard": keyboard},
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()["result"]["message_id"]
        except Exception as e:
            print(f"TelegramNotifier: Failed to send keyboard message: {e}")
            return None

    async def edit_message_reply_markup(
        self,
        chat_id: str | int,
        message_id: int,
        keyboard: list[list[dict]] | None = None,
    ) -> bool:
        """Edit reply markup of an existing message. Pass keyboard=None to remove buttons."""
        if not self._enabled:
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/editMessageReplyMarkup"
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": keyboard} if keyboard is not None else {},
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"TelegramNotifier: Failed to edit message reply markup: {e}")
            return False
```

At module level (after `format_freeze_message`), add:

```python
def format_freeze_message_with_keyboard(
    suggested_weights: dict[str, float],
    current_weights: dict[str, float],
    freeze_reason: str,
    suggestion_token: str,
) -> tuple[str, list[list[dict]]]:
    """Format freeze message text and inline keyboard. Strips the manual API hint."""
    base = format_freeze_message(suggested_weights, current_weights, freeze_reason)
    text = "\n".join(
        line for line in base.splitlines() if "POST /api/weights/approve" not in line
    ).rstrip()
    keyboard = [[
        {"text": "✅ Approva", "callback_data": f"approve:{suggestion_token}"},
        {"text": "❌ Rifiuta", "callback_data": f"reject:{suggestion_token}"},
    ]]
    return text, keyboard
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/notifications/test_telegram.py::TestSendMessageWithKeyboard tests/notifications/test_telegram.py::TestFormatFreezeMessageWithKeyboard -v
```

Expected: `PASSED` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/notifications/telegram.py tests/notifications/test_telegram.py
git commit -m "feat: add send_message_with_keyboard and format_freeze_message_with_keyboard"
```

---

## Task 4: Telegram Poller Worker

**Files:**
- Create: `src/workers/telegram_poller.py`
- Create: `tests/workers/test_telegram_poller.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/workers/__init__.py` if it doesn't exist (it already does), then create `tests/workers/test_telegram_poller.py`:

```python
"""Tests for Telegram polling worker."""

import hashlib
from unittest.mock import MagicMock, call, patch

import pytest

from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore


def _make_suggestion(computed_at: str = "2026-05-05T07:00:00+00:00") -> dict:
    return {
        "suggested_weights": {"opus": 0.5, "qwen3.5:cloud": 0.5},
        "computed_at": computed_at,
        "freeze_reason": "VIX = 35.0 >= 30.0",
        "purified_icir": {"opus": 0.3, "qwen3.5:cloud": 0.2},
    }


def _valid_token(computed_at: str = "2026-05-05T07:00:00+00:00") -> str:
    return hashlib.sha256(computed_at.encode()).hexdigest()[:8]


def _make_callback_update(
    update_id: int = 1,
    user_id: int = 123,
    callback_data: str = "approve:abc12345",
    message_id: int = 42,
    chat_id: int = -100,
) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cq1",
            "from": {"id": user_id},
            "data": callback_data,
            "message": {"message_id": message_id, "chat": {"id": chat_id}},
        },
    }


def _make_http_client(updates: list) -> MagicMock:
    """Return a mock httpx.Client context manager returning given updates."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": updates}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp
    mock_client.post.return_value = MagicMock()
    return mock_client


class TestPollTelegramUpdates:
    """Tests for poll_telegram_updates Celery task."""

    COMPUTED_AT = "2026-05-05T07:00:00+00:00"

    def _run(self, updates, suggestion, allowed_ids=("123",)):
        redis = MagicMock(spec=RedisStore)
        redis.get_telegram_update_offset.return_value = 0
        redis.get_weight_suggestion.return_value = suggestion

        pg = MagicMock(spec=PostgreSQLStore)
        pg.log_weight_update.return_value = 1

        mock_client = _make_http_client(updates)

        with patch("src.workers.telegram_poller.RedisStore", return_value=redis), \
             patch("src.workers.telegram_poller.PostgreSQLStore", return_value=pg), \
             patch("src.workers.telegram_poller.config") as mock_cfg, \
             patch("httpx.Client", return_value=mock_client):
            mock_cfg.TELEGRAM_BOT_TOKEN = "TOKEN"
            mock_cfg.TELEGRAM_ALLOWED_USER_IDS = list(allowed_ids)
            from src.workers.telegram_poller import poll_telegram_updates
            poll_telegram_updates()

        return redis, pg, mock_client

    def test_approve_applies_weights_and_acks(self):
        """Approve callback → weights written to Redis, logged to PG, ack sent."""
        token = _valid_token(self.COMPUTED_AT)
        suggestion = _make_suggestion(self.COMPUTED_AT)
        update = _make_callback_update(callback_data=f"approve:{token}")

        redis, pg, client = self._run([update], suggestion)

        redis.set_ensemble_weights.assert_called_once_with(
            {"opus": 0.5, "qwen3.5:cloud": 0.5}, source="telegram"
        )
        redis.delete_weight_suggestion.assert_called_once()
        pg.log_weight_update.assert_called_once()
        assert pg.log_weight_update.call_args.kwargs["source"] == "telegram"
        assert client.post.call_count == 2  # answerCallbackQuery + editMessageReplyMarkup
        redis.set_telegram_update_offset.assert_called_once_with(2)

    def test_reject_deletes_suggestion_and_logs(self):
        """Reject callback → suggestion deleted, logged with source='rejected_via_telegram'."""
        token = _valid_token(self.COMPUTED_AT)
        suggestion = _make_suggestion(self.COMPUTED_AT)
        update = _make_callback_update(callback_data=f"reject:{token}")

        redis, pg, client = self._run([update], suggestion)

        redis.delete_weight_suggestion.assert_called_once()
        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "rejected_via_telegram"
        assert pg.log_weight_update.call_args.kwargs["applied_weights"] == {}
        assert client.post.call_count == 2  # answerCallbackQuery + editMessageReplyMarkup

    def test_stale_token_is_silently_ignored(self):
        """Wrong token → no Redis/PG writes, only answerCallbackQuery('Già processata')."""
        suggestion = _make_suggestion(self.COMPUTED_AT)
        update = _make_callback_update(callback_data="approve:00000000")  # wrong token

        redis, pg, client = self._run([update], suggestion)

        redis.set_ensemble_weights.assert_not_called()
        pg.log_weight_update.assert_not_called()
        assert client.post.call_count == 1  # only answerCallbackQuery
        post_call_json = client.post.call_args.kwargs.get("json", {})
        assert "Già processata" in post_call_json.get("text", "")

    def test_unauthorized_user_is_silently_ignored(self):
        """User not in allowlist → no action taken."""
        token = _valid_token(self.COMPUTED_AT)
        suggestion = _make_suggestion(self.COMPUTED_AT)
        update = _make_callback_update(callback_data=f"approve:{token}", user_id=999)

        redis, pg, client = self._run([update], suggestion, allowed_ids=("123",))

        redis.set_ensemble_weights.assert_not_called()
        pg.log_weight_update.assert_not_called()

    def test_no_callback_queries_still_updates_offset(self):
        """Plain message update (no callback_query) → only offset updated."""
        update = {"update_id": 10, "message": {"text": "hello"}}

        redis, pg, client = self._run([update], suggestion=None)

        redis.set_ensemble_weights.assert_not_called()
        pg.log_weight_update.assert_not_called()
        redis.set_telegram_update_offset.assert_called_once_with(11)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/workers/test_telegram_poller.py -v
```

Expected: `ERROR` — `src.workers.telegram_poller` module does not exist.

- [ ] **Step 3: Create `src/workers/telegram_poller.py`**

```python
"""Telegram polling worker — processes approve/reject callback queries."""

import hashlib
import logging

import httpx

from src.config import config
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)


def _compute_token(computed_at: str) -> str:
    return hashlib.sha256(computed_at.encode()).hexdigest()[:8]


def _answer_callback(client: httpx.Client, callback_query_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        client.post(url, json={"callback_query_id": callback_query_id, "text": text}, timeout=5.0)
    except Exception as e:
        log.warning("answerCallbackQuery failed: %s", e)


def _edit_reply_markup(client: httpx.Client, chat_id: int | str, message_id: int) -> None:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup"
    try:
        client.post(
            url,
            json={"chat_id": chat_id, "message_id": message_id, "reply_markup": {}},
            timeout=5.0,
        )
    except Exception as e:
        log.warning("editMessageReplyMarkup failed: %s", e)


def _process_callback(
    client: httpx.Client,
    redis: RedisStore,
    pg: PostgreSQLStore,
    callback_query_id: str,
    user_id: str,
    callback_data: str,
    chat_id: int | str,
    message_id: int,
) -> None:
    if user_id not in config.TELEGRAM_ALLOWED_USER_IDS:
        _answer_callback(client, callback_query_id, "")
        return

    if ":" not in callback_data:
        _answer_callback(client, callback_query_id, "")
        return

    action, token = callback_data.split(":", 1)
    if action not in ("approve", "reject"):
        _answer_callback(client, callback_query_id, "")
        return

    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        _answer_callback(client, callback_query_id, "Già processata")
        return

    if token != _compute_token(suggestion["computed_at"]):
        _answer_callback(client, callback_query_id, "Già processata")
        return

    if action == "approve":
        weights = suggestion["suggested_weights"]
        redis.set_ensemble_weights(weights, source="telegram")
        redis.delete_weight_suggestion()
        pg.log_weight_update(
            source="telegram",
            applied_weights=weights,
            suggested_weights=weights,
            purified_icir=suggestion.get("purified_icir"),
            freeze_reason=suggestion.get("freeze_reason"),
            note=f"Approved via Telegram by user {user_id}",
            approved_by=user_id,
        )
        _answer_callback(client, callback_query_id, "✅ Pesi applicati")
    else:
        redis.delete_weight_suggestion()
        pg.log_weight_update(
            source="rejected_via_telegram",
            applied_weights={},
            suggested_weights=suggestion["suggested_weights"],
            purified_icir=suggestion.get("purified_icir"),
            freeze_reason=suggestion.get("freeze_reason"),
            note=f"Rejected via Telegram by user {user_id}",
            approved_by=user_id,
        )
        _answer_callback(client, callback_query_id, "❌ Suggestion rifiutata")

    _edit_reply_markup(client, chat_id, message_id)


@app.task(name="src.workers.telegram_poller.poll_telegram_updates")
def poll_telegram_updates() -> None:
    """Poll Telegram /getUpdates and process approve/reject callback queries."""
    if not config.TELEGRAM_BOT_TOKEN:
        return

    redis = RedisStore()
    offset = redis.get_telegram_update_offset()

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"

    with httpx.Client(timeout=10.0) as client:
        try:
            response = client.get(url, params={"offset": offset, "timeout": 0})
            response.raise_for_status()
            updates = response.json().get("result", [])
        except Exception as e:
            log.error("poll_telegram_updates: getUpdates failed: %s", e)
            return

        if not updates:
            return

        pg = PostgreSQLStore()
        for update in updates:
            cq = update.get("callback_query")
            if cq:
                _process_callback(
                    client=client,
                    redis=redis,
                    pg=pg,
                    callback_query_id=cq["id"],
                    user_id=str(cq["from"]["id"]),
                    callback_data=cq.get("data", ""),
                    chat_id=cq["message"]["chat"]["id"],
                    message_id=cq["message"]["message_id"],
                )

        redis.set_telegram_update_offset(updates[-1]["update_id"] + 1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/workers/test_telegram_poller.py -v
```

Expected: `PASSED` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workers/telegram_poller.py tests/workers/test_telegram_poller.py
git commit -m "feat: add telegram_poller Celery task with approve/reject callback handling"
```

---

## Task 5: Performance Worker — freeze path uses keyboard

**Files:**
- Modify: `src/workers/performance.py`
- Modify: `tests/workers/test_performance_worker.py`

- [ ] **Step 1: Write the failing test**

In `tests/workers/test_performance_worker.py`, inside `TestCheckAndApplyWeights`, add:

```python
    def test_freeze_sends_keyboard_message_not_plain_alert(self):
        """Freeze path sends send_message_with_keyboard, not send_alert."""
        redis = self._make_redis(vix_cached=38.5)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        notifier.send_message_with_keyboard = AsyncMock(return_value=42)
        cfg = self._make_config(vix_threshold=30.0)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        notifier.send_message_with_keyboard.assert_called_once()
        notifier.send_alert.assert_not_called()
        # Keyboard must contain approve and reject buttons
        call_args = notifier.send_message_with_keyboard.call_args
        keyboard = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("keyboard")
        assert len(keyboard) == 1
        assert keyboard[0][0]["text"] == "✅ Approva"
        assert keyboard[0][1]["text"] == "❌ Rifiuta"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/workers/test_performance_worker.py::TestCheckAndApplyWeights::test_freeze_sends_keyboard_message_not_plain_alert -v
```

Expected: `FAILED` — `send_message_with_keyboard` not called; `send_alert` is called instead.

- [ ] **Step 3: Update `src/workers/performance.py`**

At the top of the file, add `import hashlib` after the existing imports.

Update the import line for `format_freeze_message`:

```python
# Before:
from src.notifications.telegram import TelegramNotifier, format_auto_apply_message, format_freeze_message
# After:
from src.notifications.telegram import TelegramNotifier, format_auto_apply_message, format_freeze_message, format_freeze_message_with_keyboard
```

In `check_and_apply_weights()`, replace the freeze notification block (around line 732-733):

```python
# Before:
        msg = format_freeze_message(suggested_weights, current_weights, freeze_reason)
        asyncio.run(notifier.send_alert(msg, level="warning"))
# After:
        token = hashlib.sha256(suggestion["computed_at"].encode()).hexdigest()[:8]
        text, keyboard = format_freeze_message_with_keyboard(
            suggested_weights, current_weights, freeze_reason, token
        )
        asyncio.run(notifier.send_message_with_keyboard(text, keyboard))
```

- [ ] **Step 4: Update the existing freeze tests that assert on `send_alert`**

In `tests/workers/test_performance_worker.py`, `test_g2_vix_too_high_freezes` currently asserts `"⚠️" in notifier.send_alert.call_args[0][0]`. After the change, `send_alert` is no longer called in the freeze path. Update the test:

```python
    def test_g2_vix_too_high_freezes(self):
        """G2: VIX >= threshold → freeze, log source='freeze', Telegram keyboard ⚠️."""
        redis = self._make_redis(vix_cached=38.5)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        notifier.send_message_with_keyboard = AsyncMock(return_value=42)
        cfg = self._make_config(vix_threshold=30.0)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"
        assert "VIX" in pg.log_weight_update.call_args.kwargs["note"]
        notifier.send_message_with_keyboard.assert_called_once()
```

Also update `test_g2_fred_unavailable_freezes`, `test_g3_ic_variance_too_high_freezes`, `test_g4_weight_delta_too_large_freezes` by adding `notifier.send_message_with_keyboard = AsyncMock(return_value=42)` to each (the assertion on `send_alert` is absent in those tests, so they would pass either way, but the mock needs to exist to avoid `asyncio.run` failing on a non-coroutine):

In each of those three tests, after `notifier.send_alert = AsyncMock()`, add:
```python
        notifier.send_message_with_keyboard = AsyncMock(return_value=42)
```

- [ ] **Step 5: Run all performance worker tests**

```bash
pytest tests/workers/test_performance_worker.py -v
```

Expected: all `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add src/workers/performance.py tests/workers/test_performance_worker.py
git commit -m "feat: freeze notification uses Telegram inline keyboard"
```

---

## Task 6: Celery Beat Schedule

**Files:**
- Modify: `src/workers/celery_app.py`

No tests needed for a beat schedule entry — the task itself is tested in Task 4.

- [ ] **Step 1: Add the schedule entry to `src/workers/celery_app.py`**

In `app.conf.beat_schedule`, add after the `"regime-detector"` entry:

```python
    # Telegram approval poller every 5s — processes approve/reject callback_query
    "poll-telegram-updates": {
        "task": "src.workers.telegram_poller.poll_telegram_updates",
        "schedule": 5.0,
    },
```

- [ ] **Step 2: Verify the full test suite still passes**

```bash
pytest --tb=short -q
```

Expected: all tests pass, no regressions.

- [ ] **Step 3: Commit**

```bash
git add src/workers/celery_app.py
git commit -m "feat: register poll_telegram_updates in Celery beat (every 5s)"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| §2 Flusso: polling + callback processing | Task 4 |
| §3 Token anti-replay | Task 4 (`_compute_token`) |
| §4 Config `TELEGRAM_ALLOWED_USER_IDS` | Task 1 |
| §5 `send_message_with_keyboard`, `edit_message_reply_markup`, `format_freeze_message_with_keyboard` | Task 3 |
| §6 Redis `get/set_telegram_update_offset`, `delete_weight_suggestion` | Task 2 |
| §7 Celery task `poll_telegram_updates` | Task 4 |
| §7 Beat schedule 5s | Task 6 |
| §8 Performance worker freeze path | Task 5 |
| §9 All edge cases (stale token, double-tap, unauthorized, API down, empty allowlist) | Task 4 tests |
| §11 5 test scenarios | Task 4 |
| §12 `pg_store.py` unmodified | No pg_store task — reuses `log_weight_update` |

All spec sections covered. ✅
