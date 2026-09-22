BUCKET: P3-F
STATUS: COMPLETE

PROVIDES:
- `web/components/LightCurve.tsx`: thin uPlot wrapper (data in, pixels
  out, destroyed on unmount/change). Flagship chart, no Plotly bundle.
- `web/lib/fold.ts` + `fold.test.ts`: client-side phase fold + binning
  over already-held arrays (pure transform, nothing fetched/invented).
- Integration: Simulate shows raw + folded-at-injected-period previews;
  Investigate previews uploaded CSV curves. Folded *result* curves stay
  out: the API returns evidence, not per-candidate arrays (artifact refs
  are Phase 4+ work).

CONSUMED BY:
- P3-H (chart renders in parity walkthrough)

FILES OF INTEREST:
- web/components/LightCurve.tsx, web/lib/fold.ts, web/lib/fold.test.ts
- web/app/simulate/page.tsx, web/app/investigate/page.tsx (previews)

KNOWN CONSTRAINTS:
- Bins average discrete cadences: fold test pins precision 2, not exact.
- uPlot CSS imported once in the component; no global Plotly.

NEXT REQUIRED ACTION:
- P3-H renders charts in the parity walkthrough.
