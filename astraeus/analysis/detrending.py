"""Transit-preserving detrending.

Phase 0 change (PRD v4.1 §4.2 / §9): this module previously fell back
*SILENTLY* from ``wotan`` to a ``scipy.ndimage.median_filter`` running
median when ``wotan`` was missing or raised.  ``detrend()`` returned
only the flux array, so no field recorded which estimator ran, and a
bare ``except Exception: pass`` meant an *installed-but-failing* wotan
was also silently swapped for a different algorithm.

New behaviour:

* Availability is probed through :mod:`astraeus.core.capabilities`.
* The estimator actually used is reported via
  :meth:`DetrendingEngine.detrend_with_method`, and recorded on the
  detection result as ``detrend_method``.
* Production callers pass ``require_wotan=True`` to fail closed
  (:class:`~astraeus.core.capabilities.BackendUnavailable`) instead of
  silently substituting the median filter.  ``require_wotan=False``
  (the default) preserves the historical fallback for non-production
  diagnostic runs, but now *logs* the substitution at WARNING instead
  of hiding it.
* An installed-but-failing wotan is never silently swapped: the
  exception is logged at ERROR, and under ``require_wotan=True`` it is
  re-raised.

The detrending mathematics (window scaling, sigma clipping, biweight)
are UNCHANGED -- this phase fixes observability, not the algorithm.

P4-E addition (observability only, zero numeric change): the
transit-preserving window rule is parameterized as
:func:`window_for_duration` (window scales with a duration-like
timescale, clamped to the frozen 0.5/1.5-day bounds; arithmetic
identical to the previously inline expression) and
:meth:`DetrendingEngine.detrend_report` records which window rule
produced the value consumed by the estimator.
"""

import logging

import numpy as np

from astraeus.core import capabilities as _capabilities
from astraeus.core.capabilities import (
    BackendId,
    BackendUnavailable,
    get_logger,
)

logger = get_logger("detrending")

# Estimator identifiers reported on the detection result.
METHOD_WOTAN_BIWEIGHT = "wotan:biweight"
METHOD_SCIPY_MEDIAN = "scipy:median_filter"
METHOD_NONE = "none"

# P4-E: detrending-window provenance labels. These state WHICH window
# rule produced the ``window_length_days`` value consumed by the wotan /
# median estimators -- observability only, no numeric effect. The
# rotation-clamped labels mirror the frozen MIN/MAX bounds; the st_rad
# labels mirror the frozen stellar-radius thresholds (< 0.3 / >= 0.8).
WINDOW_SOURCE_ST_RAD_SMALL = "st_rad:small"
WINDOW_SOURCE_ST_RAD_INTERPOLATED = "st_rad:interpolated"
WINDOW_SOURCE_ST_RAD_LARGE = "st_rad:large"
WINDOW_SOURCE_ROTATION_SCALED = "rotation:scaled"
WINDOW_SOURCE_ROTATION_CLAMPED_MIN = "rotation:clamped-min"
WINDOW_SOURCE_ROTATION_CLAMPED_MAX = "rotation:clamped-max"

#: All documented ``window_source`` values (see :meth:`DetrendingEngine.detrend_report`).
WINDOW_SOURCES = frozenset(
    {
        WINDOW_SOURCE_ST_RAD_SMALL,
        WINDOW_SOURCE_ST_RAD_INTERPOLATED,
        WINDOW_SOURCE_ST_RAD_LARGE,
        WINDOW_SOURCE_ROTATION_SCALED,
        WINDOW_SOURCE_ROTATION_CLAMPED_MIN,
        WINDOW_SOURCE_ROTATION_CLAMPED_MAX,
    }
)


def window_for_duration(duration_days: float) -> float:
    """Transit-preserving detrending window for a duration-like timescale.

    The window scales linearly with the input duration (half its value)
    and is clamped to the frozen transit-preserving bounds
    (:data:`DetrendingEngine.MIN_TRANSIT_PRESERVING_WINDOW_DAYS` /
    :data:`DetrendingEngine.MAX_TRANSIT_PRESERVING_WINDOW_DAYS`,
    0.5/1.5 days). The 0.5 factor keeps the window several times wider
    than a typical transit so transits are preserved while slower
    stellar variability is removed.

    This is the P4-E parameterization of the previously inline
    ``min(MAX, max(MIN, duration * 0.5))`` expression: the arithmetic is
    byte-identical (same operation order, so even NaN edge behaviour is
    preserved) -- it only gives the rule a name, bounds documentation,
    and a unit-testable entry point. Zero numeric behavior change.

    Args:
        duration_days: Duration-like timescale in days. In the current
            call shape this is the stellar rotation period; future call
            shapes may pass a measured transit duration directly.

    Returns:
        Window length in days, always within [0.5, 1.5].
    """
    return min(
        DetrendingEngine.MAX_TRANSIT_PRESERVING_WINDOW_DAYS,
        max(
            DetrendingEngine.MIN_TRANSIT_PRESERVING_WINDOW_DAYS,
            duration_days * 0.5,
        ),
    )

