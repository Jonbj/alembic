"""Shared market-clock helper for Celery task gating.

Celery beat uses hardcoded UTC crontabs; US equity market hours shift with DST
and have early closes. Tasks that should only run when the market is open can
query Alpaca's clock via this helper and exit early when closed.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient

from src.config import config

log = logging.getLogger(__name__)

_MARKET_TIMEZONE = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)


def is_regular_session_time(moment: datetime) -> bool:
    """True se `moment` cade nella regular session US (09:30-16:00 New York).

    Serve dove `is_market_open()` non puo' servire: classificare **a posteriori**
    un istante gia' passato, senza interrogare Alpaca retroattivamente per ogni
    riga (#432). Un naive e' letto come UTC, la stessa convenzione di
    `_is_stale_news` e `build_stale_drop_row` — altrimenti la stessa riga
    avrebbe due sedute a seconda di chi la guarda.

    La conversione passa da `ZoneInfo`, quindi EDT/EST sono gestiti dal fuso:
    la finestra e' 13:30-20:00Z in ora legale e 14:30-21:00Z in ora solare.
    Ricopiare la crontab `14-21` di `celery_app.py` sbaglierebbe di un'ora per
    meta' anno — ed e' la reimplementazione di regola che #169/#467 vietano.

    **Cosa non modella:** festivita' di borsa e chiusure anticipate. Ricostruirle
    richiederebbe il calendario Alpaca per ogni riga storica. La scelta e'
    fail-closed *verso l'allerta*: un istante di festivita' risulta in-seduta,
    quindi resta nel gruppo che concorre alla soglia. L'errore possibile e' un
    falso allarme, mai un guasto scusato per errore.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(_MARKET_TIMEZONE)
    if local.weekday() >= 5:
        return False
    return _REGULAR_OPEN <= local.time() < _REGULAR_CLOSE


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
