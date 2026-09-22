BUCKET: P3-I
STATUS: COMPLETE

PROVIDES:
- Streamlit frozen behind a stated legacy banner (`app.py::main`):
  "Legacy reference UI — new development happens in `web/`. Frozen
  except for reference/QA fixes." No behavior changed; the reference
  stays green until Phase 3 exit per PRD §16.

CONSUMED BY:
- Phase 4 (accuracy work validates against this frozen reference)

FILES OF INTEREST:
- app.py (banner only)

KNOWN CONSTRAINTS:
- Banner is UI text only; no routing/flag mechanism was added (the
  `--legacy` naming in the bucket title refers to this frozen status,
  not a CLI flag — no CLI exists to carry one).

NEXT REQUIRED ACTION:
- Phase 4 science buckets validate against the frozen baseline.
