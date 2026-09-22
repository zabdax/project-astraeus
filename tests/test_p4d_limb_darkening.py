"""P4-D: limb-darkening single source of truth (forward model only).

TDD tests for ``astraeus.core.limb_darkening``. Centralizes provenance,
not physics: every default here must reproduce legacy numbers bit-for-bit.

Scope notes (frozen, do NOT reopen):
- ``astraeus/core/orchestrator.py`` (batman-or-trapezoid subtraction) is
  FROZEN and untouched; its ``metadata['u'] else [0.1, 0.3]`` fallback is
  referenced here only as a documented value assertion.
- ``astraeus/core/sensitivity_engine.py`` is a uniform-disk fast model
  with no limb darkening; consulted only, never modified.
"""

from __future__ import annotations

import inspect
import unittest

import numpy as np
from astropy import units as u

from astraeus.core import limb_darkening as ld
from astraeus.core.limb_darkening import resolve, validate_coefficients
from astraeus.core.transit_model import (
    generate_geometric_transit,
    generate_model_flux,
)


class ForwardDefaultConstantsTests(unittest.TestCase):
    """The module's documented defaults must match the legacy numbers."""

    def test_forward_model_signature_defaults_are_uniform_disk(self) -> None:
        self.assertEqual(ld.FORWARD_MODEL_DEFAULT_U1, 0.0)
        self.assertEqual(ld.FORWARD_MODEL_DEFAULT_U2, 0.0)

    def test_stellar_fallback_matches_frozen_legacy_value(self) -> None:
        # Historical ASTRAEUS fallback, frozen in orchestrator.py
        # (metadata['u'] else [0.1, 0.3]) and synthetic.py injection.
        # Asserted here as a value lock, not an import (both frozen files
        # are deliberately left untouched by P4-D).
        self.assertEqual(ld.DEFAULT_U1, 0.1)
        self.assertEqual(ld.DEFAULT_U2, 0.3)

    def test_forward_defaults_referenced_by_transit_model(self) -> None:
        sig = inspect.signature(generate_geometric_transit)
        self.assertEqual(
            sig.parameters["u1"].default, ld.FORWARD_MODEL_DEFAULT_U1
        )
        self.assertEqual(
            sig.parameters["u2"].default, ld.FORWARD_MODEL_DEFAULT_U2
        )
        sig_flux = inspect.signature(generate_model_flux)
        self.assertEqual(
            sig_flux.parameters["u1"].default, ld.FORWARD_MODEL_DEFAULT_U1
        )
        self.assertEqual(
            sig_flux.parameters["u2"].default, ld.FORWARD_MODEL_DEFAULT_U2
        )


class LegacyNumbersBitForBitTests(unittest.TestCase):
    """Forward-model defaults must reproduce legacy outputs exactly."""

    def test_geometric_transit_default_equals_explicit_zeros(self) -> None:
        default_drop = generate_geometric_transit(
            0.5 * u.R_sun, 1.0 * u.R_sun, 0.1 * u.R_sun
        ).to_value(u.dimensionless_unscaled)
        explicit_drop = generate_geometric_transit(
            0.5 * u.R_sun, 1.0 * u.R_sun, 0.1 * u.R_sun, u1=0.0, u2=0.0
        ).to_value(u.dimensionless_unscaled)
        self.assertEqual(default_drop, explicit_drop)
        # Legacy uniform-disk number: fully superimposed planet blocks
        # exactly its area ratio (locked by test_transit_model.py).
        self.assertAlmostEqual(default_drop, 0.01, places=9)

    def test_model_flux_default_equals_explicit_zeros(self) -> None:
        time = np.linspace(0.0, 6.0, 7) * u.day
        kwargs = dict(
            period=3.0 * u.day,
            semi_major_axis=0.05 * u.AU,
            eccentricity=0.0 * u.dimensionless_unscaled,
            inclination=90.0 * u.deg,
            R_star=1.0 * u.R_sun,
            R_planet=0.1 * u.R_sun,
        )
        default_flux = generate_model_flux(time=time, **kwargs)
        explicit_flux = generate_model_flux(time=time, u1=0.0, u2=0.0, **kwargs)
        np.testing.assert_array_equal(default_flux, explicit_flux)


