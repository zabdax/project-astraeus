BUCKET: P3-B
STATUS: COMPLETE

PROVIDES:
- `web/app/investigate/page.tsx` (promoted P2-B slice onto the P3-A
  shell): connect → target-fetch or CSV-upload → run → SSE progress
  with polling backstop → evidence table with epistemic badges →
  provenance drawer → download → cancel, plus `CopilotPanel` (P3-G)
  and CSV `LightCurve` preview (P3-F).

CONSUMED BY:
- P3-H (parity checks against Detective)

FILES OF INTEREST:
- web/app/investigate/page.tsx

KNOWN CONSTRAINTS:
- Keeps its own connect flow (predates `lib/session.tsx`); unification
  is cosmetic-only future work, never a behavior change.

NEXT REQUIRED ACTION:
- P3-H compares evidence parity with Detective on the same CSV.
