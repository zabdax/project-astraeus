/**
 * Orbit geometry for the Simulate workbench (P3 refresh).
 * Pure Kepler math over numbers: positions for top-down + edge-on
 * panels, impact parameter, and circular transit duration. Stellar
 * defaults (1 Msun, 1 Rsun) are stated assumptions, not measurements.
 */

export interface OrbitElements {
  period_days: number;
  semi_major_axis_au: number;
  eccentricity: number;
  inclination_deg: number;
  stellar_radius_rsun?: number;
}

export interface OrbitPoint {
  x_au: number; // orbital plane x
  y_au: number; // orbital plane y
  sky_x: number; // sky-projected x (units of R*)
  sky_z: number; // sky-projected z (units of R*, +away from observer)
}

const RSUN_AU = 0.00465047;

function solveKepler(meanAnomaly: number, ecc: number): number {
  let e = meanAnomaly;
  for (let i = 0; i < 12; i++) {
    e -= (e - ecc * Math.sin(e) - meanAnomaly) / (1 - ecc * Math.cos(e));
  }
  return e;
}

/** Sample the orbit at n points (equal mean anomaly). Star at origin. */
export function sampleOrbit(el: OrbitElements, n = 256): OrbitPoint[] {
  const rStar = el.stellar_radius_rsun ?? 1.0;
  const inc = (el.inclination_deg * Math.PI) / 180;
  const pts: OrbitPoint[] = [];
  for (let i = 0; i < n; i++) {
    const m = (i / n) * Math.PI * 2;
    const e = solveKepler(m, el.eccentricity);
    const nu = 2 * Math.atan2(
      Math.sqrt(1 + el.eccentricity) * Math.sin(e / 2),
      Math.sqrt(1 - el.eccentricity) * Math.cos(e / 2),
    );
    const r = (el.semi_major_axis_au * (1 - el.eccentricity ** 2)) / (1 + el.eccentricity * Math.cos(nu));
    const x = r * Math.cos(nu);
    const y = r * Math.sin(nu);
    pts.push({
      x_au: x,
      y_au: y,
      sky_x: x / (rStar * RSUN_AU),
      sky_z: (y * Math.sin(inc)) / (rStar * RSUN_AU),
    });
  }
  return pts;
}

/** Semi-major axis from Kepler's third law (circular; solar default stated). */
export function semiMajorAxisAu(periodDays: number, stellarMassSolar = 1.0): number {
  return (stellarMassSolar * (periodDays / 365.25) ** 2) ** (1 / 3);
}

/** Impact parameter for a circular orbit (edge-on = 0). */
export function impactParameter(semiMajorAxisAu: number, inclinationDeg: number, stellarRadiusRsun = 1.0): number {
  const aRs = semiMajorAxisAu / (stellarRadiusRsun * RSUN_AU);
  return Math.abs(aRs * Math.cos((inclinationDeg * Math.PI) / 180));
}

/** Circular transit duration (days) from geometry; NaN when no transit. */
export function circularDurationDays(
  periodDays: number,
  radiusRatio: number,
  semiMajorAxisAu: number,
  inclinationDeg: number,
  stellarRadiusRsun = 1.0,
): number {
  const aRs = semiMajorAxisAu / (stellarRadiusRsun * RSUN_AU);
  const b = Math.abs(aRs * Math.cos((inclinationDeg * Math.PI) / 180));
  if (b >= 1 + radiusRatio) return NaN;
  const arg = Math.sqrt(Math.max(0, (1 + radiusRatio) ** 2 - b ** 2)) / (aRs * Math.sin((inclinationDeg * Math.PI) / 180));
  if (!(arg > 0) || arg >= 1) return NaN;
  return (periodDays / Math.PI) * Math.asin(arg);
}
