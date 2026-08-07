"""Tests for #161: surveillance of positions that carry no broker-side stop.

Alpaca needs at least 1 whole share for a stop order, so a sub-1-share position
is unprotectable *by construction* — and until now nothing in the system told
those apart from protected ones. These tests pin the classification (protectable
vs unprotectable vs protected) and the alert selection on the -15% threshold
pre-registered in config/trading.yaml:180-182.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.portfolio.fractional_stop_orders import ProtectiveStopPlan
from src.portfolio.unprotected_positions import (
    classify_protection,
    format_unprotected_alert,
    select_unprotected_alerts,
)


def _position(symbol: str, qty: str, avg_entry_price: str = "100.0", **kwargs):
    return SimpleNamespace(symbol=symbol, qty=qty, avg_entry_price=avg_entry_price, **kwargs)


def _plan(symbol: str, action: str, whole_qty: int = 0):
    return ProtectiveStopPlan(action=action, symbol=symbol, whole_qty=whole_qty, stop_price=None)


class TestClassifyProtection:
    def test_sub_one_share_position_is_not_protectable(self):
        rows = classify_protection(
            [_position("NOK", "0.563993", unrealized_plpc="-0.246")],
            [_plan("NOK", "skip_no_whole_share")],
        )

        assert len(rows) == 1
        assert rows[0].protectable is False
        assert rows[0].protected is False
        assert rows[0].status == "sub_one_share"

    def test_whole_share_position_with_live_stop_is_protected(self):
        rows = classify_protection(
            [_position("AAPL", "2.4578", unrealized_plpc="-0.30")],
            [_plan("AAPL", "noop", whole_qty=2)],
        )

        assert rows[0].protectable is True
        assert rows[0].protected is True
        assert rows[0].status == "protected"

    def test_whole_share_position_whose_stop_failed_is_protectable_but_unprotected(self):
        rows = classify_protection(
            [_position("MRVL", "1.9", unrealized_plpc="-0.22")],
            [_plan("MRVL", "create", whole_qty=1)],
            failed_symbols={"MRVL"},
        )

        assert rows[0].protectable is True
        assert rows[0].protected is False
        assert rows[0].status == "stop_sync_failed"

    def test_insufficient_qty_skip_is_protectable_but_unprotected(self):
        rows = classify_protection(
            [_position("WDC", "1.4", unrealized_plpc="-0.16")],
            [_plan("WDC", "skip_insufficient_qty")],
        )

        assert rows[0].protectable is True
        assert rows[0].protected is False
        assert rows[0].status == "stop_pending_qty"

    def test_loss_pct_falls_back_to_current_price_when_plpc_absent(self):
        rows = classify_protection(
            [_position("AMAT", "0.857076", avg_entry_price="200.0", current_price="150.0")],
            [_plan("AMAT", "skip_no_whole_share")],
        )

        assert rows[0].loss_pct == pytest.approx(-0.25)

    def test_position_without_price_information_yields_no_loss_pct(self):
        rows = classify_protection(
            [_position("CAT", "0.821012")],
            [_plan("CAT", "skip_no_whole_share")],
        )

        assert rows[0].loss_pct is None

    def test_orphan_stop_plans_without_a_position_are_ignored(self):
        rows = classify_protection([], [_plan("SOXX", "cancel_orphan")])

        assert rows == []

    def test_position_without_a_plan_is_classified_from_its_qty(self):
        """Defensive: a plan list that lost a symbol must not silently drop it —
        a sub-1-share position stays visible as unprotectable."""
        rows = classify_protection([_position("INTC", "0.4", unrealized_plpc="-0.105")], [])

        assert rows[0].protectable is False
        assert rows[0].protected is False


class TestSelectUnprotectedAlerts:
    def _rows(self):
        return classify_protection(
            [
                _position("NOK", "0.563993", unrealized_plpc="-0.246"),
                _position("WDC", "0.334697", unrealized_plpc="-0.153"),
                _position("INTC", "0.4", unrealized_plpc="-0.105"),
                _position("AAPL", "2.4578", unrealized_plpc="-0.30"),
            ],
            [
                _plan("NOK", "skip_no_whole_share"),
                _plan("WDC", "skip_no_whole_share"),
                _plan("INTC", "skip_no_whole_share"),
                _plan("AAPL", "noop", whole_qty=2),
            ],
        )

    def test_only_unprotected_positions_past_the_threshold_are_selected(self):
        selected = select_unprotected_alerts(self._rows(), loss_threshold_pct=0.15)

        # AAPL is -30% but protected; INTC is unprotected but only -10.5%.
        assert [r.symbol for r in selected] == ["NOK", "WDC"]

    def test_worst_loss_comes_first(self):
        selected = select_unprotected_alerts(self._rows(), loss_threshold_pct=0.10)

        assert [r.symbol for r in selected] == ["NOK", "WDC", "INTC"]

    def test_positions_without_loss_pct_are_never_selected(self):
        rows = classify_protection(
            [_position("CAT", "0.821012")], [_plan("CAT", "skip_no_whole_share")]
        )

        assert select_unprotected_alerts(rows, loss_threshold_pct=0.15) == []


class TestFormatUnprotectedAlert:
    def test_message_names_the_symbol_loss_qty_and_why_it_is_unprotected(self):
        row = classify_protection(
            [_position("NOK", "0.563993", unrealized_plpc="-0.246")],
            [_plan("NOK", "skip_no_whole_share")],
        )[0]

        msg = format_unprotected_alert(row, loss_threshold_pct=0.15)

        assert "NOK" in msg
        assert "-24.6%" in msg
        assert "0.5640" in msg
        assert "sub-1-share" in msg
        assert "#161" in msg

    def test_message_distinguishes_a_protectable_position_missing_its_stop(self):
        row = classify_protection(
            [_position("MRVL", "1.9", unrealized_plpc="-0.22")],
            [_plan("MRVL", "create", whole_qty=1)],
            failed_symbols={"MRVL"},
        )[0]

        msg = format_unprotected_alert(row, loss_threshold_pct=0.15)

        assert "sub-1-share" not in msg
        assert "stop sync failed" in msg
