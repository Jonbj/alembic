"""Celery application configuration for LLM Trading System."""

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
}

# Auto-discover tasks in the workers package
app.autodiscover_tasks(["src.workers"])
