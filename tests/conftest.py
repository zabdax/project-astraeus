"""Cross-test Streamlit AppTest pollution fix.

The ``DeltaGeneratorSingleton`` is instantiated at the bottom of
``streamlit/__init__.py`` (line 84) when the module is first imported::

    _dg_singleton = _DeltaGeneratorSingleton(
        delta_generator_cls=_DeltaGenerator,
        status_container_cls=_StatusContainer,
        dialog_container_cls=_Dialog,
    )

Inside ``streamlit/delta_generator_singletons.py`` the ``__init__`` method
guards re-instantiation::

    if DeltaGeneratorSingleton._instance is not None:
        raise RuntimeError("DeltaGeneratorSingleton instance already exists!")

When a second ``AppTest.from_file("app.py")`` runs in the same Python
process, the script thread's user-app import re-enters
``streamlit/__init__.py`` and triggers the guard. Six UI/Streamlit tests
are affected in this repo:

    - test_panel_routing                      (tests/test_agent_detective.py)
    - test_experiment_history_cycle           (tests/test_experiment_history.py)
    - test_ui_sync_slider_events              (tests/test_lab_realtime.py)
    - test_ui_dynamic_expansion               (tests/test_multi_planet_scaling.py)
    - test_ui_flow                            (tests/test_ui_flow.py)
    - test_workbench_navigation_persistence   (tests/test_workbench_navigation.py)

**Fix:** patch ``DeltaGeneratorSingleton.__init__`` for the duration of each
test so a fresh singleton can be created. The patch is restored after the
test. We DO NOT blank ``_instance = None`` ahead of the test: the
``_show_exception`` error-display path reads the class variable, and a
``None`` value during a test run causes a *different* failure mode
(``RuntimeError: DeltaGeneratorSingleton hasn't been created!``) on the
first exception in the script thread.

Root-cause analysis: ``reports/bucket0_diagnostic_findings.md`` §4 RC-2.
Bucket 5 is the test-infra bucket that fixes it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from streamlit.delta_generator_singletons import DeltaGeneratorSingleton


@pytest.fixture(autouse=True)
def _reset_streamlit_delta_generator_singleton():
    """Allow a fresh DeltaGeneratorSingleton to be created in each test."""
    original_init = DeltaGeneratorSingleton.__init__

    def _permissive_init(self, *args, **kwargs):
        # Allow a new instance to be created even if a previous test left
        # one set on the class. The new instance overwrites _instance.
        DeltaGeneratorSingleton._instance = None
        original_init(self, *args, **kwargs)

    DeltaGeneratorSingleton.__init__ = _permissive_init
    try:
        yield
    finally:
        DeltaGeneratorSingleton.__init__ = original_init


# ---------------------------------------------------------------------------
# save_experiment_log isolation fixture (bucket 9.2 Item 5)
# ---------------------------------------------------------------------------
# The detector's ``save_experiment_log`` (called from
# ``astraeus.analysis.detection.detect_transit_candidate``) appends a
# record to ``logs/experiments.json`` on every invocation. During a
# full fast-gate run, the file is mutated dozens of times — Bucket 9.1
# normalized this by committing the churn as ``chore(...)`` commits,
# which is undesirable (it dirties the repo on every CI run and makes
# test results non-hermetic).
#
# Two-part fix:
#
# 1. Function-scoped autouse fixture that patches
#    ``astraeus.analysis.detection.save_experiment_log`` to a no-op for
#    every test. This stops the detector's per-call mutation. Patched at
#    the detection.py call site (not the logging.py defining module)
#    because detection imports the symbol by name:
#        ``from astraeus.analysis.logging import save_experiment_log``
#    so the binding lives on ``astraeus.analysis.detection`` as
#    ``save_experiment_log``.
#
# 2. Session-scoped fixture that backs up ``logs/experiments.json`` at
#    session start and restores it at session end. This is needed
#    because ``tests/test_experiment_history.py::test_experiment_history_cycle``
#    imports ``save_experiment_log`` directly from the logging module
#    and calls it explicitly to test the save/load cycle (with explicit
#    file removal at start and cleanup at end). That test is a legitimate
#    exerciser of the production save/load cycle; we don't want to
#    change it. But we do want the file restored to its pre-session state
#    so the repo is not dirtied by the run.
#
# Why patch at the call site AND back up the file: the call-site patch
# eliminates the dominant source of churn (every detect_transit_candidate
# call writes), and the session backup handles the residual writes from
# the one test that legitimately exercises the save path.
@pytest.fixture(autouse=True)
def _suppress_save_experiment_log_during_tests():
    """Patch astraeus.analysis.detection.save_experiment_log to a no-op.

    This stops the test suite from mutating logs/experiments.json on
    every detector invocation, so the repo stays clean across CI runs.
    Verified: running the full fast gate twice in succession leaves
    ``git status --porcelain logs/experiments.json`` empty.
    """
    with patch(
        "astraeus.analysis.detection.save_experiment_log",
        lambda *args, **kwargs: None,
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def _backup_and_restore_experiments_json():
    """Session-scoped backup/restore of logs/experiments.json.

    At session start: if logs/experiments.json exists, record its bytes.
    At session end: restore the recorded bytes (or remove the file if it
    didn't exist at start). This makes the test suite hermetic w.r.t.
    the file regardless of which tests write to or delete it.
    """
    log_path = os.path.join("logs", "experiments.json")
    backup_bytes: bytes | None = None
    backup_existed = os.path.exists(log_path)
    if backup_existed:
        with open(log_path, "rb") as f:
            backup_bytes = f.read()
    try:
        yield
    finally:
        # Restore: if the file existed at start, write the backup back;
        # otherwise ensure the file is removed.
        if backup_existed and backup_bytes is not None:
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
            with open(log_path, "wb") as f:
                f.write(backup_bytes)
        else:
            if os.path.exists(log_path):
                os.remove(log_path)


# ---------------------------------------------------------------------------
# file_uploader test fixture
# ---------------------------------------------------------------------------
# Bucket 8 (fix/test-file-uploader-mocks) introduced a triplicated
# MagicMock pattern across test_agent_detective.py, test_ui_flow.py,
# and test_workbench_navigation.py to satisfy the file_uploader contract
# in ui/pages/detective.py:235-239. Bucket 9 (this branch, Item 4)
# dedupes that pattern.
#
# Why a dataclass and not a MagicMock: a MagicMock silently auto-satisfies
# ANY attribute access, so if the detective page later reads
# ``uploaded_file.size`` or ``uploaded_file.type`` (attributes real
# UploadedFile objects expose), the mock returns a child MagicMock instead
# of failing the test. A dataclass with only the contract fields raises
# AttributeError on out-of-contract access — that is the desired signal
# so the test catches unintended surface drift.
#
# Why a factory and not a fixture-with-path-parametrize: each call site
# writes its own dummy CSV to a different filename, then needs the
# fixture to read that exact file's bytes. A factory fixture is the
# simplest expression of that: the test creates the file, then calls
# ``fake_uploaded_file(test_csv)``.

@dataclass
class FakeUploadedFile:
    """Duck-typed stand-in for ``streamlit.runtime.uploaded_file_manager.UploadedFile``.

    Exposes ONLY the two attributes the detective page reads at
    ``ui/pages/detective.py:235-239``:
      - ``.getvalue()`` -> ``bytes``  (consumed by ``DataAdapter.__init__``)
      - ``.name``        -> ``str``   (e.g. ``"x.csv"``, drives format detection)

    Verified against ``astraeus.data.adapter.DataAdapter.__init__``
    (see Bucket 8 audit §5 smoke test) — ``DataAdapter(fake.getvalue(),
    fake.name).parse()`` returns a dict with ``'time'`` and ``'flux'``
    keys, exactly what the page's line-325 ``isinstance`` check needs.
    """
    _data: bytes
    name: str

    def getvalue(self) -> bytes:
        return self._data


@pytest.fixture
def fake_uploaded_file():
    """Factory fixture: build a ``FakeUploadedFile`` from a path on disk.

    Usage::

        def test_x(fake_uploaded_file):
            test_csv = "dummy.csv"
            with open(test_csv, "w") as f:
                f.write("time,flux\\n0.0,1.0\\n1.0,0.99\\n")
            try:
                with patch("ui.pages.detective.st.file_uploader",
                           return_value=fake_uploaded_file(test_csv)):
                    at = AppTest.from_file("app.py", default_timeout=60)
                    at.run()
                    ...
            finally:
                if os.path.exists(test_csv):
                    os.remove(test_csv)
    """
    def _make(path: str) -> FakeUploadedFile:
        with open(path, "rb") as f:
            data = f.read()
        return FakeUploadedFile(_data=data, name=path)
    return _make
