"""Pure buying-power pre-flight decision for Alpaca BUY orders (#199)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuyingPowerGateResult:
    """Outcome of evaluating one intended BUY against broker buying power."""

    action: str
    capped_notional: float | None
    capped_qty: int | None
    delta: float


def evaluate_buying_power_gate(
    *,
    notional: float,
    buying_power: float | None,
    is_fractionable: bool,
    mode: str,
    price: float | None = None,
) -> BuyingPowerGateResult:
    """Return pass, shadow, cap, or skip without performing side effects."""
    if mode == "off":
        return BuyingPowerGateResult("pass", None, None, 0.0)
    if buying_power is None or buying_power <= 0:
        return BuyingPowerGateResult("skip", None, None, 0.0)
    if notional <= buying_power:
        return BuyingPowerGateResult("pass", None, None, 0.0)

    delta = round(notional - buying_power, 2)
    if mode == "shadow":
        return BuyingPowerGateResult("shadow", None, None, delta)
    if mode != "cap":
        # Config validation rejects unknown modes; remain backward-compatible if
        # this pure helper is called directly with an invalid value.
        return BuyingPowerGateResult("pass", None, None, 0.0)

    if is_fractionable:
        return BuyingPowerGateResult(
            "cap", round(buying_power, 2), None, delta
        )
    if price is None or price <= 0:
        return BuyingPowerGateResult("skip", None, None, delta)

    capped_qty = int(buying_power / price)
    if capped_qty < 1:
        return BuyingPowerGateResult("skip", None, None, delta)
    return BuyingPowerGateResult(
        "cap", round(capped_qty * price, 2), capped_qty, delta
    )
