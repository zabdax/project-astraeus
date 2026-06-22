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
