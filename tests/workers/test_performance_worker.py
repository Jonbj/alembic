"""Tests for PerformanceWorker Celery tasks."""

import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.models.performance import PerformanceReport
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore
from src.workers.performance import (
    _build_signal_distribution,
    _compute_bucket_ic,
    _fetch_all_per_model_signals_for_loo,
    _fetch_all_signals_for_ic,
    _format_performance_telegram_message,
    _suggest_threshold,
    build_performance_report,
    check_suggestion_expiry,
    run_daily_report,
    run_drift_detection,
    run_weekly_weights,
)


def make_signal_row(
    score: float,
    forward_return: float,
    model_id: str = "opus",
    fallback_used: bool = False,
    confidence: float = 0.75,
) -> tuple:
    """Create a mock signal row as returned by fetch_signals_for_ic.

    Returns: (score, confidence, forward_return, generated_at, model_id, fallback_used)
    """
    return (
        score,
        confidence,
        forward_return,
        "2026-05-01",
        model_id,
        fallback_used,
    )


def generate_signal_rows(
    n: int,
    model_id: str = "opus",
    score_mean: float = 0.0,
    score_std: float = 0.5,
    return_correlation: float = 0.0,
    fallback_used: bool = False,
) -> list[tuple]:
    """Generate synthetic signal rows for testing.

    Args:
        n: Number of rows to generate
        model_id: Model identifier
        score_mean: Mean of score distribution
        score_std: Std of score distribution
        return_correlation: Correlation between scores and returns
        fallback_used: Whether these are FinBERT fallback rows

    Returns:
        List of signal row tuples
    """
    rng = np.random.default_rng(42)
    scores = rng.normal(score_mean, score_std, n).tolist()

    if return_correlation != 0:
        # Generate returns correlated with scores
        noise = rng.normal(0, 0.02, n)
        returns = (np.array(scores) * return_correlation * 0.02 + noise).tolist()
    else:
        returns = rng.normal(0, 0.02, n).tolist()

    confidences = rng.uniform(0.5, 1.0, n).tolist()
    return [make_signal_row(s, r, model_id, fallback_used, c) for s, r, c in zip(scores, returns, confidences)]


