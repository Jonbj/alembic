from enum import Enum
from typing import Protocol, runtime_checkable


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@runtime_checkable
class Notifier(Protocol):
    async def send_alert(self, message: str, level: AlertLevel = AlertLevel.INFO) -> bool: ...
