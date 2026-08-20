"""Unit tests for the pure buying-power pre-flight gate (#199)."""

from dataclasses import FrozenInstanceError

import pytest

from src.portfolio.buying_power_gate import evaluate_buying_power_gate


def test_passes_when_notional_is_within_buying_power():
    result = evaluate_buying_power_gate(
        notional=100.0,
        buying_power=500.0,
        is_fractionable=True,
        mode="cap",
    )

    assert result.action == "pass"
    assert result.capped_notional is None
    assert result.capped_qty is None
    assert result.delta == 0.0


def test_off_mode_passes_even_when_over_budget():
    result = evaluate_buying_power_gate(
        notional=1000.0,
        buying_power=100.0,
        is_fractionable=True,
        mode="off",
    )

    assert result.action == "pass"


@pytest.mark.parametrize("buying_power", [None, 0.0, -1.0])
def test_skips_when_buying_power_is_unavailable(buying_power):
    result = evaluate_buying_power_gate(
        notional=100.0,
        buying_power=buying_power,
        is_fractionable=True,
        mode="cap",
    )

    assert result.action == "skip"
    assert result.capped_notional is None
    assert result.capped_qty is None


@pytest.mark.parametrize("is_fractionable", [True, False])
def test_shadow_reports_excess_without_capping(is_fractionable):
    result = evaluate_buying_power_gate(
        notional=1000.0,
        buying_power=500.0,
        is_fractionable=is_fractionable,
        mode="shadow",
        price=150.0,
    )

    assert result.action == "shadow"
    assert result.capped_notional is None
    assert result.capped_qty is None
    assert result.delta == pytest.approx(500.0)


def test_caps_fractionable_notional_to_buying_power():
    result = evaluate_buying_power_gate(
        notional=1000.0,
        buying_power=500.0,
        is_fractionable=True,
        mode="cap",
    )

    assert result.action == "cap"
    assert result.capped_notional == pytest.approx(500.0)
    assert result.capped_qty is None
    assert result.delta == pytest.approx(500.0)


def test_caps_non_fractionable_notional_to_whole_shares():
    result = evaluate_buying_power_gate(
        notional=15000.0,
        buying_power=500.0,
        is_fractionable=False,
        mode="cap",
        price=150.0,
    )

    assert result.action == "cap"
    assert result.capped_notional == pytest.approx(450.0)
    assert result.capped_qty == 3
    assert result.delta == pytest.approx(14500.0)


@pytest.mark.parametrize(
    ("buying_power", "price"),
    [(100.0, 150.0), (500.0, None), (500.0, 0.0)],
)
def test_skips_non_fractionable_order_that_cannot_be_safely_rounded(
    buying_power, price
):
    result = evaluate_buying_power_gate(
        notional=1000.0,
        buying_power=buying_power,
        is_fractionable=False,
        mode="cap",
        price=price,
    )

    assert result.action == "skip"
    assert result.capped_notional is None
    assert result.capped_qty is None


def test_unknown_mode_is_defensively_a_noop():
    result = evaluate_buying_power_gate(
        notional=1000.0,
        buying_power=100.0,
        is_fractionable=True,
        mode="bogus",
    )

    assert result.action == "pass"


def test_result_is_immutable():
    result = evaluate_buying_power_gate(
        notional=100.0,
        buying_power=500.0,
        is_fractionable=True,
        mode="cap",
    )

    with pytest.raises(FrozenInstanceError):
        result.action = "skip"
