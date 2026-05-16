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


class TestWatchlistSymbols:
    def test_default_watchlist_is_populated(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        assert isinstance(cfg.WATCHLIST_SYMBOLS, list)
        assert len(cfg.WATCHLIST_SYMBOLS) > 0

    def test_default_watchlist_contains_expected_symbols(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        for symbol in ("AAPL", "MSFT", "GOOGL", "NVDA", "SPY", "QQQ"):
            assert symbol in cfg.WATCHLIST_SYMBOLS

    def test_watchlist_overridable(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
            WATCHLIST_SYMBOLS=["TSLA", "AMZN"],
        )
        assert cfg.WATCHLIST_SYMBOLS == ["TSLA", "AMZN"]


class TestNewsAPIKey:
    def test_newsapi_key_field_exists(self, monkeypatch):
        monkeypatch.delenv("NEWSAPI_KEY", raising=False)
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        assert hasattr(cfg, "NEWSAPI_KEY")
        assert cfg.NEWSAPI_KEY == ""

    def test_newsapi_key_reads_from_constructor(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
            NEWSAPI_KEY="test-key-123",
        )
        assert cfg.NEWSAPI_KEY == "test-key-123"
