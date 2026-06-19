"""P1-12 Paper/live divergence monitoring.

Problem (from audit): no metric exists to detect when paper-trading signals
diverge from what a live system would trade. Without this, paper trading
cannot serve as a valid proxy for live behavior.

Two main divergence sources:
1. Signal divergence: paper signals (from DB) differ from what live would use.
2. Execution divergence: paper order fill ≠ live fill (slippage, partial fill).

Fix: add check_signal_divergence() and check_execution_divergence()
primitives to src/monitoring/alerts.py.
"""
from __future__ import annotations

import pytest


class TestPaperLiveDivergenceModule:

    def test_check_signal_divergence_exported(self):
        try:
            from src.monitoring.alerts import check_signal_divergence
        except ImportError:
            pytest.fail(
                "src.monitoring.alerts must export check_signal_divergence(). "
                "This detects when paper signals differ from live signals."
            )

    def test_check_execution_divergence_exported(self):
        try:
            from src.monitoring.alerts import check_execution_divergence
        except ImportError:
            pytest.fail(
                "src.monitoring.alerts must export check_execution_divergence(). "
                "This detects when paper fills diverge from live fills."
            )


class TestSignalDivergence:

    def test_alert_fires_when_signal_overlap_below_threshold(self):
        """check_signal_divergence returns True when overlap_fraction < threshold.

        If paper generates BUY for AAPL, MSFT, GOOG but live would only BUY AAPL,
        overlap = 1/3 = 0.33. Threshold = 0.8 → alert fires.
        """
        from src.monitoring.alerts import check_signal_divergence

        paper_signals = {"AAPL", "MSFT", "GOOG"}
        live_signals  = {"AAPL"}

        alert = check_signal_divergence(
            paper_signals=paper_signals,
            live_signals=live_signals,
            threshold=0.8,
        )
        assert alert is True, (
            "check_signal_divergence must return True when signal overlap is below threshold. "
            "Overlap 1/3 < 0.8 → alert."
        )

    def test_no_alert_when_signals_identical(self):
        """check_signal_divergence returns False when paper == live signals."""
        from src.monitoring.alerts import check_signal_divergence

        signals = {"AAPL", "MSFT"}
        alert = check_signal_divergence(
            paper_signals=signals,
            live_signals=signals,
            threshold=0.8,
        )
        assert alert is False

    def test_no_alert_when_overlap_above_threshold(self):
        """check_signal_divergence returns False when overlap ≥ threshold."""
        from src.monitoring.alerts import check_signal_divergence

        alert = check_signal_divergence(
            paper_signals={"AAPL", "MSFT", "GOOG"},
            live_signals={"AAPL", "MSFT", "TSLA"},
            threshold=0.5,  # overlap = 2/4 = 0.5 → no alert
        )
        assert alert is False

    def test_alert_fires_when_both_empty_not_equal(self):
        """Both empty → overlap undefined but no divergence → no alert."""
        from src.monitoring.alerts import check_signal_divergence

        alert = check_signal_divergence(
            paper_signals=set(),
            live_signals=set(),
            threshold=0.8,
        )
        assert alert is False


class TestExecutionDivergence:

    def test_alert_fires_when_fill_ratio_diverges(self):
        """check_execution_divergence returns True when |paper_fill - live_fill| > threshold.

        Paper got 100% fill; live got 60% fill. Divergence = 0.40 > threshold=0.20 → alert.
        """
        from src.monitoring.alerts import check_execution_divergence

        alert = check_execution_divergence(
            paper_fill_ratio=1.0,
            live_fill_ratio=0.6,
            threshold=0.20,
        )
        assert alert is True, (
            "check_execution_divergence must return True when |paper - live| > threshold. "
            "|1.0 - 0.6| = 0.4 > 0.2 → alert."
        )

    def test_no_alert_when_fills_close(self):
        """check_execution_divergence returns False when fills are within threshold."""
        from src.monitoring.alerts import check_execution_divergence

        alert = check_execution_divergence(
            paper_fill_ratio=0.95,
            live_fill_ratio=0.90,
            threshold=0.10,
        )
        assert alert is False
