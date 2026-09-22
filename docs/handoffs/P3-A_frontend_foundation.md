BUCKET: P3-A
STATUS: COMPLETE

PROVIDES:
- Foundation the routes share: `web/` shell (`app/layout.tsx` topbar +
  nav: Investigate/Analyses/Simulate/Settings), P3-A theme tokens
  (`globals.css`: dark lab, epistemic badges, focus-visible,
  reduced-motion, responsive), landing (`app/page.tsx`: API liveness +
  links, never synthesized figures).
- Generated API client: `web/openapi.json` (pinned export of the P1-H
  schema) + `lib/api-generated.d.ts` via `npm run gen:api`; wire shapes
  (`JobResponse`, `InlineDataset`, …) aliased from generated components.
  Domain shapes (`AnalysisResult`, candidates) mirror
  `astraeus/contracts/` and are pinned by `lib/api.test.ts`.
- `lib/session.tsx`: memory-only token session + ConnectBox shared by
  all routes (persistence choices belong to P3-E).

CONSUMED BY:
- P3-B/C/D/E (routes), P3-F (charts), P3-G (copilot panel)

NEW CONTRACTS:
- OpenAPI-derived TS types (regenerate, never hand-edit wire shapes)

FILES OF INTEREST:
- web/app/layout.tsx, web/app/page.tsx, web/app/globals.css
- web/lib/api.ts, web/lib/api-generated.d.ts, web/lib/session.tsx
- web/openapi.json, web/package.json (`gen:api` script)

KNOWN CONSTRAINTS:
- `openapi.json` + lockfile committed; regenerate both on API change.
- Hand client helpers (SSE parsing, CSV parsing, labels) stay; only
  wire shapes are generated.

NEXT REQUIRED ACTION:
- Routes build pages on this shell; P3-H runs the gates.
