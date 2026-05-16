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
    # GDELT GKG ingestion every 15 min Mon-Fri during market hours (14:00-21:00 UTC).
    # Queries GDELT GKG, extracts tickers via PostgreSQL lookup, and pushes
    # annotated NewsItems to news:queue for the SentimentWorker.
    "run-news-ingestion": {
        "task": "src.workers.ingestion.run_news_ingestion_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
    # MarketAux ingestion every 15 min Mon-Fri during market hours.
    # 28 calls/market session — well within the 100 req/day free-tier limit.
    # Pushes MarketAuxNewsItems (with pre-computed sentiment) to news:queue.
    # The SentimentWorker skips articles with |sentiment| < 0.2 before LLM.
    "run-marketaux-ingestion": {
        "task": "src.workers.ingestion.run_marketaux_ingestion_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
    # Alpaca/Benzinga news ingestion every 15 min Mon-Fri during market hours.
    # Zero marginal cost — reuses the same Alpaca broker credentials.
    # Benzinga is a premium financial news source with full article text.
    "run-alpaca-ingestion": {
        "task": "src.workers.ingestion.run_alpaca_ingestion_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
    # Execution worker every 15 min Mon-Fri during market hours.
    # Reads LLM signals from Redis and places orders via Alpaca paper/live.
    "run-execution": {
        "task": "src.workers.execution.run_execution_worker",
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
