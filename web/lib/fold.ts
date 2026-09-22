/**
 * Phase folding (P3-F): client-side transform of already-held arrays.
 * Pure function over numbers — no data is fetched, invented, or altered.
 */

export interface FoldedPoint {
  phase: number; // [-0.5, 0.5)
  flux: number;
}

/** Fold time onto orbital phase given period and epoch. Output sorted by phase. */
export function foldToPhase(time: number[], flux: number[], period: number, epoch: number): FoldedPoint[] {
  const pts = time.map((t, i) => ({
    phase: ((((t - epoch) % period) + period) % period) / period - 0.5,
    flux: flux[i],
  }));
  pts.sort((a, b) => a.phase - b.phase);
  return pts;
}

/** Bin folded points into nBins phase bins (mean flux per bin). */
export function binFolded(pts: FoldedPoint[], nBins: number): { phase: number[]; flux: number[] } {
  const sums = new Array<number>(nBins).fill(0);
  const counts = new Array<number>(nBins).fill(0);
  for (const p of pts) {
    const b = Math.min(nBins - 1, Math.max(0, Math.floor((p.phase + 0.5) * nBins)));
    sums[b] += p.flux;
    counts[b] += 1;
  }
  const phase: number[] = [];
  const flux: number[] = [];
  for (let b = 0; b < nBins; b++) {
    if (counts[b] === 0) continue;
    phase.push((b + 0.5) / nBins - 0.5);
    flux.push(sums[b] / counts[b]);
  }
  return { phase, flux };
}
