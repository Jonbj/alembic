"""P0-03 (WS-02) — Paper/live explicit single source tests.

Currently the trading mode (paper vs live) is derived from a substring
check on ALPACA_BASE_URL in four different worker files:

    paper = "paper-api" in config.ALPACA_BASE_URL

This is fragile:
  - Changing the URL silently changes the trading mode.
  - The decision is scattered across 3 worker files.
  - There is no explicit audit-able signal that the system is in live mode.

Fix: add ALPACA_PAPER_MODE: bool to Config (single source of truth).
     Replace all four substring checks with config.ALPACA_PAPER_MODE.
"""

import os
from unittest.mock import patch


class TestAlpacaPaperModeConfig:
    """Config must expose an explicit ALPACA_PAPER_MODE field."""

    def test_alpaca_paper_mode_field_exists(self):
        """Config must have ALPACA_PAPER_MODE — not derived from URL at call sites."""
        from src.config import Config

        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        assert hasattr(cfg, "ALPACA_PAPER_MODE"), (
            "Config is missing ALPACA_PAPER_MODE field.\n"
            "Add: ALPACA_PAPER_MODE: bool = Field(default_factory=lambda: "
            "os.environ.get('ALPACA_PAPER_MODE', 'true').lower() == 'true')"
        )

    def test_alpaca_paper_mode_defaults_to_true(self):
        """Default must be paper=True — safe per the operational freeze policy."""
        from src.config import Config

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ALPACA_PAPER_MODE", None)
            cfg = Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
            )
        assert cfg.ALPACA_PAPER_MODE is True, (
            f"ALPACA_PAPER_MODE should default to True (paper), got {cfg.ALPACA_PAPER_MODE!r}"
        )

    def test_alpaca_paper_mode_explicit_false_via_env(self):
        """ALPACA_PAPER_MODE=false must set live mode — explicit opt-in to live."""
        from src.config import Config

        with patch.dict(os.environ, {"ALPACA_PAPER_MODE": "false"}):
            cfg = Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
            )
        assert cfg.ALPACA_PAPER_MODE is False

    def test_alpaca_paper_mode_independent_of_url(self):
        """Mode must NOT depend on URL content — env var wins regardless of URL."""
        from src.config import Config

        # Paper mode explicitly true, even when URL looks like live
        with patch.dict(os.environ, {
            "ALPACA_PAPER_MODE": "true",
            "ALPACA_BASE_URL": "https://api.alpaca.markets",
        }):
            cfg = Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
            )
        assert cfg.ALPACA_PAPER_MODE is True, (
            "ALPACA_PAPER_MODE=true should hold even when URL does not contain 'paper-api'"
        )


class TestNoSubstringModeDetection:
    """Worker files must not deduce mode from URL substring."""

    def _assert_no_substring_check(self, path: str) -> None:
        import pathlib

        source = pathlib.Path(path).read_text()
        assert '"paper-api" in' not in source, (
            f"{path} still uses '\"paper-api\" in config.ALPACA_BASE_URL' for mode detection.\n"
            "Replace with: config.ALPACA_PAPER_MODE"
        )

    def test_execution_worker_no_substring_mode(self):
        """execution.py must use config.ALPACA_PAPER_MODE, not URL substring."""
        self._assert_no_substring_check("src/workers/execution.py")

    def test_portfolio_scheduler_no_substring_mode(self):
        """portfolio_scheduler.py must use config.ALPACA_PAPER_MODE, not URL substring."""
        self._assert_no_substring_check("src/workers/portfolio_scheduler.py")

    def test_performance_worker_no_substring_mode(self):
        """performance.py must use config.ALPACA_PAPER_MODE, not URL substring."""
        self._assert_no_substring_check("src/workers/performance.py")
