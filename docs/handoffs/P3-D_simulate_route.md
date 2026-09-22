BUCKET: P3-D
STATUS: COMPLETE

PROVIDES:
- `web/app/simulate/page.tsx` + `web/lib/synthetic.ts`: deterministic
  (seeded) trapezoid+Gaussian sandbox, labelled SYNTHETIC everywhere,
  with parameter controls, uPlot raw + phase-folded previews, and
  one-click submit to the real detection pipeline (injection-recovery).
- `web/lib/synthetic.test.ts`: determinism, seed sensitivity,
  synthetic labelling, injected-depth recovery.

CONSUMED BY:
- P3-H (sandbox vs Simulation/Lab parity: labelled, not mock-overlay)

FILES OF INTEREST:
- web/app/simulate/page.tsx, web/lib/synthetic.ts, web/lib/synthetic.test.ts

KNOWN CONSTRAINTS:
- Trapezoid 10% ramps match the engine's subtraction-fallback
  convention and are documented as such; this is a sandbox model, not
  a science claim.

NEXT REQUIRED ACTION:
- P3-H checks the SYNTHETIC label survives submit → Analyses.
