"""Celery application configuration for LLM Trading System.

Creates the `app` Celery instance used by all workers. Beat schedule:

    sentiment-worker          every 15 min, Mon-Fri 14:00-21:00 UTC
    performance-daily         daily 03:00 UTC
    performance-weekly        Monday 04:00 UTC
    drift-detection           Sunday 04:30 UTC
    check-suggestion-expiry   daily 05:00 UTC
    regime-detector           daily Mon-Fri 07:00 UTC
    poll-telegram-updates     every 5 seconds (always active)

To run workers:
    celery -A src.workers.celery_app worker --loglevel=info
    celery -A src.workers.celery_app beat   --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from src.config import config

# Create Celery app
app = Celery(
    "trading",
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
)

# Configure Celery
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minute timeout per task
    task_soft_time_limit=240,  # Soft timeout at 4 minutes
)

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    # Sentiment Worker every 15 min during market hours (Mon-Fri 14:00-21:00 UTC = 9am-4pm ET)
    "sentiment-worker": {
        "task": "src.workers.sentiment.run_sentiment_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
    # Performance daily report at 03:00 UTC
    "performance-daily": {
        "task": "src.workers.performance.run_daily_report",
        "schedule": crontab(hour=3, minute=0),
    },
    # Performance weekly weight suggestion on Mondays at 04:00 UTC
    "performance-weekly": {
        "task": "src.workers.performance.run_weekly_weights",
        "schedule": crontab(hour=4, minute=0, day_of_week=1),
    },
    # Drift detection every Sunday at 04:30 UTC
    "drift-detection": {
        "task": "src.workers.performance.run_drift_detection",
        "schedule": crontab(hour=4, minute=30, day_of_week=0),
    },
    # Check suggestion expiry daily at 05:00 UTC
    "check-suggestion-expiry": {
        "task": "src.workers.performance.check_suggestion_expiry",
        "schedule": crontab(hour=5, minute=0),
    },
    # Regime detection daily at 07:00 UTC Mon-Fri (pre-market US)
    "regime-detector": {
        "task": "src.workers.regime.detect_regime",
        "schedule": crontab(hour=7, minute=0, day_of_week="1-5"),
    },
    # News ingestion every 15 min Mon-Fri during market hours (14:00-21:00 UTC).
    # This task queries GDELT GKG, extracts tickers via PostgreSQL lookup, and
    # pushes annotated NewsItems to the Redis news:queue for the SentimentWorker.
    # The schedule aligns with the sentiment-worker to ensure the queue is
    # consistently fed.
    "run-news-ingestion": {
        "task": "src.workers.ingestion.run_news_ingestion_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
    # Telegram poller every 5 seconds for inline keyboard approval flow
    "poll-telegram-updates": {
        "task": "src.workers.telegram_poller.poll_telegram_updates",
        "schedule": 5.0,  # 5 seconds
    },
}

# Auto-discover tasks in the workers package
app.autodiscover_tasks(["src.workers"])
