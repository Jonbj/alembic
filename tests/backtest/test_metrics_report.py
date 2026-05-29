"""Tests for backtest/metrics/report.py (T-006).

Validates markdown + HTML generation from BacktestResult.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics.report import MetricsReport, _line_chart_svg


# ---------------------------------------------------------------------------
# Fake BacktestResult
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, nav: pd.Series):
        self._nav = nav

    def to_nav_series(self) -> pd.Series:
        return self._nav

    def to_returns_series(self) -> pd.Series:
        return self._nav.pct_change().dropna()


@pytest.fixture
def nav_series() -> pd.Series:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-02", periods=252, freq="B")
    r = rng.normal(0.0005, 0.012, 252)
    return pd.Series(100_000 * np.exp(np.cumsum(r)), index=dates)


@pytest.fixture
def fake_result(nav_series) -> _FakeResult:
    return _FakeResult(nav_series)


# ---------------------------------------------------------------------------
# MetricsReport.from_backtest_result
# ---------------------------------------------------------------------------

class TestMetricsReportCreation:
    def test_creates_without_error(self, fake_result):
        report = MetricsReport.from_backtest_result(fake_result)
        assert isinstance(report, MetricsReport)

    def test_period_dates_populated(self, fake_result, nav_series):
        report = MetricsReport.from_backtest_result(fake_result)
        assert report.start_date == str(nav_series.index[0].date())
        assert report.end_date == str(nav_series.index[-1].date())

    def test_n_periods_correct(self, fake_result, nav_series):
        report = MetricsReport.from_backtest_result(fake_result)
        assert report.n_periods == len(nav_series) - 1  # pct_change drops first

    def test_sharpe_finite(self, fake_result):
        report = MetricsReport.from_backtest_result(fake_result)
        assert np.isfinite(report.sharpe)

    def test_max_drawdown_non_positive(self, fake_result):
        report = MetricsReport.from_backtest_result(fake_result)
        assert report.max_drawdown <= 0.0

    def test_var_less_than_es(self, fake_result):
        report = MetricsReport.from_backtest_result(fake_result)
        assert report.es_95 <= report.var_95

    def test_custom_title_stored(self, fake_result):
        report = MetricsReport.from_backtest_result(fake_result, title="My Strategy")
        assert report.title == "My Strategy"


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

class TestMarkdownOutput:
    def test_starts_with_h1(self, fake_result):
        md = MetricsReport.from_backtest_result(fake_result).to_markdown()
        assert md.startswith("# ")

    def test_contains_performance_section(self, fake_result):
        md = MetricsReport.from_backtest_result(fake_result).to_markdown()
        assert "## Performance" in md
        assert "Sharpe" in md
        assert "Calmar" in md
        assert "Sortino" in md

    def test_contains_risk_section(self, fake_result):
        md = MetricsReport.from_backtest_result(fake_result).to_markdown()
        assert "## Risk" in md
        assert "VaR" in md
        assert "Drawdown" in md
        assert "Kurtosis" in md

    def test_period_info_present(self, fake_result):
        md = MetricsReport.from_backtest_result(fake_result).to_markdown()
        assert "2020-01-02" in md

    def test_save_creates_file(self, tmp_path, fake_result):
        report = MetricsReport.from_backtest_result(fake_result)
        p = report.save_markdown(tmp_path / "metrics.md")
        assert p.exists()
        assert p.read_text(encoding="utf-8").startswith("# ")

    def test_save_creates_parent_dirs(self, tmp_path, fake_result):
        report = MetricsReport.from_backtest_result(fake_result)
        p = report.save_markdown(tmp_path / "deep" / "nested" / "r.md")
        assert p.exists()


# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------

class TestHTMLOutput:
    def test_starts_with_doctype(self, fake_result):
        html = MetricsReport.from_backtest_result(fake_result).to_html()
        assert html.startswith("<!DOCTYPE html>")

    def test_has_html_structure(self, fake_result):
        html = MetricsReport.from_backtest_result(fake_result).to_html()
        assert "<html" in html
        assert "</html>" in html
        assert "<body>" in html
        assert "</body>" in html

    def test_contains_metric_cards(self, fake_result):
        html = MetricsReport.from_backtest_result(fake_result).to_html()
        assert "metric-card" in html
        assert "Sharpe" in html

    def test_contains_nav_svg_chart(self, fake_result):
        html = MetricsReport.from_backtest_result(fake_result).to_html()
        assert "<svg" in html
        assert "<polyline" in html

    def test_contains_drawdown_section(self, fake_result):
        html = MetricsReport.from_backtest_result(fake_result).to_html()
        assert "Drawdown" in html

    def test_title_escaped_in_html(self, fake_result):
        report = MetricsReport.from_backtest_result(fake_result, title="A & B <test>")
        html = report.to_html()
        assert "A &amp; B &lt;test&gt;" in html

    def test_save_creates_file(self, tmp_path, fake_result):
        report = MetricsReport.from_backtest_result(fake_result)
        p = report.save_html(tmp_path / "metrics.html")
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_save_creates_parent_dirs(self, tmp_path, fake_result):
        report = MetricsReport.from_backtest_result(fake_result)
        p = report.save_html(tmp_path / "deep" / "r.html")
        assert p.exists()


# ---------------------------------------------------------------------------
# SVG chart helper
# ---------------------------------------------------------------------------

class TestLineSVGChart:
    def test_empty_series_returns_no_svg(self):
        result = _line_chart_svg(pd.Series(dtype=float))
        assert "<svg" not in result

    def test_single_point_renders(self):
        result = _line_chart_svg(pd.Series([1.0]))
        assert "<svg" in result

    def test_polyline_present(self):
        result = _line_chart_svg(pd.Series([1.0, 1.05, 1.03, 1.08]))
        assert "<polyline" in result

    def test_fill_produces_polygon(self):
        result = _line_chart_svg(pd.Series([0.0, -0.05, -0.03]), fill=True)
        assert "<polygon" in result

    def test_color_included(self):
        result = _line_chart_svg(pd.Series([1.0, 2.0]), color="#ff0000")
        assert "#ff0000" in result
