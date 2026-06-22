# Bucket 8 — Test File_Uploader Mock Audit

**Branch:** `fix/test-file-uploader-mocks`
**Baseline:** 4 fast-gate failures (3 in scope, 1 intentional).
**Streamlit version:** 1.41.1
**Investigation date:** 2026-06-22

---

## 1. AppTest `file_uploader` API in Streamlit 1.41.1

**Critical finding: `AppTest` in streamlit 1.41.1 has NO `file_uploader` property.**

Inspection of the installed package's public API confirms this:

```python
>>> from streamlit.testing.v1 import AppTest
>>> [m for m in dir(AppTest) if not m.startswith('_')]
['button', 'button_group', 'caption', 'chat_input', 'chat_message',
 'checkbox', 'code', 'color_picker', 'columns', 'dataframe',
 'date_input', 'divider', 'error', 'exception', 'expander', 'from_file',
 'from_function', 'from_string', 'get', 'header', 'info', 'json', 'latex',
 'main', 'markdown', 'metric', 'multiselect', 'number_input', 'radio',
 'run', 'select_slider', 'selectbox', 'sidebar', 'slider', 'status',
 'subheader', 'success', 'switch_page', 'table', 'tabs', 'text',
 'text_area', 'text_input', 'time_input', 'title', 'toast', 'toggle',
 'warning']
```

There is no `file_uploader`, no `upload_file` helper, and no
`FileUploader` testing widget class in this version. (Streamlit later
added `FileUploader` to `AppTest` in a post-1.41 release; we are pinned
to 1.41.1, so that newer API is unavailable.)

**Consequence:** The only viable approach in this codebase is to patch
`ui.pages.detective.st.file_uploader` directly with a stand-in object
that quacks like a Streamlit `UploadedFile`. There is no
"AppTest-native" path for file uploads in 1.41.1.

---

## 2. The detective.py upload branch contract

`ui/pages/detective.py:render_discovery_bar()` (line 235-243) calls
`st.file_uploader("Upload Asset", type=["csv", "fits"], key="raw_upload_widget", ...)`
and then immediately does:

```python
adapter = DataAdapter(uploaded_file.getvalue(), uploaded_file.name)
st.session_state.uploaded_file_data = adapter.parse()
```

**Contract the mock must satisfy:**

| Attribute / method | Expected type / behavior |
| --- | --- |
| `.getvalue()` | Returns the file **bytes** (used by `DataAdapter.__init__`). |
| `.name` | String ending in `.csv`, `.json`, `.fits`, or `.fit` (drives `DataAdapter` format detection in `parse()`). |
| Return of `st.file_uploader(...)` | An object that is not `None` so the `if uploaded_file is not None:` branch executes. |

After the upload branch runs, `st.session_state.uploaded_file_data` is
a dict (e.g. `{'time': ndarray, 'flux': ndarray, 'metadata': {}}`).
At line 325 the page checks
`isinstance(uploaded_data, dict) and 'time' in uploaded_data and 'flux' in uploaded_data`
and then renders the **"Analyze Telemetry & Verify Harmonics"** button
at line 327. Once that button renders, it is clickable and triggers
`run_analysis(uploaded_data['time'], uploaded_data['flux'], ...)` which
populates `st.session_state['detective_results']` and friends (lines
312-318). That, in turn, drives the rest of the Detective page render.

**Line 460-470** (the second branch) is for a different path: a
*fetched* target's pre-loaded `res['time']` / `res['flux']`, not a
user upload. The 3 failing tests in this bucket do not hit that branch
— they all go through the upload path — so we only need the upload
mock.

---

## 3. Per-test audit

### 3.1 `tests/test_agent_detective.py::test_panel_routing`

**Broken pattern (line 69):**

```python
with patch("ui.pages.detective.st.file_uploader", return_value=test_csv):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    ...
    # Then clicks Detective, then "Analyze Telemetry & Verify Harmonics"
```

`test_csv` is the **string path** to the dummy CSV on disk. The page
calls `uploaded_file.getvalue()` on a string, which raises
`AttributeError: 'str' object has no attribute 'getvalue'`. The upload
branch silently bails (its `try/except` at line 240 catches the error
and renders an inline error message). `st.session_state.uploaded_file_data`
is set to `None` at line 243. The button at line 327 is therefore not
rendered, and the test's
`assert run_btn is not None, "Analyze Telemetry & Verify Harmonics button not found."`
fails.

**End assertion the test is trying to make:** After upload + click,
the page should render a `BLS Periodogram` subheader, at least one
`plotly_chart`, a `Detection Report` subheader, and a `json` element
whose stringified content mentions `period` or `confidence_score`.

**Is the end assertion still valid once the upload branch executes?**
Yes — the page has the full 3-tier render at line 470+ which produces
all of those artefacts once `detective_results` is populated by
`run_analysis` (line 281-322). With a working mock, `run_analysis`
will be invoked by clicking the Analyze button, populating the
results, and triggering the rest of the render. The downstream
assertions are valid; they do not need updating.

### 3.2 `tests/test_ui_flow.py::test_ui_flow`

**Broken pattern (line 30-32):**

```python
if len(at.file_uploader) > 0:
    at.file_uploader[0].set_value(test_csv)
    at.run()
```

`AppTest` in 1.41.1 has no `file_uploader` attribute, so the
`len(at.file_uploader)` lookup raises
`AttributeError: 'AppTest' object has no attribute 'file_uploader'`
*before* the `if` even evaluates. The test currently dies on that
attribute access, never reaching any of the actual flow assertions.

