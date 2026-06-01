"""Option chain ingestion and synthetic data generation via Black-Scholes.

Primary mode (backtesting): generates synthetic SPY option chains using
historical price data + Black-Scholes pricing. No live connection required.

Secondary mode (live): ingests real option chains from IBKRAdapter and
stores them to the option_chains Postgres table.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from src.options.pricing import black_scholes_price, compute_greeks  # noqa: F401

if TYPE_CHECKING:
    import psycopg2.extensions

log = logging.getLogger(__name__)

_RISK_FREE_RATE_DEFAULT = 0.05
_BASE_IV_DEFAULT = 0.18
_MULTIPLIER = 100


# ---------------------------------------------------------------------------
# Volatility surface (simple negative skew for SPY)
# ---------------------------------------------------------------------------

def _vol_surface(atm_iv: float, S: float, K: float) -> float:
    """Return IV for strike K given underlying S and ATM vol.

    Implements a simple negative skew: OTM puts have higher IV (typical for
    equity indices). Formula: IV = atm_iv - skew_slope * ln(K/S)
    where a positive d(K/S) (OTM call) → slightly higher IV,
    and a negative d(K/S) (OTM put) → higher IV.
    """
    log_moneyness = math.log(K / S)
    # Negative slope: OTM puts (log_moneyness < 0) get higher IV
    skew = -0.10 * log_moneyness
    return max(atm_iv + skew, 0.05)


# ---------------------------------------------------------------------------
# Standard expiry calendar (3rd Friday of each month)
# ---------------------------------------------------------------------------

def _third_friday(year: int, month: int) -> date:
    """Return the 3rd Friday of year/month."""
    first = date(year, month, 1)
    # Find first Friday
    days_until_friday = (4 - first.weekday()) % 7
    first_friday = first + timedelta(days=days_until_friday)
    return first_friday + timedelta(weeks=2)


def _generate_expiries(trade_date: date, num_expiries: int = 3) -> list[date]:
    """Return next num_expiries monthly option expiries (3rd Friday) after trade_date."""
    expiries: list[date] = []
    year, month = trade_date.year, trade_date.month
    while len(expiries) < num_expiries:
        tf = _third_friday(year, month)
        if tf > trade_date:
            expiries.append(tf)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return expiries


# ---------------------------------------------------------------------------
# OptionChainDataLoader
# ---------------------------------------------------------------------------

class OptionChainDataLoader:
    """Generate synthetic SPY option chains using Black-Scholes pricing.

    Primary mode: generates realistic chains from historical underlying prices
    (via DataLoader or an externally supplied price series). No live connection.

    Args:
        data_loader: Optional DataLoader for fetching underlying prices from
                     cache/yfinance. If None, underlying_price must be supplied
                     explicitly to generate_chain().
        risk_free_rate: Continuously compounded risk-free rate.
        base_iv:        ATM implied volatility assumption.
    """

    def __init__(
        self,
        data_loader: Any | None = None,
        risk_free_rate: float = _RISK_FREE_RATE_DEFAULT,
        base_iv: float = _BASE_IV_DEFAULT,
    ) -> None:
        self._data_loader = data_loader
        self._r = risk_free_rate
        self._base_iv = base_iv

    # ------------------------------------------------------------------
    # Strike grid helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strike_grid(S: float) -> list[float]:
        """Return sorted strike list for underlying price S.

        For SPY: $1 intervals from ATM-10% to ATM+10%, rounded to nearest $1.
        """
        atm = round(S)
        step = 1.0
        n_steps = max(10, int(S * 0.10 / step))  # ±10% of underlying
        strikes = [
            round(atm + i * step, 2)
            for i in range(-n_steps, n_steps + 1)
            if atm + i * step > 0
        ]
        return sorted(set(strikes))

    # ------------------------------------------------------------------
    # Volume / OI helpers (realistic synthetic values)
    # ------------------------------------------------------------------

    @staticmethod
    def _synthetic_volume(S: float, K: float, rng: np.random.Generator) -> int:
        """Volume highest near ATM, decaying as |K-S| increases."""
        moneyness_dist = abs(K - S) / S
        base = max(1, int(50_000 * math.exp(-20 * moneyness_dist)))
        return int(rng.integers(max(1, base // 2), max(2, base * 2)))

    @staticmethod
    def _synthetic_oi(volume: int, rng: np.random.Generator) -> int:
        """Open interest ≈ 5–50× volume."""
        multiplier = rng.integers(5, 50)
        return int(volume * multiplier)

    # ------------------------------------------------------------------
    # Bid/ask spread helper
    # ------------------------------------------------------------------

    @staticmethod
    def _bid_ask(mid: float) -> tuple[float, float]:
        """Compute bid/ask around mid with realistic spread."""
        if mid < 0.50:
            half_spread = 0.05
        elif mid < 2.0:
            half_spread = 0.10
        elif mid < 10.0:
            half_spread = max(0.05, mid * 0.015)
        else:
            half_spread = max(0.10, mid * 0.02)
        bid = max(0.01, round(mid - half_spread, 2))
        ask = round(mid + half_spread, 2)
        return bid, ask

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_chain(
        self,
        symbol: str,
        trade_date: date,
        expiry: date,
        underlying_price: float | None = None,
    ) -> pd.DataFrame:
        """Generate a synthetic option chain for one (trade_date, expiry) pair.

        Args:
            symbol:           Underlying ticker (e.g. 'SPY').
            trade_date:       Date for which the chain is generated (EOD snapshot).
            expiry:           Option expiry date.
            underlying_price: Underlying close price on trade_date.
                              If None, fetched via self._data_loader.

        Returns:
            DataFrame with columns matching the option_chains table schema.
        """
        S = underlying_price if underlying_price is not None else self._fetch_price(symbol, trade_date)
        T = max((expiry - trade_date).days / 365.0, 0.0)
        strikes = self._strike_grid(S)
        rng = np.random.default_rng(int(trade_date.toordinal()) ^ hash(symbol) & 0xFFFFFFFF)

        rows: list[dict[str, Any]] = []
        for K in strikes:
            iv = _vol_surface(self._base_iv, S, K)
            for right in ("C", "P"):
                mid = black_scholes_price(S, K, T, self._r, iv, right)
                greeks = compute_greeks(S, K, T, self._r, iv, right)
                bid, ask = self._bid_ask(mid)
                vol = self._synthetic_volume(S, K, rng)
                oi = self._synthetic_oi(vol, rng)
                rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "expiry": expiry,
                        "strike": K,
                        "right": right,
                        "bid": bid,
                        "ask": ask,
                        "mid": round((bid + ask) / 2, 4),
                        "volume": vol,
                        "open_interest": oi,
                        "implied_vol": iv,
                        "delta": greeks["delta"],
                        "gamma": greeks["gamma"],
                        "theta": greeks["theta"],
                        "vega": greeks["vega"],
                        "underlying_price": S,
                        "multiplier": _MULTIPLIER,
                        "source": "synthetic",
                    }
                )

        return pd.DataFrame(rows)

    def generate_chains(
        self,
        symbol: str,
        start: date,
        end: date,
        num_expiries: int = 3,
        underlying_prices: pd.Series | None = None,
    ) -> pd.DataFrame:
        """Generate synthetic chains for all business days in [start, end].

        Args:
            symbol:            Underlying ticker.
            start:             First business day (inclusive).
            end:               Last business day (inclusive).
            num_expiries:      Number of monthly expirations per day.
            underlying_prices: Optional pre-loaded price series (DatetimeIndex →
                               float). If None, loaded via self._data_loader.

        Returns:
            Concatenated DataFrame of all chains.
        """
        bdays = pd.bdate_range(start.isoformat(), end.isoformat())
        if underlying_prices is None:
            if self._data_loader is None:
                raise RuntimeError(
                    "Either underlying_prices or a DataLoader must be provided."
                )
            df_prices = self._data_loader.download(symbol, start, end)
            price_series = df_prices["Adj Close"]
        else:
            price_series = underlying_prices

        frames: list[pd.DataFrame] = []
        for ts in bdays:
            trade_date_obj = ts.date()
            S = _lookup_price(price_series, ts)
            if S is None or math.isnan(S):
                log.debug("No price for %s on %s — skipping", symbol, trade_date_obj)
                continue
            expiries = _generate_expiries(trade_date_obj, num_expiries)
            for expiry in expiries:
                df = self.generate_chain(symbol, trade_date_obj, expiry, underlying_price=S)
                frames.append(df)

        if not frames:
            return pd.DataFrame(columns=list(_REQUIRED_COLUMNS))
        return pd.concat(frames, ignore_index=True)

    def _fetch_price(self, symbol: str, trade_date: date) -> float:
        if self._data_loader is None:
            raise RuntimeError(
                f"No underlying_price provided and no DataLoader configured "
                f"for {symbol} on {trade_date}."
            )
        df = self._data_loader.download(symbol, trade_date, trade_date + timedelta(days=1))
        ts = pd.Timestamp(trade_date)
        if ts in df.index:
            return float(df.loc[ts, "Adj Close"])
        raise ValueError(f"No price data for {symbol} on {trade_date}")


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------

_REQUIRED_COLUMNS = {
    "symbol", "trade_date", "expiry", "strike", "right",
    "bid", "ask", "mid", "volume", "open_interest",
    "implied_vol", "delta", "gamma", "theta", "vega",
    "underlying_price", "multiplier", "source",
}

_INSERT_OPTION_CHAIN = """
    INSERT INTO option_chains (
        symbol, trade_date, expiry, strike, right,
        bid, ask, mid, volume, open_interest,
        implied_vol, delta, gamma, theta, vega,
        underlying_price, multiplier, source
    ) VALUES (
        %(symbol)s, %(trade_date)s, %(expiry)s, %(strike)s, %(right)s,
        %(bid)s, %(ask)s, %(mid)s, %(volume)s, %(open_interest)s,
        %(implied_vol)s, %(delta)s, %(gamma)s, %(theta)s, %(vega)s,
        %(underlying_price)s, %(multiplier)s, %(source)s
    )
    ON CONFLICT (symbol, trade_date, expiry, strike, right) DO NOTHING
