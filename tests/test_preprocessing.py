"""Tests for light-curve preprocessing utilities."""

from __future__ import annotations

import unittest

import numpy as np

from astraeus.data.preprocessing import inject_gaussian_noise


class GaussianNoiseInjectionTests(unittest.TestCase):
    """Tests for reproducible Gaussian white-noise injection."""

    def test_seed_makes_noise_reproducible(self) -> None:
        """Using the same seed should produce identical noisy light curves."""

        flux = np.array([1.0, 0.99, 0.98, 1.0])

        first = inject_gaussian_noise(flux, snr=100.0, seed=123)
        second = inject_gaussian_noise(flux, snr=100.0, seed=123)

        np.testing.assert_allclose(first, second)

    def test_noise_scale_uses_target_snr(self) -> None:
        """Noise should be drawn with sigma equal to signal level over SNR."""

        flux = np.ones(10_000)
        snr = 50.0
        noisy_flux = inject_gaussian_noise(flux, snr=snr, seed=456)
        measured_std = np.std(noisy_flux - flux)

        self.assertAlmostEqual(measured_std, 1.0 / snr, places=3)

    def test_snr_must_be_positive(self) -> None:
        """A target SNR must describe a positive signal-to-noise ratio."""

        with self.assertRaises(ValueError):
            inject_gaussian_noise(np.ones(3), snr=0.0)


if __name__ == "__main__":
    unittest.main()
