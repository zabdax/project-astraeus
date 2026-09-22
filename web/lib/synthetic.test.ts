import { describe, expect, it } from "vitest";
import { generateSyntheticCurve } from "./synthetic";

const BASE = {
  period_days: 10,
  epoch_bjd: 5,
  duration_days: 0.3,
  depth_fraction: 0.01,
  n_points: 500,
  baseline_days: 60,
  noise_sigma: 0.001,
  seed: 42,
};

describe("generateSyntheticCurve", () => {
  it("is deterministic per seed", () => {
    const a = generateSyntheticCurve(BASE);
    const b = generateSyntheticCurve(BASE);
    expect(a.flux).toEqual(b.flux);
    expect(a.time).toEqual(b.time);
  });

  it("differs across seeds (noise is real randomness, seeded)", () => {
    const a = generateSyntheticCurve(BASE);
    const b = generateSyntheticCurve({ ...BASE, seed: 43 });
    expect(a.flux).not.toEqual(b.flux);
  });

  it("labels itself synthetic in the target name", () => {
    expect(generateSyntheticCurve(BASE).target_name).toMatch(/^SYNTHETIC/);
  });

  it("recovers approximately the injected depth at mid-transit", () => {
    const curve = generateSyntheticCurve({ ...BASE, noise_sigma: 0 });
    const mid = curve.flux.reduce((m, f) => Math.min(m, f), Infinity);
    expect(mid).toBeCloseTo(1 - BASE.depth_fraction, 6);
  });
});
