BUCKET: P1-G
STATUS: COMPLETE

PROVIDES:
- `astraeus/jobs/ingestion_bridge.py` — real data now crosses the async
  subprocess boundary for the first time (PRD §18 item 1).  The worker's
  fetch path calls the existing TTL-cached ingestion facade (proven
  against 13 real targets from the local FITS cache) and funnels the result
  through the canonical `Dataset`, persisting it to the artifact store and
  returning a content-addressed reference.
- An ingestion failure is a FAILED job with a cause, never a silent empty
  dataset (PRD §5.1 / §18).
- Non-BJD datasets are converted at the seam (`to_bjd()`).

CONSUMED BY:
- P2-A (the vertical slice runs a real target end to end)

FILES OF INTEREST:
- astraeus/jobs/ingestion_bridge.py
- astraeus/jobs/worker.py  (`_load_or_fetch_dataset`)

KNOWN CONSTRAINTS:
- The engine's ingestion stack is imported lazily and ONLY on this path,
  so the worker process pays for it only when it actually fetches.
- The API layer's `target` submission path exercises this; its tests use
  inline arrays instead so the fast gate stays network-free.

NEXT REQUIRED ACTION:
- P2-A may run a real target through the worker + API end to end.