# Probed through the module at CALL TIME (never a rebound copy) so the
# fail-closed gate and the branch decision cannot disagree: one source
# of truth, and a test/override patches exactly one name.
def _wotan_available() -> bool:
    return _capabilities.is_backend_available(BackendId.WOTAN)


class DetrendingEngine:
    MIN_TRANSIT_PRESERVING_WINDOW_DAYS = 0.5
    MAX_TRANSIT_PRESERVING_WINDOW_DAYS = 1.5

    @staticmethod
    def window_for_duration(duration_days: float) -> float:
        """Class-level alias of :func:`window_for_duration`.

        Provided so callers already holding ``DetrendingEngine`` do not
        need a second import; the module-level function is canonical and
        this delegates to it (single implementation, identical numbers).
        """
        return window_for_duration(duration_days)

    @staticmethod
    def _window_for_params(
        stellar_rotation_period_days: float, st_rad: float | None = None
    ) -> tuple[float, str]:
        """Resolve ``(window_length_days, window_source)`` for a detrend call.

        P4-E provenance helper. The VALUES reproduce the pre-P4-E inline
        branching bit-for-bit (the st_rad thresholds/threshold arithmetic
        and the rotation clamp are copied verbatim); only the adjacent
        ``window_source`` label is new. ``detrend_with_method`` routes its
        window computation through here, so every existing call shape
        feeds its estimator the identical number as before.
        """
        # Dynamic Window Scaling based on stellar radius (frozen values).
        if st_rad is not None:
            if st_rad < 0.3:
                return 0.5, WINDOW_SOURCE_ST_RAD_SMALL
            elif st_rad >= 0.8:
                return 2.0, WINDOW_SOURCE_ST_RAD_LARGE
            else:
                return (
                    0.5 + ((2.0 - 0.5) / (0.8 - 0.3)) * (st_rad - 0.3),
                    WINDOW_SOURCE_ST_RAD_INTERPOLATED,
                )
        raw = stellar_rotation_period_days * 0.5
        window_length_days = window_for_duration(stellar_rotation_period_days)
        if raw < DetrendingEngine.MIN_TRANSIT_PRESERVING_WINDOW_DAYS:
            return window_length_days, WINDOW_SOURCE_ROTATION_CLAMPED_MIN
        elif raw > DetrendingEngine.MAX_TRANSIT_PRESERVING_WINDOW_DAYS:
            return window_length_days, WINDOW_SOURCE_ROTATION_CLAMPED_MAX
        return window_length_days, WINDOW_SOURCE_ROTATION_SCALED

    @staticmethod
    def estimate_stellar_rotation(time: np.ndarray, flux: np.ndarray) -> float:
        from astropy.timeseries import LombScargle
        if len(time) > 2000:
            step = len(time) // 2000
            ls_time, ls_flux = time[::step], flux[::step]
        else:
            ls_time, ls_flux = time, flux
        frequency, power = LombScargle(ls_time, ls_flux).autopower(minimum_frequency=0.1, maximum_frequency=10.0)
        return float(1.0 / frequency[np.argmax(power)])

    @staticmethod
    def detrend(time: np.ndarray, flux: np.ndarray, stellar_rotation_period_days: float, st_rad: float = None, require_wotan: bool = False) -> np.ndarray:
        """Detrend, returning only the flattened flux.

        ``require_wotan=True`` fails closed when the preferred ``wotan``
        backend is unavailable or raises; see module docstring.
        """
        return DetrendingEngine.detrend_with_method(
            time, flux, stellar_rotation_period_days, st_rad=st_rad,
            require_wotan=require_wotan,
        )[0]

    @staticmethod
    def detrend_with_method(time: np.ndarray, flux: np.ndarray, stellar_rotation_period_days: float, st_rad: float = None, require_wotan: bool = False) -> tuple[np.ndarray, str]:
        """Detrend, returning ``(flux, method)``.

        ``method`` is one of :data:`METHOD_WOTAN_BIWEIGHT`,
        :data:`METHOD_SCIPY_MEDIAN` or :data:`METHOD_NONE`, so callers
        can record which estimator actually produced the result and
        never represent a fallback as the preferred backend.
        """
        # Preserve float64 precision
        time = np.asarray(time, dtype=np.float64)
        flux = np.asarray(flux, dtype=np.float64)

        # Asymmetric Sigma Clipping: Remove positive anomalies (> +3 sigma)
        median_flux = np.nanmedian(flux)
        std_flux = np.nanstd(flux)
        positive_outliers = flux > (median_flux + 3 * std_flux)
        clean_flux = np.copy(flux)
        clean_flux[positive_outliers] = median_flux

        # Dynamic Window Scaling based on stellar radius
        # P4-E: routed through _window_for_params, which reproduces the
        # pre-P4-E inline values bit-for-bit and additionally reports
        # WHICH rule produced them (see detrend_report). The estimator
        # receives the identical number as before this bucket.
        window_length_days, _window_source = DetrendingEngine._window_for_params(
            stellar_rotation_period_days, st_rad=st_rad
        )

        # ---- Preferred backend: wotan biweight ---------------------------
        # A missing wotan in a *production* run is a hard failure, not a
        # silent substitution (PRD §9). There is exactly ONE availability
        # probe here, used for both the fail-closed gate and the branch
        # decision, so the two can never disagree.
        wotan_available = _wotan_available()
        if require_wotan and not wotan_available:
            # Structured, diagnosable failure -- never a silent swap to
            # the scipy estimator.
            _capabilities.require_backend(BackendId.WOTAN)

        if wotan_available:
            try:
                from wotan import flatten as wotan_flatten
                flatten_flux, trend_flux = wotan_flatten(
                    time, clean_flux,
                    window_length=window_length_days,
                    method='biweight',
                    return_trend=True
                )
                nan_mask = np.isnan(flatten_flux)
                if nan_mask.any():
                    flatten_flux[nan_mask] = 1.0
                return flatten_flux, METHOD_WOTAN_BIWEIGHT
            except Exception as e:
                # An INSTALLED-but-failing backend must not be silently
                # transformed into a different algorithm (PRD §9). Log it
                # loudly, and re-raise in production runs.
                logger.error(
                    "[WOTAN] wotan.flatten raised %s: %s. The installed "
                    "backend did not produce a result.", type(e).__name__, e,
                )
                if require_wotan:
                    raise
                logger.warning(
                    "[WOTAN] Falling back to scipy median filter for this "
                    "non-production run. The result is NOT equivalent to the "
                    "preferred wotan biweight estimator."
                )

        # A production run with wotan missing already failed closed inside
        # require_backend above; reaching this branch means the historical
        # non-production fallback is in effect, which must be observable.
        if not wotan_available:
            logger.warning(
                "[WOTAN] wotan is not installed; using the scipy median "
                "filter fallback. This non-production substitution changes "
                "the detrending estimator and must not be reported as a "
                "wotan result."
            )

        # ---- Fallback: scipy running median ------------------------------
        from scipy.ndimage import median_filter
        dt = float(np.median(np.diff(time)))
        if dt > 0:
            window_length_points = int(window_length_days / dt)
            if window_length_points % 2 == 0:
                window_length_points += 1
            window_length_points = max(3, window_length_points)
            trend = median_filter(clean_flux, size=window_length_points)
            trend[trend == 0] = 1.0
            return clean_flux / trend, METHOD_SCIPY_MEDIAN

        return clean_flux, METHOD_NONE

    @staticmethod
    def detrend_report(
        time: np.ndarray,
        flux: np.ndarray,
        stellar_rotation_period_days: float,
        st_rad: float = None,
        require_wotan: bool = False,
    ) -> dict:
        """Detrend provenance report (P4-E observability, no new physics).

        Runs the identical pipeline as :meth:`detrend_with_method` and
        returns ``{"method", "window_days", "window_source"}``:

        * ``method`` -- the estimator label, always equal to what
          ``detrend_with_method`` returns for the same inputs;
        * ``window_days`` -- the ``window_length_days`` value actually
          consumed by that estimator;
        * ``window_source`` -- which window rule produced it (one of the
          ``WINDOW_SOURCE_*`` constants: ``st_rad:small`` /
          ``st_rad:interpolated`` / ``st_rad:large`` for the frozen
          stellar-radius branch, ``rotation:scaled`` /
          ``rotation:clamped-min`` / ``rotation:clamped-max`` for the
          transit-preserving rotation clamp).

        Tuple shapes are untouched: ``detrend`` still returns a bare
        array and ``detrend_with_method`` still returns a 2-tuple. The
        fail-closed ``require_wotan`` gate propagates unchanged.
        """
        _, method = DetrendingEngine.detrend_with_method(
            time, flux, stellar_rotation_period_days, st_rad=st_rad,
            require_wotan=require_wotan,
        )
        window_length_days, window_source = DetrendingEngine._window_for_params(
            stellar_rotation_period_days, st_rad=st_rad
        )
        return {
            "method": method,
            "window_days": window_length_days,
            "window_source": window_source,
        }
