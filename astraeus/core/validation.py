"""Validation helpers for physics quantities and orbital parameters."""

from __future__ import annotations

import numpy as np
from astropy import units as u

from astraeus.core.constants import (
    BOUND_ECCENTRICITY_MAXIMUM,
    BOUND_ECCENTRICITY_MINIMUM,
    POSITIVE_QUANTITY_MINIMUM,
)


def require_quantity(value: u.Quantity, parameter_name: str) -> u.Quantity:
    """Return an Astropy quantity or raise a clear type error.

    ASTRAEUS physics functions use units as part of their contracts, not as
    comments beside unitless numbers. Centralizing this check keeps model code
    focused on physics while still failing fast when callers pass bare values.
    """

    if not isinstance(value, u.Quantity):
        raise TypeError(f"{parameter_name} must be an astropy.units.Quantity.")

    return value


def require_convertible_unit(
    value: u.Quantity,
    expected_unit: u.UnitBase,
    parameter_name: str,
) -> u.Quantity:
    """Validate that a quantity can be converted to the expected unit family.

    Physics derivation and assumptions:
    This helper does not implement a physical model. It enforces dimensional
    consistency before a model evaluates equations such as ``M = n t`` or
    ``x = a(cos(E) - e)``. The expected unit represents the geometric role of
    the parameter: angles for anomalies, times for periods, and lengths for
    orbital axes.
    """

    quantity = require_quantity(value, parameter_name)
    quantity.to(expected_unit)
    return quantity


def require_positive_quantity(value: u.Quantity, parameter_name: str) -> u.Quantity:
    """Validate that a physical scale is strictly positive.

    Physics derivation and assumptions:
    Closed Keplerian periods and semi-major axes are positive scales. A zero
    or negative value has no meaning for the bound two-body ellipse assumed by
    the orbital models, so it is rejected before any derived anomaly or
    Cartesian coordinate is calculated.
    """

    quantity = require_quantity(value, parameter_name)

    if np.any(quantity.to_value(quantity.unit) <= POSITIVE_QUANTITY_MINIMUM):
        raise ValueError(f"{parameter_name} must be strictly positive.")

    return quantity


def require_non_negative_quantity(
    value: u.Quantity,
    parameter_name: str,
) -> u.Quantity:
    """Validate that a physical distance or scale is zero or positive.

    Physics derivation and assumptions:
    Projected separations and geometric distances are magnitudes, so negative
    values have no physical meaning. Zero is valid for coincident centers,
    unlike radius and orbital-scale parameters that must remain strictly
    positive.
    """

    quantity = require_quantity(value, parameter_name)

    if np.any(quantity.to_value(quantity.unit) < POSITIVE_QUANTITY_MINIMUM):
        raise ValueError(f"{parameter_name} must be non-negative.")

    return quantity


def require_bound_eccentricity(eccentricity: u.Quantity) -> u.Quantity:
    """Validate eccentricity for a bound Keplerian ellipse.

    Physics derivation and assumptions:
    The current orbital model is restricted to closed two-body ellipses. That
    regime is defined by ``0 <= e < 1``. Parabolic and hyperbolic trajectories
    require different anomaly definitions and are intentionally outside this
    helper's contract.
    """

    quantity = require_convertible_unit(
        eccentricity,
        u.dimensionless_unscaled,
        "eccentricity",
    )
    eccentricity_value = quantity.to_value(u.dimensionless_unscaled)

    if np.any(eccentricity_value < BOUND_ECCENTRICITY_MINIMUM) or np.any(
        eccentricity_value >= BOUND_ECCENTRICITY_MAXIMUM
    ):
        raise ValueError("eccentricity must satisfy 0 <= eccentricity < 1.")

    return quantity