class TestBuildPerformanceReport:
    """Tests for build_performance_report function."""

    def test_insufficient_samples_returns_empty_report(self):
        """Test that insufficient samples returns empty report."""
        mock_pg = MagicMock(spec=PostgreSQLStore)

        current_weights = {"opus": 1.0}
        # Patch _fetch_all_signals_for_ic to return exactly 10 rows total (below
        # the module-level _MIN_SAMPLES=300 threshold).  Mocking fetch_signals_for_ic
        # alone would return 10 rows per symbol (89 symbols × 10 = 890 rows), which
        # bypasses the guard entirely.
        with patch("src.workers.performance._fetch_all_signals_for_ic") as mock_fetch:
            mock_fetch.return_value = [make_signal_row(0.5, 0.02, "opus") for _ in range(10)]
            report = build_performance_report(mock_pg, current_weights, period_days=30)

        assert isinstance(report, PerformanceReport)
        assert report.overall_ic == 0.0
        assert report.icir == 0.0
        assert report.hit_rate == 0.0
        assert report.weight_change_applied is False

    def test_report_with_sufficient_samples(self):
        """Test report generation with sufficient samples."""
        mock_pg = MagicMock(spec=PostgreSQLStore)

        # Generate 350 rows with positive correlation (should yield positive IC)
        rows = generate_signal_rows(350, model_id="opus", return_correlation=0.5)
        mock_pg.fetch_signals_for_ic.return_value = rows

        current_weights = {"opus": 1.0}
        with patch("src.workers.performance._fetch_all_per_model_signals_for_loo") as mock_pm:
            mock_pm.return_value = []
            report = build_performance_report(mock_pg, current_weights, period_days=30)

        assert isinstance(report, PerformanceReport)
        assert -1.0 <= report.overall_ic <= 1.0
        assert 0.0 <= report.hit_rate <= 1.0
        assert "opus" in report.model_ic
        assert report.weight_change_applied is False

    def test_report_with_multiple_models(self):
        """Test report with multiple models in ensemble."""
        mock_pg = MagicMock(spec=PostgreSQLStore)

        # Generate rows for overall IC (model_id here is the compound ensemble ID
        # as written to sentiment_signals — irrelevant for per-model IC after the fix)
        rows = []
        rows.extend(generate_signal_rows(150, "opus", return_correlation=0.4))
        rows.extend(generate_signal_rows(150, "qwen3.5:cloud", return_correlation=0.2))
        rows.extend(generate_signal_rows(150, "deepseek-v4-pro:cloud", return_correlation=0.1))
        mock_pg.fetch_signals_for_ic.return_value = rows

        # Per-model rows from llm_responses (individual model IDs).
        # Opus has strong signal-return correlation; deepseek is uncorrelated.
        rng = np.random.default_rng(42)
        n = 50
        opus_sig = rng.normal(0, 0.5, n)
        opus_ret = opus_sig * 0.10 + rng.normal(0, 0.01, n)
        qwen_sig = rng.normal(0, 0.5, n)
        qwen_ret = qwen_sig * 0.04 + rng.normal(0, 0.01, n)
        ds_sig = rng.normal(0, 0.5, n)
        ds_ret = rng.normal(0, 0.02, n)   # no correlation with signal
        pm_rows = (
            [("opus", float(s), float(r)) for s, r in zip(opus_sig, opus_ret)] +
            [("qwen3.5:cloud", float(s), float(r)) for s, r in zip(qwen_sig, qwen_ret)] +
            [("deepseek-v4-pro:cloud", float(s), float(r)) for s, r in zip(ds_sig, ds_ret)]
        )

        current_weights = {"opus": 0.34, "qwen3.5:cloud": 0.33, "deepseek-v4-pro:cloud": 0.33}
        with patch("src.workers.performance._fetch_all_per_model_signals_for_loo") as mock_pm:
            mock_pm.return_value = pm_rows
            report = build_performance_report(mock_pg, current_weights, period_days=30)

        assert isinstance(report, PerformanceReport)
        assert set(report.model_ic.keys()) == set(current_weights.keys())
        # Opus (strong correlation) should have higher IC than deepseek (no correlation)
        assert report.model_ic["opus"] > report.model_ic["deepseek-v4-pro:cloud"]

    def test_report_excludes_fallback_rows(self):
        """Test that fallback rows are excluded from IC calculation."""
        mock_pg = MagicMock(spec=PostgreSQLStore)

        # Mix of ensemble and fallback rows
        rows = []
        rows.extend(generate_signal_rows(200, "opus", return_correlation=0.5, fallback_used=False))
        rows.extend(generate_signal_rows(150, "finbert", return_correlation=0.1, fallback_used=True))

        mock_pg.fetch_signals_for_ic.return_value = rows

        current_weights = {"opus": 1.0}
        with patch("src.workers.performance._fetch_all_per_model_signals_for_loo") as mock_pm:
            mock_pm.return_value = []
            report = build_performance_report(mock_pg, current_weights, period_days=30)

        # Should only use ensemble rows (fallback excluded)
        assert isinstance(report, PerformanceReport)
        # FinBERT should not appear in model_ic since fallbacks are excluded
        assert "finbert" not in report.model_ic


    def test_per_model_ic_uses_individual_model_ids_not_compound(self):
        """Regression: per-model IC must come from llm_responses (individual IDs).

        Bug: sentiment_signals.model_id stores compound IDs like
        'ensemble:kimi+qwen+deepseek+glm'.  Grouping by that key and then
        looking up 'kimi-k2.6:cloud' always returns [] → model_ic always 0.
        Fix: source per-model IC from _fetch_all_per_model_signals_for_loo()
        which queries llm_responses and stores the correct individual model_id.
        """
        mock_pg = MagicMock(spec=PostgreSQLStore)

        # Overall rows use a compound model_id (as written to sentiment_signals
        # in production — should NOT affect per-model IC lookup)
        compound_rows = generate_signal_rows(
            350, model_id="ensemble:kimi+qwen+deepseek+glm", return_correlation=0.5
        )
        mock_pg.fetch_signals_for_ic.return_value = compound_rows

        # Per-model rows from llm_responses with an individual model ID
        rng = np.random.default_rng(7)
        n = 50
        signals = rng.normal(0, 0.5, n)
        returns = signals * 0.08 + rng.normal(0, 0.01, n)
        pm_rows = [("kimi-k2.6:cloud", float(s), float(r)) for s, r in zip(signals, returns)]

        current_weights = {"kimi-k2.6:cloud": 0.5, "glm-5.1:cloud": 0.5}

        with patch("src.workers.performance._fetch_all_per_model_signals_for_loo") as mock_pm:
            mock_pm.return_value = pm_rows
            report = build_performance_report(mock_pg, current_weights, period_days=30)

        # kimi-k2.6:cloud has 50 per-model rows → non-zero IC from llm_responses
        assert report.model_ic["kimi-k2.6:cloud"] != 0.0, (
            "model_ic should be non-zero when llm_responses has data for the model"
        )
        # glm-5.1:cloud has no per-model rows → defaults to 0
        assert report.model_ic["glm-5.1:cloud"] == 0.0


