"""Shared market-clock helper for Celery task gating.

Celery beat uses hardcoded UTC crontabs; US equity market hours shift with DST
and have early closes. Tasks that should only run when the market is open can
query Alpaca's clock via this helper and exit early when closed.
"""
from __future__ import annotations

import logging

from alpaca.trading.client import TradingClient

from src.config import config

log = logging.getLogger(__name__)


def is_market_open() -> bool:
    """Return True if Alpaca reports the US equity market is currently open.

    Fail-closed: if the clock cannot be fetched (network outage, missing
    credentials, Alpaca error) we treat the market as closed.
    """
    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — cannot verify market hours")
        return False

    try:
        client = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        clock = client.get_clock()
        return bool(clock.is_open)
    except Exception as exc:
        log.error("Could not fetch Alpaca market clock: %s — fail-closed", exc)
        return False
