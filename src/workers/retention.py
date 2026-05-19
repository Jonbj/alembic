"""Nightly sweep to delete old rows from news_log and llm_responses.

Runs daily at 03:30 UTC via Celery beat. Default thresholds from config/trading.yaml:
  - news_log: 180 days
  - llm_responses: 365 days
"""
import logging

import psycopg2

from src.config import config
from src.store.pg_store import PostgreSQLStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

_DEFAULT_NEWS_DAYS = 180
_DEFAULT_LLM_DAYS = 365


@app.task(name="src.workers.retention.run_retention_sweep")
def run_retention_sweep() -> dict:
    """Delete old rows from news_log and llm_responses. Returns deleted counts."""
    trading_cfg = _load_retention_config()
    news_days = trading_cfg.get("news_log_days", _DEFAULT_NEWS_DAYS)
    llm_days = trading_cfg.get("llm_responses_days", _DEFAULT_LLM_DAYS)

    pg_conn = psycopg2.connect(config.DATABASE_URL)
    pg_store = PostgreSQLStore(conn=pg_conn)
    try:
        deleted_news = pg_store.delete_old_news_log(older_than_days=news_days)
        deleted_llm = pg_store.delete_old_llm_responses(older_than_days=llm_days)
        log.info(
            "Retention sweep complete: deleted %d news_log rows (>%dd), "
            "%d llm_responses rows (>%dd)",
            deleted_news, news_days, deleted_llm, llm_days,
        )
        return {"deleted_news_log": deleted_news, "deleted_llm_responses": deleted_llm}
    finally:
        pg_store.close()


def _load_retention_config() -> dict:
    try:
        import yaml
        with open("config/trading.yaml") as f:
            return yaml.safe_load(f).get("retention", {})
    except Exception:
        return {}
