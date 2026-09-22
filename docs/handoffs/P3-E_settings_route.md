BUCKET: P3-E
STATUS: COMPLETE

PROVIDES:
- `web/app/settings/page.tsx`: API endpoint display (build-time env),
  session connect/disconnect, and copilot BYOK (provider + key) saved
  to localStorage ONLY on explicit opt-in, labelled reserved for P3-G
  with "sent nowhere by this slice" stated outright. Forget button
  included.

CONSUMED BY:
- P3-G (reads the stored provider choice)

FILES OF INTEREST:
- web/app/settings/page.tsx

KNOWN CONSTRAINTS:
- API bearer tokens stay memory-only; only copilot provider choice
  persists, and only locally. Server-side key storage does not exist.

NEXT REQUIRED ACTION:
- P3-G consumes the stored provider; P3-H checks the honesty labels.
