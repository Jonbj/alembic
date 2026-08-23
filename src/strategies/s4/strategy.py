"""S4 News-Driven Tactical strategy module."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, Sequence

import pandas as pd

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import (
    MarketSnapshot,
    Order,
    OrderSide,
    RebalanceFrequency,
)
from src.models.signals import SentimentResult
from src.strategies.s4.config import S4Config
from src.strategies.s4.ranking import CrossSectionalRanker

if TYPE_CHECKING:
    from src.strategies.s4.intent_ledger import S4IntentLedger


class NewsDrivenTactical:
    """S4: News-Driven Tactical strategy, compatible with BacktestOrchestrator.

    Reads pre-computed sentiment signals (SentimentResult), ranks them
    cross-sectionally via CrossSectionalRanker, and allocates to the top-N
    bucket with equal weights.  Rebalances weekly by default.

    Args:
        config: S4Config with n_top, bucket_pct, filters, and rebalance_frequency.
        signals: Optional DataFrame with columns [symbol, score, confidence,
                 reasoning, model_id, generated_at] pre-loaded for backtesting.
                 If None, __call__ will produce no orders (live mode: inject
                 signals externally before calling).
    """

    def __init__(
        self,
        config: S4Config,
        signals: pd.DataFrame | None = None,
        intent_ledger: "S4IntentLedger | None" = None,
    ) -> None:
        self._config = config
        self._ranker = CrossSectionalRanker(config)
        self._signals_df = signals
        self._intent_ledger = intent_ledger
        self._last_rebalance: Optional[datetime] = None
        # B33-follow-up: provenance (signal_id/score/reasoning/model_id) of the
        # signal that drove each ticker's weight in the most recent
        # compute_target_weights() call. Pinned here so the orchestrator can
        # carry it through to decision logging + idempotency without ever
        # re-querying the signal store for "latest" (which races a signal
        # that arrives after ranking but before logging).
        self._last_signal_provenance: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_target_weights(
        self,
        signals: Sequence[SentimentResult],
        as_of: datetime | None = None,
    ) -> dict[str, float]:
        """Return {ticker: weight} for top-ranked tickers from given signals."""
        result = self._ranker.rank(signals, as_of=as_of)
        self._last_signal_provenance = result.provenance
        if self._intent_ledger is not None:
            for diagnostic in result.diagnostics:
                if diagnostic.signal_id is None:
                    continue
                self._intent_ledger.set_disposition(
                    signal_id=diagnostic.signal_id,
                    reason_code=diagnostic.reason_code,
                    rank=diagnostic.rank,
                )
        return result.weights

    @property
    def last_signal_provenance(self) -> dict[str, dict]:
        """Per-ticker {signal_id, score, reasoning, model_id} from the most
        recent compute_target_weights() call. Empty before the first call."""
        return self._last_signal_provenance

    def health_check(self) -> bool:
        """Return True when the preloaded signal frame is safe to consume."""
        if self._signals_df is None or self._signals_df.empty:
            return False

        required = ("symbol", "score", "confidence", "generated_at")
        if not set(required).issubset(self._signals_df.columns):
            return False

        signals = self._signals_df.loc[:, required]
        if signals.isna().any().any():
            return False
        if not signals["symbol"].map(
            lambda value: isinstance(value, str) and bool(value.strip())
        ).all():
            return False
        if not signals["generated_at"].map(lambda value: isinstance(value, datetime)).all():
            return False

        scores = pd.to_numeric(signals["score"], errors="coerce")
        confidences = pd.to_numeric(signals["confidence"], errors="coerce")
        if scores.isna().any() or not scores.between(-1.0, 1.0).all():
            return False
        return bool(
            not confidences.isna().any() and confidences.between(0.0, 1.0).all()
        )

    def should_rebalance(self, ts: datetime) -> bool:
        """Public gate: returns True if it is time to rebalance at timestamp ts."""
        return self._should_rebalance(ts)

    def mark_rebalanced(self, ts: datetime) -> None:
        """Record that a rebalance was performed at ts."""
        self._last_rebalance = ts

    def __call__(
        self,
        ts: datetime,
        data_replay: DataReplay,
        portfolio: VirtualPortfolio,
        market: MarketSnapshot,
    ) -> list[Order]:
        if not self._should_rebalance(ts):
            return []

        self._last_rebalance = ts
        signals = self._signals_as_of(ts)
        target_weights = self.compute_target_weights(signals, as_of=ts)
        nav = self._nav(portfolio, market)
        orders: list[Order] = []

        # Exit: close positions absent from target
        for pos in portfolio.all_positions():
            if pos.symbol not in target_weights:
                price = market.price_of(pos.symbol)
                if price is not None and pos.quantity > 0:
                    orders.append(
                        Order.market_order(
                            ts=ts,
                            symbol=pos.symbol,
                            side=OrderSide.SELL,
                            qty=pos.quantity,
                            strategy_id=self._config.strategy_id,
                        )
                    )

        # Entry / rebalance: move toward target weights
        for ticker, target_wt in target_weights.items():
            price = market.price_of(ticker)
            if price is None or price <= 0:
                continue
            target_qty = (nav * target_wt) / price
            current_pos = portfolio.position_of(ticker)
            current_qty = current_pos.quantity if current_pos is not None else 0.0
            delta = target_qty - current_qty

            if abs(delta) < 1e-4:
                continue

            if delta > 0:
                orders.append(
                    Order.market_order(
                        ts=ts,
                        symbol=ticker,
                        side=OrderSide.BUY,
                        qty=delta,
                        strategy_id=self._config.strategy_id,
                    )
                )
            else:
                orders.append(
                    Order.market_order(
                        ts=ts,
                        symbol=ticker,
                        side=OrderSide.SELL,
                        qty=-delta,
                        strategy_id=self._config.strategy_id,
                    )
                )

        return orders

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _signals_as_of(self, ts: datetime) -> list[SentimentResult]:
        """Return SentimentResult objects with generated_at <= ts."""
        if self._signals_df is None or self._signals_df.empty:
            return []
        df = self._signals_df
        if "generated_at" in df.columns:
            df = df[df["generated_at"] <= ts]
            # QS-07 backtest/live parity: the live cycle drops signals older than
            # max_signal_age_hours at each tick (_filter_stale_signals). Apply the same
            # freshness window here so backtest IC is reproducible in live and does not
            # use stale signals the live engine would have discarded (T0 contamination).
            #
            # #236: EXCEPT the ones the caller has already decided to re-admit. FIX-D
            # (_preserve_stale_signals_for_open_positions) puts a stale positive signal
            # back into signals_df when the symbol has an open position and no
            # counter-signal, because a signal expiry is not an exit — it means "no new
            # information". Re-filtering it here on age alone silently overrode that
            # decision: the symbol left the ranker, its merged weight went to 0, and
            # the orchestrator sold the position with no counter-signal (SONY, HOOD,
            # IBM, SPCX — see docs/issues/186/FINDING.md).
            #
            # The exemption is by PROVENANCE, not by age: only rows explicitly marked
            # survive. An unmarked stale row is still dropped, which keeps QS-07 doing
            # its real job in backtest — where nothing filters signals_df upstream and
            # this is the only defence against T0 contamination.
            max_age = getattr(self._config, "max_signal_age_hours", 0) or 0
            if max_age > 0:
                fresh_enough = df["generated_at"] >= ts - timedelta(hours=max_age)
                if "fix_d_preserved" in df.columns:
                    fresh_enough = fresh_enough | df["fix_d_preserved"].fillna(False).astype(bool)
                df = df[fresh_enough]
        results: list[SentimentResult] = []
        for _, row in df.iterrows():
            raw_signal_id = row.get("signal_id") if "signal_id" in row.index else None
            signal_id = int(raw_signal_id) if pd.notna(raw_signal_id) else None
            results.append(
                SentimentResult(
                    symbol=str(row["symbol"]),
                    score=float(row["score"]),
                    confidence=float(row["confidence"]),
                    reasoning=str(row.get("reasoning", "")),
                    model_id=str(row.get("model_id", "unknown")),
                    ensemble_std=float(row.get("ensemble_std", 0.0)),
                    fallback_used=bool(row.get("fallback_used", False)),
                    generated_at=row["generated_at"] if "generated_at" in row.index else ts,
                    signal_id=signal_id,
                )
            )
        return results

    def _should_rebalance(self, ts: datetime) -> bool:
        if self._last_rebalance is None:
            return True
        if self._config.rebalance_frequency == RebalanceFrequency.DAILY:
            return ts.date() != self._last_rebalance.date()
        if self._config.rebalance_frequency == RebalanceFrequency.WEEKLY:
            return (
                ts.isocalendar().week != self._last_rebalance.isocalendar().week
                or ts.year != self._last_rebalance.year
            )
        # MONTHLY
        return (
            ts.month != self._last_rebalance.month
            or ts.year != self._last_rebalance.year
        )

    def _nav(self, portfolio: VirtualPortfolio, market: MarketSnapshot) -> float:
        nav = portfolio.cash
        for pos in portfolio.all_positions():
            price = market.price_of(pos.symbol)
            if price is not None:
                nav += pos.market_value(price)
        return nav
