"""Celery application configuration for LLM Trading System.

Creates the `app` Celery instance used by all workers. Beat schedule:

    sentiment-worker          every 15 min, Mon-Fri 14:00-21:00 UTC
    performance-daily         daily 03:00 UTC
    performance-weekly        Monday 04:00 UTC
    drift-detection           Sunday 04:30 UTC
    check-suggestion-expiry   daily 05:00 UTC
    regime-detector           daily Mon-Fri 07:00 UTC
    poll-telegram-updates     every 5 seconds (always active)
    decay-monitor             daily 21:00 UTC (paper trading phase; revert to 1st-of-month post-live)

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
    include=[
        "src.workers.execution",
        "src.workers.ingestion",
        "src.workers.news_stream",
        "src.workers.performance",
        "src.workers.regime",
        "src.workers.retention",
        "src.workers.risk_monitor_task",
        "src.workers.portfolio_scheduler",
        "src.workers.decay_monitor_task",
        "src.workers.sentiment",
        "src.workers.telegram_poller",
        "src.workers.pead_worker",
    ],
)

# Configure Celery
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=660,  # 11 minutes — 4 articles × 90s Ollama + 43s FinBERT warmup + margin
    task_soft_time_limit=600,  # 10 minutes soft limit
)

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    # Sentiment Worker every 15 min during market hours (Mon-Fri 14:00-21:00 UTC = 9am-4pm ET)
    "sentiment-worker": {
        "task": "src.workers.sentiment.run_sentiment_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
    # Forward return worker at 22:00 UTC daily (after US market close).
    # Populates sentiment_signals.forward_return needed for IC / ICIR.
    "forward-return-worker": {
        "task": "src.workers.performance.run_forward_return_worker",
        "schedule": crontab(hour=22, minute=0),
    },
    # P0-E: Reconcile fill prices same evening (21:30 UTC = ~1h after NYSE close).
    # run_daily_report at 03:00 UTC already calls reconcile_trade_fills, but trades
    # placed today stay NULL overnight without this earlier reconciliation pass.
    "reconcile-fills-evening": {
        "task": "src.workers.performance.run_daily_report",
        "schedule": crontab(hour=21, minute=30, day_of_week="1-5"),
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
    # SEC EDGAR filings every 30 min during market hours.
    # 8-K filings = earnings, M&A, guidance revision — high signal/noise ratio.
    # Public API, zero cost. Filters by WATCHLIST_SYMBOLS.
    "run-sec-edgar-ingestion": {
        "task": "src.workers.ingestion.run_sec_edgar_ingestion_worker",
        "schedule": crontab(minute="*/30", hour="14-21", day_of_week="1-5"),
    },
    # RSS news ingestion every 15 min during market hours.
    # Reuters + CNBC. Lower latency than REST polling (~2-5 min vs 15 min).
    # Uses watchlist ticker mention extraction (regex, no NLP).
    "run-rss-ingestion": {
        "task": "src.workers.ingestion.run_rss_ingestion_worker",
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
    # Nightly retention sweep at 03:30 UTC
    "run-retention-sweep": {
        "task": "src.workers.retention.run_retention_sweep",
        "schedule": crontab(hour=3, minute=30),
    },
    # Portfolio orchestration cycle every 15 min, offset +7 min after sentiment start.
    # Sentiment fires at :00/:15/:30/:45 and takes 3-5 min; portfolio at :07/:22/:37/:52
    # ensures it reads the freshly written signals, not the previous cycle's.
    "portfolio-cycle": {
        "task": "src.workers.portfolio_scheduler.run_portfolio_cycle",
        "schedule": crontab(minute="7,22,37,52", hour="14-21", day_of_week="1-5"),
    },
    # Decay monitor: daily at 21:00 UTC (market close + buffer) for paper trading validation.
    # Change back to crontab(minute=0, hour=23, day_of_month="1") after paper trading phase.
    "decay-monitor": {
        "task": "src.workers.decay_monitor_task.run_decay_check",
        "schedule": crontab(hour=21, minute=0),
    },
    # Risk monitor daily at 22:30 UTC (after forward-return worker at 22:00)
    "risk-monitor": {
        "task": "src.workers.risk_monitor_task.compute_risk_report",
        "schedule": crontab(hour=22, minute=30),
    },
    # Loss feedback check every 30 min during market hours (Mon-Fri 14:00-21:00 UTC).
    # Detects N consecutive losses or negative rolling P&L → raises ENTRY_THRESHOLD,
    # reduces regime scale, sends Telegram alert. Respects 4h cooldown internally.
    "loss-feedback-check": {
        "task": "src.workers.performance.run_loss_feedback_check",
        "schedule": crontab(minute="*/30", hour="14-21", day_of_week="1-5"),
    },
    # Counterfactual worker at 22:45 UTC daily (after risk monitor at 22:30).
    # Computes 1-hour forward return for SKIP_EMA and SKIP_CAP decisions.
    "counterfactual-worker": {
        "task": "src.workers.performance.run_counterfactual_worker",
        "schedule": crontab(hour=22, minute=45),
    },
    # S7 PEAD: classify 8-K filings every 30 min during market hours.
    # Offset by 5 min from SEC EDGAR ingestion (:00/:30) to ensure filings
    # are already in EDGAR before we classify them.
    "pead-ingestion": {
        "task": "src.workers.pead_worker.run_pead_ingestion_worker",
        "schedule": crontab(minute="5,35", hour="14-21", day_of_week="1-5"),
    },
}

