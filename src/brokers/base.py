"""Broker adapter abstract base class."""

from abc import ABC, abstractmethod
from typing import Any


class BrokerAdapter(ABC):
    """Abstract base for broker adapters.

    Implementations must never be called synchronously in the hot trading path —
    all broker interactions happen in background workers.
    """

    @abstractmethod
    def connect(self) -> None:
        """Open connection to the broker."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the broker connection."""
        ...

    @abstractmethod
    def get_account_summary(self) -> dict[str, Any]:
        """Return account state as {tag: value} dict."""
        ...

    @abstractmethod
    def submit_order(self, contract: Any, order: Any) -> Any:
        """Submit an order and return the broker's trade/order object."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: int) -> None:
        """Cancel an open order by its broker-assigned ID."""
        ...

    @abstractmethod
    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        """Return option chain for symbol and expiry (YYYYMMDD).

        Each entry: {symbol, expiry, strike, right, exchange, multiplier}.
        """
        ...
