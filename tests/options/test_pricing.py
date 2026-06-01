"""Tests for src.options.pricing — Black-Scholes pricing, greeks, implied vol.

Validation reference: S=100, K=100, T=1yr, r=5%, sigma=20%
  call ≈ 10.4506, put ≈ 5.5735, call delta ≈ 0.6368, put delta ≈ -0.3632
  (matches CBOE calculator and standard Black-Scholes tables)
"""

from __future__ import annotations

import math

import pytest

from src.options.pricing import black_scholes_price, compute_greeks, implied_vol

# ---------------------------------------------------------------------------
# Canonical reference parameters
# ---------------------------------------------------------------------------

_S, _K, _T, _R, _SIG = 100.0, 100.0, 1.0, 0.05, 0.20


# ---------------------------------------------------------------------------
# Known-value validation (ATM, 1-year)
# ---------------------------------------------------------------------------


class TestKnownValues:
    """Validate against published Black-Scholes reference values."""

    def test_atm_1yr_call_price(self) -> None:
        """ATM 1-year call: known BS value ≈ 10.4506."""
        price = black_scholes_price(_S, _K, _T, _R, _SIG, "C")
        assert price == pytest.approx(10.4506, abs=0.01)

    def test_atm_1yr_put_price(self) -> None:
        """ATM 1-year put: known BS value ≈ 5.5735."""
        price = black_scholes_price(_S, _K, _T, _R, _SIG, "P")
        assert price == pytest.approx(5.5735, abs=0.01)

    def test_atm_1yr_call_delta(self) -> None:
        """ATM 1-year call delta ≈ 0.6368."""
        g = compute_greeks(_S, _K, _T, _R, _SIG, "C")
        assert g["delta"] == pytest.approx(0.6368, abs=0.001)

    def test_atm_1yr_put_delta(self) -> None:
        """ATM 1-year put delta ≈ -0.3632."""
        g = compute_greeks(_S, _K, _T, _R, _SIG, "P")
        assert g["delta"] == pytest.approx(-0.3632, abs=0.001)

    def test_put_call_parity(self) -> None:
        """C - P = S - K * exp(-rT) (European put-call parity)."""
        c = black_scholes_price(_S, _K, _T, _R, _SIG, "C")
        p = black_scholes_price(_S, _K, _T, _R, _SIG, "P")
        assert c - p == pytest.approx(_S - _K * math.exp(-_R * _T), abs=1e-6)


# ---------------------------------------------------------------------------
# ITM options
# ---------------------------------------------------------------------------


class TestITM:
    def test_itm_call_above_intrinsic(self) -> None:
        """Deep ITM call: price > intrinsic (time value > 0)."""
        price = black_scholes_price(120.0, 100.0, 1.0, _R, _SIG, "C")
        assert price > 20.0

    def test_itm_call_below_upper_bound(self) -> None:
        price = black_scholes_price(120.0, 100.0, 1.0, _R, _SIG, "C")
        assert price < 40.0

    def test_itm_put_above_discounted_intrinsic(self) -> None:
        """Deep ITM put: price > K*exp(-rT) - S."""
        price = black_scholes_price(80.0, 100.0, 1.0, _R, _SIG, "P")
        discounted_intrinsic = 100.0 * math.exp(-_R) - 80.0
        assert price > discounted_intrinsic


# ---------------------------------------------------------------------------
# OTM options
# ---------------------------------------------------------------------------


class TestOTM:
    def test_otm_call_small_positive(self) -> None:
        """Deep OTM call: small positive value (time value only)."""
        price = black_scholes_price(80.0, 100.0, 1.0, _R, _SIG, "C")
        assert 0.0 < price < 5.0

    def test_otm_put_small_positive(self) -> None:
        price = black_scholes_price(120.0, 100.0, 1.0, _R, _SIG, "P")
        assert 0.0 < price < 5.0

    def test_otm_call_less_than_itm_call(self) -> None:
        otm = black_scholes_price(80.0, 100.0, 1.0, _R, _SIG, "C")
        itm = black_scholes_price(120.0, 100.0, 1.0, _R, _SIG, "C")
        assert otm < itm


