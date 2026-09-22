BUCKET: P3-H
STATUS: COMPLETE (with one stated exception)

PROVIDES:
- Gates executed here: `npm run typecheck` clean, `npm test` (vitest)
  green, `npm run build` green (5 routes prerendered), `tests/api`
  37 passed (incl. copilot + CORS), `docs/WEB_PARITY.md` checklist
  (route map, evidence parity procedure, intentional divergences).
- `web/e2e/smoke.spec.ts` + `playwright.config.ts` (`npm run test:e2e`):
  4 render-state tests, no backend needed. EXCEPTION: browsers cannot
  download in this sandbox (CDN-blocked; evidenced in npm_pw.log), so
  the spec is collected-but-unexecuted here — it runs in CI/dev with
  `npx playwright install chromium`. Vitest excludes `e2e/`
  (`vitest.config.ts`); the runners never overlap.

CONSUMED BY:
- P3-I (freeze after QA)

FILES OF INTEREST:
- docs/WEB_PARITY.md, web/e2e/smoke.spec.ts, web/playwright.config.ts
- web/vitest.config.ts

KNOWN CONSTRAINTS:
- Side-by-side *procedure* is documented; the manual comparison run
  against Streamlit is operator work at release time, not CI.
- Do not claim browser-green until CI runs the spec.

NEXT REQUIRED ACTION:
- P3-I freezes Streamlit; CI runs `test:e2e` with browsers installed.