class TestComputeBucketIC:
    """Tests for _compute_bucket_ic function."""

    def test_bucket_ic_computation(self):
        """Test bucket IC computation."""
        rng = np.random.default_rng(42)
        scores = rng.uniform(0.1, 1.0, 200).tolist()
        returns = rng.normal(0, 0.02, 200).tolist()
        confidences = [0.75] * 200

        bucket_ic = _compute_bucket_ic(scores, returns, confidences)

        assert isinstance(bucket_ic, dict)
        assert "0.1-0.2" in bucket_ic
        assert "0.2-0.3" in bucket_ic
        assert "0.3-0.4" in bucket_ic
        assert "0.4-0.6" in bucket_ic
        assert "0.6-1.0" in bucket_ic

    def test_bucket_ic_empty_buckets(self):
        """Test bucket IC with insufficient samples in buckets."""
        # All scores in same bucket
        scores = [0.5] * 100
        returns = [0.02] * 100
        confidences = [0.75] * 100

        bucket_ic = _compute_bucket_ic(scores, returns, confidences)

        # Only 0.4-0.6 bucket should have data
        assert bucket_ic["0.4-0.6"] != 0.0
        # Other buckets should be 0.0 (insufficient samples)
        assert bucket_ic["0.1-0.2"] == 0.0


class TestSuggestThreshold:
    """Tests for _suggest_threshold function."""

    def test_suggest_higher_threshold_on_improvement(self):
        """Test threshold suggestion when stricter bucket has better IC."""
        bucket_ic = {
            "0.1-0.2": 0.05,
            "0.2-0.3": 0.08,
            "0.3-0.4": 0.10,
            "0.4-0.6": 0.15,  # 50% improvement over 0.3-0.4
            "0.6-1.0": 0.18,
        }

        suggestion = _suggest_threshold(bucket_ic, current_threshold=0.3)

        # Should suggest higher threshold
        assert suggestion is not None
        assert suggestion >= 0.4

    def test_no_suggestion_without_improvement(self):
        """Test no suggestion when stricter buckets don't improve."""
        bucket_ic = {
            "0.1-0.2": 0.05,
            "0.2-0.3": 0.08,
            "0.3-0.4": 0.10,
            "0.4-0.6": 0.09,  # Worse than current
            "0.6-1.0": 0.08,
        }

        suggestion = _suggest_threshold(bucket_ic, current_threshold=0.3)

        assert suggestion is None

    def test_no_suggestion_with_missing_buckets(self):
        """Test no suggestion when current bucket is missing."""
        bucket_ic = {
            "0.1-0.2": 0.05,
            "0.4-0.6": 0.15,
            "0.6-1.0": 0.18,
            # Missing 0.2-0.3 and 0.3-0.4
        }

        suggestion = _suggest_threshold(bucket_ic, current_threshold=0.3)

        assert suggestion is None


class TestFetchAllSignalsForIC:
    """Tests for _fetch_all_signals_for_ic function."""

    def test_fetches_from_multiple_symbols(self):
        """Test fetching signals from multiple symbols."""
        mock_pg = MagicMock(spec=PostgreSQLStore)
        mock_pg.fetch_signals_for_ic.return_value = [
            make_signal_row(0.5, 0.02, "opus")
        ]

        rows = _fetch_all_signals_for_ic(mock_pg, days=30)

        # Should call fetch_signals_for_ic for each symbol
        assert mock_pg.fetch_signals_for_ic.call_count >= 1
        assert isinstance(rows, list)

    def test_fetch_all_signals_uses_watchlist_symbols(self):
        """_fetch_all_signals_for_ic uses config.WATCHLIST_SYMBOLS, not hardcoded list."""
        from src.workers.performance import _fetch_all_signals_for_ic
        from src.config import config

        mock_pg = MagicMock()
        mock_pg.fetch_signals_for_ic.return_value = []

        _fetch_all_signals_for_ic(mock_pg, days=30)

        called_symbols = [call[0][0] for call in mock_pg.fetch_signals_for_ic.call_args_list]
        for symbol in config.WATCHLIST_SYMBOLS:
            assert symbol in called_symbols


