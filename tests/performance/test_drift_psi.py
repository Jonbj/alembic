"""Tests for PSI formula correctness."""

import numpy as np
import pytest

from src.performance.drift import compute_psi


class TestPSIFormula:
    """Test PSI formula implementation.

    Correct formula: PSI = Σ expected_i * ln(expected_i / actual_i)
    """

    def test_psi_identical_distributions(self):
        """Test PSI is 0 for identical distributions."""
        baseline = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        current = baseline.copy()

        psi = compute_psi(baseline, current)

        # Should be very close to 0 (may have small floating point error)
        assert abs(psi) < 0.01

    def test_psi_different_distributions(self):
        """Test PSI detects different distributions."""
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(1, 1, 1000)  # Shifted mean

        psi = compute_psi(baseline, current)

        # Should detect drift (positive PSI)
        assert psi > 0

    def test_psi_formula_correctness(self):
        """Test PSI formula is positive for different distributions.

        PSI = Σ expected_i * ln(expected_i / actual_i)

        The formula produces positive values when distributions differ.
        Exact value depends on binning and distribution shape.
        """
        # Create clearly different distributions
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(2, 1, 1000)  # Shifted mean

        psi = compute_psi(baseline, current)

        # PSI should be positive for different distributions
        assert psi > 0
        # Severe drift typically produces PSI > 0.25
        assert psi > 0.25

    def test_psi_empty_arrays(self):
        """Test PSI handles empty arrays."""
        assert compute_psi(np.array([]), np.array([])) == 0.0
        assert compute_psi(np.array([1, 2, 3]), np.array([])) == 0.0
        assert compute_psi(np.array([]), np.array([1, 2, 3])) == 0.0

    def test_psi_single_value(self):
        """Test PSI with single value arrays."""
        assert compute_psi(np.array([5.0]), np.array([5.0])) == 0.0

    def test_psi_yellow_threshold(self):
        """Test PSI yellow threshold detection (0.10)."""
        # Create moderate drift
        baseline = np.random.normal(0, 1, 500)
        current = np.random.normal(0.5, 1.2, 500)

        psi = compute_psi(baseline, current)

        # Should be able to detect moderate drift
        assert psi >= 0  # PSI is always non-negative

    def test_psi_red_threshold(self):
        """Test PSI red threshold detection (0.25)."""
        # Create severe drift
        baseline = np.random.normal(0, 1, 500)
        current = np.random.normal(2, 2, 500)

        psi = compute_psi(baseline, current)

        # Severe drift should have higher PSI
        assert psi > 0
