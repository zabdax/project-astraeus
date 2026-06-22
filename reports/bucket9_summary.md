# Bucket 9 — Polish & Follow-up: Summary

**Branch:** `polish/bucket8-followup` (stacked on `fix/test-file-uploader-mocks`)
**Type:** test-hygiene + doc-consistency (no app code changes)
**Date:** 2026-06-22
**Streamlit version:** 1.41.1 (pinned)

---

## TL;DR

| Metric | Before (Phase 0 baseline) | After (Phase 3 verification) | Delta |
| --- | --- | --- | --- |
| Tests passed | 71 | 70 | -1 (test_ui_flow now SKIPPED per Item 1) |
| Tests failed | 1 (`test_noise_injection`) | 0 | **-1 (gate is GREEN)** |
| Tests xfailed | 0 | 1 (`test_noise_injection`) | +1 (Item 2's `strict=True` mark) |
| Tests skipped | 0 | 1 (`test_ui_flow`) | +1 (Item 1's deliberate skip) |
| Deselected (network + slow) | 33 | 33 | 0 |
| **Fast-gate exit code** | **1 (RED)** | **0 (GREEN)** | **gate now has signal** |
| App code modified | — | — | 0 (per bucket type constraint) |

Two decision-gate items were investigated in Phase 1 and the user
picked the recommended options for both:

- **Item 1** — `test_ui_flow` passes vacuously. **Pick: Skip + assert
  upload.** Test now navigates to Detective, asserts the upload
  branch populated `st.session_state.uploaded_file_data`, then
  `pytest.skip(...)` the rest with a clear pointer to a future
  "ui-flow-realism" bucket.
- **Item 2** — fast gate is permanently red. **Pick:
  `pytest.mark.xfail(strict=True)` on `test_noise_injection`.**
  Gate now exits 0; the strict mark means the gate will turn RED with
  XPASS the day the underlying signal-detection bug is fixed — which
  is exactly the signal Bucket 5's "tracked for future
  signal-detection tuning bucket" comment wants.

Two straight-execution items:

- **Item 3** — reconcile `reports/bucket8_mock_audit.md` §6 with
  `reports/bucket8_summary.md` §3.1/§3.2 (audit said "No downstream
  assertions change", summary admitted two stale-assertion updates).
  Audit now records the same fact as the summary with the same
  "stale-assertion update, not a loosening" justification.
- **Item 4** — dedupe the triplicated `MagicMock` block in the three
  Bucket 8 tests into a single `fake_uploaded_file` factory fixture
  in `tests/conftest.py`. Replaces `MagicMock` (which silently
  auto-satisfies any attribute access) with a small
  `FakeUploadedFile` dataclass that raises `AttributeError` on
  out-of-contract access — verified by smoke test.

---

## Per-item diff summary

### Item 1 — `tests/test_ui_flow.py::test_ui_flow`

**Before (Bucket 8's fix, vacuously passing):**
- 3 button-search loops, every step guarded by `if <btn>:` so missing
  matches silently skipped the assertion.
- Search strings: "Simulate" / "Load Uploaded" / "Run Detection" /
  "Retrieve Parameters" / "Run MCMC" / "Download Report" /
  "Export Report" — **none** match any live `st.button` label
  (per `reports/bucket9_decisions.md` §1.1 table).
- Test passed for the wrong reason.

**After:**
- Navigate to Detective via the sidebar nav button (so the upload
  branch actually runs against the fixture).
- Assert `st.session_state.uploaded_file_data` is a dict with
  `'time'` and `'flux'` keys (the DataAdapter contract).
- `pytest.skip(...)` the rest with a clear pointer to a future
  "ui-flow-realism" bucket.
- Side fix: `at.session_state.get(...)` does not exist on streamlit
  1.41.1's `SafeSessionState` — use `filtered_state` membership
  check + subscript access.

**Commit:** `03d2a56 test(ui-flow): assert upload branch + skip vacuous downstream steps`

### Item 2 — `tests/test_agent_detective.py::test_noise_injection`

**Before (Bucket 5's "leave red by design"):**
- Test failed: BLS false-positive in seeded white noise
  (`confidence_score ≈ 4.09` at `snr_threshold=5.0`).
- Fast gate exited 1 on every run.

**After:**
- `@pytest.mark.xfail(reason=..., strict=True)` decorator.
- Fast gate now exits 0.
- If the underlying signal-detection bug is ever fixed, the test
  will XPASS and the gate will turn RED — the strong positive
  signal the future bucket's author wants.
- Honors Bucket 5's intent: the test is documented, the root cause
  is referenced, and the mark is reversible (one-line change on the
  day the bug is fixed).

**Commit:** `472c584 test(noise): mark test_noise_injection xfail(strict=True)`

### Item 3 — `reports/bucket8_mock_audit.md` reconciliation

**Before (the contradiction):**
- `bucket8_mock_audit.md` §6: "No downstream assertions change."
- `bucket8_summary.md` §3.1 + §3.2: explicitly records two
  stale-assertion updates (the "BLS Periodogram" → "Phase-Folded
  Light Curve" h3 markdown update in `test_panel_routing`, and the
  three `at.session_state.keys()` → `at.session_state.filtered_state.keys()`
  updates in `test_ui_flow`).

**After:**
- Audit §6 now states the same fact as the summary, with the same
  "stale-assertion update, not a loosening" justification and
  cross-references to the summary for the per-test detail.
- No other wording in the audit is changed.

**Commit:** `44d74d1 docs(bucket8): reconcile audit §6 with summary §3.1 + §3.2`

### Item 4 — `tests/conftest.py` `fake_uploaded_file` fixture

**Before (triplicated inline MagicMock in 3 tests):**
```python
from unittest.mock import patch, MagicMock
with open(test_csv, "rb") as f:
    file_bytes = f.read()
fake_uploaded = MagicMock()
fake_uploaded.getvalue.return_value = file_bytes
fake_uploaded.name = test_csv
with patch("ui.pages.detective.st.file_uploader", return_value=fake_uploaded):
    ...
```

**After (one fixture, 3 call-site swaps):**
```python
# tests/conftest.py
@dataclass
class FakeUploadedFile:
    _data: bytes
    name: str
    def getvalue(self) -> bytes: return self._data

@pytest.fixture
def fake_uploaded_file():
    def _make(path: str) -> FakeUploadedFile:
        with open(path, "rb") as f:
            return FakeUploadedFile(_data=f.read(), name=path)
    return _make

# each test
def test_x(fake_uploaded_file):
    ...
    with patch("ui.pages.detective.st.file_uploader",
               return_value=fake_uploaded_file(test_csv)):
        ...
```

**Why dataclass and not `MagicMock`:** `MagicMock` silently
auto-satisfies ANY attribute access — if `detective.py` later reads
`uploaded_file.size` or `uploaded_file.type` (attributes real
`UploadedFile` objects expose), the mock returns a child `MagicMock`
instead of failing the test, masking the surface drift. The dataclass
raises `AttributeError` on out-of-contract access (verified: `fake.size`,
`fake.type`, `fake.id`, `fake.content_type` all `AttributeError`).

**Commit:** `2f5c003 test(fixture): dedupe file_uploader mock into a conftest fixture`

---

## Verification (Phase 3)

Per-test:

| Test | Status |
| --- | --- |
| `test_agent_detective.py::test_panel_routing` | **PASSED** |
| `test_ui_flow.py::test_ui_flow` | **SKIPPED** (deliberate, Item 1) |
| `test_workbench_navigation.py::test_workbench_navigation_persistence` | **PASSED** |
| `test_agent_detective.py::test_noise_injection` | **XFAIL** (per Item 2's `strict=True` mark; failure-on-fix signal preserved) |

Full fast gate:

```text
70 passed, 1 skipped, 33 deselected, 1 xfailed, 27 warnings
exit 0
```

**Expected post-bucket behavior:** The fast gate exits **0 (GREEN)**.
If `test_noise_injection`'s underlying signal-detection bug is ever
fixed, the test will XPASS and the gate will turn RED — that's the
correct signal for the future signal-detection tuning bucket to
remove the `xfail` mark.

---

## Stacking / merge-order note

**Bucket 8 must land before (or with) Bucket 9.** Bucket 8 ships
the three test-file fixes and the `reports/bucket8_*` docs that this
branch assumes are present. If Bucket 8 is rebased or amended
between this bucket's creation and merge, rebase
`polish/bucket8-followup` onto the new Bucket 8 tip before
merging. No rebase was required during Bucket 9's execution.

**Merge order:**
1. `fix/test-file-uploader-mocks` (Bucket 8) → `main` first.
2. `polish/bucket8-followup` (Bucket 9) → `main` second.

Do not open a Bucket 9 PR that targets `main` directly while
Bucket 8 is still open — either target Bucket 8's branch or wait
for Bucket 8 to land.

---

## Out-of-scope findings (flagged, not fixed)

- **`test_ui_flow.py` step 2-4 buttons have no current equivalent.**
  The "ui-flow-realism" bucket referenced in the pytest.skip
  message is the right home for a test rewrite against current
  app labels. Out of scope for this polish bucket.
- **`test_noise_injection` underlying signal-detection issue.**
  The xfail mark exists to give the gate signal. The actual BLS
  false-positive fix is the signal-detection tuning bucket's job.
- **`@pytest.mark.xfail` registration in `pytest.ini`.** Pytest
  treats `xfail` as a built-in marker (no registration needed);
  the existing `pytest.ini` markers block (smoke / network / slow
  from Bucket 5) does not need an addition. Verified.
- **CI workflow filter.** No change needed to
  `.github/workflows/tests.yml`. The fast-gate job runs
  `pytest tests/ -m "not network and not slow" -v` which still
  selects `test_noise_injection` (no marker excludes it). The
  xfail mark does not require the test to be deselected — it
  still runs and is counted as XFAIL.

---

## Files touched

| File | Change |
| --- | --- |
| `tests/test_ui_flow.py` | Item 1: assert upload + `pytest.skip` downstream; Item 4: use fixture |
| `tests/test_agent_detective.py` | Item 2: add `xfail(strict=True)` to `test_noise_injection`; Item 4: `test_panel_routing` uses fixture |
| `tests/test_workbench_navigation.py` | Item 4: use fixture |
| `tests/conftest.py` | Item 4: add `FakeUploadedFile` dataclass + `fake_uploaded_file` factory fixture |
| `reports/bucket8_mock_audit.md` | Item 3: reconcile §6 with summary §3.1 + §3.2 |
| `reports/bucket9_decisions.md` | New: Phase 1 decision-gate document |
| `reports/bucket9_pretest_baseline.txt` | New: Phase 0 baseline (71 passed, 1 failed) |
| `reports/bucket9_posttest.txt` | New: Phase 3 result (70 passed, 1 skipped, 1 xfailed, exit 0) |
| `reports/bucket9_summary.md` | New: this document |

**No app code (`astraeus/`, `ui/`, `app.py`, `route.py`) was
modified.** The deprecated dashboard file was not touched. Bucket
8's commits are not amended or reverted.

---

## Commits (5 small, each independently revertible)

```
2f5c003 test(fixture): dedupe file_uploader mock into a conftest fixture
44d74d1 docs(bucket8): reconcile audit §6 with summary §3.1 + §3.2
472c584 test(noise): mark test_noise_injection xfail(strict=True)
03d2a56 test(ui-flow): assert upload branch + skip vacuous downstream steps
```

(Plus the Phase 1 decision doc `reports/bucket9_decisions.md` was
written but not committed per Phase 1's read-only rule; it landed
in Phase 3's docs commit along with this summary. See the
following docs commit.)

```
[docs commit, see git log]  docs(bucket9): add decisions, pretest, posttest, and summary
```

---

## Verification commands (reproducible)

```bash
# Switch to the branch
git checkout polish/bucket8-followup

# Confirm clean tree
git status

# Show the diff vs Bucket 8's tip
git log fix/test-file-uploader-mocks..HEAD
git diff fix/test-file-uploader-mocks..HEAD -- tests/ reports/

# Per-test verification
python -m pytest tests/test_agent_detective.py::test_panel_routing -v
python -m pytest tests/test_ui_flow.py::test_ui_flow -v
python -m pytest tests/test_workbench_navigation.py::test_workbench_navigation_persistence -v
python -m pytest tests/test_agent_detective.py::test_noise_injection -v

# Full fast gate. Expected: 70 passed, 1 skipped, 1 xfailed, exit 0.
python -m pytest tests/ -m "not network and not slow" -v > reports/bucket9_posttest.txt 2>&1
echo "exit=$?"   # exit 0 (gate is GREEN)
tail -5 reports/bucket9_posttest.txt
```

---

## Stacking / merge-order summary (TL;DR)

- **Bucket 8** ships 3 test-mock fixes + the `bucket8_*` reports.
  **First to land.**
- **Bucket 9** (this branch) polishes Bucket 8: Item 1 (test_ui_flow
  honesty), Item 2 (gate signal via xfail), Item 3 (doc consistency),
  Item 4 (conftest fixture dedup). **Second to land.**
- If Bucket 8 is rebased before Bucket 9 merges: rebase
  `polish/bucket8-followup` onto the new Bucket 8 tip before
  merging. Flag this in the PR description.
