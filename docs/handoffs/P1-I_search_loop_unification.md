BUCKET: P1-I
STATUS: COMPLETE

PROVIDES:
- Retirement of the search-loop drift (PRD §2.5).  `_subprocess_search_worker`
  is now an ADAPTER, not a second copy of the loop: it validates the async
  path's own contract (insufficient data is a FAILED job with a reason,
  not an empty result), delegates to the single `run_multi_planet_search`
  implementation, and translates its `on_event` progress into the queue
  messages `_monitor_worker` expects.
- One implementation of every load-bearing scientific guardrail.  Before
  this, GUARDRAIL 1 retried marginal candidates with subtraction on the
  async path while breaking immediately on the sync path, and both paths
  carried their own copy of the fail-closed TLS gate — exactly how a
  bypass silently reappears on one path and not the other.
- `BackendUnavailable` (the sync loop's fail-closed signal) is translated
  back into the async terminal error message, so both paths report a TLS
  infrastructure failure as FAILED, never "DONE / 0 candidates".

CONSUMED BY:
- P4-G (the TLS multiprocessing unlock lands on the now-unified loop)
- app.py (the live Streamlit async path — unchanged mechanism)

FILES OF INTEREST:
- astraeus/core/orchestrator.py  (`_subprocess_search_worker` is now ~90
  lines of adapter, down from ~170 of duplicated loop)
- tests/test_p1i_search_loop_unification.py

KNOWN CONSTRAINTS:
- `submit_multi_planet_search`'s `daemon=True` Process mechanism is
  UNCHANGED and still pinned by `tests/characterize/
  test_tls_call_path_contract.py` (the nested-pool constraint that forces
  `use_threads=1` in `detection.py`).  P1-I touches the loop body only.
- The adapter does NOT forward the loop's own `running`/`done` events —
  its terminal messages carry the candidates; forwarding both duplicates
  them on the channel and in the store.
- Unification is onto the SYNC semantics: that is the path real data and
  the P1-F worker use (PRD §16).  The async path's former
  marginal-subtraction retry is retired; the sync break is authoritative.
  This is a documented Streamlit-visible behaviour change on the async
  path only: both paths now agree, which is the point of the bucket
  (PRD §8 — behaviour changes Streamlit exposes must be stated).

NEXT REQUIRED ACTION:
- P4-G may land the TLS unlock on the single loop behind a feature flag.
