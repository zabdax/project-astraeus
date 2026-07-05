"""Characterization test fixtures — wired to the Phase 0 seams.

Every characterization test injects fakes from ``tests/_fixtures/fakes.py``
via monkeypatching the production module globals. Production code paths
stay unchanged — the fakes are pre-loaded by the fixture function and
yielded to the test.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make tests/_fixtures/ importable as a non-package directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _fixtures.fakes import (  # noqa: E402  (sys.path manipulation above)
    FakeHttpClient,
    FakeFs,
    FakeClock,
    FakeLightkurveRow,
    FakeSearchResult,
)


@pytest.fixture
def fake_http() -> FakeHttpClient:
    """A pristine FakeHttpClient; tests queue responses per scenario."""
    return FakeHttpClient()


@pytest.fixture
def fake_fs() -> FakeFs:
    """A pristine FakeFs; tests stage files/dirs per scenario."""
    return FakeFs()


@pytest.fixture
def fake_clock() -> FakeClock:
    """A FakeClock starting at epoch 0."""
    return FakeClock(start=0.0)


@pytest.fixture
def fake_search_result() -> FakeSearchResult:
    """A 2-row FakeSearchResult pointing at staged cache files."""
    return FakeSearchResult(rows=[
        FakeLightkurveRow(download_path="/cache/tess_s001.fits", products=["tess1"]),
        FakeLightkurveRow(download_path="/cache/tess_s002.fits", products=["tess2"]),
    ])
