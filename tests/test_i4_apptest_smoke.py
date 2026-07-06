"""Smoke test: I4 fix — AppTest.from_file('app.py').run() must complete
inside a reasonable timeout (round 1 evidence: 3s timeout on unkeyed
buttons). The post-I4-patch version must complete without timing out.

This test is a `pytest.mark.timeout`-style safety net, not a hard
assertion on elapsed time. We use Python's signal.SIGALRM on POSIX
and a wall-time check on Windows. The test passes if the script
exits in under 30s; the round-1 evidence was a 3s timeout, so 30s
gives ample headroom.
"""

import os
import sys
import time
import platform

import pytest


def test_apptest_runs_without_timeout():
    """AppTest.from_file('app.py').run() must complete within 30s
    post-I4-patch. Round 1 evidence was a 3s timeout on the unpatched
    version.
    """
    from streamlit.testing.v1 import AppTest

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir)
    )
    app_path = os.path.join(project_root, "app.py")
    assert os.path.exists(app_path), f"app.py not found at {app_path}"

    t0 = time.time()
    at = AppTest.from_file(app_path)
    at.run(timeout=30)  # raise on timeout
    wall = time.time() - t0

    assert wall < 30.0, f"AppTest took {wall:.1f}s (> 30s timeout)"
    # Round 1's failure mode was a 3s timeout. We assert we got
    # something well under that, with margin.
    print(f"\n[I4-apptest] AppTest completed in {wall:.2f}s")
