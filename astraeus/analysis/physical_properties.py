import math
import numpy as np

# Solar radius in Earth radii — see derive() below for the canonical use.
R_SUN_TO_R_EARTH = 109.2

class PhysicalPropertiesEngine:
    @staticmethod
    def derive(period_days: float, transit_depth_fraction: float, st_rad: float, st_teff: float, st_mass: float, sy_jmag: float) -> dict:
        planet_radius_earth = 0.0

        if transit_depth_fraction > 0 and st_rad > 0:
            planet_radius_earth = float(st_rad * math.sqrt(transit_depth_fraction) * R_SUN_TO_R_EARTH)

        bond_albedo = 0.3
        equilibrium_temp_k = 0.0

        if period_days > 0 and st_teff > 0 and st_mass > 0 and st_rad > 0:
            period_yr = period_days / 365.25
            semi_major_axis_au = (st_mass * period_yr ** 2) ** (1.0 / 3.0)
            stellar_radius_au = st_rad * 0.00465047
            if semi_major_axis_au > 0:
                equilibrium_temp_k = float(
                    st_teff * np.sqrt(stellar_radius_au / (2.0 * semi_major_axis_au)) * (1.0 - bond_albedo) ** 0.25
                )

        jwst_tsm_score = 0.0
        if planet_radius_earth > 0 and equilibrium_temp_k > 0 and st_rad > 0:
            # Audit fix M5 (2026-08-21): the Kempton et al. 2018 TSM scale
            # factors and the R^2.06 mass proxy are calibrated/defined only
            # for R < 10 R_Earth; the TSM is *undefined* for giant planets
            # (R >= 10 R_Earth), which are reported as 0.0 here (the dict's
            # established "not computable" sentinel).
            if planet_radius_earth >= 10.0:
                jwst_tsm_score = 0.0
            else:
                if planet_radius_earth < 1.5:
                    tsm_scale = 0.190
                elif planet_radius_earth < 2.75:
                    tsm_scale = 1.26
                elif planet_radius_earth < 4.0:
                    tsm_scale = 1.28
                else:
                    # 1.15 scale + R^2.06 mass law valid for 4 <= R < 10
                    # R_Earth only (see regime note above).
                    tsm_scale = 1.15

                planet_mass_earth = planet_radius_earth ** 2.06
                jwst_tsm_score = float(
                    tsm_scale * (planet_radius_earth ** 3 * equilibrium_temp_k) /
                    (planet_mass_earth * st_rad ** 2) * 10.0 ** (-sy_jmag / 5.0)
                )

        return {
            'planet_radius_earth': round(planet_radius_earth, 4),
            'equilibrium_temp_k': round(equilibrium_temp_k, 2),
            'jwst_tsm_score': round(jwst_tsm_score, 4)
        }

    @staticmethod
    def expected_occultation_depth_ppm(
        planet_radius_earth: float,
        stellar_radius_solar: float,
        planet_equilibrium_temp_k: float,
        stellar_teff_k: float,
    ) -> float | None:
        """Estimate the expected thermal secondary-eclipse depth in ppm.

        The flux ratio at secondary eclipse is the planet-to-star surface
        brightness ratio:

            depth = (R_p / R_star)^2 * B(T_planet, band) / B(T_star, band)

        In the Rayleigh-Jeans limit (B ∝ T — the relevant regime when the
        observation bandpass is longward of the stellar peak and the planet
        radiates its re-processed stellar light as a thermalised blackbody),
        the bandpass dependence collapses to a pure temperature ratio and
        the depth simplifies to::

            depth ≈ (R_p / R_star)^2 * (T_planet / T_star)

        which is what this function returns, converted to ppm.

        The Rayleigh-Jeans approximation is a *conservative lower bound*
        for IR observations and an *upper bound* for very blue bandpasses
        (where the planet's Wien-tail emission is exponentially suppressed
        anyway).  It avoids the false-eclipsing-binary misclassification
        of a real hot, large planet that the old flat 800 ppm constant
        produced.

        Parameters
        ----------
        planet_radius_earth : float
            Planet radius in Earth radii. Must be positive.
        stellar_radius_solar : float
            Stellar radius in Solar radii. Must be positive.
        planet_equilibrium_temp_k : float
            Day-side equilibrium temperature of the planet in Kelvin. Must
            be positive.
        stellar_teff_k : float
            Stellar effective temperature in Kelvin. Must be positive.

        Returns
        -------
        float | None
            Expected occultation depth in ppm, or ``None`` if any required
            input is missing or non-positive. The caller is responsible
            for substituting the fallback constant
            ``VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM`` when ``None`` is
            returned, and for surfacing the fact that the fallback was
            used in the vetting result dict.
        """
        if (
            planet_radius_earth <= 0
            or stellar_radius_solar <= 0
            or planet_equilibrium_temp_k <= 0
            or stellar_teff_k <= 0
        ):
            return None

        # R_p / R_star — convert Earth radii to Solar radii first so the
        # ratio is dimensionless, matching the surface-brightness ratio.
        radius_ratio_sq = (planet_radius_earth / (stellar_radius_solar * R_SUN_TO_R_EARTH)) ** 2

        # Cap at 1.0: a planet cannot emit more thermal flux than the
        # star in any bandpass without violating energy conservation. If
        # archive values are physically inconsistent (e.g. T_eq > T_eff
        # due to bad metadata), still refuse to predict a depth that
        # would imply a self-luminous companion.
        temp_ratio = min(planet_equilibrium_temp_k / stellar_teff_k, 1.0)

        return float(radius_ratio_sq * temp_ratio * 1.0e6)