"""

_FETCH_CHAIN = """
    SELECT symbol, trade_date, expiry, strike, right,
           bid, ask, mid, volume, open_interest,
           implied_vol, delta, gamma, theta, vega,
           underlying_price, multiplier, source
    FROM option_chains
    WHERE symbol = %s AND trade_date = %s
    ORDER BY expiry, strike, right
"""


def store_chain(
    df: pd.DataFrame,
    conn: "psycopg2.extensions.connection",
) -> int:
    """Upsert option chain rows into option_chains table.

    Args:
        df:   DataFrame from generate_chain() or generate_chains().
        conn: psycopg2 connection (caller owns transaction lifecycle).

    Returns:
        Number of rows actually inserted (ON CONFLICT DO NOTHING skips dupes).
    """
    records = df.to_dict("records")
    if not records:
        return 0

    try:
        with conn.cursor() as cur:
            cur.executemany(_INSERT_OPTION_CHAIN, records)
            inserted = cur.rowcount
        conn.commit()
        return inserted
    except Exception:
        conn.rollback()
        raise


def fetch_chain(
    symbol: str,
    trade_date: date,
    conn: "psycopg2.extensions.connection",
) -> pd.DataFrame:
    """Fetch stored option chain for symbol on trade_date.

    Returns:
        DataFrame with all option chain columns, ordered by (expiry, strike, right).
        Empty DataFrame if no rows found.
    """
    with conn.cursor() as cur:
        cur.execute(_FETCH_CHAIN, (symbol, trade_date))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []

    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# IBKR live ingestion
# ---------------------------------------------------------------------------

def ingest_from_ibkr(
    adapter: Any,
    symbol: str,
    expiry: str,
    conn: "psycopg2.extensions.connection",
    trade_date: date | None = None,
) -> int:
    """Pull live option chain from IBKRAdapter and store to Postgres.

    Args:
        adapter:    IBKRAdapter (or BrokerAdapter) instance with active connection.
        symbol:     Underlying ticker (e.g. 'SPY').
        expiry:     Expiry in YYYYMMDD format (e.g. '20241220').
        conn:       psycopg2 connection to the option_chains database.
        trade_date: Trade date for the chain (default: today).

    Returns:
        Number of rows inserted.
    """
    chain = adapter.get_option_chain(symbol, expiry)
    if not chain:
        log.info("ingest_from_ibkr: empty chain for %s %s", symbol, expiry)
        return 0

    td = trade_date or date.today()
    expiry_date = date(int(expiry[:4]), int(expiry[4:6]), int(expiry[6:8]))

    records = [
        {
            "symbol": row["symbol"],
            "trade_date": td,
            "expiry": expiry_date,
            "strike": row["strike"],
            "right": row["right"],
            "bid": None,
            "ask": None,
            "mid": None,
            "volume": None,
            "open_interest": None,
            "implied_vol": None,
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "underlying_price": None,
            "multiplier": int(row.get("multiplier", "100")),
            "source": "ibkr",
        }
        for row in chain
    ]

    df = pd.DataFrame(records)
    return store_chain(df, conn)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lookup_price(price_series: pd.Series, ts: pd.Timestamp) -> float | None:
    """Return price for timestamp ts, trying exact match then nearest prior date."""
    if ts in price_series.index:
        return float(price_series[ts])
    # Try nearest prior business day
    prior = price_series.index[price_series.index <= ts]
    if len(prior) > 0:
        return float(price_series[prior[-1]])
    return None
