# Bucket 8 — Test File_Uploader Mock Fix: Summary

**Branch:** `fix/test-file-uploader-mocks`
**Streamlit version:** 1.41.1
**Bucket type:** test-hygiene (no app code changed)
**Bucket date:** 2026-06-22

---

## TL;DR

All 3 target tests are now green. The full fast gate shows exactly 1
failure (the intentionally red `test_noise_injection` from Bucket 5
Decision 3) and 71 passes — a +3 swing from the baseline (was 68
passes / 4 fails).

| Test | Status before | Status after |
| --- | --- | --- |
| `tests/test_agent_detective.py::test_panel_routing` | FAIL — Analyze button not found | **PASS** |
| `tests/test_ui_flow.py::test_ui_flow` | FAIL — `AppTest` has no attribute `file_uploader` | **PASS** |
| `tests/test_workbench_navigation.py::test_workbench_navigation_persistence` | FAIL — Analyze button not found | **PASS** |
| `tests/test_agent_detective.py::test_noise_injection` | FAIL (intentional) | FAIL (intentional, unchanged) |

---

## 1. Root cause (common to all 3)

`ui/pages/detective.py:235` calls `st.file_uploader("Upload Asset", type=["csv", "fits"], ...)`
and then at line 238-239 calls `uploaded_file.getvalue()` and
`uploaded_file.name` to construct a `DataAdapter` and parse the file.
The expected contract is a duck-typed `UploadedFile`-shaped object
with `.getvalue() -> bytes` and `.name -> str`.

All 3 failing tests were mocking `st.file_uploader` to return a
**filesystem path string** (`return_value=test_csv` / `set_value(test_csv)`).
The page then silently failed at `uploaded_file.getvalue()` (a string
has no such method), the upload branch's `try/except` swallowed the
error, and the downstream `"Analyze Telemetry & Verify Harmonics"`
button at line 327 was never rendered. The tests' `assert run_btn is
not None` then failed.

For `test_ui_flow.py` the failure was earlier and more direct:
streamlit 1.41.1's `AppTest` class has **no `file_uploader` property**
at all, so `at.file_uploader[0].set_value(test_csv)` raised
`AttributeError` immediately.

Full root-cause analysis lives in `reports/bucket8_mock_audit.md`.

---

## 2. Fix pattern (applied to all 3)

The minimal, consistent fix is to **patch
`ui.pages.detective.st.file_uploader` with a `MagicMock` that
quacks like a Streamlit `UploadedFile`**:

```python
from unittest.mock import patch, MagicMock

with open(test_csv, "rb") as f:
    file_bytes = f.read()
fake_uploaded = MagicMock()
fake_uploaded.getvalue.return_value = file_bytes
fake_uploaded.name = test_csv

with patch("ui.pages.detective.st.file_uploader", return_value=fake_uploaded):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    ...
```

`MagicMock` was chosen over a hand-rolled `FakeUploadedFile` class
because:
- `test_workbench_navigation.py` and `test_agent_detective.py`
  already import `patch` from `unittest.mock`, so no new import
  surface
- It is the smallest possible test-side change
- The duck-typed contract (`.getvalue()` / `.name`) is all the page
  reads from the upload object

---

## 3. Per-test diff summary

### 3.1 `tests/test_agent_detective.py::test_panel_routing`

**Before** (`tests/test_agent_detective.py:68-69`):
```python
try:
    from unittest.mock import patch
    with patch("ui.pages.detective.st.file_uploader", return_value=test_csv):
        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
```

**After**:
```python
try:
    from unittest.mock import patch, MagicMock
    with open(test_csv, "rb") as f:
        file_bytes = f.read()
    fake_uploaded = MagicMock()
    fake_uploaded.getvalue.return_value = file_bytes
    fake_uploaded.name = test_csv
    with patch("ui.pages.detective.st.file_uploader", return_value=fake_uploaded):
        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
```

**Downstream assertions updated:** Yes, one.
The test asserted `"BLS Periodogram" in subheaders` to verify the
center panel plot title. That subheader no longer exists in the
current `ui/pages/detective.py` — the center panel title is now
rendered as an `<h3>` markdown element
(`st.markdown("<h3 ...>Phase-Folded Light Curve</h3>", ...)` at
line 522), not as `st.subheader`. Updated the assertion to look for
`"Phase-Folded Light Curve"` in `at.get("markdown")`. The
`plotly_chart` count check is retained unchanged. This is a
stale-assertion update, not a loosening — the test still verifies
the center panel plot is rendered, just by the current title.

**App bug surfaced:** No.

### 3.2 `tests/test_ui_flow.py::test_ui_flow`

**Before** (`tests/test_ui_flow.py:17-32`):
```python
# Initialize the Streamlit app test
at = AppTest.from_file("app.py", default_timeout=60)
at.run()

# Ensure app loaded without immediate crashes
assert not at.exception, f"App failed to load: {at.exception}"

# Setup a dummy light curve file for upload
test_csv = "dummy_test_lightcurve.csv"
with open(test_csv, "w") as f:
    f.write("time,flux,flux_err\n0.0,1.0,0.01\n1.0,0.99,0.01\n2.0,1.0,0.01\n")

try:
    # Step 1: Upload a file
    if len(at.file_uploader) > 0:
        at.file_uploader[0].set_value(test_csv)
        at.run()
