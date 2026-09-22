import { describe, expect, it } from "vitest";
import { circularDurationDays, impactParameter, sampleOrbit, semiMajorAxisAu } from "./orbit";

describe("sampleOrbit", () => {
  it("holds constant radius on a circular orbit", () => {
    const pts = sampleOrbit({ period_days: 10, semi_major_axis_au: 0.09, eccentricity: 0, inclination_deg: 90 });
    for (const p of pts) {
      expect(Math.hypot(p.x_au, p.y_au)).toBeCloseTo(0.09, 9);
    }
  });

  it("goes edge-on through the star at 90 degrees", () => {
    const pts = sampleOrbit({ period_days: 10, semi_major_axis_au: 0.09, eccentricity: 0, inclination_deg: 90 });
    expect(Math.min(...pts.map((p) => Math.abs(p.sky_z)))).toBeLessThan(0.05);
  });
});

describe("impactParameter", () => {
  it("is zero edge-on and grows as inclination drops", () => {
    expect(impactParameter(0.05, 90)).toBeCloseTo(0, 9);
    expect(impactParameter(0.05, 85)).toBeGreaterThan(impactParameter(0.05, 89));
  });
});

describe("semiMajorAxisAu", () => {
  it("returns 1 AU for Earth around the Sun", () => {
    expect(semiMajorAxisAu(365.25, 1.0)).toBeCloseTo(1.0, 9);
  });
});

describe("circularDurationDays", () => {
  it("matches a hot-Jupiter-scale duration", () => {
    // P=3.5d, k=0.1, a=0.045AU, i=89.9: a/R*~9.7, duration ~2h.
    const d = circularDurationDays(3.5, 0.1, 0.045, 89.9);
    expect(d).toBeGreaterThan(0.05);
    expect(d).toBeLessThan(0.2);
  });

  it("returns NaN for a non-transiting geometry", () => {
    expect(circularDurationDays(10, 0.05, 0.5, 70)).toBeNaN();
  });
});
