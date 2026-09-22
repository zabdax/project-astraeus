BUCKET: P5-A
STATUS: COMPLETE

PROVIDES:
- `tests/test_p5a_validation_corpus.py` (slow, weekly gate):
  corpus (3 cached real curves, pinned outcomes) + injection
  recovery (3 synthetic truths, period within 5%, TLS executed).
- Corpus pins measured by probe (4 passed in 1413 s):
  Kepler_4d → 3.2136 d / SNR 302 / ran_pass / candidate;
  Kepler_90 → 616.4 d spurious / ran_fail / honest negative;
  TRAPPIST_1 → 1.384 d (archive 1.51 d, alias-class miss) /
  ran_fail on period disagreement despite SDE 7.68 / negative.

CONSUMED BY:
- Release process (corpus must stay green)

FILES OF INTEREST:
- tests/test_p5a_validation_corpus.py

KNOWN CONSTRAINTS:
- WASP-12 b excluded: 270k points, serially infeasible; covered by
  the P4-G benchmark instead.
- Corpus expectations are pinned measurements; a pipeline change that
  moves them must explain the delta, not silently update pins.

NEXT REQUIRED ACTION:
- P5-B/C close the release; final full gate closes the project.