class TestRunDailyReport:
    """Tests for run_daily_report Celery task."""

    @patch("src.workers.performance.PostgreSQLStore")
    @patch("src.workers.performance.RedisStore")
    @patch("src.workers.performance.TelegramNotifier")
    def test_run_daily_report_success(
        self, mock_notifier_cls, mock_redis_cls, mock_pg_cls
    ):
        """Test successful daily report execution."""
        # Mock PostgreSQL
        mock_pg = MagicMock(spec=PostgreSQLStore)
        mock_pg_cls.return_value = mock_pg

        # Generate sufficient samples
        rows = generate_signal_rows(350, "opus", return_correlation=0.3)
        mock_pg.fetch_signals_for_ic.return_value = rows
        mock_pg.fetch_per_model_signals_for_ic.return_value = []

        # Mock Redis with proper get_ensemble_weights method
        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.get_ensemble_weights.return_value = None  # No weights stored, use defaults
        mock_redis._r = MagicMock()
        mock_redis_cls.return_value = mock_redis

        # Mock Telegram with async send_alert
        mock_notifier = MagicMock()
        mock_notifier.send_alert = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        # Run task
        run_daily_report()

        # Verify stores were initialized
        mock_pg_cls.assert_called_once()
        mock_redis_cls.assert_called_once()

        # Verify Telegram alert was sent
        mock_notifier.send_alert.assert_called_once()

    @patch("src.workers.performance.PostgreSQLStore")
    @patch("src.workers.performance.RedisStore")
    def test_run_daily_report_handles_exception(
        self, mock_redis_cls, mock_pg_cls
    ):
        """Test daily report handles exceptions gracefully."""
        mock_pg = MagicMock(spec=PostgreSQLStore)
        mock_pg.fetch_signals_for_ic.side_effect = Exception("DB error")
        mock_pg_cls.return_value = mock_pg

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis_cls.return_value = mock_redis

        # Should raise exception (Celery will handle retry)
        with pytest.raises(Exception):
            run_daily_report()


class TestRunWeeklyWeights:
    """Tests for run_weekly_weights Celery task."""

    @patch("src.workers.performance.check_and_apply_weights")
    @patch("src.workers.performance.compute_purified_icir")
    @patch("src.workers.performance._fetch_all_per_model_signals_for_loo")
    @patch("src.workers.performance.RedisStore")
    @patch("src.workers.performance.TelegramNotifier")
    def test_run_weekly_weights_observational(
        self, mock_notifier_cls, mock_redis_cls, mock_fetch_cls, mock_purified_cls, mock_apply_task
    ):
        """Test weekly weights computation is observational (no auto-apply)."""
        # Per-model rows: (model_id, score, forward_return)
        mock_fetch_cls.return_value = (
            [("opus", 0.3, 0.02)] * 300 +
            [("qwen3.5:cloud", 0.2, 0.01)] * 300
        )

        # Mock compute_purified_icir to return valid ICIR values
        mock_purified_cls.return_value = {
            "opus": 1.2,
            "qwen3.5:cloud": 0.8,
        }

        # Mock Redis with proper get_ensemble_weights method and _r attribute
        mock_redis = MagicMock()
        mock_redis.get_ensemble_weights = MagicMock(return_value=None)
        mock_redis._r = MagicMock()
        mock_redis_cls.return_value = mock_redis

        # Mock Telegram with async send_alert
        mock_notifier = MagicMock()
        mock_notifier.send_alert = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        # Run task
        run_weekly_weights()

        # Verify suggestion was stored (not applied)
        mock_redis._r.setex.assert_called()
        # Check that both suggestion and snapshot keys were set
        setex_calls = mock_redis._r.setex.call_args_list
        assert any(call[0][0] == "ensemble:weights:suggestion" for call in setex_calls)
        assert any(call[0][0] == "ensemble:weights:suggestion:snapshot" for call in setex_calls)

        # Verify Telegram alert was sent
        mock_notifier.send_alert.assert_called()

        # Verify check_and_apply_weights was chained
        mock_apply_task.apply_async.assert_called_once_with(countdown=5)

    @patch("src.workers.performance._fetch_all_per_model_signals_for_loo")
    @patch("src.workers.performance.RedisStore")
    def test_run_weekly_weights_insufficient_samples(
        self, mock_redis_cls, mock_fetch_cls
    ):
        """Test weekly weights skips computation with insufficient samples."""
        # Empty per-model rows → no data → early return
        mock_fetch_cls.return_value = []

        # Mock Redis with proper structure
        mock_redis = MagicMock()
        mock_redis.get_ensemble_weights = MagicMock(return_value=None)
        mock_redis._r = MagicMock()
        mock_redis_cls.return_value = mock_redis

        # Should return early without storing suggestions
        run_weekly_weights()

        # Verify no suggestion was stored
        mock_redis._r.setex.assert_not_called()


