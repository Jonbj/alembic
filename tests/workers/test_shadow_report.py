"""Auto-report task: no-op before 7 days; report+disarm after."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.workers.performance import run_shadow_comparison_report


def _run(started_at: str | None):
    redis = MagicMock()
    redis.get_shadow_comparison_start.return_value = started_at
    pg = MagicMock()
    pg.fetch_shadow_rows.return_value = []
    pg.fetch_live_response_rows.return_value = []
    with patch("src.workers.performance.RedisStore", return_value=redis), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("src.workers.performance.TelegramNotifier") as tn, \
         patch("src.workers.performance.run_async"):
        result = run_shadow_comparison_report()
    return result, redis, tn


def test_noop_when_not_armed():
    result, redis, tn = _run(None)
    assert result["skipped"] is True
    tn.assert_not_called()


def test_noop_before_seven_days():
    ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    result, redis, tn = _run(ts)
    assert result["skipped"] is True
    redis.clear_shadow_comparison_start.assert_not_called()


def test_report_and_disarm_after_seven_days():
    ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    result, redis, tn = _run(ts)
    assert result.get("reported") is True
    tn.assert_called_once()
    redis.clear_shadow_comparison_start.assert_called_once()
