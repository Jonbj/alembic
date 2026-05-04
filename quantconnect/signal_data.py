"""
QuantConnect Lean PythonData custom feed for LLM signals.
Lives in the quantconnect/ directory; QC imports it at algorithm init.
Reads live signals from http://localhost:8000/api/signals/{symbol}
Reads historical signals from http://localhost:8000/api/signals/history?symbol=...&date=...
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict

# AlgorithmImports is provided by QC runtime at execution time
try:
    from AlgorithmImports import *
except ImportError:
    # Fallback for local testing/IDE support
    pass

SIGNAL_API_BASE = "http://localhost:8000"
SIGNAL_MAX_AGE_MIN = 30  # ignore signal if older than 2x worker interval


class LLMSignalData:
    """
    Custom PythonData feed for QuantConnect Lean.
    Reads pre-computed LLM sentiment signals from local API/Redis.

    Signal format expected from API:
    {
        "score": 0.45,
        "confidence": 0.85,
        "regime_multiplier": 1.0,
        "fallback_used": false,
        "generated_at": "2026-05-04T10:30:00Z"
    }
    """

    def __init__(self):
        self.Symbol = None
        self.Time = None
        self.Value = 0.0
        self._data: Dict[str, Any] = {}

    def GetSource(self, config, date, isLive):
        """
        Returns the data source URL for the signal feed.

        Args:
            config: Subscription configuration with Symbol
            date: The date being requested
            isLive: Whether this is live trading mode

        Returns:
            SubscriptionDataSource for REST API endpoint (or URL string in testing)
        """
        symbol = config.Symbol.Value
        if isLive:
            url = f"{SIGNAL_API_BASE}/api/signals/{symbol}"
        else:
            url = f"{SIGNAL_API_BASE}/api/signals/history?symbol={symbol}&date={date:%Y-%m-%d}"

        # In QC runtime, SubscriptionDataSource is available via AlgorithmImports
        # In testing/local mode, return URL string directly
        try:
            return SubscriptionDataSource(url, SubscriptionTransportMedium.Rest)
        except NameError:
            # Testing mode - return URL string for verification
            return url

    def Reader(self, config, line, date, isLive):
        """
        Parses JSON signal data from API response.

        Args:
            config: Subscription configuration
            line: JSON line from API response
            date: The date being processed
            isLive: Whether in live trading mode

        Returns:
            LLMSignalData instance or None if parsing fails
        """
        if not line.strip():
            return None

        try:
            data = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            return None

        signal = LLMSignalData()
        signal.Symbol = config.Symbol
        signal.Time = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
        signal.Value = float(data.get("score", 0.0))
        signal._data = {
            "sentiment_score": float(data.get("score", 0.0)),
            "regime_multiplier": float(data.get("regime_multiplier", 1.0)),
            "confidence": float(data.get("confidence", 0.0)),
            "fallback_used": bool(data.get("fallback_used", False)),
            "generated_at": data.get("generated_at", ""),
        }
        return signal

    def __getitem__(self, key: str) -> Any:
        """Access signal data fields by key."""
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Safely access signal data fields."""
        return self._data.get(key, default)

    @staticmethod
    def is_fresh(signal: "LLMSignalData", algorithm_time: datetime) -> bool:
        """
        Check if signal is fresh enough to use.

        Args:
            signal: The LLMSignalData instance to check
            algorithm_time: Current algorithm time

        Returns:
            True if signal age <= SIGNAL_MAX_AGE_MIN
        """
        try:
            gen_at_str = signal.get("generated_at", "")
            if not gen_at_str:
                return False
            gen_at = datetime.fromisoformat(gen_at_str.replace("Z", "+00:00"))
            # Handle timezone-naive algorithm_time
            if algorithm_time.tzinfo is None:
                algorithm_time = algorithm_time.replace(tzinfo=timezone.utc)
            age_min = (algorithm_time - gen_at).total_seconds() / 60
            return age_min <= SIGNAL_MAX_AGE_MIN
        except (KeyError, ValueError, TypeError, AttributeError):
            return False
