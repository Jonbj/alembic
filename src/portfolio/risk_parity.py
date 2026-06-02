"""RiskParityAllocator: inverse-vol weights with min/max constraints."""
from __future__ import annotations

import pandas as pd


class RiskParityAllocator:
    """Compute inverse-volatility weights across strategies for equal risk contribution.

    Args:
        returns: mapping of strategy_id → daily-returns Series
        window:  rolling window (bars) used to estimate realized volatility
        min_weight: floor per strategy (default 10%)
        max_weight: cap per strategy (default 60%)
    """

    MIN_VOL: float = 1e-9  # below this → equal-weight fallback

    def __init__(
        self,
        returns: dict[str, pd.Series],
        window: int = 60,
        min_weight: float = 0.10,
        max_weight: float = 0.60,
    ) -> None:
        self._returns = returns
        self._window = window
        self._min_weight = min_weight
        self._max_weight = max_weight

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def compute_weights(self) -> dict[str, float]:
        """Return strategy weights as a dict summing to 1.0."""
        vols = self._realized_vols()
        n = len(vols)

        if any(v < self.MIN_VOL for v in vols.values()):
            return {sid: 1.0 / n for sid in vols}

        inv_vols = {sid: 1.0 / v for sid, v in vols.items()}
        total = sum(inv_vols.values())
        raw = {sid: iv / total for sid, iv in inv_vols.items()}

        return self._apply_constraints(raw)

    def compare_vs_equal(self) -> pd.DataFrame:
        """Return DataFrame with capital_allocation and risk_contribution per strategy."""
        weights = self.compute_weights()
        vols = self._realized_vols()

        risk_budgets = {sid: weights[sid] * vols[sid] for sid in weights}
        total_risk = sum(risk_budgets.values())
        n = len(weights)

        records = []
        for sid in sorted(weights):
            rc = risk_budgets[sid] / total_risk if total_risk > 0 else 1.0 / n
            records.append({
                "strategy_id": sid,
                "capital_allocation": weights[sid],
                "risk_contribution": rc,
            })

        return pd.DataFrame(records).set_index("strategy_id")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _realized_vols(self) -> dict[str, float]:
        vols: dict[str, float] = {}
        for sid, ret in self._returns.items():
            recent = ret.iloc[-self._window :]
            vols[sid] = float(recent.std())
        return vols

    def _apply_constraints(self, weights: dict[str, float]) -> dict[str, float]:
        """Water-filling projection onto [min_weight, max_weight] per strategy.

        Iteratively fixes strategies that violate their bounds and redistributes
        the remaining weight proportionally among the unconstrained strategies.
        Converges in at most len(weights) rounds.
        """
        w = dict(weights)
        min_w, max_w = self._min_weight, self._max_weight
        eps = 1e-12

        for _ in range(len(w) + 10):
            fixed: dict[str, float] = {}
            free_keys: list[str] = []

            for k, v in w.items():
                if v < min_w - eps:
                    fixed[k] = min_w
                elif v > max_w + eps:
                    fixed[k] = max_w
                else:
                    free_keys.append(k)

            if not fixed:
                # All within bounds — normalize to 1.0 in case of rounding drift
                total = sum(w.values())
                return {k: v / total for k, v in w.items()}

            remaining = 1.0 - sum(fixed.values())

            if not free_keys or remaining <= eps:
                # No free strategies: renormalize and loop — the new values may
                # again violate bounds and need further redistribution.
                total = sum(fixed.values())
                w = {k: fixed.get(k, w[k]) / total for k in w}
                continue

            free_total = sum(w[k] for k in free_keys)
            if free_total <= eps:
                equal = remaining / len(free_keys)
                w = {**fixed, **{k: equal for k in free_keys}}
            else:
                w = {**fixed, **{k: w[k] / free_total * remaining for k in free_keys}}

        # Fallback: normalize whatever we have
        total = sum(w.values())
        return {k: v / total for k, v in w.items()}
