"""Paper-trading validation metrics endpoint (point 3).

GET /api/validation/metrics?days=N — deployment %, turnover, churn, realized net PnL,
exit breakdown and current regime multiplier for monitoring the controlled-paper run.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key
from src.analytics.paper_validation import compute_validation_metrics

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/validation", dependencies=[Depends(require_api_key)])


def _current_regime_mult() -> float | None:
    """Regime multiplier actually in effect (regime:current), or None if unavailable."""
    try:
        from redis import Redis
        from src.config import config
        r = Redis.from_url(config.REDIS_URL, decode_responses=True)
        try:
            raw = r.get("regime:current")
        finally:
            r.close()
        if raw:
            return float(json.loads(raw)["multiplier"])
    except Exception as exc:
        log.debug("validation: regime read failed: %s", exc)
    return None


def _account_nav() -> float | None:
    """Live paper account equity (NAV), or None if the broker read fails (fail-soft)."""
    try:
        from alpaca.trading.client import TradingClient
        from src.config import config
        tc = TradingClient(
            config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=config.ALPACA_PAPER_MODE
        )
        return float(tc.get_account().equity)
    except Exception as exc:
        log.debug("validation: nav read failed: %s", exc)
        return None


@router.get("/metrics")
def get_validation_metrics(days: int = 7) -> dict:
    """Paper-validation metrics over the last ``days``.

    Deployment % uses live NAV; falls back to null fields if the broker/Redis are
    unavailable (never errors). Read-only.
    """
    from src.store.pg_store import PostgreSQLStore

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    trades: list[dict] = []
    try:
        with PostgreSQLStore() as store:
            rows = store.fetch_trades(status="all", limit=1000)
        trades = [t for t in rows if t.get("entry_time") and t["entry_time"] >= cutoff]
    except Exception as exc:
        log.warning("validation metrics: trade fetch failed: %s", exc)

    return compute_validation_metrics(
        trades,
        nav=_account_nav(),
        regime_mult=_current_regime_mult(),
        window_days=days,
    )