# ---------------------------------------------------------------------------
# Near-expiry
# ---------------------------------------------------------------------------


class TestNearExpiry:
    def test_near_expiry_itm_call_approaches_intrinsic(self) -> None:
        T = 1.0 / 365
        price = black_scholes_price(105.0, 100.0, T, _R, _SIG, "C")
        assert abs(price - 5.0) < 0.5

    def test_near_expiry_otm_call_near_zero(self) -> None:
        T = 1.0 / 365
        price = black_scholes_price(95.0, 100.0, T, _R, _SIG, "C")
        assert 0.0 <= price < 0.5

    def test_expired_call_intrinsic_itm(self) -> None:
        assert black_scholes_price(110.0, 100.0, 0.0, _R, _SIG, "C") == pytest.approx(10.0)

    def test_expired_call_zero_otm(self) -> None:
        assert black_scholes_price(90.0, 100.0, 0.0, _R, _SIG, "C") == pytest.approx(0.0)

    def test_expired_put_intrinsic_itm(self) -> None:
        assert black_scholes_price(90.0, 100.0, 0.0, _R, _SIG, "P") == pytest.approx(10.0)

    def test_expired_put_zero_otm(self) -> None:
        assert black_scholes_price(110.0, 100.0, 0.0, _R, _SIG, "P") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# High vol
# ---------------------------------------------------------------------------


class TestHighVol:
    def test_high_vol_call_more_expensive(self) -> None:
        low = black_scholes_price(_S, _K, _T, _R, 0.20, "C")
        high = black_scholes_price(_S, _K, _T, _R, 0.50, "C")
        assert high > low

    def test_high_vol_put_more_expensive(self) -> None:
        low = black_scholes_price(_S, _K, _T, _R, 0.20, "P")
        high = black_scholes_price(_S, _K, _T, _R, 0.50, "P")
        assert high > low


# ---------------------------------------------------------------------------
# Greeks — properties
# ---------------------------------------------------------------------------


class TestGreeksProperties:
    def test_call_delta_bounded_0_to_1(self) -> None:
        for K in (80.0, 100.0, 120.0):
            g = compute_greeks(_S, K, _T, _R, _SIG, "C")
            assert 0.0 <= g["delta"] <= 1.0

    def test_put_delta_bounded_minus1_to_0(self) -> None:
        for K in (80.0, 100.0, 120.0):
            g = compute_greeks(_S, K, _T, _R, _SIG, "P")
            assert -1.0 <= g["delta"] <= 0.0

    def test_gamma_equals_call_put(self) -> None:
        """Call and put have identical gamma."""
        gc = compute_greeks(_S, _K, _T, _R, _SIG, "C")
        gp = compute_greeks(_S, _K, _T, _R, _SIG, "P")
        assert gc["gamma"] == pytest.approx(gp["gamma"], rel=1e-6)

    def test_vega_equals_call_put(self) -> None:
        """Call and put have identical vega."""
        gc = compute_greeks(_S, _K, _T, _R, _SIG, "C")
        gp = compute_greeks(_S, _K, _T, _R, _SIG, "P")
        assert gc["vega"] == pytest.approx(gp["vega"], rel=1e-6)

    def test_gamma_positive(self) -> None:
        for right in ("C", "P"):
            assert compute_greeks(_S, _K, _T, _R, _SIG, right)["gamma"] > 0

    def test_vega_positive(self) -> None:
        for right in ("C", "P"):
            assert compute_greeks(_S, _K, _T, _R, _SIG, right)["vega"] > 0

    def test_theta_negative_long_options(self) -> None:
        """Theta is negative for long calls and puts (time decay)."""
        for right in ("C", "P"):
            assert compute_greeks(_S, _K, _T, _R, _SIG, right)["theta"] < 0

    def test_call_delta_increases_with_underlying(self) -> None:
        g_low = compute_greeks(90.0, _K, _T, _R, _SIG, "C")
        g_mid = compute_greeks(100.0, _K, _T, _R, _SIG, "C")
        g_high = compute_greeks(110.0, _K, _T, _R, _SIG, "C")
        assert g_low["delta"] < g_mid["delta"] < g_high["delta"]

    def test_expired_itm_call_delta_is_1(self) -> None:
        g = compute_greeks(110.0, 100.0, 0.0, _R, _SIG, "C")
        assert g["delta"] == 1.0

    def test_expired_itm_put_delta_is_minus1(self) -> None:
        g = compute_greeks(90.0, 100.0, 0.0, _R, _SIG, "P")
        assert g["delta"] == -1.0

    def test_expired_greeks_zero_except_delta(self) -> None:
        g = compute_greeks(110.0, 100.0, 0.0, _R, _SIG, "C")
        assert g["gamma"] == 0.0
        assert g["theta"] == 0.0
        assert g["vega"] == 0.0


