"""Tests for synthetic transit simulation workflows."""

from __future__ import annotations

import unittest

import numpy as np

from astraeus.simulation import (
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)


class SyntheticTransitSeriesTests(unittest.TestCase):
    """Regression tests for composed synthetic transit workflows."""

    def test_default_hot_jupiter_series_has_expected_shape(self) -> None:
        """The default scenario should produce aligned ten-day arrays."""

        scenario = SyntheticTransitScenario(samples=500)
        light_curve = generate_synthetic_transit_series(scenario)

        self.assertEqual(light_curve.time_days.shape, (500,))
        self.assertEqual(light_curve.theoretical_flux.shape, (500,))
        self.assertEqual(light_curve.observed_flux.shape, (500,))
        self.assertAlmostEqual(light_curve.time_days[0], 0.0)
        self.assertAlmostEqual(light_curve.time_days[-1], 10.0)

    def test_default_hot_jupiter_series_contains_transits(self) -> None:
        """The noiseless hot-Jupiter curve should include transit dips."""

        scenario = SyntheticTransitScenario(samples=1_000)
        light_curve = generate_synthetic_transit_series(scenario)

        self.assertLess(np.min(light_curve.theoretical_flux), 1.0)
        self.assertAlmostEqual(np.max(light_curve.theoretical_flux), 1.0)

    def test_residuals_are_observed_minus_theoretical(self) -> None:
        """Residuals should stay a derived view of the stored arrays."""

        light_curve = generate_synthetic_transit_series(
            SyntheticTransitScenario(samples=128)
        )

        np.testing.assert_allclose(
            light_curve.residuals,
            light_curve.observed_flux - light_curve.theoretical_flux,
        )

    def test_invalid_sample_count_is_rejected(self) -> None:
        """A synthetic time grid needs at least two points."""

        with self.assertRaises(ValueError):
            generate_synthetic_transit_series(SyntheticTransitScenario(samples=1))


if __name__ == "__main__":
    unittest.main()
