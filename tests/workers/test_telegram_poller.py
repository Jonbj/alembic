"""Tests for poll_telegram_updates Celery task."""

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _compute_token(computed_at: str) -> str:
    """Helper to compute suggestion token."""
    import hashlib
    return hashlib.sha256(computed_at.encode()).hexdigest()[:8]


class TestTelegramPoller:
    """5 scenarios covering all consensus branches, validation, and edge cases."""

    @pytest.fixture
    def suggestion(self):
        """Sample weight suggestion."""
        computed_at = "2026-05-05T10:00:00Z"
        return {
            "suggested_weights": {"opus": 0.45, "qwen3.5:cloud": 0.55},
            "current_weights": {"opus": 0.34, "qwen3.5:cloud": 0.66},
            "computed_at": computed_at,
            "freeze_reason": "VIX too high",
        }

    @pytest.fixture
    def token(self, suggestion):
        """Compute token for suggestion."""
        return _compute_token(suggestion["computed_at"])

    def _run_poller(self, updates, redis, pg, notifier):
        """Run poll_telegram_updates with mocked dependencies."""
        with patch("src.workers.telegram_poller.httpx.Client") as mock_client, \
             patch("src.workers.telegram_poller.RedisStore", return_value=redis), \
             patch("src.workers.telegram_poller.PostgreSQLStore", return_value=pg), \
             patch("src.workers.telegram_poller.TelegramNotifier", return_value=notifier), \
             patch("src.workers.telegram_poller.config") as mock_config:
            mock_config.TELEGRAM_ALLOWED_USER_IDS = ["123456", "789012"]
            mock_config.TELEGRAM_BOT_TOKEN = "test-bot-token"

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True, "result": updates}
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            from src.workers.telegram_poller import poll_telegram_updates
            poll_telegram_updates()

    def test_callback_approve_valid(self, suggestion, token):
        """Valid approve callback → weights applied, suggestion deleted, log written."""
        redis = MagicMock()
        redis.get_offset.return_value = 100
        redis.get_weight_suggestion.return_value = suggestion

        pg = MagicMock()
        notifier = MagicMock()
        notifier.edit_message_reply_markup = AsyncMock(return_value=True)

        update = {
            "update_id": 101,
            "callback_query": {
                "id": "cb123",
                "from": {"id": 123456},
                "message": {"message_id": 42},
                "data": f"approve:{token}",
            },
        }

        self._run_poller([update], redis, pg, notifier)

        redis.set_ensemble_weights.assert_called_once()
        redis.delete_weight_suggestion.assert_called_once()
        pg.log_weight_update.assert_called_once()
        call_args = pg.log_weight_update.call_args
        assert call_args[1]["source"] == "telegram"
        assert call_args[1]["applied_weights"] == {"opus": 0.45, "qwen3.5:cloud": 0.55}

    def test_callback_reject_valid(self, suggestion, token):
        """Valid reject callback → suggestion deleted, log with empty weights."""
        redis = MagicMock()
        redis.get_offset.return_value = 100
        redis.get_weight_suggestion.return_value = suggestion

        pg = MagicMock()
        notifier = MagicMock()
        notifier.edit_message_reply_markup = AsyncMock(return_value=True)

        update = {
            "update_id": 101,
            "callback_query": {
                "id": "cb123",
                "from": {"id": 123456},
                "message": {"message_id": 42},
                "data": f"reject:{token}",
            },
        }

        self._run_poller([update], redis, pg, notifier)

        redis.delete_weight_suggestion.assert_called_once()
        pg.log_weight_update.assert_called_once()
        call_args = pg.log_weight_update.call_args
        assert call_args[1]["source"] == "rejected_via_telegram"
        assert call_args[1]["applied_weights"] == {}

    def test_token_stale_no_action(self, suggestion):
        """Stale token (suggestion changed) → no action, 'Già processata' response."""
        redis = MagicMock()
        redis.get_offset.return_value = 100
        # Suggestion in Redis has different computed_at → token mismatch
        stale_suggestion = suggestion.copy()
        stale_suggestion["computed_at"] = "2026-05-05T11:00:00Z"
        redis.get_weight_suggestion.return_value = stale_suggestion

        pg = MagicMock()
        notifier = MagicMock()
        notifier.edit_message_reply_markup = AsyncMock(return_value=True)

        old_token = _compute_token(suggestion["computed_at"])
        update = {
            "update_id": 101,
            "callback_query": {
                "id": "cb123",
                "from": {"id": 123456},
                "message": {"message_id": 42},
                "data": f"approve:{old_token}",
            },
        }

        with patch("src.workers.telegram_poller.httpx.Client") as mock_client, \
             patch("src.workers.telegram_poller.RedisStore", return_value=redis), \
             patch("src.workers.telegram_poller.PostgreSQLStore", return_value=pg), \
             patch("src.workers.telegram_poller.TelegramNotifier", return_value=notifier), \
             patch("src.workers.telegram_poller.config") as mock_config:
            mock_config.TELEGRAM_ALLOWED_USER_IDS = ["123456"]
            mock_config.TELEGRAM_BOT_TOKEN = "test-bot-token"

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True, "result": [update]}
            mock_http_client = mock_client.return_value.__enter__.return_value
            mock_http_client.get.return_value = mock_response
            mock_http_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            from src.workers.telegram_poller import poll_telegram_updates
            poll_telegram_updates()

        redis.set_ensemble_weights.assert_not_called()
        redis.delete_weight_suggestion.assert_not_called()
        pg.log_weight_update.assert_not_called()
        # Verify the user received "Già processata" via answerCallbackQuery
        post_calls = mock_http_client.post.call_args_list
        answer_calls = [c for c in post_calls if "answerCallbackQuery" in str(c)]
        assert len(answer_calls) == 1
        payload = answer_calls[0][1]["json"]
        assert payload["text"] == "Già processata"

    def test_double_tap_idempotent(self, suggestion, token):
        """Second tap after suggestion already processed → 'Già processata', no side effects."""
        redis = MagicMock()
        redis.get_offset.return_value = 100
        # Suggestion already gone (deleted by first tap)
        redis.get_weight_suggestion.return_value = None

        pg = MagicMock()
        notifier = MagicMock()
        notifier.edit_message_reply_markup = AsyncMock(return_value=True)

        update = {
            "update_id": 102,
            "callback_query": {
                "id": "cb456",
                "from": {"id": 123456},
                "message": {"message_id": 42},
                "data": f"approve:{token}",
            },
        }

        with patch("src.workers.telegram_poller.httpx.Client") as mock_client, \
             patch("src.workers.telegram_poller.RedisStore", return_value=redis), \
             patch("src.workers.telegram_poller.PostgreSQLStore", return_value=pg), \
             patch("src.workers.telegram_poller.TelegramNotifier", return_value=notifier), \
             patch("src.workers.telegram_poller.config") as mock_config:
            mock_config.TELEGRAM_ALLOWED_USER_IDS = ["123456"]
            mock_config.TELEGRAM_BOT_TOKEN = "test-bot-token"

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True, "result": [update]}
            mock_http_client = mock_client.return_value.__enter__.return_value
            mock_http_client.get.return_value = mock_response
            mock_http_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            from src.workers.telegram_poller import poll_telegram_updates
            poll_telegram_updates()

        # No state changes
        redis.set_ensemble_weights.assert_not_called()
        redis.delete_weight_suggestion.assert_not_called()
        pg.log_weight_update.assert_not_called()
        # User receives "Già processata" via answerCallbackQuery
        post_calls = mock_http_client.post.call_args_list
        answer_calls = [c for c in post_calls if "answerCallbackQuery" in str(c)]
        assert len(answer_calls) == 1
        payload = answer_calls[0][1]["json"]
        assert payload["text"] == "Già processata"

    def test_user_not_in_allowlist(self, suggestion, token):
        """User not in TELEGRAM_ALLOWED_USER_IDS → no action, silent rejection."""
        redis = MagicMock()
        redis.get_offset.return_value = 100
        redis.get_weight_suggestion.return_value = suggestion

        pg = MagicMock()
        notifier = MagicMock()

        update = {
            "update_id": 101,
            "callback_query": {
                "id": "cb123",
                "from": {"id": 999999},  # Not in allowlist
                "message": {"message_id": 42},
                "data": f"approve:{token}",
            },
        }

        self._run_poller([update], redis, pg, notifier)

        redis.set_ensemble_weights.assert_not_called()
        redis.delete_weight_suggestion.assert_not_called()
        pg.log_weight_update.assert_not_called()

    def test_no_callback_query_offset_updated(self):
        """No callback_query in updates → offset updated, no other action."""
        redis = MagicMock()
        redis.get_offset.return_value = 100

        pg = MagicMock()
        notifier = MagicMock()

        update = {
            "update_id": 101,
            "message": {"text": "Hello"},  # Not a callback_query
        }

        self._run_poller([update], redis, pg, notifier)

        redis.set_offset.assert_called_once_with(102)  # last_update_id + 1
        redis.set_ensemble_weights.assert_not_called()
        redis.delete_weight_suggestion.assert_not_called()
        pg.log_weight_update.assert_not_called()
