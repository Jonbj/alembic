"""Tests for retention worker."""

import pytest
from unittest.mock import MagicMock, patch

from src.workers.retention import run_retention_sweep


def test_retention_sweep_calls_delete_methods():
    """run_retention_sweep calls both delete methods with configured thresholds."""
    mock_pg = MagicMock()
    mock_pg.delete_old_news_log.return_value = 42
    mock_pg.delete_old_llm_responses.return_value = 100

    with patch("src.workers.retention.PostgreSQLStore", return_value=mock_pg), \
         patch("src.workers.retention.psycopg2.connect"), \
         patch("src.workers.retention._load_retention_config", return_value={}):
        result = run_retention_sweep()

    mock_pg.delete_old_news_log.assert_called_once_with(older_than_days=180)
    mock_pg.delete_old_llm_responses.assert_called_once_with(older_than_days=365)
    assert result["deleted_news_log"] == 42
    assert result["deleted_llm_responses"] == 100


def test_retention_sweep_returns_stats():
    """run_retention_sweep returns a stats dict with deleted counts."""
    mock_pg = MagicMock()
    mock_pg.delete_old_news_log.return_value = 0
    mock_pg.delete_old_llm_responses.return_value = 0

    with patch("src.workers.retention.PostgreSQLStore", return_value=mock_pg), \
         patch("src.workers.retention.psycopg2.connect"), \
         patch("src.workers.retention._load_retention_config", return_value={}):
        result = run_retention_sweep()

    assert "deleted_news_log" in result
    assert "deleted_llm_responses" in result


def test_retention_sweep_uses_config_thresholds():
    """run_retention_sweep uses thresholds from config file."""
    mock_pg = MagicMock()
    mock_pg.delete_old_news_log.return_value = 10
    mock_pg.delete_old_llm_responses.return_value = 20

    with patch("src.workers.retention.PostgreSQLStore", return_value=mock_pg), \
         patch("src.workers.retention.psycopg2.connect"), \
         patch("src.workers.retention._load_retention_config", return_value={
             "news_log_days": 90,
             "llm_responses_days": 180
         }):
        result = run_retention_sweep()

    mock_pg.delete_old_news_log.assert_called_once_with(older_than_days=90)
    mock_pg.delete_old_llm_responses.assert_called_once_with(older_than_days=180)
