BUCKET: P3-G
STATUS: COMPLETE

PROVIDES:
- `astraeus/api/copilot.py`: POST /copilot/explain (auth-required) —
  posts an AnalysisResult + question, server serializes the *evidence*
  (status, counts, TLS roll-up, capability, warnings, per-candidate
  period/SNR/depth/TLS — never prose, never an uncomputed verdict) and
  streams SSE (`evidence` → `text` → `done`). No provider/SDK → streamed
  UNAVAILABLE, never a mock, never a 500. LLM imported lazily; blocking
  call runs in a thread with a 180 s cap.
- `web/components/CopilotPanel.tsx` (+ `explainResult` in lib): chat
  over the active result, AI-INTERPRETED badge, abort, BYOK provider
  from Settings. Integrated in Investigate results.
- `tests/api/test_copilot.py`: unavailable path + auth, fast (no LLM).

CONSUMED BY:
- P3-H (honesty labels in parity walkthrough)

FILES OF INTEREST:
- astraeus/api/copilot.py, astraeus/api/main.py (router mount)
- web/components/CopilotPanel.tsx, web/lib/api.ts (`explainResult`)
- tests/api/test_copilot.py

KNOWN CONSTRAINTS:
- With no provider configured (the normal case today) the panel shows
  the server's UNAVAILABLE text — that IS the feature working.
- Numeric claims in prose are unverified; the UI says to check the table.

NEXT REQUIRED ACTION:
- P3-H checks the AI badge + unavailable honesty.
