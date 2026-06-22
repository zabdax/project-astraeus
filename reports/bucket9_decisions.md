# Bucket 9 — Decision Gates (Phase 1)

**Branch:** `polish/bucket8-followup` (stacked on `fix/test-file-uploader-mocks`)
**Date:** 2026-06-22
**Phase 0 baseline confirmed:** 71 passed, 1 failed (`test_noise_injection`, intentional)

This document presents the two decision-gate items for Bucket 9 with
the investigation findings, tradeoffs, and a recommended pick. **STOP
and wait for user approval before executing Items 1-4.**

---

## Item 1 — `test_ui_flow` is green but asserts ~nothing

### 1.1 Investigation: which button labels does the test search?

The post-Bucket-8 version of `tests/test_ui_flow.py` searches for
these substrings in `at.button[*].label` (test_ui_flow.py lines 57-58,
71-72, 89-90):

| Step | Test searches for | Exists today? | Closest current equivalent |
| --- | --- | --- | --- |
| 2 ("Click Simulate") | `"Simulate"` | **NO** | (none — closest is `"Add Planet"` / `"Execute Stability Sweep"` on Simulator, both unrelated) |
| 2 (fallback) | `"Load Uploaded"` | **NO** | (none — the "Load Uploaded File" label is in `deprecated/astraeus_dashboard_ui/data_ingestion_panel.py:81`, not in the live app) |
| 2 (fallback) | `"Run Detection"` | **NO** | (removed in a prior refactor; current label is `"Analyze Telemetry & Verify Harmonics"` on Detective page, but that's an entirely different page-flow) |
| 3 ("Click Retrieve Parameters") | `"Retrieve Parameters"` | **NO** | (none — no MCMC-retrieval button exists in the current app) |
| 3 (fallback) | `"Run MCMC"` | **NO** | (none — same as above) |
| 4 ("Click Download Report") | `"Download Report"` | **NO** | (none — there is `"Download Document PDF"` on `app.py:235` but it's `st.download_button`, not `st.button`, so it doesn't show up in `at.button`) |
| 4 (fallback) | `"Export Report"` | **NO** | (none) |

**Full inventory of live `st.button(...)` calls** (in `ui/pages/*.py` and `app.py` only — `deprecated/` excluded per `--ignore=deprecated`):

| File:line | Label |
| --- | --- |
| `app.py:223` | `"Generate Research Manuscript"` |
| `astraeus/dashboard/ui/layout.py:204` | `feature` — variable, one per sidebar nav button: `"Simulation"`, `"Lab"`, `"Detective"`, `"Discover"`, `"History"`, `"Settings"` |
| `ui/pages/detective.py:327` | `"Analyze Telemetry & Verify Harmonics"` (upload path) |
| `ui/pages/detective.py:362` | `"Fetch Target Metadata"` |
| `ui/pages/detective.py:464` | `"Analyze Telemetry & Verify Harmonics"` (target-fetch path) |
| `ui/pages/detective.py:687` | `"Analyze System Stability"` |
| `ui/pages/history.py:52` | `"Restore"` |
| `ui/pages/simulator.py:63` | `"Add Planet"` |
| `ui/pages/simulator.py:73` | `"Reset to Default"` |
| `ui/pages/simulator.py:93` | `"Save"` |
| `ui/pages/simulator.py:100` | `"Edit"` |
| `ui/pages/simulator.py:106` | `"Remove"` |
| `ui/pages/simulator.py:242` | `"Execute Stability Sweep"` |

**Conclusion: zero of the test's search strings match any live button.**
The test's `if <btn>:` guard at every step means a missing match
silently skips the assertion, so the test passes vacuously. Bucket 8
fixed the `at.file_uploader` crash; it did not (and could not, per
its scope) fix the vacuous assertions downstream.

### 1.2 Two options + tradeoffs

#### Option (a): `pytest.skip(...)` the vacuous steps

Replace the test body with an honest `pytest.skip` that explains what
the test does and doesn't cover, with a pointer to a future "UI flow
realism" bucket.

**Pros:**
- Most truthful: the test no longer pretends to verify things it
  doesn't verify
- One small change, no app coupling
- Matches the bucket 5 audit's "no silent fallbacks" rule in spirit
  (the test is honest about its gaps rather than passing by accident)

**Cons:**
- Loses all test value for the interactive flow portion
- The "Upload" step (which Bucket 8 actually fixed to work) still
  wouldn't be exercised, so even the upload + run combination isn't
  verified

#### Option (b): rewrite the search strings to current labels

Update the test's three button-search blocks to use labels that exist
today (e.g. swap "Simulate" for "Add Planet", "Retrieve Parameters"
for nothing-equivalent, "Download Report" for "Download Document
PDF" via `at.download_button` instead of `at.button`).

**Pros:**
- The test would actually exercise the UI flow
- Restores the test's stated intent (verifying that clicking
  meaningful buttons populates session state / generates output)

**Cons:**
- **Cannot fully restore the original intent.** Step 3 ("Retrieve
  Parameters" / "Run MCMC") has no current equivalent — the
  MCMC-retrieval UI was removed in a refactor. No string rewrite
  can bring it back without changing the test's purpose.
- Step 4 ("Download Report") requires reaching `at.download_button`
  (a different `at.get(...)` namespace), which is a bigger
  restructure than the other steps.
- Substantial test rewrite — out of proportion for a "polish" bucket.
- Mixes "polish the existing test" with "rewrite the test for the
  current UI", which is a separate concern.

### 1.3 Recommendation

**Option (a) — honest `pytest.skip` for the vacuous steps.**

Reasoning:
1. The test as written verifies a UI flow that no longer exists.
   Pretending otherwise by chasing new labels would mask the drift.
2. A future "UI flow realism" bucket is the right home for a
   test rewrite against the current app — not this polish bucket.
3. Bucket 8 already shipped the upload-mock fix; the file
   structure (`test_csv` creation, `with patch(...)` block,
   `AppTest.from_file().run()` skeleton) is reusable for that future
   bucket. We should not throw that away.

Concretely, the proposed test_ui_flow change would look like:

```python
def test_ui_flow():
    """..."""
    # Setup dummy CSV (preserved for future UI-flow-realism bucket)
    test_csv = ...
    with patch("ui.pages.detective.st.file_uploader", return_value=fake_uploaded):
        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        # Verify the upload branch executes and populates
        # st.session_state.uploaded_file_data
        assert at.session_state.get('uploaded_file_data') is not None, \
            "Upload branch should populate session_state"
        pytest.skip(
            "Downstream button assertions target a UI flow that has "
            "been substantially refactored (Simulate / Retrieve "
            "Parameters / Download Report labels no longer exist). "
            "Tracked in TODO bucket 'ui-flow-realism' to rewrite "
            "this test against current app labels."
        )
```

Wait — the test's first assertion IS valuable: it verifies the
upload branch populates session_state. That part should stay and be
asserted (not just `at.run()` and skip). This gives the test real
signal even with the skip.

---

## Item 2 — fast gate is permanently red (test_noise_injection)

### 2.1 Investigation: Bucket 5 rationale

From `reports/bucket5_ci_audit.md` §1.4 and `reports/bucket5_summary.md` §1, §7:

- The test fails because `detect_transit_candidate` (called with
  seeded white noise + `snr_threshold=5.0`) returns
  `candidate_found: True` with `confidence_score ≈ 4.09` for
  pure white noise. The BLS search finds a spurious peak that
  crosses the `snr_threshold=5.0` gate.
- **Verdict from Bucket 5:** "This is a real signal-detection
  concern, not a test artifact."
- **User's explicit choice** (Bucket 5 prompt response, recorded
  in `bucket5_ci_audit.md` §1.4 and `bucket5_summary.md` §7):
  "leave red and document" with **"do NOT mark `@pytest.mark.xfail`"
  and "do NOT relax the noise floor"**.
- **Why not xfail per Bucket 5:** the bucket's hard-constraint
  rule is "no silent fallbacks" — marking a known-broken test as
  expected-to-fail would be a silent fallback that masks the
  underlying signal-detection bug.
- **Tracked for:** "a future signal-detection tuning bucket" (per
  `bucket5_summary.md` §7).

The test has been red since well before Bucket 5 (the audit notes
it was already in the baseline of 10 failures). Bucket 5 confirmed
it as intentional and left it red. Bucket 8 unmasked the other 3
failing tests; the noise test is the only one that remains red.

### 2.2 The problem Bucket 9 is now raising

A gate that's always red has no signal. A developer who fixes the
underlying signal-detection bug won't see the gate go green —
they'd have to know to look at the noise test specifically. CI
tools, dashboards, and "is main green?" checks all treat non-zero
exit codes as broken.

This is a real tension with Bucket 5's "no silent fallback" rule:
- Bucket 5 said "don't xfail" because xfail hides bugs.
- Bucket 9 is now asking: how do we get signal from the gate
  without hiding bugs?

### 2.3 Three options + tradeoffs

#### Option 1: `pytest.mark.xfail(reason=..., strict=True)`

```python
@pytest.mark.xfail(
    reason="BLS false-positive in pure white noise (Bucket 5 §1.4); "
           "tracked for signal-detection tuning bucket. strict=True "
           "means: if this ever passes, the gate goes RED (XPASS) — "
           "which is the correct signal for 'we just fixed the bug'.",
    strict=True,
)
def test_noise_injection(): ...
```

**Pros:**
- Gate exits 0 today. CI dashboards are green.
- `strict=True` means: if the test ever passes, the gate turns
  RED with XPASS. This is a **strong positive signal** for the
  future signal-detection tuning bucket — fixing the bug is the
  trigger to revisit the mark.
- Keeps the test running, so the underlying signal-detection
  state is still being exercised.
- Honors Bucket 5's intent: the test is documented, the root
  cause is referenced, and the mark is reversible.

**Cons:**
- Mild violation of Bucket 5's "no silent fallback" rule — but
  `strict=True` is the design pattern that makes it not silent:
  the test still has teeth.
- If the fix happens to be a threshold change that the test
  author doesn't realize would turn the test green, the XPASS
  will be a useful surprise (forces explicit acknowledgment).

#### Option 2: separate marker (`@pytest.mark.known_failing`)

```ini
# pytest.ini
markers =
    known_failing: tests with a known issue, excluded from fast gate
```

```python
@pytest.mark.known_failing
def test_noise_injection(): ...
```

```yaml
# CI fast-gate job
python -m pytest tests/ -m "not network and not slow and not known_failing" -v
```

**Pros:**
- Cleanest separation: the test is clearly in "known broken" tier
- Gate is unambiguously green
- Easy to enumerate `pytest -m known_failing` when reviewing the
  backlog

**Cons:**
- The test stops running in the fast gate, so we lose any
  incidental coverage benefit (small for this test — it just
  exercises `detect_transit_candidate` with white noise).
- Easy to forget: the test sits in the file, doesn't run, may
  rot or stop compiling.
- Reversing the marker requires a CI config change AND a
  developer remembering to look at it.
- **Bucket 9 prompt's note:** would require changing the
  `pytest -m` filter in `pytest.ini` AND in the GitHub Actions
  workflow (`.github/workflows/tests.yml`); more surface area
  than xfail.

#### Option 3: actually fix the underlying behavior

This is the "signal-detection tuning bucket" that Bucket 5
deferred. It would mean: tweak the BLS algorithm or noise
handling so that white noise doesn't trip a `candidate_found:
True` at `confidence_score ≈ 4.09`. **Out of scope** for Bucket
9 (which is test-hygiene + doc-consistency, not signal-detection
algorithm work). Flagged for a future dedicated bucket.

### 2.4 Recommendation

**Option 1 — `pytest.mark.xfail(strict=True)`.**

Reasoning:
1. The "no silent fallback" concern is addressed by `strict=True`:
   the mark is NOT silent. If the underlying bug is fixed, the
   gate turns RED with XPASS — that's exactly the signal the
   "tracked for future signal-detection tuning bucket" comment
   wants.
2. The mark is reversible and tightly scoped: removing the
   decorator on the day the test is fixed is a one-line change.
3. Compared to Option 2 (separate marker), this keeps the test
   actually running in the fast gate — so any incidental
   regression in the detection path is still caught, and the
   XPASS behavior is automatic.
4. Compared to Option 3 (fix it), that's the right long-term
   answer but it's a different bucket. Not this one.

The only minor risk: Bucket 5 explicitly said "do NOT mark xfail"
in its §1.4. Bucket 9 is explicitly asking me to revisit that
position in light of the gate-signal problem. I am recommending
the revisit because the situation has changed (Bucket 8 unmasked
the other 3, so the noise test is the only remaining red) and
because `strict=True` mitigates the original concern.

If the user disagrees and prefers Option 2 (marker exclusion) or
still wants the Bucket 5 "leave red" stance preserved, that's a
perfectly defensible position too — the user is the source of
truth.

---

## Files touched in Phase 1

- `reports/bucket9_decisions.md` — this document (new)

No other files modified. No code touched. The three call-site
refactors and the doc-consistency update wait for user approval.
