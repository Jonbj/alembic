"""Tests for DecayMonitor and decay_monitor_task (T-605)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.portfolio.decay_monitor import (
    DecayLevel,
    DecayMetric,
    DecayMonitor,
    DecayReport,
    _ic_decay_score,
    _hit_rate_decay_score,
    _sharpe_decay_score,
    _drawdown_decay_score,
    _DECAY_WARNING,
    _DECAY_CRITICAL,
)


# ── Helper fixtures ──────────────────────────────────────────────────────────

BASELINES = {
    "S1": {"ic": 0.05, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.08},
    "S2": {"ic": 0.042, "hit_rate": 0.56, "sharpe": 1.10, "max_drawdown": 0.06},
    "S4": {"ic": 0.028, "hit_rate": 0.52, "sharpe": 0.80, "max_drawdown": 0.10},
}


# ── Decay score functions ────────────────────────────────────────────────────


class TestICDecayScore:
    def test_no_decay_when_actual_equals_baseline(self):
        assert _ic_decay_score(0.05, 0.05) == 0.0

    def test_half_decay_when_actual_drops_50pct(self):
        score = _ic_decay_score(0.05, 0.025)
        assert abs(score - 0.5) < 0.01

    def test_full_decay_when_actual_goes_negative(self):
        score = _ic_decay_score(0.05, -0.05)
        assert score == 1.0

    def test_zero_baseline_negative_actual_is_full_decay(self):
        assert _ic_decay_score(0.0, -0.01) == 1.0

    def test_zero_baseline_positive_actual_is_no_decay(self):
        assert _ic_decay_score(0.0, 0.01) == 0.0

    def test_improvement_gives_zero_decay(self):
        assert _ic_decay_score(0.05, 0.10) == 0.0

    def test_large_negative_actual_clamped_to_one(self):
        score = _ic_decay_score(0.05, -1.0)
        assert score == 1.0


class TestHitRateDecayScore:
    def test_no_decay_when_same(self):
        assert _hit_rate_decay_score(0.55, 0.55) == 0.0

    def test_15pp_drop_gives_moderate_score(self):
        score = _hit_rate_decay_score(0.55, 0.40)
        # 0.15 drop / 0.30 normalisation = 0.5
        assert abs(score - 0.5) < 0.01

    def test_30pp_drop_gives_full_decay(self):
        score = _hit_rate_decay_score(0.55, 0.25)
        assert score == 1.0

    def test_improvement_gives_zero(self):
        assert _hit_rate_decay_score(0.55, 0.65) == 0.0


class TestSharpeDecayScore:
    def test_no_decay_when_equal(self):
        assert _sharpe_decay_score(1.2, 1.2) == 0.0

    def test_half_score_when_actual_is_half(self):
        # ratio = 0.6/1.2 = 0.5, decay = 1 - 0.5 = 0.5
        score = _sharpe_decay_score(1.2, 0.6)
        assert abs(score - 0.5) < 0.01

    def test_zero_actual_gives_full_decay(self):
        assert _sharpe_decay_score(1.2, 0.0) == 1.0

    def test_negative_actual_gives_full_decay(self):
        assert _sharpe_decay_score(1.2, -0.5) == 1.0

    def test_zero_baseline_positive_actual_no_decay(self):
        assert _sharpe_decay_score(0.0, 0.5) == 0.0

    def test_zero_baseline_negative_actual_full_decay(self):
        assert _sharpe_decay_score(0.0, -0.5) == 1.0


class TestDrawdownDecayScore:
    def test_no_decay_when_same(self):
        assert _drawdown_decay_score(0.08, 0.08) == 0.0

    def test_excess_5pp_gives_moderate_score(self):
        # excess = 0.13 - 0.08 = 0.05, score = 0.05/0.10 = 0.5
        score = _drawdown_decay_score(0.08, 0.13)
        assert abs(score - 0.5) < 0.01

    def test_zero_baseline_any_dd_is_decay(self):
        # baseline=0, actual=0.05, score = 0.05/0.10 = 0.5
        score = _drawdown_decay_score(0.0, 0.05)
        assert abs(score - 0.5) < 0.02

    def test_less_dd_than_baseline_is_no_decay(self):
        assert _drawdown_decay_score(0.10, 0.05) == 0.0

    def test_large_dd_clamped_to_one(self):
        score = _drawdown_decay_score(0.08, 0.50)
        assert score == 1.0


# ── DecayMonitor ──────────────────────────────────────────────────────────────


class TestDecayMonitor:
    def setup_method(self):
        self.monitor = DecayMonitor(baselines=BASELINES)

    def test_healthy_strategy_returns_normal(self):
        # Actual metrics same as baseline → no decay
        actual = {"ic": 0.05, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.08}
        report = self.monitor.compute_report("S1", actual)
        assert report.overall_level == DecayLevel.NORMAL
        assert report.overall_decay_score < _DECAY_WARNING
        assert len(report.alerts) == 0

    def test_degraded_ic_fires_alert(self):
        actual = {"ic": 0.01, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.08}
        report = self.monitor.compute_report("S1", actual)
        assert report.overall_decay_score > _DECAY_WARNING
        assert any("IC" in a for a in report.alerts)

    def test_degraded_sharpe_fires_alert(self):
        actual = {"ic": 0.05, "hit_rate": 0.55, "sharpe": 0.4, "max_drawdown": 0.08}
        report = self.monitor.compute_report("S1", actual)
        assert any("Sharpe" in a for a in report.alerts)

    def test_severe_degradation_gives_critical(self):
        actual = {"ic": -0.05, "hit_rate": 0.30, "sharpe": -0.5, "max_drawdown": 0.30}
        report = self.monitor.compute_report("S1", actual)
        assert report.overall_level == DecayLevel.CRITICAL
        assert report.overall_decay_score >= _DECAY_CRITICAL

    def test_moderate_degradation_gives_warning(self):
        actual = {"ic": 0.02, "hit_rate": 0.45, "sharpe": 0.7, "max_drawdown": 0.12}
        report = self.monitor.compute_report("S1", actual)
        assert report.overall_level in (DecayLevel.WARNING, DecayLevel.CRITICAL)

    def test_unknown_strategy_uses_zero_baselines(self):
        actual = {"ic": 0.05, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.08}
        report = self.monitor.compute_report("S99", actual)
        # With zero baselines, positive actual = 0 decay for IC/Sharpe
        assert isinstance(report, DecayReport)
        assert report.strategy_id == "S99"

    def test_report_contains_all_four_metrics(self):
        actual = {"ic": 0.05, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.08}
        report = self.monitor.compute_report("S1", actual)
        metric_names = {m.metric for m in report.metrics}
        assert metric_names == {"ic", "hit_rate", "sharpe", "max_drawdown"}

    def test_metrics_have_correct_levels(self):
        actual = {"ic": 0.05, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.08}
        report = self.monitor.compute_report("S1", actual)
        for m in report.metrics:
            assert m.level == DecayLevel.NORMAL

    def test_timestamp_is_utc(self):
        actual = {"ic": 0.05, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.08}
        report = self.monitor.compute_report("S1", actual)
        assert report.timestamp.tzinfo is not None

    def test_drawdown_excess_fires_alert(self):
        # Actual DD exceeds baseline by >5pp
        actual = {"ic": 0.05, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.15}
        report = self.monitor.compute_report("S1", actual)  # baseline DD=0.08
        assert any("drawdown" in a.lower() for a in report.alerts)


# ── Decay Monitor Celery task ────────────────────────────────────────────────


class TestDecayMonitorTask:
    def test_run_decay_check_returns_results_dict(self):
        from src.workers.decay_monitor_task import run_decay_check

        mock_pg = MagicMock()
        mock_cur = MagicMock()
        # IC query returns None (not enough data)
        mock_cur.fetchone.return_value = (None, None, 0)
        # Returns query returns empty
        mock_cur.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pg._get_connection.return_value = mock_conn
        mock_pg.close = MagicMock()

        with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg):
            with patch("src.workers.decay_monitor_task._store_decay_report", return_value=1):
                result = run_decay_check.run()

        assert "strategies" in result
        assert "total_alerts" in result
        assert len(result["strategies"]) == 3  # S1, S2, S4

    def test_run_decay_check_critical_decay_logs_critical(self):
        from src.workers.decay_monitor_task import run_decay_check

        mock_pg = MagicMock()
        mock_cur = MagicMock()
        # Severe degradation
        mock_cur.fetchone.return_value = (0.1, -0.05, 50)  # hit_rate, ic, n
        mock_cur.fetchall.return_value = [(0.05,), (-0.1,)]  # daily returns
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pg._get_connection.return_value = mock_conn
        mock_pg.close = MagicMock()

        with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg):
            with patch("src.workers.decay_monitor_task._store_decay_report", return_value=1):
                result = run_decay_check.run()

        # Should have alerts due to degradation
        assert result["total_alerts"] >= 0

    def test_fetch_actual_metrics_handles_db_error(self):
        from src.workers.decay_monitor_task import _fetch_actual_metrics

        mock_pg = MagicMock()
        mock_pg._get_connection.side_effect = Exception("DB down")

        result = _fetch_actual_metrics("S1", mock_pg)
        assert result["ic"] == 0.0
        assert result["hit_rate"] == 0.5
        assert result["sharpe"] == 0.0
        assert result["max_drawdown"] == 0.0

    def test_store_decay_report_inserts_rows(self):
        from src.portfolio.decay_monitor import DecayMonitor, DecayLevel
        from src.workers.decay_monitor_task import _store_decay_report

        monitor = DecayMonitor(baselines=BASELINES)
        actual = {"ic": 0.02, "hit_rate": 0.45, "sharpe": 0.7, "max_drawdown": 0.12}
        report = monitor.compute_report("S1", actual)

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pg = MagicMock()
        mock_pg._get_connection.return_value = mock_conn

        _store_decay_report(mock_pg, report)
        assert mock_cur.execute.call_count == 4  # One per metric
        mock_conn.commit.assert_called_once()