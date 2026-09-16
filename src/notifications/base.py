"""Notification protocol and alert severity levels.

All alerting in Alembic goes through the Notifier protocol so that the concrete
transport (Telegram, email, …) can be swapped without touching worker code.
Workers receive a Notifier instance via dependency injection and call send_alert().
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Any, Coroutine, Protocol, TypeVar, runtime_checkable

_T = TypeVar("_T")

# Quanto un alert puo' far aspettare chi lo emette prima di essere abbandonato.
# Un trasporto lento non deve mai diventare un problema del chiamante.
TIMEOUT_ALERT_SECONDI = 10.0


def esegui_sincrono(coro: "Coroutine[Any, Any, _T]", timeout: float = TIMEOUT_ALERT_SECONDI) -> _T:
    """Esegue una coroutine da codice sincrono, anche dentro un loop gia' attivo.

    `asyncio.run()` solleva RuntimeError se un loop e' gia' in esecuzione nel
    thread, e la coroutine appena costruita resta non attesa: e' cio' che il
    2026-09-14 ha silenziato l'alert del breaker di fallback, chiamato dal
    callback sincrono di RedisStore mentre la pipeline girava dentro
    `asyncio.run()` (22 timeout dell'ensemble, zero avvisi).

    Quando un loop sta girando la coroutine viene eseguita in un thread separato
    con un loop proprio, e il chiamante aspetta al massimo `timeout` secondi.
    Bloccare per un istante il loop e' preferibile a un fire-and-forget che il
    loop puo' cancellare chiudendosi: un alert che non si sa se e' partito e'
    peggio di nessun alert.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(coro, timeout))
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="alert") as pool:
        return pool.submit(asyncio.run, asyncio.wait_for(coro, timeout)).result()


class AlertLevel(str, Enum):
    """Severity level attached to every outbound alert.

    INFO     — informational, no action required (e.g. daily P&L summary)
    WARNING  — degraded state that may need attention (e.g. high fallback rate)
    CRITICAL — immediate action required (e.g. drawdown cap hit, kill-switch fired)
    """
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@runtime_checkable
class Notifier(Protocol):
    """Protocol satisfied by any alert transport (Telegram, email, …).

    Workers depend on this protocol rather than a concrete class so they remain
    testable with a simple mock and decoupled from the delivery channel.
    """

    async def send_alert(self, message: str, level: AlertLevel = AlertLevel.INFO) -> bool:
        """Send an alert and return True if delivery succeeded, False otherwise."""
        ...
