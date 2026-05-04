"""Tests for LLM budget tracker."""

from unittest.mock import MagicMock, patch

import pytest

from src.llm.budget import LLMBudgetExhaustedError, LLMBudgetTracker


class TestBudgetTracker:
    """Test LLM budget tracking."""

    def test_check_budget_no_row(self):
        """Test check_budget when no row exists for today."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(tracker.check_budget())

        assert result == "ok"

    def test_check_budget_under_limit(self):
        """Test check_budget when under limit."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total_spent_usd": 25.0, "budget_exhausted": False}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)
        tracker._daily_limit = 50.0

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(tracker.check_budget())

        assert result == "ok"

    def test_check_budget_exhausted(self):
        """Test check_budget when already marked exhausted."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total_spent_usd": 40.0, "budget_exhausted": True}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)

        import asyncio
        with pytest.raises(LLMBudgetExhaustedError):
            asyncio.get_event_loop().run_until_complete(tracker.check_budget())

    def test_check_budget_over_limit(self):
        """Test check_budget when over limit."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total_spent_usd": 60.0, "budget_exhausted": False}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)
        tracker._daily_limit = 50.0

        import asyncio
        with pytest.raises(LLMBudgetExhaustedError):
            asyncio.get_event_loop().run_until_complete(tracker.check_budget())

    def test_record_spending(self):
        """Test recording spending."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total_spent_usd": 5.0}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)

        import asyncio
        spent = asyncio.get_event_loop().run_until_complete(
            tracker.record_spending("opus", input_tokens=1000, output_tokens=500)
        )

        # Verify cursor was used
        mock_cursor.execute.assert_called()
        assert spent >= 0  # Some spending recorded

    def test_get_remaining_budget(self):
        """Test getting remaining budget."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total_spent_usd": 20.0}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)
        tracker._daily_limit = 50.0

        import asyncio
        remaining = asyncio.get_event_loop().run_until_complete(tracker.get_remaining_budget())

        assert remaining == 30.0

    def test_get_remaining_budget_no_spending(self):
        """Test getting remaining budget when no spending yet."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)
        tracker._daily_limit = 50.0

        import asyncio
        remaining = asyncio.get_event_loop().run_until_complete(tracker.get_remaining_budget())

        assert remaining == 50.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
