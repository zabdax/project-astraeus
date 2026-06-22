import os
import pytest
from streamlit.testing.v1 import AppTest

def test_ui_flow():
    """
    Smoke test for the ASTRAEUS UI flow.

    Step 1 (kept): upload a file via the Detective page and verify the
    upload branch populates ``st.session_state.uploaded_file_data``.

    Steps 2-5 (skipped): the original test searched for buttons labelled
    "Simulate", "Retrieve Parameters", and "Download Report" — labels
    that no longer exist in the current app (none of the current
    ``st.button`` calls use any of those substrings; the only download
    element is a ``st.download_button`` named "Download Document PDF"
    which lives in a different ``at.get(...)`` namespace). Each step
    was guarded by ``if <btn>:` so a missing match silently skipped the
    assertion and the test passed vacuously. A future "ui-flow-realism"
    bucket should rewrite the test against current app labels; in the
    meantime this test honestly states what it does and does not cover.
    """
    # Setup a dummy light curve file for upload
    test_csv = "dummy_test_lightcurve.csv"
    with open(test_csv, "w") as f:
        f.write("time,flux,flux_err\n0.0,1.0,0.01\n1.0,0.99,0.01\n2.0,1.0,0.01\n")

    # Build a fake UploadedFile for the file_uploader widget. AppTest in
    # streamlit 1.41.1 has no file_uploader property, so we patch
    # ui.pages.detective.st.file_uploader with a stand-in object whose
    # .getvalue() returns the file bytes and .name is the CSV path —
    # the contract the detective page reads at ui/pages/detective.py:235-239
    # (see reports/bucket8_mock_audit.md §2 for the full contract).
    from unittest.mock import patch, MagicMock
    with open(test_csv, "rb") as f:
        file_bytes = f.read()
    fake_uploaded = MagicMock()
    fake_uploaded.getvalue.return_value = file_bytes
    fake_uploaded.name = test_csv

    try:
        with patch("ui.pages.detective.st.file_uploader", return_value=fake_uploaded):
            at = AppTest.from_file("app.py", default_timeout=60)
            at.run()

            # Ensure app loaded without immediate crashes
            assert not at.exception, f"App failed to load: {at.exception}"

            # The default route is Simulation, so the Detective page
            # (and therefore the file_uploader widget) is not rendered
            # in the first pass. Navigate to Detective so the upload
            # branch (ui/pages/detective.py:235-243) actually runs
            # against the mock.
            for btn in at.sidebar.get("button"):
                if "Detective" in btn.label:
                    btn.click().run()
                    break

            # Verify the upload branch populated session_state with a
            # DataAdapter-parsed dict. This is the part of the test that
            # still has real signal today. SafeSessionState in streamlit
            # 1.41.1 does not expose .get() — use filtered_state and
            # subscript access.
            uploaded = (
                at.session_state["uploaded_file_data"]
                if "uploaded_file_data" in at.session_state.filtered_state
                else None
            )
            assert uploaded is not None, (
                "Detective page upload branch should populate "
                "st.session_state.uploaded_file_data after navigation."
            )
            assert isinstance(uploaded, dict), (
                f"Uploaded data should be a dict after DataAdapter.parse(), "
                f"got {type(uploaded).__name__}."
            )
            assert "time" in uploaded and "flux" in uploaded, (
                "Parsed data should contain 'time' and 'flux' keys."
            )

        # The original test's downstream steps (Simulate / Retrieve
        # Parameters / Download Report) were all vacuous because the
        # searched button labels drifted out of the live UI. Skip the
        # rest of the test and document why. A future "ui-flow-realism"
        # bucket should rewrite the test against the current app.
        pytest.skip(
            "Downstream button assertions (Simulate / Retrieve "
            "Parameters / Download Report) target a UI flow that has "
            "been substantially refactored — none of the searched "
            "labels exist in the current app. The upload assertion "
            "above is the part of this test that still has signal. "
            "Tracked for a future 'ui-flow-realism' bucket to rewrite "
            "the downstream steps against current app labels."
        )

    finally:
        # Clean up the dummy CSV file
        if os.path.exists(test_csv):
            os.remove(test_csv)
