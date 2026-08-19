"""FIX-01/FIX-02 (docs/FUNCTIONAL_REVIEW_2026-07-03.md): MarketAux and RSS are
net-negative sources and must be out of the beat schedule, with their Celery
tasks env-gated like Finnhub/SEC EDGAR."""

import os
from unittest.mock import patch


def test_marketaux_not_in_beat_schedule():
    from src.workers.celery_app import app
    assert "run-marketaux-ingestion" not in app.conf.beat_schedule


def test_rss_not_in_beat_schedule():
    from src.workers.celery_app import app
    assert "run-rss-ingestion" not in app.conf.beat_schedule


def test_marketaux_task_skips_when_disabled():
    from src.workers.ingestion import run_marketaux_ingestion_worker
    with patch.dict(os.environ, {"MARKETAUX_INGESTION_ENABLED": "0"}):
        result = run_marketaux_ingestion_worker()
    assert result.get("skipped") is True


def test_rss_task_skips_when_disabled():
    from src.workers.ingestion import run_rss_ingestion_worker
    with patch.dict(os.environ, {"RSS_INGESTION_ENABLED": "0"}):
        result = run_rss_ingestion_worker()
    assert result.get("skipped") is True


def test_marketaux_task_skips_by_default():
    """Default (env var absent) must be OFF — fail-closed."""
    env = {k: v for k, v in os.environ.items() if k != "MARKETAUX_INGESTION_ENABLED"}
    with patch.dict(os.environ, env, clear=True):
        from src.workers.ingestion import run_marketaux_ingestion_worker
        result = run_marketaux_ingestion_worker()
    assert result.get("skipped") is True


def test_reconcile_fills_evening_points_to_reconcile_task():
    """B20: the evening entry must run fill reconciliation, not the daily report."""
    from src.workers.celery_app import app
    entry = app.conf.beat_schedule["reconcile-fills-evening"]
    assert entry["task"] == "src.workers.performance.run_reconcile_fills_intraday"


def test_reconcile_positions_eod_beat_entry():
    """spec §2: EOD position reconciliation beat entry at 21:35 UTC Mon-Fri,
    pointing at the new run_reconcile_positions task."""
    from src.workers.celery_app import app
    entry = app.conf.beat_schedule["reconcile-positions-eod"]
    assert entry["task"] == "src.workers.performance.run_reconcile_positions"