# ---------------------------------------------------------------------------
# Implied vol — recovery round-trip
# ---------------------------------------------------------------------------


class TestImpliedVolRecovery:
    def test_atm_call_recovers_sigma(self) -> None:
        price = black_scholes_price(_S, _K, _T, _R, 0.20, "C")
        iv = implied_vol(price, _S, _K, _T, _R, "C")
        assert iv == pytest.approx(0.20, abs=1e-4)

    def test_atm_put_recovers_sigma(self) -> None:
        price = black_scholes_price(_S, _K, _T, _R, 0.20, "P")
        iv = implied_vol(price, _S, _K, _T, _R, "P")
        assert iv == pytest.approx(0.20, abs=1e-4)

    def test_itm_call_recovers_sigma(self) -> None:
        price = black_scholes_price(110.0, 100.0, _T, _R, 0.25, "C")
        iv = implied_vol(price, 110.0, 100.0, _T, _R, "C")
        assert iv == pytest.approx(0.25, abs=1e-4)

    def test_otm_call_recovers_sigma(self) -> None:
        price = black_scholes_price(90.0, 100.0, _T, _R, 0.30, "C")
        iv = implied_vol(price, 90.0, 100.0, _T, _R, "C")
        assert iv == pytest.approx(0.30, abs=1e-4)

    def test_high_vol_recovers(self) -> None:
        price = black_scholes_price(_S, _K, _T, _R, 0.50, "C")
        iv = implied_vol(price, _S, _K, _T, _R, "C")
        assert iv == pytest.approx(0.50, abs=1e-4)

    def test_near_expiry_put_recovers_sigma(self) -> None:
        T = 30.0 / 365
        price = black_scholes_price(_S, _K, T, _R, 0.20, "P")
        iv = implied_vol(price, _S, _K, T, _R, "P")
        assert iv == pytest.approx(0.20, abs=1e-4)


# ---------------------------------------------------------------------------
# Implied vol — edge cases
# ---------------------------------------------------------------------------


class TestImpliedVolEdgeCases:
    def test_expired_option_raises(self) -> None:
        with pytest.raises(ValueError, match="T must be positive"):
            implied_vol(5.0, 105.0, 100.0, 0.0, _R, "C")

    def test_negative_price_raises(self) -> None:
        with pytest.raises(ValueError, match="market_price"):
            implied_vol(-1.0, _S, _K, _T, _R, "C")

    def test_zero_price_raises(self) -> None:
        with pytest.raises(ValueError, match="market_price"):
            implied_vol(0.0, _S, _K, _T, _R, "C")

    def test_price_below_intrinsic_raises(self) -> None:
        """market_price=3 for ITM call with S=105, K=100 is below no-arb bound."""
        with pytest.raises(ValueError):
            implied_vol(3.0, 105.0, 100.0, 1.0, _R, "C")