class TestRunDriftDetection:
    """Tests for run_drift_detection Celery task."""

    @patch("src.workers.performance.PostgreSQLStore")
    @patch("src.workers.performance.RedisStore")
    @patch("src.workers.performance.TelegramNotifier")
    def test_run_drift_detection_no_drift(
        self, mock_notifier_cls, mock_redis_cls, mock_pg_cls
    ):
        """Test drift detection when no drift is present."""
        # Mock PostgreSQL - return same distribution for all periods
        mock_pg = MagicMock(spec=PostgreSQLStore)
        rows = generate_signal_rows(100, "opus", score_mean=0.0, score_std=0.5)
        mock_pg.fetch_signals_for_ic.return_value = rows

        mock_pg_cls.return_value = mock_pg

        # Mock Redis with proper structure
        mock_redis = MagicMock()
        mock_redis.get_ensemble_weights = MagicMock(return_value=None)
        mock_redis._r = MagicMock()
        mock_redis_cls.return_value = mock_redis

        # Mock Telegram with async send_alert
        mock_notifier = MagicMock()
        mock_notifier.send_alert = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        # Run task
        run_drift_detection()

        # Should not send alert when no drift detected
        mock_notifier.send_alert.assert_not_called()

    @patch("src.workers.performance.PostgreSQLStore")
    @patch("src.workers.performance.RedisStore")
    @patch("src.workers.performance.TelegramNotifier")
    def test_run_drift_detection_with_drift(
        self, mock_notifier_cls, mock_redis_cls, mock_pg_cls
    ):
        """Test drift detection sends alert when drift is present."""
        # Mock PostgreSQL - different distributions to trigger drift
        mock_pg = MagicMock(spec=PostgreSQLStore)

        # 7 days: shifted mean
        rows_7d = generate_signal_rows(50, "opus", score_mean=2.0, score_std=0.5)
        # 90 days: normal
        rows_90d = generate_signal_rows(300, "opus", score_mean=0.0, score_std=0.5)

        def fetch_side_effect(symbol, days):
            if days == 7:
                return rows_7d
            elif days == 90:
                return rows_90d
            elif days == 365:
                return rows_90d
            return []

        mock_pg.fetch_signals_for_ic.side_effect = fetch_side_effect
        mock_pg_cls.return_value = mock_pg

        # Mock Redis with proper structure
        mock_redis = MagicMock()
        mock_redis.get_ensemble_weights = MagicMock(return_value=None)
        mock_redis._r = MagicMock()
        mock_redis_cls.return_value = mock_redis

        # Mock Telegram with async send_alert
        mock_notifier = MagicMock()
        mock_notifier.send_alert = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        # Run task
        run_drift_detection()

        # Should send alert for drift
        mock_notifier.send_alert.assert_called()


