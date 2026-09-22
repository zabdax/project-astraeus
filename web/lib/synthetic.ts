/**
 * Honest synthetic sandbox (P3-D).
 *
 * Generates a labelled-SYNTHETIC light curve in-browser: trapezoid transit
 * (10% ingress/egress ramps — the same convention as the engine's
 * subtraction fallback) plus seeded Gaussian noise. Deterministic per
 * seed so a run is reproducible from its parameters alone.
 *
 * Nothing here claims to be data: the payload carries
 * `synthetic: true` in the target name suffix and the UI badges every
 * downstream number as derived-from-synthetic.
 */

export interface SyntheticParams {
  period_days: number;
  epoch_bjd: number;
  duration_days: number;
  depth_fraction: number;
  n_points: number;
  baseline_days: number;
  noise_sigma: number;
  seed: number;
}

export interface SyntheticCurve {
  time: number[];
  flux: number[];
  target_name: string;
}

/** Deterministic PRNG (mulberry32). */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Gaussian via Box-Muller over a seeded uniform source. */
export function gaussian(rng: () => number): number {
  const u1 = Math.max(rng(), 1e-12);
  const u2 = rng();
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

export function generateSyntheticCurve(p: SyntheticParams): SyntheticCurve {
  const rng = mulberry32(p.seed);
  const time: number[] = [];
  const flux: number[] = [];
  const model = transitModel(p);
  for (let i = 0; i < p.n_points; i++) {
    const t = (i / Math.max(p.n_points - 1, 1)) * p.baseline_days;
    time.push(t);
    flux.push(model(t) + gaussian(rng) * p.noise_sigma);
  }
  return {
    time,
    flux,
    target_name: `SYNTHETIC P=${p.period_days}d depth=${Math.round(p.depth_fraction * 1e6)}ppm`,
  };
}

/** Noiseless transit model (shared by the curve, residuals, and fold). */
export function transitModel(p: SyntheticParams): (t: number) => number {
  const ramp = 0.1 * p.duration_days;
  const half = p.duration_days / 2;
  return (t: number) => {
    const phase = ((((t - p.epoch_bjd) % p.period_days) + p.period_days) % p.period_days) - p.period_days / 2;
    const d = Math.abs(phase);
    if (d <= half - ramp) return 1 - p.depth_fraction;
    if (d <= half + ramp) return 1 - p.depth_fraction * (1 - (d - (half - ramp)) / (2 * ramp));
    return 1;
  };
}
