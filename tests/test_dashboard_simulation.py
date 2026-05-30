"""Tests for dashboard simulation orchestration."""

from __future__ import annotations

import unittest

import numpy as np

from astraeus.dashboard import (
    DashboardTransitScenario,
    generate_dashboard_simulation,
)


class DashboardSimulationTests(unittest.TestCase):
    """Regression tests for dashboard-facing simulation boundaries."""

    def test_simulation_arrays_are_aligned(self) -> None:
        """A dashboard scenario should produce aligned orbit and flux arrays."""

        simulation = generate_dashboard_simulation(
            DashboardTransitScenario(
                radius_ratio=0.1,
                period_days=3.0,
                eccentricity=0.1,
                inclination_degrees=89.0,
                snr=200,
                samples=256,
            )
        )

        self.assertEqual(simulation.time_days.shape, (256,))
        self.assertEqual(simulation.x_rsun.shape, (256,))
        self.assertEqual(simulation.y_rsun.shape, (256,))
        self.assertEqual(simulation.z_rsun.shape, (256,))
        self.assertEqual(simulation.theoretical_flux.shape, (256,))
        self.assertEqual(simulation.observed_flux.shape, (256,))

    def test_residuals_are_derived_from_flux_arrays(self) -> None:
        """Residuals should remain a derived view of observed minus theoretical."""

        simulation = generate_dashboard_simulation(
            DashboardTransitScenario(
                radius_ratio=0.08,
                period_days=2.5,
                eccentricity=0.0,
                inclination_degrees=90.0,
                snr=300,
                samples=128,
            )
        )

        np.testing.assert_allclose(
            simulation.residuals,
            simulation.observed_flux - simulation.theoretical_flux,
        )

    def test_same_scenario_is_reproducible(self) -> None:
        """Stable scenario seeds should make repeated dashboard runs identical."""

        scenario = DashboardTransitScenario(
            radius_ratio=0.12,
            period_days=4.0,
            eccentricity=0.2,
            inclination_degrees=88.5,
            snr=150,
            samples=128,
        )

        first = generate_dashboard_simulation(scenario)
        second = generate_dashboard_simulation(scenario)

        np.testing.assert_allclose(first.observed_flux, second.observed_flux)

    def test_invalid_dashboard_scenario_is_rejected(self) -> None:
        """Scenario validation should catch invalid UI-domain inputs."""

        scenario = DashboardTransitScenario(
            radius_ratio=0.0,
            period_days=3.0,
            eccentricity=0.0,
            inclination_degrees=90.0,
            snr=100,
        )

        with self.assertRaises(ValueError):
            generate_dashboard_simulation(scenario)


if __name__ == "__main__":
    unittest.main()
