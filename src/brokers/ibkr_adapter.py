"""Interactive Brokers adapter via ib_insync (TWS / IB Gateway).

Paper trading port: 7497 (TWS), 7496 (IB Gateway).
Live trading port:  7496 (TWS), 4001 (IB Gateway).

All methods are synchronous — call from background workers only, never
from the live trading hot-path.
"""

import logging
import time
from typing import Any

try:
    from ib_insync import IB, Stock
    _IB_INSYNC_AVAILABLE = True
except ImportError:
    IB = None  # type: ignore[assignment,misc]
    Stock = None  # type: ignore[assignment]
    _IB_INSYNC_AVAILABLE = False

from src.brokers.base import BrokerAdapter

log = logging.getLogger(__name__)

_RECONNECT_DELAY_SECONDS = 5
_CONNECT_TIMEOUT_SECONDS = 4


class IBKRConnectionError(Exception):
    """Raised when connection to IBKR TWS/Gateway fails."""


class IBKROrderNotFoundError(Exception):
    """Raised when cancel_order cannot find the requested order ID."""


class IBKRContractNotFoundError(Exception):
    """Raised when the underlying contract cannot be qualified."""


class IBKRAdapter(BrokerAdapter):
    """Broker adapter for Interactive Brokers via ib_insync.

    Supports connect/disconnect, account queries, order placement/cancellation,
    and option chain retrieval. Auto-reconnects on unexpected disconnects.

    Args:
        host:      TWS/Gateway host (default 127.0.0.1).
        port:      TWS/Gateway port (7497 = TWS paper, 7496 = Gateway).
        client_id: IBKR client ID (must be unique per simultaneous connection).
        account:   IBKR account number (e.g. 'DU123456'). Empty = primary account.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        account: str = "",
    ) -> None:
        if IB is None:
            raise ImportError(
                "ib_insync is required for IBKRAdapter. "
                "Install it with: pip install ib_insync"
            )
        self._host = host
        self._port = port
        self._client_id = client_id
        self._account = account
        self._ib = IB()
        self._ib.disconnectedEvent += self._on_disconnect

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to TWS/Gateway. Raises IBKRConnectionError on failure."""
        try:
            self._ib.connect(
                self._host,
                self._port,
                clientId=self._client_id,
                timeout=_CONNECT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise IBKRConnectionError(
                f"Failed to connect to IBKR at {self._host}:{self._port} "
                f"(clientId={self._client_id}): {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Disconnect from TWS/Gateway."""
        self._ib.disconnect()

    def _on_disconnect(self) -> None:
        """Auto-reconnect handler — registered on disconnectedEvent at init."""
        log.warning("IBKR disconnected — reconnecting in %ds", _RECONNECT_DELAY_SECONDS)
        time.sleep(_RECONNECT_DELAY_SECONDS)
        try:
            self.connect()
            log.info("IBKR reconnected successfully")
        except IBKRConnectionError as exc:
            log.error("IBKR reconnect failed: %s", exc)

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account_summary(self) -> dict[str, Any]:
        """Return account summary as {tag: value} dict.

        Tags include NetLiquidation, AvailableFunds, BuyingPower, etc.
        """
        values = self._ib.accountSummary(self._account)
        return {v.tag: v.value for v in values}

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def submit_order(self, contract: Any, order: Any) -> Any:
        """Submit order to IBKR. Returns the ib_insync Trade object."""
        return self._ib.placeOrder(contract, order)

    def cancel_order(self, order_id: int) -> None:
        """Cancel an open order by its orderId.

        Raises IBKROrderNotFoundError if no open order has that ID.
        """
        for trade in self._ib.trades():
            if trade.order.orderId == order_id:
                self._ib.cancelOrder(trade.order)
                return
        raise IBKROrderNotFoundError(
            f"No open order with ID {order_id} — already filled or unknown"
        )

    # ------------------------------------------------------------------
    # Option chain
    # ------------------------------------------------------------------

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        """Return all strikes (call + put) for symbol and expiry.

        Args:
            symbol: Underlying ticker (e.g. 'SPY').
            expiry: Expiry in YYYYMMDD format (e.g. '20241220').

        Returns:
            List of dicts: {symbol, expiry, strike, right, exchange, multiplier}.
            Empty list if no chains contain the requested expiry.

        Raises:
            IBKRContractNotFoundError: if the underlying contract cannot be qualified.
        """
        underlying = Stock(symbol, "SMART", "USD")
        qualified = self._ib.qualifyContracts(underlying)
        if not qualified:
            raise IBKRContractNotFoundError(f"No contract found for {symbol}")

        con_id = qualified[0].conId
        chains = self._ib.reqSecDefOptParams(symbol, "", "STK", con_id)

        result: list[dict[str, Any]] = []
        for chain in chains:
            if expiry not in chain.expirations:
                continue
            for strike in sorted(chain.strikes):
                for right in ("C", "P"):
                    result.append(
                        {
                            "symbol": symbol,
                            "expiry": expiry,
                            "strike": strike,
                            "right": right,
                            "exchange": chain.exchange,
                            "multiplier": chain.multiplier,
                        }
                    )
        return result
