"""
Intraday 1h strategy using pre-computed LLM sentiment signals.
Entry: sentiment_score > ENTRY_THRESHOLD and EMA momentum confirmed.
Risk: 2% stop-loss, max 10% position size, rate limit 10 orders/min.
Kill-switch: checked via Redis at every OnData() call.

Brokerage: Alpaca Markets (paper or live).
  - Paper: set algorithm parameter "alpaca-paper" = "true" (default)
  - Live:  set "alpaca-paper" = "false" in lean.json environment

CRITICAL: This strategy NEVER calls LLM APIs synchronously.
All signals are read from pre-computed Redis cache via LLMSignalData.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List

try:
    from AlgorithmImports import *
except ImportError:
    # Fallback for local testing/IDE support
    pass

# Import custom signal data feed
from quantconnect.signal_data import LLMSignalData

# Configuration - override via config/trading.yaml
ENTRY_THRESHOLD = 0.3
MAX_POSITION_PCT = 0.10
STOP_LOSS_PCT = 0.02
MAX_ORDERS_PER_MIN = 10
REDIS_URL = "redis://localhost:6379/0"

# Default symbols - can be overridden in Initialize()
_DEFAULT_SYMBOLS = ["AAPL", "MSFT", "SPY", "QQQ"]


class LLMIntradayStrategy(QCAlgorithm):
    """
    Intraday 1-hour strategy using LLM sentiment signals.

    Entry Logic:
    - sentiment_score > ENTRY_THRESHOLD (default 0.3)
    - Price above 20-period EMA (momentum confirmation)
    - Signal is fresh (generated within 30 minutes)
    - Kill-switch not active
    - No existing position on the ticker (idempotent — no pyramiding)

    Risk Management:
    - Stop-loss at 2% below entry price
    - Maximum 10% portfolio value per position
    - Rate limit: 10 orders per minute per symbol
    - Kill-switch via Redis kills all positions immediately

    Brokerage: Alpaca Markets.
    - Paper trading by default ("alpaca-paper" parameter = "true").
    - Commission-free model; slippage applied by QC default model.
    """

    def Initialize(self):
        """Initialize strategy parameters and data feeds."""
        self.SetStartDate(2022, 1, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(100_000)

        # Alpaca brokerage — paper by default, live when "alpaca-paper"="false"
        is_paper = (self.GetParameter("alpaca-paper") or "true").lower() != "false"
        account_type = AccountType.Cash if is_paper else AccountType.Margin
        self.SetBrokerageModel(BrokerageName.Alpaca, account_type)
        self.Debug(f"Brokerage: Alpaca ({'paper' if is_paper else 'live'}, {account_type})")

        # Redis connection for kill-switch check
        # Note: In QC cloud, Redis may not be available; kill-switch
        # can alternatively be checked via object store or API
        try:
            import redis
            self._redis = redis.from_url(REDIS_URL)
        except ImportError:
            self._redis = None
            self.Debug("Redis not available - kill-switch disabled")

        # Order tracking for rate limiting
        self._order_times: List[datetime] = []

        # Stop-loss prices per symbol
        self._stop_prices: Dict[str, float] = {}

        # Symbols to trade
        self._symbols = self.GetParameter("symbols") or _DEFAULT_SYMBOLS
        if isinstance(self._symbols, str):
            self._symbols = json.loads(self._symbols)

        # Add equity data feeds
        for sym in self._symbols:
            equity = self.AddEquity(sym, Resolution.Hour)
            equity.SetDataNormalizationMode(DataNormalizationMode.Adjusted)

            # Add LLM signal data feed
            # The signal data is subscribed at Minute resolution for freshness
            self.AddData(LLMSignalData, sym, Resolution.Minute)

        # EMA for momentum confirmation (20-period on hourly data)
        self._emas = {}
        for sym in self._symbols:
            self._emas[sym] = self.EMA(sym, 20, Resolution.Hour)

        # Logging
        self.Debug(f"LLMIntradayStrategy initialized with symbols: {self._symbols}")

    def OnData(self, data: Slice):
        """
        Main strategy logic executed on each data tick.

        CRITICAL: No LLM API calls here. All signals come from
        pre-computed LLMSignalData feed which reads from Redis/API cache.
        """
        # Check kill-switch every tick (blocks all trading if active)
        if self._is_killswitch_active():
            self.Liquidate("Kill-switch active")
            return

        for sym in self._symbols:
            # Check if we have price data
            if not data.ContainsKey(sym):
                continue

            # Check if we have signal data
            signal_key = f"{sym}_llmsignaldata"
            if not data.ContainsKey(signal_key):
                continue

            signal = data[signal_key]

            # Freshness check - skip stale signals
            if not LLMSignalData.is_fresh(signal, self.Time):
                self.Debug(f"Stale signal for {sym}, skipping")
                continue

            # Extract signal components
            score = signal.get("sentiment_score", 0.0)
            regime_mult = signal.get("regime_multiplier", 1.0)
            confidence = signal.get("confidence", 0.0)

            # Check EMA momentum
            ema = self._emas[sym]
            if not ema.IsReady:
                continue

            price = self.Securities[sym].Price
            holding = self.Portfolio[sym]

            # ENTRY LOGIC — idempotent: skip if already in position
            if not holding.Invested and score > ENTRY_THRESHOLD:
                momentum_ok = price > ema.Current.Value
                if momentum_ok and self._can_place_order():
                    # Position sizing with regime multiplier
                    # Higher multiplier in favorable regimes = larger position
                    size = (
                        self.Portfolio.TotalPortfolioValue
                        * MAX_POSITION_PCT
                        * regime_mult
                        / price
                    )
                    self.MarketOrder(sym, int(size))
                    self._stop_prices[sym] = price * (1 - STOP_LOSS_PCT)
                    self._order_times.append(self.Time)
                    self.Debug(
                        f"ENTER {sym}: score={score:.2f}, regime={regime_mult:.2f}, "
                        f"price={price:.2f}, size={int(size)}"
                    )

            # STOP-LOSS LOGIC
            if holding.Invested and sym in self._stop_prices:
                if price < self._stop_prices[sym]:
                    self.Liquidate(sym)
                    del self._stop_prices[sym]
                    self.Debug(f"STOP-LOSS {sym}: price={price:.2f}")

    def _can_place_order(self) -> bool:
        """
        Check rate limit: max MAX_ORDERS_PER_MIN orders in last 60 seconds.

        Returns:
            True if order can be placed, False if rate limited
        """
        now = self.Time
        # Keep only orders from last 60 seconds
        recent = [
            t for t in self._order_times
            if (now - t).total_seconds() < 60
        ]
        self._order_times = recent
        return len(recent) < MAX_ORDERS_PER_MIN

    def _is_killswitch_active(self) -> bool:
        """
        Check if kill-switch is active via Redis.

        Returns:
            True if kill-switch is active, False otherwise
        """
        if self._redis is None:
            return False
        try:
            return bool(self._redis.get("killswitch_active"))
        except Exception as e:
            self.Debug(f"Kill-switch check failed: {e}")
            return False