class ValidationTests(unittest.TestCase):
    """Unphysical coefficients must be rejected; legacy ones accepted."""

    def test_accepts_legacy_coefficients(self) -> None:
        validate_coefficients(0.0, 0.0)  # uniform-disk legacy default
        validate_coefficients(0.1, 0.3)  # stellar fallback
        validate_coefficients(*resolve().as_tuple())  # resolve() output

    def test_rejects_negative_u1(self) -> None:
        with self.assertRaises(ValueError):
            validate_coefficients(-0.1, 0.3)

    def test_rejects_non_positive_limb_intensity(self) -> None:
        # I(mu=0)/I(1) = 1 - u1 - u2 must stay positive.
        with self.assertRaises(ValueError):
            validate_coefficients(0.5, 0.5)
        with self.assertRaises(ValueError):
            validate_coefficients(0.8, 0.4)

    def test_rejects_non_finite(self) -> None:
        with self.assertRaises(ValueError):
            validate_coefficients(float("nan"), 0.3)
        with self.assertRaises(ValueError):
            validate_coefficients(0.1, float("inf"))
        with self.assertRaises(ValueError):
            validate_coefficients(float("-inf"), 0.3)

    def test_rejects_non_numeric(self) -> None:
        with self.assertRaises((TypeError, ValueError)):
            validate_coefficients("not-a-number", 0.3)
        with self.assertRaises((TypeError, ValueError)):
            validate_coefficients(None, 0.3)


class ResolveProvenanceTests(unittest.TestCase):
    """resolve() must be explicit about where coefficients come from."""

    def test_unknown_star_returns_documented_defaults_explicitly(self) -> None:
        res = resolve()
        self.assertEqual((res.u1, res.u2), (ld.DEFAULT_U1, ld.DEFAULT_U2))
        # Explicit, not silent: the provenance must say it is a fallback.
        self.assertIn("fallback", res.source.lower() + res.provenance.lower())
        self.assertTrue(res.provenance)  # non-empty documentation string

    def test_known_star_params_still_return_explicit_fallback(self) -> None:
        # No coefficient tables ship in P4-D; stellar parameters are
        # accepted (forward-compatible) but honestly reported as
        # unresolved fallbacks, never silently treated as fitted values.
        res = resolve(st_teff=5778.0, logg=4.44, metallicity=0.0, band="Kepler")
        self.assertEqual((res.u1, res.u2), (ld.DEFAULT_U1, ld.DEFAULT_U2))
        self.assertIn("fallback", res.source.lower() + res.provenance.lower())

    def test_caller_supplied_coefficients_validated_and_labelled(self) -> None:
        res = resolve(u1=0.2, u2=0.25)
        self.assertEqual((res.u1, res.u2), (0.2, 0.25))
        self.assertIn("caller", res.source.lower())
        with self.assertRaises(ValueError):
            resolve(u1=-0.5, u2=0.3)

    def test_partial_caller_supply_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve(u1=0.2)
        with self.assertRaises(ValueError):
            resolve(u2=0.25)

    def test_result_unpacks_like_legacy_pair(self) -> None:
        u1, u2 = resolve()
        self.assertEqual((u1, u2), (ld.DEFAULT_U1, ld.DEFAULT_U2))


class SensitivityEngineUntouchedTests(unittest.TestCase):
    """Consult-only confirmation: the fast model has no limb darkening."""

    def test_sensitivity_engine_has_no_limb_darkening(self) -> None:
        from astraeus.core import sensitivity_engine

        sig = inspect.signature(sensitivity_engine.get_model_curve)
        for name in ("u1", "u2", "limb", "limb_darkening"):
            self.assertNotIn(name, sig.parameters)
        source = inspect.getsource(sensitivity_engine.get_model_curve)
        self.assertIn("uniform", source.lower())


if __name__ == "__main__":
    unittest.main()