class TestCheckSuggestionExpiry:
    """Tests for check_suggestion_expiry Celery task."""

    def test_logs_expired_when_suggestion_gone_and_snapshot_present(self):
        """If snapshot exists but suggestion key is gone, logs source='expired'."""
        from unittest.mock import MagicMock, patch

        snapshot = {
            "suggested_weights": {"opus": 0.45, "qwen3.5:cloud": 0.35, "deepseek-v4-pro:cloud": 0.20},
            "purified_icir": {"opus": 0.31},
            "freeze_reason": "",
            "computed_at": "2026-05-04T08:00:00+00:00",
        }

        mock_redis_client = MagicMock()
        mock_redis_client.get.side_effect = lambda key: (
            json.dumps(snapshot).encode() if key == "ensemble:weights:suggestion:snapshot"
            else None  # suggestion key is gone (expired)
        )

        mock_redis_store = MagicMock()
        mock_redis_store._r = mock_redis_client

        mock_pg = MagicMock()

        with patch("src.workers.performance.RedisStore", return_value=mock_redis_store), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg):
            from src.workers.performance import check_suggestion_expiry
            check_suggestion_expiry()

        mock_pg.log_weight_update.assert_called_once()
        call_kwargs = mock_pg.log_weight_update.call_args.kwargs
        assert call_kwargs["source"] == "expired"
        assert call_kwargs["note"] == "Suggestion expired without approval"
        mock_redis_client.delete.assert_called_once_with("ensemble:weights:suggestion:snapshot")

    def test_does_nothing_when_no_snapshot(self):
        """If no snapshot exists, task exits silently."""
        from unittest.mock import MagicMock, patch

        mock_redis_client = MagicMock()
        mock_redis_client.get.return_value = None

        mock_redis_store = MagicMock()
        mock_redis_store._r = mock_redis_client

        mock_pg = MagicMock()

        with patch("src.workers.performance.RedisStore", return_value=mock_redis_store), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg):
            from src.workers.performance import check_suggestion_expiry
            check_suggestion_expiry()

        mock_pg.log_weight_update.assert_not_called()

    def test_does_nothing_when_suggestion_still_active(self):
        """If both snapshot and suggestion exist, suggestion hasn't expired yet."""
        from unittest.mock import MagicMock, patch

        snapshot = {"suggested_weights": {}, "purified_icir": {}, "freeze_reason": "", "computed_at": "2026-05-04T08:00:00+00:00"}

        mock_redis_client = MagicMock()
        mock_redis_client.get.return_value = json.dumps(snapshot).encode()  # both keys exist

        mock_redis_store = MagicMock()
        mock_redis_store._r = mock_redis_client

        mock_pg = MagicMock()

        with patch("src.workers.performance.RedisStore", return_value=mock_redis_store), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg):
            from src.workers.performance import check_suggestion_expiry
            check_suggestion_expiry()

        mock_pg.log_weight_update.assert_not_called()

    def test_handles_corrupted_json_snapshot(self):
        """If snapshot JSON is corrupted, log error and delete snapshot without crashing."""
        mock_redis_client = MagicMock()
        mock_redis_client.get.side_effect = lambda key: (
            b"not-valid-json{{{" if key == "ensemble:weights:suggestion:snapshot"
            else None
        )

        mock_redis_store = MagicMock()
        mock_redis_store._r = mock_redis_client

        mock_pg = MagicMock()

        with patch("src.workers.performance.RedisStore", return_value=mock_redis_store), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg):
            from src.workers.performance import check_suggestion_expiry
            check_suggestion_expiry()

        # Should NOT log (corrupted data)
        mock_pg.log_weight_update.assert_not_called()
        # Should delete corrupted snapshot
        mock_redis_client.delete.assert_called_once_with("ensemble:weights:suggestion:snapshot")

    def test_handles_non_dict_snapshot(self):
        """If snapshot is not a dict, delete it without crashing."""
        mock_redis_client = MagicMock()
        mock_redis_client.get.side_effect = lambda key: (
            b"['not', 'a', 'dict']" if key == "ensemble:weights:suggestion:snapshot"
            else None
        )

        mock_redis_store = MagicMock()
        mock_redis_store._r = mock_redis_client

        mock_pg = MagicMock()

        with patch("src.workers.performance.RedisStore", return_value=mock_redis_store), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg):
            from src.workers.performance import check_suggestion_expiry
            check_suggestion_expiry()

        # Should NOT log (invalid structure)
        mock_pg.log_weight_update.assert_not_called()
        # Should delete invalid snapshot
        mock_redis_client.delete.assert_called_once_with("ensemble:weights:suggestion:snapshot")


