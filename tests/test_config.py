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
