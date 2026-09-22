"""Quadratic limb-darkening single source of truth (P4-D, forward model).

This module centralizes *provenance*, not physics. Every number here
reproduces a legacy ASTRAEUS value bit-for-bit; no light-curve output
changes by adopting it.

Two documented coefficient sets (do NOT conflate them):

- ``FORWARD_MODEL_DEFAULT_U1/U2 = (0.0, 0.0)`` — the uniform-disk
  (no limb darkening) legacy signature defaults of
  :func:`astraeus.core.transit_model.generate_geometric_transit` and
  :func:`astraeus.core.transit_model.generate_model_flux`. Existing
  tests (e.g. ``tests/test_transit_model.py``) call the forward model
  without coefficients and lock the uniform-disk numbers, so these
  stay exactly zero.
- ``DEFAULT_U1/U2 = (0.1, 0.3)`` — the historical ASTRAEUS stellar
  fallback for *unknown* stars, identical to the frozen subtraction
  fallback in ``astraeus/core/orchestrator.py``
  (``metadata['u'] else [0.1, 0.3]``) and the injection default in
  ``astraeus/simulation/synthetic.py``. Provenance: a generic
  solar-type placeholder for a Kepler-like optical bandpass. It is NOT
  a fitted measurement and NOT interpolated from published tables
  (e.g. Claret); ``resolve()`` reports it explicitly as a fallback so
  no caller can mistake it for a stellar measurement.

Scope: P4-D covers the FORWARD transit model only. The subtraction
implementation in ``orchestrator.py`` is FROZEN (DEC-LIC: ``batman``
stays optional) and must keep reading its own coefficients.

Physical validation (:func:`validate_coefficients`) enforces, for the
quadratic law ``I(mu)/I(1) = 1 - u1*(1-mu) - u2*(1-mu)**2``:

- both coefficients finite (no NaN/inf);
- ``u1 >= 0`` (exactly zero = the uniform-disk legacy case is allowed;
  strictly negative linear terms are unphysical for normal stars);
- ``u1 + u2 < 1`` so the limb intensity ``I(0)/I(1)`` stays positive.

``resolve()`` is the single entry point: stellar parameters are
accepted for forward compatibility but, until coefficient tables ship
in a future bucket, any unrecognized star explicitly returns the
documented fallback (labelled, never silent). Caller-supplied
coefficients are validated and labelled as caller-supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

__all__ = [
    "DEFAULT_U1",
    "DEFAULT_U2",
    "DEFAULT_PROVENANCE",
    "FORWARD_MODEL_DEFAULT_U1",
    "FORWARD_MODEL_DEFAULT_U2",
    "FORWARD_MODEL_DEFAULT_PROVENANCE",
    "ResolvedLimbDarkening",
    "resolve",
    "validate_coefficients",
]

# ---------------------------------------------------------------------------
# Documented defaults.
# ---------------------------------------------------------------------------

#: Historical ASTRAEUS stellar fallback for unknown stars (quadratic law).
#: Generic solar-type placeholder for a Kepler-like optical bandpass —
#: NOT a measurement, NOT from Claret tables. Value-locked to the frozen
#: subtraction fallback (orchestrator.py ``metadata['u'] else [0.1, 0.3]``)
#: and the synthetic-injection default (synthetic.py).
DEFAULT_U1 = 0.1
DEFAULT_U2 = 0.3

#: Provenance string for the stellar fallback (see module docstring).
DEFAULT_PROVENANCE = (
    "ASTRAEUS historical fallback (0.1, 0.3): generic solar-type "
    "placeholder for a Kepler-like optical bandpass, matching the frozen "
    "orchestrator subtraction fallback and synthetic-injection default. "
    "Not a fitted measurement; not interpolated from published tables."
)

#: Legacy forward-model signature defaults (uniform disk = no limb
#: darkening). Locked by tests/test_transit_model.py; must stay zero.
FORWARD_MODEL_DEFAULT_U1 = 0.0
FORWARD_MODEL_DEFAULT_U2 = 0.0

#: Provenance string for the uniform-disk forward defaults.
FORWARD_MODEL_DEFAULT_PROVENANCE = (
    "Uniform-disk legacy (0.0, 0.0): no limb darkening. Preserves the "
    "historical generate_geometric_transit/generate_model_flux signature "
    "defaults locked by tests/test_transit_model.py."
)


def validate_coefficients(u1: float, u2: float) -> tuple[float, float]:
    """Validate quadratic limb-darkening coefficients.

    Returns the ``(float(u1), float(u2))`` pair so validated values can
    be forwarded directly. Raises ``ValueError`` for non-finite,
    negative-``u1``, or limb-intensity-violating (``u1 + u2 >= 1``)
    inputs, and ``TypeError``-as-``ValueError`` for non-numeric input.
    """
    try:
        u1_f = float(u1)
        u2_f = float(u2)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Limb-darkening coefficients must be numeric, got u1={u1!r}, u2={u2!r}."
        ) from exc
    if not (isfinite(u1_f) and isfinite(u2_f)):
        raise ValueError(
            f"Limb-darkening coefficients must be finite, got u1={u1!r}, u2={u2!r}."
        )
    if u1_f < 0.0:
        raise ValueError(
            f"Unphysical limb darkening: u1 must be >= 0 (got {u1_f})."
        )
    if u1_f + u2_f >= 1.0:
        raise ValueError(
            "Unphysical limb darkening: u1 + u2 must be < 1 so the limb "
            f"intensity stays positive (got u1={u1_f}, u2={u2_f})."
        )
    return (u1_f, u2_f)


@dataclass(frozen=True)
class ResolvedLimbDarkening:
    """A resolved coefficient pair plus explicit provenance.

    ``source`` is a short machine-readable label (``"fallback:…"`` or
    ``"caller-supplied"``); ``provenance`` is the human-readable record.
    Iterating/unpacking yields ``(u1, u2)`` so existing ``u1, u2 = …``
    call patterns keep working.
    """

    u1: float
    u2: float
    source: str
    provenance: str

    def __iter__(self):  # type: ignore[no-untyped-def]
        yield self.u1
        yield self.u2

    def as_tuple(self) -> tuple[float, float]:
        """Return the plain ``(u1, u2)`` coefficient pair."""
        return (self.u1, self.u2)


def resolve(
    st_teff: float | None = None,
    logg: float | None = None,
    metallicity: float | None = None,
    band: str | None = None,
    *,
    u1: float | None = None,
    u2: float | None = None,
) -> ResolvedLimbDarkening:
    """Resolve quadratic limb-darkening coefficients (P4-D entry point).

    - Caller-supplied ``u1``/``u2`` (both required together) are
      validated and returned labelled ``"caller-supplied"``.
    - Otherwise the documented ``(DEFAULT_U1, DEFAULT_U2)`` fallback is
      returned, explicitly labelled ``"fallback:…"`` — including when
      stellar parameters are given, because no coefficient tables ship
      in P4-D (a future bucket may interpolate e.g. Claret tables).
    """
    if (u1 is None) != (u2 is None):
        raise ValueError(
            "Caller-supplied limb darkening requires both u1 and u2 together."
        )
    if u1 is not None and u2 is not None:
        u1_f, u2_f = validate_coefficients(u1, u2)
        return ResolvedLimbDarkening(
            u1=u1_f,
            u2=u2_f,
            source="caller-supplied",
            provenance=(
                "Caller-supplied coefficients, validated "
                "(finite, u1 >= 0, u1 + u2 < 1)."
            ),
        )
    if (
        st_teff is None
        and logg is None
        and metallicity is None
        and band is None
    ):
        source = "fallback:unknown-star"
        detail = "no stellar parameters given"
    else:
        source = "fallback:unrecognized-star"
        detail = (
            f"no coefficient tables ship in P4-D; stellar parameters "
            f"(Teff={st_teff}, logg={logg}, [Fe/H]={metallicity}, "
            f"band={band}) recorded but unresolved"
        )
    return ResolvedLimbDarkening(
        u1=DEFAULT_U1,
        u2=DEFAULT_U2,
        source=source,
        provenance=f"{DEFAULT_PROVENANCE} Applied as {source} ({detail}).",
    )