**End assertion the test is trying to make:** Five sequential UI
interactions (upload, Simulate, Retrieve Parameters, download report)
should each populate / mutate `at.session_state`, and the "Download
Report" path should produce a non-empty PDF on disk.

**Is the end assertion still valid once the upload branch executes?**
Mostly yes, but **the test has a separate, pre-existing fragility
unrelated to this bucket**: it tries to click buttons labelled
"Simulate", "Load Uploaded", or "Run Detection" (line 41-44), and
"Retrieve Parameters" or "Run MCMC" (line 55-58), and "Download Report"
or "Export Report" (line 73-76). A scan of `ui/pages/` shows none of
those exact labels exist in the current app (Simulator has
"Add Planet", "Reset to Default", "Edit", "Save", "Remove",
"Execute Stability Sweep"; Detective has "Analyze Telemetry &
Verify Harmonics"; the manuscript export on `app.py:223` is
"Generate Research Manuscript" / "Download Document PDF"). The test
guards every step with `if <btn>:` so a missing button simply skips
the corresponding assertion block — the test should still pass
overall once the AttributeError is fixed, with most downstream
checks effectively becoming no-ops. **Documenting this here per
the bucket's instruction to surface (not fix) downstream test
issues.**

**Approach for the fix:** Switch from the (non-existent) AppTest
`file_uploader` API to the same `patch("ui.pages.detective.st.file_uploader", ...)`
pattern the other two tests use, so the three tests stay consistent.
This means the test must move the `AppTest.from_file(...).run()` call
*inside* the `with patch(...)` block, mirroring the structure of
`test_panel_routing` and `test_workbench_navigation_persistence`.

### 3.3 `tests/test_workbench_navigation.py::test_workbench_navigation_persistence`

**Broken pattern (line 16):**

```python
with patch("ui.pages.detective.st.file_uploader", return_value=test_csv):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
```

Same root cause as 3.1: a string path is returned, the upload
branch fails on `.getvalue()`, and the "Analyze Telemetry & Verify
Harmonics" button never renders.

**End assertion the test is trying to make:** After
Simulator → Detective → History → Simulator navigation, the right-panel
`Detection Report` and the `snr=123` setting must both persist.

**Is the end assertion still valid once the upload branch executes?**
Yes. The first part of the test (slider, navigation) is independent
of the upload mock — the patch is set before `AppTest.from_file()` and
remains active for the whole test, so when the Detective page renders
the upload branch will execute and the Analyze button will be
clickable. The detection-report subheader at line 80 will then be
present after the Analyze click. No downstream assertion needs to
change.

---

## 4. Existing patterns in the suite

A full repo grep confirms no test mocks `file_uploader` correctly:

```
$ grep -rln "file_uploader\|UploadedFile" F:\solo_leveling_assistant\project-astraeus
tests\test_workbench_navigation.py
tests\test_agent_detective.py
tests\test_ui_flow.py
ui\pages\detective.py
deprecated\astraeus_dashboard_ui\data_ingestion_panel.py
```

The deprecated dashboard file (not part of the live test suite) calls
`st.file_uploader` the same way `detective.py` does, but it has no
test. So **there is no pre-existing correct pattern to copy**; I am
introducing the canonical pattern for this repo.

**Chosen pattern (used in all three fixes):**

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

This satisfies the contract from §2. A `MagicMock` was chosen over a
hand-rolled `FakeUploadedFile` class because (a) the existing
`test_workbench_navigation.py` and `test_agent_detective.py` already
import `patch` from `unittest.mock`, so no new import surface, and (b)
it is the smallest possible test-side change.

---

## 5. Verification of the chosen pattern (smoke test)

Ran a quick smoke test outside pytest to confirm the contract holds:

```python
>>> from unittest.mock import MagicMock
>>> from astraeus.data.adapter import DataAdapter
>>> fake = MagicMock()
>>> fake.name = "dummy.csv"
>>> csv_bytes = b"time,flux\n0.0,1.0\n1.0,0.99\n2.0,1.0\n"
>>> fake.getvalue.return_value = csv_bytes
>>> parsed = DataAdapter(fake.getvalue(), fake.name).parse()
>>> isinstance(parsed, dict) and 'time' in parsed and 'flux' in parsed
True
```

The mock quacks correctly. `parsed` is a dict with `time` and `flux`
ndarrays, exactly what the page's line-325 `isinstance` check needs.

---

## 6. Summary of changes planned for Phase 2

| Test | Plan |
| --- | --- |
| `test_agent_detective.py::test_panel_routing` | Replace `return_value=test_csv` with a `MagicMock` whose `.getvalue()` returns the CSV bytes and `.name` is the test CSV path. Read the bytes once at the top of the test. |
| `tests/test_ui_flow.py::test_ui_flow` | Move the `AppTest.from_file(...).run()` call *inside* a `with patch("ui.pages.detective.st.file_uploader", return_value=MagicMock(getvalue=..., name=test_csv)):` block. Delete the dead `at.file_uploader` block. |
| `tests/test_workbench_navigation.py::test_workbench_navigation_persistence` | Same as test_panel_routing: replace `return_value=test_csv` with a `MagicMock`. |

No downstream assertions change. No app code is touched. The
intentionally-red `test_noise_injection` is not modified.

---

## 7. Out-of-scope findings (flagged, not fixed)

1. **`test_ui_flow.py` downstream steps are effectively no-ops**:
   the test's button search strings ("Simulate", "Retrieve Parameters",
   "Download Report") do not appear verbatim in the current app. The
   `if <btn>:` guards make the test pass without exercising those
   interactions. This is a pre-existing test-quality issue unrelated
   to the file_uploader bug; per the bucket rules I do not weaken or
   rewrite it. Recommended for a future "UI test realism" bucket.
