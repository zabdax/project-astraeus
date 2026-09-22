# Web vs Streamlit parity (P3-H)

The Streamlit app (`app.py`, frozen legacy per P3-I) is the side-by-side
QA reference until Phase 3 exit (PRD §16). This checklist is how a
reviewer compares the two surfaces on the same target.

## Route map

| Streamlit tab | Web route | Status |
|---|---|---|
| Detective (real discovery) | `/investigate` | slice: target fetch + CSV upload + SSE + evidence |
| History (ledger) | `/analyses` | durable jobs + provenance + download |
| Simulation + Lab (sandbox) | `/simulate` | labelled-synthetic sandbox + detection submit |
| Settings (LLM keys, dead write) | `/settings` | connection + BYOK reserved for P3-G |
| Discover (synthetic-only ledger) | `/` landing | eliminated as a data path by design (PRD §9) |

## Evidence parity (same job, both surfaces)

1. Submit the same dataset (CSV upload in both) with the same
   `max_signals` / `snr_floor`.
2. Compare: period_days, depth_fraction, SNR, `tls.outcome` + SDE,
   vetting verdict, `dataset_id` (content hash — must match exactly).
3. Compare provenance: capability snapshot backends, effective config.
4. Tolerances: statistical quantities within pipeline noise; `dataset_id`
   and config must be identical.

## Known intentional divergences

- Discover's synthesized figures have no web equivalent (decorative path
  removed, PRD §9).
- Lab's mock-dataset overlay is replaced by the labelled sandbox.
- MCMC/inference appears in neither (Phase 4).
- The web copilot is evidence-grounded SSE; Streamlit's is a hardcoded
  mock (P3-G).

## Gates run for this phase

- `npm run typecheck`, `npm test`, `npm run build` (web)
- `pytest tests/api tests/contracts tests/jobs -q` (backend contract)
- `pytest tests/test_p2a_vertical_slice.py -q -m slow` (real-data slice)
- Playwright smoke (`web/e2e/`, mocked API): page renders connect →
  data → run states without a backend.
