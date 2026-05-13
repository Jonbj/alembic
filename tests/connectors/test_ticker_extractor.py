"""Tests for TickerExtractor."""

from unittest.mock import MagicMock, call

import pytest

from src.connectors.ticker_extractor import TickerExtractor


def make_pg_conn(rows_by_query: dict) -> MagicMock:
    """Mock psycopg2 connection that returns rows based on query substring."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    def execute_side_effect(sql, params=None):
        cur._last_sql = sql
        cur._last_params = params

    def fetchall_side_effect():
        for key, rows in rows_by_query.items():
            if key in (cur._last_sql or ""):
                return rows
        return []

    cur.execute.side_effect = execute_side_effect
    cur.fetchall.side_effect = fetchall_side_effect

    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def test_extract_exact_match():
    """Known org name maps to correct ticker."""
    conn = make_pg_conn({"lower(company_name)": [("AAPL",)]})
    extractor = TickerExtractor(conn)
    result = extractor.extract(["Apple Inc"])
    assert "AAPL" in result


def test_extract_empty_org_names_returns_empty():
    """Empty input returns empty list without querying DB."""
    conn = MagicMock()
    extractor = TickerExtractor(conn)
    assert extractor.extract([]) == []
    conn.cursor.assert_not_called()


def test_extract_no_match_returns_empty():
    """Unknown org name returns empty list."""
    conn = make_pg_conn({"lower(company_name)": [], "aliases": []})
    extractor = TickerExtractor(conn)
    result = extractor.extract(["UnknownCorp XYZ"])
    assert result == []


def test_extract_deduplicates_tickers():
    """Same ticker from multiple org names appears once."""
    conn = make_pg_conn({"lower(company_name)": [("AAPL",), ("AAPL",)]})
    extractor = TickerExtractor(conn)
    result = extractor.extract(["Apple Inc", "Apple Incorporated"])
    assert result.count("AAPL") == 1


def test_extract_multiple_tickers():
    """Two different org names return two tickers."""
    conn = make_pg_conn({"lower(company_name)": [("AAPL",), ("MSFT",)]})
    extractor = TickerExtractor(conn)
    result = extractor.extract(["Apple Inc", "Microsoft Corporation"])
    assert "AAPL" in result
    assert "MSFT" in result


def test_normalize_strips_inc():
    assert TickerExtractor.normalize("Apple Inc") == "apple"


def test_normalize_strips_corporation():
    assert TickerExtractor.normalize("Microsoft Corporation") == "microsoft"


def test_normalize_strips_trailing_dot():
    assert TickerExtractor.normalize("Apple Inc.") == "apple"


def test_normalize_case_insensitive():
    assert TickerExtractor.normalize("APPLE INC") == "apple"


def test_normalize_preserves_ampersand_words():
    assert "johnson" in TickerExtractor.normalize("Johnson & Johnson")


def test_normalize_strips_ltd():
    assert TickerExtractor.normalize("Some Company Ltd") == "some"


def test_normalize_empty_string():
    assert TickerExtractor.normalize("") == ""