```

**After**: AppTest creation moved inside the `patch` block; the
`at.file_uploader` API call (which doesn't exist in 1.41.1) is
replaced with the same `patch` pattern used in the other two tests.

**Downstream assertions updated:** Yes, three.
The test called `at.session_state.keys()` at three points. The
streamlit 1.41.1 `SafeSessionState` doesn't expose a `keys()` method
on the proxy itself; the equivalent is
`at.session_state.filtered_state.keys()`. Updated all three call
sites. This is a stale-assertion update surfaced by the upload-mock
fix; same intent (asserting session_state population), updated to
the current streamlit API.

**App bug surfaced:** No.

### 3.3 `tests/test_workbench_navigation.py::test_workbench_navigation_persistence`

**Before** (`tests/test_workbench_navigation.py:15-19`):
```python
try:
    # Patch the file uploader before the app runs
    with patch("ui.pages.detective.st.file_uploader", return_value=test_csv):
        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
```

**After**:
```python
try:
    with open(test_csv, "rb") as f:
        file_bytes = f.read()
    fake_uploaded = MagicMock()
    fake_uploaded.getvalue.return_value = file_bytes
    fake_uploaded.name = test_csv
    with patch("ui.pages.detective.st.file_uploader", return_value=fake_uploaded):
        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
```

Plus `MagicMock` added to the existing `unittest.mock` import line.

**Downstream assertions updated:** No.
The test's downstream assertions (subheaders, session_state
attributes, persistence checks) all held once the upload branch
executed.

**App bug surfaced:** No.

---

## 4. What was tested and how

| Verification step | Command | Result |
| --- | --- | --- |
| Per-test isolation (test 1) | `python -m pytest tests/test_agent_detective.py::test_panel_routing -v` | 1 passed |
| Per-test isolation (test 2) | `python -m pytest tests/test_ui_flow.py::test_ui_flow -v` | 1 passed |
| Per-test isolation (test 3) | `python -m pytest tests/test_workbench_navigation.py::test_workbench_navigation_persistence -v` | 1 passed |
| Full fast-gate (after) | `python -m pytest tests/ -m "not network and not slow" -v` | 71 passed, 1 failed (`test_noise_injection` only) |
| Pre-fix fast-gate (for comparison, from Phase 0) | same command, before changes | 68 passed, 4 failed |
| Delta | | +3 passes, −3 fails (exactly the 3 in scope) |

The smoke test that proves the MagicMock is contract-compliant lives
in `reports/bucket8_mock_audit.md` §5.

---

## 5. What remains uncertain or deferred

- **`test_ui_flow.py` downstream "Simulate" / "Retrieve Parameters" /
  "Download Report" steps are effectively no-ops.** The test's button
  search strings don't match the current app's button labels
  (Simulator has "Add Planet" / "Reset to Default" / "Execute
  Stability Sweep"; app.py has "Generate Research Manuscript" /
  "Download Document PDF"). The test's `if <btn>:` guards skip the
  assertions when no button matches, so the test passes without
  actually exercising those interactions. This is a pre-existing
  test-quality issue unrelated to the file_uploader bug; flagged in
  `reports/bucket8_mock_audit.md` §7. Recommended for a future "UI
  test realism" bucket.
- **No app code was changed.** This bucket is purely test-side
  hygiene. The detective page's upload contract is unchanged.

---

## 6. Commits (3 small commits per the bucket rules)

```
916c5e3 test(ui): fix file_uploader mock in test_workbench_navigation_persistence
792bc6f test(ui): fix file_uploader mock in test_ui_flow
bad1763 test(ui): fix file_uploader mock in test_panel_routing
```

Each commit touches exactly one test file. The bucket prompt's
"small commits" rule is satisfied — any single commit can be
reverted without losing the other two fixes.

---

## 7. Verification commands (reproducible)

```bash
# Switch to the branch
git checkout fix/test-file-uploader-mocks

# Confirm clean tree
git status

# Show the diff vs main
git diff main..HEAD -- tests/

# Re-run each of the 3 in-scope tests in isolation
python -m pytest tests/test_agent_detective.py::test_panel_routing -v
python -m pytest tests/test_ui_flow.py::test_ui_flow -v
python -m pytest tests/test_workbench_navigation.py::test_workbench_navigation_persistence -v

# Re-run the full fast gate. Expected: 1 failure
# (test_noise_injection, intentionally red per Bucket 5 Decision 3).
python -m pytest tests/ -m "not network and not slow" -v > reports/bucket8_posttest.txt 2>&1
echo "exit=$?"   # exit 1 because of the 1 intentional failure
grep -E "FAILED|passed" reports/bucket8_posttest.txt | tail -5
```

---

## 8. Files touched

| File | Change |
| --- | --- |
| `tests/test_agent_detective.py` | Replaced `return_value=test_csv` with `MagicMock`; updated stale "BLS Periodogram" subheader assertion to current "Phase-Folded Light Curve" h3 markdown |
| `tests/test_ui_flow.py` | Moved `AppTest.from_file()` inside a `patch` block; deleted dead `at.file_uploader` block; updated three `at.session_state.keys()` call sites to `at.session_state.filtered_state.keys()` |
| `tests/test_workbench_navigation.py` | Replaced `return_value=test_csv` with `MagicMock`; added `MagicMock` to existing `unittest.mock` import |
| `reports/bucket8_mock_audit.md` | New: full discovery report (read-only phase artifact) |
| `reports/bucket8_pretest_baseline.txt` | New: pre-fix fast-gate output (4 failures as expected) |
| `reports/bucket8_posttest.txt` | New: post-fix fast-gate output (1 intentional failure) |
| `reports/bucket8_summary.md` | New: this document |

No app code (`astraeus/`, `ui/`, `app.py`, `route.py`) was modified.
