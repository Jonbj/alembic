"""IC net-of-costs fields in BacktestReport."""
import pytest
from src.backtest.report import BacktestReport, BacktestReportBuilder
from src.performance.ic import ICResult, ICIRResult
from datetime import datetime, timezone


def _make_report(**overrides) -> BacktestReport:
    base = dict(
        run_id="test",
        period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
        total_signals=100,
        signals_with_returns=80,
        ic_1h=ICResult(composite_ic=0.30, spearman_ic=0.02, weighted_hit_rate=0.55, brier_score=0.25, sample_count=80),
        ic_4h=ICResult(composite_ic=0.28, spearman_ic=0.01, weighted_hit_rate=0.52, brier_score=0.26, sample_count=70),
        ic_24h=ICResult(composite_ic=0.29, spearman_ic=0.015, weighted_hit_rate=0.53, brier_score=0.255, sample_count=75),
        icir_1h=ICIRResult(icir=12.0, ic_mean=0.28, ic_std=0.13, newey_west_std=0.022, lag=3, sample_count=80),
        icir_4h=ICIRResult(icir=11.0, ic_mean=0.27, ic_std=0.12, newey_west_std=0.021, lag=3, sample_count=70),
        icir_24h=ICIRResult(icir=13.0, ic_mean=0.29, ic_std=0.11, newey_west_std=0.020, lag=3, sample_count=75),
        ic_1h_net=ICResult(composite_ic=0.28, spearman_ic=0.018, weighted_hit_rate=0.54, brier_score=0.252, sample_count=80),
        ic_4h_net=None,
        ic_24h_net=ICResult(composite_ic=0.27, spearman_ic=0.012, weighted_hit_rate=0.51, brier_score=0.258, sample_count=75),
        icir_1h_net=ICIRResult(icir=11.5, ic_mean=0.265, ic_std=0.13, newey_west_std=0.022, lag=3, sample_count=80),
        icir_4h_net=None,
        icir_24h_net=ICIRResult(icir=12.2, ic_mean=0.275, ic_std=0.11, newey_west_std=0.020, lag=3, sample_count=75),
    )
    base.update(overrides)
    return BacktestReport(**base)


class TestBacktestReportNetIC:
    def test_to_dict_includes_net_fields(self):
        report = _make_report()
        d = report.to_dict()
        assert "ic_1h_net" in d
        assert "icir_1h_net" in d
        assert "ic_4h_net" in d
        assert "icir_4h_net" in d
        assert "ic_24h_net" in d
        assert "icir_24h_net" in d

    def test_net_ic_lower_than_gross(self):
        report = _make_report()
        d = report.to_dict()
        assert d["ic_1h"]["composite_ic"] > d["ic_1h_net"]["composite_ic"]
        assert d["ic_24h"]["composite_ic"] > d["ic_24h_net"]["composite_ic"]

    def test_gross_fields_unchanged(self):
        """Gross IC fields must not be modified."""
        report = _make_report()
        d = report.to_dict()
        assert d["ic_1h"]["composite_ic"] == pytest.approx(0.30)
        assert d["icir_24h"]["icir"] == pytest.approx(13.0)

    def test_none_net_fields_serialize_as_none(self):
        report = _make_report()
        d = report.to_dict()
        assert d["ic_4h_net"] is None
        assert d["icir_4h_net"] is None
