import { describe, expect, it } from "vitest";
import { binFolded, foldToPhase } from "./fold";
import { generateSyntheticCurve } from "./synthetic";

describe("foldToPhase", () => {
  it("recovers the injected dip at phase 0 on a noiseless curve", () => {
    const curve = generateSyntheticCurve({
      period_days: 10,
      epoch_bjd: 5,
      duration_days: 0.4,
      depth_fraction: 0.02,
      n_points: 1000,
      baseline_days: 60,
      noise_sigma: 0,
      seed: 1,
    });
    const folded = foldToPhase(curve.time, curve.flux, 10, 5);
    expect(folded).toHaveLength(1000);
    const binned = binFolded(folded, 50);
    const deepest = Math.min(...binned.flux);
    // Bins average discrete cadences (ramps included): precision 2, not exact.
    expect(deepest).toBeCloseTo(0.98, 2);
    const idx = binned.flux.indexOf(deepest);
    expect(Math.abs(binned.phase[idx])).toBeLessThan(0.05);
  });

  it("wraps phases into [-0.5, 0.5)", () => {
    const folded = foldToPhase([0, 5, 10, 15], [1, 1, 1, 1], 10, 0);
    for (const p of folded) {
      expect(p.phase).toBeGreaterThanOrEqual(-0.5);
      expect(p.phase).toBeLessThan(0.5);
    }
  });
});
