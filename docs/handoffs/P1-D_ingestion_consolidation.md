BUCKET: P1-D
STATUS: COMPLETE

PROVIDES:
- Ingestion consolidation onto the `Dataset` seam without changing the
  pinned tuple-returning loaders (PRD §8.1).  The existing loaders are
  frozen by `tests/characterize/test_data_loader_contract.py`; adopters
  wrap their output instead.
- `time_unit` is now FORWARDED at the ingestion seam rather than dropped
  (PRD §18 item 4).  `lightkurve_client.py` emits "BJD"; the seam
  previously rebuilt the dict without the key, so the unit was asserted by
  convention downstream (`detection.py`) instead of carried by the data.
  The canonical `Dataset` reads the label from here on.
- Adopters: `data/loader.py::load_dataset`,
  `dashboard/services/data_ingestion.py::to_dataset`,
  and the P1-G bridge.

CONSUMED BY:
- P1-G (real data crossing the worker boundary)
- P1-H (the API builds a `Dataset` from inline arrays)

FILES OF INTEREST:
- astraeus/core/ingestion.py          (time_unit forwarding, +8 lines)
- astraeus/data/loader.py             (load_dataset adopter)
- astraeus/dashboard/services/data_ingestion.py  (to_dataset adopter)

KNOWN CONSTRAINTS:
- Streamlit stays live and unchanged (PRD §16 / §8): the dashboard service
  still returns `LightCurveData` for its existing consumers; the zero-error
  default is kept for them and the canonical adopter reads it as absent.
- A zero-only error column means ABSENT — the silent-invention problem is
  fixed at the seam, not by changing the service's return type.

NEXT REQUIRED ACTION:
- P1-G may fetch real data through the consolidated seam.
