"""Notification protocol and alert severity levels.

All alerting in Alembic goes through the Notifier protocol so that the concrete
transport (Telegram, email, …) can be swapped without touching worker code.
Workers receive a Notifier instance via dependency injection and call send_alert().
"""
from enum import Enum
from typing import Protocol, runtime_checkable


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
