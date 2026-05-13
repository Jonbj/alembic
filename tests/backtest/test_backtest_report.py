"""Tests for BacktestReportBuilder."""

import json
from unittest.mock import MagicMock

import pytest

from src.backtest.report import BacktestReport, BacktestReportBuilder


def make_rows(
    n: int,
    symbol: str = "AAPL",
    model_id: str = "ensemble:opus",
    return_1h: float = 0.01,
    return_4h: float = 0.02,
    return_24h: float = 0.015,
    score: float = 0.5,
    confidence: float = 0.8,
    fallback_used: bool = False,
) -> list[tuple]:
    """Generate n fake scored rows with forward returns."""
    return [
        (symbol, model_id, score, confidence, fallback_used, return_1h, return_4h, return_24h)
        for _ in range(n)
    ]
    # columns: symbol, model_id, score, confidence, fallback_used,
    #          forward_return_1h, forward_return_4h, forward_return_24h


def make_builder_with_rows(rows: list[tuple]) -> BacktestReportBuilder:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    mock_cur.fetchall.return_value = rows
    # build() calls fetchone twice: COUNT_TOTAL then FETCH_BOUNDS
    mock_cur.fetchone.side_effect = [
        (len(rows),),  # COUNT_TOTAL
        (None, None),  # FETCH_BOUNDS (period_start, period_end)
    ]
    return BacktestReportBuilder(pg_conn=mock_conn)


def test_report_computes_ic_at_three_horizons():
    """build() produces non-None IC results for 1h, 4h, 24h when >= 30 rows."""
    rows = make_rows(50)
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert report.ic_1h is not None
    assert report.ic_4h is not None
    assert report.ic_24h is not None
    assert report.signals_with_returns == 50


def test_report_returns_none_ic_below_min_samples():
    """build() returns None for a horizon when fewer than 30 rows have that return."""
    rows = make_rows(10)
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert report.ic_1h is None
    assert report.ic_4h is None
    assert report.ic_24h is None


def test_report_by_model_populated():
    """build() groups IC results by model_id."""
    rows = make_rows(50, model_id="ensemble:opus") + make_rows(50, model_id="finbert")
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert "ensemble:opus" in report.by_model
    assert "finbert" in report.by_model


def test_report_by_model_all_three_horizons():
    """build() computes IC/ICIR at all three horizons per model_id."""
    rows = make_rows(50)
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert "ensemble:opus" in report.by_model
    stats = report.by_model["ensemble:opus"]
    for key in ("ic_1h", "ic_4h", "ic_24h", "icir_1h", "icir_4h", "icir_24h"):
        assert key in stats, f"Missing key '{key}' in by_model stats"


def test_report_by_symbol_populated():
    """build() groups 24h IC results by symbol."""
    rows = make_rows(50, symbol="AAPL") + make_rows(50, symbol="MSFT")
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert "AAPL" in report.by_symbol
    assert "MSFT" in report.by_symbol


def test_report_excludes_none_returns():
    """build() counts only rows where at least one forward_return is not None."""
    rows_with = make_rows(40)
    rows_without = [("AAPL", "ensemble:opus", 0.5, 0.8, False, None, None, None)] * 10
    builder = make_builder_with_rows(rows_with + rows_without)
    report = builder.build("test-run")

    assert report.signals_with_returns == 40


def test_report_excludes_fallback_rows():
    """build() excludes rows where fallback_used=True from IC computation."""
    rows = make_rows(50, fallback_used=True)
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert report.ic_1h is None
    assert report.ic_4h is None
    assert report.ic_24h is None
    assert report.signals_with_returns == 0


def test_report_serializes_to_json():
    """BacktestReport can be serialized to a JSON-compatible dict."""
    rows = make_rows(50)
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    data = report.to_dict()
    json_str = json.dumps(data)  # must not raise
    parsed = json.loads(json_str)
    assert parsed["run_id"] == "test-run"
    assert "by_symbol" in parsed
    assert "period_start" in parsed
    assert "period_end" in parsed