class TestCheckAndApplyWeights:
    """Tests for check_and_apply_weights Celery task."""

    SUGGESTION = {
        "suggested_weights": {
            "opus": 0.45,
            "qwen3.5:cloud": 0.35,
            "deepseek-v4-pro:cloud": 0.20,
        },
        "purified_icir": {
            "opus": 0.31,
            "qwen3.5:cloud": 0.18,
            "deepseek-v4-pro:cloud": 0.09,
        },
        "freeze_reason": "",
        "computed_at": "2026-05-04T08:00:00+00:00",
    }
    CURRENT = {"weights": {"opus": 0.34, "qwen3.5:cloud": 0.33, "deepseek-v4-pro:cloud": 0.33}, "source": "suggestion"}

    def _make_redis(self, suggestion=None, current=None, vix_cached=None):
        mock = MagicMock()
        mock.get_weight_suggestion.return_value = suggestion if suggestion is not None else self.SUGGESTION
        mock.get_current_weights_stored.return_value = current if current is not None else self.CURRENT
        mock.get_vix_cached.return_value = vix_cached
        mock.set_vix_cached = MagicMock()
        mock.set_ensemble_weights = MagicMock()
        mock._r = MagicMock()
        return mock

    def _make_config(self, enabled=True, vix_threshold=30.0, ic_var_threshold=0.15, delta_max=0.15):
        from src.config import Config
        return Config(
            ADMIN_API_KEY="test-api-key-for-testing-only-12345678",
            DATABASE_URL="postgresql://localhost:5432/test",
            AUTO_APPLY_ENABLED=enabled,
            AUTO_APPLY_VIX_THRESHOLD=vix_threshold,
            AUTO_APPLY_IC_VARIANCE_THRESHOLD=ic_var_threshold,
            AUTO_APPLY_WEIGHT_DELTA_MAX=delta_max,
            AUTO_APPLY_VIX_REDIS_TTL_SECONDS=3600,
            AUTO_APPLY_VIX_FRED_SERIES="VIXCLS",
        )

    def test_all_guardrails_pass_applies_weights(self):
        """All guardrails pass → weights applied, log source='auto_apply', Telegram ✅."""
        redis = self._make_redis(vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_called_once_with(
            self.SUGGESTION["suggested_weights"], source="auto_apply"
        )
        pg.log_weight_update.assert_called_once()
        assert pg.log_weight_update.call_args.kwargs["source"] == "auto_apply"
        assert pg.log_weight_update.call_args.kwargs["approved_by"] == "system"
        notifier.send_alert.assert_called_once()
        assert "✅" in notifier.send_alert.call_args[0][0]

    def test_g1_disabled_exits_silently(self):
        """G1: auto_apply_enabled=False → silent exit, no log, no Telegram."""
        redis = self._make_redis(vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        cfg = self._make_config(enabled=False)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        pg.log_weight_update.assert_not_called()
        notifier.send_alert.assert_not_called()
        redis.set_ensemble_weights.assert_not_called()

    def test_g2_vix_too_high_freezes(self):
        """G2: VIX >= threshold → freeze, log source='freeze', Telegram ⚠️."""
        redis = self._make_redis(vix_cached=38.5)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        notifier.send_message_with_keyboard = AsyncMock(return_value=None)
        cfg = self._make_config(vix_threshold=30.0)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"
        assert "VIX" in pg.log_weight_update.call_args.kwargs["note"]
        assert "⚠️" in notifier.send_message_with_keyboard.call_args[0][0]

    def test_g2_fred_unavailable_freezes(self):
        """G2: FRED fetch fails → guardrail fails (fail-safe) → freeze."""
        redis = self._make_redis(vix_cached=None)  # cache miss
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        notifier.send_message_with_keyboard = AsyncMock(return_value=None)
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg), \
             patch("src.workers.performance._get_vix", return_value=None):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"

    def test_g3_ic_variance_too_high_freezes(self):
        """G3: std(purified_icir) >= threshold → freeze."""
        # Large spread across IC values → high variance
        high_var_suggestion = {
            **self.SUGGESTION,
            "purified_icir": {"opus": 2.0, "qwen3.5:cloud": 0.01, "deepseek-v4-pro:cloud": 0.01},
        }
        redis = self._make_redis(suggestion=high_var_suggestion, vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        notifier.send_message_with_keyboard = AsyncMock(return_value=None)
        cfg = self._make_config(ic_var_threshold=0.15)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"

    def test_g4_weight_delta_too_large_freezes(self):
        """G4: max weight delta >= threshold → freeze."""
        big_delta_suggestion = {
            **self.SUGGESTION,
            "suggested_weights": {
                "opus": 0.90,  # +56pp vs current 0.34
                "qwen3.5:cloud": 0.05,
                "deepseek-v4-pro:cloud": 0.05,
            },
        }
        redis = self._make_redis(suggestion=big_delta_suggestion, vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        notifier.send_message_with_keyboard = AsyncMock(return_value=None)
        cfg = self._make_config(delta_max=0.15)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"

    def test_no_suggestion_exits_silently(self):
        """No suggestion in Redis → silent exit, no log, no Telegram."""
        redis = self._make_redis(suggestion=None)
        redis.get_weight_suggestion.return_value = None
        pg = MagicMock()
        notifier = MagicMock()
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        pg.log_weight_update.assert_not_called()
        notifier.send_alert.assert_not_called()

    def test_apply_deletes_snapshot_key(self):
        """Successful apply deletes ensemble:weights:suggestion:snapshot from Redis."""
        redis = self._make_redis(vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.delete_suggestion_snapshot.assert_called_once()

    def test_g3_missing_purified_icir_freezes(self):
        """G3: empty purified_icir → freeze with 'missing' reason."""
        empty_icir_suggestion = {
            **self.SUGGESTION,
            "purified_icir": {},
        }
        redis = self._make_redis(suggestion=empty_icir_suggestion, vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        notifier.send_message_with_keyboard = AsyncMock(return_value=None)
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"
        assert "purified_icir missing" in pg.log_weight_update.call_args.kwargs["note"]


class TestBuildSignalDistribution:
    """Tests for _build_signal_distribution function."""

    def test_empty_rows_returns_empty_dict(self):
        """No recent signals → empty distribution dict."""
        mock_pg = MagicMock(spec=PostgreSQLStore)
        mock_pg.fetch_signals_last_hours.return_value = []

        result = _build_signal_distribution(mock_pg, lookback_hours=24)

        assert result == {}

    def test_groups_by_model_id(self):
        """Signals from two model_ids produce two keys in result."""
        mock_pg = MagicMock(spec=PostgreSQLStore)
        mock_pg.fetch_signals_last_hours.return_value = [
            (0.4, "ensemble:kimi+qwen"),
            (0.2, "ensemble:kimi+qwen"),
            (0.5, "deepseek:cloud"),
        ]

        result = _build_signal_distribution(mock_pg, lookback_hours=24)

        assert set(result.keys()) == {"ensemble:kimi+qwen", "deepseek:cloud"}

    def test_computes_count_and_percentiles(self):
        """Distribution stats include count, mean, median, p25, p75."""
        mock_pg = MagicMock(spec=PostgreSQLStore)
        scores = [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_pg.fetch_signals_last_hours.return_value = [(s, "m1") for s in scores]

        result = _build_signal_distribution(mock_pg, lookback_hours=24)

        stats = result["m1"]
        assert stats["count"] == 5
        assert abs(stats["mean"] - np.mean(scores)) < 1e-9
        assert abs(stats["median"] - np.median(scores)) < 1e-9
        assert abs(stats["p25"] - np.percentile(scores, 25)) < 1e-9
        assert abs(stats["p75"] - np.percentile(scores, 75)) < 1e-9

    def test_counts_above_threshold(self):
        """Signals with score > 0.3 are counted in above_threshold."""
        mock_pg = MagicMock(spec=PostgreSQLStore)
        # 2 above 0.3, 3 at or below 0.3
        scores = [0.35, 0.40, 0.10, 0.20, 0.30]
        mock_pg.fetch_signals_last_hours.return_value = [(s, "m1") for s in scores]

        result = _build_signal_distribution(mock_pg, lookback_hours=24)

        assert result["m1"]["above_threshold"] == 2

    def test_counts_near_threshold(self):
        """Signals in (0.15, 0.30] are counted in near_threshold."""
        mock_pg = MagicMock(spec=PostgreSQLStore)
        # 0.20 and 0.28 are near (0.15, 0.30]; 0.10 is below; 0.40 is above
        scores = [0.10, 0.20, 0.28, 0.40]
        mock_pg.fetch_signals_last_hours.return_value = [(s, "m1") for s in scores]

        result = _build_signal_distribution(mock_pg, lookback_hours=24)

        assert result["m1"]["near_threshold"] == 2

    def test_calls_fetch_with_correct_hours(self):
        """Passes lookback_hours to fetch_signals_last_hours."""
        mock_pg = MagicMock(spec=PostgreSQLStore)
        mock_pg.fetch_signals_last_hours.return_value = []

        _build_signal_distribution(mock_pg, lookback_hours=48)

        mock_pg.fetch_signals_last_hours.assert_called_once_with(48)


class TestFormatPerformanceTelegramMessageWithDistribution:
    """Tests that _format_performance_telegram_message includes signal distribution."""

    def _make_report(self) -> PerformanceReport:
        return PerformanceReport(
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            overall_ic=0.05,
            icir=0.4,
            hit_rate=0.52,
            model_ic={"m1": 0.05},
            model_icir={"m1": 0.4},
            recommended_weights={"m1": 1.0},
            weight_change_applied=False,
            threshold_analysis={},
            threshold_suggestion=None,
            drift_alerts=[],
            post_mortems=[],
            generated_at=datetime(2026, 5, 31, 3, 0, tzinfo=timezone.utc),
            report_version="1.0",
        )

    def test_message_includes_signal_distribution_section(self):
        """When distribution is provided, message contains Signal Distribution header."""
        report = self._make_report()
        distribution = {
            "ensemble:kimi+qwen": {
                "count": 10,
                "mean": 0.18,
                "median": 0.17,
                "p25": 0.12,
                "p75": 0.24,
                "above_threshold": 1,
                "near_threshold": 4,
            }
        }

        msg = _format_performance_telegram_message(report, soft_warnings=[], signal_distribution=distribution)

        assert "Signal Distribution" in msg
        assert "above_threshold" in msg or "above" in msg.lower()
        assert "ensemble:kimi+qwen" in msg

    def test_message_without_distribution_omits_section(self):
        """When distribution is None, Signal Distribution section is absent."""
        report = self._make_report()

        msg = _format_performance_telegram_message(report, soft_warnings=[], signal_distribution=None)

        assert "Signal Distribution" not in msg

    def test_message_backward_compat_no_distribution_kwarg(self):
        """Calling with two positional args (old API) still works."""
        report = self._make_report()

        msg = _format_performance_telegram_message(report, [])

        assert isinstance(msg, str)
        assert "Signal Distribution" not in msg
